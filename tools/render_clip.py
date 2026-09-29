"""Render an action as a side-view filmstrip (+ animated GIF) with a camera that tracks the Root.
python3 tools/render_clip.py <file.blend> <Action> <out_prefix> [--frames 0:24:3] [--res 360] [--samples 8] [--side left|right|front|threequarter]
Writes <out_prefix>.png (strip) and <out_prefix>.gif."""
import sys, os, math, argparse, tempfile
import bpy
from mathutils import Vector
ap = argparse.ArgumentParser()
ap.add_argument("src"); ap.add_argument("action"); ap.add_argument("out")
ap.add_argument("--frames", default=None); ap.add_argument("--res", type=int, default=360)
ap.add_argument("--samples", type=int, default=8); ap.add_argument("--side", default="left")
ap.add_argument("--cols", type=int, default=6)
a = ap.parse_args(sys.argv[1:])
bpy.ops.wm.open_mainfile(filepath=a.src)
sc = bpy.context.scene
arm = bpy.data.objects["CalfRig"]
act = bpy.data.actions[a.action]
ad = arm.animation_data_create(); ad.action = act
if act.slots: ad.action_slot = act.slots[0]
for o in sc.objects:
    if o.type == "MESH" and not o.name.endswith("_LOD0"): o.hide_render = True
    if o.type == "MESH":
        for m in o.modifiers:
            if m.type == "ARMATURE": m.show_viewport = True; m.show_render = True
lo, hi = int(act.frame_range[0]), int(act.frame_range[1])
if a.frames:
    s0, s1, st = (int(x) for x in a.frames.split(":"))
    frames = list(range(s0, s1 + 1, st))
else:
    frames = list(range(lo, hi + 1, max(1, (hi - lo) // 11)))
w = bpy.data.worlds.new("W"); sc.world = w; w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.8, 0.83, 0.86, 1)
bpy.ops.mesh.primitive_plane_add(size=60, location=(0, 0, 0))
gm = bpy.data.materials.new("g"); gm.use_nodes = True
bsdf = gm.node_tree.nodes["Principled BSDF"]
# checker ground so foot sliding is visible
tex = gm.node_tree.nodes.new("ShaderNodeTexChecker"); tex.inputs["Scale"].default_value = 60.0
tex.inputs[1].default_value = (0.55, 0.6, 0.45, 1); tex.inputs[2].default_value = (0.45, 0.5, 0.36, 1)
gm.node_tree.links.new(tex.outputs[0], bsdf.inputs["Base Color"])
bpy.context.object.data.materials.append(gm)
bpy.ops.object.light_add(type="SUN", rotation=(math.radians(50), 0, math.radians(30)))
bpy.context.object.data.energy = 3.5
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); sc.collection.objects.link(cam); sc.camera = cam
cam.data.lens = 40
sc.render.engine = "CYCLES"; sc.cycles.device = "CPU"; sc.cycles.samples = a.samples
sc.cycles.use_denoising = True
sc.render.resolution_x = a.res; sc.render.resolution_y = int(a.res * 0.75)
offs = {"left": Vector((3.2, 0, 0.45)), "right": Vector((-3.2, 0, 0.45)), "front": Vector((0, -3.4, 0.6)),
        "threequarter": Vector((2.4, -2.4, 0.9))}[a.side]
tmp = tempfile.mkdtemp(); files = []
for f in frames:
    sc.frame_set(f)
    dg = bpy.context.evaluated_depsgraph_get(); ae = arm.evaluated_get(dg)
    root = ae.matrix_world @ ae.pose.bones["Root"].head
    tgt = Vector((root.x, root.y - 0.25, 0.5))
    cam.location = tgt + offs
    cam.rotation_euler = (tgt - cam.location).to_track_quat("-Z", "Y").to_euler()
    sc.render.filepath = os.path.join(tmp, "f%04d.png" % f)
    bpy.ops.render.render(write_still=True)
    files.append((f, sc.render.filepath))
from PIL import Image, ImageDraw
ims = []
for f, p in files:
    im = Image.open(p).convert("RGB"); ImageDraw.Draw(im).text((5, 5), "%s f%d" % (a.action, f), fill=(0, 0, 0)); ims.append(im)
cols = min(a.cols, len(ims)); rows = math.ceil(len(ims) / cols)
W, H = ims[0].size
strip = Image.new("RGB", (W * cols, H * rows), "white")
for i, im in enumerate(ims): strip.paste(im, ((i % cols) * W, (i // cols) * H))
strip.save(a.out + ".png")
ims[0].save(a.out + ".gif", save_all=True, append_images=ims[1:], duration=int(1000 / 30 * (frames[1] - frames[0] if len(frames) > 1 else 1)), loop=0)
print("WROTE", a.out + ".png", a.out + ".gif")
