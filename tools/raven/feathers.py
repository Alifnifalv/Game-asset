"""Feather geometry for the raven: every flight feather, covert, rectrix, hackle and bristle is an explicit closed
strip (a thin lens-section shell: top and bottom sheets that share their outline), rigid on one bone.

  Feather(...)          one feather: base point, rachis direction, dorsal normal (world, bind pose), length, vane
                        widths, outline shape, curvature, camber, thickness, atlas slot, bone
  strip(f, nt, ns)      -> (V (n,3), F (m,3) int, UV (n,2)) closed mesh of the feather; nt segments along, ns across
                        each half vane (LOD control). Top sheet UV = the slot; the bottom sheet mirrors it (same
                        texels: the underside of a raven feather is the same black, a little greyer - the texture
                        pass darkens it through the vertex normal, not the UV).

Frame of a feather (all unit vectors, bind pose):  d = along the rachis (base -> tip), n = dorsal normal, s = n x d
(points to the feather's LEFT when seen from above with the tip away). For a left-wing primary pointing out and back
that is toward the leading edge; the 'outer' vane is the leading-edge side for flight feathers ('outer' = -s side is
chosen per feather with `outer_sign`).

Shape:
  width(t) of each half vane, t in [0, 1] along the rachis:
      calamus (bare quill) for t < t0; the vane widens over [t0, t0 + grow] (grow 0.12; coverts taper longer), holds, then the tip rounds off with
      shape `tip` ('round', 'point', 'lance'); emarginated feathers narrow to `emarg_w` of the width beyond
      `emarg_t` (the outer vane only for P9-P10 notches, both vanes for the inner notch).
  curvature: the rachis bends ventrally (toward -n) by curve * L * t^2, and sideways by sweep * L * t^2 (+ = to s);
  camber: the vane edges drop by camber * w^2 (ventral), so each feather is a shallow arch;
  thickness: a lens section, max `thick` at the rachis, 0 at the vane edge (the edge vertices are shared).
"""
import math
import numpy as np


class Feather:
    __slots__ = ("name", "group", "bone", "base", "d", "n", "length", "w_in", "w_out", "t0", "tip", "emarg_t",
                 "emarg_w", "emarg_both", "curve", "sweep", "camber", "thick", "slot", "slot_under", "layer",
                 "outer_sign", "twist", "lod", "grow", "skin")

    def __init__(self, name, group, bone, base, d, n, length, w_in, w_out, t0=0.08, tip="round", emarg_t=None,
                 emarg_w=0.55, emarg_both=False, curve=0.05, sweep=0.0, camber=0.12, thick=0.0012, slot=None,
                 layer=0, outer_sign=1.0, twist=0.0, lod=2, grow=0.12, skin=None):
        self.name, self.group, self.bone = name, group, bone
        self.base = np.asarray(base, float)
        d = np.asarray(d, float); d = d / np.linalg.norm(d)
        n = np.asarray(n, float); n = n - d * (n @ d); n = n / np.linalg.norm(n)
        self.d, self.n = d, n
        self.length, self.w_in, self.w_out, self.t0, self.tip = length, w_in, w_out, t0, tip
        self.emarg_t, self.emarg_w, self.emarg_both = emarg_t, emarg_w, emarg_both
        self.curve, self.sweep, self.camber, self.thick = curve, sweep, camber, thick
        self.slot = slot if slot is not None else (0.0, 0.0, 1.0, 1.0)      # (u0, v0, u1, v1) in the atlas
        self.slot_under = self.slot                                           # the underside's slot
        self.layer, self.outer_sign, self.twist, self.lod = layer, outer_sign, twist, lod
        self.grow = grow                                   # vane growth span after t0 (a longer span = a tapered root)
        # optional constant multi-bone skin [(bone, weight), ...] (<= 4, sum 1) instead of rigid on `bone`: the wing
        # covert pivot bones (raven_anatomy.COVERT_GROUPS) blended so the feather turns about its own root
        self.skin = skin

    @property
    def s(self):
        return np.cross(self.n, self.d)

    def tip_point(self):
        return self.base + self.d * self.length - self.n * self.curve * self.length


def _smooth(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def half_width(f, t, outer):
    """width (m) of one half vane at t (array); outer = True for the outer (narrow) vane"""
    w = f.w_out if outer else f.w_in
    t = np.asarray(t, float)
    grow = _smooth(f.t0, f.t0 + f.grow, t)
    if f.tip == "round":
        end = np.sqrt(np.clip(1.0 - ((t - 0.80) / 0.20).clip(0, None) ** 2, 0, 1))
    elif f.tip == "point":
        end = np.clip((1.0 - t) / 0.35, 0, 1) ** 0.8
    elif f.tip == "lance":                    # lanceolate: widest at 40 %, tapering to a sharp point
        end = np.clip(np.where(t < 0.4, 1.0, (1.0 - t) / 0.6), 0, 1) ** 1.2
    else:
        raise ValueError(f.tip)
    wt = w * grow * end
    if f.emarg_t is not None and (outer or f.emarg_both):
        wt = wt * (1.0 - (1.0 - f.emarg_w) * _smooth(f.emarg_t - 0.04, f.emarg_t + 0.04, t))
    return wt


def strip(f, nt=14, ns=3):
    """closed thin strip: a top sheet (UV in f.slot) and a bottom sheet (UV in f.slot_under, mirrored in u) that meet
    along the outline (duplicated vertices: a UV seam), joined at the quill end.  Returns V (n,3), F (m,3), UV (n,2),
    and a per-face flag `under` (1 on the bottom sheet)."""
    L = f.length
    t = 1.0 - (1.0 - np.linspace(0.0, 1.0, nt + 1)) ** 1.4               # denser toward the rounded tip
    wl = np.maximum(half_width(f, t, outer=(f.outer_sign < 0)), 0.0010)     # the -s side (a < 0)
    wr = np.maximum(half_width(f, t, outer=(f.outer_sign > 0)), 0.0010)     # the +s side (a > 0)
    wl[-1] = wr[-1] = 0.0
    d, n, s = f.d, f.n, f.s
    a = np.linspace(-1.0, 1.0, 2 * ns + 1)                                 # across: -1 edge, 0 rachis, +1 edge
    W = np.where(a[None, :] < 0, wl[:, None], wr[:, None]) * np.abs(a)[None, :]    # (nt+1, na) signed-less widths
    Wsgn = W * np.sign(a)[None, :]
    tw = np.radians(f.twist) * t
    si = s[None, :] * np.cos(tw)[:, None] + n[None, :] * np.sin(tw)[:, None]
    ni = n[None, :] * np.cos(tw)[:, None] - s[None, :] * np.sin(tw)[:, None]
    C = (f.base[None, :] + d[None, :] * (L * t)[:, None] - n[None, :] * (f.curve * L * t ** 2)[:, None]
         + s[None, :] * (f.sweep * L * t ** 2)[:, None])
    wmax = max(f.w_in, f.w_out, 1e-6)
    drop = f.camber * W ** 2 / wmax                                        # vane edges lower (ventral)
    hh = 0.5 * f.thick * (1.0 - a[None, :] ** 2) * (1.0 - 0.6 * t)[:, None]
    base = C[:, None, :] + si[:, None, :] * Wsgn[..., None] - ni[:, None, :] * drop[..., None]
    Vt = base + ni[:, None, :] * hh[..., None]
    Vb = base - ni[:, None, :] * hh[..., None]
    na = len(a)
    ucoord = 0.5 + 0.5 * Wsgn / wmax                                       # true width scale: narrow vanes stay narrow
    def uv(slot, mirror):
        u0, v0, u1, v1 = slot
        uu = (1.0 - ucoord) if mirror else ucoord
        return np.stack([u0 + (u1 - u0) * uu, v0 + (v1 - v0) * np.repeat(t[:, None], na, 1)], -1)
    UVt, UVb = uv(f.slot, False), uv(f.slot_under, True)
    it = np.arange((nt + 1) * na).reshape(nt + 1, na)
    ib = it + it.size
    # the tip row collapses to one vertex per sheet (the rachis column): no zero-area triangles, no zero UV area
    it[nt, :] = it[nt, ns]
    ib[nt, :] = ib[nt, ns]
    V = np.concatenate([Vt.reshape(-1, 3), Vb.reshape(-1, 3)])
    UV = np.concatenate([UVt.reshape(-1, 2), UVb.reshape(-1, 2)])
    i0, j0 = np.meshgrid(np.arange(nt), np.arange(na - 1), indexing="ij")
    i0, j0 = i0.ravel(), j0.ravel()
    a0, a1, b0, b1 = it[i0, j0], it[i0, j0 + 1], it[i0 + 1, j0], it[i0 + 1, j0 + 1]
    Ft = np.concatenate([np.stack([a0, a1, b1], 1), np.stack([a0, b1, b0], 1)])
    a0, a1, b0, b1 = ib[i0, j0], ib[i0, j0 + 1], ib[i0 + 1, j0], ib[i0 + 1, j0 + 1]
    Fb = np.concatenate([np.stack([a0, b1, a1], 1), np.stack([a0, b0, b1], 1)])
    # the quill end stays open (it sits in the skin or under the coverts); closing it would join two atlas slots
    F = np.concatenate([Ft, Fb])
    under = np.concatenate([np.zeros(len(Ft), np.int8), np.ones(len(Fb), np.int8)])
    # the tip row collapses to one point per sheet: drop the zero-area triangles there
    keep = (F[:, 0] != F[:, 1]) & (F[:, 1] != F[:, 2]) & (F[:, 0] != F[:, 2])
    F, under = F[keep], under[keep]
    # compact: drop the tip-row vertices that are no longer referenced
    used = np.unique(F)
    remap = -np.ones(len(V), np.int64); remap[used] = np.arange(len(used))
    V, UV, F = V[used], UV[used], remap[F]
    # the top sheet must face +n: flip everything if the winding came out reversed
    tri = V[F[:4]]
    nrm = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]).sum(0)
    if np.dot(nrm, n) < 0:
        F = F[:, ::-1]
    return V, F, UV, under


def signed_volume(V, F):
    tri = V[F]
    return float(np.einsum("ij,ij->i", tri[:, 0], np.cross(tri[:, 1], tri[:, 2])).sum() / 6.0)
