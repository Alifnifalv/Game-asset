"""Raven stage C: the raven's textures and materials (numpy; Blender only to wire the materials).

  python3 tools/raven/raven_textures.py [--mesh build/raven/stage_a.npz] [--in build/raven/stage_b.blend]
          [--out build/raven/stage_c.blend] [--tex-dir build/raven/textures] [--res 4096] [--preview <png>]
          [--textures-only] [--relink-only]

Three texture sets (look: docs/raven_reference.md 5.1-5.3; metallic-workflow fallback of 5.2: the violet / blue-violet
gloss tints are in the albedo (head / mantle at about 1.5x the chroma of the main table, wings / breast at the 2x of
the fallback table), the smoothness values as in 5.2):

1. BODY atlas (stage A's xatlas UVs of the M_Raven_Body faces: plumage skin, mouth, bill, bare legs, claws).  The LOD0
   atlas is rasterised in numpy (every texel: triangle, barycentrics, rest position, normal, tangent frame, part, bone
   regions) and painted in 3D, so the painting follows any shape change:
   - plumage: overlapping feather "scales" (a Poisson-disk set of feather seeds on the skin, each an ellipse pointing
     along the feather flow; the upstream feather lies on top, so the visible outlines are the tips, convex toward the
     tail).  Exposed size per region: head 3.5 mm (lores 2.5), throat 4.5 mm lanceolate (under the hackles, dark),
     neck 6.5, mantle 16, rump 13, breast 9 -> belly 12, thighs 11 lanceolate, wing arm 8.  Each seed has its own
     tone; outlines darker on the mantle; barb striations along each feather; barb streaks along the flow (1.2 x 5
     mm).  The relief is faint on the head (spec 5.3: hardly visible) and strongest on the mantle.  Colours: violet
     head / nape / mantle, blue-violet wing arm, warm matte breast / belly / thighs / undertail (by the bone regions of the skin weights and
     a dorsal / ventral split of the trunk).
   - lores darker; the pale beaded eyelid ring (from 0.8 mm inside the edge of the opening, measured on the SDF by
     eye_opening(), to LID_R + 2 mm (raven_anatomy's raised lid torus): rho about 4.0-8.0 mm = the 16 mm outer
     diameter of spec 3.3; beads 0.9 mm apart on the torus crest), a dark socket inside it.
   - bill (part 2): grey with longitudinal ridges (1.1 mm) and micro-pitting, a paler worn tip (the distal 14-16 mm,
     grading from 30 mm) with a few pale specks, the tomium line, the pale gape flange at the rictus.
   - mouth interior (part 1): near-black slate, matte (roughness 0.70 instead of the spec's 0.4-0.45: a glossy dark
     wall catches the sky at grazing angles).
   - bare legs (part 3): slate-grey scutes: transverse plates (7.5 mm) down the front of the tarsus, transverse scutes
     (4 mm) on top of the toes, reticulate 1.5 mm scales on the sides / pads, dark crevices.
   - claws (part 4): black horn, paler tips.
   AO: ray-cast occlusion of the whole LOD0 (body + feather strips, bind pose, rays up to 2.5 cm) at the body vertices,
   times the micro occlusion of the feather steps / scute crevices.
2. FEATHER atlas (plumage.SLOTS: 16 columns x 256 px of 2048 px, some split into 512 px quarters; u = across the vane
   with the rachis at the slot's centre line, v = base -> tip).  Painted in texture space per slot, from the feathers
   that use the slot (their outlines -> the slot's envelope; their median width / length -> the physical scale):
   raised rachis (pale grey on the primaries, primary coverts and rectrices), barbs toward the tip (20-35 deg, anti-
   aliased away when finer than the texel), barb clumps (streaks that survive the mips), vane splits (notches along the
   barbs, mostly on the wide inner vane), frayed edges and ragged tips (alpha cutout), covered bases darker (AO).
   Undersides ('_u' slots) paler satin grey.  Hackles: lanceolate spears with a strong rachis ridge and jagged edges;
   nasal bristles: 5 hair strands (alpha).
3. EYE (T_RavenEye_BaseColor, 1024): azimuthal equidistant around the front pole (raven_stage_a.eye_mesh: r = 0.5 *
   angle / pi): dark umber iris to 0.003 beyond the edge of the opening (eye_opening(): 48 deg = r 0.133 = rho
   4.8 mm on the 6.5 mm ball, so the whole 10 mm opening is iris) with a dark limbal ring under the lid edge, a faint
   pupil, dark beyond.

Normal maps are tangent space (OpenGL +Y = +v), built in the UV frame (MikkTSpace tangent = dP/du): the body by
finite differences of the 3D height field along each texel's tangent / bitangent, the feathers by image-space
gradients of the slot height field scaled to the slot's physical size.

Writes (tex-dir), as tools/dog/dog_textures.py: T_Raven_{BaseColor, Normal, Roughness, AO, MaskMap (HDRP: R metal,
G AO, B detail mask, A smoothness), MetallicSmoothness (URP / Standard: R metal, A smoothness), SpecularSmoothness
(Standard Specular setup / URP Specular workflow: RGB = the tinted F0 of spec 5.2, A smoothness)}; the same six for
T_Raven_Feather_* (BaseColor is RGBA: A = cutout, threshold 0.5); T_RavenEye_BaseColor; uv_hash.txt (the LOD0 UVs the
textures were painted for).  Then opens stage B and builds the three materials M_Raven_Body, M_Raven_Feather (image
alpha -> Math ROUND -> Principled Alpha: glTF alphaMode MASK, cutoff 0.5; Cycles renders the cutout), M_Raven_Eye
(glossy coat), same node layout as the dog (AO image node unconnected: the exporter links it to the glTF occlusion).
--relink-only rebuilds stage C from the PNGs already in --tex-dir (for build_all --skip-textures; the LOD0 UV hash
must match).

Unity (for the setup script): feathers = Cutout / Alpha Clipping at 0.5, single-sided (the strips are closed: top and
bottom sheets with their own slots), albedo alpha = cutout; set the feather BaseColor importer's
mipMapsPreserveCoverage = true (alphaTestReferenceValue 0.5) so the fray does not erode at distance.
"""
import argparse, hashlib, math, os, sys, time, zlib
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
os.environ.setdefault("ASSET", "raven")
import asset_profile as AP                                 # noqa: E402
import raven_anatomy as A                                  # noqa: E402 (adds tools/dog for sdf)
import feathers as FT                                      # noqa: E402
import plumage as PL                                       # noqa: E402

TEX, TEX_EYE = AP.TEX, AP.TEX_EYE                          # T_Raven, T_RavenEye
TEX_F = TEX + "_Feather"
PART = dict(plumage=0, mouth=1, bill=2, leg=3, claw=4, eye=5, feather=6, feather_under=7)
MAT_BODY, MAT_FEATHER, MAT_EYE = 0, 1, 2


def log(*a):
    print("[textures]", *a, flush=True)


def srgb2lin(c):
    c = np.asarray(c, dtype=np.float32) / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4).astype(np.float32)


def lin2srgb(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)


def sstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def unit_rows(v):
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-12)


# ------------------------------------------------------------------------------------------------ noise
_PERM = np.random.RandomState(11).permutation(1 << 16).astype(np.int64)


def _hash(ix, iy, iz):
    h = (ix * 73856093) ^ (iy * 19349663) ^ (iz * 83492791)
    return _PERM[h & 0xFFFF].astype(np.float32) / 65535.0


def hash1(i, salt=0):
    """random [0, 1] per integer (array)"""
    i = np.asarray(i, np.int64)
    return _PERM[((i * 2654435761) ^ (salt * 40503 + 977)) & 0xFFFF].astype(np.float32) / 65535.0


def vnoise(P):
    """value noise in [0, 1] at points P (N, 3) (1 unit = 1 cell)"""
    fl = np.floor(P); f = (P - fl).astype(np.float32)
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


def fbm(P, octaves=3, lac=2.0, gain=0.5):
    a, s, tot, out = 1.0, 1.0, 0.0, 0.0
    for _ in range(octaves):
        out = out + a * vnoise(P * s + 17.3 * s)
        tot += a; a *= gain; s *= lac
    return out / tot


def noise1(x, salt=0):
    """smooth 1D value noise in [0, 1]"""
    i = np.floor(x).astype(np.int64); f = (x - i).astype(np.float32)
    f = f * f * (3 - 2 * f)
    return hash1(i, salt) * (1 - f) + hash1(i + 1, salt) * f


def worley(P, cell, salt=0):
    """F1, F2 distances (in cells) of a jittered 3D grid"""
    Q = P / cell
    i = np.floor(Q).astype(np.int64)
    d1 = np.full(len(P), 9.0, np.float32); d2 = np.full(len(P), 9.0, np.float32)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for dz in (-1, 0, 1):
                c = i + np.array([dx, dy, dz])
                j = np.stack([_hash(c[:, 0] + 7 * salt, c[:, 1], c[:, 2]), _hash(c[:, 0], c[:, 1] + 13, c[:, 2] + salt),
                              _hash(c[:, 0] + 29, c[:, 1] + salt, c[:, 2] + 5)], 1)
                d = np.linalg.norm(Q - (c + 0.1 + 0.8 * j), axis=1).astype(np.float32)
                d2 = np.where(d < d1, d1, np.minimum(d2, d)); d1 = np.minimum(d1, d)
    return d1, d2


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


def dilate(img, filled):
    """fill every empty texel with its nearest filled texel (seams / mip padding)"""
    from scipy import ndimage
    _, (iy, ix) = ndimage.distance_transform_edt(~filled, return_indices=True)
    return img[iy, ix]


# ================================================================================================ BODY
# colours (sRGB; spec 5.2 metallic fallback) and smoothness
C = dict(
    head=(60, 57, 67), lores=(50, 49, 55), throat=(34, 33, 38), neck=(56, 54, 62), mantle=(52, 50, 58),
    breast=(51, 46, 41), rump=(50, 48, 55), undertail=(44, 42, 42), wing=(41, 42, 52), thigh=(44, 42, 42),
    ring=(92, 92, 96), ring_hi=(140, 140, 146), socket=(20, 19, 21),
    bill=(60, 59, 58), bill_tip=(112, 111, 107), bill_speck=(140, 139, 136), tomium=(74, 73, 71),
    flange=(104, 102, 99), mouth=(30, 29, 33), mouth_edge=(70, 70, 73),
    scute=(78, 77, 79), scute_edge=(112, 111, 113), crevice=(28, 28, 31),
    claw=(40, 38, 37), claw_tip=(62, 58, 54))
SMOOTH = dict(head=0.42, lores=0.35, throat=0.50, neck=0.45, mantle=0.55, breast=0.32, rump=0.52, undertail=0.30,
              wing=0.60, thigh=0.30)
# Specular-setup F0 (sRGB) per region (spec 5.2)
F0 = dict(violet=(58, 52, 70), blue=(52, 54, 74), neutral=(56, 56, 56), hackle=(56, 54, 66), tail=(54, 55, 62),
          under=(56, 56, 58))
# feather scale per region: exposed size r (m), lanceolate tip, outline darkening, tone contrast, relief (x r)
SCALE = dict(head=(0.0035, 0, 0.04, 0.05, 0.006), lores=(0.0025, 0, 0.03, 0.04, 0.004),
             throat=(0.0045, 1, 0.20, 0.20, 0.020), neck=(0.0065, 0, 0.10, 0.10, 0.018),
             mantle=(0.016, 0, 0.22, 0.14, 0.026), breast=(0.009, 0, 0.10, 0.12, 0.024),
             rump=(0.013, 0, 0.20, 0.12, 0.026), undertail=(0.012, 1, 0.10, 0.12, 0.024),
             wing=(0.008, 0, 0.18, 0.12, 0.024), thigh=(0.011, 1, 0.10, 0.12, 0.024))
KEYS = list(SCALE.keys())
# bone regions of the skin weights
REG = ("head", "throat", "neck", "trunk", "rump", "wing", "thigh", "foot")


def bone_region(b):
    if b in ("Head", "Jaw") or b.startswith(("Eye", "Lid")):
        return 0
    if b == "Throat":
        return 1
    if b.startswith("Neck"):
        return 2
    if b in ("Root", "Hips", "Spine1", "Spine2"):
        return 3
    if b in ("TailBase", "Tail") or b.startswith("Rect"):
        return 4
    if b.startswith(("Shoulder", "UpperArm", "Forearm", "Hand", "Alula", "Prim", "Sec", "Tert")):
        return 5
    if b.startswith(("Thigh", "Shin")):
        return 6
    return 7


FLOW = {"head": (0, 1, -0.15), "throat": (0, 0.52, -0.84), "neck": (0, 0.89, -0.45), "dorsal": tuple(A.U_WING),
        "ventral": (0, 0.35, -0.94), "rump": tuple(A.TAIL_DIR), "wing": tuple(A.U_WING), "thigh": (0, 0.15, -1),
        "foot": (0, 0.05, -1)}


def region_mix(P, N, R):
    """per-point weights of the paint regions (KEYS order) and the feather flow direction.
    R (n, 8) bone-region weights (REG order)."""
    n = len(P)
    dors = sstep(-0.15, 0.35, N @ A.N_WING).astype(np.float32)
    W = np.zeros((n, len(KEYS)), np.float32)
    k = {key: i for i, key in enumerate(KEYS)}
    W[:, k["head"]] = R[:, 0]
    W[:, k["throat"]] = R[:, 1]
    W[:, k["neck"]] = R[:, 2]
    W[:, k["mantle"]] = R[:, 3] * dors
    W[:, k["breast"]] = R[:, 3] * (1 - dors)
    W[:, k["rump"]] = R[:, 4] * dors
    W[:, k["undertail"]] = R[:, 4] * (1 - dors)
    W[:, k["wing"]] = R[:, 5]
    W[:, k["thigh"]] = R[:, 6] + R[:, 7]
    # lores / around the eye (a darker mask) inside the head
    lo = np.zeros(n, np.float32)
    for s in "LR":
        c, _ = A.eye_frame(s)
        d_eye = np.linalg.norm(P - c, axis=1)
        sx = 1.0 if s == "L" else -1.0
        d_lore = np.linalg.norm((P - np.array([sx * 0.012, -0.245, 0.351])) / np.array([0.010, 0.011, 0.008]), axis=1)
        lo = np.maximum(lo, np.maximum(sstep(0.0125, 0.0085, d_eye), sstep(1.2, 0.8, d_lore)))
    moved = W[:, k["head"]] * lo
    W[:, k["head"]] -= moved; W[:, k["lores"]] += moved
    W /= np.maximum(W.sum(1, keepdims=True), 1e-6)
    # flow
    Dv = (R[:, 0:1] * np.array(FLOW["head"]) + R[:, 1:2] * np.array(FLOW["throat"]) + R[:, 2:3] * np.array(FLOW["neck"])
          + R[:, 3:4] * (dors[:, None] * np.array(FLOW["dorsal"]) + (1 - dors[:, None]) * np.array(FLOW["ventral"]))
          + R[:, 4:5] * np.array(FLOW["rump"]) + R[:, 5:6] * np.array(FLOW["wing"])
          + R[:, 6:7] * np.array(FLOW["thigh"]) + R[:, 7:8] * np.array(FLOW["foot"]))
    Dv = unit_rows(Dv)
    for s in "LR":                                   # radiating around the eye
        c, _ = A.eye_frame(s)
        rad = unit_rows(P - c)
        wr = sstep(0.013, 0.007, np.linalg.norm(P - c, axis=1))[:, None]
        Dv = unit_rows(Dv * (1 - wr) + rad * wr)
    # belly: larger, fluffier feathers low on the trunk
    return W, Dv.astype(np.float32), dors


def region_params(W, P):
    """blend the per-region tables: albedo (lin), smoothness, scale r, lance, outline dark, contrast, relief, F0"""
    col = np.zeros((len(W), 3), np.float32); sm = np.zeros(len(W), np.float32)
    lr = np.zeros(len(W), np.float32); lance = np.zeros(len(W), np.float32)
    edk = np.zeros(len(W), np.float32); con = np.zeros(len(W), np.float32); rel = np.zeros(len(W), np.float32)
    f0 = np.zeros((len(W), 3), np.float32)
    f0map = dict(head="violet", lores="violet", throat="hackle", neck="violet", mantle="violet", breast="neutral",
                 rump="violet", undertail="neutral", wing="blue", thigh="neutral")
    for i, key in enumerate(KEYS):
        w = W[:, i]
        col += w[:, None] * srgb2lin(C[key])[None]
        sm += w * SMOOTH[key]
        r, la, ed, co, re = SCALE[key]
        if key == "breast":                         # belly: larger, fluffier
            r = r + 0.003 * sstep(0.19, 0.12, P[:, 2])
        lr += w * np.log(r); lance += w * la; edk += w * ed; con += w * co; rel += w * re
        f0 += w[:, None] * srgb2lin(F0[f0map[key]])[None]
    return dict(col=col, sm=sm, r=np.exp(lr).astype(np.float32), lance=lance > 0.5, edk=edk, con=con, rel=rel, f0=f0)


def make_seeds(V, F, fsel, Nv, Rv, rng):
    """Poisson-disk feather seeds on the plumage faces fsel (variable radius from the region scale)"""
    from scipy.spatial import cKDTree
    Fs = F[fsel]
    a = np.linalg.norm(np.cross(V[Fs[:, 1]] - V[Fs[:, 0]], V[Fs[:, 2]] - V[Fs[:, 0]]), axis=1) * 0.5
    M0 = 600_000
    fi = rng.choice(len(Fs), M0, p=a / a.sum())
    r1, r2 = rng.rand(M0), rng.rand(M0)
    s = np.sqrt(r1)
    b = np.stack([1 - s, s * (1 - r2), s * r2], 1)
    P = (V[Fs[fi]] * b[..., None]).sum(1)
    N = unit_rows((Nv[Fs[fi]] * b[..., None]).sum(1))
    R = (Rv[Fs[fi]] * b[..., None]).sum(1)
    W, _, _ = region_mix(P, N, R)
    prm = region_params(W, P)
    r = prm["r"]
    keep = rng.rand(M0) < (r.min() / r) ** 2
    P, r, lance = P[keep], r[keep], prm["lance"][keep]
    tree = cKDTree(P)
    nb = tree.query_ball_point(P, 0.9 * r)
    alive = np.ones(len(P), bool); acc = []
    for i in rng.permutation(len(P)):
        if alive[i]:
            acc.append(i)
            alive[nb[i]] = False
    acc = np.array(acc)
    return dict(c=P[acc].astype(np.float32), r=r[acc], lance=lance[acc], rnd=rng.rand(len(acc)).astype(np.float32),
                rnd2=rng.rand(len(acc)).astype(np.float32))


def scallop(P, D, Q, idx, S):
    """the visible feather at each point among the candidate seeds idx (n, K): local (a, b) in feather units
    (a along the flow: -1 root side .. 1 tip; b across), rho (outline = 1), seed id, r"""
    Cc = S["c"][idx]
    rel = P[:, None, :] - Cc
    r = S["r"][idx]
    a = np.einsum("nkj,nj->nk", rel, D) / (1.25 * r)
    b = np.einsum("nkj,nj->nk", rel, Q) / (0.80 * r)
    ap = np.clip(a, 0, 1)
    w = np.where(S["lance"][idx], (1 - ap) ** 0.85, np.sqrt(np.clip(1 - ap * ap, 0, 1)))
    rho = np.abs(b) / np.maximum(w, 1e-3)
    cov = (rho < 1) & (a > -1.6) & (a < 1)
    key = np.where(cov, a, -9.0)
    j = key.argmax(1)
    rows = np.arange(len(P))
    return idx[rows, j], a[rows, j], b[rows, j], np.where(cov[rows, j], rho[rows, j], 1.2), r[rows, j]


def feather_height(a, b, rho, r, sid, S, fade, texel):
    """relief of the plumage scales, 0..~1.2 (x relief * r metres): rising toward each feather's tip, bevelled at
    its outline (over >= 2.5 texels, so the outline never becomes a one-texel crack), a rachis ridge on the larger
    feathers, barb striations (faded out when finer than the texel)"""
    base = 0.2 + 0.8 * np.clip((a + 0.3) / 1.3, 0, 1)
    bw = np.clip(2.5 * texel / (0.8 * r), 0.2, 0.6)
    bev = sstep(1 - bw, 1.0, rho)
    h = base * (1 - bev) + 0.2 * bev
    bm = b * 0.80 * r
    ridge = np.exp(-(bm / 0.00045) ** 2) * sstep(0.006, 0.010, r) * (a > -0.8)
    am = a * 1.25 * r
    phase = (am - np.abs(bm) * 1.43) / 0.0008 + S["rnd2"][sid] * 7
    barbs = np.cos(2 * np.pi * phase) * fade
    return h + 0.12 * ridge + 0.05 * barbs, barbs


def eye_opening():
    """angle (rad) from the eye axis at which the lid / socket wall first covers the eyeball: the edge of the visible
    iris (measured on the SDF, so the ring and the iris follow the anatomy)"""
    from sdf import eval_prims
    prims = [p for p in A.body_prims() + A.eye_socket_prims() if p.tag not in ("bill", "bill_low")]
    c, n = A.eye_frame("L")
    x = np.cross([0, 0, 1.0], n); x /= np.linalg.norm(x); y = np.cross(n, x)
    ph = np.linspace(0, 2 * np.pi, 16, endpoint=False)
    for th in np.radians(np.arange(20.0, 90.0, 0.5)):
        d = n * np.cos(th) + (np.outer(np.cos(ph), x) + np.outer(np.sin(ph), y)) * np.sin(th)
        if np.median(eval_prims(prims, c + d * A.EYE_R)) < 0:
            return th
    return np.radians(48.0)


def eye_ring(P, rho_open):
    """eyelid ring mask, bead field, socket mask.  The ring (spec 3.3: pale, beaded, 2-3 mm wide, outer diameter
    0.016) covers the raised lid margin of raven_anatomy (a torus of radius LID_R at LID_T along the eye axis) and the
    socket wall from the edge of the opening (rho_open) outward."""
    ring = np.zeros(len(P), np.float32); bead = np.zeros(len(P), np.float32); sock = np.zeros(len(P), np.float32)
    hb = np.zeros(len(P), np.float32)
    lid_r = getattr(A, "LID_R", 0.0062)
    r_in, r_out = rho_open - 0.0008, max(lid_r + 0.0020, rho_open + 0.0026)
    for s in "LR":
        c, n = A.eye_frame(s)
        rel = P - c
        al = rel @ n
        perp = rel - np.outer(al, n)
        rho = np.linalg.norm(perp, axis=1)
        front = sstep(-0.0030, -0.0010, al)
        e1 = np.cross([0, 0, 1.0], n); e1 /= np.linalg.norm(e1); e2 = np.cross(n, e1)
        ang = np.arctan2(perp @ e2, perp @ e1)
        rg = sstep(r_in, r_in + 0.0004, rho) * sstep(r_out + 0.0004, r_out - 0.0002, rho) * front
        nb = int(round(2 * np.pi * lid_r / 0.0009))                   # beads 0.9 mm apart on the crest
        bd = (0.5 + 0.5 * np.cos(ang * nb)) * np.clip(1 - ((rho - lid_r) / 0.0014) ** 2, 0, 1)
        ring = np.maximum(ring, rg); bead = np.maximum(bead, bd * rg)
        hb = np.maximum(hb, rg * (0.5 + 0.5 * bd))
        sock = np.maximum(sock, sstep(r_in + 0.0002, r_in - 0.0002, rho) * front)
    return ring, bead, sock, hb


def paint_body(P, N, Tp, Bn, part, R, dom, texel, AOg, S, tree, bones, heads, tails, rho_open, K=10):
    """P, N, Tp, Bn (n, 3); part (n,); R (n, 8) bone regions; dom (n,) dominant bone index; texel (n,) texel size (m);
    AOg (n,) geometric AO.  Returns linear albedo (n, 3), roughness, normal (n, 3), AO, F0 (n, 3)."""
    n = len(P)
    W, D, dors = region_mix(P, N, R)
    prm = region_params(W, P)
    D = D - N * (D * N).sum(1, keepdims=True)
    bad = np.linalg.norm(D, axis=1) < 1e-3
    if bad.any():
        D[bad] = np.cross(N[bad], [1.0, 0, 0])
    D = unit_rows(D); Q = np.cross(N, D)
    _, idx = tree.query(P, k=K, workers=2)
    dl = np.maximum(0.6 * texel, 0.00008)[:, None]
    fade = np.clip(1 - 2.2 * (texel / 0.0008), 0, 1) ** 2
    sid, a, b, rho, r = scallop(P, D, Q, idx, S)
    h, barbs = feather_height(a, b, rho, r, sid, S, fade, texel)
    sT = scallop(P + Tp * dl, D, Q, idx, S); hT, _ = feather_height(sT[1], sT[2], sT[3], sT[4], sT[0], S, fade, texel)
    sB = scallop(P + Bn * dl, D, Q, idx, S); hB, _ = feather_height(sB[1], sB[2], sB[3], sB[4], sB[0], S, fade, texel)
    amp = prm["rel"] * r
    dx = (hT - h) * amp / dl[:, 0]; dy = (hB - h) * amp / dl[:, 0]
    # barb streaks along the flow (1.2 mm across, 5 mm along): the feathery sheen that survives the mips
    def streak(X):
        s_ = (X * D).sum(1, keepdims=True)
        return fbm((X - D * s_) / 0.0012 + D * s_ / 0.005 + 3.7, 2)
    st0 = streak(P)
    dx = dx + (streak(P + Tp * dl) - st0) * 0.00005 / dl[:, 0]
    dy = dy + (streak(P + Bn * dl) - st0) * 0.00005 / dl[:, 0]
    # plumage colour: region albedo x per-feather tone x outline darkening x barbs; soft large-scale variation
    noise = fbm(P / 0.012, 3)
    tone = 1 + prm["con"] * 2.0 * (S["rnd"][sid] - 0.5)
    edge = 1 - prm["edk"] * sstep(0.70, 1.0, rho) * (a > -0.2)
    col = prm["col"] * (tone * edge * (0.92 + 0.16 * noise) * (1 + 0.06 * barbs) * (0.94 + 0.12 * st0))[:, None]
    rough = 1 - prm["sm"] + 0.10 * sstep(0.75, 1.0, rho) - 0.04 * (1 - rho).clip(0, 1) + 0.04 * (noise - 0.5)
    ao_micro = 1 - (0.04 + 0.43 * sstep(4, 14, r * 1000)) * (1 - sstep(0.2, 0.55, h))   # crevices: faint on the head
    f0 = prm["f0"]
    # the eyelid ring and the socket
    ring, bead, sock, hb = eye_ring(P, rho_open)
    pl = part == PART["plumage"]
    ring *= pl; sock *= pl
    rc = srgb2lin(C["ring"])[None] * (1 - bead[:, None]) + srgb2lin(C["ring_hi"])[None] * bead[:, None]
    col = col * (1 - ring[:, None]) + rc * ring[:, None]
    col = col * (1 - sock[:, None]) + srgb2lin(C["socket"])[None] * sock[:, None]
    rough = rough * (1 - ring) + 0.20 * ring
    f0 = f0 * (1 - ring[:, None]) + srgb2lin(F0["neutral"])[None] * ring[:, None]
    # ring relief: finite differences of the bead field
    _, _, _, hbT = eye_ring(P + Tp * dl, rho_open); _, _, _, hbB = eye_ring(P + Bn * dl, rho_open)
    dx = dx * (1 - ring) + (hbT - hb) * 0.00015 / dl[:, 0]
    dy = dy * (1 - ring) + (hbB - hb) * 0.00015 / dl[:, 0]
    ao_micro = ao_micro * (1 - ring) + ring
    AOg = np.maximum(AOg, 0.85 * ring)                 # the lid margin in the socket stays pale

    # ---- bill
    bill = part == PART["bill"]
    if bill.any():
        Pb = P[bill]
        ax = A.J["billtip"] - A.J["billbase"]; ax = ax / np.linalg.norm(ax)
        d_tip = np.minimum(np.linalg.norm(Pb - A.J["billtip"], axis=1), np.linalg.norm(Pb - A.J["jawtip"], axis=1))
        tipm = sstep(0.030, 0.012, d_tip)

        e1 = np.cross(ax, [1.0, 0, 0]); e1 /= np.linalg.norm(e1)

        def grain(X):                                   # ridges along the bill: long along the axis, 1.1 mm across
            along = X @ ax
            g = fbm(np.c_[X[:, 0] / 0.0011, (X @ e1) / 0.0011, along / 0.010], 2)
            pit = fbm(X / 0.0003 + 5.1, 2)
            return (0.8 * g + 0.25 * pit) * (1 - 0.7 * sstep(0.022, 0.010, np.minimum(
                np.linalg.norm(X - A.J["billtip"], axis=1), np.linalg.norm(X - A.J["jawtip"], axis=1))))
        g0 = grain(Pb); gT = grain(Pb + Tp[bill] * dl[bill]); gB = grain(Pb + Bn[bill] * dl[bill])
        dx[bill] = (gT - g0) * 0.00004 / dl[bill, 0]; dy[bill] = (gB - g0) * 0.00004 / dl[bill, 0]
        c = srgb2lin(C["bill"])[None] * (1 - tipm[:, None]) + srgb2lin(C["bill_tip"])[None] * tipm[:, None]
        c = c * (0.90 + 0.2 * g0[:, None])
        speck = sstep(0.80, 0.86, fbm(Pb / 0.0007 + 3.3, 2)) * tipm
        c = c * (1 - speck[:, None]) + srgb2lin(C["bill_speck"])[None] * speck[:, None]
        tom = sstep(0.0008, 0.0004, np.abs(Pb[:, 2] - A.gape_z(Pb[:, 1]))) * (Pb[:, 1] < -0.240) * 0.7
        c = c * (1 - tom[:, None]) + srgb2lin(C["tomium"])[None] * tom[:, None]
        col[bill] = c
        rough[bill] = 0.50 + 0.15 * tipm - 0.05 * tom
        ao_micro[bill] = 1.0
        f0[bill] = srgb2lin(F0["neutral"])[None]
    # gape flange at the rictus (bill and the plumage next to it)
    fl = np.zeros(n, np.float32)
    for s_ in "LR":
        fl = np.maximum(fl, sstep(0.0045, 0.0025, np.linalg.norm(P - A.side("rictus", s_), axis=1)))
    fl *= (part != PART["mouth"])
    col = col * (1 - fl[:, None]) + srgb2lin(C["flange"])[None] * fl[:, None]
    rough = rough * (1 - fl) + 0.55 * fl

    # ---- mouth interior
    mo = part == PART["mouth"]
    if mo.any():
        Pm = P[mo]
        col[mo] = srgb2lin(C["mouth"])[None] * (0.9 + 0.2 * fbm(Pm / 0.002, 2))[:, None]
        # smoothness 0.30 (spec 0.55-0.6): the cut walls of the gape are faceted, and a glossy dark wall catches the
        # sky at grazing angles like a row of teeth
        rough[mo] = 0.70; dx[mo] = 0; dy[mo] = 0; ao_micro[mo] = 0.6
        f0[mo] = srgb2lin(F0["neutral"])[None]

    # ---- bare legs: scutes
    lg = part == PART["leg"]
    if lg.any():
        Pl, Nl, dm = P[lg], N[lg], dom[lg]

        def scutes(X):
            hh = np.zeros(len(X), np.float32); crev = np.zeros(len(X), np.float32)
            d1, d2 = worley(X, 0.0015, 1)
            ret = sstep(0.02, 0.16, d2 - d1)                    # 0 in the crevices between reticulate scales
            hh = ret.copy(); crev = 1 - ret
            for bi in np.unique(dm):
                sel = dm == bi
                name = bones[bi]
                h0, t1 = heads[bi], tails[bi]
                axis = (t1 - h0) / max(np.linalg.norm(t1 - h0), 1e-9)
                s = (X[sel] - h0) @ axis
                if name.startswith("Tarsus"):
                    fr = np.array([0, -1.0, 0]) - axis * (-axis[1]); fr /= np.linalg.norm(fr)
                    front = sstep(0.05, 0.45, Nl[sel] @ fr)
                    period = 0.0075
                elif name.startswith("Toe"):
                    front = sstep(0.05, 0.45, Nl[sel][:, 2])
                    period = 0.0040
                else:
                    continue
                g = np.mod(s / period, 1.0)
                plate = sstep(0.0, 0.10, g) * sstep(1.0, 0.90, g)
                ph = plate * (0.55 + 0.45 * g)                  # each plate overlaps the next toward the foot
                hh[sel] = hh[sel] * (1 - front) + ph * front
                crev[sel] = crev[sel] * (1 - front) + (1 - plate) * front
            return hh, crev
        h0, crev = scutes(Pl)
        hT0, _ = scutes(Pl + Tp[lg] * dl[lg]); hB0, _ = scutes(Pl + Bn[lg] * dl[lg])
        dx[lg] = (hT0 - h0) * 0.00025 / dl[lg, 0]; dy[lg] = (hB0 - h0) * 0.00025 / dl[lg, 0]
        nz = fbm(Pl / 0.004, 2)
        c = srgb2lin(C["scute"])[None] * (0.9 + 0.2 * nz[:, None])
        hi = sstep(0.75, 1.0, h0) * (1 - crev)
        c = c * (1 - hi[:, None] * 0.6) + srgb2lin(C["scute_edge"])[None] * (hi[:, None] * 0.6)
        c = c * (1 - crev[:, None]) + srgb2lin(C["crevice"])[None] * crev[:, None]
        col[lg] = c
        rough[lg] = 0.50 + 0.20 * crev
        ao_micro[lg] = 1 - 0.45 * crev
        f0[lg] = srgb2lin(F0["neutral"])[None]

    # ---- claws
    cl = part == PART["claw"]
    if cl.any():
        Pc = P[cl]
        tips = []
        for toe, (pts, tip) in A.TOES.items():
            tips += [tip, A.mirror(tip)]
        dt = np.min(np.stack([np.linalg.norm(Pc - t, axis=1) for t in tips], 1), axis=1)
        tipm = sstep(0.007, 0.0015, dt)
        col[cl] = srgb2lin(C["claw"])[None] * (1 - tipm[:, None]) + srgb2lin(C["claw_tip"])[None] * tipm[:, None]
        rough[cl] = 0.38; dx[cl] = 0; dy[cl] = 0; ao_micro[cl] = 1.0
        f0[cl] = srgb2lin(F0["neutral"])[None]

    v3 = np.stack([-dx, -dy, np.ones_like(dx)], axis=1)
    nrm = unit_rows(v3)
    AO = np.clip(AOg * ao_micro, 0, 1)
    return col.astype(np.float32), np.clip(rough, 0.03, 1).astype(np.float32), nrm.astype(np.float32), \
        AO.astype(np.float32), f0.astype(np.float32)


def vertex_ao(V, F, Nv, verts, maxd=0.025, nray=16, seed=5):
    """ray-cast occlusion at the vertices `verts` against the whole LOD0 (body + feather strips, bind pose)"""
    import bpy  # noqa: F401  (mathutils comes with the bpy module)
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    bvh = BVHTree.FromPolygons([tuple(v) for v in V.astype(float)], [tuple(int(i) for i in f) for f in F],
                               all_triangles=True)
    rng = np.random.RandomState(seed)
    # cosine-weighted hemisphere directions (local z = normal)
    u1, u2 = rng.rand(nray), rng.rand(nray)
    rr = np.sqrt(u1); th = 2 * np.pi * u2
    loc = np.stack([rr * np.cos(th), rr * np.sin(th), np.sqrt(1 - u1)], 1)
    ao = np.ones(len(V), np.float32)
    for vi in verts:
        n = Nv[vi]
        t = np.cross(n, [0, 0, 1.0]) if abs(n[2]) < 0.9 else np.cross(n, [1.0, 0, 0])
        t /= np.linalg.norm(t); bt = np.cross(n, t)
        dirs = loc[:, 0:1] * t + loc[:, 1:2] * bt + loc[:, 2:3] * n
        o = Vector(V[vi] + n * 0.0004)
        occ = 0.0
        for d in dirs:
            hit = bvh.ray_cast(o, Vector(d), maxd)
            if hit[0] is not None:
                occ += 1.0 - 0.6 * hit[3] / maxd
        ao[vi] = 1 - 0.85 * occ / nray
    return np.clip(ao, 0.2, 1)


def body_textures(D, res, tex_dir, t0, rho_open):
    from scipy.spatial import cKDTree
    V, F, UV, part, mat = D["v0"], D["f0"], D["uv0"], D["part0"], D["mat0"]
    bones = [str(b) for b in D["bones"]]
    heads, tails = D["heads"], D["tails"]
    wi, ww = D["wi0"], D["ww0"]
    fb = np.nonzero(mat == MAT_BODY)[0]
    # vertex normals (area weighted, body faces)
    fn = np.cross(V[F[fb, 1]] - V[F[fb, 0]], V[F[fb, 2]] - V[F[fb, 0]])
    Nv = np.zeros_like(V)
    for k in range(3):
        np.add.at(Nv, F[fb, k], fn)
    Nv = unit_rows(Nv)
    reg = np.array([bone_region(b) for b in bones])
    Rv = np.zeros((len(V), len(REG)), np.float32)
    for k in range(4):
        np.add.at(Rv, (np.arange(len(V)), reg[wi[:, k]]), ww[:, k])
    Rv /= np.maximum(Rv.sum(1, keepdims=True), 1e-6)
    dom_v = wi[np.arange(len(V)), ww.argmax(1)]
    bverts = np.unique(F[fb])
    ao_v = vertex_ao(V, F, Nv, bverts)
    log(f"body vertex AO: {len(bverts)} vertices, mean {ao_v[bverts].mean():.2f} ({time.time() - t0:.0f} s)")
    rng = np.random.RandomState(21)
    S = make_seeds(V, F, fb[part[fb] == PART["plumage"]], Nv, Rv, rng)
    tree = cKDTree(S["c"])
    log(f"feather seeds: {len(S['c'])} (r {S['r'].min() * 1000:.1f}-{S['r'].max() * 1000:.1f} mm) "
        f"({time.time() - t0:.0f} s)")
    tri, bar = rasterize(UV[fb], res)
    filled = tri >= 0
    log(f"rasterised {filled.mean() * 100:.1f} % of {res}^2 ({time.time() - t0:.0f} s)")
    ty, tx = np.nonzero(filled)
    tl = fb[tri[ty, tx]]
    bb = bar[ty, tx]
    del bar, tri
    # per-face tangent frame and texel size
    e1 = V[F[:, 1]] - V[F[:, 0]]; e2 = V[F[:, 2]] - V[F[:, 0]]
    d1 = UV[:, 1] - UV[:, 0]; d2 = UV[:, 2] - UV[:, 0]
    det = d1[:, 0] * d2[:, 1] - d2[:, 0] * d1[:, 1]
    det = np.where(np.abs(det) < 1e-12, 1e-12, det)
    Tt = (e1 * d2[:, 1:2] - e2 * d1[:, 1:2]) / det[:, None]
    Bt = (e2 * d1[:, 0:1] - e1 * d2[:, 0:1]) / det[:, None]
    A3 = 0.5 * np.linalg.norm(np.cross(e1, e2), axis=1)
    tex_f = np.sqrt(A3 / np.maximum(0.5 * np.abs(det), 1e-14)) / res
    n = len(tl)
    base = np.zeros((n, 3), np.float32); rough = np.zeros(n, np.float32); nrm = np.zeros((n, 3), np.float32)
    aot = np.zeros(n, np.float32); f0 = np.zeros((n, 3), np.float32)
    CH = 400_000
    for s in range(0, n, CH):
        sl = slice(s, s + CH)
        Fv = F[tl[sl]]; b = bb[sl]
        P = (V[Fv] * b[..., None]).sum(1)
        N = unit_rows((Nv[Fv] * b[..., None]).sum(1))
        R = (Rv[Fv] * b[..., None]).sum(1)
        AOg = (ao_v[Fv] * b).sum(1)
        dom = dom_v[Fv[np.arange(len(Fv)), b.argmax(1)]]
        Tp = Tt[tl[sl]]; Bp = Bt[tl[sl]]
        Tp = unit_rows(Tp - N * (Tp * N).sum(1, keepdims=True))
        sgn = np.sign((np.cross(N, Tp) * Bp).sum(1)); sgn[sgn == 0] = 1
        Bn = np.cross(N, Tp) * sgn[:, None]
        col, ro, nm, ao, ff = paint_body(P, N, Tp, Bn, part[tl[sl]], R, dom, tex_f[tl[sl]], AOg, S, tree, bones,
                                         heads, tails, rho_open)
        base[sl] = col * (0.55 + 0.45 * ao)[:, None]
        rough[sl] = ro; nrm[sl] = nm; aot[sl] = ao; f0[sl] = ff
        log(f"  painted {min(s + CH, n)}/{n} ({time.time() - t0:.0f} s)")

    def to_img(vals, ch, fill):
        img = np.zeros((res, res, ch), np.float32); img[:] = fill
        img[ty, tx] = vals.reshape(n, ch)
        return dilate(img, filled)
    return write_set(tex_dir, TEX, to_img(base, 3, 0), None, to_img(nrm, 3, 0), to_img(rough, 1, 0.6)[..., 0],
                     to_img(aot, 1, 1)[..., 0], to_img(f0, 3, 0.04))


def write_set(tex_dir, prefix, base_lin, alpha, nrm, rough, ao, f0_lin):
    from PIL import Image
    os.makedirs(tex_dir, exist_ok=True)
    bc = (lin2srgb(base_lin) * 255 + 0.5).astype(np.uint8)
    if alpha is not None:
        bc = np.dstack([bc, (np.clip(alpha, 0, 1) * 255 + 0.5).astype(np.uint8)])
        Image.fromarray(bc, "RGBA").save(os.path.join(tex_dir, prefix + "_BaseColor.png"))
    else:
        Image.fromarray(bc).save(os.path.join(tex_dir, prefix + "_BaseColor.png"))
    nm = np.clip(nrm * 0.5 + 0.5, 0, 1)
    Image.fromarray((nm * 255 + 0.5).astype(np.uint8)).save(os.path.join(tex_dir, prefix + "_Normal.png"))
    Image.fromarray((np.clip(rough, 0, 1) * 255 + 0.5).astype(np.uint8)).save(os.path.join(tex_dir, prefix + "_Roughness.png"))
    Image.fromarray((np.clip(ao, 0, 1) * 255 + 0.5).astype(np.uint8)).save(os.path.join(tex_dir, prefix + "_AO.png"))
    sm = 1 - np.clip(rough, 0, 1)
    z = np.zeros_like(sm)
    mask = np.stack([z, np.clip(ao, 0, 1), z, sm], axis=-1)
    Image.fromarray((mask * 255 + 0.5).astype(np.uint8), "RGBA").save(os.path.join(tex_dir, prefix + "_MaskMap.png"))
    ms = np.stack([z, z, z, sm], axis=-1)
    Image.fromarray((ms * 255 + 0.5).astype(np.uint8), "RGBA").save(
        os.path.join(tex_dir, prefix + "_MetallicSmoothness.png"))
    sp = np.dstack([lin2srgb(f0_lin), sm])
    Image.fromarray((sp * 255 + 0.5).astype(np.uint8), "RGBA").save(
        os.path.join(tex_dir, prefix + "_SpecularSmoothness.png"))
    return bc


# ================================================================================================ FEATHERS
# per slot kind: vane albedo, rachis albedo, smoothness (vane / rachis), F0; underside ('_u') variants; barb angle
# (deg), barb spacing (m), rachis width base -> tip (m), rachis relief (m), split spacing (m), split depth, fray
FK = {
    "prim": dict(col=(39, 40, 50), rach=(96, 96, 100), sm=0.72, rsm=0.70, f0="blue", phi=25, sp=0.0008,
                 rw=(0.0022, 0.0006), rh=0.00030, split=(0.015, 0.040), depth=(0.50, 0.90), fray=0.06),
    "sec": dict(col=(39, 40, 50), rach=(74, 74, 78), sm=0.70, rsm=0.66, f0="blue", phi=28, sp=0.0008,
                rw=(0.0020, 0.0006), rh=0.00025, split=(0.015, 0.040), depth=(0.50, 0.90), fray=0.08),
    "tert": dict(col=(41, 42, 51), rach=(64, 64, 68), sm=0.68, rsm=0.62, f0="blue", phi=30, sp=0.0008,
                 rw=(0.0018, 0.0005), rh=0.00020, split=(0.015, 0.040), depth=(0.55, 0.90), fray=0.08),
    "rect": dict(col=(40, 41, 46), rach=(96, 96, 100), sm=0.62, rsm=0.68, f0="tail", phi=28, sp=0.0008,
                 rw=(0.0022, 0.0006), rh=0.00028, split=(0.012, 0.035), depth=(0.50, 0.90), fray=0.10, ragged=1),
    "gcov": dict(col=(41, 42, 52), rach=(62, 62, 66), sm=0.62, rsm=0.60, f0="blue", phi=35, sp=0.0007,
                 rw=(0.0010, 0.0003), rh=0.00012, split=(0.020, 0.050), depth=(0.60, 0.92), fray=0.08),
    "pcov": dict(col=(41, 42, 52), rach=(90, 90, 94), sm=0.62, rsm=0.66, f0="blue", phi=32, sp=0.0007,
                 rw=(0.0012, 0.0003), rh=0.00014, split=(0.020, 0.050), depth=(0.60, 0.92), fray=0.08),
    "mcov": dict(col=(42, 43, 52), rach=(58, 58, 62), sm=0.60, rsm=0.58, f0="blue", phi=38, sp=0.0007,
                 rw=(0.0008, 0.0003), rh=0.00010, split=(0.020, 0.050), depth=(0.65, 0.93), fray=0.10),
    "alula": dict(col=(41, 42, 52), rach=(80, 80, 84), sm=0.64, rsm=0.64, f0="blue", phi=30, sp=0.0007,
                  rw=(0.0010, 0.0003), rh=0.00012, split=(0.020, 0.050), depth=(0.65, 0.93), fray=0.06),
    "scap": dict(col=(53, 50, 59), rach=(60, 58, 64), sm=0.55, rsm=0.55, f0="violet", phi=40, sp=0.0008,
                 rw=(0.0010, 0.0003), rh=0.00010, split=(0.012, 0.030), depth=(0.60, 0.92), fray=0.14),
    "utc": dict(col=(50, 48, 56), rach=(58, 57, 62), sm=0.55, rsm=0.55, f0="violet", phi=40, sp=0.0008,
                rw=(0.0010, 0.0003), rh=0.00010, split=(0.012, 0.030), depth=(0.60, 0.92), fray=0.14),
    "hackle": dict(col=(53, 53, 57), rach=(66, 66, 70), sm=0.53, rsm=0.62, f0="hackle", phi=30, sp=0.0006,
                   rw=(0.0006, 0.0002), rh=0.00018, split=(0.003, 0.007), depth=(0.30, 0.70), fray=0.30, ragged=1),
    "ucov": dict(col=(46, 46, 50), rach=(60, 60, 64), sm=0.50, rsm=0.50, f0="under", phi=38, sp=0.0008,
                 rw=(0.0008, 0.0003), rh=0.00008, split=(0.020, 0.050), depth=(0.60, 0.92), fray=0.12),
    "bristle": dict(col=(50, 49, 54), rach=(50, 49, 54), sm=0.60, rsm=0.60, f0="neutral", phi=10, sp=0.0008,
                    rw=(0.0003, 0.0001), rh=0.0, split=(1, 1), depth=(1, 1), fray=0.0),
}
UNDER = dict(col=(58, 58, 62), sm=0.45, f0="under")                   # remiges / rectrices underside (satin grey)
UNDER_RACH = (128, 128, 132)
UNDER_COV = dict(col=(54, 54, 58), sm=0.48, f0="under")               # coverts underside (gcov_u)
FRAY_COL = (58, 58, 64)


def slot_cell(rect):
    """the full atlas cell (u0, v0, u1, v1) of a slot rectangle (column or quarter of a column)"""
    u0, v0, u1, v1 = rect
    cu0 = math.floor(u0 * 16 + 1e-6) / 16.0
    if (v1 - v0) < 0.2:
        cv0 = math.floor(v0 * 8 + 1e-6) / 8.0; cv1 = cv0 + 0.125
    else:
        cv0 = math.floor(v0 * 2 + 1e-6) / 2.0; cv1 = cv0 + 0.5
    return cu0, cv0, cu0 + 1 / 16.0, cv1


def slot_users(FE):
    name_of = {tuple(np.round(v, 9)): k for k, v in PL.SLOTS.items()}
    users = {k: [] for k in PL.SLOTS}
    for f in FE:
        users[name_of[tuple(np.round(f.slot, 9))]].append((f, False))
        users[name_of[tuple(np.round(f.slot_under, 9))]].append((f, True))
    return users


def envelope(users, t):
    """min left / max right u edge (0..1 across the slot) of every user's outline at t; median scale"""
    L, R, wm, ln, t0, outer_left = [], [], [], [], [], []
    for f, mirror in users:
        wl = np.maximum(FT.half_width(f, t, outer=(f.outer_sign < 0)), 0.0010)
        wr = np.maximum(FT.half_width(f, t, outer=(f.outer_sign > 0)), 0.0010)
        wmax = max(f.w_in, f.w_out, 1e-6)
        uL = 0.5 - 0.5 * wl / wmax; uR = 0.5 + 0.5 * wr / wmax
        ol = f.outer_sign < 0
        if mirror:
            uL, uR = 1 - uR, 1 - uL; ol = not ol
        L.append(uL); R.append(uR); wm.append(wmax); ln.append(f.length); t0.append(f.t0)
        if abs(f.w_in - f.w_out) > 1e-6:
            outer_left.append(ol)
    ol = np.mean(outer_left) if outer_left else 0.5
    return (np.min(L, 0), np.max(R, 0), float(np.median(wm)), float(np.median(ln)), float(np.median(t0)), ol)


def paint_slot(name, users, H, W, res):
    """one atlas cell (H x W texels): linear albedo, alpha, roughness, height (m), AO, F0; + the pixel sizes (m)"""
    kind = PL.SLOT_KIND[name]
    under = name.endswith("_u")
    k = FK[kind if kind in FK else "gcov"]
    rect = PL.SLOTS[name]
    cu0, cv0, cu1, cv1 = slot_cell(rect)
    u0, v0, u1, v1 = rect
    xs = cu0 + (np.arange(W) + 0.5) / res
    vs = cv1 - (np.arange(H) + 0.5) / res                       # row 0 = top of the cell = high v
    lu = np.clip((xs - u0) / (u1 - u0), 0, 1)[None, :].repeat(H, 0)
    lv = np.clip((vs - v0) / (v1 - v0), 0, 1)[:, None].repeat(W, 1)
    tg = np.linspace(0, 1, 257)
    envL, envR, wmax, L, t0, outer_left = envelope(users, tg)
    eL = np.interp(lv, tg, envL); eR = np.interp(lv, tg, envR)
    side = np.where(lu >= 0.5, 1, -1)
    half = np.where(side > 0, eR - 0.5, 0.5 - eL)
    xr = np.abs(lu - 0.5) / np.maximum(half, 1e-4)             # 0 rachis .. 1 the slot's widest outline
    x = (lu - 0.5) * 2 * wmax
    y = lv * L
    px_x = 2 * wmax / ((u1 - u0) * res); px_y = L / ((v1 - v0) * res)
    seed = zlib.crc32(name.encode()) % 997                    # deterministic (str hash() is salted)
    # outer (narrow, stiff) vane side of this slot's feathers: fewer splits and less fray there
    inner_side = np.where(side > 0, outer_left, 1 - outer_left)          # 1 = the wide inner vane
    inner_side = np.where(abs(outer_left - 0.5) < 0.3, 1.0, inner_side)  # mixed / symmetric slots: both vanes
    cot = 1 / math.tan(math.radians(k["phi"]))
    xw = np.abs(x)
    q = y - xw * cot                                          # barb coordinate (m): constant along a barb
    phase = q / k["sp"]
    f_px = math.hypot(cot * px_x / k["sp"], px_y / k["sp"])
    fade = max(0.0, 1 - 2.2 * f_px) ** 2
    barbs = np.cos(2 * np.pi * phase) * fade
    streak = noise1(q / (4.0 * k["sp"]) + 1000 * (side > 0), seed) * 0.6 + noise1(q / (13 * k["sp"]), seed + 1) * 0.4
    # rachis
    rw = (k["rw"][0] + (k["rw"][1] - k["rw"][0]) * lv) * 0.5
    rw = np.maximum(rw, 0.8 * px_x)
    rmask = sstep(1.0, 0.7, xw / rw)
    rheight = k["rh"] * np.sqrt(np.clip(1 - (xw / rw) ** 2, 0, 1))
    calamus = lv < t0
    # vane splits along the barbs (per side, random spacing / depth)
    rng = np.random.RandomState(seed)
    cut = np.zeros((H, W), bool)
    crease = np.zeros((H, W), np.float32)
    if kind != "bristle":
        for sd in (-1, 1):
            qs, depth = [], []
            yk = -L
            while yk < 2 * L:
                yk += rng.uniform(*k["split"]); qs.append(yk); depth.append(rng.uniform(*k["depth"]))
            qs = np.array(qs); depth = np.array(depth)
            sel = side == sd
            qq = q[sel]
            j = np.clip(np.searchsorted(qs, qq), 1, len(qs) - 1)
            jn = np.where(np.abs(qq - qs[j - 1]) < np.abs(qq - qs[j]), j - 1, j)
            dq = np.abs(qq - qs[jn]) * math.sin(math.radians(k["phi"]))
            dk = depth[jn]
            isd = inner_side[sel]
            dk = np.where(isd > 0.5, dk, 1 - 0.25 * (1 - dk))          # the outer vane: shallow nicks only
            xrs = xr[sel]
            gw = max(0.00030, 1.1 * min(px_x, px_y))
            open_ = (xrs > dk) & (dq < gw * (0.35 + 0.9 * (xrs - dk) / np.maximum(1 - dk, 1e-3)))
            cut[sel] = open_ & (lv[sel] > t0 + 0.05)
            crease[sel] = sstep(gw * 2.5, 0, dq) * sstep(dk - 0.25, dk, xrs) * (lv[sel] > t0 + 0.05)
    # frayed edges: barb clumps end at random widths; ragged tips
    spc = max(2 * k["sp"], 2.5 * px_y)
    kc = np.floor(q / spc).astype(np.int64) + 5000 * (side > 0)
    fr = k["fray"] * (0.6 + 0.4 * inner_side)
    xr_end = 1 - fr * hash1(kc, seed + 7) * (hash1(kc, seed) > 0.45)     # about half of the barb clumps frayed
    if k.get("ragged"):
        xr_end = xr_end - 0.20 * sstep(0.80, 1.0, lv) * hash1(kc, seed + 3)
    xr_end = xr_end - 0.10 * sstep(0.88, 1.0, lv) * hash1(kc, seed + 5)
    cut |= (xr > xr_end) & (xr <= 1.02) & ~calamus
    alpha = np.where(cut & (rmask < 0.5), 0.0, 1.0).astype(np.float32)
    fray_band = sstep(1 - 1.8 * k["fray"] - 0.02, 1.0, xr) if k["fray"] > 0 else np.zeros_like(xr)
    fray_band = np.where(xr > 1.02, 0.0, fray_band)
    # colours
    if under and kind in ("prim", "sec", "tert", "rect"):
        vane_c, sm, f0k, rach_c = UNDER["col"], UNDER["sm"], UNDER["f0"], UNDER_RACH
    elif under:
        vane_c, sm, f0k, rach_c = UNDER_COV["col"], UNDER_COV["sm"], UNDER_COV["f0"], k["rach"]
    else:
        vane_c, sm, f0k, rach_c = k["col"], k["sm"], k["f0"], k["rach"]
    col = srgb2lin(vane_c)[None, None] * (1 + 0.14 * (streak - 0.5) + 0.05 * barbs)[..., None]
    col = col * (1 - 0.35 * fray_band[..., None]) + srgb2lin(FRAY_COL)[None, None] * (0.35 * fray_band[..., None])
    col = col * (1 - 0.25 * crease[..., None])
    rc = srgb2lin(rach_c)[None, None] * (1 - 0.3 * lv[..., None])                 # the shaft darkens to the tip
    col = col * (1 - rmask[..., None]) + rc * rmask[..., None]
    col = np.where(calamus[..., None], srgb2lin(rach_c)[None, None] * 0.8, col)
    rough = (1 - sm) + 0.15 * fray_band + 0.06 * (0.5 - streak) + 0.05 * crease
    rough = rough * (1 - rmask) + (1 - k["rsm"]) * rmask
    height = rheight + 0.000015 * barbs + 0.00002 * (streak - 0.5) - 0.00004 * crease
    covered = 0.72 + 0.28 * sstep(0.02, 0.30, lv) if kind in ("prim", "sec", "tert", "rect", "gcov", "pcov") \
        else 0.80 + 0.20 * sstep(0.02, 0.40, lv)
    ao = covered * (1 - 0.12 * crease) * (1 - 0.06 * sstep(1.0, 2.2, xw / rw) * sstep(4.0, 2.2, xw / rw))
    if kind == "bristle":                                     # 5 hair strands converging to the tip
        a_h = np.zeros((H, W), np.float32); hh = np.zeros((H, W), np.float32)
        for i, uc in enumerate(np.linspace(0.18, 0.82, 5)):
            c = 0.5 + (uc - 0.5) * (1 - 0.75 * lv)
            wdt = np.maximum(0.075 * (1 - 0.8 * lv), 0.9 / ((u1 - u0) * res))
            d = np.abs(lu - c) / wdt
            a_h = np.maximum(a_h, (d < 1) & (lv < 0.96 - 0.05 * hash1(np.full(1, i), seed)[0]))
            hh = np.maximum(hh, np.sqrt(np.clip(1 - d * d, 0, 1)))
        alpha = a_h.astype(np.float32)
        height = 0.0002 * hh
        ao = 0.85 + 0.15 * hh
    alpha = np.where(xr > 1.02, 1.0, alpha)                   # beyond every outline: opaque (mip coverage)
    return dict(col=col.astype(np.float32), alpha=alpha, rough=np.clip(rough, 0.03, 1).astype(np.float32),
                h=height.astype(np.float32), ao=np.clip(ao, 0, 1).astype(np.float32),
                f0=srgb2lin(F0[f0k]), px=(px_x, px_y))


def feather_textures(res, tex_dir, t0):
    from sdf import eval_prims
    prims = A.body_prims()
    FE = PL.plumage(lambda Q: eval_prims(prims, Q))
    users = slot_users(FE)
    col = np.zeros((res, res, 3), np.float32); col[:] = srgb2lin(FK["gcov"]["col"])
    alpha = np.ones((res, res), np.float32)
    rough = np.full((res, res), 0.4, np.float32)
    nrm = np.zeros((res, res, 3), np.float32); nrm[..., 2] = 1
    ao = np.ones((res, res), np.float32)
    f0 = np.zeros((res, res, 3), np.float32); f0[:] = srgb2lin(F0["blue"])
    for name in PL.SLOTS:
        if not users[name]:
            continue
        cu0, cv0, cu1, cv1 = slot_cell(PL.SLOTS[name])
        x0, x1 = int(round(cu0 * res)), int(round(cu1 * res))
        y0, y1 = int(round((1 - cv1) * res)), int(round((1 - cv0) * res))
        R = paint_slot(name, users[name], y1 - y0, x1 - x0, res)
        col[y0:y1, x0:x1] = R["col"]; alpha[y0:y1, x0:x1] = R["alpha"]; rough[y0:y1, x0:x1] = R["rough"]
        ao[y0:y1, x0:x1] = R["ao"]; f0[y0:y1, x0:x1] = R["f0"]
        # tangent-space normal from the slot's height field (x = +u, y = +v = up in the image)
        gy, gx = np.gradient(R["h"])
        px_x, px_y = R["px"]
        dx = gx / px_x; dy = -gy / px_y
        v3 = np.stack([-dx, -dy, np.ones_like(dx)], -1)
        nrm[y0:y1, x0:x1] = unit_rows(v3)
    col *= (0.6 + 0.4 * ao)[..., None]
    log(f"feather atlas: {sum(1 for k in users if users[k])} slots, {len(FE)} feathers ({time.time() - t0:.0f} s)")
    return write_set(tex_dir, TEX_F, col, alpha, nrm, rough, ao, f0)


# ================================================================================================ EYE
def eye_texture(res=1024, th_open=None):
    y, x = np.mgrid[0:res, 0:res]
    u = (x + 0.5) / res - 0.5; v = 0.5 - (y + 0.5) / res
    r = np.hypot(u, v); ang = np.arctan2(v, u)
    # the whole opening is iris: it reaches 0.003 under the lid (azimuthal equidistant: r = 0.5 * angle / pi)
    R_IRIS = (0.5 * th_open / np.pi if th_open is not None else 0.133) + 0.003
    R_PUP = 0.38 * R_IRIS
    rng = np.random.RandomState(3)
    streak = np.interp(ang, np.linspace(-np.pi, np.pi, 241), rng.rand(241))
    C_IN = srgb2lin((44, 38, 33)); C_OUT = srgb2lin((54, 46, 39)); C_LIMB = srgb2lin((22, 19, 17))
    C_PUP = srgb2lin((12, 11, 11))
    t = np.clip((r - R_PUP) / (R_IRIS - R_PUP), 0, 1)[..., None]
    iris = C_IN * (1 - t) + C_OUT * t
    iris = iris * (0.85 + 0.3 * streak[..., None])
    limb = sstep(R_IRIS - 0.018, R_IRIS - 0.002, r)[..., None]
    iris = iris * (1 - limb) + C_LIMB * limb
    col = np.where((r < R_IRIS)[..., None], iris, srgb2lin((20, 19, 21)))
    pup = (1 - sstep(R_PUP - 0.006, R_PUP + 0.004, r))[..., None]
    col = col * (1 - pup) + C_PUP * pup
    return (lin2srgb(col) * 255 + 0.5).astype(np.uint8)


# ================================================================================================ main
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
                    help="skip the painting: build stage C from the PNGs already in --tex-dir (the LOD0 UVs must not "
                         "have changed; the stored atlas hash is checked)")
    a = ap.parse_args()
    t0 = time.time()
    D = np.load(a.mesh, allow_pickle=False)
    uv_hash = hashlib.sha1(np.ascontiguousarray(D["uv0"].astype(np.float32)).tobytes()).hexdigest()
    hash_file = os.path.join(a.tex_dir, "uv_hash.txt")
    if a.relink_only:
        old = open(hash_file).read().strip() if os.path.exists(hash_file) else ""
        if old != uv_hash:
            raise SystemExit("--relink-only: the LOD0 UV atlas changed since the textures were painted; re-paint them")
        return relink(a)
    os.makedirs(a.tex_dir, exist_ok=True)
    from PIL import Image
    fc = feather_textures(a.res, a.tex_dir, t0)
    th = eye_opening()
    log(f"eye opening {math.degrees(th):.1f} deg (rho {A.EYE_R * math.sin(th) * 1000:.2f} mm): iris to r "
        f"{0.5 * th / math.pi + 0.003:.3f}")
    Image.fromarray(eye_texture(1024, th)).save(os.path.join(a.tex_dir, TEX_EYE + "_BaseColor.png"))
    bc = body_textures(D, a.res, a.tex_dir, t0, A.EYE_R * math.sin(th))
    with open(hash_file, "w") as fh:
        fh.write(uv_hash + "\n")
    log(f"wrote textures to {a.tex_dir} ({time.time() - t0:.0f} s)")
    if a.preview:
        s = 768
        chk = ((np.indices((s, s)).sum(0) // 16) % 2 * 60 + 130).astype(np.uint8)
        f = np.asarray(Image.fromarray(fc, "RGBA").resize((s, s), Image.BILINEAR)).astype(np.float32)
        fa = f[..., 3:4] / 255
        fimg = (f[..., :3] * fa + chk[..., None] * (1 - fa)).astype(np.uint8)
        # brighten the near-black albedos x3 (display only) so the detail is visible
        bimg = np.asarray(Image.fromarray(bc).resize((s, s), Image.BILINEAR)).astype(np.float32)
        sheet = np.concatenate([np.clip(bimg * 3, 0, 255).astype(np.uint8),
                                np.clip(fimg.astype(np.float32) * np.where(fa > 0.5, 3, 1), 0, 255).astype(np.uint8)], 1)
        Image.fromarray(sheet).save(a.preview)
        log("preview", a.preview)
    if a.textures_only:
        return
    relink(a)


def relink(a):
    import bpy
    bpy.ops.wm.open_mainfile(filepath=os.path.abspath(a.inp))
    tex = {os.path.splitext(f)[0]: os.path.abspath(os.path.join(a.tex_dir, f)) for f in os.listdir(a.tex_dir)
           if f.lower().endswith(".png")}
    build_materials(bpy, tex)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(a.out))
    log(f"wrote {a.out}")


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

    def principled(m, prefix, alpha=False):
        m.use_nodes = True
        nt = m.node_tree; nd, ln = nt.nodes, nt.links
        nd.clear()
        out = nd.new("ShaderNodeOutputMaterial"); out.location = (600, 0)
        bs = nd.new("ShaderNodeBsdfPrincipled"); bs.location = (250, 0)
        uv = nd.new("ShaderNodeUVMap"); uv.uv_map = "UVMap"; uv.location = (-700, 0)

        def tnode(key, noncolor, loc, label):
            t = nd.new("ShaderNodeTexImage")
            t.image = load_image(tex[key], key, noncolor)
            t.location = loc; t.label = label
            ln.new(uv.outputs[0], t.inputs["Vector"])
            return t
        bc = tnode(prefix + "_BaseColor", False, (-400, 300), "BaseColor (sRGB)" + (", A = cutout" if alpha else ""))
        ro = tnode(prefix + "_Roughness", True, (-400, 0), "Roughness")
        nm = tnode(prefix + "_Normal", True, (-400, -300), "Normal (tangent, OpenGL +Y)")
        tnode(prefix + "_AO", True, (-400, -600), "AO (engine occlusion slot; not used by Principled)")
        nmap = nd.new("ShaderNodeNormalMap"); nmap.space = "TANGENT"; nmap.uv_map = "UVMap"; nmap.location = (-50, -300)
        ln.new(bc.outputs["Color"], bs.inputs["Base Color"])
        ln.new(ro.outputs["Color"], bs.inputs["Roughness"])
        ln.new(nm.outputs["Color"], nmap.inputs["Color"])
        ln.new(nmap.outputs["Normal"], bs.inputs["Normal"])
        bs.inputs["Specular IOR Level"].default_value = 0.5       # F0 0.04, as Unity Lit
        if alpha:
            # glTF alpha clip pattern (io_scene_gltf2 detect_alpha_clip: Math ROUND -> alphaMode MASK, cutoff 0.5)
            rnd = nd.new("ShaderNodeMath"); rnd.operation = "ROUND"; rnd.location = (-50, 150); rnd.label = "cutout 0.5"
            ln.new(bc.outputs["Alpha"], rnd.inputs[0])
            ln.new(rnd.outputs[0], bs.inputs["Alpha"])
            bc.image.alpha_mode = "STRAIGHT"
            for attr, val in (("surface_render_method", "DITHERED"), ("blend_method", "CLIP")):
                try:
                    setattr(m, attr, val)
                except (AttributeError, TypeError):
                    pass
        ln.new(bs.outputs[0], out.inputs["Surface"])

    def mat(n):
        return bpy.data.materials.get(n) or bpy.data.materials.new(n)
    principled(mat(f"M_{NAME}_Body"), TEX)
    principled(mat(f"M_{NAME}_Feather"), TEX_F, alpha=True)
    me_ = mat(f"M_{NAME}_Eye")
    me_.use_nodes = True
    nt = me_.node_tree; nd, ln = nt.nodes, nt.links
    nd.clear()
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
