"""Clip family "idle_graze": standing idle, grazing and calling (bleat) clips for the calf rig.

    build(calf) -> ["Idle_LookAround", "Graze_Start", "Graze_Loop", "Graze_End", "Call"]

Clips (30 fps; hooves planted unless a step is listed)
  Idle_LookAround  loop 150 f  Pose() -> look left -> centre -> look right -> Pose(). The head leads the neck
                               and the neck leads the weight shift (overlapping action); ears turn toward the look
                               and flick independently (L f30, R f88, L f124); fly-swat tail swish f58-100; 3 breaths.
  Graze_Start      42 f        Pose() -> GRAZE. The neck leads, the head's extension lags a little (face tips down
                               with the neck, never past vertical, then reaches for the grass), the front end dips,
                               and the left fore takes a slow 6 cm step forward (f12-27) as in the GiM reference
                               (one fore leg forward while grazing).
  Graze_Loop       loop 120 f  GRAZE: 3 x (bite -> tear jerk -> 2 chews), sweeping left / right between bites;
                               ear flicks, tail swish, 2 breaths.
  Graze_End        40 f        GRAZE -> Pose(): the muzzle leads up (head extends further, then settles to rest
                               last), chewing while it rises, left fore steps back (f13-27), ears prick.
  Call             72 f        Pose() -> inhale/anticipation (f4-19) -> neck stretches forward & a bit up, head
                               extends nose-forward, jaw opens f16-22, >= 85 % open f22-43 (0.7 s) with a slight
                               vibrato, closes by f50, ears back, tail lifts -> Pose().

GRAZE pose (graze_pose): body pitch 1.8 deg nose-down + 6 mm lower, withers (Torso3) 8 deg down, neck 26.5/29.5/26.5
deg, head extended -43 deg (Head bone ~92 deg below horizontal: the face hangs about vertical), left fore 6 cm forward.
Nose pad 2.6-4.3 cm above the ground through Graze_Loop on Calf_LOD2 (2.9-4.6 cm on LOD0; lowest in the bites, highest
in the side sweeps), >= 2.8 cm in Graze_Start/End, ~13 cm ahead of the stepped left fore toe. Retuned for the final,
smaller head (stage B head_scale 0.97): the old neck 22.7/26.2/23.2, head -36, Torso3 7 left it 6.9-9.0 cm up.

Shared constant poses (module level): stand_pose() (== Pose()) and graze_pose() (GRAZE). Every non-loop clip starts
and ends EXACTLY at those (pose functions return them verbatim on the boundary frames; overlays are 0 there).

Ear convention of anim_lib.Pose.ears (verified with renders): x + = ear tip forward, y + = ear tip down (droop),
z = twist about the ear's long axis. Head roll + = left ear down (opposite of body_rot roll).

Leg reach: anim_lib clamps foot targets at 0.9985 x chain and vaults the body above 0.997 x chain; the straight front
legs rest at 0.996, so Pose() == rest (rest carpus 10.4 deg). A planted fore leg has ~0.5 mm of slack before the vault
and ~1.2 mm before the clamp, so these clips never raise the elbows above rest (body z <= 0, no front-up pitch).
make_clip is called without stance_fn.

Standalone: python3 tools/clips/idle_graze.py [--in build/stage_b.blend] [--out-dir DIR] [--no-render] [--only a,b]
                                              [--gif-step 3] [--res 320] [--samples 6] [--sides left,front]
  builds the clips, prints calf.qa + a mesh ground check (Calf_LOD2) + carpus/hock bend + pop/seam/boundary checks,
  saves DIR/test.blend and renders filmstrips (DIR/<clip>_<side>.png) + GIFs (DIR/<clip>_<side>_anim.gif).
  DIR defaults to this session's scratchpad if it exists, else build/clip_tests/idle_graze (gitignored).
  ~5 s without renders, ~3.5 min with (4 shared cores).
"""
import argparse, math, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(TOOLS)
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import bpy
import numpy as np
from mathutils import Vector, Quaternion
import anim_lib as A
from anim_lib import Pose, LEGS

FPS = 30
CLIPS = ("Idle_LookAround", "Graze_Start", "Graze_Loop", "Graze_End", "Call")


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
    """quick ear/skin twitch: eased rise over `up` frames (no velocity jump at the start: the old ease-out rise made
    the Graze_Loop tear jerk start at full speed in one frame, review A12b), slower settle over `down` frames"""
    t = f - f0
    if t <= 0 or t >= up + down:
        return 0.0
    if t < up:
        return smooth(t / up)
    return 1.0 - smooth((t - up) / down)


class Curve:
    """Scalar key curve with monotone cubic (Fritsch-Carlson) interpolation: passes through every key, never
    overshoots between keys (extreme keys get flat tangents = natural ease in/out). `period` makes it cyclic
    (keys must then start at 0 and end at `period` with equal values)."""

    def __init__(self, keys, period=None):
        self.k = sorted(keys)
        self.period = period
        xs = [k[0] for k in self.k]; ys = [k[1] for k in self.k]
        n = len(xs)
        d = [(ys[i + 1] - ys[i]) / (xs[i + 1] - xs[i]) for i in range(n - 1)]
        m = [0.0] * n
        for i in range(1, n - 1):
            m[i] = 0.0 if d[i - 1] * d[i] <= 0 else 0.5 * (d[i - 1] + d[i])
        if period and n > 2:
            dd = (d[-1], d[0])
            m[0] = m[-1] = 0.0 if dd[0] * dd[1] <= 0 else 0.5 * (dd[0] + dd[1])
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
        self.xs, self.ys, self.m = xs, ys, m

    def __call__(self, f):
        xs, ys, m = self.xs, self.ys, self.m
        if self.period:
            f = f % self.period
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
        return ((2 * t3 - 3 * t2 + 1) * ys[i] + (t3 - 2 * t2 + t) * h * m[i]
                + (-2 * t3 + 3 * t2) * ys[i + 1] + (t3 - t2) * h * m[i + 1])


# ============================================================================== pose helpers
def copy_pose(P):
    return A.pose_combine([(1.0, P)])


def group_blend(a, b, w):
    """anim_lib.blend_pose with a separate weight per field group (overlapping action). w: group -> t with groups
    body, spine, neck, head, jaw, ears, tail, feet (feet + flex + glide + femur + top_rot); 'default' for the rest."""
    cache = {}

    def bp(g):
        t = w.get(g, w.get("default", 0.0))
        if t not in cache:
            cache[t] = A.blend_pose(a, b, t)
        return cache[t]

    out = Pose()
    out.root_pos, out.root_yaw = bp("root").root_pos, bp("root").root_yaw
    out.body_off, out.body_rot = bp("body").body_off, bp("body").body_rot
    out.spine = bp("spine").spine
    out.neck, out.neck_yaw = bp("neck").neck, bp("neck").neck_yaw
    out.head = bp("head").head
    out.jaw = bp("jaw").jaw
    out.ears = bp("ears").ears
    out.tail = bp("tail").tail
    f = bp("feet")
    out.feet, out.flex, out.glide, out.femur, out.top_rot = f.feet, f.flex, f.glide, f.femur, f.top_rot
    out.auto_top, out.top_gain = a.auto_top, dict(a.top_gain)
    return out


def add_spine(P, bone, pitch=0.0, yaw=0.0, roll=0.0):
    p, y, r = P.spine.get(bone, (0.0, 0.0, 0.0))
    P.spine[bone] = (p + pitch, y + yaw, r + roll)


def add_tail_wave(P, amp_side, phase, lift=0.0, lag=0.07):
    """travelling wave along the tail (grows toward the tip); phase in cycles"""
    for i in range(7):
        s, l = P.tail[i]
        P.tail[i] = (s + amp_side * (0.35 + 0.16 * (i + 1)) * math.sin(2 * math.pi * (phase - lag * (i + 1))),
                     l + lift * (1.0 - 0.1 * i))


def breathe(P, s, amp=1.0):
    """breathing (s in [0,1]: 0 = exhaled/rest, 1 = inhaled). The chest (Torso2/Torso3) lifts a little against the
    loin (Torso), the COG sinks <= 1.5 mm (never rises: straight front legs have no reach to spare)."""
    add_spine(P, "Torso", pitch=0.5 * amp * s)
    add_spine(P, "Torso2", pitch=-0.8 * amp * s)
    add_spine(P, "Torso3", pitch=0.3 * amp * s)
    P.body_off = P.body_off + V(0, 0, -0.0015 * amp * s)


# ============================================================================== shared poses
def stand_pose():
    """neutral standing pose (rest). Idle / Walk / every standing clip starts and ends here."""
    return Pose()


# GRAZE: tuned on the final stage B (smaller head) so the nose pad hangs 2.5-5 cm above the ground through Graze_Loop
# (LOD0 and LOD2 skinning; lowest in the bites) with the face about vertical, the front end ~1.5 cm lower (body pitch +
# withers), carpi only slightly more flexed than at rest.
GRAZE_FEET = {"LF": V(0.0, -0.06, 0.0)}           # left fore stepped forward 6 cm (Graze_Start/End step it)


def graze_pose():
    P = Pose()
    P.body_off = V(0.0, 0.0, -0.006)
    P.body_rot = V(1.8, 0.0, 0.0)                  # nose down 1.8 deg about the COG
    P.spine = {"Torso": (-0.6, 0.0, 0.0), "Torso3": (8.0, 0.0, 0.0)}   # withers follow the neck down
    P.neck = [26.5, 29.5, 26.5]                    # (was 22.7/26.2/23.2 for the old, bigger head: nose pad 6.9-9.0 cm up)
    P.neck_yaw = [1.0, 1.5, 2.0]
    P.head = V(-43.0, 3.0, 2.0)                    # head extends against the neck: Head bone ~92 deg below horizontal
    P.jaw = 0.0
    P.ears = {"L": V(-6.0, 14.0, -4.0), "R": V(-4.0, 12.0, -4.0)}      # relaxed, drooping out/back
    P.tail = [(0.44, -1.0), (0.86, 0.0), (0.04, 0.0), (-0.47, 0.0), (0.04, 0.0), (0.2, -0.01), (0.15, -0.01)]   # (A10 axis)
    P.feet = {k: v.copy() for k, v in GRAZE_FEET.items()}
    return P


# ============================================================================== Idle_LookAround
IDLE_N = 150


def idle_pose_fn():
    N = IDLE_N
    look = Curve([(0, 0.0), (12, 0.0), (38, 1.0), (56, 0.86), (72, 0.08), (80, 0.0), (104, -1.0), (120, -0.88),
                  (136, 0.0), (150, 0.0)], period=N)
    # head a little higher while looking (alert), a little lower in between (relaxed)
    lift = Curve([(0, 0.0), (14, 0.0), (40, 1.0), (58, 0.7), (78, -0.6), (90, -0.2), (106, 0.9), (122, 0.6),
                  (140, 0.0), (150, 0.0)], period=N)
    rest = stand_pose()

    def fn(f):
        P = copy_pose(rest)
        lh, ln, lb = look(f + 5), look(f), look(f - 7)      # head leads, neck, body follows
        # look: ~44 deg total (neck 26 + head 18), a slight head tilt into the turn
        P.neck_yaw = [5.0 * ln, 9.0 * ln, 12.0 * ln]
        P.head = V(0.0, 18.0 * lh, -4.0 * lh)
        up = lift(f + 2)
        P.neck = [-2.0 * up, -3.0 * up, -3.0 * up]
        P.head = P.head + V(-3.0 * up, 0.0, 0.0)
        # weight shift toward the look side + body yaw into it; COG sinks a little while shifted (reach)
        P.body_off = V(0.008 * lb, 0.0, -0.002 * abs(lb))
        P.body_rot = V(0.0, -0.4 * lb, 1.6 * lb)
        add_spine(P, "Torso3", yaw=2.0 * ln)
        add_spine(P, "Torso2", yaw=1.0 * lb)
        # ears: both prick forward while looking, the outer ear swivels toward the look side
        att = abs(look(f + 8))
        P.ears["L"] = V(10.0 * att + 8.0 * look(f + 8), -4.0 * att, 0.0)
        P.ears["R"] = V(10.0 * att - 8.0 * look(f + 8), -4.0 * att, 0.0)
        # independent ear flicks (back + twist)
        for side, f0 in (("L", 30), ("R", 88), ("L", 124)):
            k = flick(f, f0, 3, 9)
            P.ears[side] = P.ears[side] + V(-28.0 * k, -8.0 * k, 14.0 * k)
        # breathing: 3 breaths per loop
        breathe(P, 0.5 - 0.5 * math.cos(2 * math.pi * 3 * f / N))
        # tail: slow idle sway (2 cycles, faded to 0 at the seam) + a fly-swat swish f58-100
        add_tail_wave(P, 2.0 * (0.5 - 0.5 * math.cos(2 * math.pi * f / N)), 2.0 * f / N)
        sw = bump(f, 58, 70, 100)
        add_tail_wave(P, 18.0 * sw, (f - 58) / 15.0, lift=4.0 * sw)   # tip +-30 cm (A10: the tail swings now)
        return P
    return N, fn, stand_pose, stand_pose


# ============================================================================== grazing
GS_N = 42           # Graze_Start
GS_STEP = (12, 27)  # left fore swing (lift-off, touch-down)
GE_N = 40           # Graze_End
GE_STEP = (13, 27)
GL_N = 120          # Graze_Loop


def step_overlay(leg, f0, f1, a_off, b_off, lift=0.05, flex=55.0):
    """foot swing from a_off to b_off (root-frame offsets from rest) between frames f0..f1: smoother travel,
    sine lift arc (peak early, like a real careful step), hoof flexed back during the swing"""
    def ov(f, P):
        if f <= f0 or f >= f1:
            return P
        s = (f - f0) / float(f1 - f0)
        p = a_off.lerp(b_off, smoother(s))
        # lift arc peaking at ~44% of the swing with zero vertical speed at lift-off and touch-down
        h = math.sin(math.pi * s ** 0.85) ** 1.5
        p = p + V(0, 0, lift * h)
        P.feet[leg] = p
        # hoof flex follows the lift height: the hoof chain hangs ~22 deg off vertical, so flexing it near the
        # ground would first swing the toe DOWN into the ground (up to ~9 mm)
        P.flex[leg] = flex * h * h
        # weight comes off the stepping leg: COG drifts toward the diagonal support a few mm
        side = -1.0 if leg[0] == "L" else 1.0
        P.body_off = P.body_off + V(0.006 * side * math.sin(math.pi * s), 0, -0.002 * math.sin(math.pi * s))
        return P
    return ov


def graze_start_fn():
    N = GS_N
    rest, G = stand_pose(), graze_pose()
    f0, f1 = GS_STEP

    def fn(f):
        # the neck leads; the head's extension against the neck lags a little, so the face first tips down
        # with the neck (never past vertical) and then reaches forward for the grass
        w = dict(body=ramp(f, 2, 36), spine=ramp(f, 2, 38), neck=ramp(f, 0, 38, smoother),
                 head=ramp(f, 6, 38), ears=ramp(f, 16, 42), tail=ramp(f, 4, 40),
                 jaw=1.0, feet=ramp(f, f0, f1, smoother))
        P = group_blend(rest, G, w)
        P = step_overlay("LF", f0, f1, V(), GRAZE_FEET["LF"])(f, P)
        # the head swings slightly deeper mid-way (momentum) and is caught as it reaches the grass
        P.neck = [P.neck[0], P.neck[1] + 2.5 * bump(f, 18, 32, 42), P.neck[2] + 2.0 * bump(f, 18, 32, 42)]
        P.head = P.head + V(-4.0 * bump(f, 6, 22, 40), 0, 0)
        breathe(P, math.sin(math.pi * f / N) ** 2)
        # ears flick once as the head goes down
        P.ears["R"] = P.ears["R"] + V(-20.0, -6.0, 10.0) * flick(f, 24, 3, 8)
        return P
    return N, fn, stand_pose, graze_pose


def graze_loop_fn():
    N = GL_N
    G = graze_pose()
    # sideways sweeps between bites (muzzle travels ~8-10 cm each way), key-framed on the shared GRAZE pose
    sweep = Curve([(0, 0.0), (14, 0.0), (30, 1.0), (48, 0.8), (60, 0.1), (74, -0.9), (92, -0.85), (106, 0.0),
                   (120, 0.0)], period=N)
    bites = (4, 46, 80)                 # grab -> tear
    chews = (18, 30, 60, 70, 94, 106)   # jaw cycles between bites

    def jaw_at(f):
        j = 0.0
        for b in bites:
            j += 13.0 * bump(f, b, b + 4, b + 9)
        for c in chews:
            j += 7.0 * bump(f, c, c + 4, c + 10)
        return j

    def fn(f):
        P = copy_pose(G)
        s, sh = sweep(f), sweep(f + 3)                 # head leads the neck into each sweep
        P.neck_yaw = [P.neck_yaw[0] + 3.0 * s, P.neck_yaw[1] + 4.0 * s, P.neck_yaw[2] + 5.0 * s]
        P.head = P.head + V(0.0, 6.0 * sh, 3.0 * sh)
        add_spine(P, "Torso3", yaw=1.5 * s)
        P.body_rot = P.body_rot + V(0, 0.0, 0.6 * sweep(f - 6))
        P.body_off = P.body_off + V(0.004 * sweep(f - 6), 0, 0)
        # bite: muzzle dips into the grass, jaw grabs, then a short tear jerk up/back
        for b in bites:
            dip = bump(f, b - 4, b + 3, b + 8)
            tear = flick(f, b + 7, 3, 9)
            P.neck = [P.neck[0], P.neck[1] + 2.0 * dip - 1.5 * tear, P.neck[2] + 1.5 * dip - 2.5 * tear]
            P.head = P.head + V(2.0 * dip - 7.0 * tear, 0, 0)
            P.body_off = P.body_off + V(0, 0.004 * tear, 0)
        P.jaw = jaw_at(f)
        # chewing makes the head bob a touch
        P.head = P.head + V(-0.8 * P.jaw / 7.0, 0, 0)
        breathe(P, 0.5 - 0.5 * math.cos(2 * math.pi * 2 * f / N), amp=0.8)
        for side, f0, k0 in (("L", 36, 1.0), ("R", 66, 0.8), ("L", 100, 0.7)):
            k = flick(f, f0, 3, 9) * k0
            P.ears[side] = P.ears[side] + V(-24.0 * k, -10.0 * k, 12.0 * k)
        sw = bump(f, 50, 62, 92)
        add_tail_wave(P, 18.0 * sw, (f - 50) / 14.0, lift=3.0 * sw)   # tip +-30 cm (A10: the tail swings now)
        add_tail_wave(P, 1.5 * (0.5 - 0.5 * math.cos(2 * math.pi * f / N)), 1.0 * f / N)
        return P
    return N, fn, graze_pose, graze_pose


def graze_end_fn():
    N = GE_N
    rest, G = stand_pose(), graze_pose()
    f0, f1 = GE_STEP

    def fn(f):
        # the muzzle leads up: the head extends further (nose lifts off the grass, face comes up toward level)
        # while the neck starts rising; the head's own angle returns to rest last. Body/withers follow.
        w = dict(head=ramp(f, 8, 38), neck=ramp(f, 0, 32, smoother), spine=ramp(f, 2, 32),
                 body=ramp(f, 2, 30), ears=ramp(f, 18, 40), tail=ramp(f, 2, 36), jaw=1.0,
                 feet=ramp(f, f0, f1, smoother))
        P = group_blend(G, rest, w)
        P = step_overlay("LF", f0, f1, GRAZE_FEET["LF"], V())(f, P)
        P.head = P.head + V(-8.0 * bump(f, 0, 9, 26), 0, 0)
        # chewing the last mouthful while the head comes up
        env = math.sin(math.pi * f / N)
        P.jaw = sum(7.0 * bump(f, c, c + 4, c + 10) for c in (6, 17, 28)) * min(1.0, env * 1.6)
        # slight overshoot/settle of the head at the top
        P.head = P.head + V(-3.0 * bump(f, 24, 32, 40), 0, 0)
        breathe(P, math.sin(math.pi * f / N) ** 2)
        # alert ear flick after the head is up
        P.ears["L"] = P.ears["L"] + V(12.0, -6.0, 0.0) * bump(f, 26, 33, 40)
        P.ears["R"] = P.ears["R"] + V(12.0, -6.0, 0.0) * bump(f, 27, 34, 40)
        return P
    return N, fn, graze_pose, stand_pose


# ============================================================================== Call (bleat / moo)
CALL_N = 72


def call_pose_fn():
    N = CALL_N
    # 0..1 channels (monotone curves, flat at the ends)
    antic = Curve([(0, 0.0), (4, 0.0), (11, 1.0), (19, 0.0), (72, 0.0)])            # inhale, head dips
    ext = Curve([(0, 0.0), (9, 0.0), (21, 1.0), (40, 0.93), (48, 0.75), (62, 0.08), (72, 0.0)])   # stretch
    jaw = Curve([(0, 0.0), (16, 0.0), (22, 1.0), (36, 0.92), (43, 0.85), (50, 0.0), (72, 0.0)])
    ears = Curve([(0, 0.0), (12, 0.0), (22, 1.0), (46, 0.9), (60, 0.0), (72, 0.0)])

    def fn(f):
        P = stand_pose()
        a, e, j, er = antic(f), ext(f), jaw(f), ears(f)
        # anticipation: breath in, head tucks a little
        P.neck = [3.0 * a, 2.0 * a, 1.0 * a]
        P.head = V(6.0 * a, 0, 0)
        breathe(P, a, amp=1.6)
        # call: neck stretches forward (base lowers, top lifts), head extends nose-forward-up, throat long
        P.neck = [P.neck[0] + 9.0 * e, P.neck[1] - 2.0 * e, P.neck[2] - 9.0 * e]
        P.head = P.head + V(-26.0 * e, 0.0, 0.0)
        add_spine(P, "Torso3", pitch=-1.5 * e)
        # abdomen presses: loin rounds a touch (Torso/Torso2 balanced so the elbows keep their height: the
        # straight front legs have no reach to spare), COG sinks and shifts forward a little
        add_spine(P, "Torso", pitch=-0.6 * e)
        add_spine(P, "Torso2", pitch=1.0 * e)
        P.body_off = P.body_off + V(0, -0.006 * e, -0.003 * e)
        # jaw open ~24 deg with a small vibrato while held
        vib = 1.6 * math.sin(2 * math.pi * (f - 22) / 7.0) * bump(f, 22, 32, 46)
        P.jaw = 24.0 * j + vib * j
        P.ears["L"] = V(-22.0 * er, -6.0 * er, 6.0 * er)
        P.ears["R"] = V(-20.0 * er, -7.0 * er, 6.0 * er)
        # tail lifts a little with the effort, then a small swish on the release
        for i in range(7):
            P.tail[i] = (0.0, 8.0 * e * (1.0 - 0.12 * i))
        sw = bump(f, 44, 54, 70)
        add_tail_wave(P, 10.0 * sw, (f - 44) / 13.0)
        return P
    return N, fn, stand_pose, stand_pose


# ============================================================================== build
SWING = {"Graze_Start": {"LF": [GS_STEP]}, "Graze_End": {"LF": [GE_STEP]}}


def planted_fn(name):
    sw = SWING.get(name, {})

    def fn(leg, f):
        return not any(a < f < b for a, b in sw.get(leg, ()))
    return fn


def pose_fns():
    """name -> (frames, raw pose fn, start pose fn, end pose fn, loop)"""
    return {"Idle_LookAround": idle_pose_fn() + (True,),
            "Graze_Start": graze_start_fn() + (False,),
            "Graze_Loop": graze_loop_fn() + (True,),
            "Graze_End": graze_end_fn() + (False,),
            "Call": call_pose_fn() + (False,)}


def guarded(N, raw, start, end):
    """the boundary frames return the shared constant poses verbatim (bit-exact chaining); run_qa reports how far
    the raw curves + overlays are from them there (should be ~0, otherwise frame 1 / N-1 would pop)"""
    def fn(f):
        if f == 0:
            return start()
        if f == N:
            return end()
        return raw(f)
    return fn


def pose_values(P):
    """flat list of every numeric channel of a Pose (for comparisons)"""
    v = list(P.root_pos) + [P.root_yaw] + list(P.body_off) + list(P.body_rot)
    for b in A.SPINE:
        v += list(P.spine.get(b, (0.0, 0.0, 0.0)))
    v += list(P.neck) + list(P.neck_yaw) + list(P.head) + [P.jaw] + list(P.ears["L"]) + list(P.ears["R"])
    for t in P.tail:
        v += list(t)
    for leg in LEGS:
        v += list(P.feet.get(leg, V())) + [P.flex.get(leg, 0.0), P.glide.get(leg, 0.0), P.femur.get(leg, 0.0)]
        v += list(P.top_rot.get(leg, (0.0, 0.0, 0.0)))
    return v


def pose_delta(a, b):
    return max(abs(x - y) for x, y in zip(pose_values(a), pose_values(b)))


def build(calf, only=None):
    made = []
    for name, (N, raw, start, end, loop) in pose_fns().items():
        if only and name not in only:
            continue
        calf.make_clip(name, N, guarded(N, raw, start, end), loop=loop)
        made.append(name)
    return made


# ============================================================================== QA helpers
class MeshProbe:
    """Evaluates the skinned cage mesh Calf_LOD2 (fast) and reports ground clearance:
    body = min z of non-hoof verts (no face with orig_part == 2), hoof = min z of hoof verts (also per leg),
    nose = min z of the nose pad (orig_part == 3), head = min z of verts weighted > 0.5 to Head/Jaw.
    Note: at rest the hoof verts already reach z = -1.3 cm (the hoof sole sits slightly below the ground plane), so
    hoof contact is judged relative to each leg's rest value."""

    def __init__(self, calf, obj="Calf_LOD2"):
        self.calf = calf
        self.ob = bpy.data.objects[obj]
        me = self.ob.data
        nv = len(me.vertices)
        fp = np.zeros(len(me.polygons), np.int32)
        me.attributes["orig_part"].data.foreach_get("value", fp)
        self.hoof = np.zeros(nv, bool); self.nose = np.zeros(nv, bool)
        for p in me.polygons:
            if fp[p.index] == 2:
                self.hoof[list(p.vertices)] = True
            elif fp[p.index] == 3:
                self.nose[list(p.vertices)] = True
        gi = {g.index: g.name for g in self.ob.vertex_groups}
        hw = np.zeros(nv)
        for v in me.vertices:
            for g in v.groups:
                if gi.get(g.group) in ("Head", "Jaw"):
                    hw[v.index] += g.weight
        self.head = hw > 0.5
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
        r = dict(body=float(z[~self.hoof].min()), hoof=float(z[self.hoof].min()),
                 nose=float(z[self.nose].min()), head=float(z[self.head].min()),
                 nose_y=float(co[self.nose, 1].min()))
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
        """planted(leg, f) -> bool: report the worst |hoof min z - rest| of each leg while planted"""
        rest = self.rest_sample()
        self.calf.use_action(act)
        rows = []
        for f in list(range(0, frames + 1, step)) + ([frames] if frames % step else []):
            self.calf.sc.frame_set(f)
            r = self.sample(); r["f"] = f
            rows.append(r)
        contact = 0.0
        for leg in LEGS:
            for r in rows:
                if planted is None or planted(leg, r["f"]):
                    contact = max(contact, abs(r[leg] - rest[leg]))
        out = dict(body_min=min(r["body"] for r in rows), body_f=min(rows, key=lambda r: r["body"])["f"],
                   hoof_min=min(r["hoof"] for r in rows), contact=contact,
                   nose_min=min(r["nose"] for r in rows), nose_max=max(r["nose"] for r in rows),
                   head_min=min(r["head"] for r in rows),
                   rest_hoof=rest["hoof"], rest_body=rest["body"], rows=rows)
        return out


def smoothness(calf, act, frames, loop):
    """largest per-frame 'pop': second difference of every bone's local rotation (deg/frame^2) and location
    (mm/frame^2), wrapping across the seam for loops. Also the peak angular speed (deg/frame)."""
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
    idx = (range(frames) if loop else range(1, frames))
    for n in qs:
        Q, L = qs[n], ls[n]
        def at(i):
            if loop:
                i %= frames
            return Q[i], L[i]
        for i in idx:
            (qa, la), (qb, lb), (qc, lc) = at(i - 1), at(i), at(i + 1)
            if qa.dot(qb) < 0: qa = -qa
            if qc.dot(qb) < 0: qc = -qc
            d1 = qa.rotation_difference(qb); d2 = qb.rotation_difference(qc)
            acc = math.degrees(d1.rotation_difference(d2).angle)
            if acc > worst_r[0]: worst_r = (acc, n, i)
            if acc > per_bone.get(n, (0.0, 0))[0]: per_bone[n] = (acc, i)
            sp = math.degrees(d2.angle)
            if sp > speed[0]: speed = (sp, n, i)
            la_ = ((la - lb) - (lb - lc)).length * 1000
            if la_ > worst_l[0]: worst_l = (la_, n, i)
    top = sorted(((v[0], n, v[1]) for n, v in per_bone.items()), reverse=True)
    body_top = next((t for t in top if not t[1].startswith(("Ear", "Tail", "Jaw")) and
                     not any(t[1] in LEGS[l]["chain"] + (LEGS[l]["foot"], LEGS[l]["toe"]) for l in LEGS)), (0.0, None, None))
    return dict(rot_acc=worst_r, loc_acc=worst_l, speed=speed, body_rot_acc=body_top)


def joint_bends(calf, act, frames):
    """signed carpus / hock bend (deg) per frame. Carpus + = knee forward (cannon folds back, correct);
    hock + = point of the hock behind the stifle-fetlock line (correct)."""
    calf.use_action(act)
    res = {leg: [] for leg in LEGS}
    for f in range(frames + 1):
        calf.sc.frame_set(f)
        dg = bpy.context.evaluated_depsgraph_get(); ae = calf.arm.evaluated_get(dg)
        root_m = (ae.pose.bones["Root"].matrix @ calf.rest["Root"].inverted()).to_3x3()
        fwd = (root_m @ Vector((0, -1, 0))).normalized()          # calf forward (armature -Y) in the root frame
        for leg, d in LEGS.items():
            up, lo = ae.pose.bones[d["chain"][0]], ae.pose.bones[d["chain"][1]]
            a, j, b = up.head, up.tail, lo.tail
            ang = math.degrees((j - a).angle(b - j, 0.0))
            ab = (b - a)
            t = (j - a).dot(ab) / max(1e-9, ab.length_squared)
            off = (j - (a + ab * t)).dot(fwd)
            sgn = 1.0 if (off > 0) == leg.endswith("F") else -1.0
            res[leg].append(sgn * ang)
    return res


def bone_states(calf, act, frames_list):
    calf.use_action(act)
    out = []
    for f in frames_list:
        calf.sc.frame_set(f)
        out.append({pb.name: (pb.location.copy(), pb.rotation_quaternion.copy()) for pb in calf.arm.pose.bones})
    return out


def state_diff(a, b):
    dl, da = 0.0, 0.0
    for n in a:
        dl = max(dl, (a[n][0] - b[n][0]).length)
        da = max(da, math.degrees(a[n][1].rotation_difference(b[n][1]).angle))
    return dl, da


def run_qa(calf, names):
    probe = MeshProbe(calf)
    report = {}
    for n in names:
        act = bpy.data.actions[n]
        N = int(act.frame_range[1])
        q = calf.qa(act, N, planted_fn(n), label=n)
        m = probe.check(act, N, planted_fn(n), step=1)
        jb = joint_bends(calf, act, N)
        sm = smoothness(calf, act, N, act.use_cyclic)
        car = [min(min(jb["LF"]), min(jb["RF"])), max(max(jb["LF"]), max(jb["RF"]))]
        hoc = [min(min(jb["LH"]), min(jb["RH"])), max(max(jb["LH"]), max(jb["RH"]))]
        report[n] = dict(q, mesh=m, carpus=car, hock=hoc, smooth=sm)
        print(f"MESH {n}: body (non-hoof) min z {m['body_min']*100:.2f} cm (f{m['body_f']}, rest {m['rest_body']*100:.2f}) | "
              f"hoof min z {m['hoof_min']*100:.2f} cm (rest {m['rest_hoof']*100:.2f}) | planted hoof off its rest "
              f"height <= {m['contact']*1000:.1f} mm | nose pad z {m['nose_min']*100:.2f}..{m['nose_max']*100:.2f} cm | "
              f"head/jaw min z {m['head_min']*100:.2f} cm")
        print(f"SMOOTH {n}: max rot 2nd diff {sm['rot_acc'][0]:.2f} deg/f^2 ({sm['rot_acc'][1]} f{sm['rot_acc'][2]}) | "
              f"max loc 2nd diff {sm['loc_acc'][0]:.2f} mm/f^2 ({sm['loc_acc'][1]} f{sm['loc_acc'][2]}) | "
              f"peak speed {sm['speed'][0]:.2f} deg/f ({sm['speed'][1]} f{sm['speed'][2]}) | body/neck/head max rot "
              f"2nd diff {sm['body_rot_acc'][0]:.2f} ({sm['body_rot_acc'][1]} f{sm['body_rot_acc'][2]})")
        print(f"JOINTS {n}: carpus bend {car[0]:.1f}..{car[1]:.1f} deg | hock bend {hoc[0]:.1f}..{hoc[1]:.1f} deg "
              f"(+ = anatomical direction)")
    # overlay residuals at the guarded boundary frames (raw curves vs the shared poses)
    fns = pose_fns()
    for n in names:
        N, raw, start, end, loop = fns[n]
        r0, r1 = pose_delta(raw(0), start()), pose_delta(raw(N), end())
        print(f"RESIDUAL {n}: raw pose vs shared pose at f0 {r0:.2e}, at f{N} {r1:.2e} (deg / m)")
        report.setdefault("_residuals", []).append((n, r0, r1))
    # boundaries (chain with Pose() / GRAZE) and loop seams, all bones
    have = set(names)
    st = {}
    for n in names:
        act = bpy.data.actions[n]; N = int(act.frame_range[1])
        st[n] = bone_states(calf, act, [0, N])
    checks = []
    if "Idle_LookAround" in have: checks.append(("Idle_LookAround f0 vs last (seam)", st["Idle_LookAround"][0], st["Idle_LookAround"][1]))
    if "Graze_Loop" in have: checks.append(("Graze_Loop f0 vs last (seam)", st["Graze_Loop"][0], st["Graze_Loop"][1]))
    if {"Graze_Start", "Graze_Loop"} <= have: checks.append(("Graze_Start end vs Graze_Loop start", st["Graze_Start"][1], st["Graze_Loop"][0]))
    if {"Graze_Loop", "Graze_End"} <= have: checks.append(("Graze_Loop end vs Graze_End start", st["Graze_Loop"][1], st["Graze_End"][0]))
    base = next((st[n][0] for n in ("Idle_LookAround", "Call", "Graze_Start") if n in have), None)
    if base is not None:
        for n, i in (("Graze_Start", 0), ("Graze_End", 1), ("Call", 0), ("Call", 1), ("Idle_LookAround", 1)):
            if n in have:
                checks.append((f"{n} {'start' if i == 0 else 'end'} vs Pose()", st[n][i], base))
    for label, a, b in checks:
        dl, da = state_diff(a, b)
        print(f"BOUNDARY {label}: max loc diff {dl*1000:.4f} mm, max rot diff {da:.4f} deg")
        report.setdefault("_boundaries", []).append((label, dl, da))
    return report


# ============================================================================== standalone
RENDER = {  # clip -> (strip frames a:b:step, side); GIFs are rendered separately every --gif-step frames
    "Idle_LookAround": ("0:150:10", "threequarter"),
    "Graze_Start": ("0:42:6", "left"),
    "Graze_Loop": ("0:120:10", "left"),
    "Graze_End": ("0:40:5", "left"),
    "Call": ("0:72:6", "left"),
}

if __name__ == "__main__":
    SCR = "/tmp/claude-0/-home-user-Game-asset/f3fb310f-97d7-5da4-a5e8-b863f47eb685/scratchpad/idle_graze"
    if not os.path.isdir(os.path.dirname(SCR)):
        SCR = os.path.join(ROOT, "build", "clip_tests", "idle_graze")
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src", default=os.path.join(ROOT, "build", "stage_b.blend"))
    ap.add_argument("--out-dir", default=SCR)
    ap.add_argument("--no-render", action="store_true")
    ap.add_argument("--only", default="")
    ap.add_argument("--res", type=int, default=320)
    ap.add_argument("--samples", type=int, default=6)
    ap.add_argument("--sides", default="", help="override render side for all clips")
    ap.add_argument("--gif-step", type=int, default=3, help="frame step of the animated GIFs (0 = no GIF pass)")
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
            frames, side = RENDER[n]
            N = int(bpy.data.actions[n].frame_range[1])
            for sd in (a.sides.split(",") if a.sides else [side]):
                render(n, frames, sd, os.path.join(a.out_dir, f"{n}_{sd}"))          # filmstrip (+ coarse gif)
                print("rendered", os.path.join(a.out_dir, f"{n}_{sd}.png"))
                if a.gif_step:
                    # dense pass for a watchable GIF (its own .png strip is a by-product)
                    render(n, f"0:{N}:{a.gif_step}", sd, os.path.join(a.out_dir, f"{n}_{sd}_anim"))
                    print("rendered", os.path.join(a.out_dir, f"{n}_{sd}_anim.gif"))
