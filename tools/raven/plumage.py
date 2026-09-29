"""The raven's feathers in the bind pose: every Feather (tools/raven/feathers.py) with its bone, atlas slot and LOD.

  plumage(skin=None) -> list[Feather]   (skin: callable P -> SDF distance of the body, used to seat the throat hackles
                                         and the nasal bristles on the surface; None = raven_anatomy.body_prims())

Groups (spec 4.3-4.8, 3.4-3.5): remiges (P1-P10, S1-S6, T1-T3; one bone each), greater secondary coverts and
greater primary coverts and median coverts (ride the bone of the remex they overlie, so they fan with it), alula,
underwing coverts (arm), scapulars (Shoulder), rectrices R1-R6 (one bone each), upper tail coverts (Tail), throat
hackles (Throat), nasal bristles (Head).

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


def coverts(s):
    """greater secondary / primary coverts, median coverts, alula, underwing coverts (arm)"""
    F = []
    sx = 1.0 if s == "L" else -1.0
    top = 0.004 + 0.0022                       # just above T3 (the top remex)
    # greater secondary coverts: one per secondary / tertial; tip line (spec 4.6)
    tips = {"Tert3": (0.030, 0.100), "Tert2": (0.058, 0.098), "Tert1": (0.086, 0.094), "Sec6": (0.110, 0.088),
            "Sec5": (0.131, 0.085), "Sec4": (0.153, 0.078), "Sec3": (0.176, 0.072), "Sec2": (0.199, 0.066),
            "Sec1": (0.219, 0.060)}
    for k, (name, (tx, ty)) in enumerate(tips.items()):
        _b, d, n = A.remex_frame(name, s)
        L = 0.092 if name.startswith("Tert") else 0.074
        tip = A.wp(tx, ty, s, top + 0.0009 * k)
        b = tip - d * L
        f = Feather(f"GCov_{name}.{s}", "gcov", f"{name}.{s}", b, d, n, L, 0.016, 0.013, t0=0.05, tip="round",
                    curve=0.01, camber=0.03, thick=0.0012, slot=SLOTS[_slot("gcov", k, 3)], lod=1)
        f.outer_sign = _outer_sign(f, V(sx, 0, 0))
        f.slot_under = SLOTS["gcov_u"]
        F.append(f)
    # greater primary coverts on P1-P8 (0.08-0.09, shorter outward), pale shafts
    for k, name in enumerate(["Prim01", "Prim02", "Prim03", "Prim04", "Prim05", "Prim06", "Prim07", "Prim08"]):
        b0, d, n = A.remex_frame(name, s)
        L = 0.088 - 0.004 * k
        b = b0 + n * (0.0060 + 0.0006 * k) + d * 0.004
        f = Feather(f"PCov_{name}.{s}", "pcov", f"{name}.{s}", b, d, n, L, 0.015, 0.011, t0=0.05, tip="round",
                    curve=0.01, camber=0.03, thick=0.0011, slot=SLOTS[_slot("pcov", k, 2)], lod=1)
        f.outer_sign = _outer_sign(f, -A.U_WING)
        f.slot_under = SLOTS["gcov_u"]
        F.append(f)
    # median coverts: one row, 0.04-0.05 long, over the greater covert bases (ride the nearest remex)
    rows = [("Tert3", 0.034), ("Tert2", 0.060), ("Tert1", 0.086), ("Sec6", 0.112), ("Sec5", 0.134), ("Sec4", 0.156),
            ("Sec3", 0.178), ("Sec2", 0.198), ("Sec1", 0.216)]
    for k, (name, x) in enumerate(rows):
        _b, d, n = A.remex_frame(name, s)
        L = 0.046
        tip = A.wp(x, 0.050, s, top + 0.0105 + 0.0006 * k)
        b = tip - d * L
        f = Feather(f"MCov_{name}.{s}", "mcov", f"{name}.{s}", b, d, n, L, 0.013, 0.011, t0=0.05, tip="round",
                    curve=0.01, camber=0.03, thick=0.0011, slot=SLOTS[_slot("mcov", k, 2)], lod=0)
        f.outer_sign = _outer_sign(f, V(sx, 0, 0))
        f.slot_under = SLOTS["gcov_u"]
        F.append(f)
    # alula: 3 feathers along the leading edge at the wrist (longest 0.065)
    w = A.side("wrist", s)
    d0 = unit(A.wp(0.300, -0.030, s) - A.wp(0.225, -0.028, s))
    for k, L in enumerate((0.065, 0.052, 0.040)):
        b = w + A.N_WING * (0.009 + 0.0009 * k) + A.U_WING * (-0.006 + 0.004 * k)
        d = unit(d0 + A.U_WING * 0.12 * k)
        f = Feather(f"Alula{k + 1}.{s}", "alula", f"Alula.{s}", b, d, A.N_WING, L, 0.008, 0.005, t0=0.06,
                    tip="round", curve=0.01, camber=0.02, thick=0.0010, slot=SLOTS["alula"], lod=1)
        f.outer_sign = _outer_sign(f, -A.U_WING)
        f.slot_under = SLOTS["alula"]
        F.append(f)
    # underwing coverts on the arm: below the secondaries (ventral), 2 rows covering 40-50 % of the chord
    low = 0.004 - 11 * A.LAYER_STEP
    for row, (y_tip, L, h) in enumerate(((0.090, 0.075, 0.0), (0.050, 0.050, -0.0014))):
        for k, (name, x) in enumerate(rows):
            _b, d, n = A.remex_frame(name, s)
            tip = A.wp(x + 0.004 * row, y_tip, s, low + h - 0.0007 * k)
            b = tip - d * L
            f = Feather(f"UCov{row}_{name}.{s}", "ucov", f"{name}.{s}", b, d, n, L, 0.014, 0.012, t0=0.05,
                        tip="round", curve=-0.01, camber=0.02, thick=0.0010, slot=SLOTS["ucov"], lod=1 - row)
            f.outer_sign = _outer_sign(f, V(sx, 0, 0))
            f.slot_under = SLOTS["ucov"]
            F.append(f)
    return F


def scapulars(s, skin):
    """two rows of broad feathers seated on the back along the wing root (mantle), pointing back along the spine and
    a little outward; on Shoulder.X. They cover the top edge of the folded wing (spec 3.6, 4.7)."""
    F = []
    sx = 1.0 if s == "L" else -1.0
    u = A.U_WING
    for row, (ys, x, L, W) in enumerate((((-0.070, -0.048, -0.026, -0.004), 0.034, 0.075, 0.030),
                                         ((-0.078, -0.058, -0.038, -0.018), 0.050, 0.068, 0.028))):
        for k, y in enumerate(ys):
            p0 = V(sx * x, y, 0.30)
            out = unit(V(sx * (0.55 + 0.25 * row), 0.0, 1.0))
            p = seat(skin, p0, out, gap=0.0012 + 0.0016 * row + 0.0004 * k)
            d = unit(u + V(sx * (0.10 + 0.12 * row), 0, 0))
            nrm = unit(out - d * np.dot(out, d))
            f = Feather(f"Scap{row}{k}.{s}", "scap", f"Shoulder.{s}", p, d, nrm, L, W * 0.5, W * 0.5, t0=0.05,
                        tip="round", curve=0.05, camber=0.06, thick=0.0012, slot=SLOTS[_slot("scap", k, 2)],
                        lod=1 if row == 1 else 0)
            f.outer_sign = _outer_sign(f, V(sx, 0, 0))
            f.slot_under = SLOTS["scap_a"]
            F.append(f)
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
    for _ in range(40):
        dist = float(skin(p[None])[0])
        if abs(dist - gap) < 2e-5:
            break
        p = p - n * (dist - gap) * 0.8
    return p


def hackles(skin):
    """lanceolate throat hackles: chin (-0.247, 0.324) to tips about (-0.192, 0.240), wrapping to X +-0.035; they
    stand 1.5-2.5 cm off the throat at the tips (a 'beard'); rigid on Throat."""
    F = []
    rows = [(-0.240, 0.318, 0.036), (-0.228, 0.302, 0.042), (-0.216, 0.286, 0.046), (-0.204, 0.270, 0.046)]
    k = 0
    for r, (y, z, L) in enumerate(rows):
        n_cols = 5 + r
        for c in range(n_cols):
            a = (c - (n_cols - 1) / 2) / ((n_cols - 1) / 2)          # -1 .. 1 around the throat
            ang = a * np.radians(70 + 8 * r)
            radial = unit(V(np.sin(ang), -np.cos(ang) * 0.65, -np.cos(ang) * 0.75))   # outward from the throat axis
            p0 = V(0.0, y, z) + radial * 0.004
            p = seat(skin, p0, radial, gap=0.0012)
            # down-back along the throat (57 deg front outline) and off the surface
            d = unit(V(0.25 * np.sin(ang), 0.52, -0.84) + radial * (0.30 + 0.05 * r))
            nrm = unit(np.cross(d, np.cross(radial, d)))
            if np.dot(nrm, radial) < 0:
                nrm = -nrm
            f = Feather(f"Hackle{k:02d}", "hackle", "Throat", p, d, nrm, L * (0.9 + 0.2 * ((c * 7 + r * 3) % 5) / 4),
                        0.0036, 0.0036, t0=0.10, tip="lance", curve=-0.06, camber=0.10, thick=0.0010,
                        slot=SLOTS[_slot("hackle", k, 2)], lod=1 if (c + r) % 2 == 0 else 0)
            f.slot_under = SLOTS["hackle_a"]
            F.append(f); k += 1
    return F


def bristles(skin):
    """nasal bristles: stiff, forward-and-down, 0.021-0.026 long, over the top and sides of the proximal 35-40 % of
    the culmen (to (0, -0.270, 0.356)), halfway down the sides; rigid on Head."""
    F = []
    k = 0
    for r, y in enumerate((-0.246, -0.251)):
        for c in range(7):
            a = (c - 3) / 3.0
            ang = a * np.radians(80)
            radial = unit(V(np.sin(ang), -0.20, np.cos(ang)))
            p0 = V(0, y, 0.350) + radial * 0.020
            p = seat(skin, p0, radial, gap=0.0008)
            d = unit(V(0.0, -0.86, -0.46) + radial * 0.10 - V(np.sin(ang) * 0.05, 0, 0))
            nrm = unit(radial - d * np.dot(radial, d))
            L = 0.024 - 0.002 * abs(a) - 0.002 * r
            f = Feather(f"Bristle{k:02d}", "bristle", "Head", p, d, nrm, L, 0.0022, 0.0022, t0=0.05, tip="point",
                        curve=-0.03, camber=0.05, thick=0.0007, slot=SLOTS["bristle"], lod=0)
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
        F += remiges(s) + coverts(s) + scapulars(s, skin)
    F += tail(skin) + hackles(skin) + bristles(skin)
    return F
