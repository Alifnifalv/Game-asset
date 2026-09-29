"""Rottweiler (male) anatomy: rest skeleton joints and the SDF primitives of the body and the separate parts.

Conventions (as the calf): meters, Z up, the dog faces -Y, ground z = 0, '.L' = +X (the dog's left).
Size: a male Rottweiler, withers 0.66 m (FCI standard 61-68 cm), trunk length point of shoulder to point of buttock
0.74 m (standard: at most 15 % over the withers height), chest depth 50 % of the withers height, skull:muzzle 3:2.
The whole pipeline is authored at this final size (no scale stage).

Every primitive carries the bone (or bone chain) it moves with; dog_mesh.py derives the skin weights from them, so the
anatomy and the weights never drift apart.
"""
import numpy as np
from sdf import Sphere, Ellipsoid, ellipsoid_seg, RoundCone, RoundBox, frame_from

V = lambda *a: np.array(a, dtype=float)


def mirror(p):
    p = np.array(p, dtype=float); p[0] = -p[0]; return p


# --------------------------------------------------------------------------------------------------------------------
# Head placement. Everything of the head (skull, muzzle, jaw, lips, nose, ears, eyes, mouth cut, teeth, tongue and the
# head joints) is authored in the design frame of the first build, whose atlas joint is ATLAS0, and placed by
# H(p) = HEAD_POS + HEAD_SCALE * RH @ (p - ATLAS0): HEAD_POS moves the atlas (the head carriage), HEAD_PITCH (deg,
# + = nose down) tilts the head about it and HEAD_SCALE scales the design frame about the atlas (the HE/HC/HB radii,
# the eyeball, socket, lids, ear and tongue scale with it; Hd, a direction, does not). dog_stage_a.py and
# dog_textures.py map points back with H_inv for the lip line and the head markings, so changing these values moves
# the whole head consistently.
# --------------------------------------------------------------------------------------------------------------------
ATLAS0 = V(0, -0.425, 0.775)
HEAD_POS = V(0, -0.440, 0.740)      # the atlas, lowered and set back: the nose is level with the withers top (GiM)
HEAD_PITCH = 10.0                   # + = nose down
HEAD_SCALE = 1.05                   # the head design frame is scaled about the atlas


def _rh():
    a = np.radians(HEAD_PITCH)
    c, s_ = np.cos(a), np.sin(a)
    return np.array([[1, 0, 0], [0, c, -s_], [0, s_, c]])


RH = _rh()


def H(p):
    """design-frame head point -> world"""
    return HEAD_POS + HEAD_SCALE * (RH @ (np.asarray(p, dtype=float) - ATLAS0))


def Hd(v):
    """design-frame head direction -> world (a rotation only: not scaled)"""
    return RH @ np.asarray(v, dtype=float)


def H_inv(P):
    """world points (N, 3) or (3,) -> design-frame head coordinates"""
    P = np.asarray(P, dtype=float)
    return (P - HEAD_POS) @ RH / HEAD_SCALE + ATLAS0


# --------------------------------------------------------------------------------------------------------------------
# Rest skeleton (joint positions). Leg joints are given for the left side (+X) and mirrored.
# --------------------------------------------------------------------------------------------------------------------
J = {
    # spine, midline
    "hips":      V(0, 0.150, 0.555),    # Hips bone head (lumbosacral region); the body root
    "sacrum":    V(0, 0.330, 0.585),
    "tail0":     V(0, 0.365, 0.588),
    "lumbar":    V(0, -0.020, 0.575),
    "thorax":    V(0, -0.170, 0.572),
    "withers":   V(0, -0.285, 0.560),   # T1 (the skin top of the withers is 0.66 m: the dorsal spines stand up)
    "neck1":     V(0, -0.330, 0.600),   # C7/C6
    "neck2":     V(0, -0.392, 0.672),   # follows the lower head carriage (no kink between Neck1 and Neck2)
    "atlas":     HEAD_POS.copy(),       # head joint
    # head joints: design frame, placed by H()
    "snout":     H(V(0, -0.662, 0.752)),   # nose tip
    "tmj":       H(V(0, -0.470, 0.718)),   # jaw hinge (midline stand-in for both TMJs)
    "chin":      H(V(0, -0.640, 0.686)),
    "tongue0":   H(V(0, -0.495, 0.703)),
    "tongue1":   H(V(0, -0.555, 0.703)),
    "tongue2":   H(V(0, -0.610, 0.703)),
    "tongue3":   H(V(0, -0.645, 0.703)),
    # ear (left): base on the skull's top corner, fold crest, flap tip beside the cheek
    "ear0":      H(V(0.054, -0.472, 0.866)),
    "ear1":      H(V(0.090, -0.478, 0.862)),
    "ear2":      H(V(0.109, -0.516, 0.767)),
    # front leg (left)
    "scap":      V(0.062, -0.215, 0.615),
    "shoulder":  V(0.098, -0.340, 0.450),
    "elbow":     V(0.098, -0.245, 0.325),   # high elbow: a long fore leg below the chest (GiM)
    "carpus":    V(0.094, -0.254, 0.105),
    "mcp":       V(0.094, -0.270, 0.036),
    "ftoe":      V(0.094, -0.318, 0.014),
    # hind leg (left)
    "hip":       V(0.086, 0.268, 0.522),
    "stifle":    V(0.100, 0.186, 0.340),
    "hock":      V(0.090, 0.345, 0.145),
    "mtp":       V(0.090, 0.336, 0.038),
    "htoe":      V(0.090, 0.290, 0.014),
    # tail (hanging at rest)
    "tail1":     V(0, 0.420, 0.560),
    "tail2":     V(0, 0.458, 0.505),
    "tail3":     V(0, 0.478, 0.443),
    "tail4":     V(0, 0.490, 0.378),
    "tail5":     V(0, 0.500, 0.314),    # the lower third hooks back (resting sickle hook)
    "tail6":     V(0, 0.522, 0.258),
}

TOES = ((0.0128, -0.041), (-0.0128, -0.041), (0.0300, -0.029), (-0.0300, -0.029))   # digits III/IV, II/V
TOE_R = (0.0136, 0.0050, 0.0136)     # toe ellipsoid: half width, length extra past its axis, half depth (x PAW_SC)
PAW_SC = (1.26, 1.16)                # front, hind paw scale (dog_textures reads TOES and PAW_SC for the toe creases)
CLAW_M = (-0.0110, -0.0010)          # claw bend relative to the toe's front-low axis end (y, z; x PAW_SC)
CLAW_TIP = (-0.0035, 0.0020)         # claw tip: dy from the bend, absolute z
CLAW_R = (0.0050, 0.0040, 0.0013)    # claw radii: root, bend, tip
TAIL_R = [0.030, 0.027, 0.024, 0.021, 0.018, 0.015, 0.012]


def side(name, s):
    """Joint `name` on side s ('L' or 'R')."""
    p = J[name]
    return p.copy() if s == "L" else mirror(p)


# --------------------------------------------------------------------------------------------------------------------
# Bones: name -> (head joint, tail joint, parent). Built for both sides by rig code.
# --------------------------------------------------------------------------------------------------------------------
def bone_table():
    B = {}
    B["Root"] = (V(0, 0, 0), V(0, -0.15, 0), None)
    B["Hips"] = (J["hips"], J["sacrum"], "Root")
    B["Spine1"] = (J["hips"], J["lumbar"], "Hips")
    B["Spine2"] = (J["lumbar"], J["thorax"], "Spine1")
    B["Spine3"] = (J["thorax"], J["withers"], "Spine2")
    B["Neck1"] = (J["withers"], J["neck2"], "Spine3")
    B["Neck2"] = (J["neck2"], J["atlas"], "Neck1")
    B["Head"] = (J["atlas"], H(V(0, -0.560, 0.790)), "Neck2")
    B["Nose"] = (H(V(0, -0.560, 0.790)), J["snout"], "Head")        # muzzle (sniff wrinkle / nose twitch)
    B["Jaw"] = (J["tmj"], J["chin"], "Head")
    B["Tongue1"] = (J["tongue0"], J["tongue1"], "Jaw")
    B["Tongue2"] = (J["tongue1"], J["tongue2"], "Tongue1")
    B["Tongue3"] = (J["tongue2"], J["tongue3"], "Tongue2")
    tails = ["tail0", "tail1", "tail2", "tail3", "tail4", "tail5", "tail6"]
    for i in range(6):
        B[f"Tail{i + 1}"] = (J[tails[i]], J[tails[i + 1]], "Hips" if i == 0 else f"Tail{i}")
    for s in "LR":
        B[f"Ear1.{s}"] = (side("ear0", s), side("ear1", s), "Head")
        B[f"Ear2.{s}"] = (side("ear1", s), side("ear2", s), f"Ear1.{s}")
        ec, en, _ = eye_frame(s)
        B[f"Eye.{s}"] = (ec, ec + en * 0.02, "Head")
        B[f"Scapula.{s}"] = (side("scap", s), side("shoulder", s), "Spine3")
        B[f"UpperArm.{s}"] = (side("shoulder", s), side("elbow", s), f"Scapula.{s}")
        B[f"Forearm.{s}"] = (side("elbow", s), side("carpus", s), f"UpperArm.{s}")
        B[f"FrontFoot.{s}"] = (side("carpus", s), side("mcp", s), f"Forearm.{s}")
        B[f"FrontToe.{s}"] = (side("mcp", s), side("ftoe", s), f"FrontFoot.{s}")
        B[f"Thigh.{s}"] = (side("hip", s), side("stifle", s), "Hips")
        B[f"Shin.{s}"] = (side("stifle", s), side("hock", s), f"Thigh.{s}")
        B[f"HindFoot.{s}"] = (side("hock", s), side("mtp", s), f"Shin.{s}")
        B[f"HindToe.{s}"] = (side("mtp", s), side("htoe", s), f"HindFoot.{s}")
    return B


SPINE = ["Hips", "Spine1", "Spine2", "Spine3"]
TRUNK = ["Spine1", "Spine2", "Spine3"]
NECK = ["Spine3", "Neck1", "Neck2", "Head"]


# --------------------------------------------------------------------------------------------------------------------
# Body primitives (one watertight surface). Order matters: smooth unions accumulate.
# --------------------------------------------------------------------------------------------------------------------
def leg_prims(s):
    """Primitives of one front and one hind leg incl. paws for side s."""
    P = []
    sx = 1 if s == "L" else -1
    j = lambda n: side(n, s)
    X = lambda x: V(sx * x, 0, 0)

    # ---- front leg
    # scapula + shoulder muscles (deltoid / supraspinatus) lying on the chest wall
    P.append(RoundCone(j("scap") + V(-sx * 0.012, 0.0, -0.01), j("shoulder") + X(-0.008), 0.042, 0.060,
                       k=0.05, bones=f"Scapula.{s}", tag="shoulder"))
    P.append(ellipsoid_seg(j("scap") + X(-0.006) + V(0, 0.01, -0.03), j("shoulder") + V(0, 0.02, 0.03), 0.040, 0.075,
                           up=(sx, 0, 0), k=0.045, bones=f"Scapula.{s}", tag="shoulder"))
    # upper arm: humerus + triceps mass behind it
    P.append(RoundCone(j("shoulder"), j("elbow") + V(0, 0.005, 0.02), 0.064, 0.042,
                       k=0.035, bones=f"UpperArm.{s}", tag="upperarm"))
    P.append(ellipsoid_seg(j("shoulder") + V(0, 0.045, -0.02), j("elbow") + V(0, 0.018, 0.02), 0.050, 0.054,
                           up=(sx, 0, 0), k=0.035, bones=f"UpperArm.{s}", tag="triceps"))
    # elbow point (olecranon)
    P.append(Sphere(j("elbow") + V(0, 0.030, 0.004), 0.029, k=0.02, bones=f"Forearm.{s}", tag="elbow"))
    # forearm: bone + extensor/flexor bellies at the top, lean towards the carpus
    P.append(RoundCone(j("elbow"), j("carpus"), 0.046, 0.035, k=0.02, bones=f"Forearm.{s}", tag="forearm"))
    P.append(ellipsoid_seg(j("elbow") + V(0, -0.008, -0.01), j("elbow") + V(0, -0.010, -0.15), 0.040, 0.042,
                           up=(0, -1, 0), k=0.025, bones=f"Forearm.{s}", tag="forearm"))
    # carpus (wrist) + accessory carpal pad bump at the back
    P.append(Sphere(j("carpus") + V(0, 0.003, 0.0), 0.035, k=0.012, bones=f"FrontFoot.{s}", tag="carpus"))
    P.append(Sphere(j("carpus") + V(0, 0.024, -0.014), 0.013, k=0.01, bones=f"FrontFoot.{s}", tag="carpalpad"))
    # pastern (metacarpus)
    P.append(RoundCone(j("carpus"), j("mcp") + V(0, 0, 0.008), 0.032, 0.033, k=0.012,
                       bones=f"FrontFoot.{s}", tag="pastern"))
    P += paw_prims(j("mcp"), sx, f"FrontFoot.{s}", f"FrontToe.{s}", front=True)

    # ---- hind leg
    # thigh: big biceps femoris / quadriceps mass (Rottweiler: broad, muscular; deep from front to back, the hips no
    # wider than the shoulders)
    P.append(ellipsoid_seg(j("hip") + V(0, 0.05, 0.03), j("stifle") + V(0, 0.035, 0.0), 0.078, 0.072,
                           up=(sx, 0, 0), extra=0.02, k=0.05, bones=f"Thigh.{s}", tag="thigh"))
    P.append(RoundCone(j("hip"), j("stifle"), 0.060, 0.045, k=0.04, bones=f"Thigh.{s}", tag="thigh"))
    # stifle (knee cap) at the front
    P.append(Sphere(j("stifle") + V(0, -0.012, 0.0), 0.030, k=0.03, bones=f"Shin.{s}", tag="stifle"))
    # second thigh (gaskin): tibia + calf muscles behind, tapering to the Achilles tendon
    P.append(RoundCone(j("stifle"), j("hock"), 0.050, 0.031, k=0.03, bones=f"Shin.{s}", tag="gaskin"))
    P.append(ellipsoid_seg(j("stifle") + V(0, 0.030, -0.02), j("hock") + V(0, 0.018, 0.05), 0.050, 0.038,
                           up=(sx, 0, 0), k=0.03, bones=f"Shin.{s}", tag="gaskin"))
    # Achilles tendon to the point of the hock
    P.append(RoundCone(j("hock") + V(0, -0.040, 0.13), j("hock") + V(0, 0.030, 0.012), 0.014, 0.013, k=0.02,
                       bones=f"Shin.{s}", tag="achilles"))
    # point of the hock (calcaneus): the sharp corner at the back of the hock
    P.append(Sphere(j("hock") + V(0, 0.032, 0.004), 0.016, k=0.008, bones=f"HindFoot.{s}", tag="hock"))
    P.append(Sphere(j("hock") + V(0, 0.012, 0.0), 0.029, k=0.012, bones=f"HindFoot.{s}", tag="hock"))
    # rear pastern (metatarsus)
    P.append(RoundCone(j("hock"), j("mtp") + V(0, 0, 0.008), 0.030, 0.031, k=0.012,
                       bones=f"HindFoot.{s}", tag="metatarsus"))
    P += paw_prims(j("mtp"), sx, f"HindFoot.{s}", f"HindToe.{s}", front=False)
    return P


def toe_axis(g, dx, dy, sc):
    """front-low and back-high ends of one arched toe (its knuckle rises back into the paw dome)"""
    return g + V(dx, dy - 0.007, 0.0100) * sc, g + V(dx * 0.85, dy + 0.013, 0.026) * sc


def paw_prims(c, sx, foot_bone, toe_bone, front):
    """A big round 'cat foot': four high-arched toes (digits II-V, creased apart) under a dome that carries the
    pastern down onto them, and the metacarpal/metatarsal pad. Built on the ground point g under the joint c (MCP/MTP),
    so the soles stay on z = 0 whatever the paw scale."""
    P = []
    sc = PAW_SC[0] if front else PAW_SC[1]
    g = V(c[0], c[1], 0.0)
    # dome: the top of the paw, from the pastern forward onto the knuckles
    P.append(Ellipsoid(g + V(0, -0.014, 0.025) * sc, V(0.030, 0.030, 0.021) * sc, k=0.014,
                       bones=[foot_bone, toe_bone], tag="paw"))
    # metacarpal / metatarsal pad under the joint
    P.append(Ellipsoid(g + V(0, 0.005, 0.010) * sc - V(0, 0, 0.0015), V(0.021, 0.017, 0.0115) * sc, k=0.010,
                       bones=foot_bone, tag="pad"))
    # toes: III/IV in front, II/V a bit back and wider; arched, small blend radius so the creases stay
    for dx, dy in TOES:
        a, b = toe_axis(g, dx, dy, sc)
        P.append(ellipsoid_seg(a, b, TOE_R[0] * sc, TOE_R[2] * sc, up=(0, 0, 1), extra=TOE_R[1] * sc, k=0.006,
                               bones=toe_bone, tag="toe"))
    return P


def trunk_prims():
    P = []
    # rib cage: deep, broad, oval (chest depth 0.33 m = 50 % of the withers height)
    P.append(Ellipsoid(V(0, -0.160, 0.488), V(0.140, 0.215, 0.158), k=0.0, bones=TRUNK, tag="ribs"))
    # withers + back muscles: a firm level top line
    P.append(RoundCone(V(0, -0.255, 0.600), V(0, 0.250, 0.585), 0.060, 0.060, k=0.06, bones=SPINE + ["Spine3"],
                       tag="back"))
    P.append(ellipsoid_seg(V(0, -0.300, 0.590), V(0, -0.150, 0.610), 0.055, 0.050, extra=0.02, k=0.05,
                           bones=["Spine3", "Neck1"], tag="withers"))
    # loin / abdomen: a full belly with a gentle tuck-up
    P.append(Ellipsoid(V(0, 0.070, 0.495), V(0.120, 0.175, 0.125), k=0.06, bones=["Spine1", "Hips"], tag="belly"))
    # croup / pelvis: broad, slightly sloping
    P.append(Ellipsoid(V(0, 0.275, 0.530), V(0.118, 0.105, 0.108), k=0.05, bones="Hips", tag="croup"))
    # point of buttock (ischial tuberosities) and the hamstring mass under them
    for sx in (1, -1):
        P.append(Sphere(V(sx * 0.050, 0.350, 0.520), 0.046, k=0.06, bones="Hips", tag="buttock"))
    # forechest / prosternum: broad, well developed
    P.append(Ellipsoid(V(0, -0.330, 0.445), V(0.115, 0.072, 0.100), k=0.05, bones=["Spine3", "Neck1"],
                       tag="forechest"))
    # brisket (sternum) down to the elbows (chest depth ~50 % of the withers height)
    P.append(Ellipsoid(V(0, -0.255, 0.375), V(0.090, 0.115, 0.050), k=0.05, bones="Spine3", tag="brisket"))
    return P


def HE(c, r, **kw):
    """ellipsoid in the head design frame (radii scaled by HEAD_SCALE)"""
    return Ellipsoid(H(c), np.asarray(r) * HEAD_SCALE, RH, **kw)


def HC(a, b, ra, rb, **kw):
    """round cone in the head design frame (radii scaled by HEAD_SCALE)"""
    return RoundCone(H(a), H(b), ra * HEAD_SCALE, rb * HEAD_SCALE, **kw)


def HB(c, h, rad, **kw):
    """rounded box in the head design frame (half sizes and rounding scaled by HEAD_SCALE)"""
    return RoundBox(H(c), np.asarray(h) * HEAD_SCALE, rad * HEAD_SCALE, RH, **kw)


def lip_z(x, y):
    """Height of the lip line (the slit between the upper lip / flews and the lower jaw) in the head design frame.
    Seen from the front it is an inverted V: 0.707 under the nose, 1.8 cm lower at the sides, where the flews hang
    over the lower jaw; seen from the side it rises toward the lip corner (the commissure)."""
    x, y = np.abs(np.asarray(x, dtype=float)), np.asarray(y, dtype=float)
    return 0.707 - 0.42 * np.clip(x - 0.012, 0, 0.042) + 0.25 * np.clip(y + 0.575, 0, None)


class LipCut:
    """The lip slit as a thin sheet following lip_z (smooth subtraction), from the front of the muzzle to the
    commissure at y = -0.51 (design frame)."""
    op = "sub"; bones = None; tag = "lipcut"; pad = 0.0

    def __init__(self, half=0.0027, y0=-0.690, y1=-0.509, xmax=0.078, k=0.001):
        self.half, self.y0, self.y1, self.xmax, self.k = half, y0, y1, xmax, k

    def aabb(self):
        c = [H(V(sx * self.xmax, y, z)) for sx in (-1, 1) for y in (self.y0, self.y1) for z in (0.66, 0.74)]
        return np.min(c, axis=0) - 0.01, np.max(c, axis=0) + 0.01

    def dist(self, P):
        q = H_inv(np.atleast_2d(P))
        d = np.abs(q[:, 2] - lip_z(q[:, 0], q[:, 1])) * 0.9 - self.half      # 0.9: the sheet is tilted <= 23 deg
        d = np.maximum(d, np.maximum(q[:, 1] - self.y1, self.y0 - q[:, 1]))
        return np.maximum(d, np.abs(q[:, 0]) - self.xmax) * HEAD_SCALE


def neck_head_prims():
    P = []
    # neck: strong, muscular, slightly arched, no dewlap (the head end follows the head placement)
    P.append(RoundCone(V(0, -0.300, 0.540), H(V(0, -0.415, 0.755)), 0.135, 0.088, k=0.06,
                       bones=["Spine3", "Neck1", "Neck2"], tag="neck"))
    P.append(RoundCone(V(0, -0.260, 0.625), H(V(0, -0.420, 0.815)), 0.058, 0.052, k=0.05,
                       bones=["Spine3", "Neck1", "Neck2"], tag="crest"))
    # throat under the jaw angle
    P.append(HE(V(0, -0.445, 0.675), V(0.062, 0.055, 0.045), k=0.04, bones=["Neck2", "Head"], tag="throat"))
    # cranium: broad, flat top (a soft plate, no helmet rim); ends at the stop (does not fill the space before the eyes)
    P.append(HE(V(0, -0.458, 0.800), V(0.090, 0.094, 0.074), k=0.04, bones="Head", tag="skull"))
    P.append(HB(V(0, -0.460, 0.832), V(0.030, 0.040, 0.002), 0.050, k=0.03, bones="Head", tag="skulltop"))
    for sx in (1, -1):
        # cheeks (masseter / zygomatic arch): strongly developed, low and wide
        P.append(HE(V(sx * 0.066, -0.500, 0.730), V(0.042, 0.056, 0.052), k=0.03, bones=["Head", "Jaw"],
                    tag="cheek"))
        # brow ridge above the eye (well-defined stop)
        P.append(HE(V(sx * 0.036, -0.548, 0.823), V(0.026, 0.020, 0.016), k=0.02, bones="Head", tag="brow"))
    # muzzle base: broad where it meets the cheeks
    P.append(HE(V(0, -0.555, 0.760), V(0.064, 0.040, 0.048), k=0.03, bones="Head", tag="muzzlebase"))
    # nasal bridge (upper jaw): straight, rounded across; shorter than the skull (3:2)
    P.append(HE(V(0, -0.600, 0.772), V(0.046, 0.060, 0.029), k=0.03, bones=["Head", "Nose"], tag="muzzle"))
    # upper lips / flews: full, broad; the lip line (lip_z) lets them hang over the lower jaw at the sides
    for sx in (1, -1):
        P.append(HE(V(sx * 0.038, -0.590, 0.728), V(0.034, 0.066, 0.044), k=0.025, bones=["Head", "Nose"],
                    tag="flew"))
        # lip corner fold
        P.append(HE(V(sx * 0.056, -0.518, 0.703), V(0.014, 0.018, 0.015), k=0.012, bones=["Head", "Jaw"],
                    tag="flew"))
    # front upper lip under the nose
    P.append(HE(V(0, -0.639, 0.730), V(0.046, 0.026, 0.038), k=0.02, bones=["Head", "Nose"], tag="flew"))
    # nose leather: broad, large, standing proud of the lips (the only primitive tagged 'nose': stage A labels by it)
    P.append(HB(V(0, -0.648, 0.767), V(0.020, 0.008, 0.010), 0.014, k=0.010, bones="Nose", tag="nose"))
    # lower jaw: a little narrower than the flews, the chin set back under the nose
    P.append(HB(V(0, -0.568, 0.686), V(0.020, 0.052, 0.012), 0.012, k=0.02, bones="Jaw", tag="jaw"))
    P.append(HE(V(0, -0.618, 0.687), V(0.029, 0.022, 0.020), k=0.015, bones="Jaw", tag="jaw"))
    for sx in (1, -1):
        P.append(HC(V(sx * 0.048, -0.485, 0.698), V(sx * 0.026, -0.610, 0.684), 0.023, 0.016, k=0.02,
                    bones="Jaw", tag="jaw"))
    return P


def mouth_cut_prims():
    """Subtractions that open the lip line and hollow the mouth (the oral cavity is part of the body surface, so the
    jaw opens without tearing anything; the tongue and teeth are separate parts inside)."""
    # the lip slit: a thin sheet along the curved lip line (lip_z), from the commissure (closed) to the front
    P = [LipCut()]
    # oral cavity behind the lips
    P.append(HE(V(0, -0.570, 0.706), V(0.026, 0.078, 0.011), k=0.004, op="sub", tag="oral"))
    return P


EYE_R = 0.0125 * HEAD_SCALE          # eyeball radius (the visible almond is about 2.2 x 1.35 cm)


_SKIN = None


def skin_prims():
    """The additive primitives of the body (no cuts, nothing that depends on the eye placement)."""
    global _SKIN
    if _SKIN is None:
        P = trunk_prims() + neck_head_prims()
        for s in "LR":
            P += leg_prims(s)
        _SKIN = [p for p in P + tail_prims() if p.op == "add"]
    return _SKIN


def head_field(P):
    """The skin field (all additive body primitives, smooth unions included) at the points P."""
    from sdf import eval_prims
    P = np.atleast_2d(P)
    lo = H(V(0, -0.75, 0.55)) - 0.2; hi = H(V(0, -0.30, 0.95)) + 0.2   # a box around the head (placed)
    lo[0], hi[0] = -0.2, 0.2
    return eval_prims([p for p in skin_prims() if np.all(p.aabb()[1] > lo) and np.all(p.aabb()[0] < hi)], P)


def ray_to_surface(q0, n, offset=0.0, far=0.2):
    """First point along q0 + t n (q0 inside the skin) where the skin field reaches `offset`. Vectorised: q0 (N, 3)
    or (3,), n the same shape or (3,)."""
    q0 = np.atleast_2d(q0).astype(float); n = np.broadcast_to(np.atleast_2d(n), q0.shape)
    lo = np.zeros(len(q0)); hi = np.full(len(q0), far)
    for _ in range(40):
        m = (lo + hi) / 2
        inside = head_field(q0 + n * m[:, None]) < offset
        lo = np.where(inside, m, lo); hi = np.where(inside, hi, m)
    out = q0 + n * lo[:, None]
    return out[0] if len(out) == 1 else out


_EYES = {}


def eye_frame(s):
    """(center, look direction, rotation) of the eyeball on side s, placed on the head surface: the cornea stands
    1.5 mm (x HEAD_SCALE) proud of the skin surface of the head primitives. The frame's local z is the head's up,
    rolled 12 deg about the look direction so the almond is slightly oblique (outer corner higher)."""
    if s not in _EYES:
        sx = 1 if s == "L" else -1
        n = Hd(V(sx * 0.42, -0.88, 0.16)); n /= np.linalg.norm(n)   # forward and slightly out/up
        q0 = H(V(sx * 0.018, -0.515, 0.793))
        surf = ray_to_surface(q0, n)
        c = surf - n * (EYE_R - 0.0015 * HEAD_SCALE)
        R = frame_from(n, Hd(V(0, 0, 1)))
        # oblique tilt: roll the frame about n; the inner (front) corner goes down, the outer (rear) one up
        th = np.radians(12); x_, z_ = R[:, 0].copy(), R[:, 2].copy()
        sg = 1 if (H_inv(c + x_) - H_inv(c))[1] < 0 else -1        # +local x toward the front (the inner corner)
        R[:, 0] = np.cos(th) * x_ - sg * np.sin(th) * z_; R[:, 2] = np.cos(th) * z_ + sg * np.sin(th) * x_
        _EYES[s] = (c, n, R)
    return _EYES[s]


def eye_socket_prims():
    P = []
    for s in "LR":
        c, n, R = eye_frame(s)
        # almond opening: wider than tall; local x = across the eye, y = along the look direction, z = up
        P.append(Ellipsoid(c + n * 0.0015 * HEAD_SCALE, V(0.0181, 0.0135, 0.0112) * HEAD_SCALE, R, k=0.002, op="sub",
                           tag="socket"))
    return P


def eye_lid_prims():
    """Lid rims around the socket (the second socket cut hollows them into rings); slim, the upper lid a bit heavier."""
    P = []
    for s in "LR":
        c, n, R = eye_frame(s)
        P.append(Ellipsoid(c + n * 0.0095 * HEAD_SCALE + R[:, 2] * 0.0010 * HEAD_SCALE,
                           V(0.0200, 0.0030, 0.0135) * HEAD_SCALE, R, k=0.004, bones="Head", tag="lid"))
    return P


def eye_mesh(s, seg=24, rings=16):
    """UV sphere eyeball (its own material M_Dog_Eye). Returns verts, faces (quads), uv (planar front
    projection: the iris texture is centred at uv 0.5)."""
    c, n, R = eye_frame(s)
    verts, uvs = [], []
    for i in range(rings + 1):
        th = np.pi * i / rings                     # 0 = front pole (cornea)
        for j in range(seg):
            ph = 2 * np.pi * j / seg
            loc = V(np.sin(th) * np.cos(ph), np.cos(th), np.sin(th) * np.sin(ph))
            verts.append(c + R @ (loc * EYE_R))
            # front hemisphere projected onto the texture disc; back hemisphere to the rim (sclera)
            rr = min(th / np.pi * 1.0, 1.0) * 0.5
            uvs.append((0.5 + rr * np.cos(ph), 0.5 + rr * np.sin(ph)))
    faces = []
    for i in range(rings):
        for j in range(seg):
            a = i * seg + j; b = i * seg + (j + 1) % seg
            faces.append((a, b, b + seg, a + seg))
    return np.array(verts), faces, np.array(uvs)


# Folded, high-set pendant ear. Outline and attachment in the head design frame (y, z); the fold radii, thicknesses,
# stand-offs and the base embedding are world meters at HEAD_SCALE 1 (ear_mesh multiplies them by HEAD_SCALE).
EAR = dict(
    base_f=V(-0.517, 0.866), base_b=V(-0.426, 0.848),    # attachment (y, z); z is replaced by the skull surface
    base_x=(0.052, 0.060),                               # attachment x (front, back): the top corners of the skull
    base_embed=0.0045,                                   # the base sits this far inside the skin (crest ~ skull top)
    front_ctl=V(-0.531, 0.818), front_end=V(-0.536, 0.779),   # front edge: hangs straight, slightly forward
    back_ctl=V(-0.430, 0.796), back_end=V(-0.496, 0.772),     # back edge: convex, sweeps forward to the bottom
    bottom_bulge=0.011,                                  # the bottom edge is a round U between front_end and back_end
    fold_r=(0.009, 0.014, 0.007),                        # fold radius at the front end / the peak (u 0.3) / the back end
    flare_f=0.003, flare_b=0.020, cup=0.004,             # extra stand-off at the bottom of the front / back edge
    gap_min=0.006,                                       # least clearance of the flap from the head
    thick_fold=0.0090, thick_flap=0.0040,                # shell thickness (the rims taper to 40 %)
)


def _bez(p0, p1, p2, t):
    t = np.asarray(t)[..., None]
    return (1 - t) ** 2 * p0 + 2 * (1 - t) * t * p1 + t ** 2 * p2


def _signed_volume(v, faces):
    f = np.asarray(faces); tri = np.concatenate([f[:, [0, 1, 2]], f[:, [0, 2, 3]]])
    return np.einsum("ij,ij->i", v[tri[:, 0]], np.cross(v[tri[:, 1]], v[tri[:, 2]])).sum() / 6


def ear_mesh(s, ns=12, nt=18, nfold=6, P=EAR):
    """Folded pendant ear: set high on the top corners of the skull, it rolls up and out over an arched fold crest
    and hangs as a broad triangular flap beside the cheek (straight front edge, convex back edge, round U bottom); the
    flap stands off the head field by at least gap_min, more at the bottom of the back edge. An explicit closed shell
    (outer and inner sheet joined by rims), outward winding. Returns verts, quad faces, per-vertex (Ear1, Ear2)
    weights, uv on its own (u across, t down) square and an inner-sheet flag."""
    sx = 1 if s == "L" else -1
    sc = HEAD_SCALE
    bf, bb = P["base_f"], P["base_b"]
    lat = Hd(V(sx, 0, 0)); up = Hd(V(0, 0, 1))
    us = np.linspace(0, 1, ns + 1)
    rf, rp, rb = (r * sc for r in P["fold_r"])          # fold radius: front end, peak (at u = 0.3), back end
    r = np.where(us < 0.3, rf + (rp - rf) * np.sin(np.pi / 2 * us / 0.3),
                 rb + (rp - rb) * np.cos(np.pi / 2 * (us - 0.3) / 0.7))
    base_yz = bf[None] * (1 - us[:, None]) + bb[None] * us[:, None]
    bx = P["base_x"][0] * (1 - us) + P["base_x"][1] * us
    q0 = np.array([H(V(sx * x, y, 0.80)) for x, (y, z) in zip(bx, base_yz)])
    B = ray_to_surface(q0, up, offset=-P["base_embed"] * sc)            # on the skull's top corners, embedded
    zb = H_inv(B)[:, 2]
    bf = V(bf[0], zb[0]); bb = V(bb[0], zb[-1])
    rows, T = [], []
    for k in range(nfold + 1):                              # fold: base (going up) -> crest -> flap top (going down)
        ph = np.pi * (1 - k / nfold)
        rows.append(B + lat[None] * (r + r * np.cos(ph))[:, None] + up[None] * (r * np.sin(ph))[:, None])
        T.append(0.22 * k / nfold)
    top = B + lat[None] * (2 * r)[:, None]
    top_lat = top @ lat
    flare_f, flare_b, cup, gap_min = P["flare_f"] * sc, P["flare_b"] * sc, P["cup"] * sc, P["gap_min"] * sc
    for k in range(1, nt + 1):
        t = k / nt
        tt = 1 - (1 - t) ** 1.1
        fe = _bez(bf, P["front_ctl"], P["front_end"], tt); be = _bez(bb, P["back_ctl"], P["back_end"], tt)
        yz = fe[None] * (1 - us[:, None]) + be[None] * us[:, None]
        k2 = np.clip((tt - 0.55) / 0.45, 0, 1) ** 2                      # round U bottom
        yz = yz + np.stack([np.zeros_like(us), -np.sqrt(np.sin(np.pi * us)) * P["bottom_bulge"] * k2], 1)
        pts = np.array([H(V(0.0, y, z)) for y, z in yz])
        head = ray_to_surface(pts, lat, offset=0.0)
        hx = (head - pts) @ lat
        flare = (flare_f * (1 - us) + flare_b * us) * tt ** 0.8 + cup * np.sin(np.pi * us) * np.sin(np.pi * min(tt, 1))
        want = np.maximum(top_lat - pts @ lat + flare, hx + gap_min + 0.5 * flare)
        rows.append(pts + lat[None] * want[:, None]); T.append(0.22 + 0.78 * t)
    nu = ns + 1; nr = len(rows)
    G = np.array(rows)
    du = np.gradient(G, axis=1); dt = np.gradient(G, axis=0)
    Nn = np.cross(dt, du)
    Nn /= np.linalg.norm(Nn, axis=2, keepdims=True) + 1e-12
    if (Nn[-3, nu // 2] @ lat) < 0:
        Nn = -Nn
    tpar = np.array(T)[:, None] * np.ones((1, nu))
    tf, tl = P["thick_fold"] * sc, P["thick_flap"] * sc
    th = np.where(tpar < 0.22, tf, tf + (tl - tf) * np.clip((tpar - 0.22) / 0.25, 0, 1))
    edge = np.minimum(np.minimum(us, 1 - us)[None, :] * 3, 1) * np.ones((nr, 1))
    edge = np.minimum(edge, np.clip((1 - tpar) * 8, 0, 1))
    th = th * (0.40 + 0.60 * np.sqrt(np.clip(edge, 0, 1)))              # the rims taper to 40 %
    out = (G + Nn * th[..., None] / 2).reshape(-1, 3)
    inn = (G - Nn * th[..., None] / 2).reshape(-1, 3)
    verts = np.concatenate([out, inn]); off = len(out)
    faces = []
    for it in range(nr - 1):
        for iu in range(ns):
            a = it * nu + iu
            q = (a, a + 1, a + 1 + nu, a + nu)
            faces.append(q if s == "L" else q[::-1])
            qi = tuple(off + x for x in q)
            faces.append(qi[::-1] if s == "L" else qi)
    def rim(a, b):
        q = (a, b, off + b, off + a)
        faces.append(q[::-1] if s == "L" else q)
    for it in range(nr - 1):
        rim(it * nu + ns, (it + 1) * nu + ns)
        rim((it + 1) * nu, it * nu)
    for iu in range(ns):
        rim((nr - 1) * nu + iu + 1, (nr - 1) * nu + iu)
        rim(iu, iu + 1)
    faces = [tuple(q[::-1]) for q in faces]           # outward winding (the loops above build the shell inside-out)
    vol = _signed_volume(verts, faces)
    assert vol > 0, f"ear {s}: the shell is inside-out (signed volume {vol * 1e6:.1f} cm3)"
    Tm = np.repeat(np.array(T), nu)
    t_all = np.concatenate([Tm, Tm])
    w2 = np.clip((t_all - 0.20) / 0.45, 0, 1)
    wts = np.stack([1 - w2, w2], axis=1)
    uv = np.stack([np.tile(us, nr * 2), 1 - t_all], axis=1)
    inner = np.array([False] * off + [True] * off)
    return verts, faces, wts, uv, inner


def tail_prims():
    P = []
    names = ["tail0", "tail1", "tail2", "tail3", "tail4", "tail5", "tail6"]
    for i in range(6):
        P.append(RoundCone(J[names[i]], J[names[i + 1]], TAIL_R[i], TAIL_R[i + 1],
                           k=0.03 if i == 0 else 0.006, bones=f"Tail{i + 1}", tag="tail"))
    return P


def body_prims():
    P = trunk_prims()
    P += neck_head_prims()
    for s in "LR":
        P += leg_prims(s)
    P += tail_prims()
    # re-carve after everything is unioned (a later smooth union must not refill the cuts)
    P += mouth_cut_prims()
    P += eye_socket_prims()
    P += eye_lid_prims()
    P += eye_socket_prims()      # the lid rims must not cover the eyeball
    return P


# --------------------------------------------------------------------------------------------------------------------
# Separate parts (own fine grids, own shells): ears, claws, teeth, tongue. Eyes are analytic spheres (dog_mesh.py).
# --------------------------------------------------------------------------------------------------------------------
def claw_prims():
    """One claw per toe (4 per paw) + the front dewclaws: short, thick, dark hooks that leave the lower front of each
    toe and curve down to the ground (two round cones)."""
    P = []
    for s in "LR":
        sx = 1 if s == "L" else -1
        for joint, bone, sc in (("mcp", f"FrontToe.{s}", PAW_SC[0]), ("mtp", f"HindToe.{s}", PAW_SC[1])):
            c = side(joint, s)
            g = V(c[0], c[1], 0.0)
            for dx, dy in TOES:
                ta, tb = toe_axis(g, dx, dy, sc)
                a = ta + V(0, -0.002, 0.003) * sc                  # root inside the toe
                m = ta + V(0, CLAW_M[0], CLAW_M[1]) * sc            # the bend, just out of the fur
                b = V(m[0], m[1] + CLAW_TIP[0], CLAW_TIP[1])        # tip just above the ground
                P.append(RoundCone(a, m, CLAW_R[0], CLAW_R[1], k=0.0, bones=bone, tag="claw"))
                P.append(RoundCone(m, b, CLAW_R[1], CLAW_R[2], k=0.0, bones=bone, tag="claw"))
        # dewclaw on the inside of the front pastern (clear of the thicker pastern)
        c = side("carpus", s) + V(-sx * 0.033, -0.006, -0.032)
        P.append(RoundCone(c, c + V(-sx * 0.004, -0.010, -0.010), 0.0042, 0.0012, k=0.0, bones=f"FrontFoot.{s}",
                           tag="claw"))
        P.append(Sphere(c + V(sx * 0.004, 0.004, 0.004), 0.0075, k=0.0, bones=f"FrontFoot.{s}", tag="dewclaw"))
    return P


def teeth_prims():
    """Canines and incisors (upper on Head, lower on Jaw). Simple cones; they show when the mouth opens."""
    P = []
    zu, zl = 0.716, 0.697          # upper / lower gum line (the lip slit is at 0.707; tips stay inside the lips)
    for sx in (1, -1):
        # upper canine hangs down in front of the lower canine
        P.append(HC(V(sx * 0.024, -0.626, zu + 0.004), V(sx * 0.023, -0.628, zu - 0.011), 0.0045, 0.0012,
                           k=0.0, bones="Head", tag="tooth"))
        P.append(HC(V(sx * 0.020, -0.614, zl - 0.004), V(sx * 0.022, -0.616, zl + 0.010), 0.0042, 0.0011,
                           k=0.0, bones="Jaw", tag="tooth"))
        for i, dx in enumerate((0.004, 0.010, 0.016)):
            y = -0.636 + 0.003 * i
            P.append(HC(V(sx * dx, y, zu + 0.002), V(sx * dx, y - 0.001, zu - 0.004), 0.0024, 0.0016,
                               k=0.0, bones="Head", tag="tooth"))
            y = -0.628 + 0.003 * i
            P.append(HC(V(sx * dx * 0.9, y, zl - 0.002), V(sx * dx * 0.9, y - 0.001, zl + 0.004), 0.0022,
                               0.0015, k=0.0, bones="Jaw", tag="tooth"))
        # carnassials / premolars (a low ridge)
        P.append(HC(V(sx * 0.027, -0.600, zu), V(sx * 0.031, -0.540, zu - 0.002), 0.0035, 0.0035,
                           k=0.0, bones="Head", tag="tooth"))
        P.append(HC(V(sx * 0.024, -0.600, zl), V(sx * 0.028, -0.540, zl + 0.002), 0.0032, 0.0032,
                           k=0.0, bones="Jaw", tag="tooth"))
    return P


def tongue_prims():
    """Long flat tongue lying on the floor of the mouth (tip just behind the lower incisors)."""
    P = []
    pts = [J["tongue0"], J["tongue1"], J["tongue2"], J["tongue3"]]
    bones = ["Tongue1", "Tongue2", "Tongue3"]
    widths = [w * HEAD_SCALE for w in (0.019, 0.020, 0.019, 0.015)]
    down = Hd(V(0, 0, -0.003)) * HEAD_SCALE
    for i in range(3):
        a, b = pts[i] + down, pts[i + 1] + down
        R = frame_from(b - a, Hd(V(0, 0, 1)))
        P.append(Ellipsoid((a + b) / 2, V(widths[i], np.linalg.norm(b - a) / 2 + 0.012 * HEAD_SCALE,
                                          0.0055 * HEAD_SCALE), R,
                           k=0.012, bones=bones[i], tag="tongue"))
    return P
