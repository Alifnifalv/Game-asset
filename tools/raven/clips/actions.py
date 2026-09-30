"""Raven actions (spec 6.3 / 6.6, GiM timings): Attack, Hit_L, Hit_R, Death_L, Death_R.

  Attack   48 f one-shot, root motion 0.15 m forward: crouch 6, wing flare 6, lunge-hop with a big forward-down flap 8
           (both feet off the ground, bill open 35 deg, head thrust), recover 8 (wings half open, level, then
           folding), hunched hold 12 (wings half folded and held off the body, hackles puffed), rise 8 (tail flick)
  Hit_L/R  15 f one-shot: flinch away from the hit side, wings jerk half open for 5 f, hackles ruffle
  Death_L/R 45 f one-shot: the head tilts, collapse 8 f (the body tips forward and onto its left / right side),
           impact bounce and settle, hold from f28: lying on the side, legs stiff and extended back, toes curled,
           wings loosely closed, head on the ground. The body is settled on the ground by a LOD2 evaluation
           (settle_body), so the dead pose follows mesh changes.

Boundaries: Attack and the hits start and end on stand(); Death starts on stand() (QA_EXTRA ends='start').
Feet: pinned in world space (the attack hop lands 0.15 m ahead); Death's feet are carried by the body once it falls.

  python3 tools/raven/clips/actions.py --in <stage_b.blend> [--out-dir <scratch>] [--only Attack] [--no-ground]
"""
import math, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE))
import bpy  # noqa: F401,E402
from mathutils import Vector  # noqa: E402
import raven_anim as R  # noqa: E402
import _common as C  # noqa: E402

SIDES = R.SIDES
RIG = None
ATTACK_N, HIT_N, DEATH_N = 48, 15, 45
ATTACK_DIST = 0.15


def _fin(P):
    return C.fit_thigh(RIG, P)


def _wings(P, **kw):
    for s in SIDES:
        P.wings[s] = R.WingPose(**kw)
    return P


# ================================================================================================= attack
def _atk_root_y(f):
    return -ATTACK_DIST * R.smoother((f - 9) / 14.0)


def attack(f, N=ATTACK_N):
    P = C.stand()
    P.root_pos = Vector((0, _atk_root_y(f), 0))
    # crouch (f0-6) -> lunge (f6-20) -> recover (f20-28) -> hunched hold (f28-40) -> rise (f40-48)
    crouch = C.track([(0, 0.0), (6, 1.0), (10, 0.7), (13, 0.2), (20, 0.6), (26, 0.5), (30, 1.0), (40, 1.0),
                      (47, 0.0)], f)
    pitch = C.track([(0, 0.0), (6, 20.0), (12, 26.0), (16, 30.0), (20, 22.0), (28, 16.0), (40, 16.0), (47, 0.0)], f)
    P.body_rot = (pitch, 0, 0)
    bz = -0.022 * crouch
    if 12 < f < 20:                                   # the lunge-hop: ballistic 4 cm above the crouch line
        u = (f - 12) / 8.0
        bz += 0.045 * 4 * u * (1 - u)
    P.body_off = Vector((0, -0.012 * C.track([(0, 0.0), (8, 1.0), (16, 1.6), (24, 0.8), (40, 0.6), (47, 0.0)], f),
                         bz))
    # head: low and forward in the crouch, thrust at the strike, drawn in during the hold
    thrust = C.track([(0, 0.0), (6, 0.4), (11, 0.2), (15, 1.0), (20, 0.8), (28, 0.3), (40, 0.3), (47, 0.0)], f)
    C.neck_bend(P, 26 * thrust)
    C.look(P, pitch=-pitch * 0.6 - 10 * thrust + 4 * crouch, yaw=C.track([(28, 0.0), (32, 12.0), (37, 12.0),
                                                                               (41, 0.0)], f))
    P.jaw = 35 * C.track([(0, 0.0), (11, 0.0), (14, 1.0), (22, 1.0), (26, 0.0)], f)
    P.throat = 22 * C.track([(0, 0.0), (6, 0.5), (12, 1.0), (24, 0.6), (30, 1.0), (40, 1.0), (46, 0.0)], f)
    # wings: flare high (f6-12), big forward-down stroke (f12-18), half open and level (f20-24), folding, held off
    # the body (f28-40), folded (f46)
    fold = C.track([(0, 1.0), (5, 1.0), (10, 0.22), (13, 0.12), (18, 0.18), (22, 0.5), (27, 0.68), (30, 0.72),
                    (40, 0.72), (46, 1.0)], f)
    elev = C.track([(0, 0.0), (5, 0.0), (10, 68.0), (12, 70.0), (17, 12.0), (20, 30.0), (23, 44.0), (28, 34.0),
                    (40, 28.0), (46, 0.0)], f)
    sweep = C.track([(0, 0.0), (10, 12.0), (12, 14.0), (17, 28.0), (21, 6.0), (28, 0.0)], f)
    arm = C.track([(0, 1.0), (5, 1.0), (10, 0.22), (13, 0.12), (18, 0.18), (22, 0.5), (27, 0.6), (40, 0.6),
                   (46, 1.0)], f)
    spread = C.track([(0, 0.0), (10, 6.0), (15, 8.0), (18, 0.0)], f)
    _wings(P, fold=fold, arm=arm, elev=elev, sweep=sweep, spread=spread)
    P.tail_spread = C.track([(0, 0.0), (8, 0.0), (14, 0.8), (22, 0.5), (30, 0.2), (40, 0.2), (46, 0.0)], f)
    P.tailbase = (C.track([(0, 0.0), (6, 6.0), (14, 12.0), (22, 4.0), (40, 4.0), (44, 0.0)], f), 0, 0)
    C.tail_flick(P, f, 40, amp=10, dur=7)
    # feet: planted at the start spot until f12, airborne f12-20, planted 0.15 m ahead from f20
    for s in SIDES:
        rest = C.rest_mtp(s)
        if f <= 12 or f >= 20:
            C.set_foot(P, s, (rest.x, 0.0 if f <= 12 else -ATTACK_DIST, rest.z))
        else:
            u = (f - 12) / 8.0
            y0 = 0.0 - _atk_root_y(12)
            y1 = -ATTACK_DIST - _atk_root_y(20)
            h = 0.032 * math.sin(math.pi * u)
            P.legs[s] = R.LegPose(Vector((rest.x, R.lerp(y0, y1, R.smoother(u)), rest.z + h)), 0.0,
                                  0.8 * math.sin(math.pi * u))
    return _fin(P)


# ================================================================================================= hits
def hit(f, side, N=HIT_N):
    """side = the side that is hit ('L' / 'R'): the bird flinches away from it"""
    k = 1.0 if side == "L" else -1.0              # hit on the left: lean right (-X), roll right side down (+)
    P = C.stand()
    a = C.track([(0, 0.0), (3, 1.0), (6, 0.8), (15, 0.0)], f)
    w = C.track([(0, 0.0), (2, 1.0), (7, 1.0), (12, 0.0)], f)
    P.body_off = Vector((-0.012 * k * a, 0.006 * a, -0.008 * a))
    P.body_rot = (-6 * a, 9 * k * a, -6 * k * a)
    C.look(P, pitch=-10 * a, yaw=-22 * k * a, roll=14 * k * a)
    P.throat = 18 * C.track([(0, 0.0), (3, 1.0), (10, 0.6), (15, 0.0)], f)
    P.jaw = 8 * C.track([(0, 0.0), (3, 1.0), (7, 0.0)], f)
    P.tail_spread = 0.3 * w
    C.tail_flick(P, f, 1, amp=8, dur=8)
    for s in SIDES:
        near = (s == side)
        P.wings[s] = R.WingPose(fold=1.0 - (0.30 if near else 0.26) * w, arm=1.0 - 0.36 * w,
                                elev=(30 if near else 24) * w)
    return _fin(P)


# ================================================================================================= death
_DEAD = {}


def _dead_legs(P, sd):
    """stiff legs extended back toward the belly side, carried by the body; toes curled"""
    for s in SIDES:
        sx = 1.0 if s == "L" else -1.0
        tgt = C.body_to_root(P, Vector((sx * 0.045, 0.075, 0.005)))
        P.legs[s] = R.LegPose(tgt, 0.0, 1.0, local=1.0)
    C.fit_thigh(RIG, P, lo=0.12, hi=0.168)
    return P


def _dead_pose(side):
    """lying on `side` ('L' / 'R'); cached per side (it needs LOD2 evaluations)"""
    if side in _DEAD:
        return _DEAD[side]
    k = 1.0 if side == "R" else -1.0             # roll + = the right side down
    P = C.stand()
    P.body_rot = (10.0, 86.0 * k, 8.0 * k)
    P.body_off = Vector((0.06 * k * -1, -0.03, -0.12))
    # neck and head drop to the ground (down = toward the lying side: yaw to the bird's right for 'R')
    C.look(P, pitch=18, yaw=-38 * k, roll=-20 * k)
    P.jaw = 6.0
    P.tailbase = (0, 6 * k, 0)
    P.tail_spread = 0.1
    for s in SIDES:
        up = (s != side)
        P.wings[s] = R.WingPose(fold=0.88 if up else 0.95, elev=8 if up else 0)
    C.settle_body(RIG, P, legs_fn=lambda Q: _dead_legs(Q, side), target=-0.003)
    _DEAD[side] = P
    return P


def _tip_pose(side):
    """mid-collapse (f6): the body tipped forward and half onto its side, legs buckling"""
    k = 1.0 if side == "R" else -1.0
    D = _dead_pose(side)
    P = R.blend(C.stand(), D, 0.45)
    P.body_rot = (32.0, 38.0 * k, 4.0 * k)
    P.body_off = Vector((D.body_off.x * 0.4, -0.02, -0.05))
    C.look(P, pitch=20, yaw=-10 * k, roll=-10 * k)
    for s in SIDES:
        P.legs[s] = R.LegPose(C.rest_mtp(s) + Vector((0, 0.0, 0.0)), 0.0, 0.3)
    return P


def death(f, side, N=DEATH_N):
    D = _dead_pose(side)
    k = 1.0 if side == "R" else -1.0
    tilt = C.stand()
    C.look(tilt, pitch=8, yaw=-6 * k, roll=-12 * k)
    tip = _tip_pose(side)
    # bounce: the body lifts 1.2 cm and rolls back a little after the impact (f10), settles by f18, final by f28
    bounce = D.copy()
    bounce.body_off = D.body_off + Vector((0, 0, 0.012))
    bounce.body_rot = (D.body_rot[0] + 3, D.body_rot[1] - 8 * k, D.body_rot[2])
    C.look(bounce, pitch=-10, roll=6 * k)
    settle = D.copy()
    settle.body_off = D.body_off + Vector((0, 0, 0.002))
    C.look(settle, pitch=3)
    keys = [(0, C.stand()), (2, tilt), (6, tip), (10, D), (13, bounce), (18, settle), (28, D)]
    P = C.timeline(keys, f, lift=0.0)
    # legs: planted until the collapse, then carried by the body (stiff, extended) - blended over f4-10
    lg = C.track([(0, 0.0), (4, 0.0), (10, 1.0)], f)
    # toes: world-flat while planted, then carried by the tarsus (LegPose.local). Blended slowly (f4-20): faster, the
    # body roll spins the toes about their own axis (> 25 deg/f); slower, they twist > 90 deg against the tarsus
    lc = C.track([(0, 0.0), (4, 0.0), (20, 1.0)], f)
    Q = P.copy()
    _dead_legs(Q, side)
    for s in SIDES:
        rest = C.rest_mtp(s)
        tgt = rest.lerp(Q.legs[s].mtp, lg)
        P.legs[s] = R.LegPose(tgt, 0.0, lg, R.lerp(0.0, Q.legs[s].thigh, lg), local=lc)
    # a last twitch of the legs and wing at f30-36
    tw = C.track([(30, 0.0), (32, 1.0), (36, 0.0)], f)
    if tw:
        for s in SIDES:
            P.legs[s].mtp = P.legs[s].mtp + Vector((0, 0.008 * tw, 0))
    return C.fit_thigh(RIG, P, lo=0.12, hi=0.168)


# ================================================================================================= build / QA
QA_EXTRA = {"Death_L": dict(ends="start"), "Death_R": dict(ends="start")}


def build(rig):
    global RIG
    RIG = rig
    _DEAD.clear()
    spec = [("Attack", ATTACK_N, attack, False),
            ("Hit_L", HIT_N, lambda f: hit(f, "L"), False), ("Hit_R", HIT_N, lambda f: hit(f, "R"), False),
            ("Death_L", DEATH_N, lambda f: death(f, "L"), False), ("Death_R", DEATH_N, lambda f: death(f, "R"), False)]
    out = []
    for name, n, fn, loop in spec:
        rig.make_clip(name, n, fn, loop=loop)
        out.append(name)
    return out


def planted_fn(name):
    if name == "Attack":
        return lambda s, f: f <= 12 or f >= 20
    if name in ("Hit_L", "Hit_R"):
        return lambda s, f: True
    if name in ("Death_L", "Death_R"):
        return lambda s, f: f <= 4
    return None


if __name__ == "__main__":
    C.run_family(sys.modules[__name__], os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(HERE))),
                                                     "build", "raven", "stage_b.blend"))
