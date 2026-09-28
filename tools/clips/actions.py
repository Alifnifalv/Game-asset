"""Clip family "actions": Death, Leap, HeadShake for the calf rig.

    build(calf) -> ["Death", "Leap", "HeadShake"]

Clips (30 fps)
  Death      72 f, no root motion. Pose() -> flinch (head jerks up, ears back, tail clamps) -> stagger to the right
             (right fore then right hind step out to catch the sway) -> front legs buckle (carpi fold forward,
             chest drops, head sags) -> the calf topples onto its RIGHT side with gravity acceleration (roll ~88 deg),
             legs lose tension and swing out to its left, head whips down after the body -> impact with a small
             bounce / roll-back -> last hind-leg stretch -> limp. dead_pose() is held exactly from f62 to f72.
             Reference: GiM video ~26.8-27.5 s (falls onto its right side, legs out, head on the ground).
  Leap       42 f, root motion ~1.4 m along -Y. Playful calf jump/buck: Pose() -> crouch with the weight back ->
             front lifts first (fore feet tuck) -> hind push-off -> airborne (~0.3 s, apex ~15 cm) with a buck:
             hind legs kick out back and up -> front feet reach and land first, hind feet swing through and land
             -> absorb -> Pose() at the new root position. Planted hooves are fixed world positions (0 slide).
  HeadShake  36 f. Fly-shaking: head dips, then 2.5 fast (7-frame period, ~4.3 Hz) head roll/yaw oscillations
             that start at the withers and neck base (overlapping action), ears flap with ~1/4-period lag and
             more amplitude than the head, tail flicks, settle with an ear flick. Pose() -> Pose(), legs planted.

Shared constant poses (module level): stand_pose() (== Pose(), the start of all three and the end of Leap and
HeadShake, relative to the root) and dead_pose(calf) (end of Death). The pose functions return them verbatim on
the boundary frames; QA prints how far the raw curves are from them there.

Conventions verified on this rig (quick FK probes + renders):
  Pose.flex + = toe back; Pose.ears x + = tip forward, y + = tip down (droop), z = twist; Pose.head roll + =
  left ear down; body_rot roll + = right side down; spine roll + = LEFT side down; tail side + = tail tip toward
  the calf's right (-X). Pose() lifts the straight front hooves ~2 mm (reach clamp), so standing clips never
  raise the elbows (no body z > 0 / no roll / no nose-up pitch while all four feet are planted).

Library extension (kept here, anim_lib.py is shared): make_clip_ex() is Calf.make_clip with a per-frame basis
hook. Death uses it to turn the hoof bones with the body once a leg goes limp (anim_lib keeps hooves upright:
only root yaw + flex), so the hooves lie along the legs when the calf is on its side.

Standalone: python3 tools/clips/actions.py [--in build/stage_b.blend] [--out-dir DIR] [--no-render] [--only a,b]
                                           [--res 320] [--samples 6] [--gif-step 2]
  builds the clips, prints calf.qa + a Calf_LOD2 mesh ground check + carpus/hock bend + pops + boundaries,
  saves DIR/test.blend and renders filmstrips (DIR/<clip>_<side>.png) + GIFs (DIR/<clip>_<side>_anim.gif).
"""
import argparse, math, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(TOOLS)
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import bpy
import numpy as np
from mathutils import Matrix, Quaternion, Vector
import anim_lib as A
from anim_lib import Pose, LEGS

FPS = 30
CLIPS = ("Death", "Leap", "HeadShake")
FRONT, HIND = ("LF", "RF"), ("LH", "RH")
LEG_PARENT = {"LF": "Torso2", "RF": "Torso2", "LH": "Back", "RH": "Back"}   # parent of each leg's top bone chain


# ============================================================================== small maths
def V(x=0.0, y=0.0, z=0.0):
    return Vector((x, y, z))


def clamp01(t):
    return min(1.0, max(0.0, t))


def smooth(t):
    t = clamp01(t)
    return t * t * (3 - 2 * t)


def smoother(t):
    t = clamp01(t)
    return t * t * t * (t * (6 * t - 15) + 10)


def ramp(f, a, b, fn=smooth):
    """0 before a, 1 after b, eased in between"""
    return fn((f - a) / float(b - a))


def bump(f, a, p, b):
    """0 outside (a, b), 1 at p, smooth rise and fall"""
    if f <= a or f >= b:
        return 0.0
    return smooth((f - a) / (p - a)) if f < p else 1.0 - smooth((f - p) / (b - p))


def flick(f, f0, up=3.0, down=9.0):
    """quick twitch: fast ease-out rise over `up` frames, slower settle over `down` frames"""
    t = f - f0
    if t <= 0 or t >= up + down:
        return 0.0
    if t < up:
        u = t / up
        return 1 - (1 - u) ** 2
    return 1.0 - smooth((t - up) / down)


class Curve:
    """Scalar key curve, piecewise cubic Hermite. keys: (frame, value) -> monotone (Fritsch-Carlson) slope, no
    overshoot, flat at extremes; (frame, value, slope) or (frame, value, slope_in, slope_out) -> explicit slopes
    (value per frame; None = auto). Explicit slopes model impacts (fast arrival, abrupt stop)."""

    def __init__(self, keys):
        ks = sorted(keys, key=lambda k: k[0])
        xs = [float(k[0]) for k in ks]; ys = [float(k[1]) for k in ks]
        n = len(xs)
        d = [(ys[i + 1] - ys[i]) / (xs[i + 1] - xs[i]) for i in range(n - 1)]
        m = [0.0] * n
        for i in range(1, n - 1):
            m[i] = 0.0 if d[i - 1] * d[i] <= 0 else 0.5 * (d[i - 1] + d[i])
        for i in range(n - 1):
            if d[i] == 0.0:
                m[i] = m[i + 1] = 0.0
                continue
            a, b = m[i] / d[i], m[i + 1] / d[i]
            if a < 0: m[i] = 0.0; a = 0.0
            if b < 0: m[i + 1] = 0.0; b = 0.0
            s = a * a + b * b
            if s > 9.0:
                t = 3.0 / math.sqrt(s)
                m[i] = t * a * d[i]; m[i + 1] = t * b * d[i]
        mi, mo = m[:], m[:]
        for i, k in enumerate(ks):
            if len(k) >= 3 and k[2] is not None:
                mi[i] = mo[i] = float(k[2])
            if len(k) >= 4 and k[3] is not None:
                mo[i] = float(k[3])
        self.xs, self.ys, self.mi, self.mo = xs, ys, mi, mo

    def __call__(self, f):
        xs, ys = self.xs, self.ys
        if f <= xs[0]:
            return ys[0]
        if f >= xs[-1]:
            return ys[-1]
        i = 0
        while f > xs[i + 1]:
            i += 1
        h = xs[i + 1] - xs[i]
        t = (f - xs[i]) / h
        t2, t3 = t * t, t * t * t
        return ((2 * t3 - 3 * t2 + 1) * ys[i] + (t3 - 2 * t2 + t) * h * self.mo[i]
                + (-2 * t3 + 3 * t2) * ys[i + 1] + (t3 - t2) * h * self.mi[i + 1])


class VCurve:
    """Curve per component of a Vector (or of a list of floats)"""

    def __init__(self, keys, size=3):
        self.size = size
        self.c = [Curve([(k[0], k[1][i]) + tuple(None if s is None else s[i] for s in k[2:]) for k in keys])
                  for i in range(size)]

    def __call__(self, f):
        return [c(f) for c in self.c]


def hermite_path(keys):
    """Vector path through keys [(frame, Vector, tangent Vector (per frame) or None)]. None = non-uniform
    Catmull-Rom tangent (zero at the end keys)."""
    fs = [float(k[0]) for k in keys]; ps = [Vector(k[1]) for k in keys]
    n = len(keys)
    ms = []
    for i, k in enumerate(keys):
        if len(k) > 2 and k[2] is not None:
            ms.append(Vector(k[2]))
        elif 0 < i < n - 1:
            ms.append((ps[i + 1] - ps[i - 1]) / (fs[i + 1] - fs[i - 1]))
        else:
            ms.append(V())

    def fn(f):
        if f <= fs[0]:
            return ps[0].copy()
        if f >= fs[-1]:
            return ps[-1].copy()
        i = 0
        while f > fs[i + 1]:
            i += 1
        h = fs[i + 1] - fs[i]
        t = (f - fs[i]) / h
        t2, t3 = t * t, t * t * t
        return ((2 * t3 - 3 * t2 + 1) * ps[i] + (t3 - 2 * t2 + t) * h * ms[i]
                + (-2 * t3 + 3 * t2) * ps[i + 1] + (t3 - t2) * h * ms[i + 1])
    return fn


# ============================================================================== pose helpers
def copy_pose(P):
    Q = A.pose_combine([(1.0, P)])
    Q.auto_top = P.auto_top
    Q.top_gain = dict(P.top_gain)
    return Q


def add_spine(P, bone, pitch=0.0, yaw=0.0, roll=0.0):
    p, y, r = P.spine.get(bone, (0.0, 0.0, 0.0))
    P.spine[bone] = (p + pitch, y + yaw, r + roll)


def add_tail_wave(P, amp_side, phase, lift=0.0, lag=0.07):
    """travelling wave along the tail (grows toward the tip); phase in cycles"""
    for i in range(7):
        s, l = P.tail[i]
        P.tail[i] = (s + amp_side * (0.35 + 0.16 * (i + 1)) * math.sin(2 * math.pi * (phase - lag * (i + 1))),
                     l + lift * (1.0 - 0.1 * i))


def rest_foot(calf, leg):
    return calf.rest_head(LEGS[leg]["foot"])


def body_rot_matrix(P):
    """rotation (3x3, armature space) the body gets from root yaw + body_rot (same maths as anim_lib)"""
    pr, rr, yr = (math.radians(v) for v in P.body_rot)
    return (Matrix.Rotation(math.radians(P.root_yaw), 3, "Z") @ Matrix.Rotation(yr, 3, "Z") @
            Matrix.Rotation(pr, 3, "X") @ Matrix.Rotation(-rr, 3, "Y"))


def leg_frames(calf, P):
    """armature-space transform of each leg's parent bone (Torso2 front / Back hind) relative to its rest:
    M_pose @ M_rest^-1. Maps rest-space points carried by the trunk into the pose."""
    calf.pose_to_basis(P)
    M = calf._last_pose
    return {leg: M[n] @ calf.rest[n].inverted() for leg, n in LEG_PARENT.items()}


def make_clip_ex(calf, name, frames, pose_fn, loop=False, basis_hook=None):
    """anim_lib.Calf.make_clip (no reach pass) with basis_hook(frame, Pose, basis dict) called after
    pose_to_basis, before keying (used to re-orient hoof bones about their head: the leg IK targets the head
    only, so the solve is unaffected)."""
    act = calf.new_action(name)
    poses = [pose_fn(f) for f in range(frames + 1)]
    chain_bones = [n for d in LEGS.values() for n in d["chain"]]
    for pb in calf.arm.pose.bones:
        pb.matrix_basis = Matrix.Identity(4)
    samples = {n: [] for n in calf.order if n not in chain_bones}
    for f in range(frames + 1):
        B = calf.pose_to_basis(poses[f])
        if basis_hook:
            basis_hook(f, poses[f], B)
        for n in samples:
            loc, rot, _ = B.get(n, Matrix.Identity(4)).decompose()
            samples[n].append((loc, rot))
    calf.write_curves(act, samples)
    calf.use_action(act)
    calf.add_ik()
    calf.use_action(act)
    baked = {n: [] for n in chain_bones}
    for f in range(frames + 1):
        calf.sc.frame_set(f)
        dg = bpy.context.evaluated_depsgraph_get()
        ae = calf.arm.evaluated_get(dg)
        for n in chain_bones:
            par = ae.pose.bones[calf.par[n]].matrix
            local = (par @ calf.rel(n)).inverted() @ ae.pose.bones[n].matrix
            baked[n].append((Vector((0, 0, 0)), local.to_quaternion()))
    calf.remove_ik()
    calf.write_curves(act, baked)
    act.use_frame_range = True
    act.frame_start, act.frame_end = 0, frames
    act.use_cyclic = loop
    return act


# ============================================================================== shared constant poses
def stand_pose(root=None):
    """neutral standing pose (rest). `root` = root position (Leap ends 1.4 m ahead): the feet are then given as
    feet_world at their rest positions under that root (identical bone transforms relative to the root)."""
    P = Pose()
    if root is not None:
        P.root_pos = Vector(root)
        for leg in LEGS:
            P.feet_world[leg] = Vector(root) + _REST_FEET[leg]
    return P


_REST_FEET = {}      # filled by _init(calf): leg -> rest fetlock position


def _init(calf):
    for leg, d in LEGS.items():
        _REST_FEET[leg] = calf.rest_head(d["foot"])


# ---------------------------------------------------------------------------- DEAD (end of Death)
# lying flat on the RIGHT side (as in the GiM reference), legs limp and extended out to the calf's left, head on
# the ground on its right cheek. Feet are given in armature space (the root never moves in Death).
DEAD = dict(
    body_off=V(-0.30, 0.02, -0.50),
    body_rot=V(2.0, 88.0, -4.0),
    spine={"Back": (0.0, 3.0, 0.0), "Torso": (0.0, 2.0, 0.0), "Torso3": (4.0, -3.0, 0.0)},
    neck=[8.0, 8.0, 6.0],
    neck_yaw=[-6.0, -8.0, -8.0],
    head=V(8.0, -8.0, 0.0),
    jaw=6.0,
    ears={"L": V(-10.0, 35.0, 0.0), "R": V(-10.0, 30.0, 0.0)},
    tail=[(14.0, -6.0), (10.0, 0.0), (6.0, 0.0), (3.0, 0.0), (0.0, 0.0), (0.0, 0.0), (0.0, 0.0)],
    feet={"LF": V(0.14, -0.60, 0.11), "RF": V(0.20, -0.56, 0.04),
          "LH": V(0.16, 0.58, 0.12), "RH": V(0.18, 0.63, 0.04)},
    flex={"LF": 25.0, "RF": 20.0, "LH": 20.0, "RH": 15.0},
    top_rot={"LF": (-12.0, 0.0, 0.0), "RF": (-6.0, 0.0, 0.0)},
    femur={"LH": -8.0, "RH": -14.0},
)


def dead_pose(calf):
    """final Death pose (held). auto_top off: the legs' tops only get the explicit top_rot / femur."""
    P = Pose()
    P.auto_top = False
    P.body_off = DEAD["body_off"].copy(); P.body_rot = DEAD["body_rot"].copy()
    P.spine = dict(DEAD["spine"])
    P.neck = list(DEAD["neck"]); P.neck_yaw = list(DEAD["neck_yaw"]); P.head = DEAD["head"].copy()
    P.jaw = DEAD["jaw"]
    P.ears = {s: v.copy() for s, v in DEAD["ears"].items()}
    P.tail = list(DEAD["tail"])
    P.feet = {leg: DEAD["feet"][leg] - _REST_FEET[leg] for leg in LEGS}
    P.flex = dict(DEAD["flex"]); P.top_rot = dict(DEAD["top_rot"]); P.femur = dict(DEAD["femur"])
    return P


# ============================================================================== Death
DEATH_N = 72
DEATH_HOLD = 62
D_STEPS = {"RF": (8, 15, V(-0.06, -0.03, 0.0)), "RH": (15, 22, V(-0.05, 0.02, 0.0))}   # stagger steps
D_DETACH = {"LF": (28, 38), "RF": (29, 39), "LH": (31, 41), "RH": (32, 42)}       # legs lose tension


def death_channels():
    dx, dy, dz = DEAD["body_off"]
    dp, dr, dyaw = DEAD["body_rot"]
    C = {}
    C["bx"] = Curve([(0, 0.0), (5, 0.006), (14, -0.02), (24, -0.045), (29, -0.07), (36, -0.16), (41, -0.26),
                     (46, dx - 0.006), (DEATH_HOLD, dx)])
    C["by"] = Curve([(0, 0.0), (4, 0.012), (12, 0.004), (24, -0.02), (34, -0.01), (44, dy), (DEATH_HOLD, dy)])
    # gravity: slow start of the topple, fastest just before the impact (f42), small bounce, settle
    C["bz"] = Curve([(0, 0.0), (4, -0.004), (12, -0.03), (20, -0.07), (28, -0.13), (33, -0.20), (38, -0.33),
                     (42, dz, -0.035, 0.0), (45, dz + 0.015), (49, dz - 0.002), (53, dz), (DEATH_HOLD, dz)])
    C["pitch"] = Curve([(0, 0.0), (4, -2.0), (12, 2.0), (22, 10.0), (29, 12.0), (38, 7.0), (44, dp),
                        (DEATH_HOLD, dp)])
    C["roll"] = Curve([(0, 0.0), (5, -1.0), (13, 4.0), (21, 8.0), (28, 15.0), (33, 30.0), (38, 57.0),
                       (42, dr - 1.0, 8.5, 0.5), (45, dr + 3.0), (50, dr - 0.8), (55, dr), (DEATH_HOLD, dr)])
    C["yaw"] = Curve([(0, 0.0), (14, -1.5), (30, -3.0), (44, dyaw), (DEATH_HOLD, dyaw)])
    # head/neck: flinch up (f3), sag with the stagger, drop with the buckle, lag while the body falls, whip
    # down to the ground just after the body lands (f45), bounce, settle
    C["neck"] = VCurve([(0, [0.0, 0.0, 0.0]), (3, [-3.0, -5.0, -5.0]), (12, [4.0, 6.0, 5.0]),
                        (24, [10.0, 12.0, 10.0]), (34, [2.0, 2.0, 0.0]), (40, [-2.0, -3.0, -4.0]),
                        (45, [10.0, 10.0, 9.0]), (49, [6.0, 7.0, 5.0]), (54, DEAD["neck"]),
                        (DEATH_HOLD, DEAD["neck"])])
    C["neck_yaw"] = VCurve([(0, [0.0, 0.0, 0.0]), (14, [1.0, 1.5, 2.0]), (30, [2.0, 3.0, 3.0]),
                            (40, [1.0, 1.0, 0.0]), (45, [-8.0, -10.0, -10.0]), (49, [-5.0, -7.0, -7.0]),
                            (54, DEAD["neck_yaw"]), (DEATH_HOLD, DEAD["neck_yaw"])])
    C["head"] = VCurve([(0, [0.0, 0.0, 0.0]), (3, [-6.0, 0.0, 0.0]), (12, [6.0, 2.0, -3.0]),
                        (24, [10.0, 3.0, -4.0]), (36, [-2.0, 0.0, 0.0]), (45, [12.0, -10.0, 0.0]),
                        (49, [6.0, -7.0, 0.0]), (54, list(DEAD["head"])), (DEATH_HOLD, list(DEAD["head"]))])
    C["jaw"] = Curve([(0, 0.0), (3, 7.0), (10, 3.0), (24, 4.0), (40, 2.0), (45, 9.0), (52, DEAD["jaw"]),
                      (DEATH_HOLD, DEAD["jaw"])])
    eL, eR = DEAD["ears"]["L"], DEAD["ears"]["R"]
    C["earL"] = VCurve([(0, [0.0, 0.0, 0.0]), (3, [-28.0, -6.0, 8.0]), (12, [-18.0, 10.0, 4.0]),
                        (26, [-12.0, 22.0, 0.0]), (38, [-4.0, 6.0, 0.0]), (44, [-6.0, 48.0, 0.0]),
                        (50, [-12.0, 28.0, 0.0]), (55, list(eL)), (DEATH_HOLD, list(eL))])
    C["earR"] = VCurve([(0, [0.0, 0.0, 0.0]), (3, [-26.0, -6.0, 8.0]), (12, [-16.0, 12.0, 4.0]),
                        (26, [-10.0, 24.0, 0.0]), (38, [-2.0, 4.0, 0.0]), (44, [-8.0, 44.0, 0.0]),
                        (50, [-12.0, 25.0, 0.0]), (55, list(eR)), (DEATH_HOLD, list(eR))])
    tail_dead = [c for seg in DEAD["tail"] for c in seg]
    clamp = [0.0, -12.0, 0.0, -6.0, 0.0, -2.0] + [0.0] * 8
    C["tail"] = VCurve([(0, [0.0] * 14), (4, clamp), (14, [2.0, -8.0, 3.0, -3.0, 3.0, 0.0] + [2.0, 0.0] * 4),
                        (30, [4.0, -4.0] + [2.0, 0.0] * 6), (44, tail_dead), (DEATH_HOLD, tail_dead)], size=14)
    # spine: shared DEAD values from the impact on
    C["spine"] = {b: VCurve([(0, [0.0, 0.0, 0.0]), (30, [0.0, 0.0, 0.0]), (46, list(v)), (DEATH_HOLD, list(v))])
                  for b, v in DEAD["spine"].items()}
    # leg tops (explicit, auto_top off): scapulae swing forward / femurs back as the legs go limp
    C["top"] = {leg: VCurve([(0, [0.0, 0.0, 0.0]), (30, [0.0, 0.0, 0.0]), (46, list(v)), (DEATH_HOLD, list(v))])
                for leg, v in DEAD["top_rot"].items()}
    C["femur"] = {leg: Curve([(0, 0.0), (8, 0.0), (22, 4.0), (32, 6.0), (46, v - 6.0), (50, v - 9.0),
                              (56, v), (DEATH_HOLD, v)]) for leg, v in DEAD["femur"].items()}
    return C


def death_fn(calf):
    """returns (N, pose fn, planted fn, basis hook)"""
    N = DEATH_N
    C = death_channels()
    dead = dead_pose(calf)
    dead_frames = leg_frames(calf, dead)
    # dead feet in each leg-parent's rest space (carried by the trunk while the leg is limp)
    local_dead = {leg: dead_frames[leg].inverted() @ DEAD["feet"][leg] for leg in LEGS}
    # last planted position (after the stagger step)
    planted_at = {leg: _REST_FEET[leg] + (D_STEPS[leg][2] if leg in D_STEPS else V()) for leg in LEGS}

    def detach(leg, f):
        a, b = D_DETACH[leg]
        return ramp(f, a, b, lambda t: smooth(t) ** 1.0)

    def base(f):
        P = Pose()
        P.auto_top = False
        P.body_off = V(C["bx"](f), C["by"](f), C["bz"](f))
        P.body_rot = V(C["pitch"](f), C["roll"](f), C["yaw"](f))
        for b, c in C["spine"].items():
            P.spine[b] = tuple(c(f))
        P.neck = C["neck"](f); P.neck_yaw = C["neck_yaw"](f)
        P.head = Vector(C["head"](f)); P.jaw = C["jaw"](f)
        P.ears = {"L": Vector(C["earL"](f)), "R": Vector(C["earR"](f))}
        t = C["tail"](f)
        P.tail = [(t[2 * i], t[2 * i + 1]) for i in range(7)]
        for leg, c in C["top"].items():
            P.top_rot[leg] = tuple(c(f))
        for leg, c in C["femur"].items():
            P.femur[leg] = c(f)
        return P

    def raw(f):
        P = base(f)
        frames = leg_frames(calf, P)
        for leg in LEGS:
            # planted (with the stagger step)
            w0 = _REST_FEET[leg].copy()
            fl0 = 0.0
            if leg in D_STEPS:
                a, b, off = D_STEPS[leg]
                if f >= b:
                    w0 = w0 + off
                elif f > a:
                    s = (f - a) / float(b - a)
                    h = math.sin(math.pi * s ** 0.85) ** 1.5
                    w0 = w0 + off * smoother(s) + V(0, 0, 0.045 * h)
                    fl0 = 50.0 * h * h
            w = detach(leg, f)
            carried = frames[leg] @ local_dead[leg]
            p = w0.lerp(carried, w)
            p.z = max(p.z, 0.036 if w > 0 else p.z)
            P.feet[leg] = p - _REST_FEET[leg]
            P.flex[leg] = fl0 * (1 - w) + DEAD["flex"][leg] * w
        # last stretch of the lower hind leg after the impact (reflex), then limp
        k = bump(f, 47, 51, 58)
        if k:
            P.feet["RH"] = P.feet["RH"] + V(0.0, 0.06, 0.0) * k
            P.flex["RH"] += 25.0 * k
        return P

    def fn(f):
        if f == 0:
            return stand_pose()
        if f >= DEATH_HOLD:
            return dead_pose(calf)
        return raw(f)

    def planted(leg, f):
        if leg in D_STEPS and D_STEPS[leg][0] < f < D_STEPS[leg][1]:
            return False
        return f <= D_DETACH[leg][0]

    def hook(f, P, B):
        """hooves of limp legs turn with the trunk (slerp by the detach weight)"""
        if f == 0:
            return
        pose = calf._last_pose
        Rb = body_rot_matrix(P).to_quaternion()
        for leg in LEGS:
            w = 1.0 if f >= DEATH_HOLD else detach(leg, f)
            if w <= 0.0:
                continue
            fb = LEGS[leg]["foot"]
            M = pose[fb]
            h = M.translation.copy()
            Rp = M.to_quaternion()                       # planted orientation (flex about world X)
            rest_q = calf.rest[fb].to_quaternion()
            flex_q = Rp @ rest_q.inverted()              # world-space delta = yaw + flex
            target = (Rb @ flex_q) @ rest_q
            q = Rp.slerp(target, w)
            Mn = Matrix.Translation(h) @ q.to_matrix().to_4x4()
            B[fb] = calf.basis_for(fb, pose, Mn)

    return N, fn, planted, hook, raw


# ============================================================================== Leap
LEAP_N = 42
# forward speed of the body (m/s), integrated to the root path
LEAP_V = [(0, 0.0), (4, 0.0), (9, 0.8), (14, 2.8), (19, 2.9), (24, 2.75), (27, 1.5), (31, 0.6), (36, 0.15),
          (42, 0.0)]
LEAP_FEET = {"LF": (9, 24), "RF": (10, 25), "LH": (14, 29), "RH": (15, 30)}     # lift-off, touch-down


def leap_root():
    v = Curve(LEAP_V)
    s = [0.0]
    sub = 20
    for f in range(LEAP_N):
        acc = 0.0
        for k in range(sub):
            acc += v(f + (k + 0.5) / sub) / FPS / sub
        s.append(s[-1] + acc)
    return s, v


def leap_fn(calf):
    N = LEAP_N
    s, vel = leap_root()
    D = s[-1]
    rootp = lambda f: V(0.0, -s[int(f)], 0.0)
    C = {}
    C["by"] = Curve([(0, 0.0), (5, 0.03), (10, 0.02), (15, 0.0), (N, 0.0)])
    # ballistic flight f14..24 (g = 9.81 m/s^2), apex ~ +15 cm
    g = 9.81 / FPS / FPS
    z0, z1, t0, t1 = 0.03, 0.0, 14.0, 24.0
    vz = (z1 - z0 + 0.5 * g * (t1 - t0) ** 2) / (t1 - t0)
    def flight(f):
        t = f - t0
        return z0 + vz * t - 0.5 * g * t * t
    C["bz_pre"] = Curve([(0, 0.0), (6, -0.045), (10, -0.02), (14, z0, vz)])
    C["bz_post"] = Curve([(24, z1, vz - g * 10, -0.01), (27, -0.06), (31, -0.05), (36, -0.012), (N, 0.0)])
    C["pitch"] = Curve([(0, 0.0), (6, -2.0), (10, -9.0), (14, -14.0), (19, -2.0), (23, 9.0), (25, 10.0),
                        (28, 6.0), (31, 1.0), (36, -0.8), (N, 0.0)])
    C["neck"] = VCurve([(0, [0.0] * 3), (6, [4.0, 4.0, 3.0]), (12, [-6.0, -8.0, -8.0]), (19, [-4.0, -6.0, -6.0]),
                        (25, [2.0, 2.0, 2.0]), (29, [7.0, 8.0, 6.0]), (35, [1.0, 1.0, 0.0]), (N, [0.0] * 3)])
    C["head"] = VCurve([(0, [0.0] * 3), (6, [4.0, 0.0, 0.0]), (13, [-10.0, 0.0, 0.0]), (20, [-6.0, 3.0, 4.0]),
                        (26, [2.0, 0.0, 0.0]), (30, [6.0, 0.0, 0.0]), (36, [-1.0, 0.0, 0.0]), (N, [0.0] * 3)])
    C["ears"] = VCurve([(0, [0.0] * 3), (6, [8.0, -4.0, 0.0]), (12, [-24.0, -6.0, 6.0]), (22, [-26.0, -2.0, 6.0]),
                        (27, [-8.0, 22.0, 0.0]), (32, [-4.0, 4.0, 0.0]), (38, [2.0, -2.0, 0.0]), (N, [0.0] * 3)])
    C["tail_lift"] = Curve([(0, 0.0), (8, 0.0), (15, 1.0), (24, 0.8), (32, 0.1), (N, 0.0)])
    C["kick_twist"] = Curve([(0, 0.0), (15, 0.0), (19, 1.0), (24, 0.3), (29, 0.0), (N, 0.0)])
    C["gain_f"] = Curve([(0, 1.0), (10, 1.0), (13, 0.6), (21, 0.6), (24, 1.0), (N, 1.0)])

    # swing paths (root-frame offsets from rest) with world-velocity 0 at lift-off / touch-down
    swing_keys = {
        "F": [(0.30, V(0.0, 0.10, 0.20), 90.0), (0.55, V(0.0, 0.02, 0.26), 115.0),
              (0.80, V(0.0, -0.22, 0.13), 20.0)],
        "H": [(0.25, V(0.0, 0.34, 0.14), 40.0), (0.45, V(0.0, 0.40, 0.24), 70.0), (0.62, V(0.0, 0.30, 0.22), 75.0),
              (0.85, V(0.0, -0.02, 0.10), 45.0)],
    }
    paths, flexes = {}, {}
    for leg, (a, b) in LEAP_FEET.items():
        kind = leg[1]
        vel_a = V(0.0, vel(a) / FPS, 0.0)
        vel_b = V(0.0, vel(b) / FPS, -0.012)
        rel_a = V(0.0, s[a], 0.0)
        rel_b = V(0.0, s[b] - D, 0.0)
        keys = [(a, rel_a, vel_a)]
        fkeys = [(a, 0.0)]
        for u, p, fl in swing_keys[kind]:
            fr = a + u * (b - a)
            keys.append((fr, p, None)); fkeys.append((fr, fl))
        keys.append((b, rel_b, vel_b)); fkeys.append((b - 1, 0.0 if kind == "F" else 5.0)); fkeys.append((b, 0.0))
        paths[leg] = hermite_path(keys)
        flexes[leg] = Curve(fkeys)

    def raw(f):
        P = Pose()
        P.root_pos = rootp(f)
        bz = C["bz_pre"](f) if f <= t0 else (flight(f) if f <= t1 else C["bz_post"](f))
        P.body_off = V(0.0, C["by"](f), bz)
        tw = C["kick_twist"](f)
        P.body_rot = V(C["pitch"](f), 0.0, 0.0)
        add_spine(P, "Back", yaw=6.0 * tw, roll=-5.0 * tw)
        add_spine(P, "Torso", yaw=-2.0 * tw)
        P.neck = C["neck"](f)
        P.head = Vector(C["head"](f))
        e = Vector(C["ears"](f))
        P.ears = {"L": e.copy(), "R": e.copy()}
        tl = C["tail_lift"](f)
        P.tail = [(0.0, 12.0 * tl * (1.0 - 0.13 * i)) for i in range(7)]
        add_tail_wave(P, 6.0 * bump(f, 12, 22, 34), (f - 12) / 12.0)
        P.top_gain = {"F": C["gain_f"](f), "H": 0.9}
        for leg, (a, b) in LEAP_FEET.items():
            if f <= a:
                P.feet_world[leg] = _REST_FEET[leg].copy()
                P.flex[leg] = 0.0
            elif f >= b:
                P.feet_world[leg] = _REST_FEET[leg] + V(0.0, -D, 0.0)
                P.flex[leg] = 0.0
            else:
                P.feet_world[leg] = P.root_pos + _REST_FEET[leg] + paths[leg](f)
                P.flex[leg] = flexes[leg](f)
        return P

    end = stand_pose(V(0.0, -D, 0.0))

    def fn(f):
        if f == 0:
            return stand_pose(V())
        if f == N:
            return end
        return raw(f)

    def planted(leg, f):
        a, b = LEAP_FEET[leg]
        return f <= a or f >= b

    return N, fn, planted, None, raw


# ============================================================================== HeadShake
SHAKE_N = 36


def headshake_fn(calf):
    N = SHAKE_N
    T = 7.0                              # shake period (frames): ~4.3 Hz
    f0 = 6.0                             # shake phase origin
    env = Curve([(0, 0.0), (5, 0.0), (9, 1.0), (17, 1.0), (27, 0.0), (N, 0.0)])
    dip = Curve([(0, 0.0), (4, 1.0), (10, 0.8), (22, 0.6), (30, 0.0), (N, 0.0)])

    def osc(f, lag=0.0):
        return env(f - lag) * math.sin(2 * math.pi * (f - lag - f0) / T)

    def raw(f):
        P = Pose()
        d = dip(f)
        P.neck = [3.0 * d, 4.0 * d, 3.0 * d]
        P.head = V(5.0 * d, 0.0, 0.0)
        # the shake starts at the withers/neck base and travels to the head (each link ~0.6 f later)
        add_spine(P, "Torso3", yaw=2.0 * osc(f, 0.0), roll=-2.0 * osc(f, 0.0))
        P.neck_yaw = [3.0 * osc(f, 0.3), 4.0 * osc(f, 0.8), 5.0 * osc(f, 1.3)]
        P.head = P.head + V(1.5 * osc(f + 1.75, 1.8), 9.0 * osc(f, 1.8), 30.0 * osc(f, 1.8))
        # ears: lag the head by ~1/4 period, flap wider (loose cartilage), flip up/down in anti-phase
        eo = osc(f, 3.6)
        eo2 = osc(f, 4.2)
        P.ears["L"] = V(-10.0 * env(f) - 14.0 * eo2, -38.0 * eo, 10.0 * eo2)
        P.ears["R"] = V(-10.0 * env(f) + 14.0 * eo2, 38.0 * eo, -10.0 * eo2)
        # jaw loose during the shake
        P.jaw = 3.0 * env(f - 1) * (0.5 + 0.5 * math.sin(2 * math.pi * (f - 2) / T))
        # settle: ear flick after the shake (left), little head re-centre overshoot
        k = flick(f, 26, 3, 8)
        P.ears["L"] = P.ears["L"] + V(-22.0 * k, -8.0 * k, 12.0 * k)
        # tail flick: one quick swish during the shake
        sw = bump(f, 8, 14, 28)
        add_tail_wave(P, 18.0 * sw, (f - 8) / 10.0, lift=4.0 * sw)
        return P

    def fn(f):
        if f == 0 or f == N:
            return stand_pose()
        return raw(f)

    return N, fn, (lambda leg, f: True), None, raw


# ============================================================================== build
def clip_fns(calf):
    """name -> (frames, pose fn, planted fn, basis hook, raw fn)"""
    _init(calf)
    return {"Death": death_fn(calf), "Leap": leap_fn(calf), "HeadShake": headshake_fn(calf)}


def build(calf, only=None):
    made = []
    for name, (N, fn, planted, hook, raw) in clip_fns(calf).items():
        if only and name not in only:
            continue
        make_clip_ex(calf, name, N, fn, loop=False, basis_hook=hook)
        made.append(name)
    return made


# ============================================================================== QA helpers
class MeshProbe:
    """Evaluates the skinned cage mesh Calf_LOD2 (fast): body = min z of non-hoof verts (orig_part != 2),
    hoof = min z of hoof verts (also per leg), head = min z of verts weighted > 0.5 to Head/Jaw. The hoof verts
    sit at z -1.3 cm at rest (the sole is slightly sunk), so hoof contact is judged relative to each leg's rest."""

    def __init__(self, calf, obj="Calf_LOD2"):
        self.calf = calf
        self.ob = bpy.data.objects[obj]
        me = self.ob.data
        nv = len(me.vertices)
        fp = np.zeros(len(me.polygons), np.int32)
        me.attributes["orig_part"].data.foreach_get("value", fp)
        self.hoof = np.zeros(nv, bool)
        for p in me.polygons:
            if fp[p.index] == 2:
                self.hoof[list(p.vertices)] = True
        gi = {g.index: g.name for g in self.ob.vertex_groups}
        hw = np.zeros(nv); tw = np.zeros(nv)
        for v in me.vertices:
            for g in v.groups:
                n = gi.get(g.group, "")
                if n in ("Head", "Jaw"):
                    hw[v.index] += g.weight
                if n.startswith("Tail"):
                    tw[v.index] += g.weight
        self.head = hw > 0.5
        self.tail = tw > 0.5
        self.mods = [m for m in self.ob.modifiers if m.type == "ARMATURE"]
        self.rest = None
        self.leg_mask = None

    def _coords(self):
        for m in self.mods:
            m.show_viewport = True
        dg = bpy.context.evaluated_depsgraph_get()
        oe = self.ob.evaluated_get(dg)
        n = len(oe.data.vertices)
        co = np.zeros(n * 3); oe.data.vertices.foreach_get("co", co); co = co.reshape(-1, 3)
        M = np.array(oe.matrix_world)
        co = co @ M[:3, :3].T + M[:3, 3]
        for m in self.mods:
            m.show_viewport = False
        return co

    def sample(self):
        co = self._coords()
        z = co[:, 2]
        body = ~self.hoof
        i = int(np.argmin(np.where(body, z, 1e9)))
        r = dict(body=float(z[i]), body_at=tuple(float(c) for c in co[i]), hoof=float(z[self.hoof].min()),
                 head=float(z[self.head].min()), tail=float(z[self.tail].min()))
        if self.leg_mask is not None:
            for leg, mk in self.leg_mask.items():
                r[leg] = float(z[mk].min())
        return r

    def rest_sample(self):
        if self.rest is None:
            arm = self.calf.arm
            if arm.animation_data:
                arm.animation_data.action = None
            for pb in arm.pose.bones:
                pb.matrix_basis.identity()
            co = self._coords()
            xl, yf = co[:, 0] > 0, co[:, 1] < 0.0
            self.leg_mask = {"LF": self.hoof & xl & yf, "RF": self.hoof & ~xl & yf,
                             "LH": self.hoof & xl & ~yf, "RH": self.hoof & ~xl & ~yf}
            self.rest = self.sample()
        return self.rest

    def check(self, act, frames, planted=None, step=1):
        rest = self.rest_sample()
        self.calf.use_action(act)
        rows = []
        for f in list(range(0, frames + 1, step)) + ([frames] if frames % step else []):
            self.calf.sc.frame_set(f)
            r = self.sample(); r["f"] = f
            rows.append(r)
        contact = (0.0, None, None)
        for leg in LEGS:
            for r in rows:
                if planted is None or planted(leg, r["f"]):
                    d = abs(r[leg] - rest[leg])
                    if d > contact[0]:
                        contact = (d, leg, r["f"])
        worst = min(rows, key=lambda r: r["body"])
        return dict(body_min=worst["body"], body_f=worst["f"], body_at=worst["body_at"],
                    hoof_min=min(r["hoof"] for r in rows), contact=contact,
                    head_min=min(r["head"] for r in rows), tail_min=min(r["tail"] for r in rows),
                    rest_hoof=rest["hoof"], rest_body=rest["body"], rows=rows)


def joint_bends(calf, act, frames):
    """signed carpus / hock bend (deg) per frame. Carpus + = knee forward (cannon folds back, correct);
    hock + = point of the hock behind the stifle-fetlock line (correct). Measured in the TRUNK frame
    (Torso2 for the fore legs, Back for the hind legs) so it stays meaningful when the calf lies on its side."""
    calf.use_action(act)
    res = {leg: [] for leg in LEGS}
    for f in range(frames + 1):
        calf.sc.frame_set(f)
        dg = bpy.context.evaluated_depsgraph_get(); ae = calf.arm.evaluated_get(dg)
        for leg, d in LEGS.items():
            par = LEG_PARENT[leg]
            R = (ae.pose.bones[par].matrix @ calf.rest[par].inverted()).to_3x3()
            fwd = (R @ Vector((0, -1, 0))).normalized()
            up, lo = ae.pose.bones[d["chain"][0]], ae.pose.bones[d["chain"][1]]
            a, j, b = up.head, up.tail, lo.tail
            ang = math.degrees((j - a).angle(b - j, 0.0))
            ab = (b - a)
            t = (j - a).dot(ab) / max(1e-9, ab.length_squared)
            off = (j - (a + ab * t)).dot(fwd)
            sgn = 1.0 if (off > 0) == leg.endswith("F") else -1.0
            res[leg].append(sgn * ang)
    return res


def smoothness(calf, act, frames):
    """largest per-frame 'pop': second difference of every bone's local rotation (deg/frame^2) and location
    (mm/frame^2); per-bone maxima for the body/neck/head chain"""
    calf.use_action(act)
    qs, ls = {}, {}
    for f in range(frames + 1):
        calf.sc.frame_set(f)
        for pb in calf.arm.pose.bones:
            q = pb.rotation_quaternion.copy()
            prev = qs.get(pb.name)
            if prev and prev[-1].dot(q) < 0:
                q.negate()
            qs.setdefault(pb.name, []).append(q)
            ls.setdefault(pb.name, []).append(pb.location.copy())
    worst_r, worst_l, speed = (0.0, None, None), (0.0, None, None), (0.0, None, None)
    per_bone = {}
    for n in qs:
        Q, L = qs[n], ls[n]
        for i in range(1, frames):
            qa, qb, qc = Q[i - 1], Q[i], Q[i + 1]
            d1 = qa.rotation_difference(qb); d2 = qb.rotation_difference(qc)
            acc = math.degrees(d1.rotation_difference(d2).angle)
            if acc > worst_r[0]: worst_r = (acc, n, i)
            if acc > per_bone.get(n, (0.0, 0))[0]: per_bone[n] = (acc, i)
            sp = math.degrees(d2.angle)
            if sp > speed[0]: speed = (sp, n, i)
            la_ = ((L[i - 1] - L[i]) - (L[i] - L[i + 1])).length * 1000
            if la_ > worst_l[0] and n != "Root": worst_l = (la_, n, i)
    top = sorted(((v[0], n, v[1]) for n, v in per_bone.items()), reverse=True)
    leg_bones = {b for l in LEGS for b in LEGS[l]["chain"] + (LEGS[l]["foot"], LEGS[l]["toe"], LEGS[l]["top"])}
    body_top = next((t for t in top if not t[1].startswith(("Ear", "Tail", "Jaw")) and t[1] not in leg_bones),
                    (0.0, None, None))
    return dict(rot_acc=worst_r, loc_acc=worst_l, speed=speed, body_rot_acc=body_top)


def bone_states(calf, act, frames_list):
    calf.use_action(act)
    out = []
    for f in frames_list:
        calf.sc.frame_set(f)
        dg = bpy.context.evaluated_depsgraph_get(); ae = calf.arm.evaluated_get(dg)
        root = ae.pose.bones["Root"].matrix.inverted()
        out.append({pb.name: (pb.location.copy(), pb.rotation_quaternion.copy(), (root @ pb.matrix).copy())
                    for pb in ae.pose.bones})
    return out


def state_diff(a, b, skip_root=True):
    """max local loc / rot difference of every bone (Root excluded: Leap ends 1.4 m ahead by design) and the
    max root-relative position difference of every bone head"""
    dl, da, dp = 0.0, 0.0, 0.0
    for n in a:
        if skip_root and n == "Root":
            continue
        if n in ("IKFrontLeg.L", "IKFrontLeg.R", "IKBackLeg.L", "IKBackLeg.R"):   # children of Root: compare root-relative
            dp = max(dp, (a[n][2].translation - b[n][2].translation).length)
            da = max(da, math.degrees(a[n][2].to_quaternion().rotation_difference(b[n][2].to_quaternion()).angle))
            continue
        dl = max(dl, (a[n][0] - b[n][0]).length)
        da = max(da, math.degrees(a[n][1].rotation_difference(b[n][1]).angle))
        dp = max(dp, (a[n][2].translation - b[n][2].translation).length)
    return dl, da, dp


def pose_values(P):
    v = list(P.root_pos) + [P.root_yaw] + list(P.body_off) + list(P.body_rot)
    for b in A.SPINE:
        v += list(P.spine.get(b, (0.0, 0.0, 0.0)))
    v += list(P.neck) + list(P.neck_yaw) + list(P.head) + [P.jaw] + list(P.ears["L"]) + list(P.ears["R"])
    for t in P.tail:
        v += list(t)
    for leg in LEGS:
        fw = P.feet_world.get(leg, P.root_pos + _REST_FEET[leg] + P.feet.get(leg, V()))
        v += list(fw) + [P.flex.get(leg, 0.0), P.glide.get(leg, 0.0), P.femur.get(leg, 0.0)]
        v += list(P.top_rot.get(leg, (0.0, 0.0, 0.0)))
    return v


def pose_delta(a, b):
    return max(abs(x - y) for x, y in zip(pose_values(a), pose_values(b)))


def reach_report(calf, N, fn, planted):
    """worst reach excess (m) of planted legs (>0 = the library clamps the foot toward the leg root)"""
    worst = (-1.0, None, None)
    for f in range(N + 1):
        ex = calf.reach_excess(fn(f))
        for leg, e in ex.items():
            if planted(leg, f) and e > worst[0]:
                worst = (e, leg, f)
    return worst


def run_qa(calf, names):
    fns = clip_fns(calf)
    probe = MeshProbe(calf)
    report = {}
    for n in names:
        N, fn, planted, hook, raw = fns[n]
        act = bpy.data.actions[n]
        q = calf.qa(act, N, planted, label=n)
        m = probe.check(act, N, planted, step=1)
        jb = joint_bends(calf, act, N)
        sm = smoothness(calf, act, N)
        rr = reach_report(calf, N, fn, planted)
        car = [min(min(jb["LF"]), min(jb["RF"])), max(max(jb["LF"]), max(jb["RF"]))]
        hoc = [min(min(jb["LH"]), min(jb["RH"])), max(max(jb["LH"]), max(jb["RH"]))]
        report[n] = dict(q, mesh=m, carpus=car, hock=hoc, smooth=sm, reach=rr)
        c = m["contact"]
        print(f"MESH {n}: non-hoof min z {m['body_min']*100:.2f} cm (f{m['body_f']} at "
              f"{tuple(round(x, 2) for x in m['body_at'])}, rest {m['rest_body']*100:.2f}) | hoof min z "
              f"{m['hoof_min']*100:.2f} cm (rest {m['rest_hoof']*100:.2f}) | planted hoof off its rest height <= "
              f"{c[0]*1000:.1f} mm ({c[1]} f{c[2]}) | head min z {m['head_min']*100:.2f} cm | tail min z "
              f"{m['tail_min']*100:.2f} cm")
        print(f"REACH {n}: worst planted-leg reach excess {rr[0]*1000:.1f} mm ({rr[1]} f{rr[2]}) (>0 = clamped)")
        print(f"SMOOTH {n}: max rot 2nd diff {sm['rot_acc'][0]:.2f} deg/f^2 ({sm['rot_acc'][1]} f{sm['rot_acc'][2]}) | "
              f"max loc 2nd diff {sm['loc_acc'][0]:.2f} mm/f^2 ({sm['loc_acc'][1]} f{sm['loc_acc'][2]}) | "
              f"peak speed {sm['speed'][0]:.2f} deg/f ({sm['speed'][1]} f{sm['speed'][2]}) | body/neck/head max "
              f"rot 2nd diff {sm['body_rot_acc'][0]:.2f} ({sm['body_rot_acc'][1]} f{sm['body_rot_acc'][2]})")
        print(f"JOINTS {n}: carpus bend {car[0]:.1f}..{car[1]:.1f} deg | hock bend {hoc[0]:.1f}..{hoc[1]:.1f} deg "
              f"(+ = anatomical direction)")
        r0, r1 = pose_delta(raw(0), fn(0)), pose_delta(raw(N), fn(N))
        print(f"RESIDUAL {n}: raw curves vs shared pose at f0 {r0:.2e}, at f{N} {r1:.2e} (deg / m)")
    # boundaries: every clip starts at Pose(); Leap / HeadShake end at Pose() (root-relative)
    ref = None
    for n in names:
        act = bpy.data.actions[n]; N = int(act.frame_range[1])
        st = bone_states(calf, act, [0, N])
        if ref is None:
            ref = st[0]
        dl, da, dp = state_diff(st[0], ref)
        print(f"BOUNDARY {n} start vs Pose(): max loc {dl*1000:.4f} mm, rot {da:.4f} deg, root-rel pos {dp*1000:.4f} mm")
        if n != "Death":
            dl, da, dp = state_diff(st[1], ref)
            print(f"BOUNDARY {n} end vs Pose(): max loc {dl*1000:.4f} mm, rot {da:.4f} deg, root-rel pos {dp*1000:.4f} mm")
        if n == "Leap":
            calf.use_action(act); calf.sc.frame_set(N)
            print(f"ROOT {n}: end root position {tuple(round(x, 4) for x in calf.arm.pose.bones['Root'].location)} "
                  f"(local), travelled {leap_root()[0][-1]:.3f} m")
        if n == "Death":
            # hold: last frames identical
            s2 = bone_states(calf, act, [DEATH_HOLD, N])
            dl, da, dp = state_diff(s2[0], s2[1])
            print(f"HOLD {n}: f{DEATH_HOLD} vs f{N}: loc {dl*1000:.4f} mm, rot {da:.4f} deg")
    return report


# ============================================================================== standalone
RENDER = {  # clip -> (strip frames a:b:step, sides)
    "Death": ("0:72:4", ("threequarter", "left")),
    "Leap": ("0:42:3", ("left",)),
    "HeadShake": ("0:36:2", ("front",)),
}

if __name__ == "__main__":
    SCR = "/tmp/claude-0/-home-user-Game-asset/f3fb310f-97d7-5da4-a5e8-b863f47eb685/scratchpad/actions"
    if not os.path.isdir(os.path.dirname(SCR)):
        SCR = os.path.join(ROOT, "build", "clip_tests", "actions")
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src", default=os.path.join(ROOT, "build", "stage_b.blend"))
    ap.add_argument("--out-dir", default=SCR)
    ap.add_argument("--no-render", action="store_true")
    ap.add_argument("--no-gif", action="store_true")
    ap.add_argument("--only", default="")
    ap.add_argument("--res", type=int, default=320)
    ap.add_argument("--samples", type=int, default=6)
    ap.add_argument("--sides", default="", help="override render sides (comma list)")
    ap.add_argument("--frames", default="", help="override strip frames a:b:step")
    ap.add_argument("--gif-step", type=int, default=2)
    a = ap.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:])
    os.makedirs(a.out_dir, exist_ok=True)
    only = [s for s in a.only.split(",") if s] or None
    calf = A.Calf(a.src)
    names = build(calf, only)
    run_qa(calf, names)
    out = os.path.join(a.out_dir, "test.blend")
    calf.save(out)
    print("saved", out)
    if not a.no_render:
        def render(n, frames, sd, prefix):
            subprocess.run([sys.executable, os.path.join(TOOLS, "render_clip.py"), out, n, prefix, "--frames", frames,
                            "--res", str(a.res), "--samples", str(a.samples), "--side", sd], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for n in names:
            frames, sides = RENDER[n]
            if a.frames:
                frames = a.frames
            N = int(bpy.data.actions[n].frame_range[1])
            for sd in (a.sides.split(",") if a.sides else sides):
                render(n, frames, sd, os.path.join(a.out_dir, f"{n}_{sd}"))
                print("rendered", os.path.join(a.out_dir, f"{n}_{sd}.png"))
                if not a.no_gif and a.gif_step:
                    render(n, f"0:{N}:{a.gif_step}", sd, os.path.join(a.out_dir, f"{n}_{sd}_anim"))
                    print("rendered", os.path.join(a.out_dir, f"{n}_{sd}_anim.gif"))
