"""Dog stage C: the Rottweiler's textures and materials.

  python3 tools/dog/dog_textures.py [--mesh build/dog/stage_a.npz] [--in build/dog/stage_b.blend]
          [--out build/dog/stage_c.blend] [--tex-dir build/dog/textures] [--res 4096] [--preview <png>]
          [--textures-only]

The atlas of LOD0 (stage A) is rasterised in numpy: every texel knows its triangle, barycentric weights, rest-pose
3D position, normal, tangent frame and part id.  The coat is painted as a function of 3D position relative to the
anatomy landmarks (tools/dog/anatomy.py), so the markings follow any shape change:
  black coat with grey hair tips on the clump crests; tan markings (golden tan with a rust rim along the borders,
  pale golden paws): a spot on the brow over each eye, one face region from the muzzle side to the cheek (the nose
  bridge and the upper-lip midline stay black) with a stripe down the side of the throat and a U bib under the chin,
  two wide wedges on the forechest, the fore legs along carpus -> elbow (to the elbow on the inside, about 40 % up the
  outside), the hind legs below the hock, up the front and the inside, the inside of the thighs, under the tail.  The
  leg masks are relative to the joints (anatomy.J), the head masks to the head design frame and the curved lip line
  (anatomy.lip_z).  Black lip band, lid rims and pencil marks between the toes; nose leather, claws; dark pads;
  lavender-pink tongue and gums.
Normal map: fine fur strands and coarse clumps (noise stretched along the hair flow: head to tail on the body, down
the legs, along the tail and ears), sampled in 3D and differentiated along each texel's tangent frame (OpenGL +Y
convention), plus a pebbled nose leather and pad texture.  AO from the anatomy SDF at the LOD0 vertices.

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
C_BLACK = srgb2lin((34, 31, 35))
C_BLACK_HI = srgb2lin((74, 70, 80))        # grey hair tips / sheen on top surfaces
C_TAN = srgb2lin((186, 122, 72))
C_TAN_LT = srgb2lin((206, 148, 96))
C_TAN_DK = srgb2lin((118, 58, 28))         # the rust rim along the black/tan borders
C_TAN_PAW = srgb2lin((212, 166, 116))      # pale golden paws and pasterns
C_NOSE = srgb2lin((30, 29, 33))
C_LIP = srgb2lin((24, 20, 21))
C_PAD = srgb2lin((38, 34, 34))
C_CLAW = srgb2lin((26, 24, 24))
C_TOOTH = srgb2lin((226, 214, 188))
C_TONGUE = srgb2lin((152, 100, 148))
C_GUM = srgb2lin((120, 58, 70))
C_GUM_DK = srgb2lin((40, 28, 30))
C_EARIN = srgb2lin((52, 44, 46))
C_MUZZLE = srgb2lin((70, 52, 44))          # the sooty tan toward the nose leather


def ellip(P, c, r):
    return np.linalg.norm((P - np.asarray(c)) / np.asarray(r), axis=1)


def seg(P, a, b):
    """parameter t along a -> b (0 at a, 1 at b, unclamped) and the distance to the clamped segment"""
    ab = b - a
    t = ((P - a) @ ab) / (ab @ ab)
    q = a + np.clip(t, 0, 1)[:, None] * ab
    return t, np.linalg.norm(P - q, axis=1)


def band(P2, pts, hw):
    """distance to a 2D polyline pts (k, 2) divided by its half width hw (k,) (interpolated along each segment):
    < 1 inside the band"""
    best = np.full(len(P2), 1e9)
    for i in range(len(pts) - 1):
        a, b = np.asarray(pts[i], float), np.asarray(pts[i + 1], float)
        ab = b - a
        t = np.clip(((P2 - a) @ ab) / (ab @ ab), 0, 1)
        w = hw[i] * (1 - t) + hw[i + 1] * t
        best = np.minimum(best, np.linalg.norm(P2 - (a + t[:, None] * ab), axis=1) / w)
    return best


def fur_macro(P, D):
    """coarse fur clumps (~5.5 mm wide, ~28 mm long along the hair flow D), in [0, 1]: they streak the black/tan
    borders, tint the clump crests and add a macro normal that survives mip-mapping at game distances"""
    s = (P * D).sum(axis=1, keepdims=True)
    perp = P - D * s
    return fbm(perp / 0.0055 + D * s / 0.028 + 11.7, 3)


def face_hair(Ph):
    """1 on the body, 0.4 on the short face hair: fur_macro's contrast, grey tips and macro normal are scaled by it.
    Ph are head design-frame coordinates (anatomy.H_inv), so the mask follows the head; its window ends where the
    throat meets the neck (the design frame is pitched and lowered with the head, so a window at design z 0.50 would
    smooth the neck front down to the forechest)."""
    return 1 - 0.6 * sstep(0.55, 0.63, Ph[:, 2]) * sstep(-0.35, -0.42, Ph[:, 1])


def paint(P, N, part, m, noise):
    """P, N (n, 3) rest positions / normals; part (n,) ids; m (n,) macro fur clumps (fur_macro); noise (n,) fbm in
    [0, 1]. Returns linear RGB (n, 3), roughness (n,), tan mask (n,)."""
    x, y, z = P[:, 0], P[:, 1], P[:, 2]
    ax = np.abs(x)
    n = len(P)
    nx_in = -np.sign(x) * N[:, 0]                      # + = the normal points toward the midline (inner surfaces)
    jit = (noise - 0.5) * 0.018                         # organic edges (m)
    tan = np.zeros(n, np.float32)
    paw = np.zeros(n, np.float32)                       # 1 = pale paw tan
    legcore = np.ones(n, np.float32)                    # < 1: the rust rim of the leg markings reaches this deep

    # the head markings are laid out in the head's design frame (anatomy.H_inv), so they follow the head placement
    Ph = A.H_inv(P); Nh = N @ A.RH
    hy, hz = Ph[:, 1], Ph[:, 2]
    hax = np.abs(Ph[:, 0])
    L = A.lip_z(Ph[:, 0], hy)                           # the curved lip line (design frame)
    ec = A.H_inv(A.eye_frame("L")[0])
    # 1. spot over each eye, anchored on the skin of the brow (a little medial and ~2.4 cm above the cornea)
    sd = np.array([0.20, -0.98, 0.0]); sd /= np.linalg.norm(sd)
    spot_c = A.H_inv(A.ray_to_surface(A.H(ec + np.array([-0.010, 0.020, 0.026])), A.Hd(sd)))
    tan = np.maximum(tan, 1 - sstep(0.75, 1.1, ellip(np.c_[hax, hy, hz], spot_c, (0.010, 0.010, 0.009)) + jit * 20))
    # 2. one continuous face region (muzzle side -> cheek), below a top line rising from the nostrils and capped under
    #    the eye; the nose bridge and the upper-lip midline stay black; gated by the curved lip line
    ztop = np.minimum(0.748 + 0.36 * (hy + 0.635), 0.766)
    ztop = ztop - 0.014 * np.clip(1 - np.abs(hy + 0.505) / 0.025, 0, 1)      # the black dips under the eye's rear
    ztop = np.maximum(ztop, 0.786 * sstep(-0.488, -0.478, hy))              # the band rises to the ear front
    face = sstep(-0.455, -0.475, hy + jit * 0.5) * sstep(0.004, -0.006, hz - ztop + jit * 0.6)
    face *= sstep(0.016, 0.028, hax) * (hz > L - 0.007)
    tan = np.maximum(tan, face)
    #    throat-side stripe from behind the jaw angle down the side of the throat
    ts = band(np.c_[hy, hz], [(-0.478, 0.715), (-0.468, 0.640), (-0.455, 0.595)], [0.020, 0.022, 0.015])
    tan = np.maximum(tan, (1 - sstep(0.8, 1.15, ts + jit * 14)) * sstep(0.030, 0.050, hax))
    #    throat bib: a U from under the chin to about half-way from the jaw angle to the chest wedges, between the
    #    stripes (the stripe end and the bib's lower bound are raised 2 cm for the lower, pitched head carriage)
    u = np.clip((hz - 0.555) / (0.668 - 0.555), 0, 1)
    bib = (sstep(0.006, -0.006, hax - 0.060 * np.sqrt(u) + jit * 0.6) * sstep(0.573, 0.583, hz)   # no chest leak
           * (hz < 0.690) * (hy < -0.40) * (hy > -0.625))
    tan = np.maximum(tan, bib * sstep(0.0, 0.35, -(Nh[:, 1] * 0.8 + Nh[:, 2] * 0.6)))
    # 3. lower jaw: black lower lip and chin front, tan only underneath
    under = sstep(-0.15, -0.45, Nh[:, 2])
    lowjaw = (hz <= L - 0.007) & (hz > 0.600) & (hy < -0.49)
    tan = np.where(lowjaw, under * sstep(-0.648, -0.628, hy), tan)

    # 4. two wide inverted triangles on the lower forechest, over the front of the upper arms, wrapping back along
    #    the bottom of the upper arm to the front of the elbow
    def tri_mask(pa, pb, pc, soft=0.006):
        def edge(p, q):
            e = np.array(q) - np.array(p); nrm = np.array([e[1], -e[0]]) / np.hypot(*e)
            return (ax - p[0]) * nrm[0] + (z - p[1]) * nrm[1]
        d = np.minimum(np.minimum(edge(pa, pb), edge(pb, pc)), edge(pc, pa))
        return sstep(-soft, soft, d + jit * 0.6)
    zs, ze, xs, ye = A.J["shoulder"][2], A.J["elbow"][2], A.J["shoulder"][0], A.J["elbow"][1]
    pa = (0.020, ze + 0.76 * (zs - ze)); pb = (xs + 0.045, ze + 0.78 * (zs - ze)); pc = (xs - 0.008, ze + 0.18 * (zs - ze))
    chest = np.maximum(tri_mask(pa, pb, pc, soft=0.007), tri_mask(pb, pa, pc, soft=0.007)) * (y < -0.28) * (N[:, 1] < -0.05)
    tail = 1 - sstep(0.8, 1.1, ellip(np.c_[ax, y, z], (xs - 0.012, ye - 0.050, ze + 0.040), (0.032, 0.055, 0.028)) + jit * 14)
    chest = np.maximum(chest, tail * (N[:, 2] < 0.4) * (ax > 0.03) * sstep(-0.05, 0.25, -nx_in))
    tan = np.maximum(tan, chest)

    # 5. fore legs, along carpus -> elbow: highest on the inside (to the elbow), lowest on the outside; legcore is the
    #    same mask 7 cm deeper into the tan (the rust rim fades to the clear tan over that distance)
    Lf = np.linalg.norm(A.J["elbow"] - A.J["carpus"])
    for s in "LR":
        sd = (x > 0) if s == "L" else (x < 0)
        t, d = seg(P, A.side("carpus", s), A.side("elbow", s))                    # 0 carpus .. 1 elbow
        leg = sd & (d < 0.075) & (y < -0.12) & (t < 1.3)
        h = 0.48 + 0.64 * np.maximum(nx_in, 0) - 0.10 * np.maximum(-nx_in, 0) + 0.08 * (-N[:, 1])
        tan = np.where(leg, np.maximum(tan, sstep(h + 0.13, h - 0.13, t + jit * 4)), tan)
        paw = np.where(leg, np.maximum(paw, 0.7 * sstep(0.35, -0.10, t)), paw)
        i = 0.07 / Lf
        legcore = np.where(leg & (t < 0.95), sstep(h + 0.13 - i, h - 0.13 - i, t + jit * 4), legcore)
    # 6. hind legs, along hock -> stifle: all round below the hock, a stripe up the front widening to the hock, the
    #    inside; then the inside of the thighs up to the groin
    Lh = np.linalg.norm(A.J["stifle"] - A.J["hock"])
    for s in "LR":
        sd = (x > 0) if s == "L" else (x < 0)
        t, d = seg(P, A.side("hock", s), A.side("stifle", s))                     # 0 hock .. 1 stifle
        leg = sd & (d < 0.080) & (y > 0.10) & (t < 1.5)
        below = sstep(0.18, -0.02, t + jit * 3)
        thr = -0.15 + 0.80 * np.clip(t, 0, 1.3)
        stripe = sstep(thr - 0.12, thr + 0.12, -N[:, 1] + jit * 6) * sstep(1.45, 1.20, t)
        inner = sstep(0.10, 0.40, nx_in)
        tan = np.where(leg, np.maximum(tan, np.maximum(np.maximum(below, stripe), inner)), tan)
        paw = np.where(leg, np.maximum(paw, 0.7 * sstep(0.30, -0.10, t)), paw)
        ih = 0.07 / Lh
        legcore = np.where(leg & (t < 0.9), np.maximum(np.maximum(sstep(0.18 - ih, -0.02 - ih, t + jit * 3), stripe),
                                                       inner), legcore)
    zst = A.J["stifle"][2]
    inner_th = sstep(zst + 0.12, zst + 0.06, z + jit) * sstep(0.15, 0.5, nx_in) * (y > 0.13) * (y < 0.36)
    tan = np.maximum(tan, np.where((y > 0.12) & (ax > 0.03), inner_th, 0))
    # 7. paws + pasterns all round (pale)
    for s in "LR":
        sd = (x > 0) if s == "L" else (x < 0)
        for j0, j1, j2 in (("carpus", "mcp", "ftoe"), ("hock", "mtp", "htoe")):
            _, d1 = seg(P, A.side(j0, s), A.side(j1, s)); _, d2 = seg(P, A.side(j1, s), A.side(j2, s))
            w = np.where(sd & (np.minimum(d1, d2) < 0.07), sstep(A.J[j0][2] + 0.02, A.J[j0][2] - 0.03, z), 0)
            tan = np.maximum(tan, w); paw = np.maximum(paw, w); legcore = np.maximum(legcore, w)
    # 8. under the tail root
    tan = np.maximum(tan, (1 - sstep(0.8, 1.15, ellip(P, (0, 0.372, 0.535), (0.030, 0.030, 0.040)) + jit * 18))
                     * (N[:, 1] > 0.1))
    tan = np.clip(tan, 0, 1); tan = np.where(part == PART["coat"], tan, 0)

    # colours
    hs = face_hair(Ph)                                                          # shorter face hair
    m = 0.5 + (m - 0.5) * hs
    tan = np.clip(tan + 2.0 * (m - 0.5) * tan * (1 - tan), 0, 1)               # black hairs streak into the borders
    tan = np.where(part == PART["coat"], tan, 0)
    shade = 0.82 + 0.36 * noise; top = np.clip(N[:, 2], 0, 1); tip = sstep(0.45, 0.80, m) * hs
    black = C_BLACK[None] * (shade * (1 + 0.3 * (m - 0.5) * 2))[:, None] \
        + (C_BLACK_HI - C_BLACK)[None] * (0.5 * tip + 0.8 * top * noise)[:, None]
    tcore = np.minimum(sstep(0.0, 1.0, tan), 0.2 + 0.8 * legcore)
    tmid = C_TAN[None] * (1 - noise)[:, None] + C_TAN_LT[None] * noise[:, None]
    tmid = tmid * (1 - 0.8 * paw)[:, None] + C_TAN_PAW[None] * (0.8 * paw)[:, None]
    tanc = C_TAN_DK[None] * (1 - tcore)[:, None] + tmid * tcore[:, None]
    tanc = tanc * (0.85 + 0.30 * m)[:, None]
    mdk = 0.45 * sstep(-0.56, -0.64, hy) * (hz > 0.64)                          # muzzle darkens toward the nose
    tanc = tanc * (1 - mdk)[:, None] + C_MUZZLE[None] * mdk[:, None]
    col = black * (1 - tan)[:, None] + tanc * tan[:, None]
    rough = 0.40 * (1 - tan) + 0.56 * tan + 0.20 * (0.5 - m)
    # black lip band along the curved slit, the rim of the eyelids, pencil marks between the toes
    lip = sstep(0.009, 0.005, hz - L) * sstep(-0.012, -0.006, hz - L) * (hy < -0.47) * (hax < 0.085)
    lid = sstep(0.0045, 0.002, np.abs(np.linalg.norm(np.c_[hax, hy, hz] - ec, axis=1) - 0.016))
    pm = np.zeros(n, np.float32); T = np.array(A.TOES)
    for s in "LR":
        for jn, sc in (("mcp", A.PAW_SC[0]), ("mtp", A.PAW_SC[1])):
            c = A.side(jn, s)
            near = (np.abs(x - c[0]) < 0.06) & (np.abs(y - c[1] + 0.04) < 0.06) & (z < 0.07)
            for gx, gy in ((T[0] + T[1]) / 2, (T[0] + T[2]) / 2, (T[1] + T[3]) / 2):
                g0y, g1y = c[1] + (gy + 0.010) * sc, c[1] + (gy - 0.008) * sc            # back .. toe tip
                t2 = np.clip((y - g0y) / (g1y - g0y), 0, 1)
                dd = np.hypot(x - (c[0] + gx * sc), y - (g0y + t2 * (g1y - g0y)))
                pm = np.maximum(pm, sstep(0.0032, 0.0012, dd) * sstep(-0.1, 0.3, N[:, 2]) * near)
    k = np.maximum(np.maximum(lip, lid), 0.85 * pm * (part == PART["coat"]))[:, None]
    col = col * (1 - k) + C_LIP[None] * k
    # parts
    def put(mask, c, r):
        nonlocal col, rough
        col = np.where(mask[:, None], c[None], col); rough = np.where(mask, r, rough)
    put(part == PART["nose"], C_NOSE * (0.8 + 0.4 * noise[:, None]), 0.30)
    nos = (part == PART["nose"]) * (1 - sstep(0.8, 1.1, ellip(np.c_[hax, hy, hz], (0.021, -0.668, 0.762),
                                                               (0.0065, 0.0060, 0.0035))))
    col = col * (1 - 0.5 * nos)[:, None]                                          # nostrils
    put(part == PART["pad"], C_PAD * (0.8 + 0.4 * noise[:, None]), 0.85)
    put(part == PART["claw"], C_CLAW, 0.32)
    put(part == PART["tooth"], C_TOOTH, 0.25)
    put(part == PART["tongue"], C_TONGUE * (0.85 + 0.3 * noise[:, None]), 0.30)
    cut = part == PART["cut"]
    near_eye = np.linalg.norm(np.c_[hax, hy, hz] - ec, axis=1) < 0.022
    # mouth: black gum margin at the lip line, pink-red inside; the eye socket walls dark
    gum = np.where((np.abs(hz - L) < 0.004)[:, None], C_GUM_DK[None], C_GUM[None] * (0.8 + 0.4 * noise[:, None]))
    col = np.where((cut & ~near_eye)[:, None], gum, col); rough = np.where(cut & ~near_eye, 0.35, rough)
    put(cut & near_eye, C_GUM_DK, 0.3)
    # inner face of the ear flap (the fold's medial side, above hz 0.850, stays black)
    ear_in = (part == PART["ear"]) & (np.sign(N[:, 0]) != np.sign(x)) & (hz < 0.850)
    col = np.where(ear_in[:, None], C_EARIN[None] * (0.8 + 0.4 * noise[:, None]), col)
    rough = np.where(ear_in, 0.65, rough)
    return col.reshape(n, 3).astype(np.float32), rough.astype(np.float32), tan


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
    R_IRIS, R_PUP = 0.118, 0.056
    rng = np.random.RandomState(3)
    streak = np.interp(ang, np.linspace(-np.pi, np.pi, 181), rng.rand(181))
    C_IRIS_IN = srgb2lin((128, 78, 36)); C_IRIS_OUT = srgb2lin((62, 36, 16)); C_RING = srgb2lin((20, 12, 8))
    C_PUP = srgb2lin((6, 5, 5)); C_SCL = srgb2lin((70, 52, 44))          # dark brown sclera (only a rim shows)
    t = np.clip((r - R_PUP) / (R_IRIS - R_PUP), 0, 1)[..., None]
    iris = C_IRIS_IN * (1 - t) + C_IRIS_OUT * t
    iris = iris * (0.8 + 0.4 * streak[..., None])
    ring = sstep(R_IRIS - 0.022, R_IRIS, r)[..., None]
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
        mac = fur_macro(P[sl], Dflow[sl])
        col, ro, _ = paint(P[sl], Nn[sl], pt[sl], mac, noise)
        # fur strands brighten/darken the albedo a little
        h = fur_height(P[sl], Dflow[sl], pt[sl])
        col = col * (0.88 + 0.24 * h[:, None])
        base[sl] = col; rough[sl] = ro
        dl = 0.0003
        hT = fur_height(P[sl] + Tp[sl] * dl, Dflow[sl], pt[sl])
        hB = fur_height(P[sl] + Bn[sl] * dl, Dflow[sl], pt[sl])
        strength = np.where(np.isin(pt[sl], (PART["nose"], PART["pad"])), 0.00012, 0.00022)
        dx = (hT - h) / dl * strength; dy = (hB - h) / dl * strength
        # macro clumps (fur_macro), softer on the short face hair
        ms = np.where(np.isin(pt[sl], (PART["coat"], PART["ear"])), 0.0016, 0.0) * face_hair(A.H_inv(P[sl]))
        dm = 0.0010
        mT = fur_macro(P[sl] + Tp[sl] * dm, Dflow[sl]); mB = fur_macro(P[sl] + Bn[sl] * dm, Dflow[sl])
        dx = dx + (mT - mac) / dm * ms; dy = dy + (mB - mac) / dm * ms
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
    bs.inputs["Specular IOR Level"].default_value = 0.5       # F0 0.04, as Unity Lit
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
