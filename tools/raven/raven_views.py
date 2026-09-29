"""Clay contact sheet of the raven for shape work (Cycles CPU; keep --res <= 480, --samples <= 12), and a side-view
silhouette overlay on the GiM perched still 88c16e0c (known scale 0.4486 mm/px, origin = the near foot at (1165, 995)).

  python3 tools/raven/raven_views.py <model.glb|.blend|.fbx> <out.png> [--action NAME --frame N] [--res 420]
          [--samples 8] [--views side,front,top,three,head,headfront,foot,wing] [--color clay|black] [--textured]
          [--cmp88 <overlay.png>]
"""
import argparse, math, os, re, sys, tempfile
import bpy
from mathutils import Vector

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ap = argparse.ArgumentParser()
ap.add_argument("src"); ap.add_argument("out")
ap.add_argument("--action"); ap.add_argument("--frame", type=int, default=0)
ap.add_argument("--res", type=int, default=420)
ap.add_argument("--samples", type=int, default=8)
ap.add_argument("--views", default="side,front,top,three,head,headfront,foot,wing")
ap.add_argument("--color", default="clay")
ap.add_argument("--textured", action="store_true")
ap.add_argument("--cmp88", default=None, help="also write a silhouette overlay on ravan/88c16e0c*.webp")
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
for o in sc.objects:
    if o.type == "MESH" and re.search(r"_LOD[1-9]$", o.name):
        o.hide_render = True
meshes = [o for o in sc.objects if o.type == "MESH" and not o.hide_render]
if not a.textured:
    m = bpy.data.materials.new("clay"); m.use_nodes = True
    bsdf = m.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.72, 0.70, 0.66, 1) if a.color == "clay" else (0.03, 0.03, 0.035, 1)
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
ground = bpy.context.object
g = bpy.data.materials.new("g"); g.use_nodes = True
g.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.5, 0.52, 0.5, 1)
ground.data.materials.append(g)
bpy.ops.object.light_add(type="SUN", rotation=(math.radians(45), math.radians(-15), math.radians(-40)))
bpy.context.object.data.energy = 3.0; bpy.context.object.data.angle = math.radians(10)
sc.render.engine = "CYCLES"; sc.cycles.device = "CPU"; sc.cycles.samples = a.samples
sc.render.resolution_x = a.res; sc.render.resolution_y = int(a.res * 0.75)
cam_d = bpy.data.cameras.new("cam"); cam = bpy.data.objects.new("cam", cam_d); sc.collection.objects.link(cam)
sc.camera = cam


def bone_point(name, fallback, tail=False):
    if arm and name in arm.pose.bones:
        pb = arm.pose.bones[name]
        return arm.matrix_world @ (pb.tail if tail else pb.head)
    return Vector(fallback)


head = bone_point("Head", (0, -0.235, 0.352), tail=False) + Vector((0, -0.02, 0.005))
foot = bone_point("Tarsus.L", (0.042, 0.0, 0.012), tail=True)
wrist = bone_point("Hand.L", (0.222, -0.108, 0.272))
# body extent without the spread wings (|x| < 0.09)
bpts = [p for p in pts if abs(p.x) < 0.09]
bmn = Vector([min(p[i] for p in bpts) for i in range(3)]); bmx = Vector([max(p[i] for p in bpts) for i in range(3)])
bctr = (bmn + bmx) / 2
bsize = max(bmx.y - bmn.y, (bmx.z - bmn.z) / 0.75)


def look(loc, target):
    cam.location = loc
    d = (Vector(target) - Vector(loc)).normalized()
    cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()


VIEWS = {
    "side":  dict(ortho=bsize * 1.1, loc=(bctr.x + 3, bctr.y, bctr.z), tgt=bctr),
    "front": dict(ortho=max(mx.x - mn.x, (mx.z - mn.z) / 0.75) * 1.05, loc=(ctr.x, ctr.y - 3, ctr.z), tgt=ctr),
    "back":  dict(ortho=max(mx.x - mn.x, (mx.z - mn.z) / 0.75) * 1.05, loc=(ctr.x, ctr.y + 3, ctr.z), tgt=ctr),
    "top":   dict(ortho=max(mx.x - mn.x, (mx.y - mn.y) / 0.75) * 1.05, loc=(ctr.x, ctr.y, ctr.z + 3), tgt=ctr),
    "three": dict(lens=50, loc=(ctr.x + 1.2, ctr.y - 1.5, ctr.z + 0.55), tgt=ctr),
    "head":  dict(lens=70, loc=(head.x + 0.22, head.y - 0.22, head.z + 0.06), tgt=head),
    "headside": dict(ortho=0.16, loc=(head.x + 3, head.y, head.z), tgt=head),
    "headfront": dict(ortho=0.14, loc=(head.x, head.y - 3, head.z), tgt=head),
    "foot":  dict(lens=70, loc=(foot.x + 0.16, foot.y - 0.22, foot.z + 0.10), tgt=foot + Vector((0, -0.01, 0.01))),
    "wingside": dict(ortho=0.40, loc=(3.0, 0.02, 0.20), tgt=(0.0, 0.02, 0.20)),
    "backq": dict(lens=60, loc=(0.55, 0.75, 0.55), tgt=(0.0, 0.0, 0.20)),
    "frontq": dict(lens=60, loc=(0.60, -0.75, 0.45), tgt=(0.0, -0.05, 0.22)),
    "wing":  dict(ortho=0.62, loc=(0.26, -0.02 + 3 * 0.53, 0.26 + 3 * 0.848), tgt=(0.26, -0.02, 0.26)),
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

if a.cmp88:
    # silhouette of the model (black, no ground) rendered with the photo's scale, overlaid in red on 88c16e0c
    k = 0.4486e-3
    ground.hide_render = True
    sc.render.film_transparent = True
    sc.render.resolution_x, sc.render.resolution_y = 960, 540            # half resolution of the photo
    cam_d.type = "ORTHO"; cam_d.ortho_scale = 1920 * k
    cy, cz = (960 - 1165) * k, (995 - 540) * k
    look((3.0, cy, cz), (0.0, cy, cz))
    sc.cycles.samples = 2
    p = os.path.join(tmp, "cmp.png"); sc.render.filepath = p
    bpy.ops.render.render(write_still=True)
    sil = np.asarray(Image.open(p).convert("RGBA"))[..., 3] > 128
    # the camera looks along -X: image left = -Y (the bill), as in the photo (bird facing left)
    ref = [f for f in os.listdir(os.path.join(ROOT, "ravan")) if f.startswith("88c16e0c")][0]
    photo = Image.open(os.path.join(ROOT, "ravan", ref)).convert("RGB").resize((960, 540))
    ph = np.asarray(photo).astype(float)
    out = ph * 0.75
    edge = sil ^ np.roll(sil, 1, 0) | sil ^ np.roll(sil, 1, 1)
    out[sil] = out[sil] * 0.55 + np.array([255, 60, 60]) * 0.45
    out[edge] = (255, 0, 0)
    Image.fromarray(out.clip(0, 255).astype(np.uint8)).save(a.cmp88)
    print("WROTE", a.cmp88)
