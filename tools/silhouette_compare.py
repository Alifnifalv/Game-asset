"""Orthographic side-view silhouette of the calf next to (and overlaid on) the side-view reference,
both normalised to the same withers-to-ground height.  python3 tools/silhouette_compare.py <blend> <ref.png> <out.png>"""
import sys, os, numpy as np, bpy
from mathutils import Vector
src, ref, out = sys.argv[1:4]
bpy.ops.wm.open_mainfile(filepath=src)
sc = bpy.context.scene
for o in sc.objects:
    if o.type == "MESH" and not o.name.endswith("_LOD0"):
        o.hide_render = True
ob = sc.objects["Calf_LOD0"]
dg = bpy.context.evaluated_depsgraph_get()
e = ob.evaluated_get(dg); m = e.to_mesh()
ys = [v.co.y for v in m.vertices]; zs = [v.co.z for v in m.vertices]
e.to_mesh_clear()
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); sc.collection.objects.link(cam); sc.camera = cam
cam.data.type = "ORTHO"; cam.data.ortho_scale = 2.4
cam.location = (5, (min(ys) + max(ys)) / 2, 0.55); cam.rotation_euler = (1.5708, 0, 1.5708)
sc.render.engine = "BLENDER_WORKBENCH" if False else "CYCLES"
sc.cycles.samples = 1; sc.render.film_transparent = True
sc.render.resolution_x = 1200; sc.render.resolution_y = 700
sc.render.filepath = out + ".tmp.png"
bpy.ops.render.render(write_still=True)
from PIL import Image
a = np.array(Image.open(out + ".tmp.png"))[..., 3] > 10
def crop_norm(mask, H=500):
    rows = np.where(mask.any(1))[0]; cols = np.where(mask.any(0))[0]
    mk = mask[rows[0]:rows[-1] + 1, cols[0]:cols[-1] + 1]
    s = H / mk.shape[0]
    im = Image.fromarray((mk * 255).astype(np.uint8)).resize((int(mk.shape[1] * s), H))
    return np.array(im) > 127
r = np.array(Image.open(ref).convert("RGB")).astype(int)
rm = (np.abs(r - r[5, 5]).sum(-1) > 60)  # not background
# drop soft shadow at the bottom: keep rows where object pixels are not just shadow
A = crop_norm(a); R = crop_norm(rm)
# calf faces left in render (-Y to the left) ; reference faces right -> mirror reference
R = R[:, ::-1]
W = max(A.shape[1], R.shape[1]) + 20
canvas = np.full((520, W, 3), 255, np.uint8)
def paste(mask, col):
    canvas[10:10 + mask.shape[0], 10:10 + mask.shape[1]][mask] = (canvas[10:10 + mask.shape[0], 10:10 + mask.shape[1]][mask] * 0.45 + np.array(col) * 0.55).astype(np.uint8)
paste(R, (255, 120, 0)); paste(A, (0, 90, 255))
side = np.full((520, A.shape[1] + R.shape[1] + 40, 3), 255, np.uint8)
side[10:10 + A.shape[0], 10:10 + A.shape[1]][A] = (40, 90, 200)
side[10:10 + R.shape[0], 30 + A.shape[1]:30 + A.shape[1] + R.shape[1]][R] = (220, 120, 40)
Image.fromarray(np.vstack([side[:, :max(side.shape[1], W)], np.pad(canvas, ((0, 0), (0, side.shape[1] - W), (0, 0)), constant_values=255)])).save(out)
os.remove(out + ".tmp.png")
print("model aspect L/H %.2f  ref aspect L/H %.2f" % (A.shape[1] / A.shape[0], R.shape[1] / R.shape[0]))
