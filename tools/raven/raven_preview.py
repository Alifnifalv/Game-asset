"""Quick look at the raven in its bind pose: the SDF body (marching cubes at --h), claws, eyeballs and every feather
strip, written as one GLB (Y up) for tools/dog/dog_views.py.

  python3 tools/raven/raven_preview.py --h 0.002 --out <scratch>/raven.glb [--no-feathers] [--lod 0]
"""
import argparse, os, sys, time
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import raven_anatomy as A                     # noqa: E402  (puts tools/dog on sys.path for sdf)
from sdf import Field, eval_prims             # noqa: E402
import plumage, feathers                      # noqa: E402


def sdf_mesh(prims, h, pad=0.006):
    lo = np.min([p.aabb()[0] for p in prims if p.op == "add"], axis=0) - pad
    hi = np.max([p.aabb()[1] for p in prims if p.op == "add"], axis=0) + pad
    G = Field(lo, hi, h)
    for p in prims:
        G.add(p)
    return G.mesh()


def eye_mesh(s, seg=20, rings=12):
    import trimesh
    c, n = A.eye_frame(s)
    m = trimesh.creation.uv_sphere(radius=A.EYE_R, count=[rings, seg])
    m.vertices += c
    return m.vertices, m.faces


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--h", type=float, default=0.002)
    ap.add_argument("--out", required=True)
    ap.add_argument("--no-feathers", action="store_true")
    ap.add_argument("--lod", type=int, default=0)
    a = ap.parse_args()
    import trimesh
    t = time.time()
    prims = A.body_prims() + A.eye_socket_prims()
    v, f = sdf_mesh(prims, a.h)
    print(f"body {len(f)} tris ({time.time() - t:.1f} s)")
    meshes = [trimesh.Trimesh(v, f, process=False)]
    for s in "LR":
        cv, cf = sdf_mesh(A.claw_prims(s), 0.0006)
        meshes.append(trimesh.Trimesh(cv, cf, process=False))
        ev, ef = eye_mesh(s)
        meshes.append(trimesh.Trimesh(ev, ef, process=False))
    if not a.no_feathers:
        t = time.time()
        body = A.body_prims()
        skin = lambda P: eval_prims(body, P)
        F = plumage.plumage(skin)
        res = {0: (14, 3), 1: (8, 2), 2: (5, 1)}[a.lod]
        n_tri = 0
        for fe in F:
            if fe.lod < a.lod:
                continue
            nt, ns = res
            if fe.group in ("hackle", "bristle", "alula", "mcov", "ucov", "gcov", "pcov", "scap", "utc"):
                nt = max(3, nt // 2)
            V_, F_, UV_, _u = feathers.strip(fe, nt, ns)
            meshes.append(trimesh.Trimesh(V_, F_, process=False)); n_tri += len(F_)
        print(f"{len(F)} feathers, {n_tri} tris ({time.time() - t:.1f} s)")
    m = trimesh.util.concatenate(meshes)
    print("bounds", m.bounds.round(3).tolist(), "tris", len(m.faces))
    m.vertices = m.vertices[:, [0, 2, 1]] * np.array([1, 1, -1])      # Z-up -> glTF Y-up
    m.export(a.out)
    print("wrote", a.out)


if __name__ == "__main__":
    main()
