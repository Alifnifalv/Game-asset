"""Animation sanity check: calf rig vs the original cow.glb.

For every key time of every bone action ("Eating", "Idle") it measures
  1. leg / foot consistency
       gap   = world distance lower-leg bone tail (FrontLowerLeg.X / BackLowerLeg.X) ->
               foot bone head (IKFrontLeg.X / IKBackLeg.X), / withers height
       tip   = world distance between the lower leg's real chain end and the foot bone head, / withers.
               glTF stores no bone tails, so the importer invents the tail of the leaf bone
               FrontLowerLeg/BackLowerLeg (it ends ~0.13 x withers below the foot bone head, under the
               ground). The real IK chain end is the point fixed in lower-leg space that coincides with
               the foot bone head in the rest pose. In the original the IK bake keeps tip ~ 0 on every
               frame (and therefore gap == rest gap); tip > 0 in the calf means the leg and the hoof
               (skinned to the foot bones) separate / stretch at the fetlock.
  2. mesh stretching: evaluated edge length / rest edge length on sampled key times, with the
     dominant bones of the worst edges (whole mesh, leg region and fetlock = lower-leg<->foot seam).
     The original is measured as imported (cage) and with the same subdiv-2 the calf LOD0 uses.
  3. loop quality (first vs last sample per bone), frame rate / key spacing, root motion.

Usage
  python3 tools/check_animation.py [--calf build/stage_b.blend] [--orig cow.glb] [--no-orig]
        [--calf-meshes Calf_LOD0,Calf_LOD2] [--mesh-step 4] [--integer-frames] [--json out.json]
"""
import argparse, json, math, os, re, struct, sys, time
import numpy as np
import bpy
from mathutils import Vector, Matrix, Quaternion

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

LEGS = [  # (label, lower-leg bone, foot / IK-target bone)
    ("front.L", "FrontLowerLeg.L", "IKFrontLeg.L"),
    ("front.R", "FrontLowerLeg.R", "IKFrontLeg.R"),
    ("back.L", "BackLowerLeg.L", "IKBackLeg.L"),
    ("back.R", "BackLowerLeg.R", "IKBackLeg.R"),
]
LEG_BONES = {"FrontUpperLeg", "FrontLowerLeg", "IKFrontLeg", "FF",
             "BackLeg", "BackUpperLeg", "BackLowerLeg", "IKBackLeg", "FFB"}
FETLOCK = ({"FrontLowerLeg", "BackLowerLeg"}, {"IKFrontLeg", "FF", "IKBackLeg", "FFB"})


def clean(n):
    """cow.glb bone names -> clean names used by the calf (FrontLowerLeg.L_5 -> FrontLowerLeg.L)."""
    return "Root" if n == "GLTF_created_0_rootJoint" else re.sub(r"_\d+$", "", n)


def base(n):
    return n.split(".")[0]


# ------------------------------------------------------------------------------------------
# loading / actions
def load(path):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    ext = os.path.splitext(path)[1].lower()
    if ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=path)
    elif ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=path)
    else:
        bpy.ops.wm.open_mainfile(filepath=path)
    sc = bpy.context.scene
    arms = [o for o in sc.objects if o.type == "ARMATURE"]
    arm = max(arms, key=lambda o: len(o.data.bones))
    names = {clean(b.name): b.name for b in arm.data.bones}
    return sc, arm, names


def skinned_meshes(sc, arm, only=None):
    out = [o for o in sc.objects if o.type == "MESH" and (only is None or o.name in only)
           and any(m.type == "ARMATURE" and m.object == arm for m in o.modifiers)]
    if only is not None:
        out.sort(key=lambda o: only.index(o.name))
    return out


def channelbags(act):
    for l in act.layers:
        for s in l.strips:
            for cb in s.channelbags:
                yield cb


def bone_actions():
    acts = [a for a in bpy.data.actions
            if any(fc.data_path.startswith("pose.bones") for cb in channelbags(a) for fc in cb.fcurves)]
    return sorted(acts, key=lambda a: a.name)


def use_action(arm, act):
    """Assign `act` to the armature; mute NLA everywhere so only this action evaluates."""
    for o in bpy.context.scene.objects:
        ad = o.animation_data
        if ad:
            for t in ad.nla_tracks:
                t.mute = True
            if o is not arm and ad.action is not None:
                ad.action = None
    ad = arm.animation_data or arm.animation_data_create()
    ad.action = act
    if act is not None and act.slots:
        slot = next((s for s in act.slots if s.identifier == "OB" + arm.name), None)
        if slot is None and ad.action_slot is None:
            slot = act.slots[0]
        if slot is not None:
            ad.action_slot = slot


def frame_range(act):
    f0, f1 = act.frame_range
    return int(math.floor(f0 + 1e-4)), int(math.ceil(f1 - 1e-4))


def key_times(act):
    return sorted({round(kp.co[0], 4) for cb in channelbags(act) for fc in cb.fcurves for kp in fc.keyframe_points})


def set_frame(sc, f):
    """f may be fractional (glTF keys imported at 24 fps from 30 fps data sit on 0.8-frame steps)."""
    fi = int(math.floor(f + 1e-6))
    sc.frame_set(fi, subframe=float(f - fi))
    return bpy.context.evaluated_depsgraph_get()


# ------------------------------------------------------------------------------------------
# geometry helpers
def world_verts(o, dg):
    oe = o.evaluated_get(dg)
    m = oe.to_mesh()
    co = np.empty(len(m.vertices) * 3, np.float32)
    m.vertices.foreach_get("co", co)
    oe.to_mesh_clear()
    M = np.array(oe.matrix_world, dtype=np.float64)
    return co.reshape(-1, 3).astype(np.float64) @ M[:3, :3].T + M[:3, 3]


def rest_mesh_info(o, dg):
    """edges + dominant bone per vertex, taken from the EVALUATED rest mesh (works with subsurf)."""
    oe = o.evaluated_get(dg)
    m = oe.to_mesh()
    e = np.empty(len(m.edges) * 2, np.int32)
    m.edges.foreach_get("vertices", e)
    gnames = {g.index: clean(g.name) for g in o.vertex_groups}
    dom = []
    for v in m.vertices:
        best, bw = "-", 0.0
        for g in v.groups:
            if g.weight > bw and g.group in gnames:
                best, bw = gnames[g.group], g.weight
        dom.append(best)
    oe.to_mesh_clear()
    return e.reshape(-1, 2), np.array(dom, dtype=object)


class MeshGroup:
    """a named set of skinned mesh objects measured together (e.g. all parts of the original)."""

    def __init__(self, name, objs):
        self.name, self.objs = name, objs

    def init_rest(self, dg, wh):
        self.edges, self.dom, self.rest = [], [], []
        keys, mids, L0 = [], [], []
        for o in self.objs:
            e, dom = rest_mesh_info(o, dg)
            R = world_verts(o, dg)
            self.edges.append(e); self.rest.append(R)
            keys.append(np.array(["|".join(sorted({dom[a], dom[b]})) for a, b in e], dtype=object))
            mids.append((R[e[:, 0]] + R[e[:, 1]]) / 2 / wh)
            L0.append(np.linalg.norm(R[e[:, 0]] - R[e[:, 1]], axis=1))
        self.key = np.concatenate(keys)
        self.mid = np.concatenate(mids)
        self.L0 = np.concatenate(L0)
        self.ok = self.L0 > 1e-7 * max(wh, 1e-9)
        bset = [set(k.split("|")) for k in self.key]
        self.leg = np.array([all(base(b) in LEG_BONES for b in s) for s in bset])
        self.fet = np.array([any(base(b) in FETLOCK[0] for b in s) and any(base(b) in FETLOCK[1] for b in s) for s in bset])

    def reset(self, f0):
        n = len(self.L0)
        self.maxr, self.minr = np.ones(n), np.ones(n)
        self.maxf, self.minf = np.full(n, float(f0)), np.full(n, float(f0))

    def sample(self, dg, f):
        L = []
        for o, e in zip(self.objs, self.edges):
            W = world_verts(o, dg)
            if len(W) != len(self.rest[len(L)]):
                raise RuntimeError(f"topology changed while evaluating {o.name}")
            L.append(np.linalg.norm(W[e[:, 0]] - W[e[:, 1]], axis=1))
        r = np.where(self.ok, np.concatenate(L) / np.where(self.ok, self.L0, 1.0), 1.0)
        up = r > self.maxr; self.maxr[up] = r[up]; self.maxf[up] = f
        dn = r < self.minr; self.minr[dn] = r[dn]; self.minf[dn] = f
        return float(r.max()), float(r.min())

    def report(self, top=6):
        def desc(i, ratio, f):
            return dict(ratio=round(float(ratio), 3), frame=round(float(f), 2), bones=self.key[i],
                        rest_pos_withers=[round(float(x), 3) for x in self.mid[i]])

        def region(mask):
            if not mask.any():
                return None
            idx = np.nonzero(mask)[0]
            iu, idn = idx[self.maxr[idx].argmax()], idx[self.minr[idx].argmin()]
            return dict(edges=int(mask.sum()), max_ratio=float(self.maxr[iu]), min_ratio=float(self.minr[idn]),
                        p99_ratio=float(np.percentile(self.maxr[idx], 99)), p01_ratio=float(np.percentile(self.minr[idx], 1)),
                        worst_stretch=desc(iu, self.maxr[iu], self.maxf[iu]), worst_compress=desc(idn, self.minr[idn], self.minf[idn]))
        per = {}
        for i in np.nonzero(self.ok)[0]:
            k = self.key[i]
            mx, mn = per.get(k, (1.0, 1.0))
            per[k] = (max(mx, self.maxr[i]), min(mn, self.minr[i]))
        per_sorted = sorted(per.items(), key=lambda kv: -max(math.log(kv[1][0]), -math.log(max(kv[1][1], 1e-9))))
        mr, nr = self.maxr[self.ok], self.minr[self.ok]
        return dict(group=self.name, meshes=[o.name for o in self.objs], edges=int(self.ok.sum()),
                    max_ratio=float(mr.max()), min_ratio=float(nr.min()),
                    p999_ratio=float(np.percentile(mr, 99.9)), p001_ratio=float(np.percentile(nr, 0.1)),
                    frac_gt_1_25=float((mr > 1.25).mean()), frac_gt_1_5=float((mr > 1.5).mean()),
                    frac_lt_0_8=float((nr < 0.8).mean()), frac_lt_0_5=float((nr < 0.5).mean()),
                    worst_stretch=[desc(i, self.maxr[i], self.maxf[i]) for i in np.argsort(-self.maxr)[:top]],
                    worst_compress=[desc(i, self.minr[i], self.minf[i]) for i in np.argsort(self.minr)[:top]],
                    legs=region(self.leg & self.ok), fetlock=region(self.fet & self.ok),
                    per_bone=[(k, round(float(v[0]), 3), round(float(v[1]), 3)) for k, v in per_sorted[:12]],
                    per_bone_legs=[(k, round(float(v[0]), 3), round(float(v[1]), 3)) for k, v in per_sorted
                                   if all(base(b) in LEG_BONES for b in k.split("|"))][:10])


def withers_height(arm, names, pts):
    """Top of the body above the front-leg tops, measured from the lowest rest vertex."""
    M = arm.matrix_world
    bl = arm.data.bones
    fr = sum((M @ bl[names[n]].head_local for n in ("FrontUpperLeg.L", "FrontUpperLeg.R")), Vector()) / 2
    bk = sum((M @ bl[names[n]].head_local for n in ("BackUpperLeg.L", "BackUpperLeg.R")), Vector()) / 2
    fwd = np.array(fr - bk); fwd[2] = 0; fwd /= np.linalg.norm(fwd)
    ground = pts[:, 2].min()
    s = pts @ fwd
    length = s.max() - s.min()
    band = np.abs(s - np.dot(np.array(fr), fwd)) < 0.04 * length
    return float(pts[band, 2].max() - ground), float(ground), float(length)


# ------------------------------------------------------------------------------------------
def measure_model(path, mesh_spec, mesh_step, label, use_key_times=True, orig_subdiv=0):
    """mesh_spec: None -> all skinned meshes as group 'cage'; list of names -> one group per mesh."""
    t0 = time.time()
    sc, arm, names = load(path)
    for _, lo, ik in LEGS:
        assert lo in names and ik in names, (lo, ik, sorted(names))
    if mesh_spec is None:
        objs = skinned_meshes(sc, arm)
        groups = [MeshGroup("cage (as imported)", objs)]
        if orig_subdiv:
            subs = []
            for o in objs:   # linked copy with subsurf BEFORE the armature (what stage B baked into LOD0)
                c = o.copy(); sc.collection.objects.link(c)
                m = c.modifiers.new("sub", "SUBSURF")
                m.levels = m.render_levels = orig_subdiv
                m.boundary_smooth = "ALL"; m.use_limit_surface = True
                while c.modifiers[0] != m:
                    c.modifiers.move(c.modifiers.find(m.name), 0)
                subs.append(c)
            groups.append(MeshGroup(f"subdiv{orig_subdiv}", subs))
    else:
        groups = [MeshGroup(o.name, [o]) for o in skinned_meshes(sc, arm, mesh_spec)]
    acts = bone_actions()
    res = dict(label=label, path=os.path.relpath(path, ROOT), armature=arm.name, bones=len(arm.data.bones),
               root_bone=names.get("Root"), fps=sc.render.fps / sc.render.fps_base,
               scene_range=[sc.frame_start, sc.frame_end],
               active_action=(arm.animation_data.action.name if arm.animation_data and arm.animation_data.action else None),
               nla_tracks=[t.name for t in arm.animation_data.nla_tracks] if arm.animation_data else [],
               actions={})

    # ---- rest state
    use_action(arm, None)
    for pb in arm.pose.bones:
        pb.matrix_basis = Matrix.Identity(4)
    arm.data.pose_position = "REST"
    dg = set_frame(sc, 0)
    pts = np.concatenate([world_verts(o, dg) for o in groups[0].objs])
    wh, ground, length = withers_height(arm, names, pts)
    for g in groups:
        g.init_rest(dg, wh)
    arm.data.pose_position = "POSE"
    M = arm.matrix_world
    tip_local = {}
    for lab, lo, ik in LEGS:     # foot-bone head expressed in lower-leg bone space (rest)
        tip_local[lab] = arm.data.bones[names[lo]].matrix_local.inverted() @ arm.data.bones[names[ik]].head_local
    res.update(withers=wh, ground_z=ground, body_length=length,
               arm_scale=list(map(float, arm.matrix_world.to_scale())),
               rest_leg_gap={lab: (M @ arm.data.bones[names[lo]].tail_local - M @ arm.data.bones[names[ik]].head_local).length / wh
                             for lab, lo, ik in LEGS})

    # ---- per action
    for act in acts:
        use_action(arm, act)
        f0, f1 = frame_range(act)
        times = key_times(act) if use_key_times else list(range(f0, f1 + 1))
        A = dict(frames=[f0, f1], keys=key_info(act), n_samples=len(times), legs={})
        gaps = {lab: [] for lab, _, _ in LEGS}
        tip = {lab: [] for lab, _, _ in LEGS}
        poses = {}
        mesh_frames = sorted(set(times[::mesh_step] + [times[-1]]))
        for g in groups:
            g.reset(f0)
        per_frame_worst, root_track = [], []
        for f in times:
            dg = set_frame(sc, f)
            ae = arm.evaluated_get(dg)
            Me = ae.matrix_world
            pbs = ae.pose.bones
            for lab, lo, ik in LEGS:
                foot = Me @ pbs[names[ik]].head
                gaps[lab].append((Me @ pbs[names[lo]].tail - foot).length / wh)
                tip[lab].append((Me @ (pbs[names[lo]].matrix @ tip_local[lab]) - foot).length / wh)
            poses[f] = {clean(pb.name): (pb.matrix_basis.copy(), (Me @ pb.matrix).copy()) for pb in pbs}
            rp = pbs[names["Root"]]
            root_track.append(list(Me @ rp.head) + list((Me @ rp.matrix).to_quaternion()))
            if f in mesh_frames:
                w = [g.sample(dg, f) for g in groups]
                per_frame_worst.append((f, [round(x[0], 3) for x in w], [round(x[1], 3) for x in w]))
        for lab, _, _ in LEGS:
            g = np.array(gaps[lab]); d = np.array(tip[lab])
            A["legs"][lab] = dict(gap_max=float(g.max()), gap_mean=float(g.mean()), gap_min=float(g.min()),
                                  tip_max=float(d.max()), tip_mean=float(d.mean()), tip_argmax=float(times[int(d.argmax())]))
        A["tip_series"] = {lab: [round(float(x), 7) for x in tip[lab]] for lab in tip}
        A["times"] = times
        A["loop"] = loop_report(poses, times, wh)
        rt = np.array(root_track)
        A["root_motion"] = dict(pos_range=float(np.ptp(rt[:, :3], axis=0).max() / wh),
                                rot_range_deg=float(max(math.degrees(Quaternion(rt[0, 3:]).rotation_difference(Quaternion(q)).angle)
                                                        for q in rt[:, 3:])))
        A["body_motion"] = body_motion(poses, names, wh)
        A["mesh"] = [g.report() for g in groups]
        A["per_frame_worst"] = per_frame_worst
        res["actions"][act.name] = A
    res["seconds"] = round(time.time() - t0, 1)
    return res


def key_info(act):
    xs = set()
    n_fc = rot_fc = loc_fc = scl_fc = 0
    interp, bones_loc, per_bone_n = set(), set(), {}
    cyc = False
    for cb in channelbags(act):
        for fc in cb.fcurves:
            n_fc += 1
            bn = clean(fc.data_path.split('"')[1]) if '"' in fc.data_path else fc.data_path
            per_bone_n[bn] = max(per_bone_n.get(bn, 0), len(fc.keyframe_points))
            if fc.data_path.endswith("rotation_quaternion"):
                rot_fc += 1
            elif fc.data_path.endswith("location"):
                loc_fc += 1; bones_loc.add(bn)
            elif fc.data_path.endswith("scale"):
                scl_fc += 1
            cyc |= any(m.type == "CYCLES" for m in fc.modifiers)
            for kp in fc.keyframe_points:
                xs.add(round(kp.co[0], 4)); interp.add(kp.interpolation)
    xs = sorted(xs)
    d = np.diff(xs) if len(xs) > 1 else np.array([0.0])
    return dict(fcurves=n_fc, rot_fcurves=rot_fc, loc_fcurves=loc_fc, scale_fcurves=scl_fc,
                location_bones=sorted(bones_loc), keyed_bones=len(per_bone_n), n_key_times=len(xs),
                first_key=xs[0], last_key=xs[-1], key_spacing=sorted(set(round(float(x), 4) for x in d)),
                interpolation=sorted(interp), cycles_modifier=cyc,
                sparse_bones={b: n for b, n in per_bone_n.items() if n < len(xs)})


def pose_diff(pa, pb, wh):
    out = {}
    for bn in pa:
        la, wa = pa[bn]; lb, wb = pb[bn]
        out[bn] = (math.degrees(la.to_quaternion().rotation_difference(lb.to_quaternion()).angle),
                   (wa.translation - wb.translation).length / wh,
                   math.degrees(wa.to_quaternion().rotation_difference(wb.to_quaternion()).angle))
    return out


def loop_report(poses, times, wh):
    first_last = pose_diff(poses[times[0]], poses[times[-1]], wh)
    step0 = pose_diff(poses[times[0]], poses[times[1]], wh)
    step1 = pose_diff(poses[times[-2]], poses[times[-1]], wh)
    # typical per-sample motion over the clip (for scale)
    steps = [max(v[0] for v in pose_diff(poses[a], poses[b], wh).values()) for a, b in zip(times[:-1], times[1:])]
    worst = sorted(first_last.items(), key=lambda kv: -kv[1][0])[:5]
    return dict(max_local_rot_deg=max(v[0] for v in first_last.values()),
                max_world_pos=max(v[1] for v in first_last.values()),
                max_world_rot_deg=max(v[2] for v in first_last.values()),
                worst_bones=[(b, round(v[0], 4), round(v[1], 6), round(v[2], 4)) for b, v in worst],
                first_step_max_rot_deg=max(v[0] for v in step0.values()),
                last_step_max_rot_deg=max(v[0] for v in step1.values()),
                median_step_max_rot_deg=float(np.median(steps)),
                zero_motion_steps=int(sum(1 for s in steps if s < 1e-4)))


def body_motion(poses, names, wh):
    ts = sorted(poses)
    P = np.array([list(poses[t]["Body"][1].translation) for t in ts])
    return dict(body_pos_range_withers=[round(float(x) / wh, 5) for x in np.ptp(P, axis=0)])


# ------------------------------------------------------------------------------------------
def glb_animation_info(path):
    """Raw glTF sampler times (seconds) straight from the .glb binary chunk."""
    with open(path, "rb") as f:
        data = f.read()
    clen, _ = struct.unpack_from("<II", data, 12)
    js = json.loads(data[20:20 + clen])
    bin_off = 20 + clen + 8
    out = {}
    for a in js.get("animations", []):
        times = []
        for i in sorted({s["input"] for s in a["samplers"]}):
            acc = js["accessors"][i]
            bv = js["bufferViews"][acc["bufferView"]]
            off = bin_off + bv.get("byteOffset", 0) + acc.get("byteOffset", 0)
            times.append(np.frombuffer(data, dtype="<f4", count=acc["count"], offset=off))
        allt = np.unique(np.concatenate(times))
        d = np.diff(allt)
        out[a.get("name", "?")] = dict(
            channels=len(a["channels"]), samplers=len(a["samplers"]),
            interpolation=sorted({s.get("interpolation", "LINEAR") for s in a["samplers"]}),
            t0=float(allt[0]), t1=float(allt[-1]), n_times=int(len(allt)),
            dt_min=float(d.min()) if len(d) else 0, dt_max=float(d.max()) if len(d) else 0,
            implied_fps=float(round(1.0 / np.median(d), 3)) if len(d) else 0)
    return out


# ------------------------------------------------------------------------------------------
def fmt_region(r):
    if not r:
        return "-"
    return (f"stretch max {r['max_ratio']:.3f} (p99 {r['p99_ratio']:.3f}, {r['worst_stretch']['bones']} f{r['worst_stretch']['frame']:g}) | "
            f"compress min {r['min_ratio']:.3f} (p1 {r['p01_ratio']:.3f}, {r['worst_compress']['bones']} f{r['worst_compress']['frame']:g})")


def fmt_model(r):
    L = [f"== {r['label']}: {r['path']}  (armature {r['armature']}, {r['bones']} bones, root bone '{r['root_bone']}', "
         f"object scale {tuple(round(x, 4) for x in r['arm_scale'])})",
         f"   withers height {r['withers']:.4f} (ground z {r['ground_z']:.4f}, body length {r['body_length']:.4f}); "
         f"scene fps {r['fps']:g}, scene range {r['scene_range']}, active action {r['active_action']}, NLA tracks {r['nla_tracks']}",
         "   rest gap lowerleg.tail->foot.head (x withers): " + ", ".join(f"{k} {v:.5f}" for k, v in r["rest_leg_gap"].items())]
    for an, A in r["actions"].items():
        k = A["keys"]
        L.append(f"   -- action {an}: frames {A['frames'][0]}-{A['frames'][1]}, {A['n_samples']} samples ({k['n_key_times']} key times, spacing "
                 f"{k['key_spacing']} frames), interp {k['interpolation']}, fcurves {k['fcurves']} (rot {k['rot_fcurves']}, loc {k['loc_fcurves']}, "
                 f"scale {k['scale_fcurves']}) on {k['keyed_bones']} bones, cycles-mod {k['cycles_modifier']}")
        L.append(f"      location-keyed bones: {', '.join(k['location_bones'])}; sparsely keyed: {k['sparse_bones']}")
        for lab, g in A["legs"].items():
            L.append(f"      leg {lab:8s} tail->foot gap {g['gap_min']:.5f}..{g['gap_max']:.5f}  | chain-end->foot tip max {g['tip_max']:.6f} "
                     f"(f{g['tip_argmax']:g}) mean {g['tip_mean']:.6f}  (x withers)")
        lp = A["loop"]
        L.append(f"      loop first-vs-last sample: max local rot {lp['max_local_rot_deg']:.4f} deg, world pos {lp['max_world_pos']:.6f} x withers, "
                 f"world rot {lp['max_world_rot_deg']:.4f} deg; per-sample motion: first {lp['first_step_max_rot_deg']:.3f}, "
                 f"last {lp['last_step_max_rot_deg']:.3f}, median {lp['median_step_max_rot_deg']:.3f} deg; zero-motion steps {lp['zero_motion_steps']}")
        rm = A["root_motion"]
        L.append(f"      root bone motion: pos range {rm['pos_range']:.6f} x withers, rot range {rm['rot_range_deg']:.4f} deg; "
                 f"Body bone pos range (xyz, x withers) {A['body_motion']['body_pos_range_withers']}")
        for m in A["mesh"]:
            L.append(f"      mesh [{m['group']}] {m['edges']} edges: stretch max {m['max_ratio']:.3f} p99.9 {m['p999_ratio']:.3f} | "
                     f"compress min {m['min_ratio']:.3f} p0.1 {m['p001_ratio']:.3f} | >1.25 {100*m['frac_gt_1_25']:.3f}% >1.5 {100*m['frac_gt_1_5']:.3f}% "
                     f"<0.8 {100*m['frac_lt_0_8']:.3f}% <0.5 {100*m['frac_lt_0_5']:.3f}%")
            for s in m["worst_stretch"][:2]:
                L.append(f"         worst stretch {s['ratio']:.3f} f{s['frame']:g} bones {s['bones']} at {s['rest_pos_withers']}")
            for s in m["worst_compress"][:2]:
                L.append(f"         worst compress {s['ratio']:.3f} f{s['frame']:g} bones {s['bones']} at {s['rest_pos_withers']}")
            L.append("         per-bone worst (max/min): " + "; ".join(f"{b} {a:.2f}/{c:.2f}" for b, a, c in m["per_bone"][:7]))
            L.append(f"         legs   : {fmt_region(m['legs'])}")
            L.append(f"         fetlock: {fmt_region(m['fetlock'])}")
    return "\n".join(L)


def summary_table(out):
    L = ["", "== leg/foot separation: chain-end->foot-head distance, max / mean, fraction of withers height",
         f"   {'action':8s} {'leg':8s} {'original':>22s} {'calf':>22s}"]
    for an in out["calf"]["actions"]:
        for lab, c in out["calf"]["actions"][an]["legs"].items():
            o = out.get("original", {}).get("actions", {}).get(an, {}).get("legs", {}).get(lab)
            os_ = f"{o['tip_max']:.6f} / {o['tip_mean']:.6f}" if o else "-"
            L.append(f"   {an:8s} {lab:8s} {os_:>22s} {c['tip_max']:.6f} / {c['tip_mean']:.6f}   "
                     f"(calf abs: {1000 * c['tip_max'] * out['calf']['withers']:.1f} mm max)")
    L.append("== mesh summary (max stretch / min compress over sampled frames; legs region; fetlock region)")
    for key in ("original", "calf"):
        if key not in out:
            continue
        for an, A in out[key]["actions"].items():
            for m in A["mesh"]:
                lg, ft = m["legs"] or {}, m["fetlock"] or {}
                L.append(f"   {key:8s} {an:7s} {m['group']:20s} all {m['max_ratio']:.3f}/{m['min_ratio']:.3f}  "
                         f"legs {lg.get('max_ratio', 1):.3f}/{lg.get('min_ratio', 1):.3f}  fetlock {ft.get('max_ratio', 1):.3f}/{ft.get('min_ratio', 1):.3f}")
    return "\n".join(L)


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--calf", default=os.path.join(ROOT, "build", "stage_b.blend"))
    ap.add_argument("--orig", default=os.path.join(ROOT, "cow.glb"))
    ap.add_argument("--no-orig", action="store_true")
    ap.add_argument("--calf-meshes", default="Calf_LOD0,Calf_LOD2")
    ap.add_argument("--orig-subdiv", type=int, default=2, help="also measure the original with this subdiv level (0 = off)")
    ap.add_argument("--mesh-step", type=int, default=4, help="mesh stretch is sampled every Nth key time")
    ap.add_argument("--integer-frames", action="store_true", help="sample integer frames instead of the key times")
    ap.add_argument("--json", default=None)
    a = ap.parse_args(argv)

    out = {}
    if not a.no_orig:
        out["glb_timing"] = glb_animation_info(a.orig)
        out["original"] = measure_model(a.orig, None, a.mesh_step, "original cow.glb", not a.integer_frames, a.orig_subdiv)
    out["calf"] = measure_model(a.calf, a.calf_meshes.split(","), a.mesh_step, "calf", not a.integer_frames)

    print()
    if "glb_timing" in out:
        print("== raw glTF animation timing (cow.glb):")
        for n, t in out["glb_timing"].items():
            print(f"   {n}: {t['n_times']} sample times {t['t0']:.4f}-{t['t1']:.4f}s, dt {t['dt_min']:.5f}..{t['dt_max']:.5f}s "
                  f"-> {t['implied_fps']} fps, interp {t['interpolation']}, {t['channels']} channels")
    for k in ("original", "calf"):
        if k in out:
            print(fmt_model(out[k]))
    print(summary_table(out))
    if a.json:
        with open(a.json, "w") as f:
            json.dump(out, f, indent=1, default=str)
        print("wrote", a.json)
    return out


if __name__ == "__main__":
    main(sys.argv[1:])
