"""Export the calf for Unity (FBX: rig + LOD0/1/2 + one take per action) and for glTF engines (GLB: rig + LOD0).

Usage
  python3 tools/export_unity.py --in build/stage_d.blend --out-dir Unity/Calf [--tex-dir build/textures]
          [--actions Eating,Idle] [--keep-helpers] [--max-influences 4] [--weight-limit refit|truncate]
          [--name Calf] [--no-glb] [--no-fbx] [--validate]
  (dev)  python3 tools/export_unity.py --in build/stage_b_snapshot_v1.blend --out-dir build/export_test
  then   python3 tools/validate_export.py --fbx <out>/Calf.fbx --glb <out>/Calf.glb --src <blend>

Writes into --out-dir
  Calf.fbx                  armature node "CalfRig" + skinned Calf_LOD0/1/2 (Unity auto-builds a LODGroup from the
                            _LOD<n> suffixes), one take per action named exactly like the action, no leaf bones,
                            tangents exported, meters, Y up, calf facing +Z, identity transforms on every node above
                            the Root bone (see "Axes" below).
  Calf.glb                  glTF 2.0 binary: rig + Calf_LOD0 + one animation per action, textures embedded.
  Textures/                 copy of every image in --tex-dir (the FBX references them relatively: Textures/<file>).
  Calf_export_manifest.json what was exported (bones, dropped helpers, takes and frame ranges, LOD triangle counts,
                            influence clean-up stats, textures, exporter options); read by validate_export.py.

The source .blend is never modified: every change below happens in the in-memory session only.

What the tool does to the in-memory copy before exporting
  * Actions: every action whose F-curves all resolve on the armature is exported (or the --actions subset); other
    actions are deleted from the session so no exporter can pick them up.  The pose is reset to rest, the active
    action is cleared and the NLA is rebuilt with one track + strip per action, named like the action.  The FBX
    exporter's "NLA strips" mode then writes one take per strip, *named after the strip*, baked while only that
    strip is unmuted; channels a clip does not key come out at the rest pose.  The timeline is parked before all
    strips so the FBX default (bind-time) node transforms are the rest pose, not a blend of every strip.
    Blender 5 "All Actions" mode (--take-mode all_actions, diagnostic) does export every slotted action, but
      - the takes are named "CalfRig|Eating" (and so are the Unity clips);
      - unkeyed channels keep the pose captured at export start and unmuted NLA strips blend under every take: a
        naive export from a file with an active action leaked 198 mm of head motion into the other take in a leak
        test (tools/validate_export.py flags it); with the NLA off and the pose at rest the takes are exact;
      - a naive export also writes the current frame's pose as the default pose and the armature node rotated.
  * Helper bones: the IK pole helpers (PoleTarget*, unweighted leaf bones; the IK constraints that used them are
    baked away) are dropped unless --keep-helpers is given.  They are flagged non-deforming and the exporters run
    in deform-bones-only mode, which still keeps every non-deforming *parent* of a deforming bone (e.g. Root).
  * Skin weights: zero weights and groups that are not exported deforming bones are removed and every vertex is
    limited to --max-influences (4) bones with weights summing to 1.  The subdivided LODs have up to 7-8 influences
    per vertex; plain truncation to the 4 strongest bones (what Unity's import does) moves some neck/shoulder
    vertices by >1 cm when the head goes down.  Default --weight-limit refit: for each vertex over the limit, every
    4-bone subset of its (8 strongest) influences gets the weights that best reproduce the original all-influence
    deformation over <= --fit-frames poses sampled from all exported actions (least squares, sum = 1, >= 0, ridge
    toward the truncated weights), and the subset with the smallest worst-pose error wins.  Max deviation from the
    all-influence skin over every frame, LOD0: snapshot v1 (Eating/Idle) 12.97 mm truncated -> 2.37 mm refit;
    stage D (10 clips incl. gallop) 40.8 -> 23.5 mm (99.9th percentile 22.3 -> 9.9 mm).  The residual sits on the
    brisket midline, which the source weights split between both front legs; the real fix is to paint/limit those
    weights at stage B.  --weight-limit truncate gives the plain behaviour.
  * Polygons with more than 4 corners (if any) are triangulated, because tangents can only be exported for tris
    and quads.  Quads are kept: the exported tangents are Blender's MikkTSpace tangents of the quad mesh, i.e. the
    exact basis the Cycles normal-map bake used (Unity: Tangents = Import).
  * Material slots: M_Calf_Body is moved to the LAST slot of every LOD (source order: body, eye), so it is the last
    submesh in Unity: Unity/Calf/Fur/CalfFur.cs appends shell-fur materials, which Unity draws on the last submesh.
    Materials are remapped by name, so nothing else depends on the order (--keep-slot-order to disable).
  * Materials: images already used by the materials are re-pointed at the copies in <out>/Textures/.  If the
    materials have no image textures (stage B input) and --tex-dir holds the calf_textures.py outputs, a Principled
    network is wired from them (BaseColor, Normal, Roughness, AO -> glTF occlusion; eye BaseColor).

Axes and units (FBX)
  axis_forward='-Z', axis_up='Y'      Blender -Y (calf front) -> FBX +Z; Unity mirrors X on import, so the calf
                                      faces Unity +Z with Y up and its .L side on Unity -X (its own left).
  apply_scale_options='FBX_SCALE_ALL' coordinates stay in meters and UnitScaleFactor=100 (1 file unit = 100 cm), so
                                      Unity's "Convert Units" yields file scale 1.0 and every node has scale 1.
  bake_space_transform=True          the axis change is baked into mesh vertices, so the LOD nodes are identity.
  rig axis bake (this tool)          bake_space_transform does not apply to armatures (Blender would write the
                                      armature node with a -90 deg X rotation).  The rest pose is therefore rotated
                                      into FBX axes here and the armature object is given the inverse rotation,
                                      which the exporter's axis conversion cancels exactly: node "CalfRig" is
                                      written with identity transform and the bones are Y-up in Unity.
  primary/secondary bone axis Y/X    Blender's native bone frame; no correction matrix on every key.  Unity
                                      Generic rigs do not depend on bone axes (Humanoid does not apply to a
                                      quadruped).
  armature_nodetype='NULL'           the armature becomes a plain transform ("CalfRig"); 'ROOT'/'LIMBNODE' would
                                      add an extra skeleton joint above Root.
  bake_anim_simplify_factor=0.0      every frame keyed, no lossy curve simplification (Unity's clip compression
                                      then does its own error-bounded reduction).
"""
import argparse, json, math, os, re, shutil, sys, time

import bpy
from bpy_extras.io_utils import axis_conversion

T0 = time.time()
IMG_EXT = {".png", ".tga", ".jpg", ".jpeg", ".exr", ".tif", ".tiff", ".psd"}
LOD_RE = re.compile(r"_LOD(\d+)$")
# texture sets written by tools/calf_textures.py
BODY_TEX = {"base": "T_Calf_BaseColor", "normal": "T_Calf_Normal", "rough": "T_Calf_Roughness", "ao": "T_Calf_AO"}
EYE_TEX = {"base": "T_CalfEye_BaseColor", "normal": "T_CalfEye_Normal"}


def log(*a):
    print("[export_unity %6.1fs]" % (time.time() - T0), *a, flush=True)


# ============================================================================================ scene discovery
def find_rig(arm_name):
    arm = bpy.data.objects.get(arm_name)
    if arm is None or arm.type != "ARMATURE":
        arms = [o for o in bpy.data.objects if o.type == "ARMATURE"]
        if len(arms) != 1:
            raise SystemExit("need exactly one armature (or --armature NAME); found %s" % [o.name for o in arms])
        arm = arms[0]

    def skinned_by(o):
        return o.parent == arm or any(m.type == "ARMATURE" and m.object == arm for m in o.modifiers)
    lods = [o for o in bpy.data.objects if o.type == "MESH" and LOD_RE.search(o.name) and skinned_by(o)]
    lods.sort(key=lambda o: int(LOD_RE.search(o.name).group(1)))
    if not lods:
        raise SystemExit("no skinned *_LOD<n> meshes under %s" % arm.name)
    return arm, lods


def action_fcurves(act):
    for layer in act.layers:
        for strip in layer.strips:
            for cb in strip.channelbags:
                yield from cb.fcurves


def armature_actions(arm, wanted=None):
    """actions whose every F-curve resolves on the armature (the FBX exporter's own compatibility test)"""
    out = []
    for act in bpy.data.actions:
        fcs = list(action_fcurves(act))
        if not fcs or not act.slots:
            continue
        ok = True
        for fc in fcs:
            try:
                arm.path_resolve(fc.data_path + ("[%d]" % fc.array_index if fc.array_index else ""))
            except ValueError:
                ok = False
                break
        if ok:
            out.append(act)
    if wanted:
        names = {a.name for a in out}
        missing = [n for n in wanted if n not in names]
        if missing:
            raise SystemExit("actions not found / not compatible with %s: %s" % (arm.name, missing))
        out = [bpy.data.actions[n] for n in wanted]
    return out


def tri_count(me):
    return sum(len(p.vertices) - 2 for p in me.polygons)


# ============================================================================================ preparation
def reset_pose(arm):
    for pb in arm.pose.bones:
        pb.location = (0, 0, 0)
        pb.rotation_quaternion = (1, 0, 0, 0)
        pb.rotation_euler = (0, 0, 0)
        pb.rotation_axis_angle = (0, 0, 1, 0)
        pb.scale = (1, 1, 1)


def setup_nla(arm, actions):
    """one NLA track + strip per action, strip named like the action (= FBX take name); no active action"""
    ad = arm.animation_data or arm.animation_data_create()
    if ad.use_tweak_mode:
        ad.use_tweak_mode = False
    ad.action = None
    for t in list(ad.nla_tracks):
        ad.nla_tracks.remove(t)
    ad.use_nla = True
    for act in actions:
        tr = ad.nla_tracks.new()
        tr.name = act.name
        st = tr.strips.new(act.name, int(round(act.frame_range[0])), act)
        st.name = act.name
        if act.slots and st.action_slot is None:
            st.action_slot = act.slots[0]
        st.blend_type = "REPLACE"
        st.influence = 1.0
        st.extrapolation = "NOTHING"
    reset_pose(arm)


def helper_bones(arm, lods, pattern):
    """unweighted leaf bones whose name matches `pattern` (IK pole helpers)"""
    weighted = set()
    for o in lods:
        names = [g.name for g in o.vertex_groups]
        for v in o.data.vertices:
            for g in v.groups:
                if g.weight > 0:
                    weighted.add(names[g.group])
    rx = re.compile(pattern)
    return [b.name for b in arm.data.bones if rx.search(b.name) and not b.children and b.name not in weighted]


def skin_samples(arm, actions, bone_names, max_frames):
    """armature-space skinning matrices (pose @ rest^-1, 3x4) of `bone_names` on frames sampled evenly from every
    action (at most `max_frames` in total), evaluated like the exported takes: pose reset, one action at a time"""
    import numpy as np
    sc = bpy.context.scene
    ad = arm.animation_data or arm.animation_data_create()
    frames = [(act, f) for act in actions for f in range(int(act.frame_range[0]), int(act.frame_range[1]) + 1)]
    if not frames:
        return None
    stride = max(1, int(math.ceil(len(frames) / float(max_frames))))
    frames = frames[::stride]
    hidden = [(o, o.hide_viewport) for o in bpy.data.objects if o.type == "MESH"]
    for o, _ in hidden:
        o.hide_viewport = True          # pose sampling without evaluating the meshes
    use_nla, back = ad.use_nla, sc.frame_current
    ad.use_nla = False
    rest_inv = [arm.data.bones[n].matrix_local.inverted() for n in bone_names]
    out, cur = np.empty((len(frames), len(bone_names), 3, 4)), None
    for k, (act, f) in enumerate(frames):
        if act is not cur:
            ad.action = act
            if act.slots:
                ad.action_slot = act.slots[0]
            reset_pose(arm)
            cur = act
        sc.frame_set(f)
        for j, n in enumerate(bone_names):
            out[k, j] = np.array(arm.pose.bones[n].matrix @ rest_inv[j])[:3]
    ad.action = None
    ad.use_nla = use_nla
    reset_pose(arm)
    sc.frame_set(back)
    for o, h in hidden:
        o.hide_viewport = h
    return out


def fit_four(p, S, w, max_inf, lam):
    """Best <= max_inf bone subset + weights (sum 1, >= 0) reproducing the all-influence skinning of point p over the
    sampled poses S (F, n, 3, 4):  min_u |A u - b|^2 + lam F |u - u0|^2,  u0 = truncated renormalised weights.
    All subsets are solved at once (normal equations + sum-to-one KKT row); the subset with the smallest worst-pose
    error wins."""
    import itertools
    import numpy as np
    F, n = S.shape[0], S.shape[1]
    X = np.einsum("fbij,j->bfi", S, np.r_[p, 1.0]).reshape(n, -1)      # (n, 3F) point moved by each bone
    tgt = w @ X
    G, c = X @ X.T, X @ tgt
    subs = np.array(list(itertools.combinations(range(n), max_inf)))    # (m, k)
    k = max_inf
    u0 = w[subs] / w[subs].sum(1, keepdims=True)
    Gs = G[subs[:, :, None], subs[:, None, :]]
    K = np.zeros((len(subs), k + 1, k + 1))
    K[:, :k, :k] = Gs + lam * F * np.eye(k)
    K[:, :k, k] = 1.0
    K[:, k, :k] = 1.0
    rhs = np.concatenate([c[subs] + lam * F * u0, np.ones((len(subs), 1))], 1)
    u = np.linalg.solve(K, rhs[..., None])[:, :k, 0]
    neg = (u < 0).any(1)
    if neg.any():
        un = np.clip(u[neg], 0.0, None)
        sm = un.sum(1, keepdims=True)
        u[neg] = np.where(sm > 0, un / np.maximum(sm, 1e-12), u0[neg])
    res = np.einsum("mk,mkq->mq", u, X[subs]) - tgt                       # (m, 3F) residuals
    err = np.sqrt((res.reshape(len(subs), F, 3) ** 2).sum(2)).max(1)       # worst sampled pose per subset
    b = int(np.argmin(err))
    return float(err[b]), list(subs[b]), u[b]


_WEIGHT_CACHE = {}


def limit_weights(obj, arm, bone_names, max_inf, fit=None):
    """<= max_inf influences per vertex, weights normalised.  Vertices over the limit are either truncated to their
    strongest bones (fit=None) or refit (fit=(S, bone index, lam)): the bone subset and weights that best reproduce
    the original all-influence deformation over the sampled animation poses."""
    import numpy as np
    vgs = obj.vertex_groups
    names = [g.name for g in vgs]
    usable = [n in bone_names for n in names]
    st = {"verts": len(obj.data.vertices), "max_before": 0, "max_after": 0, "over_limit": 0,
          "zero_or_foreign_removed": 0, "max_dropped_weight": 0.0, "unweighted": 0,
          "method": "lsq-refit" if fit else "truncate"}
    to_arm = arm.matrix_world.inverted() @ obj.matrix_world
    removals, sets = {}, []
    err_trunc, err_fit = [], []
    for v in obj.data.vertices:
        gs = [(g.group, g.weight) for g in v.groups]
        keep = [(gi, w) for gi, w in gs if w > 0.0 and usable[gi]]
        st["max_before"] = max(st["max_before"], len(keep))
        keep.sort(key=lambda t: (-t[1], names[t[0]]))
        tot = sum(w for _, w in keep)
        if len(keep) > max_inf:
            st["over_limit"] += 1
            st["max_dropped_weight"] = max(st["max_dropped_weight"], sum(w for _, w in keep[max_inf:]) / tot)
            if fit is not None and (obj.name, v.index) in _WEIGHT_CACHE:
                keep, et, ef = _WEIGHT_CACHE[(obj.name, v.index)]
                err_trunc.append(et)
                err_fit.append(ef)
                keep = [(names.index(nm), w) for nm, w in keep]
            elif fit is not None and fit[0] is not None:
                S, bidx, lam = fit
                cand = keep[:8]                   # C(8,4) = 70 subsets at most
                w = np.array([x[1] for x in cand]) / sum(x[1] for x in cand)
                Sv = S[:, [bidx[names[gi]] for gi, _ in cand]]
                p = np.array(to_arm @ v.co)
                e, sub, u = fit_four(p, Sv, w, max_inf, lam)
                ut = w[:max_inf] / w[:max_inf].sum()
                A = np.einsum("fbij,j->fbi", Sv, np.r_[p, 1.0])
                full = np.einsum("b,fbi->fi", w, A)
                err_trunc.append(float(np.linalg.norm(np.einsum("b,fbi->fi", ut, A[:, :max_inf]) - full, axis=1).max()))
                err_fit.append(float(np.linalg.norm(np.einsum("b,fbi->fi", u, A[:, sub]) - full, axis=1).max()))
                keep = [(cand[k][0], float(u[i])) for i, k in enumerate(sub) if u[i] > 0.0]
                _WEIGHT_CACHE[(obj.name, v.index)] = ([(names[gi], w) for gi, w in keep], err_trunc[-1], err_fit[-1])
            else:
                keep = keep[:max_inf]
        s = sum(w for _, w in keep)
        if s <= 0.0:
            st["unweighted"] += 1
            continue
        target = {gi: w / s for gi, w in keep}
        for gi, w in gs:
            if gi not in target:
                removals.setdefault(gi, []).append(v.index)
                if w <= 0.0 or not usable[gi]:
                    st["zero_or_foreign_removed"] += 1
        for gi, w in target.items():
            sets.append((gi, v.index, w))
        st["max_after"] = max(st["max_after"], len(target))
    for gi, idx in removals.items():
        vgs[gi].remove(idx)
    for gi, vi, w in sets:
        vgs[gi].add([vi], w, "REPLACE")
    if err_fit:
        st["sampled_max_error_mm_truncate"] = round(max(err_trunc) * 1000, 3)
        st["sampled_max_error_mm_refit"] = round(max(err_fit) * 1000, 3)
    return st


def body_last(obj, body):
    """Move the body material to the LAST slot (Unity: last submesh).  Unity draws extra materials of a renderer on its
    last submesh; Unity/Calf/Fur/CalfFur.cs appends its shell materials that way, so the body must be last."""
    import numpy as np
    me = obj.data
    order = [m for m in me.materials]
    if body not in order or order[-1] == body:
        return False
    new = [m for m in order if m != body] + [body]
    remap = np.array([new.index(m) for m in order], dtype=np.int32)
    idx = np.empty(len(me.polygons), dtype=np.int32)
    me.polygons.foreach_get("material_index", idx)
    for i, m in enumerate(new):
        me.materials[i] = m
    me.polygons.foreach_set("material_index", remap[np.clip(idx, 0, len(order) - 1)])
    me.update()
    return True


def triangulate_ngons(obj):
    import bmesh
    me = obj.data
    if not any(len(p.vertices) > 4 for p in me.polygons):
        return 0
    bm = bmesh.new()
    bm.from_mesh(me)
    ng = [f for f in bm.faces if len(f.verts) > 4]
    bmesh.ops.triangulate(bm, faces=ng, quad_method="FIXED", ngon_method="BEAUTY")
    bm.to_mesh(me)
    bm.free()
    return len(ng)


# ============================================================================================ textures
def copy_textures(tex_dir, out_tex):
    if not tex_dir or not os.path.isdir(tex_dir):
        return {}
    # authoring intermediates that no Unity material uses (16-bit fur height used only for the normal bake)
    skip = {"T_Calf_Height"}
    files = sorted(f for f in os.listdir(tex_dir)
                   if os.path.splitext(f)[1].lower() in IMG_EXT and os.path.splitext(f)[0] not in skip)
    if not files:
        return {}
    os.makedirs(out_tex, exist_ok=True)
    out = {}
    for f in files:
        dst = os.path.join(out_tex, f)
        shutil.copy2(os.path.join(tex_dir, f), dst)
        out[os.path.splitext(f)[0]] = dst
    return out


def material_images(mat):
    if not mat or not mat.node_tree:
        return []
    return [n for n in mat.node_tree.nodes if n.type == "TEX_IMAGE" and n.image is not None]


def gltf_output_group():
    ng = bpy.data.node_groups.get("glTF Material Output")
    if ng is None:
        ng = bpy.data.node_groups.new("glTF Material Output", "ShaderNodeTree")
        ng.interface.new_socket("Occlusion", in_out="INPUT", socket_type="NodeSocketFloat")
    return ng


def link_occlusion(mat, ao_img_node):
    nt = mat.node_tree
    if any(n.type == "GROUP" and n.node_tree and n.node_tree.name.lower() in ("gltf material output", "gltf settings")
           and n.inputs.get("Occlusion") and n.inputs["Occlusion"].is_linked for n in nt.nodes):
        return False
    g = nt.nodes.new("ShaderNodeGroup")
    g.node_tree = gltf_output_group()
    g.location = (ao_img_node.location.x + 350, ao_img_node.location.y)
    nt.links.new(ao_img_node.outputs["Color"], g.inputs["Occlusion"])
    return True


def load_img(path, noncolor):
    img = bpy.data.images.load(path, check_existing=True)
    img.colorspace_settings.name = "Non-Color" if noncolor else "sRGB"
    return img


def wire_textures(mats, tex):
    """materials without image textures (stage B input): build a Principled network from calf_textures outputs"""
    done = []
    body, eye = mats.get("body"), mats.get("eye")
    if body and not material_images(body) and BODY_TEX["base"] in tex:
        nt = body.node_tree
        bs = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
        if bs is not None:
            uv = nt.nodes.new("ShaderNodeUVMap"); uv.uv_map = "UVMap"; uv.location = (-900, 0)

            def tnode(key, noncolor, y):
                t = nt.nodes.new("ShaderNodeTexImage"); t.image = load_img(tex[key], noncolor)
                t.location = (-600, y); nt.links.new(uv.outputs[0], t.inputs["Vector"])
                return t
            nt.links.new(tnode(BODY_TEX["base"], False, 300).outputs["Color"], bs.inputs["Base Color"])
            if BODY_TEX["rough"] in tex:
                nt.links.new(tnode(BODY_TEX["rough"], True, 0).outputs["Color"], bs.inputs["Roughness"])
            if BODY_TEX["normal"] in tex:
                nm = nt.nodes.new("ShaderNodeNormalMap"); nm.uv_map = "UVMap"; nm.location = (-250, -300)
                nt.links.new(tnode(BODY_TEX["normal"], True, -300).outputs["Color"], nm.inputs["Color"])
                nt.links.new(nm.outputs["Normal"], bs.inputs["Normal"])
            if BODY_TEX["ao"] in tex:
                link_occlusion(body, tnode(BODY_TEX["ao"], True, -600))
            done.append(body.name)
    if eye and not material_images(eye) and EYE_TEX["base"] in tex:
        nt = eye.node_tree
        bs = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
        if bs is not None:
            t = nt.nodes.new("ShaderNodeTexImage"); t.image = load_img(tex[EYE_TEX["base"]], False); t.location = (-600, 0)
            nt.links.new(t.outputs["Color"], bs.inputs["Base Color"])
            if EYE_TEX["normal"] in tex:
                n = nt.nodes.new("ShaderNodeTexImage"); n.image = load_img(tex[EYE_TEX["normal"]], True); n.location = (-600, -300)
                nm = nt.nodes.new("ShaderNodeNormalMap"); nm.location = (-250, -300)
                nt.links.new(n.outputs["Color"], nm.inputs["Color"]); nt.links.new(nm.outputs["Normal"], bs.inputs["Normal"])
            done.append(eye.name)
    return done


def retarget_images(mats, tex, out_tex):
    """point every image used by the calf materials at its copy in <out>/Textures (writing packed ones there)"""
    info = []
    seen = set()
    for m in mats.values():
        for n in material_images(m):
            img = n.image
            if img.name in seen:
                continue
            seen.add(img.name)
            src = bpy.path.abspath(img.filepath) if img.filepath else ""
            stem = os.path.splitext(os.path.basename(src))[0] if src else img.name
            if stem in tex:
                img.filepath = tex[stem]
            elif img.packed_file is not None:
                os.makedirs(out_tex, exist_ok=True)
                ext = os.path.splitext(src)[1] or ".png"
                dst = os.path.join(out_tex, bpy.path.clean_name(stem) + ext)
                with open(dst, "wb") as fh:
                    fh.write(img.packed_file.data)
                img.filepath = dst
                tex[stem] = dst
            elif src and os.path.isfile(src):
                os.makedirs(out_tex, exist_ok=True)
                dst = os.path.join(out_tex, os.path.basename(src))
                if not os.path.exists(dst):
                    shutil.copy2(src, dst)
                img.filepath = dst
                tex[stem] = dst
            else:
                log("WARNING: image %s (%s) not found; it will be missing in the export" % (img.name, src))
            img.reload()
            info.append((m.name, n.name, img.name, os.path.basename(bpy.path.abspath(img.filepath))))
        # AO image node left unconnected by calf_textures.py -> glTF occlusion slot
        for n in material_images(m):
            if re.search(r"_AO$", os.path.splitext(os.path.basename(n.image.filepath or n.image.name))[0]) \
                    and not any(l.from_node == n for l in m.node_tree.links):
                link_occlusion(m, n)
    return info


# ============================================================================================ rig axis bake
def bake_rig_axes(arm, meshes, G):
    """Rotate the armature REST pose into FBX axes and give the armature object the inverse rotation.

    World-space rest and animated poses are unchanged (bone channels are relative to the rest pose), but the FBX
    exporter's axis conversion G then cancels on the armature node: FBX node CalfRig = G @ G^-1 = identity.
    Meshes are re-parented with a compensating parent-inverse so they stay at identity in world space."""
    worlds = {m.name: m.matrix_world.copy() for m in meshes}
    for m in meshes:
        m.parent = None
        m.matrix_world = worlds[m.name]
    T = G @ arm.matrix_world
    bpy.context.view_layer.objects.active = arm
    for o in bpy.context.view_layer.objects:
        o.select_set(o == arm)
    bpy.ops.object.mode_set(mode="EDIT")
    for eb in arm.data.edit_bones:
        eb.transform(T, scale=True, roll=True)
    bpy.ops.object.mode_set(mode="OBJECT")
    arm.matrix_world = G.inverted()
    bpy.context.view_layer.update()
    for m in meshes:
        m.parent = arm
        m.matrix_parent_inverse = arm.matrix_world.inverted()
        m.matrix_world = worlds[m.name]
    bpy.context.view_layer.update()


# ============================================================================================ main
def prepare(a, blend):
    """open the blend and apply every in-memory change shared by both exports; returns a context dict"""
    bpy.ops.wm.open_mainfile(filepath=blend)
    sc = bpy.context.scene
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    arm, lods = find_rig(a.armature)
    actions = armature_actions(arm, [s for s in a.actions.split(",") if s] if a.actions else None)
    for act in list(bpy.data.actions):
        if act not in actions:
            bpy.data.actions.remove(act)
    for pb in arm.pose.bones:
        if pb.constraints:
            log("WARNING: bone %s has constraints %s; they are evaluated (baked) into the takes"
                % (pb.name, [c.type for c in pb.constraints]))
    dropped = [] if a.keep_helpers else helper_bones(arm, lods, a.helper_pattern)
    for n in dropped:
        arm.data.bones[n].use_deform = False
    exported_bones = []
    for b in arm.data.bones:        # deform-only export keeps non-deforming parents of deforming bones
        if b.use_deform or any(c.use_deform for c in b.children_recursive):
            exported_bones.append(b.name)
    non_deform_kept = [n for n in exported_bones if not arm.data.bones[n].use_deform]
    weight_stats = {}
    fit = None
    deform = [n for n in exported_bones if arm.data.bones[n].use_deform]
    if a.weight_limit == "refit" and actions and _WEIGHT_CACHE:
        fit = (None, None, a.fit_lambda)        # second pass: reuse the refit of the first pass
    elif a.weight_limit == "refit" and actions:
        S = skin_samples(arm, actions, deform, a.fit_frames)
        fit = (S, {n: j for j, n in enumerate(deform)}, a.fit_lambda) if S is not None else None
    for o in lods:
        weight_stats[o.name] = limit_weights(o, arm, set(deform), a.max_influences, fit)
        weight_stats[o.name]["ngons_triangulated"] = triangulate_ngons(o)
    setup_nla(arm, actions)
    # material slots (0 body, 1 eye by convention; fall back to names)
    mats = {}
    for o in lods:
        for i, s in enumerate(o.material_slots):
            if s.material:
                key = "eye" if ("eye" in s.material.name.lower() or i == 1) else "body"
                mats.setdefault(key, s.material)
    if not a.keep_slot_order and mats.get("body"):
        for o in lods:
            body_last(o, mats["body"])
    for o in [arm] + lods:
        o.hide_viewport = False
        o.hide_select = False
        try:
            o.hide_set(False)
        except RuntimeError:        # not in the view layer
            pass
    # Park the timeline before every strip (extrapolation NOTHING): nothing is evaluated there, so the pose written
    # as the FBX nodes' default transforms (Unity's model pose) is the rest pose, not a blend of all strips.
    park = int(min([act.frame_range[0] for act in actions] + [0])) - 1000
    sc.frame_set(park)
    reset_pose(arm)
    return {"scene": sc, "arm": arm, "lods": lods, "actions": actions, "dropped": dropped,
            "bones": exported_bones, "non_deform_kept": non_deform_kept, "weights": weight_stats, "mats": mats}


def select_only(objs):
    bpy.context.view_layer.objects.active = objs[0]
    for o in bpy.context.view_layer.objects:
        o.select_set(o in objs)


def export_glb(a, C, tex, out_tex, path):
    wired = wire_textures(C["mats"], tex) if tex else []
    retarget_images(C["mats"], tex, out_tex)
    arm, lod0 = C["arm"], C["lods"][0]
    mw = lod0.matrix_world.copy()
    lod0.parent = None              # skinned mesh node at the glTF scene root (parent transforms do not apply
    lod0.matrix_world = mw          # to skinned meshes; Khronos warns NODE_SKINNED_MESH_NON_ROOT otherwise)
    select_only([arm, lod0])
    bpy.ops.export_scene.gltf(
        filepath=path, export_format="GLB", use_selection=True, export_apply=False, export_yup=True,
        export_texcoords=True, export_normals=True, export_tangents=True, export_materials="EXPORT",
        export_image_format="AUTO", export_attributes=False, export_vertex_color="NONE", export_extras=False,
        export_cameras=False, export_lights=False, export_morph=False,
        export_skins=True, export_influence_nb=a.max_influences, export_all_influences=False,
        export_def_bones=True, export_leaf_bone=False, export_rest_position_armature=True,
        export_armature_object_remove=False,
        export_animations=True, export_animation_mode="ACTIONS", export_anim_single_armature=True,
        export_reset_pose_bones=True, export_force_sampling=True, export_frame_step=1,
        export_anim_slide_to_zero=True, export_optimize_animation_size=True,
        export_optimize_animation_keep_anim_armature=True, export_bake_animation=False)
    return wired


def export_fbx(a, C, tex, out_tex, path):
    wire_textures(C["mats"], tex) if tex else None
    retarget_images(C["mats"], tex, out_tex)
    arm, lods = C["arm"], C["lods"]
    G = axis_conversion(from_forward="Y", from_up="Z", to_forward="-Z", to_up="Y").to_4x4()
    if not a.no_rig_axis_bake:
        bake_rig_axes(arm, lods, G)
    reset_pose(arm)
    C["scene"].frame_set(C["scene"].frame_current)
    select_only([arm] + lods)
    kw = dict(
        filepath=path, use_selection=True, use_visible=False, use_active_collection=False,
        object_types={"ARMATURE", "MESH"},
        global_scale=1.0, apply_unit_scale=True, apply_scale_options="FBX_SCALE_ALL",
        axis_forward="-Z", axis_up="Y", bake_space_transform=True,
        use_mesh_modifiers=True, use_mesh_modifiers_render=True, mesh_smooth_type="FACE", use_subsurf=False,
        use_mesh_edges=False, use_tspace=True, use_triangles=False, use_custom_props=False,
        colors_type="NONE", prioritize_active_color=False,
        add_leaf_bones=False, primary_bone_axis="Y", secondary_bone_axis="X",
        use_armature_deform_only=True, armature_nodetype="NULL",
        bake_anim=True, bake_anim_use_all_bones=True,
        bake_anim_use_nla_strips=(a.take_mode == "nla"), bake_anim_use_all_actions=(a.take_mode == "all_actions"),
        bake_anim_force_startend_keying=True, bake_anim_step=1.0, bake_anim_simplify_factor=0.0,
        path_mode="RELATIVE", embed_textures=False, batch_mode="OFF", use_metadata=True)
    if a.take_mode == "all_actions":
        # Blender's own mode: the NLA must be off (strips would blend under the active action and leak into
        # every take) and the pose at rest (unkeyed channels are restored to the pose captured at export start)
        ad = C["arm"].animation_data
        ad.action = None
        for t in ad.nla_tracks:
            t.mute = True
        ad.use_nla = False
        reset_pose(C["arm"])
    bpy.ops.export_scene.fbx(**kw)
    kw.pop("filepath")
    kw["object_types"] = sorted(kw["object_types"])
    return kw


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="inp", required=True, help="source .blend (never modified)")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--tex-dir", default=None, help="textures to copy into <out>/Textures (optional)")
    ap.add_argument("--name", default="Calf", help="base name of the exported files")
    ap.add_argument("--armature", default="CalfRig")
    ap.add_argument("--actions", default="", help="comma list; default = every action compatible with the rig")
    ap.add_argument("--keep-helpers", action="store_true", help="keep the unweighted PoleTarget* helper bones")
    ap.add_argument("--helper-pattern", default=r"^PoleTarget")
    ap.add_argument("--max-influences", type=int, default=4)
    ap.add_argument("--weight-limit", choices=("refit", "truncate"), default="refit",
                    help="vertices over the influence limit: refit = least-squares refit of the best bone subset over "
                         "sampled animation poses (default); truncate = keep the strongest bones and renormalise "
                         "(what Unity's own 4-bone limit does)")
    ap.add_argument("--fit-frames", type=int, default=240, help="max sampled frames (all actions) for the refit")
    ap.add_argument("--fit-lambda", type=float, default=1e-4,
                    help="refit regularisation toward the truncated weights (per frame, m^2 per unit weight^2)")
    ap.add_argument("--take-mode", choices=("nla", "all_actions"), default="nla",
                    help="nla: takes named like the actions (default); all_actions: Blender's 'All Actions' mode "
                         "(takes named 'CalfRig|<action>'; diagnostic)")
    ap.add_argument("--no-rig-axis-bake", action="store_true",
                    help="diagnostic: leave the armature node with the -90 deg X axis rotation")
    ap.add_argument("--keep-slot-order", action="store_true",
                    help="keep the source material slot order (default: M_Calf_Body is moved to the last slot = last "
                         "Unity submesh, which the optional shell fur component Unity/Calf/Fur/CalfFur.cs relies on)")
    ap.add_argument("--validate", action="store_true", help="run tools/validate_export.py on the result")
    ap.add_argument("--no-fbx", action="store_true")
    ap.add_argument("--no-glb", action="store_true")
    a = ap.parse_args(argv)

    blend = os.path.abspath(a.inp)
    out_dir = os.path.abspath(a.out_dir)
    os.makedirs(out_dir, exist_ok=True)
    out_tex = os.path.join(out_dir, "Textures")
    if os.path.isdir(out_tex):      # repopulated below; Unity .meta files are left alone so GUIDs survive
        for f in os.listdir(out_tex):
            if os.path.splitext(f)[1].lower() in IMG_EXT:
                os.remove(os.path.join(out_tex, f))
    tex = copy_textures(os.path.abspath(a.tex_dir) if a.tex_dir else None, out_tex)
    log("textures copied: %d %s" % (len(tex), "" if tex else "(no --tex-dir or it is empty/missing)"))
    fbx_path = os.path.join(out_dir, a.name + ".fbx")
    glb_path = os.path.join(out_dir, a.name + ".glb")
    manifest = {"source": blend, "source_mtime": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(os.path.getmtime(blend))),
                "exported": time.strftime("%Y-%m-%dT%H:%M:%S"), "blender": bpy.app.version_string, "files": {}}

    if not a.no_glb:
        C = prepare(a, blend)
        wired = export_glb(a, C, dict(tex), out_tex, glb_path)
        log("GLB written", glb_path, "(%.2f MB)" % (os.path.getsize(glb_path) / 1e6), "wired:", wired)
        manifest["files"][os.path.basename(glb_path)] = os.path.getsize(glb_path)
        manifest["glb"] = {"objects": [C["arm"].name, C["lods"][0].name], "textures_wired": wired}

    C = prepare(a, blend)
    sc, arm = C["scene"], C["arm"]
    fps = sc.render.fps / sc.render.fps_base
    manifest.update({
        "armature": arm.name,
        "fps": fps,
        "bones": C["bones"],
        "bones_source": [b.name for b in arm.data.bones],
        "dropped_helper_bones": C["dropped"],
        "helper_policy": "kept (--keep-helpers)" if a.keep_helpers else
            "dropped: unweighted leaf IK pole helpers; clips are baked FK so nothing references them",
        "non_deforming_bones_kept": C["non_deform_kept"],
        "lods": {o.name: {"tris": tri_count(o.data), "verts": len(o.data.vertices), "polys": len(o.data.polygons),
                          "materials": [s.material.name if s.material else None for s in o.material_slots]}
                 for o in C["lods"]},
        "weights": C["weights"],
        "max_influences": a.max_influences,
        "takes": [{"name": act.name, "frame_start": act.frame_range[0], "frame_end": act.frame_range[1],
                   "frames": int(round(act.frame_range[1] - act.frame_range[0])) + 1,
                   "seconds": (act.frame_range[1] - act.frame_range[0]) / fps,
                   "cyclic": bool(act.use_cyclic),
                   "root_motion": any(fc.data_path.startswith('pose.bones["Root"]') and
                                      len({round(k.co[1], 6) for k in fc.keyframe_points}) > 1
                                      for fc in action_fcurves(act))}
                  for act in C["actions"]],
    })
    for n, s in C["weights"].items():
        log("%s: max influences %d -> %d, %d verts over the limit (max weight outside the 4 strongest %.3f), %d "
            "zero/foreign entries removed; %s%s" % (n, s["max_before"], s["max_after"], s["over_limit"],
                                                  s["max_dropped_weight"], s["zero_or_foreign_removed"], s["method"],
            (": sampled max deviation from the all-influence skin %.2f mm truncated -> %.2f mm refit"
             % (s["sampled_max_error_mm_truncate"], s["sampled_max_error_mm_refit"]))
            if "sampled_max_error_mm_refit" in s else ""))
    log("bones exported: %d of %d; dropped helpers: %s" % (len(C["bones"]), len(arm.data.bones), C["dropped"]))
    log("takes:", ", ".join("%s [%g-%g]" % (t["name"], t["frame_start"], t["frame_end"]) for t in manifest["takes"]))

    if not a.no_fbx:
        opts = export_fbx(a, C, tex, out_tex, fbx_path)
        manifest["fbx_options"] = opts
        manifest["rig_axis_bake"] = not a.no_rig_axis_bake
        manifest["files"][os.path.basename(fbx_path)] = os.path.getsize(fbx_path)
        log("FBX written", fbx_path, "(%.2f MB)" % (os.path.getsize(fbx_path) / 1e6))
    texfiles = sorted(f for f in os.listdir(out_tex) if os.path.splitext(f)[1].lower() in IMG_EXT) \
        if os.path.isdir(out_tex) else []
    manifest["textures"] = texfiles
    for f in texfiles:
        manifest["files"]["Textures/" + f] = os.path.getsize(os.path.join(out_tex, f))
    log("textures in %s: %s" % (out_tex, texfiles or "none"))
    with open(os.path.join(out_dir, a.name + "_export_manifest.json"), "w") as fh:
        json.dump(manifest, fh, indent=1)
    log("manifest written; done")
    if a.validate and not (a.no_fbx or a.no_glb):
        import subprocess
        r = subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "validate_export.py"),
                            "--fbx", fbx_path, "--glb", glb_path, "--src", blend])
        sys.exit(r.returncode)


if __name__ == "__main__":
    main(sys.argv[1:])
