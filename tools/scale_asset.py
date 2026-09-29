"""Stage E (adult cow only): scale the finished, animated asset uniformly and give it the cow's names.

    ASSET=cow python3 tools/scale_asset.py --in build/cow/stage_d.blend --out build/cow/stage_e.blend
                                           [--scale 1.42] [--rename Calf=Cow]

Why: the cow is authored at the calf's height (withers ~1.0 m) so every clip family, its tuned distances and its QA
keep their meaning (tools/asset_profile.py). A uniform scale of a skinned, animated rig is exact: bone rest positions
and every location key are multiplied by k, rotations are unchanged, so each vertex of each frame lands at k times its
old position (feet stay planted, loops stay seamless, IK chain ends stay on the hooves). The script checks that on
every frame of every action by comparing the world-space bone heads and tails before (x k) and after; the only
deviation allowed is float32 round-off (<= 0.05 mm; 0.014 mm measured on the Gallop_RM root motion).

Renames (objects, their data, materials): CalfRig -> CowRig, Calf_LOD0..2 -> Cow_LOD0..2, M_Calf_Body/Eye ->
M_Cow_Body/Eye. The texture images already carry the cow's names (T_Cow_*, tools/calf_textures.py).
"""
import argparse, os, sys
import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import asset_profile as AP

ap = argparse.ArgumentParser()
ap.add_argument("--in", dest="src", default=os.path.join(AP.BUILD, "stage_d.blend"))
ap.add_argument("--out", default=os.path.join(AP.BUILD, "stage_e.blend"))
ap.add_argument("--scale", type=float, default=AP.FINAL_SCALE)
ap.add_argument("--rename", default="Calf=%s" % AP.NAME, help="OLD=NEW name prefix for objects/data/materials")
a = ap.parse_args()
k = a.scale
old, new = a.rename.split("=")

bpy.ops.wm.open_mainfile(filepath=a.src)
sc = bpy.context.scene
arm = bpy.data.objects[old + "Rig"]
meshes = [o for o in bpy.data.objects if o.type == "MESH" and o.parent == arm]
actions = list(bpy.data.actions)


def channelbags(act):
    for l in act.layers:
        for s in l.strips:
            for cb in s.channelbags:
                yield cb


def use_action(act):
    ad = arm.animation_data_create(); ad.action = act
    if act.slots: ad.action_slot = act.slots[0]


def heads(act):
    use_action(act)
    lo, hi = int(act.frame_range[0]), int(act.frame_range[1])
    out = []
    for f in range(lo, hi + 1):
        sc.frame_set(f)
        ae = arm.evaluated_get(bpy.context.evaluated_depsgraph_get())
        out.append([(ae.matrix_world @ pb.head).copy() for pb in ae.pose.bones] +
                   [(ae.matrix_world @ pb.tail).copy() for pb in ae.pose.bones])
    return out


prev_action = arm.animation_data.action if arm.animation_data else None
before = {act.name: heads(act) for act in actions}

# 1. mesh + rig rest: unparent (a child would inherit the scale twice), scale, apply, re-parent
assert arm.matrix_world == Matrix.Identity(4), "the rig must sit at the origin with an identity transform"
for o in meshes:
    assert o.matrix_world == Matrix.Identity(4), o.name
    o.parent = None
bpy.ops.object.select_all(action="DESELECT")
for o in [arm] + meshes:
    o.scale = (k, k, k); o.select_set(True)
bpy.context.view_layer.objects.active = arm
bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
for o in meshes:
    o.parent = arm
    o.matrix_parent_inverse = Matrix.Identity(4)
    for m in o.modifiers:
        if m.type == "ARMATURE": m.object = arm

# 2. every location key (and its handles) x k
n_keys = 0
for act in actions:
    for cb in channelbags(act):
        for fc in cb.fcurves:
            if fc.data_path.endswith(".location"):
                for kp in fc.keyframe_points:
                    kp.co[1] *= k; kp.handle_left[1] *= k; kp.handle_right[1] *= k
                    n_keys += 1
                fc.update()

# 3. verify: every bone head/tail on every frame of every action is exactly k x its old position
worst = (0.0, None)
for act in actions:
    for f, (b0, b1) in enumerate(zip(before[act.name], heads(act))):
        for p0, p1 in zip(b0, b1):
            d = (p0 * k - p1).length
            if d > worst[0]: worst = (d, "%s f%d" % (act.name, f))
print("scaled x%.4f: %d objects, %d location keys in %d actions; max bone deviation from k x old %.4f mm (%s)"
      % (k, 1 + len(meshes), n_keys, len(actions), worst[0] * 1000, worst[1]))
if worst[0] > 5e-5:          # float32 round-off of the re-written rest matrices: ~0.01 mm over a 2.9 m gallop
    sys.exit("stage E: the scaled animation deviates from the exact k x original")
if prev_action: use_action(prev_action)

# 4. names
def rn(idb):
    if idb.name.startswith(old):
        idb.name = new + idb.name[len(old):]
for o in [arm] + meshes:
    rn(o); rn(o.data)
for m in bpy.data.materials:
    if m.name.startswith("M_" + old):
        m.name = "M_" + new + m.name[len("M_" + old):]
print("renamed:", arm.name, [o.name for o in meshes], sorted(m.name for m in bpy.data.materials))
bb = [arm.matrix_world @ v.co for v in bpy.data.objects[new + "_LOD0"].data.vertices]
print("LOD0 rest bbox min", [round(min(c[i] for c in bb), 3) for i in range(3)],
      "max", [round(max(c[i] for c in bb), 3) for i in range(3)])
os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(a.out))
bpy.ops.file.make_paths_relative()
bpy.ops.wm.save_mainfile()
print("saved", a.out)
