"""Clip family "actions": Death, Leap, HeadShake for the calf rig.

    build(calf) -> ["Death", "Leap", "HeadShake"]

Clips (30 fps)
  Death      70 f, ROOT MOTION ~0.79 m to the calf's right (armature -X; the Root ends under the carcass).
             Pose() -> flinch (f0-4: head up, ears back, jaw open, tail clamps) -> stagger: right fore (f3-9) and
             right hind (f5-11) step out, the body sways right -> from f11 it topples over the RIGHT hooves: a rigid
             pendulum about the right hooves' lateral sole edges (gravity, time-scaled to land at f33). The right
             hooves never slide: they tip onto their lateral wall about that edge. The left legs unload at f11/12,
             lift with the trunk (keeping their loaded shape) and go limp -> the right side of the trunk hits the
             ground at f33 (bounce, settle onto the side, roll back), the head whips down and hits at f36, the ears
             flop, the limp upper legs flop onto the ground in front of the lower legs (f25-40), the upper hind leg
             twitches (f40-53) -> dead_pose() held exactly f60-70. GiM reference 26.8-27.5 s: falls onto its right
             side with fairly straight legs, the hooves stay, the body goes over and away from them, head last.
  Leap       40 f, root motion 1.447 m along -Y. Crouch with the weight back -> fore feet lift (f7/8) and tuck ->
             hind push-off; the hind hooves roll onto the toe over the last 3 planted frames (toe-off) and leave at
             f13/14 -> ballistic flight (COG exactly -g until the fore contact), hind legs trail and kick back/up
             (f15-19) then swing through -> fore feet land at f24/25 (graded, nearly vertical final approach, 8 cm
             short of their final spot), fore legs give <= ~30 mm, the head keeps sinking 2-3 frames (neck lag) ->
             hind feet land f26/27 (the rear keeps falling until then) -> absorb -> the fore feet take a small
             balancing step into the final stance (LF f31-36, RF f33-38) -> Pose() at the new root.
             Landing body height / pitch come from front (elbow line) and rear (hip line) height keys (LEAP_HF /
             LEAP_HR) that were optimised for smooth head / pitch / hip motion under those physical constraints.
  HeadShake  36 f. Fly-shaking: head dips, then 2.5 fast (7-frame period, ~4.3 Hz) head roll/yaw oscillations
             that start at the withers and neck base (overlapping action), ears flap with ~1/4-period lag and
             more amplitude than the head, tail flicks, settle with an ear flick. Pose() -> Pose(), legs planted.

Shared constant poses (module level): stand_pose() (== Pose(); start of all three, end of Leap / HeadShake
root-relative) and dead_pose(calf, root=None) (end of Death, root-relative; the Death clip holds it with
root = the drifted Root). The pose functions return them verbatim on the boundary frames; QA prints the residual
of the raw curves there. The Death hoof bones are oriented by the clip's hook / post-bake pass (lower hooves:
tipped on their lateral wall; limp upper hooves: follow the baked cannon + a relaxed flex), so a later Dead_Idle
clip should reuse death_fn's hook / post functions with dead_pose().

Conventions verified on this rig (FK probes + renders):
  Pose.flex + = toe back (fetlock flexion; reduces the dorsal fetlock angle); Pose.ears x + = tip forward, y + =
  tip down (droop), z = twist; Pose.head roll + = left ear down; body_rot roll + = right side down; spine roll + =
  LEFT side down; tail side + = tail tip toward the calf's RIGHT (-X) (= down when lying on the right side), tail
  lift + = tip swings back (+Y). Pose() lifts the straight front hooves ~2 mm (reach clamp), so standing clips never
  raise the elbows (no body z > 0 / no roll / no nose-up pitch while all four feet are planted).

Library extensions (kept here, anim_lib.py is shared): make_clip_ex() = Calf.make_clip without the reach pass,
plus basis_hook (re-orient hoof bones about their head before keying; the leg IK targets the head only) and
post_bake (rewrite hoof keys from the baked cannon). Death is built DEATH_PASSES = 3 times: the limp hooves'
orientation (known only after the IK bake) feeds their ground clamp in the next pass. Hoof geometry for pivots and
clamps comes from Calf_LOD0 hoof verts (_HOOF_PTS, lateral sole edge _HOOF_EDGE, toe tip _HOOF_TOE).

QA (run_qa, standalone): calf.qa; Calf_LOD2 ground check (non-hoof / hoof / head / tail min z); CONTACT = hoof
skating on LOD0 (xy motion of hoof verts within 8 mm of the ground in consecutive frames, so rolling on an edge is
allowed and sliding is not); OVERLAP = LOD2 self-intersections between limbs / tail and bone-capsule clearance
(radii from LOD0); REACH (planted legs; Death also every leg while resting); SMOOTH (top per-bone pops); JOINTS
(carpus / hock bend sign); FETLOCK (signed dorsal angle, max while loaded, and the out-of-hinge-plane angle);
RESIDUAL / BOUNDARY / HOLD / ROOT.

Standalone: python3 tools/clips/actions.py [--in build/stage_b.blend] [--out-dir DIR] [--no-render] [--only a,b]
                                           [--res 320] [--samples 6] [--gif-step 2]
  builds the clips, prints the QA, saves DIR/test.blend and renders filmstrips (DIR/<clip>_<side>.png) + GIFs
  (DIR/<clip>_<side>_anim.gif).
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
    """quick twitch: eased rise over `up` frames (no velocity jump at the start), slower settle over `down`"""
    t = f - f0
    if t <= 0 or t >= up + down:
        return 0.0
    if t < up:
        return smooth(t / up)
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


def make_clip_ex(calf, name, frames, pose_fn, loop=False, basis_hook=None, post_bake=None):
    """anim_lib.Calf.make_clip (no reach pass) with two extension points:
    basis_hook(frame, Pose, basis dict): called after pose_to_basis, before keying. Used to re-orient hoof bones
      about their head: the leg IK targets the head only, so the solve is unaffected.
    post_bake(rows) -> {bone: [(loc, quat) per frame]}: called after the IK bake with, per frame, the evaluated
      armature-space matrices of Root, the leg chain bones and the hoof bones; the returned curves replace those
      bones' keys. Used to orient limp hooves from the baked cannon (hinge plane), which is only known after IK."""
    act = calf.new_action(name)
    poses = [pose_fn(f) for f in range(frames + 1)]
    chain_bones = [n for d in LEGS.values() for n in d["chain"]]
    feet = [d["foot"] for d in LEGS.values()]
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
    rows = []
    for f in range(frames + 1):
        calf.sc.frame_set(f)
        dg = bpy.context.evaluated_depsgraph_get()
        ae = calf.arm.evaluated_get(dg)
        for n in chain_bones:
            par = ae.pose.bones[calf.par[n]].matrix
            local = (par @ calf.rel(n)).inverted() @ ae.pose.bones[n].matrix
            baked[n].append((Vector((0, 0, 0)), local.to_quaternion()))
        if post_bake:
            rows.append({n: ae.pose.bones[n].matrix.copy() for n in ["Root"] + chain_bones + feet})
    calf.remove_ik()
    calf.write_curves(act, baked)
    if post_bake:
        calf.write_curves(act, post_bake(rows))
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
_HOOF_PTS = {}       # leg -> (n, 3) array: Calf_LOD0 hoof verts (weight >= 0.5 on the hoof bones), rel. rest fetlock
_HOOF_EDGE = {}      # leg -> lateral sole edge (rest, rel. fetlock): a hoof that tips over sideways pivots on it
_HOOF_TOE = {}       # leg -> toe tip on the sole (rest, rel. fetlock): a hoof rolling onto its toe (toe-off) pivots on it


def _init(calf):
    for leg, d in LEGS.items():
        _REST_FEET[leg] = calf.rest_head(d["foot"])
    ob = bpy.data.objects["Calf_LOD0"]
    me = ob.data
    fp = np.zeros(len(me.polygons), np.int32)
    me.attributes["orig_part"].data.foreach_get("value", fp)
    idx = sorted({v for p in me.polygons if fp[p.index] == 2 for v in p.vertices})
    gi = {g.index: g.name for g in ob.vertex_groups}
    Mw = ob.matrix_world
    for leg, d in LEGS.items():
        hb = (d["foot"], d["toe"])
        pts = []
        for i in idx:
            v = me.vertices[i]
            if sum(g.weight for g in v.groups if gi.get(g.group) in hb) >= 0.5:
                pts.append(tuple(Mw @ v.co - _REST_FEET[leg]))
        P = np.array(pts)
        _HOOF_PTS[leg] = P
        lat = 1.0 if leg[0] == "L" else -1.0
        zmin = P[:, 2].min()
        bot = P[P[:, 2] < zmin + 0.004]
        edge = bot[lat * bot[:, 0] > (lat * bot[:, 0]).max() - 0.004]
        _HOOF_EDGE[leg] = Vector((float(edge[:, 0].mean()), float(edge[:, 1].mean()), float(zmin)))
        toe = bot[bot[:, 1] < bot[:, 1].min() + 0.004]
        _HOOF_TOE[leg] = Vector((float(toe[:, 0].mean()), float(toe[:, 1].mean()), float(zmin)))


def toe_pivot_fetlock(calf, leg, flex, W):
    """fetlock position that keeps the toe tip at world point W while the hoof flexes by `flex` (anim_lib: the
    hoof bone turns by flex about the fetlock, the toe bone by another 0.35 * flex about the coronet)"""
    d = LEGS[leg]
    cor = calf.rest_head(d["toe"]) - _REST_FEET[leg]
    R1 = Matrix.Rotation(math.radians(flex), 3, "X")
    R2 = Matrix.Rotation(math.radians(1.35 * flex), 3, "X")
    return W - (R1 @ cor + R2 @ (_HOOF_TOE[leg] - cor))


def hoof_floor(leg, q):
    """lowest fetlock height that keeps the hoof (rotated by q about the fetlock) no lower than it sits at rest"""
    R = np.array(q.to_matrix())
    P = _HOOF_PTS[leg]
    return _REST_FEET[leg].z + float(P[:, 2].min()) - float((P @ R[2]).min())


def roll_q(deg):
    """world rotation 'right side down' by deg (anim_lib body roll convention)"""
    return Matrix.Rotation(-math.radians(deg), 3, "Y").to_quaternion()


def rot_rsd(v, deg):
    """rotate a vector right side down by deg about the Y axis (x, z plane)"""
    return roll_q(deg) @ v


# ============================================================================== Death
# The calf staggers to the right and topples over its right hooves onto its right side (GiM reference 26.8-27.5 s:
# the hooves stay where they are, the legs stay fairly straight, the body goes over and away from them, the head
# hits last). Physically: the right hooves are the pivot of the fall. They never slide; they tip onto their lateral
# wall (pivot on the lateral sole edge) as the legs go over. The left (up-hill) legs unload and lift with the trunk
# as soon as the topple starts, go limp and flop onto the ground in front of the lower legs at the impact.
# The Root follows the body sideways (root motion, ~0.7 m to the calf's right) so the gameplay capsule ends under
# the carcass.
DEATH_N = 70
DEATH_HOLD = 60                      # dead_pose() held exactly f60-70
D_T0 = 11                            # the body starts to go over the right hooves (topple = rotation about them)
D_IMP = 33                           # the right side of the trunk hits the ground
D_STEPS = {"RF": (3, 9, V(-0.03, -0.07, 0.0)), "RH": (5, 11, V(-0.02, 0.05, 0.0))}   # stagger steps (lift, land, offset)
D_LIFT = {"LF": (11, 15), "LH": (12, 16)}       # up-hill legs unload and lift with the trunk (ramp to limp)
D_RELAX = {"LF": (25, 39), "LH": (26, 40)}      # limp upper legs flop from their carried standing shape into the dead pose
D_PRE = dict(bx=-0.05, bz=-0.04, roll=5.0, rate=1.5)   # body state at D_T0 (roll deg, roll rate deg/f)
D_ROLL_IMP = 87.0                    # roll at the impact frame (then +4 deg settle onto the side, roll-back, 88)
D_SQUAT = 0.03                       # legs give by this much (along the body's down axis) during the topple
D_REFLEX = (40, 45, 53)              # post-mortem stretch of the upper hind leg (in the air, above the lower leg)
D_FLEX = {"LF": 25.0, "LH": 20.0}    # relaxed fetlock flex of the limp upper legs (dead pose)

# dead pose (body / head / ears were tuned for the ground contact: lower ear folded back, right cheek on the ground)
DEAD = dict(
    body_dy=0.02, body_dz=-0.50,
    body_rot=V(2.0, 88.0, -4.0),
    spine={"Back": (0.0, 3.0, 0.0), "Torso": (0.0, 2.0, 0.0), "Torso3": (4.0, -3.0, 0.0)},
    neck=[8.0, 8.0, 6.0],
    neck_yaw=[-2.0, -3.0, -3.0],
    head=V(8.0, -4.0, 0.0),
    jaw=6.0,
    ears={"L": V(-75.0, -20.0, 0.0), "R": V(-50.0, -40.0, 0.0)},
    # tail lies on the ground behind the rump, clear of the lower hind leg (lift = away from the thighs)
    tail=[(27.0, 10.0), (22.5, 11.0), (15.5, 6.0), (10.0, -0.5), (7.0, -5.5), (5.0, -8.0), (4.0, -8.0)],
    # upper (left) hooves relative to the lower (right) ones: in front of them, on the ground (no leg crossing)
    upper={"LF": V(-0.14, -0.16, 0.03), "LH": V(0.04, -0.13, 0.02)},
    top_rot={"LF": (-12.0, 0.0, 0.0), "RF": (-6.0, 0.0, 0.0)},
    glide={"LF": 0.04, "RF": 0.0},
    femur={"LH": -8.0, "RH": -6.0},
)


def _vkeys(keys):
    return VCurve([(f, list(v)) for f, v in keys])


class DeathModel:
    """World-space model of the Death clip (root at the origin at f0; the Root drifts with the body)."""

    def __init__(self, calf):
        self.calf = calf
        self.cog = calf.cog.copy()
        self.plant = {leg: _REST_FEET[leg] + (D_STEPS[leg][2] if leg in D_STEPS else V()) for leg in LEGS}
        e = [self.plant[l] + _HOOF_EDGE[l] for l in ("RF", "RH")]
        self.E = (e[0] + e[1]) * 0.5                         # pivot line of the topple (along Y)
        self.q_est = {}                                      # (f, leg) -> cannon-following hoof rotation used now
        self.q_new = {}                                      # ... measured by the last bake (next pass uses it)
        self._topple()
        self._channels()
        self._dead()

    # ---------------------------------------------------------------- body path
    def _topple(self):
        """roll angle over the topple: rigid pendulum about the right hooves' sole edges (gravity), started at D_T0
        with the stagger's roll rate, time-scaled to hit D_ROLL_IMP exactly at D_IMP"""
        G0 = self.cog + V(D_PRE["bx"], 0.0, D_PRE["bz"])
        self.G_t0 = G0
        r = (G0 - self.E).xz.length
        K = 9.81 * r / (r * r + 0.15 ** 2) / FPS / FPS       # rad/f^2 (k = 0.15 m radius of gyration about the COG)
        th, w = 0.0, math.radians(D_PRE["rate"])
        sub, t, table = 200, 0.0, [(0.0, 0.0, w)]
        span = math.radians(D_ROLL_IMP - D_PRE["roll"])
        while th < span:
            for _ in range(sub):
                w += K * math.sin(th) / sub
                th += w / sub
            t += 1.0
            table.append((t, th, w))
        # continuous time of arrival, then scale so it lands exactly on D_IMP
        (t0_, th0, _), (_, th1, _) = table[-2], table[-1]
        tstar = t0_ + (span - th0) / (th1 - th0)
        self.tscale = tstar / (D_IMP - D_T0)
        self.ode = table

        def roll_at(f):
            tt = (f - D_T0) * self.tscale
            i = min(int(tt), len(table) - 2)
            a, b = table[i], table[i + 1]
            u = tt - a[0]
            # cubic Hermite on (theta, omega) between integer ODE samples
            h00, h10, h01, h11 = 2*u**3 - 3*u**2 + 1, u**3 - 2*u**2 + u, -2*u**3 + 3*u**2, u**3 - u**2
            th_ = h00 * a[1] + h10 * a[2] + h01 * b[1] + h11 * b[2]
            return D_PRE["roll"] + math.degrees(th_)
        self.roll_topple = roll_at
        self.rate0 = D_PRE["rate"] * self.tscale                # deg/f at D_T0
        self.rate_imp = (roll_at(D_IMP) - roll_at(D_IMP - 0.01)) / 0.01   # deg/f arriving at the impact

    def G_topple(self, f, zc=True):
        """COG (world) during the topple: rotation about the pivot line + leg give (squat) + z blend to the dead height"""
        th = self.roll_topple(f)
        d = D_SQUAT * clamp01((f - D_T0) / float(D_IMP - D_T0))
        rel = self.G_t0 - self.E
        rel = rot_rsd(V(rel.x, 0.0, rel.z), th - D_PRE["roll"])
        G = self.E + rel + rot_rsd(V(0.0, 0.0, -d), th)
        G.y = self.cog.y
        if zc:
            G.z += (self.z_dead - self._z_imp_raw) * smooth((f - (D_IMP - 8)) / 8.0)
        return G

    def _channels(self):
        self.z_dead = self.cog.z + DEAD["body_dz"]
        self._z_imp_raw = self.G_topple(D_IMP, zc=False).z
        Gi = self.G_topple(D_IMP)
        Gm = self.G_topple(D_IMP - 0.01)
        v_imp = (Gi - Gm) / 0.01
        self.x_dead = Gi.x + 1.2 * v_imp.x
        Ga, Gb = self.G_topple(D_T0), self.G_topple(D_T0 + 0.01)
        v0 = (Gb - Ga) / 0.01
        H, T0, IMP = DEATH_HOLD, D_T0, D_IMP
        C = {}
        cx, cz = self.cog.x, self.cog.z
        # before the topple: flinch, sway right with the stagger steps; hands over to the pivot model at T0 with
        # matching position and velocity
        C["pre_x"] = Curve([(0, cx), (3, cx + 0.002), (7, cx - 0.012), (T0, Ga.x, v0.x)])
        C["pre_z"] = Curve([(0, cz), (4, cz - 0.012), (8, cz - 0.03), (T0, Ga.z, v0.z)])
        C["pre_roll"] = Curve([(0, 0.0), (3, 0.0), (7, 1.2), (T0, D_PRE["roll"], self.rate0)])
        # after the impact: small bounce, settle onto the side, roll back, rest
        zd = self.z_dead
        C["post_x"] = Curve([(IMP, Gi.x, v_imp.x), (IMP + 3, self.x_dead), (H, self.x_dead)])
        C["post_z"] = Curve([(IMP, zd, v_imp.z, 0.0), (IMP + 3, zd + 0.015), (IMP + 7, zd - 0.002), (IMP + 11, zd),
                             (H, zd)])
        dr = DEAD["body_rot"].y
        C["post_roll"] = Curve([(IMP, D_ROLL_IMP, self.rate_imp, 0.8), (IMP + 3, dr + 3.0), (IMP + 8, dr - 0.8),
                                (IMP + 14, dr), (H, dr)])
        dy = DEAD["body_dy"]
        C["y"] = Curve([(0, 0.0), (4, 0.004), (T0, 0.0), (IMP, 0.012), (IMP + 6, dy), (H, dy)])
        dp, dyaw = DEAD["body_rot"].x, DEAD["body_rot"].z
        C["pitch"] = Curve([(0, 0.0), (4, 0.5), (T0, 1.2), (IMP, 1.0), (IMP + 6, dp), (H, dp)])
        C["yaw"] = Curve([(0, 0.0), (T0, -1.0), (IMP, -3.0), (IMP + 6, dyaw), (H, dyaw)])
        C["root_x"] = lambda f: self.x_dead * smoother((f - (T0 - 2)) / float(IMP + 8 - (T0 - 2)))
        # head / neck: flinch up (f3), sags with the stagger, stays up while the body goes over (lags), whips down
        # after the body and hits the ground at IMP+3, bounce, settle
        C["neck"] = _vkeys([(0, [0.0, 0.0, 0.0]), (3, [-3.0, -5.0, -5.0]), (8, [2.0, 3.0, 2.0]), (13, [0.0, -2.0, -3.0]),
                            (24, [-3.0, -5.0, -6.0]), (IMP - 1, [-4.0, -6.0, -7.0]), (IMP + 3, [9.0, 9.0, 7.0]),
                            (IMP + 7, [6.0, 6.0, 5.0]), (IMP + 13, DEAD["neck"]), (H, DEAD["neck"])])
        C["neck_yaw"] = _vkeys([(0, [0.0, 0.0, 0.0]), (8, [1.0, 1.5, 2.0]), (22, [2.0, 3.0, 3.0]),
                                (IMP - 1, [1.0, 1.0, 0.0]), (IMP + 3, [-2.5, -3.5, -3.5]), (IMP + 7, [-1.0, -1.5, -1.5]),
                                (IMP + 13, DEAD["neck_yaw"]), (H, DEAD["neck_yaw"])])
        C["head"] = _vkeys([(0, [0.0, 0.0, 0.0]), (3, [-6.0, 0.0, 0.0]), (8, [4.0, 2.0, -3.0]), (13, [2.0, 3.0, -4.0]),
                            (IMP - 5, [-4.0, 0.0, 0.0]), (IMP + 3, [9.0, -5.0, 0.0]), (IMP + 7, [6.0, -2.0, 0.0]),
                            (IMP + 13, list(DEAD["head"])), (H, list(DEAD["head"]))])
        C["jaw"] = Curve([(0, 0.0), (3, 7.0), (8, 3.0), (13, 4.0), (IMP - 2, 2.0), (IMP + 3, 9.0), (IMP + 10, DEAD["jaw"]),
                          (H, DEAD["jaw"])])
        eL, eR = DEAD["ears"]["L"], DEAD["ears"]["R"]
        C["earL"] = _vkeys([(0, [0.0, 0.0, 0.0]), (3, [-28.0, -6.0, 8.0]), (8, [-18.0, 10.0, 4.0]), (16, [-12.0, 22.0, 0.0]),
                            (IMP - 4, [-20.0, 0.0, 0.0]), (IMP + 2, [-50.0, 10.0, 0.0]), (IMP + 7, [-66.0, -30.0, 0.0]),
                            (IMP + 13, list(eL)), (H, list(eL))])
        C["earR"] = _vkeys([(0, [0.0, 0.0, 0.0]), (3, [-26.0, -6.0, 8.0]), (8, [-16.0, 12.0, 4.0]), (16, [-10.0, 24.0, 0.0]),
                            (IMP - 4, [-22.0, -8.0, 0.0]), (IMP + 1, [-45.0, -35.0, 0.0]), (IMP + 6, [-56.0, -32.0, 0.0]),
                            (IMP + 13, list(eR)), (H, list(eR))])
        tail_dead = [c for seg in DEAD["tail"] for c in seg]
        clamp = [0.0, -12.0, 0.0, -6.0, 0.0, -2.0] + [0.0] * 8
        C["tail"] = VCurve([(0, [0.0] * 14), (4, clamp), (10, [2.0, -8.0, 3.0, -3.0, 3.0, 0.0] + [2.0, 0.0] * 4),
                            (22, [4.0, -4.0] + [2.0, 0.0] * 6), (IMP + 2, tail_dead), (IMP + 9, tail_dead),
                            (H, tail_dead)], size=14)
        C["spine"] = {b: _vkeys([(0, [0.0] * 3), (T0 + 8, [0.0] * 3), (IMP + 6, list(v)), (H, list(v))])
                      for b, v in DEAD["spine"].items()}
        C["top"] = {leg: _vkeys([(0, [0.0] * 3), (T0 + 8, [0.0] * 3), (IMP + 6, list(v)), (H, list(v))])
                    for leg, v in DEAD["top_rot"].items()}
        C["glide"] = {leg: Curve([(0, 0.0), (T0 + 8, 0.0), (IMP + 6, v), (H, v)]) for leg, v in DEAD["glide"].items()}
        C["femur"] = {leg: Curve([(0, 0.0), (T0, 0.0), (IMP + 6, v), (H, v)]) for leg, v in DEAD["femur"].items()}
        self.C = C

    # ---------------------------------------------------------------- pose pieces
    def body(self, f):
        """world COG, (pitch, roll, yaw), root x"""
        C = self.C
        if f <= D_T0:
            G = V(C["pre_x"](f), self.cog.y, C["pre_z"](f)); roll = C["pre_roll"](f)
        elif f <= D_IMP:
            G = self.G_topple(f); roll = self.roll_topple(f)
        else:
            G = V(C["post_x"](f), self.cog.y, C["post_z"](f)); roll = C["post_roll"](f)
        G.y += C["y"](f)
        return G, V(C["pitch"](f), roll, C["yaw"](f)), C["root_x"](f)

    def base(self, f):
        """Pose without the feet (root-relative body)"""
        C = self.C
        G, rot, rx = self.body(f)
        P = Pose()
        P.auto_top = False
        P.root_pos = V(rx, 0.0, 0.0)
        P.body_off = G - self.cog - P.root_pos
        P.body_rot = rot
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
        for leg, c in C["glide"].items():
            P.glide[leg] = c(f)
        return P

    def hoof_roll(self, f):
        """how far the right hooves have tipped onto their lateral wall (deg)"""
        if f <= D_T0:
            return 0.0
        th = self.roll_topple(min(f, D_IMP)) if f <= D_IMP else D_ROLL_IMP
        return th - D_PRE["roll"]

    def lower_foot(self, leg, f):
        """right (down-hill) legs: stagger step, then planted; the hoof tips about its lateral sole edge -> (fetlock, q)"""
        a, b, off = D_STEPS[leg]
        rest = _REST_FEET[leg]
        if f <= a:
            return rest.copy(), Quaternion()
        if f < b:
            s = (f - a) / float(b - a)
            h = 16.0 * s * s * (1.0 - s) * (1.0 - s)        # lift bell: zero speed at lift-off / touch-down
            q = Quaternion(Vector((1, 0, 0)), math.radians(15.0 * h * h))  # gentle toe-back flex in the swing
            p = rest + off * smoother(s) + V(0, 0, 0.045 * h)
            p.z = max(p.z, hoof_floor(leg, q))
            return p, q
        q = roll_q(self.hoof_roll(f))
        W = self.plant[leg] + _HOOF_EDGE[leg]
        p = W - q @ _HOOF_EDGE[leg]
        p.z = max(p.z, hoof_floor(leg, q))
        return p, q

    def limp(self, leg, f):
        """0 = planted flat, 1 = limp (hoof follows the cannon)"""
        if leg not in D_LIFT:
            return 0.0
        a, b = D_LIFT[leg]
        return ramp(f, a, b)

    def limp_flex(self, leg, f):
        a = D_LIFT[leg][0]
        fl = D_FLEX[leg] * smooth((f - a) / float(D_IMP - a))
        if leg == "LH":
            fl += 25.0 * bump(f, *D_REFLEX)
        return fl

    def _dead(self):
        """dead pose pieces (world at the final root; also the relaxed upper-foot positions in the trunk frame)"""
        self.root_end = V(self.x_dead, 0.0, 0.0)
        feet = {leg: self.lower_foot(leg, DEATH_HOLD)[0] for leg in ("RF", "RH")}
        for leg, low in (("LF", "RF"), ("LH", "RH")):
            p = feet[low] + DEAD["upper"][leg]
            q = self.q_est.get((DEATH_HOLD, leg))
            if q is not None:
                p.z = max(p.z, hoof_floor(leg, q))
            feet[leg] = p
        self.dead_feet = feet
        frames = leg_frames(self.calf, self.base(DEATH_HOLD))
        self.local_dead = {leg: frames[leg].inverted() @ feet[leg] for leg in ("LF", "LH")}

    def local_lift(self, leg):
        """planted hoof in the trunk frame at its lift-off: the unloaded leg keeps that shape, carried by the trunk"""
        if not hasattr(self, "_local_lift"):
            self._local_lift = {}
        if leg not in self._local_lift:
            fr = leg_frames(self.calf, self.base(D_LIFT[leg][0]))[leg]
            self._local_lift[leg] = fr.inverted() @ _REST_FEET[leg]
        return self._local_lift[leg]

    def upper_foot(self, leg, f, P):
        """left (up-hill) legs: planted until they unload, then carried by the trunk and relaxed into the dead pose"""
        rest = _REST_FEET[leg]
        w = self.limp(leg, f)
        if w <= 0.0:
            return rest.copy()
        fr = leg_frames(self.calf, P)[leg]
        a, b = D_RELAX[leg]
        u = smooth((f - a) / float(b - a))
        loc = self.local_lift(leg).lerp(self.local_dead[leg], u)
        c = fr @ loc
        la, lb = D_LIFT[leg]
        wz = ramp(f, la, la + 0.6 * (lb - la))           # the hoof leaves the ground upward first ...
        wxy = ramp(f, la + 1.0, lb + 1.0)                 # ... then follows the trunk sideways
        p = V(rest.x + (c.x - rest.x) * wxy, rest.y + (c.y - rest.y) * wxy, rest.z + (c.z - rest.z) * wz)
        p.z += 0.025 * bump(f, la, la + 2.0, lb + 3.0)
        if leg == "LH":
            k = bump(f, *D_REFLEX)
            if k:
                p = p + V(0.03, -0.05, 0.07) * k
        q = Quaternion().slerp(self.q_est.get((f, leg), body_rot_matrix(P).to_quaternion()), w)
        p.z = max(p.z, hoof_floor(leg, q))
        return p

    def pose(self, f):
        P = self.base(f)
        for leg in ("RF", "RH"):
            P.feet_world[leg] = self.lower_foot(leg, f)[0]
        for leg in ("LF", "LH"):
            P.feet_world[leg] = self.upper_foot(leg, f, P)
        return P

    # ---------------------------------------------------------------- hoof orientation (hook / post-bake)
    def hoof_q_pre(self, leg, f, P):
        if leg in D_STEPS:
            return self.lower_foot(leg, f)[1]
        w = self.limp(leg, f)
        return Quaternion().slerp(self.q_est.get((f, leg), body_rot_matrix(P).to_quaternion()), w)

    def cannon_q(self, leg, f, M_lower):
        lo = LEGS[leg]["chain"][1]
        D = M_lower.to_quaternion() @ self.calf.rest[lo].to_quaternion().inverted()
        axis = D @ Vector((1, 0, 0))
        return Quaternion(axis, math.radians(self.limp_flex(leg, min(f, DEATH_HOLD)))) @ D


def dead_pose(calf, root=None):
    """final Death pose (held), root-relative: lying flat on the RIGHT side, lower legs on the ground where the
    hooves pivoted, upper legs in front of them, right cheek on the ground. `root` = root position (the Death clip
    ends with the Root under the carcass). auto_top off: the leg tops only get the explicit top_rot / femur.
    The hoof bones are oriented by the Death hook (lower: tipped on the lateral wall; upper: follow the cannon)."""
    m = _death_model(calf)
    P = m.base(DEATH_HOLD)
    rel_root = P.root_pos.copy()
    P.root_pos = V() if root is None else Vector(root)
    for leg, p in m.dead_feet.items():
        P.feet_world[leg] = p - rel_root + P.root_pos
    return P


_MODELS = {}


def _death_model(calf):
    if id(calf) not in _MODELS:
        if not _REST_FEET:
            _init(calf)
        _MODELS[id(calf)] = DeathModel(calf)
    return _MODELS[id(calf)]


def death_fn(calf):
    """returns (N, pose fn, planted fn, basis hook, raw pose fn, post-bake fn)"""
    m = _death_model(calf)
    N = DEATH_N

    def raw(f):
        return m.pose(f)

    def fn(f):
        if f == 0:
            return stand_pose()
        if f >= DEATH_HOLD:
            return dead_pose(calf, m.root_end)
        return raw(f)

    def planted(leg, f):
        """hoof flat on the ground and bearing weight (calf.qa slide metric). The right hooves keep their contact
        edge fixed while they tip (f > D_T0): that phase is measured on the mesh (contact slide)."""
        if leg in D_LIFT:
            return f <= D_LIFT[leg][0]
        a, b, _ = D_STEPS[leg]
        if a < f < b:
            return False
        return f <= D_T0

    def hook(f, P, B):
        if f == 0:
            return
        pose = calf._last_pose
        ff = min(f, DEATH_HOLD)
        for leg in LEGS:
            q = m.hoof_q_pre(leg, ff, P)
            if abs(q.angle) < 1e-9:
                continue
            fb = LEGS[leg]["foot"]
            Mn = Matrix.Translation(pose[fb].translation) @ (q @ calf.rest[fb].to_quaternion()).to_matrix().to_4x4()
            B[fb] = calf.basis_for(fb, pose, Mn)

    def post(rows):
        out = {}
        for leg in ("LF", "LH"):
            fb, lo = LEGS[leg]["foot"], LEGS[leg]["chain"][1]
            vals = []
            for f, r in enumerate(rows):
                ff = min(f, DEATH_HOLD)
                qc = m.cannon_q(leg, ff, r[lo])
                if f <= DEATH_HOLD:
                    m.q_new[(f, leg)] = qc
                q = Quaternion().slerp(qc, m.limp(leg, ff))
                M = Matrix.Translation(r[fb].translation) @ (q @ calf.rest[fb].to_quaternion()).to_matrix().to_4x4()
                basis = (r["Root"] @ calf.rel(fb)).inverted() @ M
                loc, rot, _ = basis.decompose()
                vals.append((loc, rot))
            out[fb] = vals
        return out

    return N, fn, planted, hook, raw, post


# ============================================================================== Leap
LEAP_N = 40
# forward speed of the body (m/s), integrated to the root path: still while crouching, explosive hind push
# (f8-14, ~1.4 g), ballistic flight (constant), hard braking on the fore legs after the front touch-down
LEAP_V = [(0, 0.0), (7, 0.0), (8, 0.1), (11, 1.3), (14, 2.7), (24, 2.7), (26, 1.5), (28, 0.7), (31, 0.2),
          (35, 0.03), (40, 0.0)]
LEAP_FEET = {"LF": (7, 24), "RF": (8, 25), "LH": (13, 26), "RH": (14, 27)}     # lift-off, touch-down
LEAP_T0, LEAP_T1 = 14, 24          # flight: last hind lift-off .. first front touch-down
# landing, as heights of the front (elbow line, LEAP_DF ahead of the COG) and rear (hip line, LEAP_DR behind) relative
# to rest; body z and pitch follow from them. Handover from the flight curves at LEAP_HX (value + slope match).
LEAP_DF, LEAP_DR = 0.29, 0.38
LEAP_HX = 19
# optimised (scratch leapopt2.py): COG ballistic until the fore contact (f24), fore leg nearly straight at contact,
# <= ~30 mm fore-leg give after it, rear keeps falling until the hind contact (f26/27), smooth head / pitch
LEAP_HF = [(20, 0.0727), (21, 0.0473), (22, 0.0178), (23, -0.0177), (24, -0.0591), (25, -0.0529), (26, -0.0265),
           (27, -0.011), (28, -0.0055), (29, -0.0045), (30, -0.0062), (31, -0.0107), (32, -0.0148), (33, -0.017),
           (34, -0.0166), (35, -0.0127), (36, -0.0085), (40, 0.0)]
LEAP_HR = [(20, 0.1053), (21, 0.0973), (22, 0.0707), (23, 0.0284), (24, -0.0305), (25, -0.0941), (26, -0.0967),
           (27, -0.0872), (28, -0.0753), (29, -0.0634), (30, -0.054), (31, -0.0495), (32, -0.046), (33, -0.042),
           (34, -0.0368), (35, -0.0286), (36, -0.0205), (40, 0.0)]
# neck pitch added after the fore contact (+ = head lower): the head keeps sinking 2-3 frames, then recovers
LEAP_NECK_LAG = [(23, -1.8), (24, -4.57), (25, 1.42), (26, 4.42), (27, 4.05), (28, 2.33), (29, 1.05), (30, 0.22),
                 (31, -0.15), (32, -0.15), (33, 0.0)]
# the fore hooves land this much short of their final spot (a smaller forward leg angle at contact: less vault
# rebound, reachable one frame before contact) and step into it during the settle (lift, land)
LEAP_SHORT = {"LF": 0.08, "RF": 0.08}
LEAP_STEP = {"LF": (31, 36), "RF": (33, 38)}
LEAP_TOEOFF = (3, 16.0)            # hind push-off: the heel lifts over the last 3 planted frames (roll onto the toe, deg)


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
    C["by"] = Curve([(0, 0.0), (5, 0.02), (9, 0.015), (14, 0.0), (N, 0.0)])
    # ballistic flight (g = 9.81 m/s^2) between LEAP_T0 and LEAP_T1, same height at both ends
    g = 9.81 / FPS / FPS
    t0, t1 = float(LEAP_T0), float(LEAP_T1)
    z0, z1 = -0.035, -0.05
    vz = (z1 - z0 + 0.5 * g * (t1 - t0) ** 2) / (t1 - t0)

    def flight(f):
        t = f - t0
        return z0 + vz * t - 0.5 * g * t * t
    C["bz_pre"] = Curve([(0, 0.0), (5, -0.045), (8, -0.052), (11, -0.045), (t0, z0, vz)])
    # pitch up to the landing handover (LEAP_HX = 19; keys 21/23 only shape its slope there). From LEAP_HX on the
    # body height and pitch come from the front / rear height keys LEAP_HF / LEAP_HR (see the module docstring).
    C["pitch"] = Curve([(0, 0.0), (5, -6.0), (7, -6.5), (11, -11.0), (14, -14.0), (18, -3.0), (21, 7.5),
                        (23, 12.5)])
    C["neck"] = VCurve([(0, [0.0] * 3), (5, [4.0, 4.0, 3.0]), (11, [-6.0, -8.0, -8.0]), (18, [-4.0, -6.0, -6.0]),
                        (24, [0.0, 0.0, 0.0]), (28, [3.0, 4.0, 3.0]), (34, [0.5, 0.5, 0.0]), (N, [0.0] * 3)])
    C["head"] = VCurve([(0, [0.0] * 3), (5, [4.0, 0.0, 0.0]), (12, [-10.0, 0.0, 0.0]), (19, [-6.0, 3.0, 4.0]),
                        (25, [1.0, 0.0, 0.0]), (29, [3.0, 0.0, 0.0]), (35, [-1.0, 0.0, 0.0]), (N, [0.0] * 3)])
    C["ears"] = VCurve([(0, [0.0] * 3), (5, [8.0, -4.0, 0.0]), (11, [-24.0, -6.0, 6.0]), (21, [-26.0, -2.0, 6.0]),
                        (26, [-8.0, 22.0, 0.0]), (31, [-4.0, 4.0, 0.0]), (36, [2.0, -2.0, 0.0]), (N, [0.0] * 3)])
    C["tail_lift"] = Curve([(0, 0.0), (7, 0.0), (14, 1.0), (23, 0.8), (31, 0.1), (N, 0.0)])
    C["kick_twist"] = Curve([(0, 0.0), (14, 0.0), (17, 1.0), (21, 0.3), (26, 0.0), (N, 0.0)])
    C["gain_f"] = Curve([(0, 1.0), (8, 1.0), (12, 0.6), (19, 0.6), (22, 1.0), (N, 1.0)])

    # swing paths: keys (when, root-frame offset from rest, hoof flex); when = ("u", fraction of the swing),
    # ("off", frames after lift-off) or ("td", frames before touch-down). World velocity 0 at lift-off and
    # touch-down (the hoof leaves / meets the ground without sliding)
    swing_keys = {
        "F": [(("u", 0.30), V(0.0, 0.10, 0.20), 90.0), (("u", 0.55), V(0.0, 0.02, 0.26), 115.0),
              (("tdw", 3), V(0.0, 0.145, 0.16), 60.0), (("tdw", 2), V(0.0, 0.055, 0.12), 30.0),
              (("tdw", 1), V(0.0, 0.015, 0.06), 8.0)],
        # hind: fully extended at take-off, the hooves first ride up with the rising hips (leg stays long), then
        # the buck: kicked out back and up (f19-24), then swung forward under the body to land
        "H": [(("offw", 1), V(0.0, 0.55, 0.04), 25.0), (("off", 3), V(0.0, 0.29, 0.16), 45.0),
              (("u", 0.35), V(0.0, 0.27, 0.27), 80.0), (("u", 0.55), V(0.0, 0.12, 0.27), 85.0),
              (("tdw", 3), V(0.0, 0.18, 0.13), 50.0), (("tdw", 2), V(0.0, 0.07, 0.07), 25.0),
              (("tdw", 1), V(0.0, 0.018, 0.028), 8.0)],
    }
    def toeoff(leg, f):
        """hind feet before lift-off: (fetlock world, flex) rolling onto the toe tip"""
        a = LEAP_FEET[leg][0]
        n, deg = LEAP_TOEOFF
        fl = deg * smooth((f - (a - n)) / float(n)) if leg[1] == "H" else 0.0
        if fl <= 0.0:
            return _REST_FEET[leg].copy(), 0.0
        return toe_pivot_fetlock(calf, leg, fl, _REST_FEET[leg] + _HOOF_TOE[leg]), fl

    paths, flexes = {}, {}
    for leg, (a, b) in LEAP_FEET.items():
        kind = leg[1]
        # lift-off: the hoof peels off upward (toe-off); the hind legs are at full extension when they leave, so
        # their hooves must follow the rising hips at once (half the ground speed backward, 2.5 cm/f up)
        vel_a = V(0.0, vel(a) / FPS, 0.012) if kind == "F" else V(0.0, 0.5 * vel(a) / FPS, 0.025)
        vel_b = V(0.0, vel(b) / FPS, -0.012)
        p_a, fl_a = toeoff(leg, a)
        rel_a = p_a - _REST_FEET[leg] + V(0.0, s[a], 0.0)
        if kind == "H":         # continue the toe-off motion (world) at lift-off: no velocity kink
            vel_a = (p_a - toeoff(leg, a - 1)[0]) + V(0.0, vel(a) / FPS, 0.0)
        rel_b = V(0.0, s[b] - D + LEAP_SHORT.get(leg, 0.0), 0.0)
        keys = [(a, rel_a, vel_a)]
        fkeys = [(a, fl_a)]
        for (mode, u), p, fl in swing_keys[kind]:
            fr = {"u": a + u * (b - a), "off": a + u, "offw": a + u, "td": b - u, "tdw": b - u}[mode]
            if mode == "tdw":       # world-anchored: offset (behind, up) from the landing spot, u whole frames early
                p = V(0.0, s[b - u] - D + LEAP_SHORT.get(leg, 0.0) + p.y, p.z)
            if mode == "offw":      # u whole frames after lift-off: the hoof follows p.y x the root's advance, p.z up
                p = rel_a + V(0.0, (s[a + u] - s[a]) * (1.0 - p.y), p.z)
            keys.append((fr, p, None)); fkeys.append((fr, fl))
        keys.append((b, rel_b, vel_b))
        if all(abs(k[0] - (b - 1)) > 1e-6 for k in fkeys):
            fkeys.append((b - 1, 0.0 if kind == "F" else 5.0))
        fkeys.append((b, 0.0))
        paths[leg] = hermite_path(keys)
        flexes[leg] = Curve(fkeys)

    DF, DR = LEAP_DF, LEAP_DR

    def split(bz, pitch):
        sp = math.sin(math.radians(pitch))
        return bz - DF * sp, bz + DR * sp

    def join(hF, hR):
        sp = (hR - hF) / (DF + DR)
        return hF + DF * sp, math.degrees(math.asin(sp))

    def pre_bz(f):
        return C["bz_pre"](f) if f <= t0 else flight(f)
    hx = LEAP_HX
    h0, h1 = split(pre_bz(hx), C["pitch"](hx)), split(pre_bz(hx - 0.01), C["pitch"](hx - 0.01))
    CF = Curve([(hx, h0[0], (h0[0] - h1[0]) / 0.01)] + LEAP_HF)
    CR = Curve([(hx, h0[1], (h0[1] - h1[1]) / 0.01)] + LEAP_HR)
    lag = Curve([(0, 0.0)] + LEAP_NECK_LAG + [(N, 0.0)]) if LEAP_NECK_LAG else (lambda f: 0.0)

    def body_zp(f):
        if f <= hx:
            return pre_bz(f), C["pitch"](f)
        return join(CF(f), CR(f))

    def raw(f):
        P = Pose()
        P.root_pos = rootp(f)
        bz, pitch = body_zp(f)
        P.body_off = V(0.0, C["by"](f), bz)
        tw = C["kick_twist"](f)
        P.body_rot = V(pitch, 0.0, 0.0)
        add_spine(P, "Back", yaw=6.0 * tw, roll=-5.0 * tw)
        add_spine(P, "Torso", yaw=-2.0 * tw)
        lg = lag(f)
        P.neck = [v + lg * w for v, w in zip(C["neck"](f), (0.3, 0.35, 0.35))]
        P.head = Vector(C["head"](f))
        e = Vector(C["ears"](f))
        P.ears = {"L": e.copy(), "R": e.copy()}
        tl = C["tail_lift"](f)
        P.tail = [(0.0, 12.0 * tl * (1.0 - 0.13 * i)) for i in range(7)]
        add_tail_wave(P, 6.0 * bump(f, 12, 22, 34), (f - 12) / 12.0)
        P.top_gain = {"F": C["gain_f"](f), "H": 0.9}
        for leg, (a, b) in LEAP_FEET.items():
            if f <= a:
                P.feet_world[leg], P.flex[leg] = toeoff(leg, f)
            elif f >= b:
                P.feet_world[leg], P.flex[leg] = settle_foot(leg, f)
            else:
                P.feet_world[leg] = P.root_pos + _REST_FEET[leg] + paths[leg](f)
                P.flex[leg] = flexes[leg](f)
        return P

    def settle_foot(leg, f):
        """planted after the landing; the fore feet then take their small balancing step into the final stance"""
        final = _REST_FEET[leg] + V(0.0, -D, 0.0)
        if leg not in LEAP_STEP:
            return final, 0.0
        land = final + V(0.0, LEAP_SHORT[leg], 0.0)
        c, d = LEAP_STEP[leg]
        if f <= c:
            return land, 0.0
        if f >= d:
            return final, 0.0
        u = (f - c) / float(d - c)
        h = 16.0 * u * u * (1.0 - u) * (1.0 - u)
        return land.lerp(final, smoother(u)) + V(0.0, 0.0, 0.035 * h), 25.0 * h * h

    end = stand_pose(V(0.0, -D, 0.0))

    def fn(f):
        if f == 0:
            return stand_pose(V())
        if f == N:
            return end
        return raw(f)

    def planted(leg, f):
        """hoof flat and bearing weight (calf.qa slide metric; the hind toe-off frames keep the toe tip fixed while
        the fetlock rises: measured on the mesh, contact slide)"""
        a, b = LEAP_FEET[leg]
        if leg in LEAP_STEP and LEAP_STEP[leg][0] < f < LEAP_STEP[leg][1]:
            return False
        if leg[1] == "H" and a - LEAP_TOEOFF[0] < f <= a:
            return False
        return f <= a or f >= b

    return N, fn, planted, None, raw, None


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
        k = flick(f, 24, 3, 8)
        P.ears["L"] = P.ears["L"] + V(-22.0 * k, -8.0 * k, 12.0 * k)
        # tail flick: one quick swish during the shake
        sw = bump(f, 8, 14, 28)
        add_tail_wave(P, 18.0 * sw, (f - 8) / 10.0, lift=4.0 * sw)
        return P

    def fn(f):
        if f == 0 or f == N:
            return stand_pose()
        return raw(f)

    return N, fn, (lambda leg, f: True), None, raw, None


# ============================================================================== build
DEATH_PASSES = 3        # Death is built 3x: limp hooves follow the baked cannon, which feeds their ground clamp


def clip_fns(calf):
    """name -> (frames, pose fn, planted fn, basis hook, raw fn, post-bake fn); cached per Calf"""
    key = ("fns", id(calf))
    if key not in _MODELS:
        _init(calf)
        _MODELS[key] = {"Death": death_fn(calf), "Leap": leap_fn(calf), "HeadShake": headshake_fn(calf)}
    return _MODELS[key]


def build(calf, only=None):
    made = []
    for name, (N, fn, planted, hook, raw, post) in clip_fns(calf).items():
        if only and name not in only:
            continue
        passes = DEATH_PASSES if name == "Death" else 1
        for it in range(passes):
            if name == "Death":
                m = _death_model(calf)
                m.q_est = dict(m.q_new)
                m._dead()
            make_clip_ex(calf, name, N, fn, loop=False, basis_hook=hook, post_bake=post)
            if name == "Death" and m.q_est:
                d = max((math.degrees(m.q_est[k].rotation_difference(m.q_new[k]).angle), k) for k in m.q_est)
                print(f"  Death pass {it + 1}: limp-hoof orientation, baked vs assumed {d[0]:.3f} deg {d[1]}")
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
    return dict(rot_acc=worst_r, loc_acc=worst_l, speed=speed, body_rot_acc=body_top, top=top)


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


def fetlock_angles(calf, act, frames):
    """per leg and frame: (dorsal, lateral) fetlock angle in deg. dorsal = pastern (hoof bone head->tail) vs cannon
    (lower-leg bone) in the cannon's flexion plane, + = pastern forward of the cannon line (dorsiflexion; rest: fore
    28 deg, hind 13.5 deg; a loaded fetlock should stay <= ~60 deg), - = flexed (toe curled back). lateral = pastern
    out of the flexion plane (the fetlock is a hinge: should stay small)."""
    calf.use_action(act)
    res = {leg: [] for leg in LEGS}
    for f in range(frames + 1):
        calf.sc.frame_set(f)
        dg = bpy.context.evaluated_depsgraph_get(); ae = calf.arm.evaluated_get(dg)
        for leg, d in LEGS.items():
            lo, ft = ae.pose.bones[d["chain"][1]], ae.pose.bones[d["foot"]]
            D = lo.matrix.to_quaternion() @ calf.rest[d["chain"][1]].to_quaternion().inverted()
            c = (lo.tail - lo.head).normalized()
            p = (ft.tail - ft.head).normalized()
            lat = (D @ Vector((1, 0, 0))).normalized()
            fwd = (D @ Vector((0, -1, 0)))
            fwd = (fwd - c * fwd.dot(c)).normalized()
            res[leg].append((math.degrees(math.atan2(p.dot(fwd), p.dot(c))),
                             math.degrees(math.asin(max(-1.0, min(1.0, p.dot(lat)))))))
    return res


class LegOverlap:
    """Leg/tail interpenetration: (1) Calf_LOD2 self-intersections (BVH) between polygons of different limbs /
    the tail (rest-pose intersections subtracted), (2) bone-capsule clearance with radii from Calf_LOD0 (median
    distance of each bone's dominant verts to the bone)."""
    PAIRS = [("FlegL", "FlegR"), ("HlegL", "HlegR"), ("FlegL", "HlegL"), ("FlegR", "HlegR"), ("FlegL", "HlegR"),
             ("FlegR", "HlegL"), ("Tail", "HlegL"), ("Tail", "HlegR")]
    CAPS = {"FlegL": ("FrontUpperLeg.L", "FrontLowerLeg.L", "IKFrontLeg.L", "FF.L"),
            "FlegR": ("FrontUpperLeg.R", "FrontLowerLeg.R", "IKFrontLeg.R", "FF.R"),
            "HlegL": ("BackUpperLeg.L", "BackLowerLeg.L", "IKBackLeg.L", "FFB.L"),
            "HlegR": ("BackUpperLeg.R", "BackLowerLeg.R", "IKBackLeg.R", "FFB.R"),
            "Tail": ("Tail3", "Tail4", "Tail5", "Tail6", "Tail7")}

    @staticmethod
    def region(n):
        side = n[-1]
        if n.startswith(("FrontUpperLeg", "FrontLowerLeg", "IKFrontLeg", "FF.")):
            return "Fleg" + side
        if n.startswith(("BackUpperLeg", "BackLowerLeg", "IKBackLeg", "FFB")):
            return "Hleg" + side
        if n.startswith("Tail"):
            return "Tail"
        return "other"

    def __init__(self, calf):
        from mathutils.bvhtree import BVHTree
        self.BVHTree = BVHTree
        self.calf = calf
        ob = bpy.data.objects["Calf_LOD2"]
        self.ob = ob
        me = ob.data
        gi = {g.index: g.name for g in ob.vertex_groups}
        dom = [gi[max(v.groups, key=lambda g: g.weight).group] if len(v.groups) else "?" for v in me.vertices]
        self.polys = [tuple(p.vertices) for p in me.polygons]
        preg = []
        for pv in self.polys:
            names = [self.region(dom[v]) for v in pv]
            preg.append(max(set(names), key=names.count))
        self.preg = preg
        self.mods = [m for m in ob.modifiers if m.type == "ARMATURE"]
        # capsule radii from LOD0
        o0 = bpy.data.objects["Calf_LOD0"]; m0 = o0.data
        gi0 = {g.index: g.name for g in o0.vertex_groups}
        byb = {}
        for v in m0.vertices:
            if len(v.groups):
                byb.setdefault(gi0[max(v.groups, key=lambda g: g.weight).group], []).append(v.index)
        co0 = np.zeros(len(m0.vertices) * 3); m0.vertices.foreach_get("co", co0); co0 = co0.reshape(-1, 3)
        M0 = np.array(o0.matrix_world); co0 = co0 @ M0[:3, :3].T + M0[:3, 3]
        self.rad = {}
        for bones in self.CAPS.values():
            for n in bones:
                b = calf.bones[n]
                a, t = np.array(b.head_local), np.array(b.tail_local)
                pts = co0[byb.get(n, [])]
                if not len(pts):
                    self.rad[n] = 0.02; continue
                ab = t - a
                u = np.clip((pts - a) @ ab / max(1e-12, ab @ ab), 0, 1)
                self.rad[n] = float(np.median(np.linalg.norm(pts - (a + u[:, None] * ab), axis=1)))
        self.rest_pairs = None

    def _coords(self):
        for m in self.mods:
            m.show_viewport = True
        dg = bpy.context.evaluated_depsgraph_get()
        oe = self.ob.evaluated_get(dg)
        n = len(oe.data.vertices)
        co = np.zeros(n * 3); oe.data.vertices.foreach_get("co", co); co = co.reshape(-1, 3)
        M = np.array(oe.matrix_world)
        for m in self.mods:
            m.show_viewport = False
        return co @ M[:3, :3].T + M[:3, 3]

    def _pairs(self, co):
        tree = self.BVHTree.FromPolygons([Vector(c) for c in co], self.polys, all_triangles=False, epsilon=0.0)
        want = {tuple(sorted(p)) for p in self.PAIRS}
        out = {}
        for a, b in tree.overlap(tree):
            if a >= b or set(self.polys[a]) & set(self.polys[b]):
                continue
            k = tuple(sorted((self.preg[a], self.preg[b])))
            if k in want:
                out.setdefault(k, set()).add((a, b))
        return out

    @staticmethod
    def _segdist(p0, p1, q0, q1):
        d1, d2, r = p1 - p0, q1 - q0, p0 - q0
        a, e, f = d1.dot(d1), d2.dot(d2), d2.dot(r)
        if a < 1e-12 and e < 1e-12:
            return r.length
        if a < 1e-12:
            s, t = 0.0, clamp01(f / e)
        else:
            c = d1.dot(r)
            if e < 1e-12:
                t, s = 0.0, clamp01(-c / a)
            else:
                b = d1.dot(d2); den = a * e - b * b
                s = clamp01((b * f - c * e) / den) if den > 1e-12 else 0.0
                t = (b * s + f) / e
                if t < 0: t, s = 0.0, clamp01(-c / a)
                elif t > 1: t, s = 1.0, clamp01((b - c) / a)
        return ((p0 + d1 * s) - (q0 + d2 * t)).length

    def check(self, act, frames, step=1):
        calf = self.calf
        if self.rest_pairs is None:
            if calf.arm.animation_data:
                calf.arm.animation_data.action = None
            for pb in calf.arm.pose.bones:
                pb.matrix_basis.identity()
            self.rest_pairs = self._pairs(self._coords())
        calf.use_action(act)
        worst_mesh, worst_cap, per = (0, None, None), (-1.0, None, None), {}
        for f in range(0, frames + 1, step):
            calf.sc.frame_set(f)
            pr = self._pairs(self._coords())
            for k, s in pr.items():
                n = len(s - self.rest_pairs.get(k, set()))
                if n:
                    per.setdefault(k, []).append((f, n))
                    if n > worst_mesh[0]:
                        worst_mesh = (n, "~".join(k), f)
            dg = bpy.context.evaluated_depsgraph_get(); ae = calf.arm.evaluated_get(dg)
            for ra, rb in self.PAIRS:
                for na in self.CAPS[ra]:
                    for nb in self.CAPS[rb]:
                        pa, pb = ae.pose.bones[na], ae.pose.bones[nb]
                        ov = self.rad[na] + self.rad[nb] - self._segdist(pa.head, pa.tail, pb.head, pb.tail)
                        if ov > worst_cap[0]:
                            worst_cap = (ov, f"{na}~{nb}", f)
        return dict(mesh=worst_mesh, capsule=worst_cap, frames={k: v for k, v in per.items()})


def contact_slide(calf, act, frames, obj="Calf_LOD0", tol=0.008):
    """hoof skating on the mesh: per leg, xy motion of the hoof verts that are within `tol` of the ground (relative
    to the leg's rest sole height) in two consecutive frames. Rolling (tipping on an edge) moves the contact verts
    only a little; sliding moves them all. Returns {leg: (max mm/frame, frame, total mm)}."""
    ob = bpy.data.objects[obj]; me = ob.data
    fp = np.zeros(len(me.polygons), np.int32)
    me.attributes["orig_part"].data.foreach_get("value", fp)
    hoof = np.zeros(len(me.vertices), bool)
    for p in me.polygons:
        if fp[p.index] == 2:
            hoof[list(p.vertices)] = True
    mods = [m for m in ob.modifiers if m.type == "ARMATURE"]

    def coords():
        for m in mods:
            m.show_viewport = True
        dg = bpy.context.evaluated_depsgraph_get(); oe = ob.evaluated_get(dg)
        n = len(oe.data.vertices)
        co = np.zeros(n * 3); oe.data.vertices.foreach_get("co", co); co = co.reshape(-1, 3)
        M = np.array(oe.matrix_world)
        for m in mods:
            m.show_viewport = False
        return co @ M[:3, :3].T + M[:3, 3]
    if calf.arm.animation_data:
        calf.arm.animation_data.action = None
    for pb in calf.arm.pose.bones:
        pb.matrix_basis.identity()
    c0 = coords()
    xl, yf = c0[:, 0] > 0, c0[:, 1] < 0
    masks = {"LF": hoof & xl & yf, "RF": hoof & ~xl & yf, "LH": hoof & xl & ~yf, "RH": hoof & ~xl & ~yf}
    ground = {leg: float(c0[m, 2].min()) for leg, m in masks.items()}
    calf.use_action(act)
    out = {leg: [0.0, None, 0.0] for leg in LEGS}
    prev = None
    for f in range(frames + 1):
        calf.sc.frame_set(f)
        co = coords()
        if prev is not None:
            for leg, mk in masks.items():
                cont = mk & (co[:, 2] < ground[leg] + tol) & (prev[:, 2] < ground[leg] + tol)
                if cont.any():
                    d = float(np.linalg.norm((co[cont] - prev[cont])[:, :2], axis=1).max())
                    out[leg][2] += d
                    if d > out[leg][0]:
                        out[leg][0], out[leg][1] = d, f
        prev = co
    return {leg: (v[0] * 1000, v[1], v[2] * 1000) for leg, v in out.items()}


def loaded_fn(name, planted):
    """frames in which a hoof bears weight (fetlock hyperextension limit applies)"""
    if name == "Death":
        return lambda leg, f: planted(leg, f) or (leg in D_STEPS and D_T0 < f <= D_IMP)
    return planted


def run_qa(calf, names, lod0=True):
    fns = clip_fns(calf)
    probe = MeshProbe(calf)
    overlap = LegOverlap(calf)
    report = {}
    for n in names:
        N, fn, planted, hook, raw, post = fns[n]
        act = bpy.data.actions[n]
        q = calf.qa(act, N, planted, label=n)
        m = probe.check(act, N, planted, step=1)
        jb = joint_bends(calf, act, N)
        sm = smoothness(calf, act, N)
        rr = reach_report(calf, N, fn, planted)
        fa = fetlock_angles(calf, act, N)
        ld = loaded_fn(n, planted)
        car = [min(min(jb["LF"]), min(jb["RF"])), max(max(jb["LF"]), max(jb["RF"]))]
        hoc = [min(min(jb["LH"]), min(jb["RH"])), max(max(jb["LH"]), max(jb["RH"]))]
        c = m["contact"]
        print(f"MESH {n}: non-hoof min z {m['body_min']*100:.2f} cm (f{m['body_f']} at "
              f"{tuple(round(x, 2) for x in m['body_at'])}, rest {m['rest_body']*100:.2f}) | hoof min z "
              f"{m['hoof_min']*100:.2f} cm (rest {m['rest_hoof']*100:.2f}) | planted hoof off its rest height <= "
              f"{c[0]*1000:.1f} mm ({c[1]} f{c[2]}) | head min z {m['head_min']*100:.2f} cm | tail min z "
              f"{m['tail_min']*100:.2f} cm")
        cs = contact_slide(calf, act, N, "Calf_LOD0" if lod0 else "Calf_LOD2")
        print(f"CONTACT {n} ({'LOD0' if lod0 else 'LOD2'} hoof verts within 8 mm of the ground in consecutive frames): " +
              " | ".join(f"{leg} max {v[0]:.1f} mm/f (f{v[1]}) total {v[2]:.0f} mm" for leg, v in cs.items()))
        ov = overlap.check(act, N)
        mo, co_ = ov["mesh"], ov["capsule"]
        print(f"OVERLAP {n}: LOD2 limb/tail self-intersections max {mo[0]} polygon pairs ({mo[1]} f{mo[2]}) | "
              f"worst bone-capsule overlap {co_[0]*1000:.1f} mm ({co_[1]} f{co_[2]}) (<= 0 = clear)")
        extra = ""
        if n == "Death":        # after the impact every leg rests: none may be held up by the IK reach clamp
            wr = max((e, leg, f_) for f_ in range(D_IMP, N + 1) for leg, e in calf.reach_excess(fn(f_)).items())
            extra = f" | all legs f{D_IMP}-{N} (resting) {wr[0]*1000:.1f} mm ({wr[1]} f{wr[2]})"
        print(f"REACH {n}: worst planted-leg reach excess {rr[0]*1000:.1f} mm ({rr[1]} f{rr[2]}){extra} (>0 = clamped)")
        tops = ", ".join(f"{b} {v:.1f} f{f_}" for v, b, f_ in sm["top"][:4])
        print(f"SMOOTH {n}: max rot 2nd diff (deg/f^2): {tops} | max loc 2nd diff {sm['loc_acc'][0]:.2f} mm/f^2 "
              f"({sm['loc_acc'][1]} f{sm['loc_acc'][2]}) | body/neck/head max {sm['body_rot_acc'][0]:.2f} "
              f"({sm['body_rot_acc'][1]} f{sm['body_rot_acc'][2]})")
        print(f"JOINTS {n}: carpus bend {car[0]:.1f}..{car[1]:.1f} deg | hock bend {hoc[0]:.1f}..{hoc[1]:.1f} deg "
              f"(+ = anatomical direction)")
        parts = []
        for leg in LEGS:
            dors = [a[0] for a in fa[leg]]
            lod = [(a[0], f_) for f_, a in enumerate(fa[leg]) if ld(leg, f_)]
            wl = max(lod) if lod else (float("nan"), None)
            lat = max((abs(a[1]), f_) for f_, a in enumerate(fa[leg]))
            parts.append(f"{leg} {min(dors):.0f}..{max(dors):.0f} (loaded max {wl[0]:.0f} f{wl[1]}), |lat| {lat[0]:.0f} f{lat[1]}")
        print(f"FETLOCK {n}: dorsal angle deg (rest F 28 / H 14, loaded limit ~60): " + " | ".join(parts))
        r0, r1 = pose_delta(raw(0), fn(0)), pose_delta(raw(N), fn(N))
        rh = pose_delta(raw(DEATH_HOLD), fn(DEATH_HOLD)) if n == "Death" else r1
        print(f"RESIDUAL {n}: raw curves vs shared pose at f0 {r0:.2e}, at f{N} {r1:.2e}"
              + (f", at hold start f{DEATH_HOLD} {rh:.2e}" if n == "Death" else "") + " (deg / m)")
        report[n] = dict(q, mesh=m, carpus=car, hock=hoc, smooth=sm, reach=rr, fetlock=fa, contact=cs, overlap=ov)
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
        calf.use_action(act); calf.sc.frame_set(N)
        rl = calf.arm.pose.bones["Root"].location
        if n == "Leap":
            print(f"ROOT {n}: end root position {tuple(round(x, 4) for x in rl)} (local), travelled {leap_root()[0][-1]:.3f} m")
        if n == "Death":
            print(f"ROOT {n}: end root position {tuple(round(x, 4) for x in rl)} (local; armature x "
                  f"{_death_model(calf).root_end.x:+.3f} m = to the calf's right)")
            s2 = bone_states(calf, act, [DEATH_HOLD, N])
            dl, da, dp = state_diff(s2[0], s2[1], skip_root=False)
            print(f"HOLD {n}: f{DEATH_HOLD} vs f{N}: loc {dl*1000:.4f} mm, rot {da:.4f} deg")
    return report


# ============================================================================== standalone
RENDER = {  # clip -> (strip frames a:b:step, sides)
    "Death": ("0:70:4", ("threequarter", "left")),
    "Leap": ("0:40:2", ("left",)),
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
