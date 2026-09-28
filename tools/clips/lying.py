"""Lying family: LieDown (120 f), Lying_Idle (150 f loop), GetUp (120 f). No root motion (Root stays at the origin).

python3 tools/clips/lying.py [--in build/stage_b.blend] [--out <scratch>/test.blend] [--scratch DIR]
                             [--render all|none|Clip,Clip] [--step 4]
builds the clips on the rig, prints QA (anim_lib IK gap / planted hoof slide, locked-knee slide, mesh ground check
on Calf_LOD2, acceleration pops, exact seams between the three clips and against a Pose() clip), saves the blend
and renders root-tracking filmstrips + GIFs (tools/render_clip.py, left and three-quarter views).

Biomechanics (cattle):
  * lying down is FRONT end first: sniff the spot, the left fore flexes and the calf drops onto that carpus (front
    knee), then onto the right; the hindquarters then sink down and back onto the RIGHT hip while the chest follows
    the forearms back onto the sternum; the hind legs end folded to the calf's LEFT (left hind on top, cannon lying
    forward beside the belly), as in the GiM reference 29.6-38.7 s.
  * getting up is HIND end first: gather the hind legs under, lunge forward on the knees while the hind legs
    straighten and lift the rump, then the left fore steps onto its hoof, then the right, weight shift, stand.
  * the carpus bends so the cannon folds BACKWARD (the kneeling cannon lies on the ground behind the knee, hoof
    flexed with the toe pointing back); the hock bends the other way (IK poles).

Weight-bearing contacts never slide: standing hooves are planted at their rest position (per-leg Hermite tracks
with zero-tangent "stop" keys hold them exactly); kneeling carpi are kept on fixed ground points (`knee_points`) by
the knee lock in `clip_fn`, which solves body height (+ roll for two knees) every frame so each elbow stays a
forearm length from its contact.

Rig facts learnt here (useful for other families):
  * the front IK poles are children of Body and sit in front of / below the elbow: body ROLL tilts the front IK
    planes and drags a kneeling carpus sideways, so the chest stays unrolled (roll 0) whenever a knee is locked and
    the "on one hip" look is made with the Back bone (pelvis) roll + a Torso counter-roll;
  * for the same reason a fore leg stretched forward can only bend its carpus DOWNWARD mid-transition, so LYING
    keeps both fore legs folded (the reference stretches one out);
  * spine roll sign is opposite to body_rot roll: spine roll + = LEFT side down;
  * ears Vector(a, b, c): a + = forward / - = back, b + = droop down / - = up, c - = opening turns forward;
  * the library clamps a foot target at 0.992 x chain, below the rest reach of the fore legs, so a Pose() clip is
    9 mm / 3 deg away from the armature rest in the fore legs; every clip shares it, so chaining is exact.
"""
import copy, math, os, sys
import numpy as np
import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)
import anim_lib as A
from anim_lib import Pose, LEGS

FRONT = ("LF", "RF")
HIND = ("LH", "RH")
R_KNEE = 0.040          # carpus joint height when the knee rests on the ground (m)
R_FETLOCK = 0.034       # fetlock joint height when the cannon lies on the ground (m)


# ============================================================================ small helpers
def cp(P):
    return copy.deepcopy(P)


def fk(calf, P):
    """armature-space bone matrices of pose P (legs at their un-solved FK; tops/feet/body exact)"""
    calf.pose_to_basis(P)
    return calf._last_pose


def head(calf, P, bone):
    return fk(calf, P)[bone].translation.copy()


def rest_foot(calf, leg):
    return calf.rest_head(LEGS[leg]["foot"])


def set_foot(calf, P, leg, world):
    """absolute armature-space fetlock target, stored as a root-frame offset (root never moves here)"""
    P.feet[leg] = Vector(world) - rest_foot(calf, leg)


_DOF = {"x": ("body_off", 0), "y": ("body_off", 1), "z": ("body_off", 2),
        "pitch": ("body_rot", 0), "roll": ("body_rot", 1), "yaw": ("body_rot", 2)}


def _bump(P, dof, v):
    attr, i = _DOF[dof]
    vec = getattr(P, attr).copy(); vec[i] += v; setattr(P, attr, vec)


def solve_body(calf, P, residual_fns, dofs, iters=12, tol=1e-5):
    """Gauss-Newton on body DOFs so that every residual_fn(pose_matrices) -> 0."""
    def res(Q):
        M = fk(calf, Q)
        return np.array([f(M) for f in residual_fns])
    for _ in range(iters):
        r = res(P)
        if np.max(np.abs(r)) < tol:
            break
        J = np.zeros((len(r), len(dofs)))
        for j, d in enumerate(dofs):
            eps = 1e-3 if d in "xyz" else 0.05
            Q = cp(P); _bump(Q, d, eps)
            J[:, j] = (res(Q) - r) / eps
        dx = np.linalg.lstsq(J, -r, rcond=None)[0]
        for j, d in enumerate(dofs):
            _bump(P, d, float(dx[j]))
    return P


def elbow_name(leg):
    return LEGS[leg]["chain"][0]


def carpus_on_ground(calf, P, leg, K, back=True):
    """fetlock target that puts the carpus of front `leg` at ground point K (cannon lying backward)."""
    L2 = calf.bones[LEGS[leg]["chain"][1]].length
    drop = K.z - R_FETLOCK
    a = math.asin(max(-0.9, min(0.9, drop / L2)))
    d = Vector((0, math.cos(a), -math.sin(a))) if back else Vector((0, -math.cos(a), -math.sin(a)))
    set_foot(calf, P, leg, K + L2 * d)


# ============================================================================ interpolation
def hermite(keys, combine):
    """Piecewise cubic Hermite through keys [(frame, value, mode)], mode 'stop' = zero tangent (the value is held
    exactly between two equal stop keys, motion eases in/out) or 'pass' = non-uniform Catmull-Rom tangent.
    The first and last keys are always stops. combine(terms=[(w, value)...]) forms linear combinations."""
    ks = [(k[0], k[1], k[2] if len(k) > 2 else "pass") for k in keys]
    n = len(ks)

    def fn(f):
        if f <= ks[0][0]:
            return combine([(1.0, ks[0][1])])
        if f >= ks[-1][0]:
            return combine([(1.0, ks[-1][1])])
        i = max(j for j in range(n - 1) if ks[j][0] <= f)
        f1, P1, m1 = ks[i]
        f2, P2, m2 = ks[i + 1]
        t = (f - f1) / (f2 - f1)
        t2, t3 = t * t, t * t * t
        h00, h10, h01, h11 = 2 * t3 - 3 * t2 + 1, t3 - 2 * t2 + t, -2 * t3 + 3 * t2, t3 - t2
        terms = [(h00, P1), (h01, P2)]
        if i > 0 and m1 != "stop":
            f0, P0 = ks[i - 1][:2]
            a1 = (f2 - f1) / (f2 - f0)
            terms += [(h10 * a1, P2), (-h10 * a1, P0)]
        if i + 2 < n and m2 != "stop":
            f3, P3 = ks[i + 2][:2]
            a2 = (f2 - f1) / (f3 - f1)
            terms += [(h11 * a2, P3), (-h11 * a2, P1)]
        return combine(terms)
    return fn


def _foot_combine(terms):
    return (sum((w * v[0] for w, v in terms), Vector((0, 0, 0))), sum(w * v[1] for w, v in terms))


def foot_of(P, leg):
    """(fetlock offset, hoof flex) of `leg` in pose P, as a foot-track value"""
    return (P.feet.get(leg, Vector((0, 0, 0))).copy(), P.flex.get(leg, 0.0))


def in_plan(plan, leg, f):
    return any(a <= f <= b for a, b in plan.get(leg, ()))


def clip_fn(calf, body_keys, foot_keys, lock, overlays=()):
    """pose function of a clip: whole-pose Hermite keys for body/head/tail, independent Hermite tracks per foot
    (so planted feet hold exactly while the body moves), overlays, then the knee lock: while front `leg` is in a
    lock interval its carpus is held on the shared ground contact (fetlock target from the contact; body z, plus
    roll when both knees are down, solved so each elbow stays a forearm length from its contact). Keys at lock
    start/end frames are built to satisfy the lock already, so it switches on/off without a pop."""
    body = hermite(body_keys, A.pose_combine)
    feet = {leg: hermite(k, _foot_combine) for leg, k in foot_keys.items()}

    def fn(f):
        P = body(f)
        for leg, tr in feet.items():
            P.feet[leg], P.flex[leg] = tr(f)
        for ov in overlays:
            P = ov(f, P)
        legs = [leg for leg in FRONT if in_plan(lock, leg, f)]
        if legs:
            solve_body(calf, P, [knee_res(calf, leg) for leg in legs], ["z"] if len(legs) == 1 else ["z", "roll"])
            for leg in legs:
                kneel_leg(calf, P, leg)
        return P
    return fn


# ============================================================================ shared constant poses
def stand():
    """neutral standing pose == rest (auto_top off everywhere in this family so blends never switch mode)"""
    P = Pose()
    P.auto_top = False
    return P


LYING_TAIL = ((0.0, -8.0), (0.0, -5.0), (0.0, 0.0), (0.0, 5.0), (6.0, 10.0), (12.0, 25.0), (14.0, 30.0))
KNEEL_FLEX = 115.0      # hoof flex while the cannon lies on the ground behind the carpus (toe points back)
HIP_ROLL = -14.0        # Back (pelvis) roll when lying: right hip down (spine roll + = LEFT side down)
_KNEES = {}


def L1(calf, leg):
    return calf.bones[LEGS[leg]["chain"][0]].length


def _lying_base(calf):
    """LYING body, head, tail and hind legs (front legs are added by the callers). The chest stays upright on
    the sternum (body roll 0 keeps the front-leg IK planes vertical, so kneeling carpi stay put); only the
    pelvis rolls onto the right hip."""
    P = stand()
    P.body_rot = Vector((-2.0, 0.0, 0.0))
    P.body_off = Vector((0.0, 0.20, -0.43))
    P.spine = {"Back": (0.0, 0.0, HIP_ROLL), "Torso": (0.0, 0.0, -HIP_ROLL)}
    P.neck = [2.0, 3.0, 2.0]
    P.neck_yaw = [3.0, 3.0, 2.0]
    P.head = Vector((4.0, 3.0, -5.0))
    P.ears = {"L": Vector((-10.0, 12.0, 0.0)), "R": Vector((-10.0, 12.0, 0.0))}
    P.tail = list(LYING_TAIL)
    # hind legs folded to the left: femur flexed forward, hock on the ground behind, cannon lying forward
    P.femur = {"LH": 55.0, "RH": 60.0}
    set_foot(calf, P, "LH", (0.26, 0.33, R_FETLOCK))
    set_foot(calf, P, "RH", (0.00, 0.33, R_FETLOCK))
    P.flex["LH"] = -60.0
    P.flex["RH"] = -60.0
    return P


def knee_points(calf):
    """Carpus ground contacts shared by every kneeling and lying frame of the family. Derived from the lying
    body: the carpus lies a forearm length ahead of the elbow (forearm folded forward on the ground)."""
    if id(calf) not in _KNEES:
        M = fk(calf, _lying_base(calf))
        K = {}
        for leg in FRONT:
            E = M[elbow_name(leg)].translation
            dz = E.z - R_KNEE
            K[leg] = Vector((E.x, E.y - math.sqrt(L1(calf, leg) ** 2 - dz * dz), R_KNEE))
        _KNEES[id(calf)] = K
    return _KNEES[id(calf)]


def kneel_leg(calf, P, leg):
    """front leg kneeling on its carpus at the shared contact point (the elbow must be L1 from it)"""
    carpus_on_ground(calf, P, leg, knee_points(calf)[leg])
    P.flex[leg] = KNEEL_FLEX


def knee_res(calf, leg):
    K = knee_points(calf)[leg]; l1 = L1(calf, leg); n = elbow_name(leg)
    return lambda M: (M[n].translation - K).length - l1


def elbow_ahead_res(calf, leg, dy):
    """elbow `dy` behind (+) the knee contact"""
    K = knee_points(calf)[leg]; n = elbow_name(leg)
    return lambda M: M[n].translation.y - (K.y + dy)


def hip_z_res(z):
    return lambda M: 0.5 * (M["BackLeg.L"].translation.z + M["BackLeg.R"].translation.z) - z


def lying_folded(calf):
    """sternal recumbency on the right hip, hind legs folded to the left (left hind on top), both fore legs
    folded under the chest. LieDown passes through it; GetUp starts by returning to it."""
    P = _lying_base(calf)
    for leg in FRONT:
        kneel_leg(calf, P, leg)
    return P


def lying(calf):
    """LYING (LieDown end == Lying_Idle loop pose == GetUp start): sternal recumbency, both fore legs folded
    under the chest (carpi on the ground), pelvis rolled onto the right hip, hind legs folded to the left, head up.
    (The GiM reference stretches the upper fore leg forward; with this rig's front poles in front of/below the
    elbow a forward leg can only bend its carpus downward mid-transition, so the folded posture is used.)"""
    P = lying_folded(calf)
    P.neck = [0.0, 1.0, 1.0]
    P.head = Vector((6.0, 4.0, -4.0))
    return P


# ---------------------------------------------------------------------------- transition key poses
def sniff(calf):
    """standing, nose to the ground, weight a little back (inspecting the spot)"""
    P = stand()
    P.body_off = Vector((0.0, 0.012, -0.015))
    P.body_rot = Vector((1.5, 0.0, 0.0))
    P.neck = [14.0, 16.0, 14.0]
    P.head = Vector((16.0, 0.0, 0.0))
    P.ears = {"L": Vector((12.0, 4.0, -8.0)), "R": Vector((12.0, 4.0, -8.0))}
    P.tail = [(0.0, -2.0)] * 7
    return P


def kneel_prep(calf):
    """left fore lifts and flexes, the chest starts to sink, head stays low"""
    P = sniff(calf)
    P.body_off = Vector((-0.01, 0.0, -0.07))
    P.body_rot = Vector((5.0, 0.0, 0.0))
    P.neck = [12.0, 12.0, 10.0]
    K = knee_points(calf)["LF"]
    set_foot(calf, P, "LF", Vector((K.x, K.y + 0.14, 0.20)))
    P.flex["LF"] = 60.0
    return P


def kneel_left(calf):
    """left carpus touches down; right fore still on its hoof, strongly bent"""
    P = kneel_prep(calf)
    P.body_rot = Vector((12.0, 0.0, 0.0))
    P.neck = [2.0, 4.0, 4.0]
    P.head = Vector((8.0, 0.0, 0.0))
    kneel_leg(calf, P, "LF")
    P.feet["RF"] = Vector((0, 0, 0))
    solve_body(calf, P, [knee_res(calf, "LF"), elbow_ahead_res(calf, "LF", 0.05), hip_z_res(0.70)],
               ["y", "z", "pitch"])
    return P


def kneel_right_lift(calf):
    P = kneel_left(calf)
    K = knee_points(calf)["RF"]
    set_foot(calf, P, "RF", Vector((K.x, K.y + 0.12, 0.13)))
    P.flex["RF"] = 70.0
    return P


def kneel(calf, hip=0.70, ahead=0.05):
    """both carpi on the ground, hind legs still standing: the classic kneeling pose"""
    P = kneel_left(calf)
    P.body_rot = Vector((P.body_rot.x, 0.0, 0.0))
    P.neck = [0.0, 2.0, 2.0]
    P.head = Vector((6.0, 0.0, 0.0))
    kneel_leg(calf, P, "RF")
    solve_body(calf, P, [knee_res(calf, "LF"), knee_res(calf, "RF"), elbow_ahead_res(calf, "LF", ahead), hip_z_res(hip)],
               ["y", "z", "pitch", "roll"])
    return P


def hind_lowering(calf):
    """hindquarters sinking down and back toward the right hip, chest following the forearms back"""
    P = kneel(calf)
    P.femur = {"LH": 30.0, "RH": 32.0}
    P.spine = {"Back": (0.0, 0.0, 0.4 * HIP_ROLL), "Torso": (0.0, 0.0, -0.4 * HIP_ROLL)}
    P.neck = [6.0, 6.0, 4.0]
    P.head = Vector((6.0, 1.0, 0.0))
    P.tail = [(0.0, -10.0), (0.0, -6.0), (0.0, -4.0), (2.0, 0.0), (3.0, 0.0), (3.0, 0.0), (2.0, 0.0)]
    solve_body(calf, P, [knee_res(calf, "LF"), knee_res(calf, "RF"), elbow_ahead_res(calf, "LF", 0.15), hip_z_res(0.46)],
               ["y", "z", "pitch", "roll"])
    return P


def rump_down(calf):
    """hindquarters resting on the right hip, hind hooves still where they stood, chest nearly down"""
    P = lying_folded(calf)
    for leg in HIND:
        P.feet[leg] = Vector((0, 0, 0))
        P.flex[leg] = 0.0
    P.femur = {"LH": 50.0, "RH": 55.0}
    P.neck = [4.0, 4.0, 3.0]
    P.head = Vector((5.0, 2.0, -2.0))
    solve_body(calf, P, [knee_res(calf, "LF"), knee_res(calf, "RF"), elbow_ahead_res(calf, "LF", 0.23)],
               ["y", "z", "roll"])
    return P


# ============================================================================ clips
def lie_down(calf):
    """FRONT end first: sniff the spot, left carpus down, right carpus down, hindquarters sink onto the right hip
    while the chest follows the forearms back, hind legs slide out to the left, head comes up."""
    S = stand()
    kp, kl, krl, kn = kneel_prep(calf), kneel_left(calf), kneel_right_lift(calf), kneel(calf)
    hl, rd, lf, ly = hind_lowering(calf), rump_down(calf), lying_folded(calf), lying(calf)
    kn_low = cp(kn); kn_low.neck = [6.0, 8.0, 6.0]; kn_low.neck_yaw = [-2.0, -2.0, -1.0]; kn_low.head = Vector((10.0, -3.0, 2.0))
    body = [(0, S, "stop"), (14, sniff(calf)), (26, kp), (35, kl), (45, kn), (54, kn_low, "stop"),
            (70, hl), (84, rd), (96, lf, "stop"), (120, ly, "stop")]
    rest = (Vector((0, 0, 0)), 0.0)
    feet = {"LF": [(0, rest, "stop"), (17, rest, "stop"), (26, foot_of(kp, "LF")), (35, foot_of(kl, "LF"), "stop"),
                   (120, foot_of(ly, "LF"), "stop")],
            "RF": [(0, rest, "stop"), (34, rest, "stop"), (40, foot_of(krl, "RF")), (45, foot_of(kn, "RF"), "stop"),
                   (120, foot_of(ly, "RF"), "stop")],
            "LH": [(0, rest, "stop"), (83, rest, "stop"), (96, foot_of(lf, "LH"), "stop"), (120, foot_of(ly, "LH"), "stop")],
            "RH": [(0, rest, "stop"), (84, rest, "stop"), (98, foot_of(lf, "RH"), "stop"), (120, foot_of(ly, "RH"), "stop")]}
    lock = {"LF": [(35, 120)], "RF": [(45, 120)]}
    planted = {"LF": [(0, 17)], "RF": [(0, 34)], "LH": [(0, 83), (96, 120)], "RH": [(0, 84), (98, 120)]}
    return 120, clip_fn(calf, body, feet, lock), lock, planted


def get_up(calf):
    """HIND end first: gather, lunge forward onto the knees while the hind legs straighten (rump up), then the left
    fore steps up onto its hoof, then the right, weight shift, stand."""
    S, ly, lf = stand(), lying(calf), lying_folded(calf)
    prep = cp(ly); prep.neck = [-4.0, -4.0, -2.0]; prep.head = Vector((0.0, 1.0, -2.0))
    prep.ears = {"L": Vector((10.0, 0.0, -10.0)), "R": Vector((10.0, 0.0, -10.0))}
    gather = cp(lf)
    gather.spine = {"Back": (0.0, 0.0, 0.3 * HIP_ROLL), "Torso": (0.0, 0.0, -0.3 * HIP_ROLL)}
    gather.femur = {"LH": 45.0, "RH": 45.0}
    gather.neck = [-2.0, -2.0, 0.0]; gather.head = Vector((0.0, 0.0, 0.0)); gather.ears = prep.ears
    gather.tail = list(LYING_TAIL)
    for leg in HIND:
        gather.feet[leg] = Vector((0, 0, 0)); gather.flex[leg] = 0.0
    solve_body(calf, gather, [knee_res(calf, "LF"), knee_res(calf, "RF"), elbow_ahead_res(calf, "LF", 0.26)],
               ["y", "z", "roll"])
    lunge = kneel(calf, hip=0.52, ahead=0.12)
    lunge.femur = {"LH": 22.0, "RH": 22.0}
    lunge.spine = {"Back": (0.0, 0.0, 0.1 * HIP_ROLL), "Torso": (0.0, 0.0, -0.1 * HIP_ROLL)}
    lunge.neck = [8.0, 9.0, 7.0]; lunge.head = Vector((8.0, 0.0, 0.0))
    lunge.tail = [(0.0, -10.0), (0.0, -6.0), (0.0, -2.0), (2.0, 6.0), (3.0, 8.0), (3.0, 6.0), (2.0, 4.0)]
    solve_body(calf, lunge, [knee_res(calf, "LF"), knee_res(calf, "RF"), elbow_ahead_res(calf, "LF", 0.12), hip_z_res(0.52)],
               ["y", "z", "pitch", "roll"])
    kn = kneel(calf)
    kn.neck = [5.0, 6.0, 5.0]; kn.head = Vector((6.0, 0.0, 0.0))
    kn_hold = cp(kn); kn_hold.neck = [4.0, 4.0, 3.0]; kn_hold.head = Vector((4.0, 0.0, 0.0))
    # left fore steps up: knee lifts, hoof swings forward and plants at its rest position
    step = cp(kn_hold)            # no body roll while a carpus is locked (the IK pole plane would tilt the knee)
    step.neck = [0.0, 0.0, 0.0]; step.head = Vector((2.0, 0.0, 0.0))
    E = head(calf, kn, elbow_name("LF"))
    swing = (Vector((E.x, E.y - 0.10, 0.20)) - rest_foot(calf, "LF"), 20.0)
    push = cp(step); push.body_off = push.body_off + Vector((0.0, -0.01, 0.03))
    push.body_rot = Vector((push.body_rot.x - 2.0, 0.0, 0.0))
    push.neck = [-4.0, -4.0, -2.0]; push.head = Vector((0.0, 0.0, 0.0))
    solve_body(calf, push, [knee_res(calf, "RF")], ["z"])
    # right fore comes up: body rises on the planted left hoof and the hind legs
    rise = stand()
    rise.body_off = Vector((0.0, 0.0, -0.14)); rise.body_rot = Vector((7.0, 2.0, 0.0))
    rise.neck = [-6.0, -6.0, -4.0]; rise.head = Vector((-2.0, 0.0, 0.0))
    E = head(calf, push, elbow_name("RF"))
    swing_r = (Vector((E.x, E.y - 0.08, 0.18)) - rest_foot(calf, "RF"), 25.0)
    up = stand(); up.body_off = Vector((0.0, -0.01, -0.03)); up.body_rot = Vector((1.0, -1.0, 0.0))
    up.neck = [-6.0, -5.0, -3.0]; up.head = Vector((-3.0, -2.0, 0.0))
    up.ears = {"L": Vector((6.0, -4.0, -6.0)), "R": Vector((6.0, -4.0, -6.0))}
    settle = stand(); settle.neck = [1.0, 1.0, 1.0]; settle.head = Vector((1.0, 1.0, 0.0))
    body = [(0, ly, "stop"), (10, prep), (22, gather), (34, lunge), (44, kn), (52, kn_hold, "stop"),
            (60, step), (70, push), (84, rise), (97, up), (109, settle), (120, S, "stop")]
    rest = (Vector((0, 0, 0)), 0.0)
    feet = {"LF": [(0, foot_of(lf, "LF"), "stop"), (52, foot_of(lf, "LF"), "stop"), (60, swing), (68, rest, "stop"),
                   (120, rest, "stop")],
            "RF": [(0, foot_of(lf, "RF"), "stop"), (70, foot_of(lf, "RF"), "stop"), (78, swing_r), (87, rest, "stop"),
                   (120, rest, "stop")],
            "LH": [(0, foot_of(ly, "LH"), "stop"), (8, foot_of(ly, "LH"), "stop"), (22, rest, "stop"), (120, rest, "stop")],
            "RH": [(0, foot_of(ly, "RH"), "stop"), (6, foot_of(ly, "RH"), "stop"), (20, rest, "stop"), (120, rest, "stop")]}
    lock = {"LF": [(0, 52)], "RF": [(0, 70)]}      # lock ends exactly on keys that satisfy it (kn_hold, push)
    planted = {"LF": [(68, 120)], "RF": [(87, 120)], "LH": [(22, 120)], "RH": [(20, 120)]}
    return 120, clip_fn(calf, body, feet, lock), lock, planted


def lying_idle(calf, N=150):
    """loop at LYING: breathing, cud chewing, looking around, ear flicks, a tail flick"""
    ly = lying(calf)
    def look(yaw, pitch=0.0, tilt=0.0):
        P = cp(ly)
        P.neck_yaw = [ly.neck_yaw[0] + 0.3 * yaw, ly.neck_yaw[1] + 0.35 * yaw, ly.neck_yaw[2] + 0.35 * yaw]
        P.neck = [ly.neck[0] + 0.3 * pitch, ly.neck[1] + 0.35 * pitch, ly.neck[2] + 0.35 * pitch]
        P.head = ly.head + Vector((0.5 * pitch, 0.4 * yaw, tilt))
        return P
    body = [(0, ly, "stop"), (20, look(18.0, -4.0, -3.0)), (40, look(24.0, -2.0, -4.0), "stop"),
            (62, look(2.0, 6.0, 0.0)), (78, look(-2.0, 8.0, 2.0), "stop"), (100, look(-26.0, -3.0, 5.0)),
            (116, look(-22.0, -2.0, 4.0), "stop"), (134, look(-4.0, 1.0, 0.0)), (N, ly, "stop")]
    feet = {leg: [(0, foot_of(ly, leg), "stop"), (N, foot_of(ly, leg), "stop")] for leg in LEGS}

    def pulse(f, f0, dur):
        """0 -> 1 -> 0 bump over [f0, f0 + dur]"""
        t = (f - f0) / dur
        return math.sin(math.pi * t) ** 2 if 0.0 < t < 1.0 else 0.0

    def overlay(f, P):
        ph = 2 * math.pi * f / N
        # breathing: 3 breaths per loop (~1.7 s), ribcage/loin rise
        b = math.sin(3 * ph)
        P.spine = dict(P.spine)
        for n, amt in (("Torso", 0.6), ("Torso2", -0.4)):
            pt, yw, rl = P.spine.get(n, (0.0, 0.0, 0.0))
            P.spine[n] = (pt + amt * b, yw, rl)
        # rumination: 8 chews per loop, a pause while listening at the right look
        chew = 0.5 * (1 - math.cos(8 * ph)) * (1.0 - 0.8 * pulse(f, 84, 40))
        P.jaw = P.jaw + 7.0 * chew
        P.head = P.head + Vector((0.8 * chew, 0.0, 1.2 * math.sin(8 * ph)))
        # ear flicks
        P.ears = {k: v.copy() for k, v in P.ears.items()}
        P.ears["L"] = P.ears["L"] + Vector((-25.0, -10.0, 0.0)) * pulse(f, 28, 9)
        P.ears["R"] = P.ears["R"] + Vector((-25.0, -10.0, 0.0)) * pulse(f, 90, 8)
        both = pulse(f, 118, 10)
        P.ears["L"] = P.ears["L"] + Vector((20.0, -8.0, -10.0)) * pulse(f, 60, 22) + Vector((-18.0, 0, 0)) * both
        P.ears["R"] = P.ears["R"] + Vector((20.0, -8.0, -10.0)) * pulse(f, 60, 22) + Vector((-18.0, 0, 0)) * both
        # tail flick (tip lifts and swishes once)
        k = pulse(f, 64, 14)
        P.tail = [(s + k * 12.0 * max(0, i - 2) / 4.0 * math.sin(2 * math.pi * (f - 64) / 14.0), l + k * 8.0 * (i >= 3))
                  for i, (s, l) in enumerate(P.tail)]
        return P
    lock = {"RF": [(0, N)], "LF": [(0, N)]}
    planted = {leg: [(0, N)] for leg in LEGS}
    return N, clip_fn(calf, body, feet, lock, overlays=(overlay,)), lock, planted


# ============================================================================ mesh ground check
class GroundCheck:
    """Evaluates the cage mesh Calf_LOD2 (armature modifier on) and reports min z of body (non-hoof)
    vertices and per-leg hoof vertices (orig_part == 2 faces)."""

    def __init__(self, calf, obj="Calf_LOD2"):
        self.calf = calf
        self.ob = bpy.data.objects[obj]
        me = self.ob.data
        part = np.zeros(len(me.polygons), np.int32)
        me.attributes["orig_part"].data.foreach_get("value", part)
        hoof = np.zeros(len(me.vertices), bool)
        for p in me.polygons:
            if part[p.index] == 2:
                hoof[list(p.vertices)] = True
        co = np.zeros(len(me.vertices) * 3, np.float32); me.vertices.foreach_get("co", co)
        self.rest = co.reshape(-1, 3)
        self.hoof = hoof
        # region of every vertex by dominant deform bone (for the report breakdown only)
        gname = {g.index: g.name for g in self.ob.vertex_groups}
        region = []
        for v in me.vertices:
            best, bw = "", 0.0
            for g in v.groups:
                if g.weight > bw:
                    best, bw = gname.get(g.group, ""), g.weight
            region.append("tail" if best.startswith("Tail") else
                          "leg" if best.startswith(("FrontUpperLeg", "FrontLowerLeg", "BackUpperLeg", "BackLowerLeg",
                                                    "IKFront", "IKBack", "FF")) else
                          "head" if best.startswith(("Head", "Jaw", "Ear", "Neck")) else "trunk")
        self.region = np.array(region)
        self.leg_of = {}
        for leg in LEGS:
            sx = 1 if leg[0] == "L" else -1
            sy = -1 if leg[1] == "F" else 1
            self.leg_of[leg] = hoof & (np.sign(self.rest[:, 0]) == sx) & (np.sign(self.rest[:, 1]) == sy)

    def sample(self, act, frames):
        mods = [m for m in self.ob.modifiers if m.type == "ARMATURE"]
        old = [m.show_viewport for m in mods]
        for m in mods: m.show_viewport = True
        self.calf.use_action(act)
        rows = []
        for f in frames:
            self.calf.sc.frame_set(f)
            dg = bpy.context.evaluated_depsgraph_get()
            ev = self.ob.evaluated_get(dg)
            m = ev.to_mesh()
            co = np.zeros(len(m.vertices) * 3, np.float32); m.vertices.foreach_get("co", co)
            ev.to_mesh_clear()
            co = co.reshape(-1, 3) @ np.array(self.ob.matrix_world)[:3, :3].T + np.array(self.ob.matrix_world)[:3, 3]
            body = co[~self.hoof, 2]
            i = int(np.argmin(np.where(~self.hoof, co[:, 2], 9)))
            reg = {r: float(co[(self.region == r) & ~self.hoof, 2].min()) for r in ("trunk", "head", "leg", "tail")}
            rows.append(dict(f=f, body=float(body.min()), body_at=self.rest[i].round(2).tolist(), region=reg,
                             hoof={leg: float(co[msk, 2].min()) for leg, msk in self.leg_of.items()}))
        for m, o in zip(mods, old): m.show_viewport = o
        return rows

    def report(self, act, frames, planted=None, label=""):
        rows = self.sample(act, frames)
        worst = min(rows, key=lambda r: r["body"])
        msg = (f"GROUND {label or act.name}: non-hoof min z {worst['body']*100:+.1f} cm (f{worst['f']}, rest-vert "
               f"{[round(x, 2) for x in worst['body_at']]}) [" +
               ", ".join(f"{r} {min(w['region'][r] for w in rows)*100:+.1f}" for r in ("trunk", "head", "leg", "tail")) + "]")
        bad = [(r["f"], round(r["body"] * 100, 1)) for r in rows if r["body"] < -0.02]
        if bad:
            msg += f" | frames below -2 cm: {bad[:12]}{' ...' if len(bad) > 12 else ''}"
        if planted:
            hz = [r["hoof"][leg] for r in rows for leg in LEGS if planted(leg, r["f"])]
            if hz:
                msg += f" | planted hoof min z {min(hz)*100:+.1f} .. {max(hz)*100:+.1f} cm"
        print(msg)
        return rows


# ============================================================================ QA helpers
def knee_qa(calf, act, frames, lock, label=""):
    """carpus (front knee) drift in xy and height while locked"""
    calf.use_action(act)
    worst, zr = 0.0, [9.0, -9.0]
    anchor = {}
    for f in range(frames + 1):
        calf.sc.frame_set(f)
        ae = calf.arm.evaluated_get(bpy.context.evaluated_depsgraph_get())
        for leg in FRONT:
            if in_plan(lock, leg, f):
                c = ae.matrix_world @ ae.pose.bones[LEGS[leg]["chain"][1]].head
                a = anchor.setdefault((leg, [iv for iv in lock[leg] if iv[0] <= f <= iv[1]][0]), c.copy())
                worst = max(worst, (c.xy - a.xy).length)
                zr = [min(zr[0], c.z), max(zr[1], c.z)]
    print(f"KNEE {label or act.name}: locked carpus slide {worst*1000:.2f} mm, height {zr[0]*100:.1f}..{zr[1]*100:.1f} cm")
    return worst


def bone_state(calf, act, f):
    """armature-space matrices of every bone of `act` at frame f"""
    calf.use_action(act)
    calf.sc.frame_set(f)
    ae = calf.arm.evaluated_get(bpy.context.evaluated_depsgraph_get())
    return {pb.name: pb.matrix.copy() for pb in ae.pose.bones}


def seam(calf, a, fa, b, fb):
    """max bone head distance (mm) and max bone rotation difference (deg) between two clip frames"""
    A_, B_ = bone_state(calf, a, fa), bone_state(calf, b, fb)
    dp = max((A_[n].translation - B_[n].translation).length for n in A_) * 1000
    dr = max(math.degrees(A_[n].to_quaternion().rotation_difference(B_[n].to_quaternion()).angle) for n in A_)
    return dp, dr


def pop_qa(calf, act, frames, loop=False, label=""):
    """largest per-frame bone-head acceleration (2nd difference, mm/frame^2) and velocity: pops show as spikes"""
    calf.use_action(act)
    pts = []
    for f in range(frames + 1):
        calf.sc.frame_set(f)
        ae = calf.arm.evaluated_get(bpy.context.evaluated_depsgraph_get())
        pts.append(np.array([list(pb.tail) for pb in ae.pose.bones]))
    P = np.array(pts)
    if loop:                       # frame N == frame 0: wrap around the seam
        P = np.concatenate([P[-2:-1], P, P[1:2]])
    acc = np.linalg.norm(P[2:] - 2 * P[1:-1] + P[:-2], axis=2).max(axis=1) * 1000
    vel = np.linalg.norm(P[1:] - P[:-1], axis=2).max(axis=1) * 1000
    i = int(np.argmax(acc))
    print(f"POP {label or act.name}: max accel {acc.max():.1f} mm/f^2 at f{i + (0 if loop else 1)} | max speed {vel.max():.1f} mm/f")
    return acc, vel


def planted_from(plan):
    return lambda leg, f: in_plan(plan, leg, f)


# ============================================================================ clips
CLIPS = {}      # name -> (frames, fn, loop, lock, planted); filled by build()


def build(calf):
    made = []
    for name, maker, loop in (("LieDown", lie_down, False), ("Lying_Idle", lying_idle, True), ("GetUp", get_up, False)):
        N, fn, lock, planted = maker(calf)
        calf.make_clip(name, N, fn, loop=loop)
        CLIPS[name] = (N, fn, loop, lock, planted)
        made.append(name)
    return made


if __name__ == "__main__":
    import argparse, subprocess
    ROOT = os.path.dirname(TOOLS)
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src", default=os.path.join(ROOT, "build", "stage_b.blend"))
    ap.add_argument("--scratch", default="/tmp/claude-0/-home-user-Game-asset/f3fb310f-97d7-5da4-a5e8-b863f47eb685/scratchpad/lying",
                    help="directory for the test blend and the renders")
    ap.add_argument("--out", default=None, help="test blend (default <scratch>/test.blend)")
    ap.add_argument("--render", default="all", help="'all', 'none' or comma list of clips")
    ap.add_argument("--step", type=int, default=4, help="render every n-th frame")
    a = ap.parse_args()
    SCR = a.scratch
    os.makedirs(SCR, exist_ok=True)
    a.out = a.out or os.path.join(SCR, "test.blend")
    calf = A.Calf(a.src)
    names = build(calf)
    gc = GroundCheck(calf)
    for n in names:
        N, fn, loop, lock, planted = CLIPS[n]
        act = bpy.data.actions[n]
        calf.qa(act, N, planted_from(planted), label=n)
        knee_qa(calf, act, N, lock, label=n)
        gc.report(act, range(0, N + 1, 2), planted_from(planted), label=n)
        pop_qa(calf, act, N, loop=loop, label=n)
    acts = {n: bpy.data.actions[n] for n in names}
    for label, (x, fx), (y, fy) in (("LieDown end -> Lying_Idle start", ("LieDown", CLIPS["LieDown"][0]), ("Lying_Idle", 0)),
                                    ("Lying_Idle loop seam", ("Lying_Idle", CLIPS["Lying_Idle"][0]), ("Lying_Idle", 0)),
                                    ("Lying_Idle end -> GetUp start", ("Lying_Idle", CLIPS["Lying_Idle"][0]), ("GetUp", 0))):
        dp, dr = seam(calf, acts[x], fx, acts[y], fy)
        print(f"SEAM {label}: {dp:.3f} mm / {dr:.3f} deg")
    ref = calf.make_clip("_PoseRef", 1, lambda f: Pose(), loop=False)     # what any clip keys for Pose()
    for label, (x, fx) in (("LieDown start", ("LieDown", 0)), ("GetUp end", ("GetUp", CLIPS["GetUp"][0]))):
        dp, dr = seam(calf, acts[x], fx, ref, 0)
        print(f"SEAM {label} vs make_clip(Pose()): {dp:.3f} mm / {dr:.3f} deg")
    bpy.data.actions.remove(ref)
    calf.save(a.out)
    todo = names if a.render == "all" else ([] if a.render == "none" else a.render.split(","))
    for n in todo:
        N = CLIPS[n][0]
        for side in ("left", "threequarter"):
            subprocess.run([sys.executable, os.path.join(TOOLS, "render_clip.py"), a.out, n,
                            os.path.join(SCR, f"{n}_{side}"), "--frames", f"0:{N}:{a.step}", "--res", "320",
                            "--samples", "6", "--side", side], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print("rendered", n, side)
