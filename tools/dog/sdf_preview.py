"""Quick look at the SDF body: marching cubes at --h, write a GLB (no rig) for tools/render_views.py.

  python3 tools/dog/sdf_preview.py --h 0.004 --out <scratch>/body.glb [--parts]
"""
import argparse, os, sys, time
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import anatomy as A
from sdf import Field

ap = argparse.ArgumentParser()
ap.add_argument("--h", type=float, default=0.004)
ap.add_argument("--out", required=True)
ap.add_argument("--parts", action="store_true")
a = ap.parse_args()

import trimesh

t = time.time()
F = Field((-0.20, -0.74, -0.004), (0.20, 0.54, 0.93), a.h)
for p in A.body_prims():
    F.add(p)
v, f = F.mesh()
print(f"body grid {F.shape} -> {len(v)} verts {len(f)} tris ({time.time() - t:.1f} s)")
meshes = [trimesh.Trimesh(v, f, process=False)]
if a.parts:
    def quads(f):
        return [t for q in f for t in ((q[0], q[1], q[2]), (q[0], q[2], q[3]))]
    for s in "LR":
        ev, ef, *_ = A.ear_mesh(s)
        meshes.append(trimesh.Trimesh(ev, quads(ef), process=False))
        ev, ef, _ = A.eye_mesh(s)
        meshes.append(trimesh.Trimesh(ev, quads(ef), process=False))
    for name, prims, h in (("claws", A.claw_prims(), 0.0008),
                           ("teeth", A.teeth_prims(), 0.0006),
                           ("tongue", A.tongue_prims(), 0.0012)):
        lo = np.min([p.aabb()[0] for p in prims], axis=0) - 0.004
        hi = np.max([p.aabb()[1] for p in prims], axis=0) + 0.004
        G = Field(lo, hi, h)
        for p in prims:
            G.add(p)
        pv, pf = G.mesh()
        print(f"{name}: grid {G.shape} -> {len(pf)} tris")
        meshes.append(trimesh.Trimesh(pv, pf, process=False))
m = trimesh.util.concatenate(meshes)
print("bounds", m.bounds.round(3).tolist(), "volume(body)", round(meshes[0].volume, 5))
m.vertices = m.vertices[:, [0, 2, 1]] * np.array([1, 1, -1])   # Blender Z-up -> glTF Y-up (x, z, -y)
m.export(a.out)
print("wrote", a.out)
