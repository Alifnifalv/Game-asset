"""Headless turntable/contact-sheet renderer (Cycles CPU).

Usage: python3 tools/render_views.py <model.glb|.blend|.fbx> <out.png> [--frame N] [--action NAME] [--res 480]
                                     [--samples 24] [--views side,front,threequarter,back,top,head]
Renders side / front / 3-4 / top / back / close-up-head views into one contact sheet.
Keep --samples <= 12 on the shared 4-core container (the default is 24).
--action: if no action has exactly this name the rest pose is rendered WITHOUT a warning. Blender's FBX importer names
the actions "<armature>|<take>", so for Unity/Calf/Calf.fbx pass e.g. --action "CalfRig|Walk"; .blend and .glb keep
the plain clip names.
"""
import sys, math, os, argparse
import bpy
from mathutils import Vector

ap = argparse.ArgumentParser()
ap.add_argument("src"); ap.add_argument("out")
ap.add_argument("--frame", type=int, default=0)
ap.add_argument("--action", default=None)
ap.add_argument("--res", type=int, default=480)
ap.add_argument("--samples", type=int, default=24)
ap.add_argument("--views", default="side,front,threequarter,back,top,head")
a = ap.parse_args(sys.argv[1:])

bpy.ops.wm.read_factory_settings(use_empty=True)
ext = os.path.splitext(a.src)[1].lower()
if ext in (".glb", ".gltf"):
    bpy.ops.import_scene.gltf(filepath=a.src)
elif ext == ".fbx":
    bpy.ops.import_scene.fbx(filepath=a.src)
elif ext == ".blend":
    bpy.ops.wm.open_mainfile(filepath=a.src)
sc = bpy.context.scene

arm = next((o for o in sc.objects if o.type == "ARMATURE"), None)
if arm and a.action:
    act = bpy.data.actions.get(a.action)
    if act:
        arm.animation_data_create(); arm.animation_data.action = act
        if hasattr(arm.animation_data, "action_slot") and act.slots:
            arm.animation_data.action_slot = act.slots[0]
sc.frame_set(a.frame)
bpy.context.view_layer.update()

import re as _re
for o in sc.objects:   # only render the highest LOD
    if o.type == "MESH" and _re.search(r"_LOD[1-9]$", o.name):
        o.hide_render = True; o.hide_set(True)
meshes = [o for o in sc.objects if o.type == "MESH" and o.visible_get() and o.name != "Icosphere"]
for o in sc.objects:
    if o.type == "MESH" and o.name == "Icosphere":
        o.hide_render = True
dg = bpy.context.evaluated_depsgraph_get()
pts = []
for o in meshes:
    e = o.evaluated_get(dg)
    m = e.to_mesh()
    pts += [e.matrix_world @ v.co for v in m.vertices]
    e.to_mesh_clear()
mn = Vector([min(p[i] for p in pts) for i in range(3)])
mx = Vector([max(p[i] for p in pts) for i in range(3)])
ctr = (mn + mx) / 2; size = (mx - mn).length
print("BBOX", tuple(round(x, 3) for x in mn), tuple(round(x, 3) for x in mx))

# forward axis = longest horizontal extent; head end = the end with higher max z
dims = mx - mn
fwd_axis = 0 if dims.x > dims.y else 1

# world
w = bpy.data.worlds.new("W"); sc.world = w; w.use_nodes = True
bg = w.node_tree.nodes["Background"]; bg.inputs[0].default_value = (0.82, 0.84, 0.86, 1); bg.inputs[1].default_value = 0.9
# ground
bpy.ops.mesh.primitive_plane_add(size=size * 6, location=(ctr.x, ctr.y, mn.z))
gmat = bpy.data.materials.new("ground"); gmat.use_nodes = True
gmat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.55, 0.6, 0.45, 1)
bpy.context.object.data.materials.append(gmat)
# key + fill light
bpy.ops.object.light_add(type="SUN", rotation=(math.radians(50), math.radians(10), math.radians(35)))
bpy.context.object.data.energy = 3.5; bpy.context.object.data.angle = math.radians(8)

sc.render.engine = "CYCLES"; sc.cycles.device = "CPU"; sc.cycles.samples = a.samples
sc.cycles.use_denoising = True
try: sc.cycles.denoiser = "OPENIMAGEDENOISE"
except Exception: pass
sc.render.resolution_x = a.res; sc.render.resolution_y = int(a.res * 0.75)
sc.render.film_transparent = False
sc.view_settings.view_transform = "AgX" if "AgX" in [i.identifier for i in sc.view_settings.bl_rna.properties["view_transform"].enum_items] else "Filmic"

cam_data = bpy.data.cameras.new("cam"); cam = bpy.data.objects.new("cam", cam_data)
sc.collection.objects.link(cam); sc.camera = cam
cam_data.lens = 50

# determine head direction: centroid of top 5% z points
top = sorted(pts, key=lambda p: -p.z)[: max(10, len(pts) // 20)]
head_c = sum(top, Vector()) / len(top)
if arm and "Head" in arm.data.bones:   # rest-pose head position is robust to head-down poses
    head_c = arm.matrix_world @ arm.data.bones["Head"].head_local
head_sign = 1 if head_c[fwd_axis] > ctr[fwd_axis] else -1
fwd = Vector((0, 0, 0)); fwd[fwd_axis] = head_sign
side = fwd.cross(Vector((0, 0, 1))).normalized()

def look(loc, target):
    cam.location = loc
    d = (target - loc)
    cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()

views = {
    "side": (ctr + side * size * 1.7 + Vector((0, 0, size * 0.05)), ctr),
    "front": (ctr + fwd * size * 1.7 + Vector((0, 0, size * 0.1)), ctr),
    "threequarter": (ctr + (fwd + side).normalized() * size * 1.6 + Vector((0, 0, size * 0.35)), ctr),
    "back": (ctr - fwd * size * 1.7 + Vector((0, 0, size * 0.1)), ctr),
    "top": (ctr + Vector((0, 0, size * 1.9)) + side * 0.001, ctr),
    "otherside": (ctr - side * size * 1.7 + Vector((0, 0, size * 0.05)), ctr),
}
hc = head_c.copy()
if arm and "Head" in arm.pose.bones:   # frame the real head when the rig is available
    pb = arm.pose.bones["Head"]
    hc = arm.matrix_world @ ((pb.head + pb.tail) / 2)
views["head"] = (hc + (fwd * 0.9 + side * 0.9).normalized() * size * 0.75 + Vector((0, 0, size * 0.05)), hc - Vector((0, 0, size * 0.03)))

import tempfile
tmpd = tempfile.mkdtemp()
files = []
for name in a.views.split(","):
    loc, tgt = views[name]
    look(loc, tgt)
    sc.render.filepath = os.path.join(tmpd, name + ".png")
    bpy.ops.render.render(write_still=True)
    files.append(sc.render.filepath)

from PIL import Image, ImageDraw
ims = [Image.open(f).convert("RGB") for f in files]
cols = 3; rows = math.ceil(len(ims) / cols)
W, H = ims[0].size
sheet = Image.new("RGB", (W * cols, H * rows), (255, 255, 255))
for i, (im, n) in enumerate(zip(ims, a.views.split(","))):
    d = ImageDraw.Draw(im); d.text((6, 6), n, fill=(0, 0, 0))
    sheet.paste(im, ((i % cols) * W, (i // cols) * H))
sheet.save(a.out)
print("WROTE", a.out)
