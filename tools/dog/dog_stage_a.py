"""Dog stage A: the Rottweiler mesh (numpy only, no Blender).

  python3 tools/dog/dog_stage_a.py [--out build/dog/stage_a.npz] [--h 0.002] [--lod0 42000] [--lod1 11000]
          [--lod2 3000] [--preview <scratch>/a.glb]

1. Body: the SDF of tools/dog/anatomy.py sampled on an --h grid, marching cubes, internal bubbles dropped (largest
   component kept), quadric decimation (pymeshlab) to the LOD0 budget with a quality threshold (no slivers), a few
   Taubin smoothing passes.
2. Parts: ears (explicit draped sheets), eyeballs (UV spheres, own material), claws, teeth, tongue (fine SDF grids,
   decimated). Each part is a separate shell overlapping the body, as usual for game assets.
3. UVs: one xatlas atlas for body + ears + claws + teeth + tongue (material M_Dog_Body); the eyes keep their planar
   iris mapping (material M_Dog_Eye).
4. LOD1/LOD2: quadric decimation WITH texture coordinates of the UV'd LOD0 (the atlas stays valid, one texture set).
5. Skin weights: from the primitives each vertex belongs to (soft-min of the primitive distances, chains split by the
   distance to their bone segments), the lip line split hard between Head and Jaw, a few Laplacian smoothing passes,
   at most 4 influences. LOD1/2 copy the weights of the nearest LOD0 vertex of the same part.
6. Per-face part id (`part`): 0 coat, 1 mouth interior / eye socket (the cut surfaces), 2 claw, 3 nose leather,
   4 eyeball, 5 paw pad, 6 tooth, 7 tongue, 8 ear.

Output: one .npz with, per LOD n: v<n> (V,3) f<n> (F,3) uv<n> (F,3,2) part<n> (F,) wi<n> (V,4) ww<n> (V,4); plus
bones (names) and the bone table (heads, tails, parents).
"""
import argparse, os, sys, time
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import anatomy as A
from sdf import Field, eval_prims

PART = dict(coat=0, cut=1, claw=2, nose=3, eye=4, pad=5, tooth=6, tongue=7, ear=8)


def log(*a):
    print("[stage_a]", *a, flush=True)


# ---------------------------------------------------------------------------------------------------------------------
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


def sdf_part(prims, h, target, pad=0.004):
    lo = np.min([p.aabb()[0] for p in prims], axis=0) - pad
    hi = np.max([p.aabb()[1] for p in prims], axis=0) + pad
    F = Field(lo, hi, h)
    for p in prims:
        F.add(p)
    v, f = F.mesh()
    return decimate(v, f.astype(np.int64), target, quality=0.4)


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


def quads_to_tris(faces):
    out = []
    for q in faces:
        if len(q) == 3:
            out.append(q)
        else:
            out += [(q[0], q[1], q[2]), (q[0], q[2], q[3])]
    return np.array(out, dtype=np.int64)


# ---------------------------------------------------------------------------------------------------------------------
# skin weights
def seg_dist(P, a, b):
    ab = b - a
    t = np.clip(((P - a) @ ab) / (ab @ ab), 0, 1)
    return np.linalg.norm(P - (a + t[:, None] * ab), axis=1)


def membership_weights(P, prims, bones, sigma=0.010, sigma_chain=0.030):
    """(N, B) weights from the primitives' distances (soft-min) and bone chains."""
    table = A.bone_table()
    bi = {b: i for i, b in enumerate(bones)}
    add = [p for p in prims if p.op == "add" and p.bones]
    D = np.stack([p.dist(P) for p in add], axis=1)                       # (N, K)
    dmin = D.min(axis=1, keepdims=True)
    S = np.exp(-(D - dmin) / sigma)
    S[D - dmin > 6 * sigma] = 0
    W = np.zeros((len(P), len(bones)))
    for k, p in enumerate(add):
        sel = S[:, k] > 1e-4
        if not np.any(sel):
            continue
        chain = p.bones if isinstance(p.bones, (list, tuple)) else [p.bones]
        if len(chain) == 1:
            W[sel, bi[chain[0]]] += S[sel, k]
            continue
        Q = P[sel]
        dd = np.stack([seg_dist(Q, table[b][0], table[b][1]) for b in chain], axis=1)
        cw = np.exp(-(dd - dd.min(axis=1, keepdims=True)) / sigma_chain)
        cw /= cw.sum(axis=1, keepdims=True)
        for j, b in enumerate(chain):
            W[sel, bi[b]] += S[sel, k] * cw[:, j]
    return W / np.maximum(W.sum(axis=1, keepdims=True), 1e-12)


LIP_Z = 0.707          # the lip slit plane (anatomy.mouth_cut_prims)


def mouth_split(P, W, bones):
    """Hard upper/lower split along the lip line: above the slit -> Head/Nose, below -> Jaw (+tongue region)."""
    bi = {b: i for i, b in enumerate(bones)}
    x, y, z = P[:, 0], P[:, 1], P[:, 2]
    region = (np.abs(x) < 0.085) & (y < -0.455) & (z > 0.64) & (z < 0.78)
    fade = np.clip((-0.475 - y) / 0.04, 0, 1) * region            # 0 behind the jaw hinge, 1 at the commissure
    below = np.clip((LIP_Z - z) / 0.003 * 0.5 + 0.5, 0, 1)         # 1 under the slit, 0 above (3 mm ramp)
    tgt = np.zeros_like(W)
    tgt[:, bi["Jaw"]] = below
    up = 1 - below
    head_share = W[:, bi["Head"]] + W[:, bi["Nose"]] + 1e-9
    tgt[:, bi["Head"]] = up * W[:, bi["Head"]] / head_share
    tgt[:, bi["Nose"]] = up * W[:, bi["Nose"]] / head_share
    # vertices with no Head/Nose share above the line (e.g. cheek owned by Jaw): give them to Head
    none = (W[:, bi["Head"]] + W[:, bi["Nose"]]) < 1e-6
    tgt[none, bi["Head"]] = up[none]
    return W * (1 - fade[:, None]) + tgt * fade[:, None]


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
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.dirname(HERE)), "build", "dog", "stage_a.npz"))
    ap.add_argument("--h", type=float, default=0.002)
    ap.add_argument("--lod0", type=int, default=38000, help="body triangles of LOD0 (parts come on top)")
    ap.add_argument("--lod1", type=int, default=11000)
    ap.add_argument("--lod2", type=int, default=3000)
    ap.add_argument("--preview", help="also write LOD0 as a GLB (no rig) for dog_views.py")
    a = ap.parse_args()
    t0 = time.time()
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)

    table = A.bone_table()
    bones = list(table.keys())
    bi = {b: i for i, b in enumerate(bones)}

    # ---- 1. body
    prims = A.body_prims()
    F = Field((-0.20, -0.72, -0.004), (0.20, 0.54, 0.93), a.h)
    for p in prims:
        F.add(p)
    v, f = F.mesh()
    f = f.astype(np.int64)
    log(f"body grid {F.shape}: marching cubes {len(f)} tris ({time.time() - t0:.0f} s)")
    v, f, ncomp = largest_component(v, f)
    log(f"components {ncomp} -> kept the largest: {len(f)} tris")
    v, f = decimate(v, f, a.lod0, quality=0.6, smooth=3)
    log(f"body LOD0 {len(f)} tris, {len(v)} verts ({time.time() - t0:.0f} s)")
    skin = A.skin_prims()
    d_skin = eval_prims(skin, v)
    fc = v[f].mean(axis=1)
    d_face = eval_prims(skin, fc)
    body_part = np.zeros(len(f), np.int32)
    # inside the uncut skin = mouth cavity / socket walls (only there: decimation also pulls convex areas inward)
    mouth_box = (np.abs(fc[:, 0]) < 0.07) & (fc[:, 1] < -0.46) & (fc[:, 2] > 0.66) & (fc[:, 2] < 0.76)
    eyes = np.min([np.linalg.norm(fc - A.eye_frame(s)[0], axis=1) for s in "LR"], axis=0) < 0.02
    body_part[(d_face < -0.0012) & (mouth_box | eyes)] = PART["cut"]
    # nose leather and paw pads by their primitives
    nose = [p for p in prims if p.tag == "nose"][0]
    body_part[(nose.dist(fc) < 0.0015) & (body_part == 0)] = PART["nose"]
    pads = [p for p in prims if p.tag in ("pad", "toe", "carpalpad")]
    nrm = np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]])
    nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-12)
    dpad = np.min([p.dist(fc) for p in pads], axis=0)
    body_part[(dpad < 0.002) & (nrm[:, 2] < -0.35) & (fc[:, 2] < 0.03)] = PART["pad"]
    carpal = [p for p in prims if p.tag == "carpalpad"]
    body_part[(np.min([p.dist(fc) for p in carpal], axis=0) < 0.002) & (nrm[:, 1] > 0.3)] = PART["pad"]

    Wb = membership_weights(v, prims, bones)
    Wb = mouth_split(v, Wb, bones)
    Wb = smooth_weights(Wb, f, iters=4, lam=0.5)
    Wb = mouth_split(v, Wb, bones)                       # keep the lip line crisp after smoothing
    parts_v, parts_f, parts_W, parts_pid, parts_uv = [v], [f], [Wb], [body_part], [None]

    # ---- 2. parts
    def rigid(n, bone):
        W = np.zeros((n, len(bones))); W[:, bi[bone]] = 1; return W

    for s in "LR":
        ev, ef, ew, euv, inner = A.ear_mesh(s)
        ef3 = quads_to_tris(ef)
        W = np.zeros((len(ev), len(bones))); W[:, bi[f"Ear1.{s}"]] = ew[:, 0]; W[:, bi[f"Ear2.{s}"]] = ew[:, 1]
        parts_v.append(ev); parts_f.append(ef3); parts_W.append(W)
        parts_pid.append(np.full(len(ef3), PART["ear"], np.int32)); parts_uv.append(None)
    for name, plist, h, tgt, pid in (("claws", A.claw_prims(), 0.0007, 2400, PART["claw"]),
                                     ("teeth", A.teeth_prims(), 0.0006, 1600, PART["tooth"]),
                                     ("tongue", A.tongue_prims(), 0.0012, 900, PART["tongue"])):
        pv, pf = sdf_part(plist, h, tgt)
        W = membership_weights(pv, plist, bones, sigma=0.004, sigma_chain=0.012)
        parts_v.append(pv); parts_f.append(pf); parts_W.append(W)
        parts_pid.append(np.full(len(pf), pid, np.int32)); parts_uv.append(None)
        log(f"{name}: {len(pf)} tris")

    # ---- merge everything that shares the body material; eyes separately
    offs = np.cumsum([0] + [len(x) for x in parts_v])
    V0 = np.concatenate(parts_v)
    F0 = np.concatenate([pf + offs[i] for i, pf in enumerate(parts_f)])
    W0 = np.concatenate(parts_W)
    P0 = np.concatenate(parts_pid)
    shell = np.concatenate([np.full(len(pf), i, np.int32) for i, pf in enumerate(parts_f)])

    # ---- 3. UV atlas (xatlas) for the body material
    import xatlas
    atlas = xatlas.Atlas()
    atlas.add_mesh(V0.astype(np.float32), F0.astype(np.uint32))
    co = xatlas.ChartOptions(); co.max_iterations = 2; co.normal_deviation_weight = 2.0; co.max_cost = 2.5
    po = xatlas.PackOptions(); po.resolution = 4096; po.padding = 12; po.bilinear = True; po.blockAlign = True
    atlas.generate(co, po)
    vmap, fx, uvx = atlas[0]
    UV0 = uvx[fx]                                        # (F, 3, 2) wedge UVs; faces keep their order
    assert np.all(vmap[fx] == F0), "xatlas reordered faces"
    log(f"xatlas: {atlas.chart_count} charts, utilization {float(np.ravel(atlas.utilization)[0]):.2f} ({time.time() - t0:.0f} s)")

    # eyes (own material, appended after the atlas so they keep their iris UVs)
    eye_v, eye_f, eye_uv, eye_W = [], [], [], []
    base = len(V0)
    for s in "LR":
        ev, ef, euv = A.eye_mesh(s)
        ef3 = quads_to_tris(ef)
        eye_v.append(ev); eye_f.append(ef3 + base); eye_uv.append(euv[ef3]); eye_W.append(rigid(len(ev), f"Eye.{s}"))
        base += len(ev)
    V0 = np.concatenate([V0] + eye_v)
    F0 = np.concatenate([F0] + eye_f)
    UV0 = np.concatenate([UV0] + eye_uv)
    W0 = np.concatenate([W0] + eye_W)
    P0 = np.concatenate([P0] + [np.full(len(x), PART["eye"], np.int32) for x in eye_f])
    shell = np.concatenate([shell] + [np.full(len(x), 100 + i, np.int32) for i, x in enumerate(eye_f)])
    F0, (UV0, P0, shell) = drop_degenerate(V0, F0, [UV0, P0, shell])
    W0 = smooth_weights(W0, F0, iters=0)
    wi0, ww0 = limit4(W0)
    out = dict(bones=np.array(bones), heads=np.array([table[b][0] for b in bones]),
               tails=np.array([table[b][1] for b in bones]),
               parents=np.array([table[b][2] or "" for b in bones]),
               v0=V0, f0=F0, uv0=UV0, part0=P0, shell0=shell, wi0=wi0, ww0=ww0)
    log(f"LOD0 total {len(F0)} tris, {len(V0)} verts")

    # ---- 4. LOD1/LOD2: per shell (eyes: kept whole on LOD1, coarser sphere on LOD2 via decimation)
    from scipy.spatial import cKDTree
    prev_shell = {}          # LOD n decimates LOD n-1 (per shell): gentler steps leave no UV fold-overs
    for lod, target in ((1, a.lod1), (2, a.lod2)):
        Vl, Fl, UVl, Pl, Sl, srcidx = [], [], [], [], [], []
        base = 0
        total0 = len(F0)
        new_shell = {}
        for sid in np.unique(shell):
            fm = shell == sid
            fs = F0[fm]
            used = np.unique(fs)
            share = target * len(fs) / total0
            if sid in prev_shell:
                vs, fs2, uvs = prev_shell[sid]
            else:
                remap = -np.ones(len(V0), int); remap[used] = np.arange(len(used))
                vs, fs2, uvs = V0[used], remap[fs], UV0[fm]
            tgt = max(int(share), 24)
            if tgt < len(fs2):
                vs, fs2, uvs = decimate_uv_nofold(vs, fs2, uvs, tgt)
            new_shell[sid] = (vs, fs2, uvs)
            Vl.append(vs); Fl.append(fs2 + base); UVl.append(uvs)
            Pl.append(np.full(len(fs2), np.bincount(P0[fm]).argmax(), np.int32) if sid != 0 else None)
            if sid == 0:     # body: re-derive the part id per face from LOD0 (nearest face centre)
                tree = cKDTree(V0[F0[fm]].mean(axis=1))
                _, j = tree.query(vs[fs2].mean(axis=1))
                Pl[-1] = P0[fm][j]
            Sl.append(np.full(len(fs2), sid, np.int32))
            # weights: nearest LOD0 vertex of the same shell
            tree = cKDTree(V0[used])
            _, j = tree.query(vs)
            srcidx.append(used[j])
            base += len(vs)
        Vl = np.concatenate(Vl); Fl = np.concatenate(Fl); UVl = np.concatenate(UVl)
        Pl = np.concatenate(Pl); Sl = np.concatenate(Sl); src = np.concatenate(srcidx)
        Fl, (UVl, Pl, Sl) = drop_degenerate(Vl, Fl, [UVl, Pl, Sl])
        prev_shell = new_shell
        out.update({f"v{lod}": Vl, f"f{lod}": Fl, f"uv{lod}": UVl, f"part{lod}": Pl, f"shell{lod}": Sl,
                    f"wi{lod}": wi0[src], f"ww{lod}": ww0[src]})
        log(f"LOD{lod}: {len(Fl)} tris, {len(Vl)} verts, UV folds {uv_folds(Fl, UVl)} ({time.time() - t0:.0f} s)")

    np.savez_compressed(a.out, **out)
    log(f"wrote {a.out} ({time.time() - t0:.0f} s)")

    if a.preview:
        import trimesh
        m = trimesh.Trimesh(V0[:, [0, 2, 1]] * np.array([1, 1, -1]), F0, process=False)
        m.export(a.preview)
        log("preview", a.preview)


if __name__ == "__main__":
    main()
