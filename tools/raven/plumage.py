"""The raven's feathers in the bind pose: every Feather (tools/raven/feathers.py) with its bone, atlas slot and LOD.

  plumage(skin=None) -> list[Feather]   (skin: callable P -> SDF distance of the body, used to seat the throat hackles
                                         and the nasal bristles on the surface; None = raven_anatomy.body_prims())

Groups (spec 3.4-3.6, 4.3-4.8): remiges (P1-P10, S1-S6, T1-T3; one bone each), greater secondary / greater primary /
median coverts (ride the bone of the remex they overlie, rooted at its base, so they fan and fold with it), lesser and
marginal coverts (the leading-edge band: a constant blend of the covert pivot bones Cov{U,F,H}1-4.X, so each turns
about its own root in the fold: raven_anatomy.COVERT_GROUPS, cov_skin), the two coverts either side of the elbow
widened over the Tert1 / Sec6 gap, alula, underwing coverts (arm), scapulars (Shoulder, three rows, inner on top),
rectrices R1-R6 (one bone each),
upper tail coverts (Tail), throat hackles (Throat, 7 staggered rows with jitter: the shaggy beard), nasal bristles
(Head, a 3-row tuft lying on the bill base), trousers (Shin, group 'trouser', slot hackle_b).

Stacking (dorsal, spread wing): coverts > T3 > T2 > T1 > S6 ... S1 > P1 ... P10 (LAYER_STEP apart along N_WING);
tail R1 on top ... R6 lowest.

Atlas: the feather material has one texture (T_Raven_Feather_*); SLOTS maps a slot name to (u0, v0, u1, v1). Many
feathers share a slot (the outline is geometry; the slot carries the vane / rachis pattern). '_b' slots are the
undersides (paler, satin grey: spec 5.2).
"""
import numpy as np
import raven_anatomy as A
from feathers import Feather

V = A.V
unit = A.unit

# ------------------------------------------------------------------------------------------------ atlas slots
# 16 columns x 2 rows of 256 x 2048 px on a 4096 atlas (u = across the vane, v = along the rachis). Short feathers use
# quarter slots (256 x 512). Slot rectangles are in UV (v up).
def _col(c, r, q=None):
    u0, u1 = c / 16.0, (c + 1) / 16.0
    v0, v1 = r * 0.5, r * 0.5 + 0.5
    if q is not None:                                   # quarter of the column height
        v0, v1 = v0 + q * 0.125, v0 + (q + 1) * 0.125
    pad = 2.0 / 4096
    return (u0 + pad, v0 + pad, u1 - pad, v1 - pad)


SLOTS = {
    "prim_a": _col(0, 0), "prim_b": _col(1, 0), "prim_c": _col(2, 0), "prim_u": _col(3, 0),
    "sec_a": _col(4, 0), "sec_b": _col(5, 0), "sec_u": _col(6, 0),
    "tert_a": _col(7, 0), "tert_u": _col(8, 0),
    "rect_a": _col(9, 0), "rect_b": _col(10, 0), "rect_u": _col(11, 0),
    "gcov_a": _col(12, 0, 0), "gcov_b": _col(12, 0, 1), "gcov_c": _col(12, 0, 2), "gcov_u": _col(12, 0, 3),
    "pcov_a": _col(13, 0, 0), "pcov_b": _col(13, 0, 1), "mcov_a": _col(13, 0, 2), "mcov_b": _col(13, 0, 3),
    "scap_a": _col(14, 0, 0), "scap_b": _col(14, 0, 1), "utc_a": _col(14, 0, 2), "alula": _col(14, 0, 3),
    "hackle_a": _col(15, 0, 0), "hackle_b": _col(15, 0, 1), "bristle": _col(15, 0, 2), "ucov": _col(15, 0, 3),
}
SLOT_KIND = {k: k.split("_")[0] for k in SLOTS}        # prim / sec / tert / rect / gcov / pcov / mcov / scap / ...


def _slot(prefix, i, n):
    keys = [k for k in SLOTS if k.startswith(prefix + "_") and not k.endswith("_u")]
    return keys[i % len(keys)] if keys else prefix


REMEX_KIND = lambda name: "prim" if name.startswith("Prim") else ("sec" if name.startswith("Sec") else "tert")


def _outer_sign(f, outer_dir):
    """+1 when the outer (narrow) vane is on the +s side of the feather"""
    return 1.0 if float(np.dot(f.s, outer_dir)) > 0 else -1.0


def remiges(s):
    F = []
    sx = 1.0 if s == "L" else -1.0
    names = [r[0] for r in A.REMIGES]
    for i, (name, base, tip, L, W, outer, emarg, par) in enumerate(A.REMIGES):
        b, d, n = A.remex_frame(name, s)
        kind = REMEX_KIND(name)
        slot = _slot(kind, i, 3)
        f = Feather(f"{name}.{s}", kind, f"{name}.{s}", b, d, n, L, W * (1 - outer), W * outer, t0=0.07,
                    tip="round", curve=0.025 if kind == "prim" else 0.015, camber=0.03, thick=0.0013,
                    slot=A_SLOT(slot), lod=2)
        # outer vane: toward the leading edge for primaries, toward the wing tip for the arm feathers
        outer_dir = -A.U_WING if kind == "prim" else V(sx, 0, 0)
        f.outer_sign = _outer_sign(f, outer_dir)
        if emarg is not None:
            f.emarg_t = 1.0 - emarg / L
            f.emarg_w = 0.50
            f.emarg_both = name in ("Prim06", "Prim07", "Prim08", "Prim09")
            f.tip = "round"
        if kind == "prim":
            # gentle backward curve in the wing plane over the distal third (toward the trailing edge)
            f.sweep = 0.035 * float(np.sign(np.dot(f.s, A.U_WING)))
        f.slot_under = A_SLOT(kind + "_u")
        F.append(f)
    return F


def A_SLOT(name):
    return SLOTS[name]


def remex_lookup(s):
    return {r[0]: A.remex_frame(r[0], s) for r in A.REMIGES}


COV_GROW = 0.30          # coverts: the vane widens over 30 % of the length (a tapered root, no square card end)
REMEX_PARENT = {r[0]: r[-1] for r in A.REMIGES}        # remex -> arm bone (Hand / Forearm / UpperArm)


def _elbow_widths(name, w_in, w_out, w_gap):
    """(w_in, w_out) of an arm covert; the two coverts either side of the elbow (Tert1 outer vane, Sec6 inner vane)
    are widened to w_gap so the covert rows close over the 4 cm gap between the Tert1 and Sec6 bases (a see-through
    slit in flight otherwise)"""
    if name == "Tert1":
        return w_in, max(w_out, w_gap)
    if name == "Sec6":
        return max(w_in, w_gap), w_out
    return w_in, w_out


def coverts(s):
    """greater secondary / primary coverts, median coverts, alula, underwing coverts (arm).
    Every covert rides the bone of the remex it overlies and is ROOTED AT THAT REMEX'S BASE (a few layers above it, or
    below for the underwing coverts), pointing along it: the fold turns each remex about its base, so a covert rooted
    there turns with it instead of swinging around it. The shingle order follows the remiges (proximal above distal)."""
    F = []
    sx = 1.0 if s == "L" else -1.0
    st = A.LAYER_STEP
    arm = ["Tert3", "Tert2", "Tert1", "Sec6", "Sec5", "Sec4", "Sec3", "Sec2", "Sec1"]
    # greater secondary coverts: one per secondary / tertial, tips at 39-54 % of the chord (spec 4.6)
    for k, name in enumerate(arm):
        b0, d, n = A.remex_frame(name, s)
        L = 0.092 if name.startswith("Tert") else 0.076
        b = b0 + n * (1.8 * st) + d * 0.004
        w_in, w_out = _elbow_widths(name, 0.017, 0.014, 0.022)
        f = Feather(f"GCov_{name}.{s}", "gcov", f"{name}.{s}", b, d, n, L, w_in, w_out, t0=0.05, tip="round",
                    curve=0.022, camber=0.04, thick=0.0009, slot=SLOTS[_slot("gcov", k, 3)], lod=1, grow=COV_GROW)
        f.outer_sign = _outer_sign(f, V(sx, 0, 0))
        f.slot_under = SLOTS["gcov_u"]
        F.append(f)
    # median coverts over the greater covert bases (0.04-0.05)
    for k, name in enumerate(arm):
        b0, d, n = A.remex_frame(name, s)
        b = b0 + n * (3.2 * st) - d * 0.012              # starts under the lesser-covert tips (tapered root)
        w_in, w_out = _elbow_widths(name, 0.015, 0.013, 0.020)
        f = Feather(f"MCov_{name}.{s}", "mcov", f"{name}.{s}", b, d, n, 0.054, w_in, w_out, t0=0.05, tip="round",
                    curve=0.03, camber=0.04, thick=0.0009, slot=SLOTS[_slot("mcov", k, 2)], lod=0, grow=COV_GROW)
        f.outer_sign = _outer_sign(f, V(sx, 0, 0))
        f.slot_under = SLOTS["gcov_u"]
        F.append(f)
    # greater primary coverts on P1-P8 (0.08-0.09, shorter outward), pale shafts
    for k, name in enumerate(["Prim01", "Prim02", "Prim03", "Prim04", "Prim05", "Prim06", "Prim07", "Prim08"]):
        b0, d, n = A.remex_frame(name, s)
        L = 0.088 - 0.004 * k
        b = b0 + n * (1.8 * st) + d * 0.004
        f = Feather(f"PCov_{name}.{s}", "pcov", f"{name}.{s}", b, d, n, L, 0.015, 0.011, t0=0.05, tip="round",
                    curve=0.02, camber=0.04, thick=0.0009, slot=SLOTS[_slot("pcov", k, 2)], lod=1, grow=COV_GROW)
        f.outer_sign = _outer_sign(f, -A.U_WING)
        f.slot_under = SLOTS["gcov_u"]
        F.append(f)
    # alula: 3 feathers along the leading edge at the wrist (longest 0.065)
    w = A.side("wrist", s)
    d0 = unit(A.wp(0.300, -0.030, s) - A.wp(0.225, -0.028, s))
    for k, L in enumerate((0.058, 0.047, 0.037)):
        b = w + A.N_WING * (0.0065 + 0.0008 * k) + A.U_WING * (-0.004 + 0.004 * k)
        d = unit(d0 + A.U_WING * 0.12 * k)
        f = Feather(f"Alula{k + 1}.{s}", "alula", f"Alula.{s}", b, d, A.N_WING, L, 0.008, 0.005, t0=0.06,
                    tip="round", curve=0.01, camber=0.02, thick=0.0010, slot=SLOTS["alula"], lod=1)
        f.outer_sign = _outer_sign(f, -A.U_WING)
        f.slot_under = SLOTS["alula"]
        F.append(f)
    # underwing coverts on the arm: under each secondary / tertial, 2 rows covering 40-50 % of the chord
    for row, (L, h) in enumerate(((0.080, -2.5), (0.052, -4.5))):
        for k, name in enumerate(arm):
            b0, d, n = A.remex_frame(name, s)
            b = b0 + n * (h * st) + d * 0.003
            f = Feather(f"UCov{row}_{name}.{s}", "ucov", f"{name}.{s}", b, d, n, L, 0.015, 0.013, t0=0.05,
                        tip="round", curve=-0.01, camber=0.02, thick=0.0010, slot=SLOTS["ucov"], lod=1 - row)
            f.outer_sign = _outer_sign(f, V(sx, 0, 0))
            f.slot_under = SLOTS["ucov"]
            F.append(f)
    return F


def scapulars(s, skin):
    """three staggered rows of scapulars seated on the mantle along the wing root, pointing back along the spine and
    a little outward; on Shoulder.X. They cover the top edge of the folded wing and the tertial bases (spec 3.6, 4.7).
    Proximal over distal: the inner row (next to the spine) lies on top, the outer row lowest; each row follows the
    curve of the back (curve) so the feathers lie flat instead of standing as plates."""
    F = []
    sx = 1.0 if s == "L" else -1.0
    u = A.U_WING
    rows = (((-0.074, -0.054, -0.034, -0.014), 0.052, 0.060, 0.026, 0.16),      # outer, lowest
            ((-0.084, -0.064, -0.044, -0.024, -0.004), 0.040, 0.070, 0.028, 0.10),
            ((-0.090, -0.070, -0.050, -0.030), 0.027, 0.078, 0.030, 0.05))       # inner, on top
    n = 0
    for row, (ys, x, L, W, outw) in enumerate(rows):
        for k, y in enumerate(ys):
            p0 = V(sx * x, y, 0.30)
            out = unit(V(sx * (0.30 + 0.20 * (2 - row)), 0.0, 1.0))
            p = seat(skin, p0, out, gap=0.0006 + 0.0009 * row + 0.0002 * k)
            d = unit(u + V(sx * (outw + 0.02 * _jit(n, 11)), 0, 0))
            nrm = unit(out - d * np.dot(out, d))
            f = Feather(f"Scap{row}{k}.{s}", "scap", f"Shoulder.{s}", p, d, nrm, L * (1 + 0.05 * _jit(n, 12)),
                        W * 0.56, W * 0.56, t0=0.05, tip="round", curve=0.07, camber=0.05, thick=0.0009,
                        twist=3.0 * _jit(n, 13), slot=SLOTS[_slot("scap", k, 2)], lod=1 if row != 1 else 0)
            f.outer_sign = _outer_sign(f, V(sx, 0, 0))
            f.slot_under = SLOTS["scap_a"]
            F.append(f); n += 1
    return F


def cov_skin(p, s, group):
    """bilinear weights of the root p on the 2 x 2 covert pivot bones of `group` (raven_anatomy.COVERT_GROUPS): all
    four turn alike in the fold, so the blend is a rigid turn about the root (the root clamped into the quad)"""
    g = next(x for x in A.COVERT_GROUPS if x[0] == group)
    (x0, x1), (y0, y1) = g[3], g[4]
    x, y = A.wing_coords(p, s)
    u = min(max((x - x0) / (x1 - x0), 0.0), 1.0)
    v = min(max((y - y0) / (y1 - y0), 0.0), 1.0)
    w = ((1 - u) * (1 - v), u * (1 - v), (1 - u) * v, u * v)
    return [(f"Cov{group}{k + 1}.{s}", float(wk)) for k, wk in enumerate(w) if wk > 1e-6]


def lesser_coverts(s, skin):
    """the lesser / marginal coverts (spec 4.6): a soft band 3-4 cm deep along the leading edge and the propatagium,
    over the median coverts. Like the other coverts each one rides the bone of the arm remex it lies in front of
    and is placed ON THAT REMEX'S AXIS (in front of its base, along -d), so the fold turns it with its remex and the
    folded wing keeps orderly parallel rows instead of a cluster of scales; seated on the arm skin (first crossing
    below it along -n). Two rows: row 0 nearer the leading edge, on top."""
    F = []
    sx = 1.0 if s == "L" else -1.0
    st = A.LAYER_STEP
    arm = ["Tert3", "Tert2", "Tert1", "Sec6", "Sec5", "Sec4", "Sec3", "Sec2", "Sec1"]
    n = 0
    for row, (off, L, W, lift) in enumerate(((0.036, 0.036, 0.022, 0.0016), (0.021, 0.040, 0.022, 0.0008))):
        for k, name in enumerate(arm):
            b0, d, nn = A.remex_frame(name, s)
            q = b0 - d * off
            ts = np.linspace(0.0, 0.04, 161)
            dd = skin((q + nn * 0.03)[None] - ts[:, None] * nn[None])
            hit = np.nonzero(dd < lift)[0]
            p = q + nn * 0.03 - nn * ts[hit[0]] if len(hit) else q + nn * (6.0 + row) * st
            p = p if np.dot(p - b0, nn) > (4.2 - row) * st else b0 - d * off + nn * (4.2 - row) * st + nn * 0.0
            w_in, w_out = _elbow_widths(name, W * 0.5, W * 0.5, 0.017)
            f = Feather(f"LCov{row}_{name}.{s}", "mcov", f"{name}.{s}", p, d, nn, L * (1 + 0.05 * _jit(n, 22)),
                        w_in, w_out, t0=0.05, tip="round", curve=0.035, camber=0.03, thick=0.0008,
                        slot=SLOTS[_slot("mcov", k, 2)], lod=0 if row == 0 else 1, grow=COV_GROW,
                        skin=cov_skin(p, s, "U" if name.startswith("Tert") else "F"))
            f.outer_sign = _outer_sign(f, V(sx, 0, 0))
            f.slot_under = SLOTS["gcov_u"]
            F.append(f); n += 1
    return F


def marginal_coverts(s, skin):
    """the marginal coverts (spec 4.6, GiM 0a423e61): two rows of small rounded feathers rooted along the leading edge
    of the propatagium, the arm and the base of the hand, pointing back over the lesser-covert roots, so the leading
    edge is feathered (no bare pale skin tube) and no sky shows between it and the covert block in flight. Rigid on
    the arm bone under them (UpperArm to the elbow, Forearm to the wrist, Hand beyond): in the fold they ride the
    arm skin and lie over the forearm. Row 0 (front) on top."""
    F = []
    sx = 1.0 if s == "L" else -1.0
    n = 0
    xe, xw = A.J["elbow"][0], A.J["wrist"][0]
    for row, (y0, L, W, lift, x0, x1, dx) in enumerate(((-0.024, 0.034, 0.0160, 0.0034, 0.032, 0.292, 0.0115),
                                                         (-0.008, 0.040, 0.0170, 0.0026, 0.038, 0.232, 0.0115))):
        xs = np.arange(x0, x1 + 1e-9, dx) + (0.0 if row == 0 else dx * 0.5)
        for k, x in enumerate(xs):
            hand = x > xw + 0.004
            # on the hand the row follows the leading edge of the hand (wrist (0.222, -0.016) -> tip (0.296, 0.000))
            yh = -0.016 + (x - xw) / 0.074 * 0.016 - (0.008 if row == 0 else -0.004)
            yy = (yh if hand else y0) + 0.002 * _jit(n, 41)
            q = A.wp(x, yy, s)
            nn = A.N_WING.copy()
            ts = np.linspace(0.0, 0.05, 201)
            dd = skin((q + nn * 0.04)[None] - ts[:, None] * nn[None])
            hit = np.nonzero(dd < lift)[0]
            p = q + nn * 0.04 - nn * ts[hit[0]] if len(hit) else q + nn * 0.006
            d = unit(A.U_WING + V(sx * (0.12 + 0.04 * _jit(n, 42)), 0, 0))
            bone = "UpperArm" if x < xe else ("Forearm" if not hand else "Hand")
            Lk = L * (0.80 if hand else 1.0) * (1 + 0.06 * _jit(n, 43))
            f = Feather(f"Marg{row}{k:02d}.{s}", "mcov", f"{bone}.{s}", p, d, nn, Lk, W * 0.5, W * 0.5, t0=0.05,
                        tip="round", curve=0.03, camber=0.04, thick=0.0008, twist=4.0 * _jit(n, 44),
                        slot=SLOTS[_slot("mcov", k, 2)], lod=1 if row == 0 else 0, grow=COV_GROW,
                        skin=cov_skin(p, s, bone[0]))
            f.outer_sign = _outer_sign(f, V(sx, 0, 0))
            f.slot_under = SLOTS["gcov_u"]
            F.append(f); n += 1
    return F


def trousers(skin):
    """the shaggy 'trousers' (spec 3.6): loose-tipped feathers round the lower tibia, pointing down along the shin
    and flaring a little, their tips just covering the ankle (z 0.067-0.075); rigid on Shin.X. Two staggered rows,
    none on the inner side facing the other leg."""
    F = []
    n = 0
    for s in "LR":
        sx = 1.0 if s == "L" else -1.0
        K, An = A.side("knee", s), A.side("ankle", s)
        from sdf import eval_prims
        legp = [q for q in A.leg_prims(s) if q.tag in ("thigh", "trouser")]
        leg = lambda P, legp=legp: eval_prims(legp, P)             # the shin alone (the belly would capture seat())
        ax = unit(An - K)
        e1 = unit(np.cross(ax, V(0, 0, 1)) if abs(ax[2]) < 0.99 else V(1, 0, 0))
        e2 = unit(np.cross(ax, e1))
        for row, (t, L, W, angs) in enumerate(((0.52, 0.050, 0.016, (-150, -105, -60, -15, 30, 75, 120)),
                                               (0.66, 0.040, 0.014, (-128, -82, -38, 8, 52, 98, 150)))):
            for a in angs:
                ang = np.radians(a + 6 * _jit(n, 31))
                radial = unit(e1 * np.cos(ang) + e2 * np.sin(ang))
                if radial[0] * sx < -0.55:                       # inner side, facing the other leg
                    continue
                c = K + (An - K) * t
                p = seat(leg, c + radial * 0.03, radial, gap=0.0008 + 0.0010 * (1 - row))
                d = unit(ax + radial * (0.22 + 0.06 * _jit(n, 32)))
                nrm = unit(radial - d * np.dot(radial, d))
                f = Feather(f"Trouser{row}{n:02d}.{s}", "trouser", f"Shin.{s}", p, d, nrm,
                            L * (1 + 0.10 * _jit(n, 33)), W * 0.5, W * 0.5, t0=0.05, tip="lance", curve=-0.04,
                            camber=0.10, thick=0.0007, twist=10.0 * _jit(n, 34), slot=SLOTS["hackle_b"],
                            lod=1 if row == 0 else 0)
                f.slot_under = SLOTS["hackle_a"]
                F.append(f); n += 1
    return F


def tail(skin):
    F = []
    for s in "LR":
        sx = 1.0 if s == "L" else -1.0
        for i, (L, W, _g, _c) in enumerate(A.RECTRICES):
            b, d, n = A.rectrix_frame(i, s, A.TAIL_BIND_SPREAD)
            outer = 0.50 - 0.02 * i
            f = Feather(f"Rect{i + 1}.{s}", "rect", f"Rect{i + 1}.{s}", b, d, n, L, W * (1 - outer), W * outer,
                        t0=0.06, tip="round", curve=0.02, camber=0.02, thick=0.0014,
                        slot=SLOTS[_slot("rect", i, 2)], lod=2)
            f.outer_sign = _outer_sign(f, V(sx, 0, 0))
            f.slot_under = SLOTS["rect_u"]
            F.append(f)
    # upper tail coverts: cover the base 40 % of the tail, above R1
    nt = A.rectrix_frame(0, "L", A.TAIL_BIND_SPREAD)[2]
    for k, (x, L) in enumerate(((0.0, 0.100), (0.012, 0.092), (-0.012, 0.092), (0.022, 0.080), (-0.022, 0.080))):
        b = seat(skin, A.J["pyg"] + V(x, 0, 0) - A.TAIL_DIR * 0.020 + nt * 0.02, nt, gap=0.0015 + 0.0008 * (4 - k))
        d = unit(A.TAIL_DIR + V(x * 1.5, 0, 0))
        f = Feather(f"UTC{k}", "utc", "Tail", b, d, nt, L, 0.020, 0.020, t0=0.05, tip="round", curve=0.03,
                    camber=0.03, thick=0.0012, slot=SLOTS["utc_a"], lod=1)
        f.slot_under = SLOTS["utc_a"]
        F.append(f)
    return F


def seat(skin, p, n_guess, gap=0.0):
    """move p along -n_guess / +n_guess onto the skin surface (+ gap outward)"""
    n = unit(n_guess)
    p0 = np.asarray(p, float).copy()
    for _ in range(40):
        dist = float(skin(p[None])[0])
        if abs(dist - gap) < 2e-5:
            break
        p = p - n * np.clip((dist - gap) * 0.8, -0.004, 0.004)
    if np.linalg.norm(p - p0) > 0.05:
        raise ValueError(f"seat() diverged from {p0}")
    return p


def _jit(k, salt):
    """deterministic pseudo-random number in [-1, 1] for feather k"""
    x = np.sin(k * 12.9898 + salt * 78.233) * 43758.5453
    return 2.0 * (x - np.floor(x)) - 1.0


def hackles(skin):
    """throat hackles (spec 3.5): pointed lanceolate feathers, 3-5 mm wide, exposed 10-22 mm, from the chin
    (-0.247, 0.324) to tips about (-0.192, 0.240), wrapping round the neck sides to X +-0.035-0.040 below the ear
    coverts; the lower rows stand 1.5-2.5 cm off the throat (a shaggy beard), the upper rows lie closer. Rows from the
    chin down; every hackle gets a deterministic jitter in length, yaw, lift and twist so the tips separate.
    Rigid on Throat."""
    F = []
    # (y, z) of the row on the throat midline, row length, lift off the surface (0..1), wrap angle (deg)
    rows = [(-0.239, 0.321, 0.020, 0.25, 62), (-0.233, 0.313, 0.024, 0.32, 70), (-0.226, 0.305, 0.028, 0.40, 78),
            (-0.219, 0.297, 0.031, 0.48, 86), (-0.212, 0.289, 0.034, 0.55, 94), (-0.205, 0.281, 0.036, 0.60, 100),
            (-0.198, 0.273, 0.036, 0.62, 106)]
    k = 0
    for r, (y, z, L, lift, wrap) in enumerate(rows):
        n_cols = 6 + r                                     # more round the wider lower throat
        for c in range(n_cols):
            a = (c - (n_cols - 1) / 2) / ((n_cols - 1) / 2) if n_cols > 1 else 0.0
            a += 0.35 / (n_cols - 1) * (1 if r % 2 else -1)                    # stagger alternate rows
            ang = a * np.radians(wrap)
            radial = unit(V(np.sin(ang), -np.cos(ang) * 0.62, -np.cos(ang) * 0.78))   # outward from the throat axis
            p = seat(skin, V(0.0, y, z) + radial * 0.006, radial, gap=0.0008 + 0.0006 * (len(rows) - r) / len(rows))
            # down-back along the throat, turned out by `lift` and splayed a little sideways
            down = unit(V(0.0, 0.50, -0.866))
            j1, j2, j3 = _jit(k, 1), _jit(k, 2), _jit(k, 3)
            d = unit(down + radial * (lift * (1.0 - 0.25 * abs(a)) + 0.08 * j2) + V(0.18 * np.sin(ang) + 0.10 * j1, 0, 0))
            nrm = unit(radial - d * np.dot(radial, d))
            Lk = L * (1.0 + 0.15 * j3) * (1.0 - 0.18 * abs(a))
            f = Feather(f"Hackle{k:02d}", "hackle", "Throat", p, d, nrm, Lk, 0.0019, 0.0019, t0=0.06, tip="lance",
                        curve=-0.05, camber=0.12, thick=0.0006, twist=12.0 * j1,
                        slot=SLOTS[_slot("hackle", k, 2)], lod=1 if (c + r) % 2 == 0 else 0)
            f.slot_under = SLOTS["hackle_a"]
            F.append(f); k += 1
    return F


def _bill_point(u, phi):
    """a point on the upper mandible surface and its outward normal: u = -y, phi = angle round the culmen
    (0 = top, +-90 deg = the tomium; + = the bird's left)"""
    zc, zb, w = float(A.bill_culmen(u)), float(A.bill_tomium_upper(u)), float(A.bill_width(u))
    d = zc - zb
    s = min(abs(phi) / 90.0, 0.98)
    g = np.sqrt(max(1 - (1 - s) ** 2.2, 0.0))
    dg = 1.1 * (1 - s) ** 1.2 / max(g, 1e-3)                           # d g / d s
    sx = 1.0 if phi >= 0 else -1.0
    p = V(sx * w * g, -u, zc - d * s)
    slope = (float(A.bill_culmen(u - 0.001)) - float(A.bill_culmen(u + 0.001))) / 0.002    # dz / d(-y) > 0
    n2 = unit(V(sx * d, 0.0, w * dg))                                   # section normal (x, z)
    n = unit(V(n2[0], -slope * n2[2], n2[2]))
    return p, n


def bristles(skin):
    """nasal bristles (spec 3.4): a dense tuft of stiff, forward-and-down feathers 0.021-0.026 long LYING ON the
    proximal 35-40 % of the culmen (to (0, -0.270, 0.356)) and halfway down the sides, hiding the nostril. Three
    staggered rows rooted in the forehead / lores feathering along the feather line; each bristle runs forward along
    the bill surface (its tip ~0.6 mm above the horn) and curves down with it. Rigid on Head."""
    F = []
    k = 0
    rows = ((0.2370, 11, 0.0270, 0.0016), (0.2415, 10, 0.0250, 0.0011), (0.2460, 9, 0.0225, 0.0006))
    for r, (u0, n_cols, L0, lift) in enumerate(rows):
        for c in range(n_cols):
            a = (c - (n_cols - 1) / 2) / ((n_cols - 1) / 2)
            phi = a * (78.0 - 6.0 * r) + 3.0 * _jit(k, 5)
            L = L0 * (1.0 - 0.22 * abs(a) ** 1.5) * (1.0 + 0.06 * _jit(k, 7))
            # root: on the horn under the feather line (hidden in the forehead / lores feathering), lifted by the
            # rows below it; the bristle runs forward along the surface and ends ~0.6 mm above it
            base_b, n0 = _bill_point(u0, phi)
            p = base_b + n0 * (0.0006 + lift)
            ut = min(u0 + L * 0.95, 0.274)
            tip_b, n1 = _bill_point(ut, phi * 1.04)
            tgt = tip_b + n1 * (0.0005 + 0.4 * lift)
            d = unit(tgt - p)
            nrm = unit(n0 + n1)
            f = Feather(f"Bristle{k:02d}", "bristle", "Head", p, d, nrm, float(np.linalg.norm(tgt - p)), 0.0013,
                        0.0013, t0=0.04, tip="point", curve=0.012, camber=0.10, thick=0.0005,
                        twist=4.0 * _jit(k, 9), slot=SLOTS["bristle"], lod=0 if r == 2 else 1)
            f.slot_under = SLOTS["bristle"]
            F.append(f); k += 1
    return F


def plumage(skin=None):
    if skin is None:
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dog"))
        from sdf import eval_prims
        prims = A.body_prims()
        skin = lambda P: eval_prims(prims, P)
    F = []
    for s in "LR":
        F += remiges(s) + coverts(s) + scapulars(s, skin) + lesser_coverts(s, skin) + marginal_coverts(s, skin)
    F += tail(skin) + hackles(skin) + bristles(skin) + trousers(skin)
    return F
