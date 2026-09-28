"""Stage B: reshape the adult cow cage into a young cow (calf), add eyeballs, UV, subdivide,
convert to real-world meters. Mesh and rig rest pose are warped with the SAME spatial function,
so skin binding and the existing baked actions stay valid.

Input : build/stage_a.blend      Output: build/stage_b.blend
Objects out:
  CalfRig          armature (43 bones, names from stage A), meters, head toward -Y, ground z=0
  Calf_LOD0        subdiv-2 skinned mesh, materials [M_Calf_Body, M_Calf_Eye], UV "UVMap"
  Calf_LOD1        subdiv-1 skinned mesh (same UVs)
  Calf_LOD2        cage skinned mesh (same UVs)
Face attribute "orig_part": 0 coat, 1 light coat (face/socks/inner ear/tail tip/belly patch),
                             2 hooves, 3 nose/muzzle, 4 eyeball
"""
import bpy, bmesh, math, os, sys
from mathutils import Vector, Matrix
from mathutils.geometry import intersect_point_line

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "build", "stage_a.blend")
OUT = os.path.join(ROOT, "build", "stage_b.blend")

P = dict(                # all in ORIGINAL model units (1 unit ~= 22.5 cm after scaling)
    x_scale=0.90,        # narrower young body
    torso_compress=0.72, torso_y0=-1.45, torso_y1=1.75, torso_blend=0.35,
    head_scale=1.22, muzzle_compress=0.84, head_widen=1.10,
    flank_lift=0.30, flank_y0=-0.6, flank_y1=1.6,   # tucked-up calf flank / higher rear underline
    ear_scale=1.20,
    leg_thin={"FrontUpperLeg": 0.82, "FrontLowerLeg": 0.78, "BackUpperLeg": 0.76,
              "BackLowerLeg": 0.76, "IKFrontLeg": 0.82, "IKBackLeg": 0.82,
              "FF": 0.86, "FFB": 0.86, "BackLeg": 0.88},
    neck_thin=1.0, tail_thin=0.75,
    neck_deepen=1.28,   # deeper throat/brisket line under the neck bones
    eye_radius_mul=1.12, eye_protrude=0.45, eye_open=1.55, eye_open_ring=1.2,
    meters=0.225,        # withers ~1.0 m
    jaw_hinge=(-4.0, 3.15), jaw_front=(-5.05, 2.95), jaw_soft=0.09,   # (y, z) mouth line, original units
    ear_root_x=0.52, ear_soft=0.13,
)

bpy.ops.wm.open_mainfile(filepath=SRC)
arm = bpy.data.objects["CalfRig"]
ob = bpy.data.objects["Calf"]
me = ob.data

def smoothstep(e0, e1, x):
    t = min(1.0, max(0.0, (x - e0) / (e1 - e0)))
    return t * t * (3 - 2 * t)

# ---------------------------------------------------------------------------------
# 0. new deform regions for the rig upgrade (Jaw, Ear.L, Ear.R), defined in ORIGINAL coords.
#    Weight is taken from the vertex's Head influence so neck blending is untouched.
def add_region_group(name, fn):
    """region weight w goes to the new group; every existing influence is scaled by (1-w)"""
    vg = ob.vertex_groups.new(name=name)
    head_i = ob.vertex_groups["Head"].index
    for v in me.vertices:
        w = fn(v.co)
        if w <= 1e-3: continue
        if next((g.weight for g in v.groups if g.group == head_i), 0.0) <= 1e-3:
            continue                       # only head-driven verts belong to jaw/ears
        tot = sum(g.weight for g in v.groups) or 1.0
        for g in list(v.groups):
            ob.vertex_groups[g.group].add([v.index], g.weight / tot * (1.0 - w), "REPLACE")
        vg.add([v.index], w, "REPLACE")
    return vg

(hy, hz), (fy_, fz_) = P["jaw_hinge"], P["jaw_front"]
def jaw_w(c):
    if c.y > hy + 0.05: return 0.0
    t = (c.y - hy) / (fy_ - hy)
    zl = hz + (fz_ - hz) * min(1.0, max(0.0, t))
    return smoothstep(zl + 0.02, zl - P["jaw_soft"], c.z) * smoothstep(hy + 0.05, hy - 0.2, c.y)
def ear_w(side):
    def f(c):
        if c.x * side <= 0 or not (-4.15 < c.y < -3.45 and 3.65 < c.z < 4.45): return 0.0
        return smoothstep(P["ear_root_x"], P["ear_root_x"] + P["ear_soft"], abs(c.x))
    return f
add_region_group("Jaw", jaw_w)
add_region_group("Ear.L", ear_w(+1))
add_region_group("Ear.R", ear_w(-1))
REGION_GROUPS = ("Jaw", "Ear.L", "Ear.R")

# ---------------------------------------------------------------------------------
# 1. fill udder hole (only boundary loop that is not an eye socket)
bm = bmesh.new(); bm.from_mesh(me)
part = bm.faces.layers.int.get("orig_part")
bnd = [e for e in bm.edges if e.is_boundary]
udder_edges = [e for e in bnd if all(v.co.z < 2.6 for v in e.verts)]
res = bmesh.ops.holes_fill(bm, edges=udder_edges, sides=0)
for f in res["faces"]:
    f[part] = 1
# poke the n-gon so the patch subdivides smoothly
bmesh.ops.poke(bm, faces=res["faces"])
bm.to_mesh(me); bm.free()

# eye socket loops (remaining boundaries)
def boundary_loops(mesh):
    bm = bmesh.new(); bm.from_mesh(mesh)
    edges = [e for e in bm.edges if e.is_boundary]
    seen, loops = set(), []
    for e in edges:
        if e.index in seen: continue
        stack, grp = [e], []
        seen.add(e.index)
        while stack:
            x = stack.pop(); grp.append(x)
            for v in x.verts:
                for y in v.link_edges:
                    if y.is_boundary and y.index not in seen:
                        seen.add(y.index); stack.append(y)
        vids = sorted({v.index for ed in grp for v in ed.verts})
        loops.append(vids)
    bm.free()
    return loops

# ---------------------------------------------------------------------------------
# 2. local, weight-driven edits (in original space; bones untouched)
bones = arm.data.bones
vg_names = {g.index: g.name for g in ob.vertex_groups}

def bone_seg(name):
    b = bones[name]
    return b.head_local.copy(), b.tail_local.copy()

def base(name):   # "FrontLowerLeg.L" -> "FrontLowerLeg"
    return name.split(".")[0]

head_pivot = bones["Head"].head_local.copy()
eye_y = -4.32
cos = [v.co.copy() for v in me.vertices]
new = [c.copy() for c in cos]
for v in me.vertices:
    ws = {vg_names[g.group]: g.weight for g in v.groups if g.weight > 1e-5}
    tot = sum(ws.values()) or 1.0
    p = cos[v.index].copy()
    # radial thinning toward each influencing bone segment, blended by weight
    disp = Vector()
    for bn, w in ws.items():
        f = None
        kb = base(bn)
        if kb in P["leg_thin"]: f = P["leg_thin"][kb]
        elif kb.startswith("Neck"): f = P["neck_thin"]
        elif kb.startswith("Tail"): f = P["tail_thin"]
        if f is None: continue
        h, t = bone_seg(bn)
        q, _ = intersect_point_line(p, h, t)
        # clamp to segment
        seg = t - h; L2 = seg.length_squared
        s = max(0.0, min(1.0, (p - h).dot(seg) / L2)) if L2 > 0 else 0
        q = h + seg * s
        disp += (w / tot) * (q + (p - q) * f - p)
    p = p + disp
    # deeper neck: push verts that sit BELOW the neck bones further down (z only)
    wn = sum(w for bn, w in ws.items() if bn.startswith("Neck")) / tot
    if wn > 0 and P["neck_deepen"] != 1.0:
        h, t = bone_seg("Neck2")
        seg = t - h; s_ = max(0.0, min(1.0, (p - h).dot(seg) / seg.length_squared))
        q = h + seg * s_
        if p.z < q.z:
            p = p + Vector((0, 0, (p.z - q.z) * (P["neck_deepen"] - 1.0) * wn))
    # head: uniform scale about the head joint, weighted by Head weight
    wh = sum(ws.get(n, 0.0) for n in ("Head",) + REGION_GROUPS) / tot
    if wh > 0:
        p = p + wh * (P["head_scale"] - 1.0) * (p - head_pivot)
        p.x = p.x * (1 + wh * (P["head_widen"] - 1.0))          # broad calf forehead
        # shorter muzzle in front of the eyes
        if p.y < eye_y:
            p.y = eye_y + (p.y - eye_y) * (1 - wh * (1 - P["muzzle_compress"]))
    new[v.index] = p

# ears: vertices lateral of the skull near ear height
for i, c in enumerate(cos):
    ax = abs(c.x)
    if ax > 0.5 and -4.05 < c.y < -3.55 and 3.75 < c.z < 4.35:
        root = Vector((math.copysign(0.52, c.x), -3.82, 4.05))
        w = smoothstep(0.5, 0.62, ax)
        # ear root follows the head scale, so scale relative to the (already head-scaled) root
        root_s = root + (P["head_scale"] - 1.0) * (root - head_pivot)
        root_s.x *= P["head_widen"]
        p = new[i]
        new[i] = p + w * (P["ear_scale"] - 1.0) * (p - root_s)

for v in me.vertices:
    v.co = new[v.index]

# flank tuck: lift the lower barrel between front and hind legs (torso-weighted verts only)
torso_bones = {"Body", "Back", "Torso", "Torso2", "Torso3"}
for v in me.vertices:
    ws = {vg_names[g.group]: g.weight for g in v.groups if g.weight > 1e-5}
    tot = sum(ws.values()) or 1.0
    wt = sum(w for b, w in ws.items() if b in torso_bones) / tot
    if wt <= 0: continue
    c = v.co
    fy = smoothstep(P["flank_y0"], P["flank_y0"] + 0.8, c.y) * (1 - smoothstep(P["flank_y1"], P["flank_y1"] + 0.6, c.y))
    fz = 1 - smoothstep(1.9, 3.2, c.z)            # strongest at the underline, zero at mid-barrel
    c.z += P["flank_lift"] * wt * fy * fz * smoothstep(-0.2, 0.6, c.y)   # more at the rear flank

# ---------------------------------------------------------------------------------
# 3. global warp applied to mesh AND bones (keeps rig binding consistent)
def torso_map(y):
    """integral of a speed function that is `torso_compress` inside [y0,y1] and 1 outside"""
    y0, y1, b, k = P["torso_y0"], P["torso_y1"], P["torso_blend"], P["torso_compress"]
    # numeric integration from 0 (stable, smooth)
    n = 200
    a, bnd = (0.0, y) if y >= 0 else (y, 0.0)
    h = (bnd - a) / n if n else 0
    acc = 0.0
    for i in range(n):
        t = a + (i + 0.5) * h
        inside = smoothstep(y0 - b, y0 + b, t) * (1 - smoothstep(y1 - b, y1 + b, t))
        acc += (1 - inside * (1 - k)) * h
    return acc if y >= 0 else -acc

def warp(p):
    return Vector((p.x * P["x_scale"], torso_map(p.y), p.z))

for v in me.vertices:
    v.co = warp(v.co)

bpy.context.view_layer.objects.active = arm
bpy.ops.object.mode_set(mode="EDIT")
for eb in arm.data.edit_bones:
    roll = eb.roll
    eb.head = warp(eb.head); eb.tail = warp(eb.tail)
    eb.roll = roll
bpy.ops.object.mode_set(mode="OBJECT")

# ---------------------------------------------------------------------------------
# 4. eyeballs into the two sockets
loops = boundary_loops(me)
eye_objs = []
head_vg = ob.vertex_groups["Head"]
eye_mat = bpy.data.materials.new("M_Calf_Eye")
body_mat = bpy.data.materials.new("M_Calf_Body")
me.materials.clear()
me.materials.append(body_mat)
me.materials.append(eye_mat)
for p in me.polygons: p.material_index = 0

# open the eyelids: widen each socket loop (and its 1-ring, less) in its own plane
bm = bmesh.new(); bm.from_mesh(me); bm.verts.ensure_lookup_table()
for vids in loops:
    c = sum((bm.verts[i].co for i in vids), Vector()) / len(vids)
    ring = {n.index for i in vids for e in bm.verts[i].link_edges for n in e.verts} - set(vids)
    for i in vids:
        bm.verts[i].co = c + (bm.verts[i].co - c) * P["eye_open"]
    for i in ring:
        bm.verts[i].co = c + (bm.verts[i].co - c) * P["eye_open_ring"]
bm.to_mesh(me); bm.free()

for vids in loops:
    pts = [me.vertices[i].co.copy() for i in vids]
    c = sum(pts, Vector()) / len(pts)
    rad = sum((q - c).length for q in pts) / len(pts)
    # outward normal ~ lateral + slightly forward
    nrm = Vector((math.copysign(1.0, c.x), -0.35, 0.15)).normalized()
    r = rad * P["eye_radius_mul"]
    center = c - nrm * (r * (1.0 - P["eye_protrude"]))
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=10, radius=r)
    # orient: sphere pole axis (Z) -> nrm
    rot = nrm.to_track_quat("Z", "Y").to_matrix().to_4x4()
    bmesh.ops.transform(bm, matrix=Matrix.Translation(center) @ rot, verts=bm.verts)
    # planar UV looking down the eye axis: u = horizontal, v = up
    uax = nrm.cross(Vector((0, 0, 1))).normalized()
    vax = uax.cross(nrm).normalized()
    if vax.z < 0: vax = -vax
    uvl = bm.loops.layers.uv.new("UVMap")
    for f in bm.faces:
        for l in f.loops:
            d = l.vert.co - center
            l[uvl].uv = (0.5 + d.dot(uax) / (2 * r), 0.5 + d.dot(vax) / (2 * r))
    em = bpy.data.meshes.new("eye"); bm.to_mesh(em); bm.free()
    eo = bpy.data.objects.new("eye", em)
    bpy.context.scene.collection.objects.link(eo)
    eo.data.materials.append(body_mat); eo.data.materials.append(eye_mat)
    for p in eo.data.polygons: p.material_index = 1
    a = eo.data.attributes.new("orig_part", "INT", "FACE")
    for i in range(len(eo.data.polygons)): a.data[i].value = 4
    vg = eo.vertex_groups.new(name="Head")
    vg.add(list(range(len(eo.data.vertices))), 1.0, "REPLACE")
    eye_objs.append(eo)

# ---------------------------------------------------------------------------------
# 5. UV unwrap the body cage (eyes keep their planar UVs), then join eyes
bpy.ops.object.select_all(action="DESELECT")
ob.select_set(True); bpy.context.view_layer.objects.active = ob
if not me.uv_layers: me.uv_layers.new(name="UVMap")
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=0.004, area_weight=0.0, correct_aspect=True, scale_to_bounds=False)
bpy.ops.object.mode_set(mode="OBJECT")
# shrink body UVs into the bottom 100% (eyes use a separate texture, overlap is fine)
for eo in eye_objs: eo.select_set(True)
ob.select_set(True); bpy.context.view_layer.objects.active = ob
bpy.ops.object.join()

# ---------------------------------------------------------------------------------
# 6. meters: scale mesh + rig, rescale location keys
k = P["meters"]
ob.parent = None                      # scale each object once (child would inherit k twice)
ob.matrix_world = Matrix.Identity(4)
bpy.ops.object.select_all(action="DESELECT")
arm.scale = (k, k, k); ob.scale = (k, k, k)
for o in (arm, ob): o.select_set(True)
bpy.context.view_layer.objects.active = arm
bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
for act in bpy.data.actions:
    for l in act.layers:
        for s in l.strips:
            for cb in s.channelbags:
                for fc in cb.fcurves:
                    if fc.data_path.endswith(".location"):
                        for kp in fc.keyframe_points:
                            kp.co[1] *= k; kp.handle_left[1] *= k; kp.handle_right[1] *= k
# ground at z=0
minz = min(v.co.z for v in ob.data.vertices)
print("min z after scale", round(minz, 4))

# ---------------------------------------------------------------------------------
# 6b. rig upgrade: Jaw + Ear bones placed from their (final) vertex regions
def region_stats(name):
    gi = ob.vertex_groups[name].index
    pts = [(v.co.copy(), g.weight) for v in ob.data.vertices for g in v.groups if g.group == gi and g.weight > 0.05]
    return pts
bpy.ops.object.select_all(action="DESELECT")
bpy.context.view_layer.objects.active = arm
bpy.ops.object.mode_set(mode="EDIT")
eb = arm.data.edit_bones
head_eb = eb["Head"]
k_m = P["meters"]
def warp_s(y, z):   # original (y,z) -> final meters (x=0)
    return warp(Vector((0, y, z))) * k_m
jaw = eb.new("Jaw"); jaw.parent = head_eb; jaw.use_deform = True
jaw.head = warp_s(hy, hz); jaw.tail = warp_s(fy_ + 0.1, fz_ - 0.05)
# the hinge moved with the head scale: pull it onto the region's rear edge
jp = region_stats("Jaw")
if jp:
    ys = sorted(p.y for p, w in jp)
    zs = sorted(p.z for p, w in jp)
    jaw.head = Vector((0, ys[-1], zs[len(zs) // 2] + 0.01))
    jaw.tail = Vector((0, ys[0] + 0.01, zs[len(zs) // 4]))
jaw.roll = 0.0
for side, nm in ((1, "Ear.L"), (-1, "Ear.R")):
    pts = region_stats(nm)
    root = [p for p, w in pts if w < 0.5] or [p for p, w in pts]
    tipc = sorted(pts, key=lambda pw: -abs(pw[0].x))[: max(3, len(pts) // 8)]
    b = eb.new(nm); b.parent = head_eb; b.use_deform = True
    b.head = sum(root, Vector()) / len(root)
    b.tail = sum((p for p, w in tipc), Vector()) / len(tipc)
    b.roll = 0.0
bpy.ops.object.mode_set(mode="OBJECT")
for nm in ("Jaw", "Ear.L", "Ear.R"):
    bn = arm.data.bones[nm]
    print(f"bone {nm}: head {tuple(round(x,3) for x in bn.head_local)} tail {tuple(round(x,3) for x in bn.tail_local)}")

# lower-leg leaf bones: glTF has no tails, the importer invented them below the ground.
# The real chain end (fetlock) is the foot bone's head, which lies on the same line -> shorten
# along the bone direction (rest orientation and roll unchanged, so actions are unaffected).
bpy.ops.object.mode_set(mode="EDIT")
for leg, foot in (("FrontLowerLeg", "IKFrontLeg"), ("BackLowerLeg", "IKBackLeg")):
    for sd in (".L", ".R"):
        b = eb[leg + sd]; f = eb[foot + sd]
        d = (b.tail - b.head).normalized()
        roll = b.roll
        b.tail = b.head + d * (f.head - b.head).dot(d)
        b.roll = roll
bpy.ops.object.mode_set(mode="OBJECT")

# 30 fps project; glTF keys were sampled at 1/30 s but imported on a 24 fps timeline (0.8-frame
# spacing). Retime x1.25 so keys land on integer frames with unchanged real duration.
sc = bpy.context.scene
sc.render.fps = 30; sc.render.fps_base = 1.0
for act in bpy.data.actions:
    for l in act.layers:
        for st in l.strips:
            for cb in st.channelbags:
                for fc in cb.fcurves:
                    for kp in fc.keyframe_points:
                        t = kp.co[0] * 1.25
                        t = round(t) if abs(t - round(t)) < 1e-3 else t
                        kp.handle_left[0] = t + (kp.handle_left[0] - kp.co[0]) * 1.25
                        kp.handle_right[0] = t + (kp.handle_right[0] - kp.co[0]) * 1.25
                        kp.co[0] = t
    lo, hi = act.frame_range
    act.use_frame_range = True
    act.frame_start, act.frame_end = round(lo), round(hi)
    act.use_cyclic = True
    print("action", act.name, "frames", act.frame_start, act.frame_end, "@30fps")
sc.frame_start, sc.frame_end = 0, 180

# enforce <=4 influences, normalised
for v in ob.data.vertices:
    gs = sorted([(g.group, g.weight) for g in v.groups if g.weight > 0], key=lambda t: -t[1])
    keep = gs[:4]; tot = sum(w for _, w in keep) or 1.0
    for gi, w in gs[4:]:
        ob.vertex_groups[gi].remove([v.index])
    for gi, w in keep:
        ob.vertex_groups[gi].add([v.index], w / tot, "REPLACE")

# ---------------------------------------------------------------------------------
# 7. LOD meshes from subdivision levels (UVs smoothed, weights interpolated)
def make_lod(level, name):
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True); bpy.context.view_layer.objects.active = ob
    bpy.ops.object.duplicate()
    d = bpy.context.active_object
    d.name = name; d.data.name = name
    # put subsurf BEFORE the armature modifier and apply it
    if level > 0:
        m = d.modifiers.new("sub", "SUBSURF")
        m.levels = level; m.render_levels = level
        m.uv_smooth = "PRESERVE_BOUNDARIES"; m.boundary_smooth = "ALL"
        m.use_limit_surface = True
        bpy.ops.object.modifier_move_to_index(modifier="sub", index=0)
        bpy.ops.object.modifier_apply(modifier="sub")
    return d

lods = [make_lod(2, "Calf_LOD0"), make_lod(1, "Calf_LOD1"), make_lod(0, "Calf_LOD2")]
bpy.data.objects.remove(ob, do_unlink=True)
for d in lods:
    d.parent = arm
    for mdf in d.modifiers:
        if mdf.type == "ARMATURE": mdf.object = arm
    for p in d.data.polygons: p.use_smooth = True
    print(d.name, "verts", len(d.data.vertices), "tris", sum(len(p.vertices) - 2 for p in d.data.polygons))

bb = [v.co for v in lods[0].data.vertices]
print("LOD0 bbox", [round(min(c[i] for c in bb), 3) for i in range(3)], [round(max(c[i] for c in bb), 3) for i in range(3)])
bpy.ops.wm.save_as_mainfile(filepath=OUT)
print("saved", OUT)
