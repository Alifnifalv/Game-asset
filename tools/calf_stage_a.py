"""Stage A: import cow.glb, strip Sketchfab hierarchy, remove horns/udder/stray mesh,
join all skinned parts into one mesh, weld material seams, recover quads, clean bone names.
Output: build/stage_a.blend
"""
import bpy, bmesh, re, sys, os
from mathutils import Vector

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "cow.glb")
OUT = os.path.join(ROOT, "build", "stage_a.blend")

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=SRC)

arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
meshes = [o for o in bpy.data.objects if o.type == "MESH" and o.parent == arm]

# --- unparent armature, delete empties + stray icosphere --------------------
mw = arm.matrix_world.copy()
arm.parent = None
arm.matrix_world = mw
for o in list(bpy.data.objects):
    if o.type == "EMPTY" or o.name == "Icosphere":
        bpy.data.objects.remove(o, do_unlink=True)

def mat_of(o):
    return o.material_slots[0].material.name if o.material_slots and o.material_slots[0].material else ""

# --- delete horns, stylised eye decals ---------------------------------------
for o in list(meshes):
    if mat_of(o) in ("Horns", "Eye_Black", "Eye_White"):
        meshes.remove(o)
        bpy.data.objects.remove(o, do_unlink=True)

def delete_verts(o, pred):
    bm = bmesh.new(); bm.from_mesh(o.data)
    kill = [v for v in bm.verts if pred(v.co)]
    bmesh.ops.delete(bm, geom=kill, context="VERTS")
    bm.to_mesh(o.data); bm.free()
    return len(kill)

for o in meshes:
    m = mat_of(o)
    if m == "Muzzle":      # second island = udder (behind y=-3)
        print("udder verts removed:", delete_verts(o, lambda c: c.y > -3.0))
    if m == "Main":        # tiny eye-ring islands that framed the cartoon eye decal
        n = delete_verts(o, lambda c: abs(c.x) > 0.43 and abs(c.x) < 0.6 and -4.45 < c.y < -4.2 and 3.69 < c.z < 3.92 and False)
    if m == "Hooves":      # dewclaws are floating 6-vert islands; keep (they read as dewclaws) 
        pass

# --- join into one mesh --------------------------------------------------------
bpy.ops.object.select_all(action="DESELECT")
for o in meshes:
    o.select_set(True)
body = next(o for o in meshes if mat_of(o) == "Main")
bpy.context.view_layer.objects.active = body
bpy.ops.object.join()
body.name = "Calf"
body.data.name = "Calf"

# record original material per face as an int attribute (used later for region hints)
me = body.data
names = [s.material.name for s in body.material_slots]
attr = me.attributes.new("orig_part", "INT", "FACE")
for p in me.polygons:
    attr.data[p.index].value = p.material_index
print("parts:", list(enumerate(names)))

# --- weld seams + tris->quads ------------------------------------------------
bm = bmesh.new(); bm.from_mesh(me)
before = len(bm.verts)
bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
after = len(bm.verts)
bm.to_mesh(me); bm.free()
print("welded", before - after, "verts")

bpy.ops.object.select_all(action="DESELECT")
body.select_set(True); bpy.context.view_layer.objects.active = body
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.mesh.tris_convert_to_quads(face_threshold=0.698, shape_threshold=0.698, uvs=False, vcols=False, seam=False, sharp=False, materials=True)
bpy.ops.mesh.select_all(action="DESELECT")
bpy.ops.object.mode_set(mode="OBJECT")

bm = bmesh.new(); bm.from_mesh(me)
import collections
print("face sizes:", dict(collections.Counter(len(f.verts) for f in bm.faces)))
print("boundary edges:", sum(1 for e in bm.edges if e.is_boundary), "non-manifold:", sum(1 for e in bm.edges if not e.is_manifold))
bm.free()

# --- clean bone names (strip _NN suffix) and fix every action's data paths --------
rename = {}
for b in arm.data.bones:
    new = "Root" if b.name == "GLTF_created_0_rootJoint" else re.sub(r"_\d+$", "", b.name)
    rename[b.name] = new
for old, new in rename.items():
    arm.data.bones[old].name = new
for vg in body.vertex_groups:
    if vg.name in rename:
        vg.name = rename[vg.name]
def channelbags(act):
    for l in act.layers:
        for s in l.strips:
            for cb in s.channelbags:
                yield cb
for act in bpy.data.actions:
    for cb in channelbags(act):
        for fc in cb.fcurves:
            for old, new in rename.items():
                tok = f'pose.bones["{old}"]'
                if tok in fc.data_path:
                    fc.data_path = fc.data_path.replace(tok, f'pose.bones["{new}"]')
        for g in cb.groups:
            if g.name in rename:
                g.name = rename[g.name]
arm.name = "CalfRig"; arm.data.name = "CalfRig"
# drop unused vertex groups (bones that deform nothing stay in the rig, harmless)
print("bones:", [b.name for b in arm.data.bones])
print("vgroups:", len(body.vertex_groups))
bad = []
for act in bpy.data.actions:
    for cb in channelbags(act):
        for fc in cb.fcurves:
            bn = fc.data_path.split('"')[1] if '"' in fc.data_path else None
            if bn and bn not in arm.data.bones:
                bad.append((act.name, fc.data_path))
print("dangling fcurves:", bad[:5], len(bad))
bpy.ops.wm.save_as_mainfile(filepath=OUT)
print("saved", OUT)
