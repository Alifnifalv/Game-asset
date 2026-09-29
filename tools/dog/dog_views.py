"""Clay contact sheet of a dog model for shape work: orthographic side / front / back / top plus a 3/4 view and
close-ups of the head and a front paw.  Cycles CPU; keep --res <= 480 and --samples <= 12.

  python3 tools/dog/dog_views.py <model.glb|.blend|.fbx> <out.png> [--action NAME --frame N] [--res 420]
          [--samples 8] [--views side,front,back,top,three,head,paw] [--color clay|black]
"""
import argparse, math, os, sys, tempfile
import bpy
from mathutils import Vector

ap = argparse.ArgumentParser()
ap.add_argument("src"); ap.add_argument("out")
ap.add_argument("--action"); ap.add_argument("--frame", type=int, default=0)
ap.add_argument("--res", type=int, default=420)
ap.add_argument("--samples", type=int, default=8)
ap.add_argument("--views", default="side,front,back,top,three,head,headside,headfront,paw")
ap.add_argument("--color", default="clay")
ap.add_argument("--textured", action="store_true", help="keep the model's materials")
a = ap.parse_args()

bpy.ops.wm.read_factory_settings(use_empty=True)
ext = os.path.splitext(a.src)[1].lower()
if ext in (".glb", ".gltf"):
    bpy.ops.import_scene.gltf(filepath=a.src)
elif ext == ".fbx":
    bpy.ops.import_scene.fbx(filepath=a.src)
else:
    bpy.ops.wm.open_mainfile(filepath=a.src)
sc = bpy.context.scene
for o in list(sc.objects):
    if o.type in ("CAMERA", "LIGHT"):
        bpy.data.objects.remove(o)
arm = next((o for o in sc.objects if o.type == "ARMATURE"), None)
if arm and a.action:
    act = bpy.data.actions.get(a.action)
    if act is None:
        raise SystemExit(f"no action {a.action!r}: {[x.name for x in bpy.data.actions]}")
    arm.animation_data_create(); arm.animation_data.action = act
    if act.slots:
        arm.animation_data.action_slot = act.slots[0]
sc.frame_set(a.frame)
import re
for o in sc.objects:
    if o.type == "MESH" and re.search(r"_LOD[1-9]$", o.name):
        o.hide_render = True
meshes = [o for o in sc.objects if o.type == "MESH" and not o.hide_render]
if not a.textured:
    m = bpy.data.materials.new("clay"); m.use_nodes = True
    bsdf = m.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.72, 0.70, 0.66, 1) if a.color == "clay" else (0.05, 0.05, 0.055, 1)
    bsdf.inputs["Roughness"].default_value = 0.55
    for o in meshes:
        o.data.materials.clear(); o.data.materials.append(m)
dg = bpy.context.evaluated_depsgraph_get()
pts = []
for o in meshes:
    e = o.evaluated_get(dg); me = e.to_mesh()
    pts += [e.matrix_world @ v.co for v in me.vertices]; e.to_mesh_clear()
mn = Vector([min(p[i] for p in pts) for i in range(3)]); mx = Vector([max(p[i] for p in pts) for i in range(3)])
ctr = (mn + mx) / 2
print("BBOX", tuple(round(x, 3) for x in mn), tuple(round(x, 3) for x in mx))

w = bpy.data.worlds.new("W"); sc.world = w; w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.78, 0.80, 0.84, 1)
w.node_tree.nodes["Background"].inputs[1].default_value = 0.8
bpy.ops.mesh.primitive_plane_add(size=8, location=(ctr.x, ctr.y, 0))
g = bpy.data.materials.new("g"); g.use_nodes = True
g.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.5, 0.52, 0.5, 1)
bpy.context.object.data.materials.append(g)
bpy.ops.object.light_add(type="SUN", rotation=(math.radians(45), math.radians(-15), math.radians(-40)))
bpy.context.object.data.energy = 3.0; bpy.context.object.data.angle = math.radians(10)
sc.render.engine = "CYCLES"; sc.cycles.device = "CPU"; sc.cycles.samples = a.samples
sc.render.resolution_x = a.res; sc.render.resolution_y = int(a.res * 0.75)
sc.render.film_transparent = False
cam_d = bpy.data.cameras.new("cam"); cam = bpy.data.objects.new("cam", cam_d); sc.collection.objects.link(cam)
sc.camera = cam

size = max(mx - mn)
head = None
if arm and "Head" in arm.pose.bones:
    head = arm.matrix_world @ arm.pose.bones["Head"].tail
paw = None
if arm and "FrontFoot.L" in arm.pose.bones:
    paw = arm.matrix_world @ arm.pose.bones["FrontFoot.L"].tail
if head is None:        # no rig (an SDF preview): the anatomy's rest positions
    head = Vector((0, -0.575, 0.775))
if paw is None:
    paw = Vector((0.094, -0.29, 0.03))


def look(loc, target):
    cam.location = loc
    d = (Vector(target) - Vector(loc)).normalized()
    cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()


VIEWS = {
    "side":  dict(ortho=size * 1.08, loc=(ctr.x + 3, ctr.y, ctr.z), tgt=ctr),
    "front": dict(ortho=max(mx.x - mn.x, (mx.z - mn.z) / 0.75) * 1.08, loc=(ctr.x, ctr.y - 3, ctr.z), tgt=ctr),
    "back":  dict(ortho=max(mx.x - mn.x, (mx.z - mn.z) / 0.75) * 1.08, loc=(ctr.x, ctr.y + 3, ctr.z), tgt=ctr),
    "top":   dict(ortho=size * 1.08, loc=(ctr.x, ctr.y, ctr.z + 3), tgt=ctr),
    "three": dict(lens=50, loc=(ctr.x + 1.5, ctr.y - 1.9, ctr.z + 0.55), tgt=ctr),
    "head":  dict(lens=60, loc=(head.x + 0.30, head.y - 0.40, head.z + 0.08), tgt=head + Vector((0, 0.04, -0.01))),
    "headside": dict(ortho=0.36, loc=(head.x + 3, head.y + 0.05, head.z), tgt=head + Vector((0, 0.05, 0))),
    "headfront": dict(ortho=0.30, loc=(head.x, head.y - 3, head.z - 0.01), tgt=head + Vector((0, 0, -0.01))),
    "paw":   dict(lens=60, loc=(paw.x + 0.25, paw.y - 0.30, paw.z + 0.12), tgt=paw + Vector((0, 0.0, -0.01))),
}
tiles = []
tmp = tempfile.mkdtemp()
for vname in a.views.split(","):
    v = VIEWS[vname]
    if "ortho" in v:
        cam_d.type = "ORTHO"; cam_d.ortho_scale = v["ortho"]
    else:
        cam_d.type = "PERSP"; cam_d.lens = v["lens"]
    look(v["loc"], v["tgt"])
    if vname == "top":
        cam.rotation_euler = (0, 0, math.radians(90))
    p = os.path.join(tmp, vname + ".png"); sc.render.filepath = p
    bpy.ops.render.render(write_still=True)
    tiles.append((vname, p))

import numpy as np
from PIL import Image, ImageDraw
ims = [Image.open(p).convert("RGB") for _, p in tiles]
W, H = ims[0].size; cols = min(4, len(ims)); rows = (len(ims) + cols - 1) // cols
sheet = Image.new("RGB", (W * cols, H * rows), (255, 255, 255))
for i, (im, (n, _)) in enumerate(zip(ims, tiles)):
    ImageDraw.Draw(im).text((5, 5), n, fill=(0, 0, 0))
    sheet.paste(im, ((i % cols) * W, (i // cols) * H))
sheet.save(a.out)
print("WROTE", a.out)
