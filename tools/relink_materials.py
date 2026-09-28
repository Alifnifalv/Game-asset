"""Rebuild build/stage_c.blend from a NEW stage B plus the materials/images of an existing stage C, without re-baking
textures (used by `tools/build_all.sh --skip-textures`). Valid only while stage B's UV layout is unchanged: the script
compares the LOD0 UV coordinates of both files and refuses (exit 2) if they differ, because the old textures would no
longer fit. Otherwise stage C would silently keep its OLD mesh (it stores its own copy) and the animations/export would
run on stale geometry.

python3 tools/relink_materials.py --stage-b build/stage_b.blend --old-c build/stage_c.blend --out build/stage_c.blend
"""
import argparse, os, sys
import numpy as np
import bpy

ap = argparse.ArgumentParser()
ap.add_argument("--stage-b", required=True); ap.add_argument("--old-c", required=True); ap.add_argument("--out", required=True)
a = ap.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else None)

def uvs(path):
    bpy.ops.wm.open_mainfile(filepath=path)
    me = bpy.data.objects["Calf_LOD0"].data
    arr = np.zeros(len(me.uv_layers["UVMap"].data) * 2, np.float32)
    me.uv_layers["UVMap"].data.foreach_get("uv", arr)
    return arr

old_c = os.path.abspath(a.old_c)
if not os.path.exists(old_c):
    sys.exit("relink: no existing stage C at %s; run the textures step" % old_c)
u_old = uvs(old_c); u_new = uvs(a.stage_b)
if u_old.shape != u_new.shape or np.abs(u_old - u_new).max() > 1e-5:
    print("relink: stage B UV layout changed since the textures were baked -> re-run textures (no --skip-textures)")
    sys.exit(2)
# stage B is open: pull the materials (with their image datablocks) from the old stage C by name
with bpy.data.libraries.load(old_c, link=False) as (src, dst):
    dst.materials = [m for m in src.materials if m in ("M_Calf_Body", "M_Calf_Eye")]
new = {m.name: m for m in dst.materials}
for ob in [o for o in bpy.data.objects if o.type == "MESH"]:
    for slot in ob.material_slots:
        base = slot.material.name.split(".")[0] if slot.material else None
        if base in new:
            slot.material = new[base]
for m in list(bpy.data.materials):
    if m.users == 0: bpy.data.materials.remove(m)
for m in new.values():
    m.name = m.name.split(".")[0]
# keep image paths relative to the output location
out = os.path.abspath(a.out)
for img in bpy.data.images:
    if img.filepath and not img.packed_file:
        img.filepath = bpy.path.relpath(bpy.path.abspath(img.filepath, library=img.library), start=os.path.dirname(out))
bpy.ops.wm.save_as_mainfile(filepath=out)
print("relink: stage C rebuilt from", a.stage_b, "with materials of the previous stage C ->", out)
