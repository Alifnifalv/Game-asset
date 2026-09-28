"""Fur textures for the optional Unity shell fur (Unity/Calf/Fur).

python3 tools/calf_fur_textures.py [--in build/stage_b.blend] [--tex-dir build/textures] [--res 1024]

T_Calf_FurMask.png   R = fur length multiplier in UV space of Calf_LOD0 (0 = no fur: nose pad, hooves, eyes;
                     0.35 = body coat; up to 1.0 = forehead tuft and tail switch). Islands are padded so mips don't bleed.
T_Fur_Noise.png      tileable strand noise (per-texel random strand heights), sampled with high tiling by the shell shader.
"""
import argparse, os, sys
import numpy as np
import bpy
from mathutils import Vector
from PIL import Image, ImageDraw, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ap = argparse.ArgumentParser()
ap.add_argument("--in", dest="src", default=os.path.join(ROOT, "build", "stage_b.blend"))
ap.add_argument("--tex-dir", default=os.path.join(ROOT, "build", "textures"))
ap.add_argument("--res", type=int, default=1024)
a = ap.parse_args()
os.makedirs(a.tex_dir, exist_ok=True)

bpy.ops.wm.open_mainfile(filepath=a.src)
ob = bpy.data.objects["Calf_LOD0"]; arm = bpy.data.objects["CalfRig"]
me = ob.data
uv = me.uv_layers["UVMap"].data
part = me.attributes["orig_part"].data
head = arm.data.bones["Head"]
# forehead tuft centre: top of the skull between the ears (above the Head joint, slightly forward)
poll = head.head_local + Vector((0, -0.05, 0.02))
gi = {g.name: g.index for g in ob.vertex_groups}
tail_ids = {gi[n] for n in ("Tail5", "Tail6", "Tail7") if n in gi}
ear_ids = {gi[n] for n in ("Ear.L", "Ear.R") if n in gi}

def face_len(p):
    k = part[p.index].value
    if k in (2, 3, 4):
        return 0.0
    c = sum((me.vertices[v].co for v in p.vertices), Vector()) / len(p.vertices)
    L = 0.35
    d = (c - poll).length
    if d < 0.09 and c.z > poll.z - 0.08:
        L = max(L, 1.0 - 0.65 * (d / 0.09))
    tw = sum(g.weight for v in p.vertices for g in me.vertices[v].groups if g.group in tail_ids) / len(p.vertices)
    if tw > 0.3:
        L = max(L, 0.35 + 0.6 * min(1.0, (tw - 0.3) / 0.5))
    ew = sum(g.weight for v in p.vertices for g in me.vertices[v].groups if g.group in ear_ids) / len(p.vertices)
    if ew > 0.5:
        L = 0.25                                   # short, fine ear hair
    return L

R = a.res
img = Image.new("L", (R, R), 0)
cover = Image.new("L", (R, R), 0)
d = ImageDraw.Draw(img); dc = ImageDraw.Draw(cover)
for p in me.polygons:
    if part[p.index].value == 4:
        continue                                   # eyeballs use their own UVs/material
    pts = [(uv[li].uv.x * R, (1 - uv[li].uv.y) * R) for li in p.loop_indices]
    v = int(round(face_len(p) * 255))
    d.polygon(pts, fill=v); dc.polygon(pts, fill=255)
m = np.asarray(img).astype(np.float32); cov = np.asarray(cover) > 0
# pad islands: repeatedly spread covered texels into uncovered neighbours (16 px)
for _ in range(16):
    grow = ~cov
    acc = np.zeros_like(m); cnt = np.zeros_like(m)
    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        sm = np.roll(np.roll(m, dy, 0), dx, 1); sc = np.roll(np.roll(cov, dy, 0), dx, 1)
        acc += sm * sc; cnt += sc
    fill = grow & (cnt > 0)
    m[fill] = acc[fill] / cnt[fill]; cov = cov | fill
out = Image.fromarray(np.clip(m, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.2))
out.save(os.path.join(a.tex_dir, "T_Calf_FurMask.png"))

rng = np.random.default_rng(7)
N = 256
noise = rng.random((N, N)).astype(np.float32)
noise = noise ** 0.8                              # a few more tall strands
Image.fromarray((noise * 255).astype(np.uint8)).save(os.path.join(a.tex_dir, "T_Fur_Noise.png"))
print("wrote", os.path.join(a.tex_dir, "T_Calf_FurMask.png"), "and T_Fur_Noise.png", "coverage %.1f%%" % (100 * (np.asarray(cover) > 0).mean()))
