"""Common raven (Corvus corax) anatomy: bind-pose skeleton joints, the bone table, and the SDF primitives of the body.

Conventions (as the other assets): meters, Z up, the bird faces -Y, ground z = 0, '.L' = +X (the bird's left).
Size and shape follow the reference spec (docs/raven_reference.md; GiM "Animalia - Raven"): total length bill tip to tail
tip 0.62 m, crown 0.389 m, span 1.08 m, back line 31 deg front-up.

BIND POSE: the trunk, head, legs and tail stand as in the standing idle (spec 2.2), the wings are SPREAD (the glide
planform of spec 2.3/4.2) in the plane that contains +X and the spine direction U_WING (32 deg down-back), so the flight
feathers can be modelled flat. Every ground clip folds the wings through the animation library.

BILL: not SDF - two lofted meshes (bill_mesh('upper' | 'lower'): culmen / tomium / gonys / width profiles of spec 3.4,
outer horn + palate / floor of the mouth, sharp tomium); bill_prims() wraps them as MeshSDF prims (tags 'bill',
'bill_low') so eval_prims() and plumage.seat() see the bill; stage A keeps them out of its SDF grid.
HEAD (spec 3.3): forehead ramp continuing the culmen, crown behind the eye, brow / lores / cheeks, nape; the eyeball
(Eye.X, EYE_R) sits in a socket with a raised lid ring (eye_socket_prims: Torus, tag 'lid').

Every primitive carries the bone (or bone chain) it moves with; raven_stage_a.py derives the skin weights from them. The
module is named raven_anatomy (not anatomy) so it never shadows tools/dog/anatomy.py on sys.path.
"""
import os, sys
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dog"))
from sdf import Sphere, Ellipsoid, ellipsoid_seg, RoundCone, RoundBox, frame_from    # noqa: E402

V = lambda *a: np.array(a, dtype=float)


def mirror(p):
    p = np.array(p, dtype=float); p[..., 0] = -p[..., 0]; return p


def unit(v):
    v = np.asarray(v, float); return v / np.linalg.norm(v)


# --------------------------------------------------------------------------------------------------------------------
# Wing plane (spec 2.3): x = distance from the midline, y = distance behind the shoulder along U_WING
# --------------------------------------------------------------------------------------------------------------------
U_WING = V(0, 0.848, -0.530)                  # spine direction, back-down
N_WING = V(0, 0.530, 0.848)                   # dorsal normal of the spread wing
WING_O = V(0, -0.094, 0.264)                  # shoulder station on the midline


def wp(x, y, s="L", h=0.0):
    """wing-plane (x, y) [+ h along the dorsal normal] -> bird frame, side s"""
    p = V(x, 0, 0) + WING_O + U_WING * y + N_WING * h
    return p if s == "L" else mirror(p)


# --------------------------------------------------------------------------------------------------------------------
# Joints (left side for paired joints). Spec 2.2 (standing) + 2.3 (spread wing).
# --------------------------------------------------------------------------------------------------------------------
J = {
    "hips": V(0, 0.000, 0.220),
    "spine1": V(0, -0.028, 0.239),
    "spine2": V(0, -0.058, 0.259),
    "neck1": V(0, -0.098, 0.285),
    "neck2": V(0, -0.140, 0.318),
    "neck3": V(0, -0.180, 0.336),
    "atlas": V(0, -0.211, 0.342),
    "billbase": V(0, -0.246, 0.366),         # culmen feather base (Head tail)
    "quadrate": V(0, -0.224, 0.336),         # Jaw head
    "jawtip": V(0, -0.300, 0.320),
    "billtip": V(0, -0.304, 0.321),
    "rictus": V(0.013, -0.238, 0.340),
    "eye": V(0.019, -0.233, 0.354),            # eyeball centre (spec 0.021; 2 mm in so the ball bulges to 0.025)
    "throat0": V(0, -0.228, 0.318),
    "throat1": V(0, -0.205, 0.275),
    "tailbase": V(0, 0.032, 0.202),
    "pyg": V(0, 0.060, 0.186),
    "tailtip": V(0, 0.263, 0.069),
    # wing, spread (bind) pose
    "scap": V(0.012, -0.070, 0.268),          # Shoulder bone head (scapula / coracoid, near the spine)
    "shoulder": wp(0.040, 0.000),
    "elbow": wp(0.120, 0.032),
    "wrist": wp(0.222, -0.016),
    "handtip": wp(0.296, 0.000),
    # leg
    "hip": V(0.026, -0.005, 0.197),
    "knee": V(0.045, -0.0455, 0.160),
    "ankle": V(0.040, 0.019, 0.077),
    "mtp": V(0.042, 0.000, 0.012),
}

# toes: (name, joints from the MTP to the claw base, claw tip).  Toe III (middle) measured; II / IV / I from their claw
# tips and lengths (spec 2.2, 3.7): II 22 deg inward of III, IV 22 deg outward, the hallux straight back.
TOE_Z = 0.006            # toe axis height (toes 6-7 mm thick at the base, 4 mm at the tip)


def _toe(dir_xy, lens, claw, z=TOE_Z):
    d = unit(V(dir_xy[0], dir_xy[1], 0))
    p = [V(J["mtp"][0], J["mtp"][1], z)]
    for L in lens:
        p.append(p[-1] + d * L)
    tip = p[-1] + d * claw * 0.9 + V(0, 0, -z + 0.002)
    return p, tip


def _rotz(v, deg):
    a = np.radians(deg); c, s = np.cos(a), np.sin(a)
    return V(c * v[0] - s * v[1], s * v[0] + c * v[1], v[2])


_D3 = unit(V(0.008, -0.054, 0))                        # toe III direction (turned out 8 deg)
TOES = {
    "Toe3": _toe(_D3, (0.017, 0.013, 0.024), 0.023),                 # middle: phalanges 17/13/12/12 mm (2 bones)
    "Toe2": _toe(_rotz(_D3, -22), (0.020, 0.018), 0.018),            # inner (toward the midline: -X for .L)
    "Toe4": _toe(_rotz(_D3, 22), (0.022, 0.019), 0.017),             # outer
    "Toe1": _toe(unit(V(-0.10, 1.0, 0)), (0.013, 0.012), 0.021),     # hallux, back and 10 deg toward the midline
}
# note: _rotz(+) turns toward +X (outward for the left foot)


def side(name, s):
    p = J[name]
    return p.copy() if s == "L" else mirror(p)


# --------------------------------------------------------------------------------------------------------------------
# Flight-feather table (spec 4.3), wing plane of the LEFT wing: (base x, base y), (tip x, tip y), build length, full
# width, outer-vane share, emargination (outer, from the tip) ; secondaries and tertials likewise.
# --------------------------------------------------------------------------------------------------------------------
REMIGES = [
    # name     base            tip              len    width  outer  emarg(from tip)  bone parent
    ("Prim10", (0.296, 0.008), (0.437, 0.008), 0.140, 0.022, 0.30, None, "Hand"),
    ("Prim09", (0.288, 0.006), (0.507, 0.027), 0.225, 0.035, 0.27, 0.100, "Hand"),
    ("Prim08", (0.279, 0.004), (0.540, 0.090), 0.275, 0.037, 0.27, 0.100, "Hand"),
    ("Prim07", (0.271, 0.003), (0.539, 0.151), 0.300, 0.038, 0.28, 0.090, "Hand"),
    ("Prim06", (0.263, 0.001), (0.516, 0.185), 0.310, 0.040, 0.28, 0.075, "Hand"),
    ("Prim05", (0.255, -0.001), (0.487, 0.209), 0.305, 0.038, 0.30, 0.050, "Hand"),
    ("Prim04", (0.247, -0.003), (0.454, 0.221), 0.295, 0.037, 0.35, None, "Hand"),
    ("Prim03", (0.238, -0.004), (0.399, 0.215), 0.270, 0.037, 0.35, None, "Hand"),
    ("Prim02", (0.230, -0.006), (0.340, 0.210), 0.240, 0.037, 0.35, None, "Hand"),
    ("Prim01", (0.222, -0.008), (0.289, 0.214), 0.230, 0.037, 0.35, None, "Hand"),
    ("Sec1", (0.222, -0.004), (0.266, 0.216), 0.225, 0.043, 0.40, None, "Forearm"),
    ("Sec2", (0.205, 0.004), (0.244, 0.218), 0.220, 0.043, 0.40, None, "Forearm"),
    ("Sec3", (0.188, 0.012), (0.222, 0.217), 0.210, 0.043, 0.40, None, "Forearm"),
    ("Sec4", (0.171, 0.020), (0.195, 0.215), 0.200, 0.043, 0.40, None, "Forearm"),
    ("Sec5", (0.154, 0.028), (0.168, 0.213), 0.190, 0.043, 0.40, None, "Forearm"),
    ("Sec6", (0.137, 0.036), (0.141, 0.210), 0.180, 0.044, 0.40, None, "Forearm"),
    ("Tert1", (0.098, 0.040), (0.114, 0.208), 0.170, 0.045, 0.45, None, "UpperArm"),
    ("Tert2", (0.076, 0.036), (0.087, 0.207), 0.170, 0.045, 0.47, None, "UpperArm"),
    ("Tert3", (0.054, 0.032), (0.060, 0.212), 0.175, 0.045, 0.50, None, "UpperArm"),
]
# dorsal stacking (spec 4.7): T3 on top ... S1, P1 ... P10 lowest; LAYER_STEP between neighbours (along N_WING)
REMEX_ORDER = ["Tert3", "Tert2", "Tert1", "Sec6", "Sec5", "Sec4", "Sec3", "Sec2", "Sec1",
               "Prim01", "Prim02", "Prim03", "Prim04", "Prim05", "Prim06", "Prim07", "Prim08", "Prim09", "Prim10"]
LAYER_STEP = 0.0010

# covert pivot bones: per wing and arm segment a 2 x 2 grid of bones (heads at the corners of a wing-plane quad
# (x0..x1, y0..y1) that holds the roots of the marginal / lesser coverts), children of the arm bone, with the rest
# orientation of a reference remex. raven_anim gives them that remex's fold rotation, so a covert skinned to the four
# with the bilinear weights of its root (plumage.cov_skin) turns about ITS OWN ROOT: in the fold it stays on the arm
# skin and lies along the folded remiges (rigid on the remex it would swing about the remex base, 3-5 cm off; rigid on
# the arm it would point across the folded wing). Bones Cov{G}{1-4}.X: 1 (x0, y0), 2 (x1, y0), 3 (x0, y1), 4 (x1, y1).
COVERT_GROUPS = [("U", "UpperArm", "Tert2", (0.022, 0.126), (-0.042, 0.032)),
                 ("F", "Forearm", "Sec3", (0.112, 0.236), (-0.050, 0.032)),
                 ("H", "Hand", "Prim01", (0.218, 0.302), (-0.040, 0.014))]


def covert_group_bones(s="L"):
    """[(name, head, tail, parent, up)] of the covert pivot bones of side s"""
    out = []
    for g, par, ref, (x0, x1), (y0, y1) in COVERT_GROUPS:
        _b, d, n = remex_frame(ref, s)
        for k, (x, y) in enumerate(((x0, y0), (x1, y0), (x0, y1), (x1, y1))):
            h = wp(x, y, s, 0.004)
            out.append((f"Cov{g}{k + 1}.{s}", h, h + d * 0.03, f"{par}.{s}", n))
    return out


def wing_coords(p, s="L"):
    """bird-frame point -> wing-plane (x, y) of side s (inverse of wp, dropping the height)"""
    q = np.asarray(p, float) if s == "L" else mirror(p)
    return float(q[0]), float((q - WING_O) @ U_WING)


# rectrices (spec 4.8): R1 (central) .. R6 (outer); length from the pygostyle, width, glide / closed angle (deg)
# closed angles below spec 4.8's +-0.5..4 deg: with the roots converged on the pygostyle (rectrix_frame) they give the
# spec's closed width (0.055-0.065 at mid-tail) with the full-width vanes stacked under each other
RECTRICES = [(0.234, 0.050, 3, 0.0), (0.230, 0.050, 9, 0.3), (0.223, 0.049, 15, 0.6), (0.214, 0.047, 21, 1.0),
             (0.204, 0.045, 28, 1.3), (0.191, 0.042, 36, 1.6)]
TAIL_BIND_SPREAD = 0.5          # bind pose: the fan half way between closed (0) and the glide spread (1)
TAIL_DIR = unit(J["tailtip"] - J["pyg"])


def rectrix_angle(i, spread):
    """rachis angle from the midline (deg) of rectrix i (0 = R1) at a spread 0 (closed) .. 1 (glide fan)"""
    g, c = RECTRICES[i][2], RECTRICES[i][3]
    return c + (g - c) * spread


# --------------------------------------------------------------------------------------------------------------------
# Bones: name -> (head, tail, parent, up) ; `up` = the direction local +Z should point to (roll), None = world up rule
# --------------------------------------------------------------------------------------------------------------------
def remex_frame(name, s="L"):
    """base point, rachis direction, dorsal normal of a remex in the bind pose (layer offset applied)"""
    row = next(r for r in REMIGES if r[0] == name)
    (bx, by), (tx, ty) = row[1], row[2]
    k = REMEX_ORDER.index(name)
    h = -k * LAYER_STEP + 0.004                   # 4 mm above the wing-plane (bone line) at the top of the stack
    b = wp(bx, by, s, h)
    t = wp(tx, ty, s, h)
    d = unit(t - b)
    n = N_WING.copy()
    return b, d, n


def bone_table():
    B = {}
    B["Root"] = (V(0, 0, 0), V(0, -0.08, 0), None, V(0, 0, 1))
    B["Hips"] = (J["hips"], J["spine1"], "Root", None)
    B["Spine1"] = (J["spine1"], J["spine2"], "Hips", None)
    B["Spine2"] = (J["spine2"], J["neck1"], "Spine1", None)
    B["Neck1"] = (J["neck1"], J["neck2"], "Spine2", None)
    B["Neck2"] = (J["neck2"], J["neck3"], "Neck1", None)
    B["Neck3"] = (J["neck3"], J["atlas"], "Neck2", None)
    B["Head"] = (J["atlas"], J["billbase"], "Neck3", None)
    B["Jaw"] = (J["quadrate"], J["jawtip"], "Head", None)
    B["Throat"] = (J["throat0"], J["throat1"], "Head", V(0, -1, 0))
    B["TailBase"] = (J["tailbase"], J["pyg"], "Hips", None)
    B["Tail"] = (J["pyg"], J["pyg"] + TAIL_DIR * 0.04, "TailBase", None)
    for s in "LR":
        sx = 1.0 if s == "L" else -1.0
        e = side("eye", s)
        B[f"Eye.{s}"] = (e, e + V(sx * 0.012, 0, 0), "Head", V(0, 0, 1))
        B[f"Lid.{s}"] = (e, e + V(0, -0.012, 0), "Head", V(0, 0, 1))
        B[f"Shoulder.{s}"] = (side("scap", s), side("shoulder", s), "Spine2", None)
        B[f"UpperArm.{s}"] = (side("shoulder", s), side("elbow", s), f"Shoulder.{s}", N_WING)
        B[f"Forearm.{s}"] = (side("elbow", s), side("wrist", s), f"UpperArm.{s}", N_WING)
        B[f"Hand.{s}"] = (side("wrist", s), side("handtip", s), f"Forearm.{s}", N_WING)
        B[f"Alula.{s}"] = (side("wrist", s) + N_WING * 0.006, wp(0.262, -0.030, s, 0.006), f"Hand.{s}", N_WING)
        for name, *_rest, par in REMIGES:
            b, d, n = remex_frame(name, s)
            B[f"{name}.{s}"] = (b, b + d * 0.05, f"{par}.{s}", n)
        for name, h, t, par, n in covert_group_bones(s):
            B[name] = (h, t, par, n)
        for i in range(6):
            b, d, n = rectrix_frame(i, s, TAIL_BIND_SPREAD)
            B[f"Rect{i + 1}.{s}"] = (b, b + d * 0.05, "Tail", n)
        B[f"Thigh.{s}"] = (side("hip", s), side("knee", s), "Hips", None)
        B[f"Shin.{s}"] = (side("knee", s), side("ankle", s), f"Thigh.{s}", None)
        B[f"Tarsus.{s}"] = (side("ankle", s), side("mtp", s), f"Shin.{s}", None)
        for toe, (pts, tip) in TOES.items():
            P = [p if s == "L" else mirror(p) for p in pts]
            B[f"{toe}a.{s}"] = (P[0], P[1], f"Tarsus.{s}", V(0, 0, 1))
            B[f"{toe}b.{s}"] = (P[1], P[-1], f"{toe}a.{s}", V(0, 0, 1))
    return B


def rectrix_frame(i, s, spread):
    """base, direction, dorsal normal of rectrix i (0 = R1) on side s at a tail spread"""
    sx = 1.0 if s == "L" else -1.0
    ang = np.radians(rectrix_angle(i, spread)) * sx
    # the tail plane: contains TAIL_DIR and +X; the fan rotates about the plane normal
    nt = unit(np.cross(V(1, 0, 0), TAIL_DIR))          # dorsal normal of the tail plane
    if nt[2] < 0:
        nt = -nt
    x = V(1, 0, 0)
    d = unit(TAIL_DIR * np.cos(ang) + x * np.sin(ang))
    base = J["pyg"] + x * sx * (0.003 + 0.0015 * i) + TAIL_DIR * 0.006 - nt * (0.0010 * i)
    # tented section: outer feathers about 10 deg lower per side (spec 4.8), via the normal
    tilt = np.radians(-1.8 * i) * sx
    n = unit(nt * np.cos(tilt) + x * np.sin(tilt))
    return base, d, n


# --------------------------------------------------------------------------------------------------------------------
# SDF body.  Bone tags: a name or a chain (list); the stage A weights split a chain along its bones.
# --------------------------------------------------------------------------------------------------------------------
TRUNK = ["Hips", "Spine1", "Spine2"]
NECK = ["Spine2", "Neck1", "Neck2", "Neck3", "Head"]


def tube(points, rx, rz, up=(0, 0, 1), k=0.006, extra=0.35, **kw):
    """a smooth tapered tube: one ellipsoid per segment (radii interpolated), overlapping by `extra` of the radius"""
    P = []
    for i in range(len(points) - 1):
        a, b = np.asarray(points[i], float), np.asarray(points[i + 1], float)
        r1 = 0.5 * (rx[i] + rx[i + 1]); r2 = 0.5 * (rz[i] + rz[i + 1])
        P.append(ellipsoid_seg(a, b, r1, r2, up=up, extra=extra * min(r1, r2), k=k, **kw))
    return P


def trunk_prims():
    P = []
    u = unit(V(0, 0.848, -0.530))               # spine direction (back-down)
    nrm = unit(V(0, 0.530, 0.848))
    R = np.stack([V(1, 0, 0), u, nrm], axis=1)
    # the main trunk: dorsal line (-0.007, 0.262), belly (-0.079, 0.130), 0.12 wide below the wings
    P.append(Ellipsoid(V(0, -0.050, 0.200), V(0.050, 0.128, 0.074), R, k=0.0, bones=TRUNK, tag="trunk"))
    # breast: fullest forward point (-0.188, 0.231)
    # (spec 3.1 ventral line: (-0.188, 0.231), (-0.168, 0.195), (-0.132, 0.166) - the breast front runs up-forward)
    Rb = np.stack([V(1, 0, 0), unit(V(0, -0.60, 0.80)), unit(V(0, 0.80, 0.60))], axis=1)
    P.append(Ellipsoid(V(0, -0.142, 0.208), V(0.052, 0.052, 0.036), Rb, k=0.020, bones=["Spine2"], tag="breast"))
    # breast sides (pectorals) under the folded carpal: the breast is 0.12 wide below the wings and its feathers
    # overlap the carpal bend by 1-2 cm (spec 3.2, 4.9)
    for sx in (1, -1):
        P.append(Ellipsoid(V(sx * 0.030, -0.140, 0.220), V(0.027, 0.036, 0.034), R, k=0.020, bones=["Spine2"],
                           tag="breast"))
        # the shoulder bump in front of the folded carpal: the breast plumage rises over the wing bend
        P.append(Ellipsoid(V(sx * 0.044, -0.146, 0.248), V(0.020, 0.026, 0.028), R, k=0.022, bones=["Spine2"],
                           tag="breast"))
    # mantle / shoulders (the back is broad where the folded wings sit)
    P.append(Ellipsoid(V(0, -0.070, 0.262), V(0.044, 0.070, 0.030), R, k=0.030, bones=["Spine2"], tag="mantle"))
    # belly and vent fluff
    P.append(Ellipsoid(V(0, -0.010, 0.128), V(0.046, 0.070, 0.036), R, k=0.030, bones=["Hips"], tag="belly"))
    P.append(Ellipsoid(V(0, 0.056, 0.118), V(0.034, 0.040, 0.026), R, k=0.025, bones=["Hips", "TailBase"], tag="vent"))
    # rump / uropygium to the pygostyle
    P += tube([V(0, 0.000, 0.215), V(0, 0.060, 0.190), V(0, 0.100, 0.172)], [0.040, 0.030, 0.018],
              [0.032, 0.024, 0.012], up=nrm, k=0.020, bones=["Hips", "TailBase", "Tail"], tag="rump")
    # undertail coverts: end (0.155, 0.113), 1-1.5 cm below the tail underside
    P += tube([V(0, 0.070, 0.128), V(0, 0.115, 0.118), V(0, 0.150, 0.118)], [0.022, 0.018, 0.010],
              [0.016, 0.012, 0.006], up=nrm, k=0.016, bones=["TailBase", "Tail"], tag="undertail")
    return P


def neck_head_prims():
    P = []
    # neck: thick (side depth ~0.08 at z 0.30), merging into mantle and head
    P += tube([J["neck1"] + V(0, 0.005, -0.012), J["neck2"] + V(0, 0.004, -0.008), J["neck3"] + V(0, 0.006, -0.002),
               J["atlas"] + V(0, 0.012, 0.004)], [0.040, 0.036, 0.031, 0.027], [0.044, 0.040, 0.035, 0.030],
              k=0.030, bones=NECK[1:], tag="neck")
    # head (spec 3.3): the forehead rises at ~31 deg continuing the culmen, flattens to ~20 deg into a crown that
    # peaks behind the eye (-0.209, 0.389); the occiput (-0.168, 0.375) rounds into a thick nape with no notch.
    # Widths: 0.052 at the eyes (the widest), 0.044 at the crown, 0.040 at the cheeks / bill base.
    P.append(Ellipsoid(V(0, -0.203, 0.358), V(0.0225, 0.036, 0.028), k=0.016, bones="Head", tag="head"))
    P.append(Ellipsoid(V(0, -0.199, 0.371), V(0.0205, 0.031, 0.0175), k=0.012, bones="Head", tag="crown"))
    # forehead ramp: from the culmen feather base (-0.248, 0.369) up to the crown, a flat wedge over the bill base
    P.append(ellipsoid_seg(V(0, -0.247, 0.3585), V(0, -0.212, 0.3775), 0.0135, 0.0095, extra=0.002, k=0.010,
                           bones="Head", tag="forehead"))
    # the lores and the brow ridge around the eye (the head is widest here); the lores cover the bill base
    # sides back to the rictus
    for sx in (1, -1):
        P.append(Ellipsoid(V(sx * 0.0115, -0.228, 0.356), V(0.0140, 0.019, 0.0145), k=0.010, bones="Head",
                           tag="brow"))
        P.append(Ellipsoid(V(sx * 0.0085, -0.2385, 0.3465), V(0.0085, 0.0125, 0.0110), k=0.008, bones="Head",
                           tag="lores"))
        # cheeks / ear coverts
        P.append(Ellipsoid(V(sx * 0.0115, -0.209, 0.343), V(0.0135, 0.024, 0.019), k=0.012, bones="Head",
                           tag="cheek"))
    # nape: fills the occiput-neck junction (no notch behind the head)
    P.append(Ellipsoid(V(0, -0.166, 0.346), V(0.0235, 0.030, 0.027), k=0.020, bones=["Neck3", "Head"], tag="nape"))
    # chin / throat skin under the hackles; the hackle strips stand 1-2 cm off it and make the outline
    # (spec 3.5: hackle front (-0.231, 0.312), (-0.213, 0.276), tips (-0.192, 0.240))
    P += tube([V(0, -0.235, 0.327), V(0, -0.217, 0.309), V(0, -0.196, 0.286), J["neck1"] + V(0, -0.034, -0.040)],
              [0.0105, 0.0160, 0.0215, 0.032], [0.007, 0.011, 0.016, 0.028], k=0.018,
              bones=["Head", "Throat", "Neck2", "Neck1"], tag="throat")
    return P


# --------------------------------------------------------------------------------------------------------------------
# Bill (spec 3.4): two explicit LOFTED shells, not SDF - the upper mandible (rigid on Head) and the lower mandible
# (rigid on Jaw).  A 1.5 mm SDF grid cannot hold the sharp tomium or a clean gape, so stage A meshes the bill here
# and only the head skin comes from the SDF (the loft bases sit inside the head).  Profiles are functions of
# u = -y (distance in front of the origin), sliced vertically:
#   culmen: straight at ~31 deg for the proximal half (under the forehead feathers and the bristle tuft), then
#           curving down into a short hook (55-70 deg at the tip); tip (-0.304, 0.321)
#   tomium: the gape line gape_z(); the upper's edge drops into the hook over the last 8 mm
#   gonys:  nearly straight; depth 0.030-0.034 at the feather line (60 % upper), 0.018 at 2/3, 0.006 at the hook
#   width:  0.022 at the base, 0.014 mid, 0.006 about 1 cm from the tip
# Each shell is an outer sheet (part 'bill') and an inner sheet (palate / floor of the mouth: part 'mouth') that
# share their positions along the tomium but not their vertices (a hard edge), plus a hidden base cap.
# --------------------------------------------------------------------------------------------------------------------
BILL_TIP = 0.3043                 # u of the hook tip
BILL_TIP_Z = 0.3202
LOW_TIP = 0.2978                  # u of the lower mandible tip (tucked under the hook)
BILL_U0 = 0.226                   # loft base (inside the head)
_CUL = ((0.222, 0.3790), (0.234, 0.3728), (0.248, 0.3656), (0.260, 0.3592), (0.270, 0.3533), (0.280, 0.3461),
        (0.290, 0.3375), (0.296, 0.3315), (0.300, 0.3266), (0.3025, 0.3231), (0.3038, 0.3211),
        (BILL_TIP, BILL_TIP_Z))
_GONYS = ((0.222, 0.3262), (0.240, 0.3245), (0.255, 0.3234), (0.270, 0.3225), (0.284, 0.3218), (0.291, 0.3219),
          (0.2953, 0.3228), (LOW_TIP, 0.3243))
_WU = ((0.222, 0.0122), (0.238, 0.0116), (0.248, 0.0110), (0.262, 0.0090), (0.276, 0.0071), (0.288, 0.0050),
       (0.294, 0.0037), (0.300, 0.0022), (0.3030, 0.0011), (BILL_TIP, 0.0))
HOOK_U = 0.2925                   # the upper tomium leaves the gape line here and drops into the hook


def _prof(tab, u):
    from scipy.interpolate import PchipInterpolator
    t = np.array(tab, float)
    return PchipInterpolator(t[:, 0], t[:, 1], extrapolate=True)(np.asarray(u, float))


def bill_culmen(u):
    return _prof(_CUL, u)


def bill_tomium_upper(u):
    u = np.asarray(u, float)
    g = gape_z(-u)
    h = np.clip((u - HOOK_U) / (BILL_TIP - HOOK_U), 0, 1)
    drop = float(gape_z(-BILL_TIP)) - BILL_TIP_Z
    return g - drop * h ** 2.2


def bill_width(u):
    return np.maximum(_prof(_WU, u), 0.0)


def _stations(u0, u1, n):
    t = np.linspace(0, 1, n + 1)
    return u0 + (u1 - u0) * (1 - (1 - t) ** 1.3)                      # a little denser toward the tip


def _upper_ring(u, ns, npal):
    """outer half-profile (culmen -> tomium, ns+1 points) and palate half-profile (tomium -> midline, npal+1) as (x, z)"""
    zc, zb, w = float(bill_culmen(u)), float(bill_tomium_upper(u)), float(bill_width(u))
    d = max(zc - zb, 1e-5)
    s = np.linspace(0, 1, ns + 1)
    g = np.sqrt(np.clip(1 - (1 - s) ** 2.2, 0, 1))
    side = np.stack([w * g, zc - d * s], 1)
    j = np.linspace(0, 1, npal + 1)
    x = w * (1 - j)
    pal = np.stack([x, zb + 0.28 * d * (1 - (x / max(w, 1e-6)) ** 2)], 1)
    return side, pal


def _lower_ring(u, ns, npal):
    """outer half-profile (tomium -> gonys, ns+1) and floor-of-mouth half-profile (tomium -> midline, npal+1)"""
    zt = float(gape_z(-u)) - 0.0003
    zb = float(_prof(_GONYS, u))
    taper = np.clip((LOW_TIP - u) / 0.0075, 0, 1) ** 0.5
    w = 0.90 * float(bill_width(u)) * taper
    d = max(zt - zb, 1e-5)
    s = np.linspace(0, 1, ns + 1)
    g = np.sqrt(np.clip(1 - s ** 2.4, 0, 1))
    side = np.stack([w * g, zt - d * s], 1)
    j = np.linspace(0, 1, npal + 1)
    x = w * (1 - j)
    flo = np.stack([x, zt - 0.30 * d * (1 - (x / max(w, 1e-6)) ** 2)], 1)
    return side, flo


def _grid_faces(R, C, off=0):
    idx = np.arange(R * C).reshape(R, C) + off
    a, b, c, d = idx[:-1, :-1], idx[:-1, 1:], idx[1:, :-1], idx[1:, 1:]
    return np.concatenate([np.stack([a, c, d], -1).reshape(-1, 3), np.stack([a, d, b], -1).reshape(-1, 3)])


def _orient(Vx, F, want):
    """flip the whole sheet F if most of its face normals point against `want` (F,3)"""
    tri = Vx[F]
    nrm = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    return F[:, ::-1] if np.einsum("ij,ij->i", nrm, want).sum() < 0 else F


def bill_mesh(which, n_st=22, ns=7, npal=3):
    """explicit mesh of one mandible, which = 'upper' | 'lower'.  Returns V (n,3), F (m,3), mouth (m,) bool (the
    palate / floor-of-mouth sheet).  Every sheet faces outward: the outer sheet away from the mandible core, the inner
    sheet into the mouth (the gape), the base cap backward into the head."""
    up = which == "upper"
    if up:
        u0, u1, ring = BILL_U0, BILL_TIP, _upper_ring
        tip = V(0, -BILL_TIP, BILL_TIP_Z)
    else:
        u0, u1, ring = BILL_U0 + 0.004, LOW_TIP, _lower_ring
        tip = V(0, -LOW_TIP, 0.5 * (float(gape_z(-LOW_TIP)) - 0.0003 + float(_prof(_GONYS, LOW_TIP))))
    us = _stations(u0, u1, n_st)[:-1]                           # the tip is one point
    outer, inner = [], []
    for u in us:
        side, pal = ring(u, ns, npal)
        # across the midline: the left half (+X) then its mirror (upper: tomium L -> culmen -> tomium R;
        # lower: tomium L -> gonys -> tomium R; inner: tomium L -> midline -> tomium R)
        o = side[::-1] if up else side
        o = np.concatenate([o, (o[::-1] * [-1, 1])[1:]])
        i_ = np.concatenate([pal, (pal[::-1] * [-1, 1])[1:]])
        outer.append(np.stack([o[:, 0], np.full(len(o), -u), o[:, 1]], 1))
        inner.append(np.stack([i_[:, 0], np.full(len(i_), -u), i_[:, 1]], 1))
    Vs, Fs, Ms, base = [], [], [], 0
    core = lambda c: (0.5 * (bill_culmen(-c[:, 1]) + bill_tomium_upper(-c[:, 1])) if up
                      else 0.5 * (gape_z(c[:, 1]) + _prof(_GONYS, -c[:, 1])))
    for rows, mouth in ((outer, False), (inner, True)):
        R, C = len(rows), len(rows[0])
        Vx = np.concatenate(rows + [tip[None]])
        F = _grid_faces(R, C)
        t = R * C
        F = np.concatenate([F, np.array([(t - C + c, t, t - C + c + 1) for c in range(C - 1)])])
        cen = Vx[F].mean(1)
        if mouth:
            want = np.tile(V(0, 0, -1.0 if up else 1.0), (len(F), 1))
        else:
            want = np.stack([cen[:, 0], np.zeros(len(F)), cen[:, 2] - core(cen)], 1)
        F = _orient(Vx, F, want)
        Vs.append(Vx); Fs.append(F + base); Ms.append(np.full(len(F), mouth)); base += len(Vx)
    # base cap, hidden in the head: the closed base loop (outer row + the inner row between its ends)
    loop = np.concatenate([outer[0], inner[0][-2:0:-1]])
    Vx = np.concatenate([loop, loop.mean(0)[None]])
    n = len(loop)
    F = np.array([(k, (k + 1) % n, n) for k in range(n)])
    F = _orient(Vx, F, np.tile(V(0, 1.0, 0), (len(F), 1)))
    Vs.append(Vx); Fs.append(F + base); Ms.append(np.zeros(len(F), bool))
    Vx, F, M = np.concatenate(Vs), np.concatenate(Fs), np.concatenate(Ms)
    # drop the zero-area triangles where the tip fans or the rings pinch
    ar = np.linalg.norm(np.cross(Vx[F[:, 1]] - Vx[F[:, 0]], Vx[F[:, 2]] - Vx[F[:, 0]]), axis=1)
    keep = ar > 1e-12
    return Vx, F[keep], M[keep]


class MeshSDF:
    """signed distance to an explicit closed mesh (nearest dense surface sample, sign from its normal); good near the
    surface.  Used for the bill so the plumage can be seated on it (plumage.seat) and eval_prims() sees it; stage A
    meshes the bill from bill_mesh() directly and leaves these out of its SDF grid."""
    op = "add"; pad = 0.0

    def __init__(self, Vx, F, k=0.0, bones=None, tag="", inside=None):
        from scipy.spatial import cKDTree
        self.inside = inside
        tri = Vx[F]
        nrm = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
        area = np.linalg.norm(nrm, axis=1)
        ok = area > 1e-12
        tri, nrm = tri[ok], nrm[ok] / area[ok, None]
        # 6 samples per triangle (centre + 3 corners + 2 edge midpoints)
        w = np.array([(1 / 3, 1 / 3, 1 / 3), (0.8, 0.1, 0.1), (0.1, 0.8, 0.1), (0.1, 0.1, 0.8), (0.45, 0.45, 0.1),
                      (0.1, 0.45, 0.45)])
        S = np.einsum("sk,tkd->tsd", w, tri).reshape(-1, 3)
        self.S, self.N = S, np.repeat(nrm, len(w), 0)
        self.tree = cKDTree(S)
        self.lo, self.hi = Vx.min(0), Vx.max(0)
        self.k, self.bones, self.tag = k, bones, tag

    def aabb(self):
        return self.lo - 0.004, self.hi + 0.004

    def dist(self, P):
        d, j = self.tree.query(P)
        if self.inside is not None:                    # exact inside test (the analytic loft): robust sign
            return np.where(self.inside(P), -d, d)
        sgn = np.sign(np.einsum("ij,ij->i", P - self.S[j], self.N[j]))
        sgn[sgn == 0] = 1
        return d * sgn


def bill_inside(which, P):
    """True where P lies inside the analytic loft of a mandible (the vertical section at u = -y)"""
    P = np.asarray(P, float)
    u, ax, z = -P[:, 1], np.abs(P[:, 0]), P[:, 2]
    if which == "upper":
        ok = (u > BILL_U0) & (u < BILL_TIP)
        uu = np.clip(u, BILL_U0, BILL_TIP)
        zc, zb, w = bill_culmen(uu), bill_tomium_upper(uu), bill_width(uu)
        d = np.maximum(zc - zb, 1e-6)
        r = np.clip(ax / np.maximum(w, 1e-9), 0, 1)
        s_out = 1 - (1 - r * r) ** (1 / 2.2)             # inverse of g(s) = sqrt(1 - (1 - s)^2.2)
        top = zc - d * s_out
        pal = zb + 0.28 * d * (1 - r * r)
        return ok & (ax < w) & (z < top) & (z > pal)
    u0 = BILL_U0 + 0.004
    ok = (u > u0) & (u < LOW_TIP)
    uu = np.clip(u, u0, LOW_TIP)
    zt = gape_z(-uu) - 0.0003
    zb = _prof(_GONYS, uu)
    w = 0.90 * bill_width(uu) * np.clip((LOW_TIP - uu) / 0.0075, 0, 1) ** 0.5
    d = np.maximum(zt - zb, 1e-6)
    r = np.clip(ax / np.maximum(w, 1e-9), 0, 1)
    bot = zt - d * (1 - r * r) ** (1 / 2.4)
    flo = zt - 0.30 * d * (1 - r * r)
    return ok & (ax < w) & (z > bot) & (z < flo)


_BILL_SDF = {}


def bill_prims():
    """the two mandibles as MeshSDF prims (tags 'bill' / 'bill_low'; bones Head / Jaw)"""
    if not _BILL_SDF:
        for which, tag, bone in (("upper", "bill", "Head"), ("lower", "bill_low", "Jaw")):
            Vx, F, _m = bill_mesh(which, n_st=60, ns=16, npal=6)
            _BILL_SDF[which] = MeshSDF(Vx, F, k=0.0, bones=bone, tag=tag,
                                       inside=lambda P, w=which: bill_inside(w, P))
    return [_BILL_SDF["upper"], _BILL_SDF["lower"]]


def gape_z(y):
    """z of the tomium (gape line) along the bill (spec 3.4): rictus (-0.238, 0.340) -> (-0.270, 0.334) -> tip 0.325"""
    y = np.asarray(y, float)
    return np.interp(-y, [0.230, 0.238, 0.270, 0.300, 0.310], [0.341, 0.340, 0.334, 0.3255, 0.3245])


def leg_prims(s):
    P = []
    j = lambda n: side(n, s)
    sx = 1 if s == "L" else -1
    # thigh inside the body + the feathered "trousers" (tibia) down to z 0.067-0.075
    P.append(ellipsoid_seg(j("hip") + V(sx * 0.004, -0.010, -0.012), j("knee") + V(sx * 0.004, 0.000, -0.010),
                           0.024, 0.022, k=0.022, bones=[f"Thigh.{s}", f"Shin.{s}"], tag="thigh"))
    P.append(ellipsoid_seg(j("knee") + V(sx * 0.002, 0.000, -0.004), j("ankle") + V(0, -0.004, 0.002),
                           0.019, 0.018, extra=0.004, k=0.016, bones=[f"Shin.{s}"], tag="trouser"))
    # the ankle (intertarsal joint): the trouser feathers end just below it, the bare tarsus starts
    P.append(Sphere(j("ankle") + V(0, -0.001, 0.001), 0.0068, k=0.008, bones=[f"Shin.{s}", f"Tarsus.{s}"], tag="tarsus"))
    # bare tarsus: 9 x 6.5 mm mid, 11 mm at the ankle, 10 mm at the MTP
    P.append(RoundCone(j("ankle"), j("mtp") + V(0, 0, 0.004), 0.0055, 0.0048, k=0.004, bones=f"Tarsus.{s}", tag="tarsus"))
    # MTP pad
    P.append(Ellipsoid(j("mtp") + V(0, 0.002, -0.004), V(0.0065, 0.0075, 0.0055), k=0.004, bones=f"Tarsus.{s}", tag="toe"))
    for toe, (pts, tip) in TOES.items():
        Q = [p if s == "L" else mirror(p) for p in pts]
        n = len(Q)
        for i in range(n - 1):
            r0 = 0.0033 - 0.0010 * i / max(n - 2, 1)
            r1 = r0 - 0.0005
            bone = f"{toe}a.{s}" if i == 0 else f"{toe}b.{s}"
            P.append(RoundCone(Q[i], Q[i + 1], r0, r1, k=0.0025, bones=bone, tag="toe"))
            # a bulbous pad under each joint (+5 mm below the MTP line)
            P.append(Ellipsoid(Q[i + 1] + V(0, 0, -0.0012), V(0.0034, 0.0040, 0.0030), k=0.002, bones=bone, tag="toe"))
    return P


def claw_prims(s):
    """curved claws (arc 110-130 deg, 5 mm deep at the base, needle tips); rigid on the distal toe bone"""
    P = []
    for toe, (pts, tip) in TOES.items():
        Q = [p if s == "L" else mirror(p) for p in pts]
        T = tip if s == "L" else mirror(tip)
        base = Q[-1]
        d = unit(V(T[0] - base[0], T[1] - base[1], 0))
        L = np.linalg.norm((T - base)[:2]) + 0.002
        up = V(0, 0, 1)
        # a quadratic arc from the base (on the toe axis) over the top to the ground tip
        c0 = base + up * 0.0005
        c1 = base + d * L * 0.55 + up * 0.0030
        c2 = V(T[0], T[1], 0.0006)
        pts_ = [(1 - t) ** 2 * c0 + 2 * (1 - t) * t * c1 + t * t * c2 for t in np.linspace(0, 1, 6)]
        rs = np.linspace(0.0024, 0.0004, 6)
        for i in range(5):
            P.append(RoundCone(pts_[i], pts_[i + 1], rs[i], rs[i + 1], k=0.0006, bones=f"{toe}b.{s}", tag="claw"))
    return P


def wing_arm_prims(s):
    """the arm skin in the spread pose: humerus / ulna / hand round cones and the propatagium (leading-edge web),
    flattened in the wing plane; covered by the coverts (feather strips)."""
    P = []
    j = lambda n: side(n, s)
    ch = [f"UpperArm.{s}", f"Forearm.{s}"]
    Rw = np.stack([V(1, 0, 0) if s == "L" else V(-1, 0, 0), U_WING, N_WING], axis=1)
    P.append(RoundCone(j("shoulder") + N_WING * 0.002, j("elbow") + N_WING * 0.002, 0.020, 0.012, k=0.026,
                       bones=[f"Shoulder.{s}", f"UpperArm.{s}"], tag="arm"))
    P.append(RoundCone(j("elbow") + N_WING * 0.002, j("wrist") + N_WING * 0.001, 0.011, 0.0063, k=0.008,
                       bones=[f"UpperArm.{s}", f"Forearm.{s}"], tag="arm"))
    P.append(RoundCone(j("wrist") + N_WING * 0.001, j("handtip"), 0.0063, 0.0035, k=0.005,
                       bones=[f"Forearm.{s}", f"Hand.{s}"], tag="arm"))
    # propatagium: from the leading-edge root (0.010, -0.028) to the wrist; the web between shoulder, elbow and wrist
    for (x0, y0), (x1, y1), w in (((0.030, -0.018), (0.215, -0.024), 0.012),):
        a, b = wp(x0, y0, s, 0.001), wp(x1, y1, s, 0.001)
        c = (a + b) / 2
        L = np.linalg.norm(b - a) / 2
        Rl = np.stack([unit(b - a), unit(np.cross(N_WING, unit(b - a))), N_WING], axis=1)
        P.append(Ellipsoid(c + Rl[:, 1] * 0.010, V(L, 0.022, 0.0045), Rl, k=0.012, bones=ch, tag="patagium"))
    # the elbow web (behind the arm, over the secondary bases)
    a, b = wp(0.060, 0.018, s, 0.001), wp(0.200, 0.012, s, 0.001)
    Rl = np.stack([unit(b - a), unit(np.cross(N_WING, unit(b - a))), N_WING], axis=1)
    P.append(Ellipsoid((a + b) / 2, V(np.linalg.norm(b - a) / 2, 0.016, 0.0045), Rl, k=0.012, bones=ch, tag="patagium"))
    return P


def body_prims():
    P = trunk_prims() + neck_head_prims() + bill_prims()
    for s in "LR":
        P += leg_prims(s) + wing_arm_prims(s)
    return P


# --------------------------------------------------------------------------------------------------------------------
# Eye: eyeball (Eye.X) with the pale beaded lid ring (part of the head skin texture) and the nictitating membrane
# (Lid.X, a thin shell over the front of the eyeball that slides across for the blink).
# --------------------------------------------------------------------------------------------------------------------
EYE_R = 0.0065           # eyeball radius (visible iris 10 mm inside the lid ring, ring 16 mm)


def eye_frame(s):
    c = side("eye", s)
    sx = 1.0 if s == "L" else -1.0
    n = unit(V(sx * 0.92, -0.33, 0.15))          # looks out, a little forward and up
    return c, n


class Torus:
    """torus about axis n through c: ring radius R, tube radius r (a Prim for the sdf module)"""
    pad = 0.0

    def __init__(self, c, n, R, r, k=0.0, op="add", bones=None, tag=""):
        self.c, self.n, self.R, self.r = np.asarray(c, float), unit(n), R, r
        self.k, self.op, self.bones, self.tag = k, op, bones, tag

    def aabb(self):
        e = self.R + self.r + self.k
        return self.c - e, self.c + e

    def dist(self, P):
        q = P - self.c
        h = q @ self.n
        rad = np.linalg.norm(q - h[:, None] * self.n, axis=1)
        return np.hypot(rad - self.R, h) - self.r


LID_T, LID_R, LID_W = 0.0044, 0.0060, 0.0012     # lid ring: plane offset along the eye axis, ring and tube radius


def eye_socket_prims():
    """a shallow recess where the eyeball sits (subtracted from the head), then the eyelid margin: a raised ring
    around the visible iris (spec 3.3: outer diameter 0.016, 2-3 mm wide; the texture paints it pale and beaded -
    faces of the body within LID_R +- 2.5 mm of the eye axis, 3-6 mm out along it)"""
    P = []
    for s in "LR":
        c, n = eye_frame(s)
        P.append(Sphere(c + n * 0.0015, EYE_R + 0.0006, k=0.0025, op="sub", bones="Head", tag="socket"))
    for s in "LR":
        c, n = eye_frame(s)
        P.append(Torus(c + n * LID_T, n, LID_R, LID_W, k=0.0015, bones="Head", tag="lid"))
    return P
