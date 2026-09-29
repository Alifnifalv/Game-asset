"""Raven stage A: the mesh (numpy + pymeshlab + xatlas, no Blender).

  python3 tools/raven/raven_stage_a.py [--out build/raven/stage_a.npz] [--h 0.0015] [--lod0 16000] [--lod1 4500]
          [--lod2 1300] [--preview <scratch>/a.glb]

1. Body (material M_Raven_Body): the SDF of raven_anatomy (body, bill with the gape cut, legs, the spread wing arms,
   eye sockets) on an --h grid, marching cubes, the largest component, quadric decimation to --lod0, Taubin smoothing.
   Claws: fine SDF grids, decimated. One xatlas atlas for body + claws.
2. Eyes (M_Raven_Eye): UV spheres with a planar iris mapping, rigid on Eye.X.
3. Feathers (M_Raven_Feather): every Feather of plumage.plumage() as a closed strip (feathers.strip), its UVs in the
   feather atlas slot (plumage.SLOTS), rigid on its bone. LOD1/LOD2 REGENERATE the strips at a lower resolution and
   drop the groups whose Feather.lod is below the LOD.
4. Body LOD1/LOD2: decimation with texture coordinates (LOD2 from LOD1, fold-free), as the dog.
5. Skin weights (body): soft-min of the primitive distances, chains split along their bones; the gape line split hard
   between Head (upper mandible) and Jaw (lower); Laplacian smoothing; at most 4 influences.
6. Per-face `part`: 0 plumage (feathered skin), 1 mouth interior (the gape cut walls), 2 bill, 3 bare leg / toe skin,
   4 claw, 5 eyeball, 6 feather (top), 7 feather (underside); per-face `mat`: 0 body, 1 feather, 2 eye.

Output .npz, per LOD n: v<n> f<n> uv<n> (F,3,2) part<n> mat<n> shell<n> wi<n> ww<n>; plus the bone table
(bones, heads, tails, parents, ups).
"""
import argparse, os, sys, time
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import raven_anatomy as A                                  # noqa: E402 (adds tools/dog for sdf)
from sdf import Field, eval_prims                          # noqa: E402
import plumage, feathers                                   # noqa: E402
from meshops import (largest_component, decimate, decimate_uv_nofold, uv_folds, repair_folds, drop_degenerate, seg_dist,
                     smooth_weights, limit4)               # noqa: E402

PART = dict(plumage=0, mouth=1, bill=2, leg=3, claw=4, eye=5, feather=6, feather_under=7)
MAT = dict(body=0, feather=1, eye=2)
# strip resolution (nt along, ns per half vane) per LOD, for long and short feathers
RES = {0: ((12, 2), (6, 1)), 1: ((6, 1), (3, 1)), 2: ((4, 1), (2, 1))}
SHORT = ("hackle", "bristle", "alula", "mcov", "ucov", "gcov", "pcov", "scap", "utc")


def log(*a):
    print("[stage_a]", *a, flush=True)


def membership_weights(P, prims, bones, table, sigma=0.006, sigma_chain=0.020):
    bi = {b: i for i, b in enumerate(bones)}
    add = [p for p in prims if p.op == "add" and p.bones]
    D = np.stack([p.dist(P) for p in add], axis=1)
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


def gape_split(P, W, bones):
    """hard split along the gape line in front of the rictus: above -> Head, below -> Jaw"""
    bi = {b: i for i, b in enumerate(bones)}
    x, y, z = P[:, 0], P[:, 1], P[:, 2]
    region = (np.abs(x) < 0.022) & (y < -0.232) & (z > 0.312) & (z < 0.352)
    fade = np.clip((-0.234 - y) / 0.010, 0, 1) * region             # 0 behind the rictus, 1 in front of it
    below = np.clip((A.gape_z(y) - z) / 0.0015 * 0.5 + 0.5, 0, 1)
    tgt = np.zeros_like(W)
    tgt[:, bi["Jaw"]] = below
    tgt[:, bi["Head"]] = 1 - below
    return W * (1 - fade[:, None]) + tgt * fade[:, None]


def eye_mesh(s, seg=24, rings=14):
    """UV sphere around the eye axis; UV = azimuthal equidistant about the front pole (texture radius r = 0.5 * angle /
    pi from the centre: the 10 mm iris spans r < 0.12, the back of the ball maps to the rim)"""
    c, n = A.eye_frame(s)
    up = np.array([0, 0, 1.0]); x = np.cross(up, n); x /= np.linalg.norm(x); y = np.cross(n, x)
    V, UV = [], []
    for i in range(rings + 1):
        th = np.pi * i / rings
        for j in range(seg):
            ph = 2 * np.pi * j / seg
            d = n * np.cos(th) + (x * np.cos(ph) + y * np.sin(ph)) * np.sin(th)
            V.append(c + d * A.EYE_R)
            r = 0.5 * th / np.pi                       # azimuthal equidistant: front pole = centre, no overlap
            UV.append((0.5 + r * np.cos(ph), 0.5 + r * np.sin(ph)))
    V, UV = np.array(V), np.array(UV)
    F = []
    for i in range(rings):
        for j in range(seg):
            a, b = i * seg + j, i * seg + (j + 1) % seg
            c_, d = a + seg, b + seg
            F += [(a, c_, d), (a, d, b)]
    F = np.array(F, np.int64)
    # the poles collapse: drop degenerate triangles later (drop_degenerate)
    return V, F, UV


def feather_meshes(Fs, lod, bones):
    """all strips of the plumage for one LOD: V, F, UV (F,3,2), part, bone index per vertex"""
    bi = {b: i for i, b in enumerate(bones)}
    Vs, Fs_, UVs, Ps, Bs, Ss = [], [], [], [], [], []
    base = 0
    for k, fe in enumerate(Fs):
        if fe.lod < lod:
            continue
        long_, short = RES[lod]
        nt, ns = short if fe.group in SHORT else long_
        V, F, UV, under = feathers.strip(fe, nt, ns)
        Vs.append(V); Fs_.append(F + base); UVs.append(UV[F])
        Ps.append(np.where(under > 0, PART["feather_under"], PART["feather"]).astype(np.int32))
        Bs.append(np.full(len(V), bi[fe.bone], np.int32)); Ss.append(np.full(len(F), 1000 + k, np.int32))
        base += len(V)
    return (np.concatenate(Vs), np.concatenate(Fs_), np.concatenate(UVs), np.concatenate(Ps), np.concatenate(Bs),
            np.concatenate(Ss))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.dirname(HERE)), "build", "raven",
                                                  "stage_a.npz"))
    ap.add_argument("--h", type=float, default=0.0015)
    ap.add_argument("--lod0", type=int, default=16000, help="body triangles of LOD0 (claws, eyes, feathers on top)")
    ap.add_argument("--lod1", type=int, default=4500)
    ap.add_argument("--lod2", type=int, default=1300)
    ap.add_argument("--preview", help="also write LOD0 as a GLB (no rig)")
    a = ap.parse_args()
    t0 = time.time()
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    table = A.bone_table()
    bones = list(table.keys())
    bi = {b: i for i, b in enumerate(bones)}

    # ---- 1. body
    prims = A.body_prims() + A.eye_socket_prims()
    lo = np.min([p.aabb()[0] for p in prims if p.op == "add"], axis=0) - 0.006
    hi = np.max([p.aabb()[1] for p in prims if p.op == "add"], axis=0) + 0.006
    G = Field(lo, hi, a.h)
    for p in prims:
        G.add(p)
    v, f = G.mesh()
    f = f.astype(np.int64)
    log(f"body grid {G.shape}: marching cubes {len(f)} tris ({time.time() - t0:.0f} s)")
    v, f, ncomp = largest_component(v, f)
    log(f"components {ncomp} -> kept the largest: {len(f)} tris")
    v, f = decimate(v, f, a.lod0, quality=0.6, smooth=2)
    log(f"body LOD0 {len(f)} tris, {len(v)} verts ({time.time() - t0:.0f} s)")
    fc = v[f].mean(axis=1)
    uncut = [p for p in prims if p.op == "add"]
    d_uncut = eval_prims(uncut, fc)
    part = np.zeros(len(f), np.int32)
    gape = A.GapeCut()
    part[(d_uncut < -0.0004) & (gape.dist(fc) < 0.0018)] = PART["mouth"]
    feathered = [p for p in prims if p.op == "add" and p.tag not in ("bill", "bill_low", "tarsus", "toe", "claw")]
    d_feath = eval_prims(feathered, fc)
    billp = [p for p in prims if p.tag in ("bill", "bill_low")]
    d_bill = np.min([p.dist(fc) for p in billp], axis=0)
    part[(part == 0) & (d_bill < 0.0012) & (d_feath > 0.0006)] = PART["bill"]
    legp = [p for p in prims if p.tag in ("tarsus", "toe")]
    d_leg = np.min([p.dist(fc) for p in legp], axis=0)
    part[(part == 0) & (d_leg < 0.0012) & (d_feath > 0.0008) & (fc[:, 2] < 0.075)] = PART["leg"]
    Wb = membership_weights(v, prims, bones, table)
    Wb = gape_split(v, Wb, bones)
    Wb = smooth_weights(Wb, f, iters=3, lam=0.5)
    Wb = gape_split(v, Wb, bones)
    log(f"parts: mouth {np.sum(part == 1)}, bill {np.sum(part == 2)}, leg {np.sum(part == 3)}")
    shells_v, shells_f, shells_W, shells_p = [v], [f], [Wb], [part]

    # claws
    for s in "LR":
        cp = A.claw_prims(s)
        clo = np.min([p.aabb()[0] for p in cp], axis=0) - 0.003
        chi = np.max([p.aabb()[1] for p in cp], axis=0) + 0.003
        Gc = Field(clo, chi, 0.0005)
        for p in cp:
            Gc.add(p)
        cv, cf = Gc.mesh()
        cv, cf = decimate(cv, cf.astype(np.int64), 700, quality=0.4)
        W = membership_weights(cv, cp, bones, table, sigma=0.002, sigma_chain=0.006)
        shells_v.append(cv); shells_f.append(cf); shells_W.append(W)
        shells_p.append(np.full(len(cf), PART["claw"], np.int32))
        log(f"claws {s}: {len(cf)} tris")

    offs = np.cumsum([0] + [len(x) for x in shells_v])
    V0 = np.concatenate(shells_v)
    F0 = np.concatenate([sf + offs[i] for i, sf in enumerate(shells_f)])
    W0 = np.concatenate(shells_W)
    P0 = np.concatenate(shells_p)
    S0 = np.concatenate([np.full(len(sf), i, np.int32) for i, sf in enumerate(shells_f)])

    # ---- UV atlas of the body material
    import xatlas
    atlas = xatlas.Atlas()
    atlas.add_mesh(V0.astype(np.float32), F0.astype(np.uint32))
    co = xatlas.ChartOptions(); co.max_iterations = 4; co.normal_deviation_weight = 2.0; co.max_cost = 4.0
    po = xatlas.PackOptions(); po.resolution = 4096; po.padding = 12; po.bilinear = True; po.blockAlign = True
    atlas.generate(co, po)
    vmap, fx, uvx = atlas[0]
    UV0 = uvx[fx]
    assert np.all(vmap[fx] == F0), "xatlas reordered faces"
    log(f"xatlas: {atlas.chart_count} charts, utilization {float(np.ravel(atlas.utilization)[0]):.2f} "
        f"({time.time() - t0:.0f} s)")
    M0 = np.full(len(F0), MAT["body"], np.int32)

    # ---- eyes
    ev_, ef_, euv_, eW_ = [], [], [], []
    base = len(V0)
    for s in "LR":
        ev, ef, euv = eye_mesh(s)
        W = np.zeros((len(ev), len(bones))); W[:, bi[f"Eye.{s}"]] = 1
        ev_.append(ev); ef_.append(ef + base); euv_.append(euv[ef]); eW_.append(W); base += len(ev)
    nE = sum(len(x) for x in ef_)
    V0 = np.concatenate([V0] + ev_); F0 = np.concatenate([F0] + ef_); UV0 = np.concatenate([UV0] + euv_)
    W0 = np.concatenate([W0] + eW_)
    P0 = np.concatenate([P0, np.full(nE, PART["eye"], np.int32)])
    S0 = np.concatenate([S0] + [np.full(len(x), 100 + i, np.int32) for i, x in enumerate(ef_)])
    M0 = np.concatenate([M0, np.full(nE, MAT["eye"], np.int32)])
    F0, (UV0, P0, S0, M0) = drop_degenerate(V0, F0, [UV0, P0, S0, M0])

    # ---- feathers (LOD0)
    skin = lambda Q: eval_prims(A.body_prims(), Q)
    FE = plumage.plumage(skin)
    log(f"plumage: {len(FE)} feathers")

    def with_feathers(Vb, Fb, UVb, Pb, Sb, Mb, Wb_idx, Wb_w, lod):
        fv, ff, fuv, fp, fbone, fs = feather_meshes(FE, lod, bones)
        wi = np.zeros((len(fv), 4), np.int32); wi[:, 0] = fbone
        ww = np.zeros((len(fv), 4), np.float32); ww[:, 0] = 1.0
        n = len(Vb)
        return (np.concatenate([Vb, fv]), np.concatenate([Fb, ff + n]), np.concatenate([UVb, fuv]),
                np.concatenate([Pb, fp]), np.concatenate([Sb, fs]),
                np.concatenate([Mb, np.full(len(ff), MAT["feather"], np.int32)]),
                np.concatenate([Wb_idx, wi]), np.concatenate([Wb_w, ww]), len(ff))

    wi0, ww0 = limit4(W0)
    out = dict(bones=np.array(bones), heads=np.array([table[b][0] for b in bones]),
               tails=np.array([table[b][1] for b in bones]),
               parents=np.array([table[b][2] or "" for b in bones]),
               ups=np.array([table[b][3] if table[b][3] is not None else (np.nan, np.nan, np.nan) for b in bones]))
    Vx, Fx, UVx, Px, Sx, Mx, WIx, WWx, nfe = with_feathers(V0, F0, UV0, P0, S0, M0, wi0, ww0, 0)
    out.update(v0=Vx, f0=Fx, uv0=UVx, part0=Px, shell0=Sx, mat0=Mx, wi0=WIx, ww0=WWx)
    log(f"LOD0: body+claws+eyes {len(F0)} tris, feathers {nfe} tris, total {len(Fx)}")

    # ---- LOD1 / LOD2 (body shells decimated; feathers regenerated)
    from scipy.spatial import cKDTree
    prev = {}
    for lod, target in ((1, a.lod1), (2, a.lod2)):
        Vl, Fl, UVl, Pl, Sl, Ml, src = [], [], [], [], [], [], []
        base = 0
        tot = int(np.sum(S0 < 100))
        new = {}
        for sid in np.unique(S0):
            fm = S0 == sid
            fs = F0[fm]
            used = np.unique(fs)
            if sid in prev:
                vs, fs2, uvs = prev[sid]
            else:
                remap = -np.ones(len(V0), int); remap[used] = np.arange(len(used))
                vs, fs2, uvs = V0[used], remap[fs], UV0[fm]
            if sid < 100:
                tgt = max(int(target * len(fs) / tot), 60)
            else:                                            # eyes
                tgt = {1: 200, 2: 80}[lod]
            if tgt < len(fs2):
                src_ = (vs, fs2, uvs)
                for bump in range(10):                   # retry until the cleaned shell has no UV fold
                    vs, fs2, uvs = decimate_uv_nofold(*src_, int(tgt * (1 + 0.02 * bump)))
                    fs2, (uvs,) = drop_degenerate(vs, fs2, [uvs])
                    if uv_folds(fs2, uvs) == 0:
                        break
            new[sid] = (vs, fs2, uvs)
            Vl.append(vs); Fl.append(fs2 + base); UVl.append(uvs)
            if sid == 0:
                tree = cKDTree(V0[F0[fm]].mean(axis=1)); _, j = tree.query(vs[fs2].mean(axis=1))
                Pl.append(P0[fm][j])
            else:
                Pl.append(np.full(len(fs2), np.bincount(P0[fm]).argmax(), np.int32))
            Ml.append(np.full(len(fs2), np.bincount(M0[fm]).argmax(), np.int32))
            Sl.append(np.full(len(fs2), sid, np.int32))
            tree = cKDTree(V0[used]); _, j = tree.query(vs); src.append(used[j])
            base += len(vs)
        prev = new
        Vl = np.concatenate(Vl); Fl = np.concatenate(Fl); UVl = np.concatenate(UVl)
        Pl = np.concatenate(Pl); Sl = np.concatenate(Sl); Ml = np.concatenate(Ml); src = np.concatenate(src)
        Fl, (UVl, Pl, Sl, Ml) = drop_degenerate(Vl, Fl, [UVl, Pl, Sl, Ml])
        folds = uv_folds(Fl, UVl)
        if folds:                                  # a fold between shells' decimation steps: repair in place
            UVl, folds = repair_folds(Fl, UVl)
        Vx, Fx, UVx, Px, Sx, Mx, WIx, WWx, nfe = with_feathers(Vl, Fl, UVl, Pl, Sl, Ml, wi0[src], ww0[src], lod)
        out.update({f"v{lod}": Vx, f"f{lod}": Fx, f"uv{lod}": UVx, f"part{lod}": Px, f"shell{lod}": Sx,
                    f"mat{lod}": Mx, f"wi{lod}": WIx, f"ww{lod}": WWx})
        log(f"LOD{lod}: body {len(Fl)} tris (UV folds {folds}), feathers {nfe}, total {len(Fx)} "
            f"({time.time() - t0:.0f} s)")

    np.savez_compressed(a.out, **out)
    log(f"wrote {a.out} ({time.time() - t0:.0f} s)")
    if a.preview:
        import trimesh
        m = trimesh.Trimesh(out["v0"][:, [0, 2, 1]] * np.array([1, 1, -1]), out["f0"], process=False)
        m.export(a.preview)
        log("preview", a.preview)


if __name__ == "__main__":
    main()
