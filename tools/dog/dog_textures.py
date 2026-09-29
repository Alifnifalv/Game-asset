"""Dog stage C: the Rottweiler's textures and materials.

  python3 tools/dog/dog_textures.py [--mesh build/dog/stage_a.npz] [--in build/dog/stage_b.blend]
          [--out build/dog/stage_c.blend] [--tex-dir build/dog/textures] [--res 4096] [--preview <png>]
          [--textures-only]

The atlas of LOD0 (stage A) is rasterised in numpy: every texel knows its triangle, barycentric weights, rest-pose
3D position, normal, tangent frame and part id.  The coat is painted as a function of 3D position relative to the
anatomy landmarks (tools/dog/anatomy.py), so the markings follow any shape change:
  black coat with a faint blue-grey sheen; tan (mahogany) markings: a spot over each eye, cheeks, the sides of the
  muzzle and the chin (the nose bridge stays black), throat, two triangles on the forechest, the fore legs from the
  toes to half-way up the forearm (higher on the inside), the hind legs from the toes up the front of the hock and
  the inside of the thighs, under the tail.  Black lips, nose leather, claws; dark pads; pink-lavender tongue and gums.
Normal map: fur clumps (noise stretched along the hair flow: head to tail on the body, down the legs, along the
tail and ears), sampled in 3D and differentiated along each texel's tangent frame (OpenGL +Y convention), plus a
pebbled nose leather and pad texture.  AO from the anatomy SDF at the LOD0 vertices.

Writes (tex-dir): T_Rottweiler_BaseColor (sRGB), _Normal, _Roughness, _AO, _MaskMap (HDRP: R metal, G AO,
B detail mask, A smoothness), _MetallicSmoothness (URP: R metal, A smoothness) and T_RottweilerEye_BaseColor (1024).
Then opens stage B, builds the two materials with those images (same node layout as the calf) and saves stage C.
"""
import argparse, math, os, sys, time
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
os.environ.setdefault("ASSET", "dog")
import asset_profile as AP
import anatomy as A

TEX, TEX_EYE = AP.TEX, AP.TEX_EYE
PART = dict(coat=0, cut=1, claw=2, nose=3, eye=4, pad=5, tooth=6, tongue=7, ear=8)


def log(*a):
    print("[textures]", *a, flush=True)


def srgb2lin(c):
    c = np.asarray(c, dtype=np.float32) / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def lin2srgb(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)


def sstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


# ------------------------------------------------------------------------------------------------ 3D value noise
_PERM = np.random.RandomState(7).permutation(1 << 16).astype(np.int64)


def _hash(ix, iy, iz):
    h = (ix * 73856093) ^ (iy * 19349663) ^ (iz * 83492791)
    return _PERM[h & 0xFFFF].astype(np.float32) / 65535.0


def vnoise(P):
    """value noise in [0, 1] at points P (N, 3) (1 unit = 1 cell)"""
    fl = np.floor(P); f = P - fl
    i = fl.astype(np.int64)
    u = f * f * (3 - 2 * f)
    out = 0.0
    for dx in (0, 1):
        wx = u[:, 0] if dx else 1 - u[:, 0]
        for dy in (0, 1):
            wy = u[:, 1] if dy else 1 - u[:, 1]
            for dz in (0, 1):
                wz = u[:, 2] if dz else 1 - u[:, 2]
                out = out + wx * wy * wz * _hash(i[:, 0] + dx, i[:, 1] + dy, i[:, 2] + dz)
    return out


def fbm(P, octaves=4, lac=2.0, gain=0.5):
    a, s, tot = 1.0, 1.0, 0.0
    out = 0.0
    for _ in range(octaves):
        out = out + a * vnoise(P * s + 17.3 * s)
        tot += a; a *= gain; s *= lac
    return out / tot


# ------------------------------------------------------------------------------------------------ rasteriser
def rasterize(uvw, res):
    """uvw (F, 3, 2) -> tri index image (res, res) int32 (-1 empty) and barycentrics (res, res, 3) float32.
    Image row 0 = v = 1 (top), as PNGs are stored."""
    tri = -np.ones((res, res), np.int32)
    bar = np.zeros((res, res, 3), np.float32)
    px = uvw * res
    px[..., 1] = res - px[..., 1]
    for t in range(len(px)):
        a, b, c = px[t]
        x0 = int(max(math.floor(min(a[0], b[0], c[0])), 0)); x1 = int(min(math.ceil(max(a[0], b[0], c[0])), res - 1))
        y0 = int(max(math.floor(min(a[1], b[1], c[1])), 0)); y1 = int(min(math.ceil(max(a[1], b[1], c[1])), res - 1))
        if x1 < x0 or y1 < y0:
            continue
        xs = np.arange(x0, x1 + 1) + 0.5; ys = np.arange(y0, y1 + 1) + 0.5
        X, Y = np.meshgrid(xs, ys)
        d = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(d) < 1e-12:
            continue
        l0 = ((b[1] - c[1]) * (X - c[0]) + (c[0] - b[0]) * (Y - c[1])) / d
        l1 = ((c[1] - a[1]) * (X - c[0]) + (a[0] - c[0]) * (Y - c[1])) / d
        l2 = 1 - l0 - l1
        m = (l0 >= -1e-4) & (l1 >= -1e-4) & (l2 >= -1e-4)
        if not m.any():
            continue
        yy, xx = np.nonzero(m)
        yy = yy + y0; xx = xx + x0
        tri[yy, xx] = t
        bar[yy, xx, 0] = l0[m]; bar[yy, xx, 1] = l1[m]; bar[yy, xx, 2] = l2[m]
    return tri, bar


def dilate(img, filled, iters=None):
    """fill every empty texel with its nearest filled texel (seams / mip padding)"""
    from scipy import ndimage
    _, (iy, ix) = ndimage.distance_transform_edt(~filled, return_indices=True)
    return img[iy, ix]


# ------------------------------------------------------------------------------------------------ painting
C_BLACK = srgb2lin((27, 26, 28))
C_BLACK_HI = srgb2lin((52, 52, 58))        # sheen on top surfaces
C_TAN = srgb2lin((152, 84, 38))
C_TAN_LT = srgb2lin((188, 120, 64))
C_TAN_DK = srgb2lin((108, 56, 26))
C_NOSE = srgb2lin((22, 21, 22))
C_LIP = srgb2lin((24, 20, 21))
C_PAD = srgb2lin((38, 34, 34))
C_CLAW = srgb2lin((26, 24, 24))
C_TOOTH = srgb2lin((226, 214, 188))
C_TONGUE = srgb2lin((186, 104, 126))
C_GUM = srgb2lin((120, 58, 70))
C_GUM_DK = srgb2lin((40, 28, 30))
C_EARIN = srgb2lin((52, 44, 46))


def ellip(P, c, r):
    return np.linalg.norm((P - np.asarray(c)) / np.asarray(r), axis=1)


def paint(P, N, part, owner, noise):
    """P, N (n, 3) rest positions / normals; part (n,) ids; owner (n,) dominant bone name index group;
    noise (n,) fbm in [0, 1]. Returns linear RGB (n, 3), roughness (n,), tan mask (n,)."""
    x, y, z = P[:, 0], P[:, 1], P[:, 2]
    ax = np.abs(x)
    nx_in = -np.sign(x) * N[:, 0]                      # + = the normal points toward the midline (inner surfaces)
    jit = (noise - 0.5) * 0.018                         # organic edges (m)
    tan = np.zeros(len(P), np.float32)

    ec, en, _ = A.eye_frame("L")
    # 1. spot over each eye (a little medial and above)
    tan = np.maximum(tan, 1 - sstep(0.75, 1.1, ellip(np.c_[ax, y, z], ec + np.array([-0.004, 0.006, 0.021]),
                                                     (0.011, 0.012, 0.0085)) + jit * 20))
    # 2. muzzle sides + chin (the bridge stays black): in front of the eyes, below a line sloping to the nose
    ztop = 0.770 + 0.22 * (y + 0.54)
    muzzle = sstep(-0.522, -0.545, y + jit * 0.5) * sstep(0.004, -0.006, z - ztop + jit * 0.6)
    muzzle *= sstep(0.012, 0.022, ax + (z > 0.74) * 0.0)          # the top midline stays black
    muzzle = np.where(z < 0.712, sstep(-0.50, -0.53, y + jit * 0.5), muzzle)    # lower jaw / chin: tan
    tan = np.maximum(tan, muzzle * (z > 0.64))
    # 3. cheeks under the eyes, 4. throat bib
    tan = np.maximum(tan, 1 - sstep(0.8, 1.15, ellip(np.c_[ax, y, z], (0.062, -0.508, 0.728), (0.030, 0.042, 0.030))
                                    + jit * 18))
    throat = 1 - sstep(0.8, 1.15, ellip(P, (0, -0.495, 0.650), (0.050, 0.075, 0.040)) + jit * 18)
    tan = np.maximum(tan, throat * (N[:, 2] < 0.3))
    # 5. two triangles on the forechest (inverted, either side of the midline)
    u, v = ax, z
    def tri_mask(pa, pb, pc, soft=0.006):
        def edge(p, q):
            e = np.array(q) - np.array(p); nrm = np.array([e[1], -e[0]]) / np.hypot(*e)
            return (u - p[0]) * nrm[0] + (v - p[1]) * nrm[1]
        d = np.minimum(np.minimum(edge(pa, pb), edge(pb, pc)), edge(pc, pa))
        return sstep(-soft, soft, d + jit * 0.6)
    chest = tri_mask((0.085, 0.500), (0.018, 0.512), (0.048, 0.430))
    chest2 = tri_mask((0.018, 0.512), (0.085, 0.500), (0.048, 0.430))      # winding-safe
    chest = np.maximum(chest, chest2) * (y < -0.30) * (N[:, 1] < -0.15)
    tan = np.maximum(tan, chest)
    # 6. fore legs: all round below mid forearm, up the inside/front higher
    fore = (y < -0.12) & (ax > 0.05)
    lo = sstep(0.19, 0.16, z + jit)
    inner = sstep(0.27, 0.22, z + jit) * sstep(0.1, 0.5, np.maximum(nx_in, -N[:, 1] * 0.6))
    tan = np.maximum(tan, np.where(fore, np.maximum(lo, inner), 0))
    # 7. hind legs: below the hock all round, the front of the hock / gaskin, the inside of the thighs
    hind = (y > 0.12) & (ax > 0.03)
    lo = sstep(0.16, 0.12, z + jit)
    front_hock = sstep(0.30, 0.24, z + jit) * sstep(0.2, 0.6, -N[:, 1]) * (y > 0.2)
    inner = sstep(0.46, 0.40, z + jit) * sstep(0.15, 0.5, nx_in) * (y > 0.13) * (y < 0.36)
    tan = np.maximum(tan, np.where(hind, np.maximum(np.maximum(lo, front_hock), inner), 0))
    # 8. under the tail root
    tan = np.maximum(tan, (1 - sstep(0.8, 1.15, ellip(P, (0, 0.372, 0.535), (0.030, 0.030, 0.040)) + jit * 18))
                     * (N[:, 1] > 0.1))
    tan = np.clip(tan, 0, 1)
    tan = np.where(part == PART["coat"], tan, 0)
    tan = np.where(part == PART["ear"], 0, tan)

    # colours
    shade = 0.82 + 0.36 * noise
    top = np.clip(N[:, 2], 0, 1)
    black = C_BLACK[None] * shade[:, None] + (C_BLACK_HI - C_BLACK)[None] * (top * noise)[:, None]
    tcore = np.clip(tan * 1.6 - 0.3, 0, 1)
    tanc = C_TAN_DK[None] * (1 - tcore)[:, None] + (C_TAN[None] * (1 - noise)[:, None] + C_TAN_LT[None] * noise[:, None]) * tcore[:, None]
    col = black * (1 - tan)[:, None] + tanc * tan[:, None]
    rough = 0.52 * (1 - tan) + 0.66 * tan
    # black lip line and the rim of the eyelids
    lip = sstep(0.0075, 0.004, np.abs(z - 0.707)) * (y < -0.47) * (ax < 0.07)
    lid = sstep(0.0045, 0.002, np.abs(np.linalg.norm(np.c_[ax, y, z] - ec, axis=1) - 0.0145))
    k = np.maximum(lip, lid)[:, None]
    col = col * (1 - k) + C_LIP[None] * k
    # parts
    def put(mask, c, r):
        nonlocal col, rough
        col = np.where(mask[:, None], c[None], col); rough = np.where(mask, r, rough)
    put(part == PART["nose"], C_NOSE * (0.8 + 0.4 * noise[:, None]), 0.38)
    put(part == PART["pad"], C_PAD * (0.8 + 0.4 * noise[:, None]), 0.85)
    put(part == PART["claw"], C_CLAW, 0.32)
    put(part == PART["tooth"], C_TOOTH, 0.25)
    put(part == PART["tongue"], C_TONGUE * (0.85 + 0.3 * noise[:, None]), 0.30)
    cut = part == PART["cut"]
    near_eye = np.linalg.norm(np.c_[ax, y, z] - ec, axis=1) < 0.022
    # mouth: black gum margin at the lip line, pink-red inside; the eye socket walls dark
    gum = np.where((np.abs(z - 0.707) < 0.004)[:, None], C_GUM_DK[None], C_GUM[None] * (0.8 + 0.4 * noise[:, None]))
    col = np.where((cut & ~near_eye)[:, None], gum, col); rough = np.where(cut & ~near_eye, 0.35, rough)
    put(cut & near_eye, C_GUM_DK, 0.3)
    ear_in = (part == PART["ear"]) & (np.sign(N[:, 0]) != np.sign(x))
    col = np.where(ear_in[:, None], C_EARIN[None] * (0.8 + 0.4 * noise[:, None]), col)
    rough = np.where(ear_in, 0.65, rough)
    return col.astype(np.float32), rough.astype(np.float32), tan


def flow_dir(P, owner_kind):
    """hair flow per point: 0 body -> backward, 1 leg -> down, 2 tail -> along (down/back), 3 head -> backward, 4 ear
    -> down"""
    d = np.zeros_like(P)
    d[:] = (0, 1, -0.25)
    d[owner_kind == 1] = (0, 0.12, -1)
    d[owner_kind == 2] = (0, 0.4, -1)
    d[owner_kind == 3] = (0, 1, 0.1)
    d[owner_kind == 4] = (0, -0.2, -1)
    return d / np.linalg.norm(d, axis=1, keepdims=True)


def fur_height(P, D, part):
    """clumped fur height: noise stretched along the flow D (clumps ~1.6 mm wide, ~7 mm long) + fine strands"""
    s = (P * D).sum(axis=1, keepdims=True)
    perp = P - D * s
    Q1 = perp / 0.0016 + D * s / 0.0070
    Q2 = perp / 0.0006 + D * s / 0.0030
    h = 0.65 * fbm(Q1, 2) + 0.35 * vnoise(Q2 * 1.0 + 3.1)
    pebble = fbm(P / 0.0009, 2)
    h = np.where((part == PART["nose"]) | (part == PART["pad"]), pebble, h)
    h = np.where((part == PART["tooth"]) | (part == PART["claw"]) | (part == PART["cut"]), 0.5, h)
    h = np.where(part == PART["tongue"], 0.5 + 0.3 * (fbm(P / 0.0015, 2) - 0.5), h)
    return h


def eye_texture(res=1024):
    y, x = np.mgrid[0:res, 0:res]
    u = (x + 0.5) / res - 0.5; v = 0.5 - (y + 0.5) / res
    r = np.hypot(u, v); ang = np.arctan2(v, u)
    R_IRIS, R_PUP = 0.118, 0.050
    rng = np.random.RandomState(3)
    streak = np.interp(ang, np.linspace(-np.pi, np.pi, 181), rng.rand(181))
    C_IRIS_IN = srgb2lin((98, 58, 26)); C_IRIS_OUT = srgb2lin((52, 30, 14)); C_RING = srgb2lin((20, 12, 8))
    C_PUP = srgb2lin((6, 5, 5)); C_SCL = srgb2lin((120, 96, 80))
    t = np.clip((r - R_PUP) / (R_IRIS - R_PUP), 0, 1)[..., None]
    iris = C_IRIS_IN * (1 - t) + C_IRIS_OUT * t
    iris = iris * (0.8 + 0.4 * streak[..., None])
    ring = sstep(R_IRIS - 0.014, R_IRIS, r)[..., None]
    iris = iris * (1 - ring) + C_RING * ring
    col = np.where((r < R_IRIS)[..., None], iris, C_SCL * (0.9 + 0.1 * streak[..., None]))
    pup = 1 - sstep(R_PUP - 0.004, R_PUP + 0.002, r)
    col = col * (1 - pup[..., None]) + C_PUP * pup[..., None]
    return (lin2srgb(col) * 255 + 0.5).astype(np.uint8)


def vertex_ao(V, Nv, skin):
    from sdf import eval_prims
    ao = np.zeros(len(V))
    for i, dlt in enumerate((0.01, 0.02, 0.035, 0.055, 0.08)):
        d = eval_prims(skin, V + Nv * dlt)
        ao += np.clip(dlt - d, 0, None) / dlt / (1.6 ** i)
    return np.clip(1 - 0.55 * ao, 0.25, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mesh", default=os.path.join(AP.BUILD, "stage_a.npz"))
    ap.add_argument("--in", dest="inp", default=os.path.join(AP.BUILD, "stage_b.blend"))
    ap.add_argument("--out", default=os.path.join(AP.BUILD, "stage_c.blend"))
    ap.add_argument("--tex-dir", default=os.path.join(AP.BUILD, "textures"))
    ap.add_argument("--res", type=int, default=4096)
    ap.add_argument("--preview", default=None)
    ap.add_argument("--textures-only", action="store_true")
    ap.add_argument("--relink-only", action="store_true",
                    help="skip the painting: build stage C from the PNGs already in --tex-dir (the UVs must not have "
                         "changed; the stored atlas hash is checked)")
    a = ap.parse_args()
    t0 = time.time()
    D = np.load(a.mesh, allow_pickle=False)
    V, F, UV, part = D["v0"], D["f0"], D["uv0"], D["part0"]
    import hashlib
    uv_hash = hashlib.sha1(np.ascontiguousarray(UV.astype(np.float32)).tobytes()).hexdigest()
    hash_file = os.path.join(a.tex_dir, "uv_hash.txt")
    if a.relink_only:
        old = open(hash_file).read().strip() if os.path.exists(hash_file) else ""
        if old != uv_hash:
            raise SystemExit("--relink-only: the LOD0 UV atlas changed since the textures were painted; re-paint them")
        return relink(a)
    bones = [str(b) for b in D["bones"]]
    wi, ww = D["wi0"], D["ww0"]
    body = part != PART["eye"]
    fid = np.nonzero(body)[0]
    # vertex normals (area weighted)
    fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    Nv = np.zeros_like(V)
    for k in range(3):
        np.add.at(Nv, F[:, k], fn)
    Nv /= np.maximum(np.linalg.norm(Nv, axis=1, keepdims=True), 1e-12)
    # per-vertex owner kind for the hair flow
    dom = np.array([bones[i] for i in wi[:, 0]])
    kind = np.zeros(len(V), np.int32)
    legs = ("Scapula", "UpperArm", "Forearm", "FrontFoot", "FrontToe", "Thigh", "Shin", "HindFoot", "HindToe")
    kind[np.array([any(b.startswith(l) for l in legs[2:]) or b.startswith("Shin") for b in dom])] = 1
    kind[np.array([b.startswith("Tail") for b in dom])] = 2
    kind[np.array([b in ("Head", "Nose", "Jaw", "Neck2") for b in dom])] = 3
    kind[np.array([b.startswith("Ear") for b in dom])] = 4
    # AO at the vertices from the SDF
    ao_v = vertex_ao(V, Nv, A.skin_prims())
    ao_v[part_vertex_mask(F, part, (PART["cut"],), len(V))] *= 0.45
    log(f"vertex data ({time.time() - t0:.0f} s)")

    res = a.res
    tri, bar = rasterize(UV[fid], res)
    filled = tri >= 0
    log(f"rasterised {filled.mean() * 100:.1f} % of {res}^2 ({time.time() - t0:.0f} s)")
    ty, tx = np.nonzero(filled)
    tl = fid[tri[ty, tx]]
    b = bar[ty, tx]
    del bar
    Fv = F[tl]
    P = (V[Fv] * b[..., None]).sum(axis=1)
    Nn = (Nv[Fv] * b[..., None]).sum(axis=1); Nn /= np.linalg.norm(Nn, axis=1, keepdims=True)
    AO = (ao_v[Fv] * b).sum(axis=1)
    pt = part[tl]
    # tangent frame per triangle (dP/du, dP/dv)
    e1 = V[F[:, 1]] - V[F[:, 0]]; e2 = V[F[:, 2]] - V[F[:, 0]]
    d1 = UV[:, 1] - UV[:, 0]; d2 = UV[:, 2] - UV[:, 0]
    det = d1[:, 0] * d2[:, 1] - d2[:, 0] * d1[:, 1]
    det = np.where(np.abs(det) < 1e-12, 1e-12, det)
    Tt = (e1 * d2[:, 1:2] - e2 * d1[:, 1:2]) / det[:, None]
    Bt = (e2 * d1[:, 0:1] - e1 * d2[:, 0:1]) / det[:, None]
    Tp = Tt[tl]; Bp = Bt[tl]
    Tp = Tp - Nn * (Tp * Nn).sum(1, keepdims=True); Tp /= np.maximum(np.linalg.norm(Tp, axis=1, keepdims=True), 1e-12)
    sgn = np.sign((np.cross(Nn, Tp) * Bp).sum(1)); sgn[sgn == 0] = 1
    Bn = np.cross(Nn, Tp) * sgn[:, None]
    kd = np.array([np.bincount([kind[j] for j in f]).argmax() for f in F])
    Dflow = flow_dir(P, kd[tl])
    Dflow = Dflow - Nn * (Dflow * Nn).sum(1, keepdims=True)
    Dflow /= np.maximum(np.linalg.norm(Dflow, axis=1, keepdims=True), 1e-9)
    log(f"texel attributes ({time.time() - t0:.0f} s)")

    n = len(P)
    base = np.zeros((n, 3), np.float32); rough = np.zeros(n, np.float32); nrm = np.zeros((n, 3), np.float32)
    CH = 1_500_000
    for s in range(0, n, CH):
        sl = slice(s, s + CH)
        noise = fbm(P[sl] / 0.012, 4)
        col, ro, _ = paint(P[sl], Nn[sl], pt[sl], None, noise)
        # fur strands brighten/darken the albedo a little
        h = fur_height(P[sl], Dflow[sl], pt[sl])
        col = col * (0.88 + 0.24 * h[:, None])
        base[sl] = col; rough[sl] = ro
        dl = 0.0003
        hT = fur_height(P[sl] + Tp[sl] * dl, Dflow[sl], pt[sl])
        hB = fur_height(P[sl] + Bn[sl] * dl, Dflow[sl], pt[sl])
        strength = np.where(np.isin(pt[sl], (PART["nose"], PART["pad"])), 0.00012, 0.00022)
        dx = (hT - h) / dl * strength; dy = (hB - h) / dl * strength
        v3 = np.stack([-dx, -dy, np.ones_like(dx)], axis=1)
        nrm[sl] = v3 / np.linalg.norm(v3, axis=1, keepdims=True)
        log(f"  painted {min(s + CH, n)}/{n} ({time.time() - t0:.0f} s)")
    base *= (0.55 + 0.45 * AO)[:, None]                     # a little baked cavity darkening in the albedo

    def to_img(vals, ch, fill):
        img = np.zeros((res, res, ch), np.float32); img[:] = fill
        img[ty, tx] = vals.reshape(n, ch)
        return dilate(img, filled)
    os.makedirs(a.tex_dir, exist_ok=True)
    from PIL import Image
    bc = (lin2srgb(to_img(base, 3, 0)) * 255 + 0.5).astype(np.uint8)
    Image.fromarray(bc).save(os.path.join(a.tex_dir, TEX + "_BaseColor.png"))
    nm = to_img(nrm, 3, 0) * 0.5 + 0.5
    Image.fromarray((np.clip(nm, 0, 1) * 255 + 0.5).astype(np.uint8)).save(os.path.join(a.tex_dir, TEX + "_Normal.png"))
    ro = to_img(rough, 1, 0.6)[..., 0]
    Image.fromarray((ro * 255 + 0.5).astype(np.uint8)).save(os.path.join(a.tex_dir, TEX + "_Roughness.png"))
    aoi = to_img(AO.astype(np.float32), 1, 1)[..., 0]
    Image.fromarray((aoi * 255 + 0.5).astype(np.uint8)).save(os.path.join(a.tex_dir, TEX + "_AO.png"))
    sm = 1 - ro
    mask = np.stack([np.zeros_like(sm), aoi, np.zeros_like(sm), sm], axis=-1)
    Image.fromarray((mask * 255 + 0.5).astype(np.uint8), "RGBA").save(os.path.join(a.tex_dir, TEX + "_MaskMap.png"))
    ms = np.stack([np.zeros_like(sm), np.zeros_like(sm), np.zeros_like(sm), sm], axis=-1)
    Image.fromarray((ms * 255 + 0.5).astype(np.uint8), "RGBA").save(
        os.path.join(a.tex_dir, TEX + "_MetallicSmoothness.png"))
    Image.fromarray(eye_texture(1024)).save(os.path.join(a.tex_dir, TEX_EYE + "_BaseColor.png"))
    with open(hash_file, "w") as fh:
        fh.write(uv_hash + "\n")
    log(f"wrote textures to {a.tex_dir} ({time.time() - t0:.0f} s)")
    if a.preview:
        Image.fromarray(bc).resize((1024, 1024)).save(a.preview)
    if a.textures_only:
        return
    relink(a)


def relink(a):
    import bpy
    bpy.ops.wm.open_mainfile(filepath=os.path.abspath(a.inp))
    tex = {os.path.splitext(f)[0]: os.path.abspath(os.path.join(a.tex_dir, f)) for f in os.listdir(a.tex_dir)}
    tex.pop("uv_hash", None)
    build_materials(bpy, tex)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(a.out))
    log(f"wrote {a.out}")


def part_vertex_mask(F, part, ids, nv):
    m = np.zeros(nv, bool)
    for i in ids:
        m[np.unique(F[part == i])] = True
    return m


def build_materials(bpy, tex):
    NAME = AP.NAME

    def load_image(path, name, noncolor):
        img = bpy.data.images.get(name)
        if img is not None:
            bpy.data.images.remove(img)
        img = bpy.data.images.load(path, check_existing=False)
        img.name = name
        img.colorspace_settings.name = "Non-Color" if noncolor else "sRGB"
        return img
    mb = bpy.data.materials.get(f"M_{NAME}_Body") or bpy.data.materials.new(f"M_{NAME}_Body")
    me_ = bpy.data.materials.get(f"M_{NAME}_Eye") or bpy.data.materials.new(f"M_{NAME}_Eye")
    for m in (mb, me_):
        m.use_nodes = True
        m.node_tree.nodes.clear()
    nt = mb.node_tree; nd, ln = nt.nodes, nt.links
    out = nd.new("ShaderNodeOutputMaterial"); out.location = (600, 0)
    bs = nd.new("ShaderNodeBsdfPrincipled"); bs.location = (250, 0)
    uv = nd.new("ShaderNodeUVMap"); uv.uv_map = "UVMap"; uv.location = (-700, 0)

    def tnode(key, noncolor, loc, label):
        t = nd.new("ShaderNodeTexImage")
        t.image = load_image(tex[key], key, noncolor)
        t.location = loc; t.label = label
        ln.new(uv.outputs[0], t.inputs["Vector"])
        return t
    bc = tnode(TEX + "_BaseColor", False, (-400, 300), "BaseColor (sRGB)")
    ro = tnode(TEX + "_Roughness", True, (-400, 0), "Roughness")
    nm = tnode(TEX + "_Normal", True, (-400, -300), "Normal (tangent, OpenGL +Y)")
    tnode(TEX + "_AO", True, (-400, -600), "AO (engine occlusion slot; not used by Principled)")
    nmap = nd.new("ShaderNodeNormalMap"); nmap.space = "TANGENT"; nmap.uv_map = "UVMap"; nmap.location = (-50, -300)
    ln.new(bc.outputs["Color"], bs.inputs["Base Color"])
    ln.new(ro.outputs["Color"], bs.inputs["Roughness"])
    ln.new(nm.outputs["Color"], nmap.inputs["Color"])
    ln.new(nmap.outputs["Normal"], bs.inputs["Normal"])
    bs.inputs["Specular IOR Level"].default_value = 0.4
    ln.new(bs.outputs[0], out.inputs["Surface"])
    nt = me_.node_tree; nd, ln = nt.nodes, nt.links
    out = nd.new("ShaderNodeOutputMaterial"); out.location = (600, 0)
    bs = nd.new("ShaderNodeBsdfPrincipled"); bs.location = (250, 0)
    uv = nd.new("ShaderNodeUVMap"); uv.uv_map = "UVMap"; uv.location = (-700, 0)
    t = nd.new("ShaderNodeTexImage"); t.image = load_image(tex[TEX_EYE + "_BaseColor"], TEX_EYE + "_BaseColor", False)
    t.location = (-400, 0); t.label = "Eye BaseColor (sRGB)"
    ln.new(uv.outputs[0], t.inputs["Vector"])
    ln.new(t.outputs["Color"], bs.inputs["Base Color"])
    bs.inputs["Roughness"].default_value = 0.05
    bs.inputs["IOR"].default_value = 1.376
    bs.inputs["Coat Weight"].default_value = 1.0
    bs.inputs["Coat Roughness"].default_value = 0.02
    bs.inputs["Coat IOR"].default_value = 1.376
    ln.new(bs.outputs[0], out.inputs["Surface"])


if __name__ == "__main__":
    main()
