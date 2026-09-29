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
    "neck2":     V(0, -0.385, 0.690),
    "atlas":     V(0, -0.425, 0.775),   # head joint
    "snout":     V(0, -0.662, 0.752),   # nose tip
    "tmj":       V(0, -0.470, 0.718),   # jaw hinge (midline stand-in for both TMJs)
    "chin":      V(0, -0.640, 0.686),
    "tongue0":   V(0, -0.495, 0.703),
    "tongue1":   V(0, -0.555, 0.703),
    "tongue2":   V(0, -0.610, 0.703),
    "tongue3":   V(0, -0.645, 0.703),
    # ear (left)
    "ear0":      V(0.062, -0.452, 0.858),
    "ear1":      V(0.090, -0.468, 0.848),
    "ear2":      V(0.103, -0.518, 0.745),
    # front leg (left)
    "scap":      V(0.062, -0.215, 0.615),
    "shoulder":  V(0.098, -0.340, 0.450),
    "elbow":     V(0.098, -0.245, 0.302),
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
    "tail4":     V(0, 0.487, 0.378),
    "tail5":     V(0, 0.488, 0.312),
    "tail6":     V(0, 0.483, 0.250),
}

TOES = ((0.0118, -0.045), (-0.0118, -0.045), (0.0280, -0.032), (-0.0280, -0.032))   # digits III/IV, II/V
TAIL_R = [0.030, 0.026, 0.022, 0.019, 0.016, 0.013, 0.010]


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
    B["Head"] = (J["atlas"], V(0, -0.560, 0.790), "Neck2")
    B["Nose"] = (V(0, -0.560, 0.790), J["snout"], "Head")        # muzzle (sniff wrinkle / nose twitch)
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
    P.append(RoundCone(j("shoulder"), j("elbow") + V(0, 0.005, 0.01), 0.064, 0.046,
                       k=0.035, bones=f"UpperArm.{s}", tag="upperarm"))
    P.append(ellipsoid_seg(j("shoulder") + V(0, 0.045, -0.02), j("elbow") + V(0, 0.018, 0.02), 0.050, 0.054,
                           up=(sx, 0, 0), k=0.035, bones=f"UpperArm.{s}", tag="triceps"))
    # elbow point (olecranon)
    P.append(Sphere(j("elbow") + V(0, 0.030, 0.004), 0.029, k=0.02, bones=f"Forearm.{s}", tag="elbow"))
    # forearm: bone + extensor/flexor bellies at the top, lean towards the carpus
    P.append(RoundCone(j("elbow"), j("carpus"), 0.042, 0.029, k=0.02, bones=f"Forearm.{s}", tag="forearm"))
    P.append(ellipsoid_seg(j("elbow") + V(0, -0.008, -0.01), j("elbow") + V(0, -0.012, -0.12), 0.035, 0.037,
                           up=(0, -1, 0), k=0.025, bones=f"Forearm.{s}", tag="forearm"))
    # carpus (wrist) + accessory carpal pad bump at the back
    P.append(Sphere(j("carpus") + V(0, 0.003, 0.0), 0.030, k=0.012, bones=f"FrontFoot.{s}", tag="carpus"))
    P.append(Sphere(j("carpus") + V(0, 0.020, -0.012), 0.012, k=0.01, bones=f"FrontFoot.{s}", tag="carpalpad"))
    # pastern (metacarpus)
    P.append(RoundCone(j("carpus"), j("mcp") + V(0, 0, 0.008), 0.027, 0.028, k=0.012,
                       bones=f"FrontFoot.{s}", tag="pastern"))
    P += paw_prims(j("mcp"), sx, f"FrontFoot.{s}", f"FrontToe.{s}", front=True)

    # ---- hind leg
    # thigh: big biceps femoris / quadriceps mass (Rottweiler: broad, muscular)
    P.append(ellipsoid_seg(j("hip") + V(0, 0.05, 0.03), j("stifle") + V(0, 0.035, 0.0), 0.068, 0.102,
                           up=(sx, 0, 0), extra=0.02, k=0.05, bones=f"Thigh.{s}", tag="thigh"))
    P.append(RoundCone(j("hip"), j("stifle"), 0.060, 0.045, k=0.04, bones=f"Thigh.{s}", tag="thigh"))
    # stifle (knee cap) at the front
    P.append(Sphere(j("stifle") + V(0, -0.012, 0.0), 0.034, k=0.025, bones=f"Shin.{s}", tag="stifle"))
    # second thigh (gaskin): tibia + calf muscles behind, tapering to the Achilles tendon
    P.append(RoundCone(j("stifle"), j("hock"), 0.047, 0.026, k=0.03, bones=f"Shin.{s}", tag="gaskin"))
    P.append(ellipsoid_seg(j("stifle") + V(0, 0.030, -0.02), j("hock") + V(0, 0.012, 0.07), 0.038, 0.046,
                           up=(sx, 0, 0), k=0.03, bones=f"Shin.{s}", tag="gaskin"))
    # Achilles tendon to the point of the hock
    P.append(RoundCone(j("hock") + V(0, 0.020, 0.07), j("hock") + V(0, 0.020, 0.004), 0.013, 0.015, k=0.015,
                       bones=f"Shin.{s}", tag="achilles"))
    P.append(Sphere(j("hock") + V(0, 0.012, 0.0), 0.025, k=0.012, bones=f"HindFoot.{s}", tag="hock"))
    # rear pastern (metatarsus)
    P.append(RoundCone(j("hock"), j("mtp") + V(0, 0, 0.008), 0.025, 0.026, k=0.012,
                       bones=f"HindFoot.{s}", tag="metatarsus"))
    P += paw_prims(j("mtp"), sx, f"HindFoot.{s}", f"HindToe.{s}", front=False)
    return P


def paw_prims(c, sx, foot_bone, toe_bone, front):
    """A compact 'cat foot': paw body, metacarpal/metatarsal pad and four arched toes (digits II-V).
    c = the MCP/MTP joint (paw centre, above the pad)."""
    P = []
    sc = 1.12 if front else 1.05
    # paw body (webbing between the toes) sits forward of the joint
    P.append(Ellipsoid(c + V(0, -0.010 * sc, -0.008), V(0.027, 0.028, 0.020) * sc, k=0.012,
                       bones=[foot_bone, toe_bone], tag="paw"))
    # metacarpal / metatarsal pad under the joint
    P.append(Ellipsoid(c + V(0, 0.004, -0.024), V(0.022, 0.018, 0.013) * sc, k=0.010, bones=foot_bone, tag="pad"))
    # toes: III/IV in front (x +-0.011), II/V a bit back and wider (x +-0.027); each an arched knuckle
    for dx, dy in TOES:
        base = c + V(dx * sc, dy * sc, -0.021)
        P.append(Ellipsoid(base, V(0.0122, 0.0170, 0.0118) * sc, k=0.007, bones=toe_bone, tag="toe"))
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
    # loin / abdomen: moderate tuck-up
    P.append(Ellipsoid(V(0, 0.090, 0.520), V(0.118, 0.160, 0.105), k=0.06, bones=["Spine1", "Hips"], tag="belly"))
    # croup / pelvis: broad, slightly sloping
    P.append(Ellipsoid(V(0, 0.275, 0.530), V(0.118, 0.105, 0.108), k=0.05, bones="Hips", tag="croup"))
    # point of buttock (ischial tuberosities) and the hamstring mass under them
    for sx in (1, -1):
        P.append(Sphere(V(sx * 0.050, 0.350, 0.520), 0.046, k=0.06, bones="Hips", tag="buttock"))
    # forechest / prosternum: broad, well developed
    P.append(Ellipsoid(V(0, -0.330, 0.445), V(0.115, 0.072, 0.100), k=0.05, bones=["Spine3", "Neck1"],
                       tag="forechest"))
    # brisket (sternum) down to the elbows
    P.append(Ellipsoid(V(0, -0.255, 0.360), V(0.090, 0.115, 0.050), k=0.05, bones="Spine3", tag="brisket"))
    return P


def neck_head_prims():
    P = []
    # neck: strong, muscular, slightly arched, no dewlap
    P.append(RoundCone(V(0, -0.300, 0.540), V(0, -0.420, 0.760), 0.135, 0.095, k=0.06,
                       bones=["Spine3", "Neck1", "Neck2"], tag="neck"))
    P.append(RoundCone(V(0, -0.260, 0.625), V(0, -0.420, 0.820), 0.058, 0.055, k=0.05,
                       bones=["Spine3", "Neck1", "Neck2"], tag="crest"))
    # throat under the jaw angle
    P.append(Ellipsoid(V(0, -0.450, 0.680), V(0.070, 0.060, 0.050), k=0.04, bones=["Neck2", "Head"], tag="throat"))
    # skull: broad between the ears, flat forehead
    P.append(Ellipsoid(V(0, -0.475, 0.800), V(0.082, 0.098, 0.074), k=0.04, bones="Head", tag="skull"))
    P.append(Ellipsoid(V(0, -0.460, 0.828), V(0.078, 0.072, 0.047), k=0.03, bones="Head", tag="skulltop"))
    # cheeks (masseter / zygomatic arch): strongly developed
    for sx in (1, -1):
        P.append(Ellipsoid(V(sx * 0.060, -0.498, 0.752), V(0.040, 0.058, 0.048), k=0.03, bones=["Head", "Jaw"],
                           tag="cheek"))
        # brow ridge above the eye (well-defined stop)
        P.append(Ellipsoid(V(sx * 0.034, -0.540, 0.818), V(0.026, 0.024, 0.017), k=0.02, bones="Head", tag="brow"))
    # muzzle base: broad where it meets the cheeks
    P.append(Ellipsoid(V(0, -0.560, 0.752), V(0.060, 0.040, 0.045), k=0.03, bones="Head", tag="muzzlebase"))
    # muzzle (upper jaw): deep, broad, straight nose bridge; shorter than the skull (3:2)
    P.append(RoundBox(V(0, -0.598, 0.748), V(0.022, 0.040, 0.016), 0.028, k=0.035, bones=["Head", "Nose"],
                      tag="muzzle"))
    # upper lips (flews): full, black, hanging slightly over the lower jaw at the sides
    for sx in (1, -1):
        P.append(Ellipsoid(V(sx * 0.036, -0.600, 0.722), V(0.022, 0.058, 0.026), k=0.02, bones=["Head", "Nose"],
                           tag="flew"))
    # nose leather: broad, black
    P.append(Ellipsoid(V(0, -0.650, 0.768), V(0.033, 0.020, 0.024), k=0.012, bones="Nose", tag="nose"))
    # lower jaw (mandible + lower lip + chin)
    P.append(RoundBox(V(0, -0.575, 0.690), V(0.026, 0.058, 0.009), 0.012, k=0.02, bones="Jaw", tag="jaw"))
    for sx in (1, -1):
        P.append(RoundCone(V(sx * 0.050, -0.485, 0.705), V(sx * 0.022, -0.620, 0.690), 0.020, 0.013, k=0.02,
                           bones="Jaw", tag="jaw"))
    return P


def mouth_cut_prims():
    """Subtractions that open the lip line and hollow the mouth (the oral cavity is part of the body surface, so the
    jaw opens without tearing anything; the tongue and teeth are separate parts inside)."""
    P = []
    # the lip slit: a thin wedge from the commissure (closed) to the front
    P.append(RoundBox(V(0, -0.595, 0.707), V(0.075, 0.085, 0.0012), 0.0015, k=0.001, op="sub", tag="lipcut"))
    # oral cavity behind the lips
    P.append(Ellipsoid(V(0, -0.570, 0.706), V(0.026, 0.078, 0.011), k=0.004, op="sub", tag="oral"))
    return P


EYE_R = 0.0110          # eyeball radius (a dog's eyeball is ~2.2 cm across)


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
    lo = np.array([-0.2, -0.75, 0.55]); hi = np.array([0.2, -0.30, 0.95])
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
    1.5 mm proud of the skin surface of the head primitives."""
    if s not in _EYES:
        sx = 1 if s == "L" else -1
        n = V(sx * 0.42, -0.88, 0.16); n /= np.linalg.norm(n)       # forward and slightly out/up
        q0 = V(sx * 0.018, -0.515, 0.793)
        surf = ray_to_surface(q0, n)
        c = surf - n * (EYE_R - 0.0015)
        _EYES[s] = (c, n, frame_from(n, (0, 0, 1)))
    return _EYES[s]


def eye_socket_prims():
    P = []
    for s in "LR":
        c, n, R = eye_frame(s)
        # almond opening: wider than tall; local x = across the eye, y = along the look direction, z = up
        P.append(Ellipsoid(c + n * 0.0015, V(0.0138, 0.0125, 0.0094), R, k=0.002, op="sub", tag="socket"))
    return P


def eye_lid_prims():
    """Lid rims around the socket (the second socket cut hollows them into rings)."""
    P = []
    for s in "LR":
        c, n, R = eye_frame(s)
        P.append(Ellipsoid(c + n * 0.0085, V(0.0160, 0.0032, 0.0116), R, k=0.004, bones="Head", tag="lid"))
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


def ear_mesh(s, ns=11, nt=15, thick=0.0034):
    """Pendant triangular ear draped over the side of the head: an explicit two-sided surface with a rim.
    The outer sheet sits `gap` off the head field (4 mm at the base, 9 mm at the tip) so it never cuts the cheek.
    Returns verts, quad faces, per-vertex (Ear1, Ear2) weights, uv on its own (s, t) square and a side flag."""
    sx = 1 if s == "L" else -1
    # outline in the head's side plane (y, z): base from front to back at the top of the skull, rounded tip
    base_f, base_b, tip = V(-0.493, 0.852), V(-0.420, 0.852), V(-0.530, 0.742)
    def yz(u, t):
        # u in [0, 1] across the ear, t in [0, 1] from the base to the tip; the width narrows to a rounded tip
        w = (1 - t) ** 0.85 * 0.5 + 0.03 * np.sin(np.pi * t)
        mid = base_f * 0.5 + base_b * 0.5
        axis_b = (base_b - base_f)
        centre = mid * (1 - t) + tip * t
        # the front edge stays straighter (it lies along the cheek); the back edge bows out
        bow = 0.012 * np.sin(np.pi * t) * (u - 0.2)
        return centre + axis_b * (u - 0.5) * 2 * w + V(bow * 0.3, -bow * 0.1)
    Q, T = [], []
    for it in range(nt + 1):
        t2 = 1 - (1 - it / nt) ** 1.2          # denser near the base fold
        for iu in range(ns + 1):
            y, z = yz(iu / ns, t2)
            Q.append(V(sx * 0.02, y, z)); T.append(t2)
    Q, T = np.array(Q), np.array(T)
    gap = 0.004 + 0.006 * T ** 1.5
    # vectorised bisection with per-point offsets
    lo = np.zeros(len(Q)); hi = np.full(len(Q), 0.2)
    for _ in range(40):
        m = (lo + hi) / 2
        inside = head_field(Q + V(sx, 0, 0) * m[:, None]) < gap
        lo = np.where(inside, m, lo); hi = np.where(inside, hi, m)
    P = Q + V(sx, 0, 0) * lo[:, None]
    P = P + np.stack([sx * 0.004 * T ** 2, -0.004 * T ** 2, 0 * T], axis=1)      # the tip hangs free a little
    rows_out = P + V(sx * thick / 2, 0, 0)
    rows_in = P - V(sx * thick / 2, 0, 0)
    W = T
    nu = ns + 1
    verts = np.concatenate([rows_out, rows_in])
    off = len(rows_out)
    faces = []
    for it in range(nt):
        for iu in range(ns):
            a = it * nu + iu
            q = (a, a + 1, a + 1 + nu, a + nu)
            faces.append(q if s == "L" else q[::-1])                         # outer sheet faces out
            qi = tuple(off + x for x in q)
            faces.append(qi[::-1] if s == "L" else qi)                       # inner sheet faces the head
    # rim: front edge (iu = 0), back edge (iu = ns), tip row (it = nt); the base row is closed too (hidden fold)
    def rim(a, b):
        q = (a, b, off + b, off + a)
        faces.append(q[::-1] if s == "L" else q)
    for it in range(nt):
        rim(it * nu + ns, (it + 1) * nu + ns)
        rim((it + 1) * nu, it * nu)
    for iu in range(ns):
        rim(nt * nu + iu + 1, nt * nu + iu)
        rim(iu, iu + 1)
    t_all = np.concatenate([W, W])
    w2 = np.clip((t_all - 0.15) / 0.5, 0, 1)
    wts = np.stack([1 - w2, w2], axis=1)
    u_all = np.array([(i % nu) / ns for i in range(nu * (nt + 1))] * 2)
    uv = np.stack([u_all, 1 - t_all], axis=1)
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
    """One claw per toe (4 per paw) + the front dewclaws: dark, curved cones."""
    P = []
    for s in "LR":
        sx = 1 if s == "L" else -1
        for joint, bone, sc in (("mcp", f"FrontToe.{s}", 1.12), ("mtp", f"HindToe.{s}", 1.05)):
            c = side(joint, s)
            for dx, dy in TOES:
                a = c + V(dx * sc, dy * sc, -0.021) + V(0, -0.0120 * sc, 0.0035)     # inside the toe tip
                b = a + V(0, -0.0125, -0.0165)
                P.append(RoundCone(a, b, 0.0046, 0.0017, k=0.0, bones=bone, tag="claw"))
        # dewclaw on the inside of the front pastern
        c = side("carpus", s) + V(-sx * 0.021, -0.006, -0.030)
        P.append(RoundCone(c, c + V(-sx * 0.004, -0.012, -0.010), 0.004, 0.0012, k=0.0, bones=f"FrontFoot.{s}",
                           tag="claw"))
        P.append(Sphere(c + V(sx * 0.004, 0.004, 0.004), 0.0075, k=0.0, bones=f"FrontFoot.{s}", tag="dewclaw"))
    return P


def teeth_prims():
    """Canines and incisors (upper on Head, lower on Jaw). Simple cones; they show when the mouth opens."""
    P = []
    zu, zl = 0.716, 0.697          # upper / lower gum line (the lip slit is at 0.707; tips stay inside the lips)
    for sx in (1, -1):
        # upper canine hangs down in front of the lower canine
        P.append(RoundCone(V(sx * 0.024, -0.626, zu + 0.004), V(sx * 0.023, -0.628, zu - 0.011), 0.0045, 0.0012,
                           k=0.0, bones="Head", tag="tooth"))
        P.append(RoundCone(V(sx * 0.020, -0.614, zl - 0.004), V(sx * 0.022, -0.616, zl + 0.010), 0.0042, 0.0011,
                           k=0.0, bones="Jaw", tag="tooth"))
        for i, dx in enumerate((0.004, 0.010, 0.016)):
            y = -0.636 + 0.003 * i
            P.append(RoundCone(V(sx * dx, y, zu + 0.002), V(sx * dx, y - 0.001, zu - 0.004), 0.0024, 0.0016,
                               k=0.0, bones="Head", tag="tooth"))
            y = -0.628 + 0.003 * i
            P.append(RoundCone(V(sx * dx * 0.9, y, zl - 0.002), V(sx * dx * 0.9, y - 0.001, zl + 0.004), 0.0022,
                               0.0015, k=0.0, bones="Jaw", tag="tooth"))
        # carnassials / premolars (a low ridge)
        P.append(RoundCone(V(sx * 0.027, -0.600, zu), V(sx * 0.031, -0.540, zu - 0.002), 0.0035, 0.0035,
                           k=0.0, bones="Head", tag="tooth"))
        P.append(RoundCone(V(sx * 0.024, -0.600, zl), V(sx * 0.028, -0.540, zl + 0.002), 0.0032, 0.0032,
                           k=0.0, bones="Jaw", tag="tooth"))
    return P


def tongue_prims():
    """Long flat tongue lying on the floor of the mouth (tip just behind the lower incisors)."""
    P = []
    pts = [J["tongue0"], J["tongue1"], J["tongue2"], J["tongue3"]]
    bones = ["Tongue1", "Tongue2", "Tongue3"]
    widths = [0.019, 0.020, 0.019, 0.015]
    for i in range(3):
        a, b = pts[i] + V(0, 0, -0.003), pts[i + 1] + V(0, 0, -0.003)
        R = frame_from(b - a)
        P.append(Ellipsoid((a + b) / 2, V(widths[i], np.linalg.norm(b - a) / 2 + 0.012, 0.0055), R,
                           k=0.012, bones=bones[i], tag="tongue"))
    return P
