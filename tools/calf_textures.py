"""Stage C: procedural coat + eye TEXTURES and materials for the young cow (calf).

Usage
  python3 tools/calf_textures.py --in build/stage_b.blend --out build/stage_c.blend \
          --tex-dir build/textures --res 4096
  (dev)   python3 tools/calf_textures.py --in build/stage_b.blend --out <scratch>/stage_c_test.blend \
          --tex-dir <scratch>/tex --res 1024 --cache <scratch>/bake1024.npz --preview <scratch>/prev.png --textures-only
          (~20 s, ~12 s once the cache exists; delete the cache after any stage-B change. --textures-only skips the
          normal-map bake and the blend save.)

Pipeline
  1. Cycles bakes REST-POSE data from Calf_LOD0 (armature ignored; eyeball faces excluded):
     object-space position, object-space normal, face attribute "orig_part", per-vertex bone-region weights
     (from the skin vertex groups; REGIONS incl. the stage B jaw / ear bones, 3 per image) into 32-bit float images,
     plus ambient occlusion.  UV coverage mask kept.  Mesh landmarks also give the eyelid edge (socket boundary
     loops) and the mouth line (Jaw-weight 0.5 isoline).
  2. numpy: the red-pied coat pattern is computed per texel from the 3D rest position.  Every patch is placed
     relative to landmarks read from the CalfRig rest bones and from the mesh (top/bottom line profile, eyes,
     nose pad), so the pattern follows later geometry edits.  Vectorised 3D Perlin fBm gives organic, slightly
     ragged patch edges (~1-2 cm transition), low-frequency colour variation and directional fur strands.
  3. Textures (UV islands padded by nearest-texel fill of the whole background):
       T_Calf_BaseColor.png (sRGB)  T_Calf_Normal.png (tangent, OpenGL +Y, Cycles NORMAL bake of a bump material
       -> MikkTSpace)  T_Calf_Roughness.png  T_Calf_AO.png  T_Calf_MaskMap.png (HDRP: R metal, G AO, B detail, A smooth)
       T_Calf_MetallicSmoothness.png (URP: RGB metal, A smooth)  T_Calf_Height.png (16-bit, fur height used for the
       normal bake)  T_CalfEye_BaseColor.png (1024)
  4. Materials M_Calf_Body / M_Calf_Eye rebuilt on all LODs, images referenced by relative path (or --pack).

Adult cow (ASSET=cow): _cow_layout() replaces the calf patch layout with a Simmental coat (GiM adult female:
light red-tan with irregular white patches, white head / belly / lower legs / tail, tan ears), the part colours
switch (dark slate hooves, grey-pink muzzle) and two more parts are painted: horns (orig_part 5, cream with dark
tips) and the udder with its teats (orig_part 6, pink skin). Textures are named T_Cow_* / T_CowEye_*.

Deterministic: all noise uses fixed seeds.
"""
import argparse, math, os, re, sys, time

import numpy as np
import bpy
import bmesh

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import asset_profile as AP
TEX, TEX_EYE = AP.TEX, AP.TEX_EYE          # "T_Calf" / "T_CalfEye" (calf), "T_Cow" / "T_CowEye" (adult cow)

T0 = time.time()


def _mem():
    try:
        with open("/proc/self/status") as f:
            d = {l.split(":")[0]: l.split()[1] for l in f if l.startswith(("VmRSS", "VmHWM"))}
        return "%.2f/%.2fGB" % (int(d["VmRSS"]) / 1e6, int(d["VmHWM"]) / 1e6)
    except Exception:
        return "?"


def log(*a):
    print("[calf_tex %6.1fs %s]" % (time.time() - T0, _mem()), *a, flush=True)


# =====================================================================================================
# colours (sRGB 0-255, converted to linear for mixing)
# =====================================================================================================
def srgb2lin(c):
    c = np.asarray(c, np.float32) / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4).astype(np.float32)


def lin2srgb(x):
    x = np.clip(x, 0.0, 1.0)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055)


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


# =====================================================================================================
# vectorised 3D Perlin noise (improved-noise hashing, random unit gradients)
# =====================================================================================================
CHUNK = 1 << 19


class Perlin3:
    STD = 0.188  # empirical std of a single octave (for normalising to ~unit std)

    def __init__(self, seed):
        rs = np.random.RandomState(seed)
        p = rs.permutation(256).astype(np.int64)
        self.perm = np.concatenate([p, p])
        g = rs.normal(size=(256, 3))
        g /= np.linalg.norm(g, axis=1, keepdims=True)
        self.grad = g.astype(np.float32)
        self.off = rs.uniform(-64.0, 64.0, size=(16, 3))  # per-octave offsets

    def _noise(self, p):
        fl = np.floor(p)
        f = (p - fl).astype(np.float32)
        i = fl.astype(np.int64) & 255
        P, G = self.perm, self.grad
        X, Y, Z = i[:, 0], i[:, 1], i[:, 2]
        A = P[X] + Y
        B = P[X + 1] + Y
        AA = P[A] + Z; AB = P[A + 1] + Z; BA = P[B] + Z; BB = P[B + 1] + Z
        fx, fy, fz = f[:, 0], f[:, 1], f[:, 2]
        x1, y1, z1 = fx - 1, fy - 1, fz - 1

        def gd(h, dx, dy, dz):
            g = G[P[h]]
            return g[:, 0] * dx + g[:, 1] * dy + g[:, 2] * dz

        u = fx * fx * fx * (fx * (fx * 6 - 15) + 10)
        v = fy * fy * fy * (fy * (fy * 6 - 15) + 10)
        w = fz * fz * fz * (fz * (fz * 6 - 15) + 10)
        a0 = gd(AA, fx, fy, fz); a1 = gd(BA, x1, fy, fz)
        x00 = a0 + u * (a1 - a0)
        a0 = gd(AB, fx, y1, fz); a1 = gd(BB, x1, y1, fz)
        x10 = a0 + u * (a1 - a0)
        a0 = gd(AA + 1, fx, fy, z1); a1 = gd(BA + 1, x1, fy, z1)
        x01 = a0 + u * (a1 - a0)
        a0 = gd(AB + 1, fx, y1, z1); a1 = gd(BB + 1, x1, y1, z1)
        x11 = a0 + u * (a1 - a0)
        y0 = x00 + v * (x10 - x00)
        y1_ = x01 + v * (x11 - x01)
        return y0 + w * (y1_ - y0)

    def noise(self, p, octave=0):
        """single octave at points p (N,3) float64 -> (N,) float32, ~unit std"""
        p = np.asarray(p, np.float64) + self.off[octave % 16]
        out = np.empty(len(p), np.float32)
        for s in range(0, len(p), CHUNK):
            out[s:s + CHUNK] = self._noise(p[s:s + CHUNK])
        return out / self.STD

    def fbm(self, p, freq, octaves=4, lac=2.0, gain=0.5):
        """fractal sum, normalised to ~unit std.  freq in cycles per meter."""
        acc = np.zeros(len(p), np.float32)
        amp, f, norm = 1.0, freq, 0.0
        for o in range(octaves):
            acc += amp * self.noise(p * f, o)
            norm += amp * amp
            amp *= gain; f *= lac
        return acc / math.sqrt(norm)


# =====================================================================================================
# helpers for images
# =====================================================================================================
def nearest_index(mask):
    """flat index of the nearest covered texel for every texel (Voronoi of the UV coverage)"""
    import cv2
    src = (~mask).astype(np.uint8)
    _, lab = cv2.distanceTransformWithLabels(src, cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL)
    lab = lab.ravel()
    idx = np.flatnonzero(mask.ravel())
    lut = np.zeros(int(lab.max()) + 1, np.int64)
    lut[lab[idx]] = idx
    near = lut[lab]
    near[idx] = idx
    return near


def fill_background(img, mask, near=None):
    """Nearest-covered-texel fill of every uncovered texel (= unlimited island padding / dilation)."""
    if near is None:
        near = nearest_index(mask)
    H, W = mask.shape
    return img.reshape(H * W, -1)[near].reshape(img.shape)


def save_png(path, arr, bits=8):
    """arr in Blender row order (row 0 = v=0 bottom), float 0..1, shape (H,W) or (H,W,C)"""
    from PIL import Image
    a = np.flipud(np.clip(arr, 0.0, 1.0))
    if bits == 16:
        import cv2
        a16 = np.round(a * 65535.0).astype(np.uint16)
        if a16.ndim == 3:
            a16 = a16[..., ::-1]   # RGB -> BGR for cv2
        cv2.imwrite(path, a16)
        return
    a8 = np.round(a * 255.0).astype(np.uint8)
    if a8.ndim == 2:
        Image.fromarray(a8, "L").save(path, optimize=False, compress_level=6)
    else:
        Image.fromarray(a8, {1: "L", 3: "RGB", 4: "RGBA"}[a8.shape[2]]).save(path, compress_level=6)


def blur_masked(img, mask, sigma):
    """normalised Gaussian blur restricted to covered texels"""
    import cv2
    m = mask.astype(np.float32)
    k = int(sigma * 3) * 2 + 1
    num = cv2.GaussianBlur(img * m, (k, k), sigma)
    den = cv2.GaussianBlur(m, (k, k), sigma)
    return np.where(mask, num / np.maximum(den, 1e-6), img)


# =====================================================================================================
# scene access, landmarks
# =====================================================================================================
# baked 3 per RGB image (wA, wB, wC, wD). "jaw"/"ear" are the stage B Jaw / Ear.L|R bones: HEAD regions, kept separate
# so the texture can find the mouth and the ears exactly ("_pad" is always 0).
REGIONS = ["forearm", "fcannon", "thigh", "gaskin", "hcannon", "tail", "head", "neck", "torso", "jaw", "ear", "_pad"]
W_IMAGES = ["w" + "ABCD"[k] for k in range(len(REGIONS) // 3)]


def region_of(bone_name):
    b = bone_name.split(".")[0]
    if b == "FrontUpperLeg": return 0
    if b in ("FrontLowerLeg", "IKFrontLeg", "FF"): return 1
    if b == "BackLeg": return 2
    if b == "BackUpperLeg": return 3
    if b in ("BackLowerLeg", "IKBackLeg", "FFB"): return 4
    if b.startswith("Tail"): return 5
    if b == "Head": return 6
    if b == "Jaw": return 9                        # stage B bones: head regions, not torso
    if b == "Ear": return 10
    if b.startswith("Neck"): return 7
    return 8


def group_fraction(ob, me, name):
    """per-vertex normalised weight of one vertex group (0 where absent)"""
    gi = ob.vertex_groups.get(name)
    out = np.zeros(len(me.vertices), np.float32)
    if gi is None:
        return out
    for v in me.vertices:
        tot = 0.0; w = 0.0
        for g in v.groups:
            tot += g.weight
            if g.group == gi.index:
                w = g.weight
        if tot > 0:
            out[v.index] = w / tot
    return out


def rest_mesh(ob):
    """Evaluated copy of the mesh in REST pose: armature modifiers disabled, other modifiers applied,
    all data layers (UVs, orig_part, vertex-group weights) kept."""
    arms = [m for m in ob.modifiers if m.type == "ARMATURE"]
    st = [(m, m.show_viewport, m.show_render) for m in arms]
    for m in arms:
        m.show_viewport = False; m.show_render = False
    dg = bpy.context.evaluated_depsgraph_get()
    dg.update()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
    for m, v, r in st:
        m.show_viewport = v; m.show_render = r
    me.name = "CalfBake_rest"
    return me


def mesh_arrays(ob, me=None):
    me = me or ob.data
    nv, nf = len(me.vertices), len(me.polygons)
    co = np.zeros(nv * 3); me.vertices.foreach_get("co", co); co = co.reshape(-1, 3)
    part = np.zeros(nf, np.int32)
    if "orig_part" in me.attributes:
        me.attributes["orig_part"].data.foreach_get("value", part)
    ls = np.zeros(nf, np.int32); me.polygons.foreach_get("loop_start", ls)
    lt = np.zeros(nf, np.int32); me.polygons.foreach_get("loop_total", lt)
    lv = np.zeros(len(me.loops), np.int32); me.loops.foreach_get("vertex_index", lv)
    # per-vertex region weights from vertex groups
    names = {g.index: g.name for g in ob.vertex_groups}
    W = np.zeros((nv, len(REGIONS)), np.float32)
    for v in me.vertices:
        for g in v.groups:
            if g.group in names and g.weight > 0:
                W[v.index, region_of(names[g.group])] += g.weight
    s = W.sum(1, keepdims=True)
    W = np.where(s > 0, W / np.maximum(s, 1e-9), np.eye(len(REGIONS), dtype=np.float32)[REGIONS.index("torso")])
    W[:, 6] += W[:, 9] + W[:, 10]          # column 6 = whole head (skull + jaw + ears); 9 / 10 hold the parts
    return co, part, ls, lt, lv, W


def verts_of_part(part, ls, lt, lv, k):
    fs = np.flatnonzero(part == k)
    if len(fs) == 0:
        return np.zeros(0, np.int64)
    idx = np.concatenate([lv[ls[f]:ls[f] + lt[f]] for f in fs])
    return np.unique(idx)


def compute_landmarks(arm, lod0, co, part, ls, lt, lv, W, Wj=None):
    M = lod0.matrix_world.inverted() @ arm.matrix_world
    bone = {}
    for b in arm.data.bones:
        bone[b.name] = (np.array(M @ b.head_local), np.array(M @ b.tail_local))
    LM = {"bone": bone}
    # --- eyes & nose from mesh parts ----------------------------------------------------------------
    ev = verts_of_part(part, ls, lt, lv, 4)
    eyes = {}
    for s, side in ((1, "L"), (-1, "R")):
        vv = ev[co[ev, 0] * s > 0] if len(ev) else ev
        if len(vv):
            c = co[vv].mean(0)
            eyes[side] = (c, float(np.linalg.norm(co[vv] - c, axis=1).mean()))
    if len(eyes) < 2:   # fallback: along the head bone
        h, t = bone["Head"]
        c = h + 0.5 * (t - h); c = c + np.array([0.09, 0, 0.02])
        eyes = {"L": (c, 0.027), "R": (c * np.array([-1, 1, 1]), 0.027)}
    LM["eyes"] = eyes
    nvv = verts_of_part(part, ls, lt, lv, 3)
    if len(nvv):
        LM["nose_c"] = co[nvv].mean(0); LM["nose_min"] = co[nvv].min(0); LM["nose_max"] = co[nvv].max(0)
    else:
        h, t = bone["Head"]; LM["nose_c"] = t + (t - h) * 0.6
        LM["nose_min"] = LM["nose_c"] - 0.03; LM["nose_max"] = LM["nose_c"] + 0.03
    # --- top line & bottom line profile of body+neck along y (midline vertices) ---------------------
    headw, tailw = W[:, 6], W[:, 5]
    legw = W[:, 0] + W[:, 1] + W[:, 3] + W[:, 4]
    mid = np.abs(co[:, 0]) < 0.035
    top_ok = mid & (headw < 0.3) & (tailw < 0.3)
    bot_ok = mid & (headw < 0.3) & (tailw < 0.3) & (legw < 0.6)
    y0, y1 = co[:, 1].min(), co[:, 1].max()
    ys = np.arange(y0, y1 + 0.02, 0.02)
    ztop = np.full(len(ys), np.nan); zbot = np.full(len(ys), np.nan)
    for i, y in enumerate(ys):
        m = np.abs(co[:, 1] - y) < 0.02
        a = m & top_ok; b = m & bot_ok
        if a.any(): ztop[i] = co[a, 2].max()
        if b.any(): zbot[i] = co[b, 2].min()
    for arr in (ztop, zbot):
        ok = ~np.isnan(arr)
        arr[:] = np.interp(ys, ys[ok], arr[ok])
        k = np.array([1, 2, 3, 2, 1], np.float64); k /= k.sum()
        arr[:] = np.convolve(np.pad(arr, 2, mode="edge"), k, mode="valid")
    LM["prof_y"], LM["prof_top"], LM["prof_bot"] = ys, ztop, zbot
    # --- head top surface near the eyes (for the forehead blaze) -------------------------------------
    ey = 0.5 * (eyes["L"][0] + eyes["R"][0])
    m = (np.abs(co[:, 0]) < 0.03) & (np.abs(co[:, 1] - ey[1]) < 0.06) & (W[:, 6] > 0.5) & (co[:, 2] > ey[2])
    LM["head_top_z"] = float(co[m, 2].max()) if m.any() else float(ey[2] + 0.08)
    # forehead midline: from the top of the skull above the poll down the face to just above eye level
    poll = bone["Head"][0]
    m = (np.abs(co[:, 0]) < 0.012) & (co[:, 1] < poll[1] + 0.03) & (W[:, 6] + W[:, 7] > 0.8) & (co[:, 2] > ey[2])
    fy, fz = co[m, 1], co[m, 2]
    if m.sum() > 10:
        ys_h = np.arange(fy.min(), fy.max(), 0.01)
        zs_h = np.array([fz[np.abs(fy - yy) < 0.008].max() if (np.abs(fy - yy) < 0.008).any() else np.nan for yy in ys_h])
        ok = ~np.isnan(zs_h); ys_h, zs_h = ys_h[ok], zs_h[ok]
        top_i = np.argmax(zs_h)
        A = np.array([0.0, ys_h[top_i], zs_h[top_i]])
        front = ys_h < ey[1]
        zt = ey[2] + 0.035
        j = np.argmin(np.abs(zs_h[front] - zt)) if front.any() else top_i
        Bp = np.array([0.0, ys_h[front][j], zs_h[front][j]]) if front.any() else A + np.array([0, -0.12, -0.1])
    else:
        A = np.array([0.0, poll[1], LM["head_top_z"]]); Bp = A + np.array([0, -0.14, -0.1])
    LM["forehead_A"], LM["forehead_B"] = A, Bp
    # --- eyelid edge: the open boundary loops of the coat mesh around each eye (densified polyline points) ----
    fs = np.flatnonzero(part != 4)
    ed = {}
    for f in fs:
        vs = lv[ls[f]:ls[f] + lt[f]]
        for a, b in zip(vs, np.roll(vs, -1)):
            k = (min(a, b), max(a, b)); ed[k] = ed.get(k, 0) + 1
    bnd = np.array([k for k, n in ed.items() if n == 1], np.int64).reshape(-1, 2)
    lid = []
    for side in ("L", "R"):
        c, r = eyes[side]
        if len(bnd):
            e = bnd[(np.linalg.norm(co[bnd[:, 0]] - c, axis=1) < 4 * r + 0.02)]
            for t in np.linspace(0.0, 1.0, 6, endpoint=False):
                lid.append(co[e[:, 0]] * (1 - t) + co[e[:, 1]] * t)
    LM["lid_pts"] = np.concatenate(lid) if lid else np.zeros((0, 3))
    # --- mouth line: the 0.5 isoline of the Jaw weight (where the mesh opens), front part, one polyline per side --
    LM["mouth"] = []
    if Wj is not None and "Jaw" in bone:
        jh, jt = bone["Jaw"]
        y_cut = jh[1] + 0.55 * (jt[1] - jh[1])           # front part of the hinge -> chin length (the isoline
                                                          # rises toward the hinge; the lip line is the level part)
        iso = (Wj > 0.3) & (Wj < 0.7) & (co[:, 1] < y_cut)
        pts = co[iso]
        if len(pts) > 20:
            front = pts[np.abs(pts[:, 0]) < 0.012]
            f0 = front[np.argmin(front[:, 1])] * np.array([0, 1, 1]) if len(front) else None
            for s in (1, -1):
                q = pts[pts[:, 0] * s > 0.004]
                if len(q) < 5:
                    continue
                edges_y = np.arange(q[:, 1].min(), q[:, 1].max() + 0.004, 0.004)
                poly = []
                for y0 in edges_y[::-1]:                  # rear (commissure) -> front
                    m = (q[:, 1] >= y0) & (q[:, 1] < y0 + 0.004)
                    if m.any():
                        poly.append(np.median(q[m], axis=0))
                if f0 is not None:
                    poly.append(f0)
                if len(poly) >= 3:
                    sm = np.array(poly)
                    sd = np.abs(sm[:, 0]) > 0.03                 # side part: straight lip line (least-squares z(y))
                    if sd.sum() >= 3:
                        cz = np.polyfit(sm[sd, 1], sm[sd, 2], 1)
                        sm[sd, 2] = np.polyval(cz, sm[sd, 1])
                    for _ in range(4):                    # [1,2,1] smoothing, ends fixed (the bins wobble +-3 mm)
                        sm[1:-1] = 0.25 * sm[:-2] + 0.5 * sm[1:-1] + 0.25 * sm[2:]
                    LM["mouth"].append(sm)
    # --- misc bbox ----------------------------------------------------------------------------------
    LM["bbmin"], LM["bbmax"] = co.min(0), co.max(0)
    return LM


def lm_summary(LM):
    b = LM["bone"]
    out = {k: np.round(v, 3).tolist() for k, v in [
        ("elbow.R", b["FrontUpperLeg.R"][0]), ("knee.R", b["FrontUpperLeg.R"][1]),
        ("hip.R", b["BackLeg.R"][0]), ("stifle.R", b["BackLeg.R"][1]), ("hock.R", b["BackUpperLeg.R"][1]),
        ("tailhead", b["Tail1"][0]), ("poll", b["Head"][0]), ("eyeL", LM["eyes"]["L"][0]), ("nose", LM["nose_c"])]}
    out["head_top_z"] = round(LM["head_top_z"], 3)
    out["forehead"] = [np.round(LM["forehead_A"], 3).tolist(), np.round(LM["forehead_B"], 3).tolist()]
    out["lid_pts"] = len(LM.get("lid_pts", ()))
    out["mouth"] = [[np.round(p[0], 3).tolist(), np.round(p[-1], 3).tolist(), len(p)] for p in LM.get("mouth", [])]
    return out


# =====================================================================================================
# Cycles data bake
# =====================================================================================================
def new_float_image(name, res):
    img = bpy.data.images.new(name, res, res, alpha=True, float_buffer=True)
    img.colorspace_settings.name = "Non-Color"
    img.generated_color = (0, 0, 0, 0)
    return img


def image_to_array(img):
    w, h = img.size
    a = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(a)
    return a.reshape(h, w, 4)


def array_to_image(img, arr):
    h, w = arr.shape[:2]
    a = np.ones((h, w, 4), np.float32)
    if arr.ndim == 2:
        a[..., 0] = a[..., 1] = a[..., 2] = arr
    else:
        a[..., :arr.shape[2]] = arr
    img.pixels.foreach_set(a.ravel())
    img.update()


class Baker:
    """Owns a temporary rest-pose copy of Calf_LOD0 (eyes split off) in the current scene."""

    def __init__(self, lod0, rest, W):
        sc = bpy.context.scene
        self.sc = sc
        self.hidden = []
        for o in sc.objects:
            if not o.hide_render:
                self.hidden.append(o); o.hide_render = True
        me = rest.copy(); me.name = "CalfBake_mesh"
        nv = len(me.vertices)
        for k, nm in enumerate(W_IMAGES):
            a = me.color_attributes.new(nm, "FLOAT_COLOR", "POINT")
            rgba = np.ones((nv, 4), np.float32); rgba[:, :3] = W[:, 3 * k:3 * k + 3]
            a.data.foreach_set("color", rgba.ravel())
        me_eye = me.copy(); me_eye.name = "CalfBake_eyes"
        for m, keep_eye in ((me, False), (me_eye, True)):
            bm = bmesh.new(); bm.from_mesh(m)
            lay = bm.faces.layers.int.get("orig_part")
            kill = [f for f in bm.faces if (f[lay] == 4) != keep_eye] if lay else \
                   [f for f in bm.faces if (f.material_index == 1) != keep_eye]
            bmesh.ops.delete(bm, geom=kill, context="FACES")
            bm.to_mesh(m); bm.free()
        self.mat = bpy.data.materials.new("CalfBake_mat")
        self.mat.use_nodes = True
        for m in (me, me_eye):
            m.materials.clear(); m.materials.append(self.mat)
            mi = np.zeros(len(m.polygons), np.int32); m.polygons.foreach_set("material_index", mi)
            m.update()
        self.ob = bpy.data.objects.new("CalfBake", me)
        self.ob_eye = bpy.data.objects.new("CalfBakeEyes", me_eye)
        for o in (self.ob, self.ob_eye):
            sc.collection.objects.link(o)
            o.matrix_world = lod0.matrix_world.copy()
        self.world_prev = sc.world
        self.engine_prev = sc.render.engine
        self.world = bpy.data.worlds.new("CalfBakeWorld")
        sc.world = self.world
        self.world.use_nodes = True
        self.world.node_tree.nodes["Background"].inputs[0].default_value = (1, 1, 1, 1)
        sc.render.engine = "CYCLES"
        sc.cycles.device = "CPU"
        sc.cycles.use_denoising = False
        sc.render.bake.margin = 0
        sc.render.bake.use_selected_to_active = False
        sc.render.bake.target = "IMAGE_TEXTURES"
        self.nt = self.mat.node_tree
        nd = self.nt.nodes; nd.clear()
        self.out = nd.new("ShaderNodeOutputMaterial")
        self.em = nd.new("ShaderNodeEmission"); self.em.inputs["Strength"].default_value = 1.0
        self.nt.links.new(self.em.outputs[0], self.out.inputs["Surface"])
        self.img_node = nd.new("ShaderNodeTexImage")
        self.tc = nd.new("ShaderNodeTexCoord")

    def _select(self):
        for o in self.sc.objects:
            o.select_set(False)
        self.ob.select_set(True)
        bpy.context.view_layer.objects.active = self.ob

    def bake(self, img, typ="EMIT", samples=1, src=None):
        nd, ln = self.nt.nodes, self.nt.links
        if src is not None:
            for l in list(self.em.inputs["Color"].links):
                ln.remove(l)
            ln.new(src, self.em.inputs["Color"])
        self.img_node.image = img
        nd.active = self.img_node
        self.sc.cycles.samples = samples
        self._select()
        t = time.time()
        bpy.ops.object.bake(type=typ, margin=0, use_clear=True, target="IMAGE_TEXTURES")
        log("  baked", img.name, typ, "%dx%d" % tuple(img.size), "in %.1fs" % (time.time() - t))
        return image_to_array(img)

    def vec_remap(self, sock, mn, ext):
        nd, ln = self.nt.nodes, self.nt.links
        s = nd.new("ShaderNodeVectorMath"); s.operation = "SUBTRACT"; s.inputs[1].default_value = tuple(mn)
        d = nd.new("ShaderNodeVectorMath"); d.operation = "DIVIDE"; d.inputs[1].default_value = tuple(ext)
        ln.new(sock, s.inputs[0]); ln.new(s.outputs[0], d.inputs[0])
        return d.outputs[0]

    def attr(self, name, out="Color"):
        a = self.nt.nodes.new("ShaderNodeAttribute"); a.attribute_type = "GEOMETRY"; a.attribute_name = name
        return a.outputs[out]

    def bake_normal(self, height, distance, res):
        """Tangent-space (MikkTSpace, OpenGL +Y) normal bake of a Bump node driven by the height image."""
        nd, ln = self.nt.nodes, self.nt.links
        h_img = new_float_image("_bake_height", height.shape[0])
        array_to_image(h_img, height)
        tex = nd.new("ShaderNodeTexImage"); tex.image = h_img; tex.interpolation = "Linear"
        tex.extension = "EXTEND"
        uv = nd.new("ShaderNodeUVMap"); uv.uv_map = "UVMap"
        ln.new(uv.outputs[0], tex.inputs["Vector"])
        bump = nd.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = 1.0
        bump.inputs["Distance"].default_value = distance
        ln.new(tex.outputs["Color"], bump.inputs["Height"])
        dif = nd.new("ShaderNodeBsdfDiffuse")
        ln.new(bump.outputs["Normal"], dif.inputs["Normal"])
        ln.new(dif.outputs[0], self.out.inputs["Surface"])
        bk = self.sc.render.bake
        bk.normal_space = "TANGENT"; bk.normal_r = "POS_X"; bk.normal_g = "POS_Y"; bk.normal_b = "POS_Z"
        img = new_float_image("_bake_normal", res)
        a = self.bake(img, typ="NORMAL", samples=1)
        ln.new(self.em.outputs[0], self.out.inputs["Surface"])
        bpy.data.images.remove(img); bpy.data.images.remove(h_img)
        return a

    def cleanup(self):
        sc = self.sc
        for o in (self.ob, self.ob_eye):
            me = o.data
            bpy.data.objects.remove(o, do_unlink=True)
            bpy.data.meshes.remove(me)
        bpy.data.materials.remove(self.mat)
        sc.world = self.world_prev
        bpy.data.worlds.remove(self.world)
        sc.render.engine = self.engine_prev
        for o in self.hidden:
            o.hide_render = False


def bake_data(baker, res, ao_res, ao_samples, ao_dist, bbmin, bbmax):
    """returns dict of numpy arrays in Blender row order"""
    pad = 0.02
    mn = bbmin - pad; ext = (bbmax - bbmin) + 2 * pad
    D = {}
    img = new_float_image("_bake_tmp", res)
    # position (object space, remapped into 0..1)
    a = baker.bake(img, src=baker.vec_remap(baker.tc.outputs["Object"], mn, ext))
    cov = a[..., 3] > 0.5
    if cov.mean() < 0.05 or cov.mean() > 0.98:   # alpha not written -> use value test (remap keeps >0)
        cov = a[..., :3].min(-1) > 1e-4
    D["cov"] = cov
    D["pos"] = (a[..., :3] * ext + mn).astype(np.float32)
    # normal (object space)
    nd = baker.nt.nodes
    ma = nd.new("ShaderNodeVectorMath"); ma.operation = "MULTIPLY_ADD"
    ma.inputs[1].default_value = (0.5, 0.5, 0.5); ma.inputs[2].default_value = (0.5, 0.5, 0.5)
    baker.nt.links.new(baker.tc.outputs["Normal"], ma.inputs[0])
    a = baker.bake(img, src=ma.outputs[0])
    n = a[..., :3] * 2 - 1
    n /= np.maximum(np.linalg.norm(n, axis=-1, keepdims=True), 1e-6)
    D["nrm"] = n.astype(np.float32)
    # orig_part (face attribute)
    a = baker.bake(img, src=baker.attr("orig_part", "Fac"))
    D["part"] = np.rint(a[..., 0]).astype(np.int8)
    # region weights
    ws = []
    for nm in W_IMAGES:
        a = baker.bake(img, src=baker.attr(nm))
        ws.append(a[..., :3])
    D["w"] = np.concatenate(ws, -1).astype(np.float16)
    bpy.data.images.remove(img)
    # ambient occlusion (lower res, more samples, then upsampled)
    baker.world.light_settings.distance = ao_dist
    img = new_float_image("_bake_ao", ao_res)
    a = baker.bake(img, typ="AO", samples=ao_samples)
    bpy.data.images.remove(img)
    D["ao_lo"] = a[..., 0].astype(np.float32)
    D["ao_lo_cov"] = a[..., 3] > 0.5 if (a[..., 3] > 0.5).mean() < 0.98 else a[..., 0] > 1e-4
    return D


# =====================================================================================================
# coat pattern (numpy, per covered texel)
# =====================================================================================================
def seg_param(P, a, b):
    ab = b - a
    L2 = float(ab @ ab)
    t = np.clip(((P - a) @ ab) / max(L2, 1e-12), 0.0, 1.0)
    return t, np.linalg.norm(P - (a + t[:, None] * ab), axis=1)


def polyline_param(P, pts):
    """arc-length parameter (0..1) of the closest point on a polyline, and the distance to it"""
    seglen = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    cum = np.concatenate([[0.0], np.cumsum(seglen)])
    bd = np.full(len(P), np.inf); bs = np.zeros(len(P))
    for i in range(len(pts) - 1):
        t, d = seg_param(P, pts[i], pts[i + 1])
        m = d < bd
        bd[m] = d[m]; bs[m] = cum[i] + t[m] * seglen[i]
    return bs / cum[-1], bd, cum[-1]


def aniso(P, d, f_across, f_along):
    """coordinates for noise that is stretched along direction d (strands)"""
    d = np.asarray(d, np.float64); d = d / np.linalg.norm(d)
    return P * f_across + np.outer(P @ d, d) * (f_along - f_across)


def ell(P, c, r):
    """normalised ellipsoid radius (1 on the surface)"""
    q = (P - np.asarray(c)) / np.asarray(r)
    return np.sqrt((q * q).sum(1))


def box_dist(P, mn, mx):
    d = np.maximum(np.maximum(mn - P, P - mx), 0.0)
    return np.linalg.norm(d, axis=1)


def min_dist_to_set(A, Bset, chunk=2048):
    """brute-force nearest distance from points A to point set B (both small)"""
    if len(Bset) == 0:
        return np.full(len(A), 1e3)
    out = np.empty(len(A))
    Bf = Bset.astype(np.float64); b2 = (Bf * Bf).sum(1)
    for s in range(0, len(A), chunk):
        a = A[s:s + chunk].astype(np.float64)
        d2 = (a * a).sum(1)[:, None] + b2[None, :] - 2.0 * (a @ Bf.T)
        out[s:s + chunk] = np.sqrt(np.maximum(d2.min(1), 0.0))
    return out


class PatternCtx:
    """Landmark-derived constants + global point sets shared by all texel chunks."""

    def __init__(self, P, Nr, part, w, LM, texel, seed):
        self.LM, self.seed = LM, seed
        self.NZ = [Perlin3(seed + i) for i in range(12)]
        B = LM["bone"]

        def mid(name, i):   # average of .L/.R, x -> |x|
            a, b = B[name + ".L"][i], B[name + ".R"][i]
            return np.array([0.5 * (abs(a[0]) + abs(b[0])), 0.5 * (a[1] + b[1]), 0.5 * (a[2] + b[2])])

        self.elbow, self.knee = mid("FrontUpperLeg", 0), mid("FrontUpperLeg", 1)
        self.hip, self.stifle, self.hock = mid("BackLeg", 0), mid("BackLeg", 1), mid("BackUpperLeg", 1)
        self.tailpts = np.array([B["Tail1"][0]] + [B["Tail%d" % i][1] for i in range(1, 8)])
        self.neck_a, self.neck_b = B["Neck1"][0], B["Neck3"][1]      # neck axis (withers -> poll)
        self.poll, self.headtip = B["Head"][0], B["Head"][1]
        self.eyeL, self.eyeR = LM["eyes"]["L"][0], LM["eyes"]["R"][0]
        self.r_eye = 0.5 * (LM["eyes"]["L"][1] + LM["eyes"]["R"][1])
        y_el = self.elbow[1]
        self.s = (self.tailpts[0][1] - y_el) / 0.832          # body length scale (elbow -> tail head)
        self.sn = (y_el - self.poll[1]) / 0.463               # neck length scale (elbow -> poll)
        yq = y_el + 0.2 * self.s
        Hb = float(np.interp(yq, LM["prof_y"], LM["prof_top"]) - np.interp(yq, LM["prof_y"], LM["prof_bot"]))
        self.sh = Hb / 0.53                                   # barrel height scale
        self.fa = min(230.0, 0.30 / texel)                    # across-strand frequency (texel-limited)
        # ears: texels of the stage B Ear.L/R bones (baked region weight); inner = old light part facing the cup side
        ear = self.ear_mask(P, w)
        inner = ear & (part == 1) & self.inner_side(P, Nr)
        outer = ear & (part != 1)
        rs = np.random.RandomState(seed)
        # (position, EAR_NK * normal): the ear is a thin leaf, so the back side lies only 1-3 cm behind the inner
        # side; with the normal term, opposite-facing texels count as >= 2*EAR_NK away and the inner/outer
        # distances are measured across the same face (to the real inner/outer border), not through the leaf
        self.inner_pts = self.ear6(P[inner], Nr[inner]); self.outer_pts = self.ear6(P[outer], Nr[outer])
        if len(self.outer_pts) > 6000:
            self.outer_pts = self.outer_pts[rs.choice(len(self.outer_pts), 6000, replace=False)]
        if len(self.inner_pts) > 6000:
            self.inner_pts = self.inner_pts[rs.choice(len(self.inner_pts), 6000, replace=False)]
        # hooves: coat texels along the hoof/pastern border (for the coronet band), per-hoof centre x
        hv = part == 2
        self.hoof_rim = np.zeros((0, 3)); self.hoof_cx = {}
        if hv.any():
            Ph = P[hv]
            y_split = 0.5 * (self.elbow[1] + self.hip[1])
            for sx in (1, -1):
                for fr in (True, False):
                    m = (np.sign(Ph[:, 0]) == sx) & ((Ph[:, 1] < y_split) == fr)
                    if m.any():
                        self.hoof_cx[(sx, fr)] = float(np.median(Ph[m, 0]))
            hs = Ph if len(Ph) <= 6000 else Ph[rs.choice(len(Ph), 6000, replace=False)]
            zc = (part != 2) & (P[:, 2] < Ph[:, 2].max() + 0.012) & (part != 4)
            Pc = P[zc]
            if len(Pc):
                near = min_dist_to_set(Pc, hs) < 0.004
                self.hoof_rim = Pc[near]
                if len(self.hoof_rim) > 6000:
                    self.hoof_rim = self.hoof_rim[rs.choice(len(self.hoof_rim), 6000, replace=False)]
        # cow: horn base -> tip axis per side, udder / teat heights
        self.horn = {}
        hm = part == AP.PART_HORN
        for sx in (1, -1):
            q = P[hm & (np.sign(P[:, 0]) == sx)]
            if len(q) > 20:
                ax_ = np.abs(q[:, 0])
                b_ = q[ax_ <= np.percentile(ax_, 8)].mean(0)
                t_ = q[np.argmax(np.linalg.norm(q - b_, axis=1))]
                self.horn[sx] = (b_, t_)
        um = part == AP.PART_UDDER
        if um.any():
            zu = P[um, 2]
            self.udder_zmin, self.udder_top = float(zu.min()), float(zu.max())
            self.teat_z = self.udder_zmin + 0.043     # teats are 0.20 original units = 4.5 cm at authoring scale
        # eyelid edge points (texture lid rim is measured from the real socket boundary, not the eyeball sphere)
        self.lid_pts = LM.get("lid_pts", np.zeros((0, 3)))
        self.mouth = LM.get("mouth", [])

    EAR_NK = 0.008

    @classmethod
    def ear6(cls, P, Nr):
        return np.concatenate([P, cls.EAR_NK * np.asarray(Nr, np.float64)], 1)

    @staticmethod
    def inner_side(P, Nr):
        """inner-ear test: the cupped inner side faces forward / inward / down (not straight out)"""
        return np.sign(P[:, 0]) * Nr[:, 0] < 0.8

    @staticmethod
    def ear_mask(P, w):
        """ear texels: the baked Ear.L/Ear.R region weight (stage B ear bones)"""
        return w[:, 10] > 0.3


def coat_pattern(P, Nr, part, w, LM, texel, seed, chunk=1 << 20):
    """Linear base colour (N,3), roughness (N,), height (N,) for covered texels.  Evaluated in texel chunks
    (bounded memory at 4096); every value is a pure function of the texel's rest position/normal/part/weights,
    so the result does not depend on the chunking."""
    t0 = time.time()
    N = len(P)
    ctx = PatternCtx(P, Nr, part, w, LM, texel, seed)
    col = np.empty((N, 3), np.float32); rough = np.empty(N, np.float32); height = np.empty(N, np.float32)
    for s0 in range(0, N, chunk):
        sl = slice(s0, min(N, s0 + chunk))
        col[sl], rough[sl], height[sl] = _coat_chunk(ctx, P[sl], Nr[sl], part[sl], w[sl])
        log("  pattern: %d/%d texels  %.1fs" % (sl.stop, N, time.time() - t0))
    log("  pattern: done %.1fs (fa=%.0f/m, texel=%.2fmm)" % (time.time() - t0, ctx.fa, texel * 1000))
    return col, rough, height, {"fa": ctx.fa}


def _cow_layout(ctx, P, Nr, part, w, yw, zw, dt, db, edge, strand, legF, legH, headm, tailm, torso):
    """Simmental coat of the adult cow (GiM adult female, videoplayback.mp4 5-30 s): light red-tan neck, shoulders,
    barrel and rump broken by irregular jagged white patches (largest over the back behind the withers, the loin and
    the rump), white head with tan ears, white brisket / belly / udder region, white legs (the tan runs a little down
    the outer forearm and thigh), white tail below a tan root.
    Returns (M_or: 1 = tan, m_sw: tail switch mask, m_tuft: long-hair mask, hb: belly white height)."""
    NZ = ctx.NZ
    x, y, z = P[:, 0], P[:, 1], P[:, 2]
    elbow, knee, hip, stifle, hock = ctx.elbow, ctx.knee, ctx.hip, ctx.stifle, ctx.hock
    s, sn, sh = ctx.s, ctx.sn, ctx.sh
    y_el = elbow[1]
    # white belly: height above the bottom line, rising toward the udder / flank and the brisket
    by = np.array([y_el - 0.25 * s, y_el - 0.10 * s, y_el + 0.15 * s, 0.5 * (y_el + hip[1]), stifle[1] - 0.10 * s,
                   stifle[1], hip[1] + 0.12 * s])
    bh = np.array([0.02, 0.16, 0.12, 0.16, 0.24, 0.20, 0.04]) * sh   # low behind the stifle: the rear bottom line rises to the escutcheon
    hb = np.interp(yw, by, bh)
    f_w = np.where(legF + legH < 0.5, hb - db, -1.0)       # > 0: white belly (trunk only; the legs have their own line)
    # throat / dewlap / brisket underside white (GiM: white from the jaw down the throat to the chest)
    m_neck_under = np.clip(w[:, 7] + torso * smoothstep(y_el + 0.02 * s, y_el - 0.12 * s, yw), 0, 1)
    f_w = np.maximum(f_w, np.where(m_neck_under > 0.4, (-Nr[:, 2] - 0.35) * 0.1, -1.0))
    # head white, ears tan (ear region = stage B Ear bones), the crown behind the horns blends into the tan neck
    earm = smoothstep(0.25, 0.5, w[:, 10])
    f_head = (headm - 0.5) * 0.1 - 0.2 * earm
    f_head = f_head - 0.06 * smoothstep(ctx.poll[1] - 0.02, ctx.poll[1] + 0.05, y) * (z > ctx.poll[2] - 0.02)
    f_w = np.maximum(f_w, f_head)
    # legs: front white below mid-forearm (tan reaches lower on the outer front), hind white below the stifle
    lat = np.sign(x) * Nr[:, 0]
    zF = knee[2] + (0.45 - 0.25 * np.clip(lat, 0, 1)) * (elbow[2] - knee[2]) + 0.015 * NZ[8].noise(P * 22.0, 3)
    f_w = np.maximum(f_w, np.where(legF > 0.3, (zF - zw) * 0.8, -1.0))
    zH = stifle[2] - 0.03 - 0.06 * np.clip(-lat, 0, 1) + 0.015 * NZ[8].noise(P * 22.0, 4)
    f_w = np.maximum(f_w, np.where(legH + 0.4 * w[:, 2] > 0.3, (zH - zw) * 0.8, -1.0))
    # tail white below a tan root
    s_tail, _, L_tail = polyline_param(P, ctx.tailpts)
    s_tb = 0.16 + 0.03 * NZ[8].noise(P * 20.0, 5)
    f_w = np.maximum(f_w, np.where(tailm > 0.3, (s_tail - s_tb) * L_tail, -1.0))
    m_sw = tailm * smoothstep(0.66, 0.78, s_tail)          # switch (long clumped hair) for the height map
    # irregular white body patches: domain-warped fBm, thresholded; the threshold drops over the back behind the
    # withers, the loin and the rump (GiM: broad white saddle / rump patches) and rises on the neck and shoulder
    Pw = P + 0.06 * np.stack([NZ[0].fbm(P, 1.7, 2), NZ[1].fbm(P, 1.7, 2), NZ[2].fbm(P, 1.7, 2)], 1)
    n = NZ[9].fbm(Pw, 2.3, 4) + 0.35 * NZ[10].fbm(Pw, 6.0, 2)
    back = smoothstep(0.30 * sh, 0.04 * sh, dt) * smoothstep(y_el + 0.05 * s, y_el + 0.25 * s, yw) * \
        smoothstep(hip[1] + 0.02 * s, hip[1] - 0.22 * s, yw)                 # withers to loin, not the rump
    rump = smoothstep(hip[1] - 0.20 * s, hip[1] + 0.05 * s, yw) * smoothstep(0.55 * sh, 0.15 * sh, dt)
    flank = smoothstep(y_el + 0.35 * s, hip[1] - 0.1 * s, yw) * smoothstep(0.75 * sh, 0.45 * sh, dt)
    shoulder = smoothstep(y_el + 0.22 * s, y_el + 0.02 * s, yw)
    thr = 0.75 - 0.60 * back + 0.10 * rump - 0.15 * flank + 0.9 * shoulder + 1.2 * np.clip(w[:, 7] - 0.3, 0, 1)
    f_patch = (n - thr) * 0.03
    f_patch = np.where((torso + 0.6 * w[:, 7] + 0.8 * w[:, 2] + 0.5 * w[:, 0]) > 0.3, f_patch, -1.0)
    # speckle islands along the patch borders (Simmental patches are ragged, with small white flecks)
    fl = NZ[11].fbm(P, 16.0, 2)
    f_patch = np.maximum(f_patch, np.where(np.abs(n - thr) < 0.35, (fl - 1.55) * 0.02, -1.0))
    f_w = np.maximum(f_w, f_patch)
    ew = 0.0045
    M_or = smoothstep(-ew, ew, -(f_w + edge + 0.0018 * strand)).astype(np.float32)
    return M_or, m_sw, np.zeros(len(P), np.float32), hb


def _coat_chunk(ctx, P, Nr, part, w):
    LM, NZ = ctx.LM, ctx.NZ
    x, y, z = P[:, 0], P[:, 1], P[:, 2]
    nx, ny, nzn = Nr[:, 0], Nr[:, 1], Nr[:, 2]
    wf, wfc, wth, wg, whc, wt, wh, wn, wto = [w[:, i].astype(np.float32) for i in range(9)]
    elbow, knee, hip, stifle, hock = ctx.elbow, ctx.knee, ctx.hip, ctx.stifle, ctx.hock
    poll, headtip, eyeL, eyeR, r_eye = ctx.poll, ctx.headtip, ctx.eyeL, ctx.eyeR, ctx.r_eye
    s, sn, sh, fa = ctx.s, ctx.sn, ctx.sh, ctx.fa
    y_el = elbow[1]
    legF = smoothstep(0.35, 0.65, wf + wfc)
    legH = smoothstep(0.35, 0.65, wg + whc)
    headm = smoothstep(0.35, 0.65, wh)
    tailm = smoothstep(0.35, 0.65, wt)
    torso = np.clip(1.0 - legF - legH - headm - tailm, 0.0, 1.0)

    # ---------------------------------------------------------------- organic warp + ragged edge noise
    yw = y + 0.032 * NZ[0].fbm(P, 2.0, 3)
    zw = z + 0.026 * NZ[1].fbm(P, 2.0, 3)
    dt = np.interp(yw, LM["prof_y"], LM["prof_top"]) - zw      # depth below the top line
    db = zw - np.interp(yw, LM["prof_y"], LM["prof_bot"])      # height above the bottom line
    edge = 0.0085 * NZ[2].fbm(P, 7.0, 4) + 0.0022 * NZ[3].noise(P * 42.0, 5)

    # ---------------------------------------------------------------- fur strand direction fields
    fl = fa / 9.0
    dirs = [(np.array([0.0, 1.0, -0.25]), torso + 0.5 * smoothstep(0.35, 0.65, wth)),   # body: head -> tail
            (np.array([0.0, 0.08, -1.0]), legF + legH + tailm),                          # legs/tail: down
            (headtip - poll, headm)]                                                     # face: poll -> nose
    strand = np.zeros(len(P), np.float32); wsum = np.zeros(len(P), np.float32)
    clump = np.zeros(len(P), np.float32)
    for k, (dv, wd) in enumerate(dirs):
        m = wd > 0.02
        if not m.any():
            continue
        q = aniso(P[m], dv, fa, fl)
        v = 0.7 * NZ[4 + k].noise(q, 0) + 0.45 * NZ[4 + k].noise(q * 2.03, 1)
        c = NZ[7 + k].noise(aniso(P[m], dv, fa / 4.0, fa / 12.0), 2)
        strand[m] += wd[m] * v; clump[m] += wd[m] * c; wsum[m] += wd[m]
    strand /= np.maximum(wsum, 1e-3); clump /= np.maximum(wsum, 1e-3)

    if AP.IS_COW:
        M_or, m_sw, m_tuft, hb = _cow_layout(ctx, P, Nr, part, w, yw, zw, dt, db, edge, strand, legF, legH,
                                             headm, tailm, torso)
    else:
        # ---------------------------------------------------------------- patch layout (signed metric fields)
        # shoulder band (white): front / rear edge y as a function of depth below the top line
        # (GiM: the neck-base orange runs unbroken into the shoulder and forearm; the band sits behind the arm)
        dts = np.array([0.0, 0.1, 0.2, 0.3, 0.4, 0.7]) * sh
        sbF = y_el + np.array([-0.19 * sn + 0.08 * s, -0.005 * s, 0.06 * s, 0.11 * s, 0.085 * s, 0.06 * s])
        sbR = y_el + np.array([0.155, 0.145, 0.13, 0.135, 0.13, 0.14]) * s
        yF_sb = np.interp(dt, dts, sbF); yR_sb = np.interp(dt, dts, sbR)
        # hip band (white)
        dth = np.array([0.0, 0.1, 0.2, 0.3, 0.45]) * sh
        hbF = hip[1] + np.array([-0.20, -0.14, -0.11, -0.10, -0.10]) * s
        hbR = hip[1] + np.array([-0.085, -0.025, -0.005, 0.005, 0.0]) * s
        yF_hb = np.interp(dt, dth, hbF); yR_hb = np.interp(dt, dth, hbR)
        # white belly/brisket height above the bottom line, along y
        by = np.array([y_el - 0.23 * s, y_el - 0.15 * s, y_el - 0.05 * s, y_el + 0.2 * s, 0.5 * (y_el + hip[1]),
                       stifle[1] - 0.12 * s, stifle[1], hip[1] + 0.1 * s])
        # (first value < 0: ahead of the chest the throat / neck underside stays orange)
        bh = np.array([-0.06, 0.10, 0.10, 0.065, 0.055, 0.09, 0.17, 0.22]) * sh
        hb = np.interp(yw, by, bh)
        z_rb = stifle[2] + 0.075 * sh                  # lower limit of the orange rump
        s_tail, _, L_tail = polyline_param(P, ctx.tailpts)

        f1 = yw - yF_sb                                        # head / neck / shoulder / forearm orange
        # white brisket + chest: ventral / front-facing chest only, so it does not cut across the point of the
        # shoulder and elbow (the orange forearm stays connected to the shoulder, as on GiM)
        lat_b = np.sign(x) * nx
        brisk = (torso + legF > 0.5) & ((np.abs(x) < 0.07) | (lat_b < 0.45))
        f1 = np.maximum(f1, np.where(brisk, hb - db, -1.0))
        del lat_b, brisk
        knee_edge = knee[2] + 0.012 + 0.012 * NZ[8].noise(P * 28.0, 3)
        f1 = np.maximum(f1, knee_edge - zw)                    # white below the knees
        f2 = np.maximum.reduce([yR_sb - yw, yw - yF_hb, hb - db])           # barrel
        f2 = np.maximum(f2, (0.5 - torso) * 0.1)
        f3 = np.maximum(yR_hb - yw, z_rb - zw)                 # rump (incl. the tail root)
        s_tb = 0.64 + 0.03 * NZ[8].noise(P * 20.0, 4)    # white only on the lower ~40 % of the hanging tail + switch
        m_sw = tailm * smoothstep(-0.03, 0.08, s_tail - s_tb)   # switch (long clumped hair) for the height map
        f5 = np.maximum((0.5 - tailm) * 0.1, (s_tail - s_tb) * L_tail)     # orange tail base
        f_tw = np.maximum((0.5 - tailm) * 0.1, (s_tb - s_tail) * L_tail)   # white rest of the tail (cut)
        # forearms: fully orange on the right leg, lateral/front only on the left leg
        lat = np.sign(x) * nx
        fa_top = np.where(x > 0, knee[2] + 0.22 * (elbow[2] - knee[2]), knee_edge + 0.008)
        f6 = np.maximum((0.5 - legF) * 0.1, fa_top - zw)
        f6 = np.maximum(f6, np.where(x > 0, (-0.15 - (lat - 0.6 * ny)) * 0.05, -1.0))
        # left outer thigh / stifle patch hanging down from the rump orange (asymmetry)
        stL = np.array([stifle[0] + 0.05, stifle[1] + 0.075 * s, stifle[2] + 0.02])
        f4 = (ell(P, stL, np.array([0.09, 0.075, 0.105]) * s) - 1.0) * 0.08
        f4 = np.maximum(f4, 0.06 - x)
        # a few small orange spots on the white hind legs (gaskin)
        f7 = (2.15 - NZ[8].fbm(P, 14.0, 2)) * 0.015
        f7 = np.maximum(f7, (0.5 - legH) * 0.1)
        f7 = np.maximum(f7, np.maximum((hock[2] - 0.03) - zw, zw - (stifle[2] - 0.04)))
        f_or = np.minimum.reduce([f1, f2, f3, f4, f5, f6, f7])
        f_or = np.maximum(f_or, -f_tw)
        del f1, f2, f3, f4, f5, f6, f7, f_tw, yF_sb, yR_sb, yF_hb, yR_hb, lat, fa_top, s_tail, s_tb
        # forehead blaze (white) cut from the orange: jagged, tuft-like tapered capsule along the forehead
        # midline, from the crown above the poll down to just above eye level
        # GiM: a broad fluffy shield (~60 % of the forehead width) from the poll down to eye level
        fA, fB = LM["forehead_A"], LM["forehead_B"]
        fB = fB + (fB - fA) * 0.22
        fA = fA + (fA - fB) * 0.18
        tb, db_ = seg_param(P, fA, fB)
        f_bl = db_ - np.interp(tb, [0.0, 0.2, 0.5, 1.0], [0.075, 0.095, 0.072, 0.03]) * sn
        f_bl = f_bl + 0.7 * edge + 0.0055 * NZ[3].noise(aniso(P, fB - fA, 170.0, 40.0), 6)
        m_tuft = smoothstep(0.004, -0.02, f_bl) * headm              # blaze core: longer, clumped hair (height map)
        headish = np.maximum(headm, smoothstep(poll[1] + 0.08, poll[1] + 0.03, y) * (wh + wn > 0.8))
        f_bl = np.maximum(f_bl, (0.5 - headish) * 0.1)
        f_or = np.maximum(f_or, -f_bl)
        del tb, db_, f_bl, headish
        ew = 0.0055
        M_or = smoothstep(ew, -ew, f_or + edge + 0.0018 * strand).astype(np.float32)
        del f_or

    # ---------------------------------------------------------------- colours
    # orange/white ratio matched to the Gemini GiM side view (was 203,112,45: too red, too little G/B)
    C_OR = srgb2lin([200, 122, 62]); C_OR_RED = srgb2lin([186, 102, 52]); C_OR_LT = srgb2lin([216, 150, 88])
    C_WH = srgb2lin([236, 232, 224]); C_WH_GREY = srgb2lin([214, 208, 202]); C_DIRT = srgb2lin([176, 165, 150])
    if AP.IS_COW:    # GiM adult Simmental: paler, pinker red-tan; slightly cooler white
        C_OR = srgb2lin([198, 136, 94]); C_OR_RED = srgb2lin([182, 116, 80]); C_OR_LT = srgb2lin([214, 160, 120])
        C_WH = srgb2lin([238, 236, 232]); C_WH_GREY = srgb2lin([212, 208, 206]); C_DIRT = srgb2lin([168, 160, 150])
    lf1 = NZ[9].fbm(P, 3.0, 3); lf2 = NZ[10].fbm(P, 11.0, 2)
    hue = smoothstep(-1.2, 1.2, NZ[11].fbm(P, 1.6, 2))[:, None]
    orange = C_OR * (1 - hue) + C_OR_RED * hue
    br = 1.0 + 0.07 * lf1 + 0.035 * lf2
    upness = np.clip(nzn, 0, 1)
    m_top = smoothstep(0.24 * sh, 0.02, dt) * upness * (torso + 0.5 * wn)
    m_spine = np.exp(-(x / 0.018) ** 2) * smoothstep(0.07, 0.0, dt) * torso
    m_low = smoothstep(0.30 * sh, 0.10 * sh, db) * torso * (1 - upness)
    m_throat = np.clip(wn + 0.5 * headm, 0, 1) * np.clip(-nzn + 0.2, 0, 1)
    dE = np.minimum(np.linalg.norm(P - eyeL, axis=1), np.linalg.norm(P - eyeR, axis=1)) - r_eye
    m_eye = np.exp(-(np.maximum(dE, 0) / 0.022) ** 2) * headm
    br = br - 0.13 * m_spine - 0.12 * m_low - 0.16 * m_throat - 0.25 * m_eye
    lt = (0.55 * m_top)[:, None]
    orange = orange * (1 - lt) + C_OR_LT * lt
    orange = orange * (br * (1 + 0.085 * strand))[:, None]
    del hue, br, m_top, m_spine, m_low, m_throat, m_eye, lt
    white = C_WH * (1.0 + 0.02 * lf1 + 0.012 * lf2)[:, None]
    m_wgrey = np.clip(np.clip(-nzn, 0, 1) * torso * 0.5 + 0.35 * smoothstep(0.5, 0.0, np.abs(lf1)) * 0.3, 0, 1)
    white = white * (1 - m_wgrey[:, None]) + C_WH_GREY * m_wgrey[:, None]
    m_dirt = smoothstep(0.15, 0.04, z) * np.clip(legF + legH, 0, 1) * (0.32 + 0.15 * lf2)   # pastern stays paler than the hoof
    white = white * (1 - m_dirt[:, None]) + C_DIRT * m_dirt[:, None]
    white = white * (1 + 0.045 * strand)[:, None]
    # brisket speckles (grey-orange flecks in the white chest)
    m_br = smoothstep(y_el + 0.06 * s, y_el - 0.04 * s, yw) * np.clip(torso + 0.5 * legF, 0, 1) \
        * smoothstep(0.02, -0.01, db - hb) * smoothstep(elbow[2] - 0.12 * sh, elbow[2] - 0.04 * sh, z)
    spk = smoothstep(0.9, 1.6, NZ[5].noise(aniso(P, [0, 0.3, -1], 70.0, 25.0), 7)) * m_br * (0.0 if AP.IS_COW else 1.0)
    white = white * (1 - 0.55 * spk[:, None]) + srgb2lin([150, 104, 72]) * (0.55 * spk[:, None])
    col = orange * M_or[:, None] + white * (1 - M_or[:, None])
    del orange, white, m_wgrey, m_dirt, m_br, spk, yw, zw, dt, db, hb

    # ---------------------------------------------------------------- head details
    # muzzle ring (lighter tan) around the nose pad
    dn = box_dist(P, LM["nose_min"], LM["nose_max"])
    m_ring = smoothstep(0.045 * sn, 0.01, dn) * headm * M_or
    col = col * (1 - 0.45 * m_ring[:, None]) + srgb2lin([212, 146, 94]) * (0.45 * m_ring[:, None])
    # eyelids (GiM: pale whitish-pink rim around a dark eye, then a soft darker ring into the coat), measured from
    # the real socket boundary (the socket is not concentric with the eyeball, so dE alone gives an uneven rim)
    near_eye = (dE < 0.03) & (headm > 0.05)
    dL = np.full(len(P), 1.0)
    if near_eye.any() and len(ctx.lid_pts):
        dL[near_eye] = min_dist_to_set(P[near_eye], ctx.lid_pts)
    m_lid = smoothstep(0.0034, 0.0016, dL) * headm
    m_lid2 = smoothstep(0.010, 0.0034, dL) * headm * (1 - m_lid)
    col = col * (1 - 0.5 * m_lid2[:, None]) + srgb2lin([70, 38, 22]) * (0.5 * m_lid2[:, None])
    col = col * (1 - 0.8 * m_lid[:, None]) + srgb2lin([226, 200, 186]) * (0.8 * m_lid[:, None])
    del m_lid2, near_eye
    # mouth line (dark, ~3 mm) along the Jaw-weight isoline, pale-pink lower lip just below it near the front
    m_mouth = np.zeros(len(P), np.float32); m_lip = np.zeros(len(P), np.float32)
    if ctx.mouth:
        mbox = (headm > 0.3) & (z < max(pl[:, 2].max() for pl in ctx.mouth) + 0.02) & \
               (y < max(pl[:, 1].max() for pl in ctx.mouth) + 0.01)
        if mbox.any():
            Pm = P[mbox]
            best_d = np.full(len(Pm), np.inf); best_t = np.zeros(len(Pm)); best_z = np.zeros(len(Pm))
            for pl in ctx.mouth:
                seglen = np.linalg.norm(np.diff(pl, axis=0), axis=1); cum = np.concatenate([[0.0], np.cumsum(seglen)])
                for i in range(len(pl) - 1):
                    t, d = seg_param(Pm, pl[i], pl[i + 1])
                    m = d < best_d
                    best_d[m] = d[m]; best_t[m] = (cum[i] + t[m] * seglen[i]) / cum[-1]
                    best_z[m] = pl[i][2] + t[m] * (pl[i + 1][2] - pl[i][2])
            taper = smoothstep(0.0, 0.25, best_t)                 # fades out toward the commissure
            m_mouth[mbox] = smoothstep(0.0017, 0.0007, best_d) * taper
            below = (Pm[:, 2] < best_z)
            m_lip[mbox] = smoothstep(0.0065, 0.004, best_d) * (1 - smoothstep(0.0017, 0.0007, best_d)) * below * \
                smoothstep(0.45, 0.8, best_t)
    col = col * (1 - 0.75 * m_lip[:, None]) + srgb2lin([220, 180, 160]) * (0.75 * m_lip[:, None])
    col = col * (1 - 0.85 * m_mouth[:, None]) + srgb2lin([60, 35, 25]) * (0.85 * m_mouth[:, None])
    # ears: inner side (old light part) pale pinkish tan, darker rim along the inner/outer boundary
    ear = ctx.ear_mask(P, w)
    inner = ear & (part == 1) & ctx.inner_side(P, Nr)
    outer = ear & (part != 1)
    m_in = np.zeros(len(P), np.float32); m_rim = np.zeros(len(P), np.float32)
    if inner.any():
        d_o = min_dist_to_set(ctx.ear6(P[inner], Nr[inner]), ctx.outer_pts)
        m_in[inner] = smoothstep(0.003, 0.012, d_o) * smoothstep(0.3, 0.6, w[inner, 10])   # soft at the ear base
        m_rim[inner] = smoothstep(0.009, 0.002, d_o)
    if outer.any() and len(ctx.inner_pts):
        m_rim[outer] = smoothstep(0.008, 0.001, min_dist_to_set(ctx.ear6(P[outer], Nr[outer]), ctx.inner_pts))
    C_EAR = srgb2lin([214, 170, 142])
    col = col * (1 - m_in[:, None]) + (C_EAR * (1 + 0.1 * strand)[:, None]) * m_in[:, None]
    col = col * (1 - 0.7 * m_rim[:, None]) + srgb2lin([112, 54, 24]) * (0.7 * m_rim[:, None])
    # soft pink blend of the hairy muzzle edge into the pad
    m_nb = smoothstep(0.012, 0.0, dn) * (part != 3) * headm
    col = col * (1 - 0.35 * m_nb[:, None]) + srgb2lin([216, 168, 140]) * (0.35 * m_nb[:, None])

    # ---------------------------------------------------------------- roughness & height (fur)
    rough = 0.80 + 0.03 * lf2 - 0.035 * strand - 0.02 * (1 - M_or)
    rough = rough * (1 - m_in) + 0.72 * m_in
    rough = rough * (1 - m_lid) + 0.55 * m_lid
    height = 0.5 + (0.16 + 0.06 * torso) * strand + 0.07 * clump
    # long hair: tail switch and forehead tuft read as clumped tufts (stronger clump + strand relief)
    m_long = np.maximum(m_sw, m_tuft)
    height = height + m_long * (0.06 * strand + 0.16 * clump)
    # mid-frequency skin relief the fur bump can carry (wavelength <~4 cm): loose transverse skin folds on the
    # lower neck / throat (GiM neck folds), strongest on the underside, fading toward the crest and the head
    n1h, n3t = ctx.neck_a, ctx.neck_b
    t_n, d_n = seg_param(P, n1h, n3t)
    ax_n = (n3t - n1h) / max(np.linalg.norm(n3t - n1h), 1e-9)
    fold = np.sin(2 * np.pi * ((P - n1h) @ ax_n / 0.034 + 0.35 * NZ[9].noise(P * 18.0, 14)))
    m_fold = smoothstep(0.35, 0.8, wn) * smoothstep(0.1, 0.3, t_n) * (1 - smoothstep(0.75, 0.95, t_n)) * \
        smoothstep(0.1, -0.4, nzn) * (1 - m_long)
    height = height + 0.13 * fold * m_fold
    height = height - 0.18 * m_mouth                               # the mouth line is a crease
    del m_long, t_n, d_n, fold, m_fold, m_sw, m_tuft

    # ---------------------------------------------------------------- hooves (orig_part 2): warm horn, clearly darker
    # than the white pastern (GiM HD frames: hoof ~20 % darker than the pastern), a lighter coronet band at the hair
    # line, a dark cleft line down the front between the claws, vertical growth streaks, dirtier toward the ground
    hi = np.flatnonzero(part == 2)
    if len(hi):
        Ph = P[hi]; zh = Ph[:, 2]
        ring = np.sin(2 * np.pi * (zh / 0.0035 + 0.6 * NZ[6].noise(Ph * 60.0, 8)))
        streak = NZ[6].noise(Ph * np.array([220.0, 220.0, 25.0]), 13)
        hc = srgb2lin([74, 70, 72] if AP.IS_COW else [158, 132, 110]) * (1.0 + 0.08 * NZ[6].fbm(Ph, 40.0, 2) + 0.03 * ring + 0.05 * streak)[:, None]
        dirt = smoothstep(0.03, 0.0, zh)
        hc = hc * (1 - 0.30 * dirt)[:, None] + srgb2lin([120, 100, 85]) * (0.18 * dirt)[:, None]
        cor = np.zeros(len(hi), np.float32)
        if len(ctx.hoof_rim):
            cor = smoothstep(0.0055, 0.0035, min_dist_to_set(Ph, ctx.hoof_rim)).astype(np.float32)
        hc = hc * (1 - 0.8 * cor[:, None]) + srgb2lin([98, 92, 92] if AP.IS_COW else [178, 158, 138]) * (0.8 * cor[:, None])
        y_split = 0.5 * (elbow[1] + hip[1])
        cx = np.zeros(len(hi))
        for (sx, fr), v in ctx.hoof_cx.items():
            cx[(np.sign(Ph[:, 0]) == sx) & ((Ph[:, 1] < y_split) == fr)] = v
        cleft = smoothstep(0.0013, 0.0006, np.abs(Ph[:, 0] - cx)) * smoothstep(-0.2, -0.5, Nr[hi, 1]) * (1 - cor)
        hc = hc * (1 - 0.85 * cleft[:, None]) + srgb2lin([60, 45, 35]) * (0.85 * cleft[:, None])
        col[hi] = hc
        rough[hi] = 0.55 + 0.05 * NZ[6].noise(Ph * 30.0, 10) + 0.1 * dirt + 0.15 * cor
        height[hi] = 0.5 + 0.05 * ring + 0.05 * NZ[6].noise(Ph * 90.0, 11) - 0.25 * cleft
    # ---------------------------------------------------------------- nose pad (orig_part 3)
    ni = np.flatnonzero(part == 3)
    if len(ni):
        Pn = P[ni]
        peb = np.clip(1.0 - np.abs(NZ[7].noise(Pn * 330.0, 9)), 0, 1) ** 1.5   # pebbled plates + grooves
        nc = srgb2lin([204, 166, 160] if AP.IS_COW else [226, 186, 162]) * (0.95 + 0.05 * peb + 0.03 * NZ[7].noise(Pn * 60.0, 12))[:, None]
        nc_c = LM["nose_c"]; nmin, nmax = LM["nose_min"], LM["nose_max"]
        nrad = 0.5 * (nmax - nmin)
        nost = np.zeros(len(ni), np.float32); nin = np.zeros(len(ni), np.float32)
        for sx in (-1, 1):   # nostrils: pink surround, darker opening (no nostril geometry on the mesh)
            # GiM: large dark comma nostrils, ~1/4 of the pad width each, at the sides of the pad
            c = np.array([sx * 0.60 * nrad[0], nmin[1] + 0.3 * nrad[1], nc_c[2] + 0.02 * nrad[2]])
            q = Pn - c
            zt = q[:, 2] / nrad[2]
            q[:, 0] += sx * (0.45 * q[:, 2] - 0.35 * nrad[0] * zt * zt)   # comma: leans out at the bottom, head curls in
            e = ell(q, np.zeros(3), np.array([0.30, 0.72, 0.72]) * nrad)
            e = e / (1.0 + 0.35 * np.clip(zt, 0, 1))  # wider rounded head at the top-inside, tapering tail below
            nost = np.maximum(nost, smoothstep(1.3, 0.9, e))
            nin = np.maximum(nin, smoothstep(0.95, 0.6, e))
        nc = nc * (1 - 0.55 * nost[:, None]) + srgb2lin([204, 132, 124]) * (0.55 * nost[:, None])
        nc = nc * (1 - 0.95 * nin[:, None]) + srgb2lin([58, 32, 32]) * (0.95 * nin[:, None])
        col[ni] = nc
        rough[ni] = 0.50 - 0.06 * peb - 0.12 * nost
        height[ni] = 0.42 + 0.28 * peb * (1 - nin) - 0.3 * nin
    # ---------------------------------------------------------------- cow only: horns (5) and udder + teats (6)
    hi = np.flatnonzero(part == AP.PART_HORN)
    if len(hi) and ctx.horn:
        Ph = P[hi]; t = np.zeros(len(hi))
        for sx, (hb_, ht_) in ctx.horn.items():
            m = np.sign(Ph[:, 0]) == sx
            ax = ht_ - hb_; t[m] = np.clip(((Ph[m] - hb_) @ ax) / max(float(ax @ ax), 1e-9), 0, 1)
        ring = np.sin(2 * np.pi * (t * 9.0 + 0.3 * NZ[6].noise(Ph * 80.0, 15)))
        streak = NZ[6].noise(Ph * np.array([160.0, 160.0, 160.0]), 16)
        hcol = srgb2lin([228, 212, 176]) * (1 - smoothstep(0.35, 0.8, t))[:, None] + \
            srgb2lin([204, 176, 132]) * smoothstep(0.35, 0.8, t)[:, None]
        tip = smoothstep(0.72, 0.97, t)[:, None]
        hcol = hcol * (1 - tip) + srgb2lin([84, 72, 62]) * tip
        hcol = hcol * (1 + 0.04 * streak + 0.03 * ring * (1 - smoothstep(0.3, 0.5, t)))[:, None]
        col[hi] = hcol
        rough[hi] = 0.42 + 0.06 * streak - 0.08 * tip[:, 0]
        height[hi] = 0.5 + 0.08 * ring * (1 - smoothstep(0.3, 0.5, t)) + 0.03 * streak
    ui = np.flatnonzero(part == AP.PART_UDDER)
    if len(ui):
        Pu = P[ui]
        teat = smoothstep(ctx.teat_z + 0.004, ctx.teat_z - 0.004, Pu[:, 2])
        tipm = smoothstep(ctx.udder_zmin + 0.012, ctx.udder_zmin + 0.002, Pu[:, 2])
        mot = NZ[7].fbm(Pu, 30.0, 2); vein = smoothstep(0.75, 0.95, 1 - np.abs(NZ[6].noise(Pu * np.array([25.0, 12.0, 40.0]), 17)))
        ucol = srgb2lin([226, 186, 176]) * (1 + 0.05 * mot)[:, None]
        ucol = ucol * (1 - 0.25 * vein[:, None]) + srgb2lin([196, 150, 150]) * (0.25 * vein[:, None])
        ucol = ucol * (1 - teat[:, None]) + srgb2lin([216, 152, 142]) * teat[:, None]
        ucol = ucol * (1 - 0.6 * tipm[:, None]) + srgb2lin([170, 110, 104]) * (0.6 * tipm[:, None])
        # the udder top is haired like the belly it grows from: blend back to the coat colour near the body
        haired = smoothstep(ctx.udder_top - 0.05, ctx.udder_top - 0.01, Pu[:, 2])[:, None]
        col[ui] = ucol * (1 - haired) + col[ui] * haired
        rough[ui] = 0.58 + 0.04 * mot - 0.08 * teat
        height[ui] = 0.5 + 0.03 * mot - 0.04 * vein + haired[:, 0] * (height[ui] - 0.5)
    return np.clip(col, 0, 1), np.clip(rough, 0.02, 1), np.clip(height, 0, 1)


def estimate_texel(pos, cov):
    """median metric distance between horizontally adjacent covered texels"""
    both = cov[:, 1:] & cov[:, :-1]
    d = np.linalg.norm(pos[:, 1:][both] - pos[:, :-1][both], axis=1)
    return float(np.median(d))


# =====================================================================================================
# quick orthographic numpy preview (splats covered texels, z-buffered)
# =====================================================================================================
def preview(path, P, Nr, col, LM):
    from PIL import Image, ImageDraw
    views = [("side (R)", [0, -1, 0], [0, 0, 1], [1, 0, 0], 300),
             ("otherside (L)", [0, 1, 0], [0, 0, 1], [-1, 0, 0], 300),
             ("top", [0, -1, 0], [1, 0, 0], [0, 0, -1], 300),
             ("front", [1, 0, 0], [0, 0, 1], [0, 1, 0], 300),
             ("back", [-1, 0, 0], [0, 0, 1], [0, -1, 0], 300),
             ("head 3/4", [0.6, -0.8, 0], [0, 0, 1], [0.8, 0.6, 0], 900)]
    light = np.array([-0.4, -0.5, 0.75]); light /= np.linalg.norm(light)
    srgb = lin2srgb(col)
    tiles = []
    for name, r, u, f, scale in views:
        r, u, f = (np.array(v, np.float64) for v in (r, u, f))
        W, H = 560, 360
        if name.startswith("head"):
            c = LM["eyes"]["L"][0] * np.array([0, 1, 1]) + np.array([0, -0.02, 0.0])
        else:
            c = 0.5 * (LM["bbmin"] + LM["bbmax"])
        pu = ((P - c) @ r) * scale + W / 2
        pv = H / 2 - ((P - c) @ u) * scale
        dep = (P - c) @ f
        facing = (Nr @ f) < 0.15
        ok = facing & (pu >= 0) & (pu < W - 1) & (pv >= 0) & (pv < H - 1)
        o = np.argsort(-dep[ok])
        iu = pu[ok][o].astype(np.int64); iv = pv[ok][o].astype(np.int64)
        lam = np.clip(Nr[ok][o] @ light, 0, 1) * 0.55 + 0.5
        cc = np.clip(srgb[ok][o] * lam[:, None], 0, 1)
        img = np.full((H, W, 3), 0.85)
        for du in (0, 1):
            for dv in (0, 1):
                img[np.minimum(iv + dv, H - 1), np.minimum(iu + du, W - 1)] = cc
        im = Image.fromarray((img * 255).astype(np.uint8))
        ImageDraw.Draw(im).text((4, 4), name, fill=(0, 0, 0))
        tiles.append(im)
    sheet = Image.new("RGB", (560 * 3, 360 * 2))
    for i, t in enumerate(tiles):
        sheet.paste(t, ((i % 3) * 560, (i // 3) * 360))
    sheet.save(path)


# =====================================================================================================
# eye texture (planar eye UV: centre = cornea, u horizontal, v up, radius 0.5 = eyeball radius)
# =====================================================================================================
def eye_texture(res, seed):
    nz = Perlin3(seed + 100)
    v, u = (np.mgrid[0:res, 0:res] + 0.5) / res           # Blender row order (row 0 = v 0)
    du, dv = u - 0.5, v - 0.5
    r = np.sqrt(du * du + dv * dv)
    ang = np.arctan2(dv, du)
    ri = np.sqrt((du / 0.372) ** 2 + (dv / 0.350) ** 2)    # 1 at the iris edge (slightly wide)
    rp = (np.abs(du / 0.165) ** 2.6 + np.abs(dv / 0.070) ** 2.6) ** (1 / 2.6)   # horizontal pupil
    flat = lambda a: a.reshape(-1)
    # radial iris fibres: 3D noise on a cylinder (seamless around the angle)
    q = np.stack([np.cos(ang) * 9.0, np.sin(ang) * 9.0, ri * 1.5], -1).reshape(-1, 3)
    fib = nz.noise(q * np.array([1.0, 1.0, 1.0]), 0).reshape(res, res)
    q2 = np.stack([np.cos(ang) * 30.0, np.sin(ang) * 30.0, ri * 3.0], -1).reshape(-1, 3)
    fib2 = nz.noise(q2, 1).reshape(res, res)
    blot = nz.noise(np.stack([du * 14, dv * 14, np.zeros_like(du)], -1).reshape(-1, 3), 2).reshape(res, res)
    # GiM: big DARK amber-brown eyes (the old 116,58,20 read light orange behind the glossy cornea)
    C_IRIS = srgb2lin([74, 40, 20]); C_IRIS_IN = srgb2lin([96, 54, 26]); C_IRIS_OUT = srgb2lin([44, 24, 12])
    C_LIMB = srgb2lin([30, 16, 8]); C_PUP = srgb2lin([7, 5, 4]); C_SCL = srgb2lin([150, 118, 96])
    C_RIM = srgb2lin([34, 22, 17])
    t_in = smoothstep(0.75, 0.25, (ri - 0.2) / 0.8)[..., None]
    iris = C_IRIS * (1 - t_in) + C_IRIS_IN * t_in
    t_out = smoothstep(0.6, 0.95, ri)[..., None]
    iris = iris * (1 - t_out) + C_IRIS_OUT * t_out
    iris = iris * (1 + 0.22 * fib + 0.10 * fib2 + 0.06 * blot)[..., None]
    limb = smoothstep(0.86, 1.0, ri)[..., None]
    iris = iris * (1 - limb) + C_LIMB * limb
    col = iris
    # corpora nigra: small dark bumps on the upper pupil margin (ungulate eye)
    cn = np.zeros_like(r)
    for cx in (-0.07, -0.025, 0.02, 0.065):
        cn = np.maximum(cn, smoothstep(1.0, 0.6, np.sqrt(((du - cx * 1.1) / 0.03) ** 2 + ((dv - 0.064) / 0.024) ** 2)))
    col = col * (1 - 0.8 * cn[..., None]) + C_PUP * (0.8 * cn[..., None])
    pup = smoothstep(1.06, 0.94, rp)[..., None]
    col = col * (1 - pup) + C_PUP * pup
    scl = smoothstep(0.99, 1.04, ri)[..., None]
    sclc = C_SCL * (1 + 0.05 * fib2)[..., None]
    col = col * (1 - scl) + sclc * scl
    rim = smoothstep(0.385, 0.42, r)[..., None]
    col = col * (1 - rim) + C_RIM * rim
    return np.clip(lin2srgb(col), 0, 1).astype(np.float32)


# =====================================================================================================
# materials
# =====================================================================================================
def load_image(path, name, noncolor):
    img = bpy.data.images.get(name)
    if img is not None:
        bpy.data.images.remove(img)
    img = bpy.data.images.load(path, check_existing=False)
    img.name = name
    img.colorspace_settings.name = "Non-Color" if noncolor else "sRGB"
    return img


def build_materials(tex):
    """tex: dict name -> absolute path"""
    mb = bpy.data.materials.get("M_Calf_Body") or bpy.data.materials.new("M_Calf_Body")
    me_ = bpy.data.materials.get("M_Calf_Eye") or bpy.data.materials.new("M_Calf_Eye")
    for m in (mb, me_):
        m.use_nodes = True
        m.node_tree.nodes.clear()
    # ---- body
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
    ao = tnode(TEX + "_AO", True, (-400, -600), "AO (engine occlusion slot; not used by Principled)")
    nmap = nd.new("ShaderNodeNormalMap"); nmap.space = "TANGENT"; nmap.uv_map = "UVMap"; nmap.location = (-50, -300)
    ln.new(bc.outputs["Color"], bs.inputs["Base Color"])
    ln.new(ro.outputs["Color"], bs.inputs["Roughness"])
    ln.new(nm.outputs["Color"], nmap.inputs["Color"])
    ln.new(nmap.outputs["Normal"], bs.inputs["Normal"])
    bs.inputs["Specular IOR Level"].default_value = 0.4
    ln.new(bs.outputs[0], out.inputs["Surface"])
    # ---- eye
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
    # every LOD uses the same two materials in slots 0/1
    for o in bpy.data.objects:
        if o.type == "MESH" and re.match(r"Calf_LOD\d+$", o.name):
            mats = o.data.materials
            while len(mats) < 2:
                mats.append(None)
            mats[0] = mb; mats[1] = me_
    return mb, me_


# =====================================================================================================
# main
# =====================================================================================================
def parse_args(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--tex-dir", required=True)
    ap.add_argument("--res", type=int, default=2048)
    ap.add_argument("--eye-res", type=int, default=1024)
    ap.add_argument("--ao-res", type=int, default=0, help="AO bake res (default res/2, max 2048)")
    ap.add_argument("--ao-samples", type=int, default=128)
    ap.add_argument("--ao-dist", type=float, default=0.25, help="AO ray distance in meters")
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--cache", default=None, help="npz of the data bakes (loaded if present, else written)")
    ap.add_argument("--preview", default=None, help="write a quick orthographic numpy preview PNG")
    ap.add_argument("--pack", action="store_true", help="pack images into the .blend")
    ap.add_argument("--textures-only", action="store_true", help="dev: skip normal bake + blend save")
    return ap.parse_args(argv)


def main(argv):
    a = parse_args(argv)
    inp = os.path.abspath(a.inp); out = os.path.abspath(a.out); tex_dir = os.path.abspath(a.tex_dir)
    os.makedirs(tex_dir, exist_ok=True)
    R = a.res
    ao_res = a.ao_res or min(2048, max(512, R // 2))
    bpy.ops.wm.open_mainfile(filepath=inp)
    arm = bpy.data.objects["CalfRig"]
    lod0 = bpy.data.objects["Calf_LOD0"]
    rest = rest_mesh(lod0)
    co, part_f, ls, lt, lv, Wv = mesh_arrays(lod0, rest)
    log("rest mesh: %d verts, %d faces" % (len(rest.vertices), len(rest.polygons)))
    Wj = group_fraction(lod0, rest, "Jaw")
    LM = compute_landmarks(arm, lod0, co, part_f, ls, lt, lv, Wv, Wj)
    log("landmarks", lm_summary(LM))

    D = None
    if a.cache and os.path.exists(a.cache):
        z = np.load(a.cache)
        if int(z["res"]) == R and z["w"].shape[-1] == len(REGIONS):
            D = {k: z[k] for k in z.files}
            log("loaded bake cache", a.cache)
    if D is None:
        baker = Baker(lod0, rest, Wv)
        D = bake_data(baker, R, ao_res, a.ao_samples, a.ao_dist, LM["bbmin"], LM["bbmax"])
        baker.cleanup()
        if a.cache:
            np.savez(a.cache, res=R, **D)
            log("wrote bake cache", a.cache)
    cov = D["cov"]
    log("coverage %.1f%%" % (100 * cov.mean()))
    texel = estimate_texel(D["pos"], cov)
    P = D["pos"][cov].astype(np.float64)
    Nr = D["nrm"][cov].astype(np.float32)
    part = D["part"][cov].astype(np.int32)
    wreg = D["w"][cov].astype(np.float32)
    for k in ("pos", "nrm", "part", "w"):      # free the full-res float bakes (4096 memory)
        D.pop(k, None)
    col, rough, height, dbg = coat_pattern(P, Nr, part, wreg, LM, texel, a.seed)
    if a.preview:
        preview(a.preview, P, Nr, col, LM)
        log("wrote preview", a.preview)
    del P, Nr, wreg, part

    # ------------------------------------------------------------------ assemble + pad textures
    import cv2

    near = nearest_index(cov)

    def to_img(vals, C):
        img = np.zeros((R, R, C), np.float32)
        img[cov] = vals.reshape(-1, C)
        return fill_background(img, cov, near)

    paths = {}

    def out_path(name):
        p = os.path.join(tex_dir, name + ".png"); paths[name] = p
        return p

    base = to_img(lin2srgb(col).astype(np.float32), 3)
    save_png(out_path(TEX + "_BaseColor"), base)
    rough_img = to_img(rough, 1)[..., 0]
    save_png(out_path(TEX + "_Roughness"), rough_img)
    height_img = to_img(height, 1)[..., 0]
    save_png(out_path(TEX + "_Height"), height_img, bits=16)
    ao_lo, ao_cov = D["ao_lo"], D["ao_lo_cov"].astype(bool)
    ao_lo = blur_masked(ao_lo, ao_cov, 0.8)
    ao_lo = fill_background(ao_lo[..., None], ao_cov)[..., 0]
    ao_up = cv2.resize(ao_lo, (R, R), interpolation=cv2.INTER_LINEAR)
    ao_img = fill_background(np.clip(ao_up, 0, 1)[..., None], cov, near)[..., 0]
    save_png(out_path(TEX + "_AO"), ao_img)
    smooth = 1.0 - rough_img
    zero = np.zeros_like(smooth)
    save_png(out_path(TEX + "_MaskMap"), np.stack([zero, ao_img, np.ones_like(smooth), smooth], -1))
    save_png(out_path(TEX + "_MetallicSmoothness"), np.stack([zero, zero, zero, smooth], -1))
    eye = eye_texture(a.eye_res, a.seed)
    save_png(out_path(TEX_EYE + "_BaseColor"), eye)
    log("wrote colour/roughness/AO/mask/eye textures")
    if a.textures_only:
        return a, LM, D

    # ------------------------------------------------------------------ tangent-space normal bake
    del base, rough_img, ao_img, ao_up, ao_lo, smooth, zero, eye, col, rough, height
    D.clear()
    baker = Baker(lod0, rest, Wv)
    dist = 0.6 / dbg["fa"]      # ~2.6 mm at 4K: readable hair strands (0.2/fa gave a 5 deg mean tilt, invisible)
    nb = baker.bake_normal(height_img, dist, R)
    baker.cleanup()
    n = nb[..., :3] * 2 - 1
    n /= np.maximum(np.linalg.norm(n, axis=-1, keepdims=True), 1e-6)
    n = n * 0.5 + 0.5
    n = fill_background(n.astype(np.float32), cov, near)
    save_png(out_path(TEX + "_Normal"), n)
    nc = n[cov]
    log("normal map mean RGB (0-255):", np.round(nc.mean(0) * 255, 1).tolist(),
        "std:", np.round(nc.std(0) * 255, 1).tolist(), "bump distance %.5f m" % dist)

    # ------------------------------------------------------------------ materials + save
    bpy.data.meshes.remove(rest)
    build_materials(paths)
    for coll in (bpy.data.images, bpy.data.meshes, bpy.data.materials, bpy.data.worlds):   # temporaries only
        for idb in list(coll):
            if idb.name.startswith(("CalfBake", "_bake")) and idb.users == 0:
                coll.remove(idb)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    if a.pack:
        for im in bpy.data.images:
            if im.name.startswith(TEX):
                im.pack()
    bpy.ops.wm.save_as_mainfile(filepath=out)
    if not a.pack:
        bpy.ops.file.make_paths_relative()
        bpy.ops.wm.save_mainfile()
    import resource
    log("saved", out, "| peak RSS %.2f GB" % (resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6))
    for k, p in sorted(paths.items()):
        from PIL import Image
        with Image.open(p) as im:
            log("  %-28s %s %s %.1f MB" % (k, im.size, im.mode, os.path.getsize(p) / 1e6))
    return a, LM, D


if __name__ == "__main__":
    argv = sys.argv[1:]
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    main(argv)
