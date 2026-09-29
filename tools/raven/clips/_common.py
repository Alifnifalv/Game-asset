"""Shared key-pose tools for the raven clip families (the leading '_' keeps raven_animations.py from importing it as
a family).

  timeline(keys, f, lift=0.03)   keys = [(frame, Pose), ...]: eased (smootherstep) blend of neighbouring key poses;
                                 a foot that moves more than 1 cm between two keys is lifted on an arc (it steps)
  stand() / fly_neutral()        the boundary poses: every ground clip starts and ends on stand(), every flight clip on
                                 fly_neutral() (both from raven_anim)
  breathe / look / ruffle        additive layers (periodic in the clip length, so loops stay exact)
  flap(P, phase, amp)            one wingbeat of the GiM cruise flap (spec 6.3): phase 0 = top of the stroke

Timing (spec 6.4): walk 30 f per stride, flap 20 f per beat (down 10-11, up 9-10), glide float +-1.5 cm over ~2 s,
head saccades 3-5 f.
"""
import math, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import bpy  # noqa: F401,E402
from mathutils import Vector  # noqa: E402
import raven_anim as R  # noqa: E402

TAU = 2 * math.pi
stand = R.stand
fly_neutral = R.fly_neutral


def rest_mtp(s):
    return R._REST_MTP[s].copy()


def timeline(keys, f, lift=0.03):
    if f <= keys[0][0]:
        return keys[0][1].copy()
    if f >= keys[-1][0]:
        return keys[-1][1].copy()
    for (f0, p0), (f1, p1) in zip(keys, keys[1:]):
        if f0 <= f <= f1:
            t = (f - f0) / (f1 - f0)
            e = R.smoother(t)
            P = R.blend(p0, p1, e)
            for s in R.SIDES:
                a = p0.legs[s].mtp if p0.legs[s].mtp is not None else rest_mtp(s)
                b = p1.legs[s].mtp if p1.legs[s].mtp is not None else rest_mtp(s)
                dist = (Vector((a.x, a.y, 0)) - Vector((b.x, b.y, 0))).length
                if dist > 0.01 and lift > 0:
                    h = min(lift, 0.012 + dist * 0.4) * math.sin(math.pi * e)
                    P.legs[s].mtp = P.legs[s].mtp + Vector((0, 0, h))
                    P.legs[s].grip = max(P.legs[s].grip, 0.6 * math.sin(math.pi * e))
            return P
    return keys[-1][1].copy()


def breathe(P, t, amp=1.0, rate=1.0):
    """t in [0, 1) of a loop; rate = breaths per loop (an integer for loops)"""
    s = math.sin(TAU * rate * t)
    P.body_off = P.body_off + Vector((0, 0, 0.0012 * amp * s))
    a, b, c = P.spine["Spine2"]; P.spine = dict(P.spine); P.spine["Spine2"] = (a - 0.8 * amp * s, b, c)
    return P


def look(P, pitch=0.0, yaw=0.0, roll=0.0):
    """turn the head: split over Neck1-3 and Head (pitch + = bill down, yaw + = to the bird's left)"""
    n = dict(P.neck)
    for k, w in (("Neck1", 0.15), ("Neck2", 0.25), ("Neck3", 0.25)):
        a, b, c = n[k]; n[k] = (a + pitch * w, b + yaw * w, c)
    P.neck = n
    P.head = (P.head[0] + pitch * 0.35, P.head[1] + yaw * 0.35, P.head[2] + roll)
    return P


def flap(P, phase, amp=1.0, fold_up=0.35):
    """add one cruise wingbeat to a flight pose. phase in [0, 1): 0 = top, ~0.52 = bottom (downstroke 10-11 f of 20),
    then the upstroke with the wrist flexed and the hand swept back (spec 6.3: amplitude ~130 deg)"""
    down = 0.52
    if phase < down:                      # downstroke: from +62 to -62, wing fully extended, primaries closed
        u = phase / down
        e = 0.5 - 0.5 * math.cos(math.pi * u)
        elev = 62 - 124 * e
        fold = 0.0
        slot = 0.0
        spread = 4 * math.sin(math.pi * u)
    else:                                  # upstroke: flexed wrist, slots open
        u = (phase - down) / (1 - down)
        e = 0.5 - 0.5 * math.cos(math.pi * u)
        elev = -62 + 124 * e
        fold = fold_up * math.sin(math.pi * u)
        slot = 18 * math.sin(math.pi * u)
        spread = -6 * math.sin(math.pi * u)
    for s in R.SIDES:
        w = P.wings[s]
        w.elev += elev * amp
        w.fold = max(w.fold, 0.0)
        w.arm = (w.arm or 0.0) + 0.25 * fold
        w.elbow = (w.elbow or 0.0) + 0.6 * fold
        w.wrist = (w.wrist or 0.0) + 1.0 * fold
        w.feathers = (w.feathers or 0.0) + 0.7 * fold
        w.slot += slot
        w.spread += spread
        w.sweep += -8 * fold
    P.body_off = P.body_off + Vector((0, 0, 0.012 * math.sin(TAU * (phase + 0.1))))
    return P
