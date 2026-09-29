"""Generic mesh helpers for the raven pipeline (copied from tools/dog/dog_stage_a.py so the two pipelines can change
independently): pymeshlab decimation (with and without wedge UVs, fold-free), UV fold repair, component filtering,
degenerate-triangle removal, weight smoothing and the 4-influence limit.
"""
import os
import numpy as np


def pml():
    import io, contextlib
    with contextlib.redirect_stderr(io.StringIO()):
        import pymeshlab
    return pymeshlab


def largest_component(v, f):
    import scipy.sparse as sp
    from scipy.sparse.csgraph import connected_components
    n = len(v)
    e = np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]])
    g = sp.coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(n, n))
    nc, lab = connected_components(g, directed=False)
    flab = lab[f[:, 0]]
    big = np.bincount(flab).argmax()
    keep = flab == big
    f = f[keep]
    used = np.unique(f)
    remap = -np.ones(n, int); remap[used] = np.arange(len(used))
    return v[used], remap[f], nc


def decimate(v, f, target, quality=0.5, smooth=0):
    pm = pml()
    ms = pm.MeshSet()
    ms.add_mesh(pm.Mesh(v, f.astype(np.int32)))
    ms.meshing_decimation_quadric_edge_collapse(targetfacenum=int(target), qualitythr=quality, preservenormal=True,
                                                planarquadric=True, optimalplacement=True, preservetopology=True)
    if smooth:
        ms.apply_coord_taubin_smoothing(stepsmoothnum=smooth)
    m = ms.current_mesh()
    return m.vertex_matrix().copy(), m.face_matrix().astype(np.int64).copy()


def decimate_uv(v, f, uvw, target):
    """Quadric decimation preserving the wedge UVs. Returns v, f, uvw (F,3,2).
    MeshLab's texture-aware collapse needs a texture index on every wedge, which pymeshlab.Mesh() cannot set, so the
    mesh goes through an OBJ with a material and a (dummy) texture."""
    import tempfile
    from PIL import Image
    pm = pml()
    d = tempfile.mkdtemp()
    Image.new("RGB", (4, 4)).save(os.path.join(d, "t.png"))
    with open(os.path.join(d, "m.mtl"), "w") as fh:
        fh.write("newmtl M\nmap_Kd t.png\n")
    uv = uvw.reshape(-1, 2)
    with open(os.path.join(d, "m.obj"), "w") as fh:
        fh.write("mtllib m.mtl\n")
        fh.write("".join(f"v {x:.7f} {y:.7f} {z:.7f}\n" for x, y, z in v))
        fh.write("".join(f"vt {x:.7f} {y:.7f}\n" for x, y in uv))
        fh.write("usemtl M\n")
        fh.write("".join(f"f {a + 1}/{3 * i + 1} {b + 1}/{3 * i + 2} {c + 1}/{3 * i + 3}\n"
                         for i, (a, b, c) in enumerate(f)))
    ms = pm.MeshSet()
    ms.load_new_mesh(os.path.join(d, "m.obj"))
    ms.meshing_decimation_quadric_edge_collapse_with_texture(targetfacenum=int(target), qualitythr=0.5,
                                                             extratcoordw=1.0, preserveboundary=True,
                                                             boundaryweight=2.0, optimalplacement=True,
                                                             preservenormal=True, planarquadric=True)
    m = ms.current_mesh()
    return (m.vertex_matrix().copy(), m.face_matrix().astype(np.int64).copy(),
            m.wedge_tex_coord_matrix().reshape(-1, 3, 2).copy())


def uv_folds(f, uvw):
    """number of UV fold-overs: two triangles that share an edge (same vertices, same UVs on it) but lie on the same
    side of it in UV space (a flipped triangle inside a chart: its MikkTSpace tangents cancel at the shared corners)"""
    sgn = np.sign(np.cross(uvw[:, 1] - uvw[:, 0], uvw[:, 2] - uvw[:, 0]))
    edges = {}
    for t in range(len(f)):
        for k in range(3):
            a, b = f[t, k], f[t, (k + 1) % 3]
            ua, ub = tuple(np.round(uvw[t, k], 6)), tuple(np.round(uvw[t, (k + 1) % 3], 6))
            key = (min(a, b), max(a, b), ua if a < b else ub, ub if a < b else ua)
            edges.setdefault(key, []).append((t, a < b))
    folds = 0
    for lst in edges.values():
        if len(lst) == 2:
            (t0, d0), (t1, d1) = lst
            # consistent orientation: opposite traversal directions and the same UV winding sign
            if d0 != d1 and sgn[t0] != sgn[t1]:
                folds += 1
    return folds


def fold_pairs(f, uvw):
    sgn = np.sign(np.cross(uvw[:, 1] - uvw[:, 0], uvw[:, 2] - uvw[:, 0]))
    edges = {}
    for t in range(len(f)):
        for k in range(3):
            a, b = f[t, k], f[t, (k + 1) % 3]
            ua, ub = tuple(np.round(uvw[t, k], 6)), tuple(np.round(uvw[t, (k + 1) % 3], 6))
            key = (min(a, b), max(a, b), ua if a < b else ub, ub if a < b else ua)
            edges.setdefault(key, []).append((t, a < b, k))
    out = []
    for lst in edges.values():
        if len(lst) == 2:
            (t0, d0, k0), (t1, d1, k1) = lst
            if d0 != d1 and sgn[t0] != sgn[t1]:
                out.append(((t0, (k0 + 2) % 3), (t1, (k1 + 2) % 3)))      # the corners opposite the shared edge
    return out


def repair_folds(f, uvw, iters=40):
    """move the UV of the corner opposite a folded edge (every wedge of that vertex with the same UV) to the mean of
    its chart neighbours' UVs, until no fold is left. Returns the repaired uvw and the folds left."""
    uvw = uvw.copy()
    for _ in range(iters):
        pairs = fold_pairs(f, uvw)
        if not pairs:
            return uvw, 0
        for pair in pairs:
            # the triangle with the smaller UV area is the one that crossed over
            areas = [abs(np.cross(uvw[t, 1] - uvw[t, 0], uvw[t, 2] - uvw[t, 0])) for t, _ in pair]
            t, k = pair[int(np.argmin(areas))]
            vid, uv0 = f[t, k], uvw[t, k].copy()
            wed = [(tt, kk) for tt, kk in zip(*np.nonzero(f == vid)) if np.allclose(uvw[tt, kk], uv0, atol=1e-6)]
            nb = [uvw[tt, j] for tt, kk in wed for j in range(3) if j != kk]
            new = np.mean(nb, axis=0)
            for tt, kk in wed:
                uvw[tt, kk] = new
    return uvw, len(fold_pairs(f, uvw))


def decimate_uv_nofold(v, f, uvw, target, tries=12):
    """decimate_uv, retried with a growing budget (+5 % per try) until the result has no UV fold-over"""
    best = None
    for i in range(tries):
        tgt = int(target * (1 + 0.05 * i)) + (i % 2)
        if tgt >= len(f):
            return v, f, uvw
        out = decimate_uv(v, f, uvw, tgt)
        n = uv_folds(out[1], out[2])
        if best is None or n < best[0]:
            best = (n, out)
        if n == 0:
            break
    n, (vv, ff, uu) = best
    if n:
        uu, n = repair_folds(ff, uu)
    return vv, ff, uu


def drop_degenerate(v, f, extra=None, eps=1e-11):
    """remove zero-area, repeated-index and duplicate triangles (the exporters drop or merge them, and the validator
    compares triangle counts)"""
    a = np.linalg.norm(np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]]), axis=1) * 0.5
    ok = (a > eps) & (f[:, 0] != f[:, 1]) & (f[:, 1] != f[:, 2]) & (f[:, 0] != f[:, 2])
    # duplicates (the same three vertices twice, e.g. a quad rim closing on itself): keep the first
    _, first = np.unique(np.sort(f, axis=1), axis=0, return_index=True)
    uniq = np.zeros(len(f), bool); uniq[first] = True
    ok &= uniq
    return (f[ok], [x[ok] for x in extra]) if extra is not None else f[ok]


def seg_dist(P, a, b):
    ab = b - a
    t = np.clip(((P - a) @ ab) / (ab @ ab), 0, 1)
    return np.linalg.norm(P - (a + t[:, None] * ab), axis=1)


def smooth_weights(W, f, iters=3, lam=0.5, lock=None):
    n = len(W)
    import scipy.sparse as sp
    e = np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]])
    e = np.concatenate([e, e[:, ::-1]])
    Aj = sp.coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(n, n)).tocsr()
    Aj.data[:] = 1.0
    deg = np.asarray(Aj.sum(axis=1)).ravel()
    for _ in range(iters):
        avg = (Aj @ W) / np.maximum(deg, 1)[:, None]
        Wn = W + lam * (avg - W)
        if lock is not None:
            Wn[lock] = W[lock]
        W = Wn
    return W / np.maximum(W.sum(axis=1, keepdims=True), 1e-12)


def limit4(W):
    idx = np.argsort(-W, axis=1)[:, :4]
    w = np.take_along_axis(W, idx, axis=1)
    w[w < 0.01] = 0
    w /= np.maximum(w.sum(axis=1, keepdims=True), 1e-12)
    return idx.astype(np.int32), w.astype(np.float32)


# ---------------------------------------------------------------------------------------------------------------------
