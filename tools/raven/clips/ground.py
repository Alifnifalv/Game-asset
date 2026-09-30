"""Raven ground clips (spec 6.3 / 6.6, GiM timings): Idle, Idle_Look, Caw, Eat, Drink, Walk, Walk_IP, Hop, Hop_IP,
Turn_L90, Turn_R90.

Boundaries: every clip starts and ends on stand() exactly (root-relative), except Walk / Walk_IP: an alternating walk
has no frame with both feet planted side by side, so the walk loop starts in its own double-support phase (upper body
= stand() + the walk lean); QA_EXTRA exempts it (a Walk_Start / Walk_Stop pair would bridge, spec 6.6).

Feet: planted feet are pinned in WORLD space (clips._common.FootTrack / set_foot) and converted to the root frame each
frame, so root motion (Walk, Hop, the turns' yaw) never slides them; fit_thigh() swings the femur only where a foot
target would leave the comfortable knee-to-foot window (stand() is untouched).

  python3 tools/raven/clips/ground.py --in <stage_b.blend> [--out-dir <scratch>] [--only Walk,Hop] [--no-ground]
"""
import math, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE))
import bpy  # noqa: F401,E402
from mathutils import Vector  # noqa: E402
import raven_anim as R  # noqa: E402
import _common as C  # noqa: E402

TAU = 2 * math.pi
SIDES = R.SIDES
RIG = None                     # the RavenRig of the current build (set by build(); fit_thigh / bill solves need it)

IDLE_N, LOOK_N, CAW_N, EAT_N, DRINK_N = 120, 180, 45, 96, 90
WALK_N, WALK_STRIDE = 30, 0.16
HOP_N, HOP_DIST, HOP_APEX = 20, 0.30, 0.068
TURN_N = 30


def _sx(s):
    return 1.0 if s == "L" else -1.0


def _fin(P):
    """final touch of every ground pose: femur fit (no-op on stand())"""
    return C.fit_thigh(RIG, P)


# ================================================================================================= idles
def idle(f, N=IDLE_N):
    """breathing (2 breaths), two small saccades with a slow head raise/lower, a tail flick"""
    t = f / N
    P = C.stand()
    C.breathe(P, t, 1.0, rate=2)
    p, y, r = C.track([(0, (0, 0, 0)), (26, (0, 0, 0)), (30, (-8, 16, 5)), (66, (-8, 16, 5)), (70, (6, -8, -4)),
                       (98, (6, -8, -4)), (106, (0, 0, 0))], f)
    C.look(P, pitch=p + 3 * math.sin(TAU * t), yaw=y, roll=r)
    C.tail_flick(P, f, 84, amp=9, dur=8)
    return P


def idle_look(f, N=LOOK_N):
    """5 saccades (3-5 f) left / right / tilted / up, holds of 26-35 f, the body follows the big turns a little"""
    t = f / N
    P = C.stand()
    C.breathe(P, t, 1.0, rate=3)
    keys = [(0, (0, 0, 0)), (12, (0, 0, 0)), (16, (-6, 48, 14)), (48, (-6, 48, 14)), (52, (4, -32, -16)),
            (80, (4, -32, -16)), (84, (-14, 18, 20)), (110, (-14, 18, 20)), (115, (8, -66, -10)),
            (150, (8, -66, -10)), (155, (0, -4, 0)), (168, (0, 0, 0))]
    p, y, r = C.track(keys, f)
    C.look(P, pitch=p, yaw=y, roll=r)
    P.eyes = (0.0, 0.15 * y)
    by = C.track([(0, 0.0), (20, 0.0), (40, 5.0), (60, -3.0), (100, 1.5), (125, -6.0), (160, 0.0)], f)
    P.body_rot = (0.0, 0.0, by)
    C.tail_flick(P, f, 118, amp=7, dur=8)
    return P


# ================================================================================================= caw
def caw(f, N=CAW_N):
    """f0-8 bow (body +15 deg, neck forward), f8-14 the bill opens to 30 deg with the hackles puffed and a tail flick
    down, hold 8 f, closed by f30, back by f45"""
    P = C.stand()
    b = C.track([(0, 0.0), (8, 1.0), (24, 1.0), (40, 0.0)], f)
    P.body_rot = (15 * b, 0, 0)
    P.body_off = Vector((0, -0.006 * b, -0.004 * b))
    P.neck = {"Neck1": (14 * b, 0, 0), "Neck2": (6 * b, 0, 0), "Neck3": (-8 * b, 0, 0)}
    call = C.track([(0, 0.0), (8, 0.0), (14, 1.0), (22, 1.0), (30, 0.0)], f)
    P.head = (-22 * b - 6 * call, 0, 0)
    P.jaw = 30 * call
    P.throat = 22 * C.track([(0, 0.0), (8, 0.0), (13, 1.0), (25, 1.0), (34, 0.0)], f)
    tl = C.track([(0, 0.0), (8, 0.0), (11, 1.0), (20, 1.0), (32, 0.0)], f)
    P.tailbase = (-10 * tl, 0, 0)                         # + lifts the tail: the call flicks it down
    P.tail = (-4 * tl, 0, 0)
    for s in SIDES:                       # the wings stay folded (a loosened fold lifts the covert block as plates)
        P.wings[s] = R.WingPose(fold=1.0)
    return _fin(P)


# ================================================================================================= eat / drink
_KEY_CACHE = {}


def _bow_pose(pitch, drop, tail, tip_z, bill):
    """body pitched nose-down by `pitch` about the COG and lowered by `drop` (more ankle flex); the tail lifted by
    `tail` deg relative to the body (- = lowered back toward the horizontal); the neck swung down and the head pitched
    so that the bill points `bill` deg (- = down) with its lowest tip at tip_z"""
    P = C.stand()
    P.body_rot = (pitch, 0, 0)
    P.body_off = Vector((0, -0.004, -drop))
    P.tailbase = (tail, 0, 0)
    P.tail = (0.3 * tail, 0, 0)
    C.fit_thigh(RIG, P)
    return C.solve_bill(RIG, P, tip_z, bill)


def _head_back(angle, pitch=-6.0):
    """upright, head tipped back so that the bill axis points `angle` deg above horizontal (drinking swallow)"""
    P = C.stand()
    P.body_rot = (pitch, 0, 0)
    P.neck = {"Neck1": (-8, 0, 0), "Neck2": (-4, 0, 0), "Neck3": (0, 0, 0)}
    C.fit_thigh(RIG, P)
    # bill_angle decreases as pitch (bill down) increases: solve on -angle
    Q, x = C.solve_look(RIG, P, lambda rig, p: -C.bill_angle(rig, p), -angle, lo=-120, hi=40)
    return Q


def _keys():
    if not _KEY_CACHE:
        _KEY_CACHE["eat_down"] = _bow_pose(52, 0.014, -18, 0.0015, -74)
        _KEY_CACHE["drink_down"] = _bow_pose(56, 0.016, -12, -0.006, -64)
        _KEY_CACHE["drink_40"] = _head_back(40)
        _KEY_CACHE["drink_15"] = _head_back(15, pitch=-3)
    return _KEY_CACHE


def eat(f, N=EAT_N):
    """lower 12; bill on the ground 36 (2 opens of 8 f, gape 17 deg, small tugs); jerk up 9 with a sideways flick;
    swallow gape 6; upright look 33"""
    K = _keys()
    up = C.stand()
    down = K["eat_down"]
    keys = [(0, up), (12, down), (48, down), (57, up), (96, up)]
    P = C.timeline(keys, f, lift=0.0)
    # tugs while the bill is on the ground (pitch - = the bill up: the tip lifts a little, never digs in)
    if 12 <= f <= 48:
        u = (f - 12) / 36
        tug = max(0.0, math.sin(TAU * 3 * u)) ** 2
        C.look(P, pitch=-5 * tug * math.sin(math.pi * u), yaw=3 * math.sin(TAU * 2 * u) * math.sin(math.pi * u))
    P.jaw = 17 * (C.track([(18, 0.0), (21, 1.0), (23, 1.0), (26, 0.0)], f) if f < 30
                  else C.track([(34, 0.0), (37, 1.0), (39, 1.0), (42, 0.0)], f))
    # the jerk up overshoots (head raised) with a small sideways flick, then the swallow and a look around
    lift = C.track([(48, 0.0), (55, 1.0), (60, 0.6), (66, 0.0)], f)
    flick = C.track([(50, 0.0), (53, 1.0), (57, -0.4), (62, 0.0)], f)
    look_y = C.track([(63, 0.0), (67, 22.0), (80, 22.0), (84, -8.0), (90, 0.0)], f)
    C.look(P, pitch=-12 * lift, yaw=9 * flick + look_y, roll=6 * flick)
    sw = C.track([(57, 0.0), (60, 1.0), (63, 0.0)], f)
    P.jaw += 10 * sw
    P.throat += 14 * C.track([(58, 0.0), (61, 1.0), (66, 0.0)], f)
    C.breathe(P, f / N, 0.6, rate=1)
    return _fin(P)


def drink(f, N=DRINK_N):
    """lower 12; dip 27 (bill tip 0.6 cm below z=0, the deepest bow, tail up); raise 15; bill +40 deg easing to +15
    over 24 f with 2 gulps; return 12"""
    K = _keys()
    up = C.stand()
    keys = [(0, up), (12, K["drink_down"]), (39, K["drink_down"]), (54, K["drink_40"]), (78, K["drink_15"]),
            (90, up)]
    P = C.timeline(keys, f, lift=0.0)
    if 12 <= f <= 39:                                     # scooping: small forward-back bill motion (lifts only)
        u = (f - 12) / 27
        C.look(P, pitch=-4 * math.sin(math.pi * u) ** 2 * (0.5 + 0.5 * math.cos(TAU * 3 * u)))
        P.jaw = 6 * math.sin(math.pi * u) ** 2
    gulp = C.track([(56, 0.0), (59, 1.0), (63, 0.0), (66, 0.0), (69, 1.0), (73, 0.0)], f)
    P.jaw += 7 * gulp
    P.throat += 16 * gulp
    return _fin(P)


# ================================================================================================= walk
def _walk_tracks():
    """world plants of one stride with a constant root speed; swing L f0-8, R f15-23 (8 f each, long double
    support); a foot is under the hip (root-frame y = 0) at mid stance"""
    v = WALK_STRIDE / WALK_N
    tr = {}
    for s, (a, b) in (("L", (0, 8)), ("R", (15, 23))):
        m = rest = C.rest_mtp(s)
        plants = []
        for j in range(-2, 3):
            f_on, f_off = b + WALK_N * j - WALK_N, a + WALK_N * j
            mid = 0.5 * (f_on + f_off)
            plants.append((f_on, f_off, (rest.x, -v * mid - 0.004, rest.z), 0.0))
        del m
        tr[s] = C.FootTrack(plants, lift=0.030, grip=0.7)
    return tr


_WALK = {}


def walk(f, ip=False, N=WALK_N):
    """1 stride of 0.16 m (0.16 m/s): back lowered to ~24 deg (body +10 nose-down), head bob per step with a forward
    thrust at each touchdown, lateral sway +-1.2 cm per stride, tail parallel to the back"""
    tr = _WALK.setdefault("tr", _walk_tracks())
    v = WALK_STRIDE / N
    P = C.stand()
    P.root_pos = Vector((0, -v * f, 0))
    ph = TAU * (f - 19) / N                      # 0 at the L mid stance
    ph2 = TAU * 2 * (f - 4) / N                  # 0 at each mid stance (per step)
    P.body_off = Vector((0.012 * math.cos(ph), -0.004, -0.008 + 0.004 * math.cos(ph2)))
    P.body_rot = (10 + 1.0 * math.cos(ph2), -3.0 * math.cos(ph), 4.0 * math.sin(ph))
    # head: level against the lean, thrust forward (neck extends, bill dips) just after each touchdown (f8, f23)
    thrust = math.cos(TAU * 2 * (f - 10) / N)
    P.neck = {"Neck1": (4 * thrust, 0, 0), "Neck2": (2 * thrust, 0, 0), "Neck3": (-3 * thrust, 0, 0)}
    C.look(P, pitch=-10 - 3 * thrust, yaw=-4 * math.sin(ph), roll=2 * math.cos(ph))
    P.tailbase = (-3 + 2 * math.cos(ph2), 3 * math.sin(ph), 0)
    for s in SIDES:
        pos, yaw, grip, _pl = tr[s].at(f)
        C.set_foot(P, s, pos, yaw, grip)
    P = _fin(P)
    if ip:
        P.root_pos = Vector((0, 0, 0))          # the legs are already in the root frame: same root-relative motion
    return P


# ================================================================================================= hop
def _hop_root_y(f):
    return -HOP_DIST * R.smoother((f - 5) / 14.0)


def _hop_air(f):
    """0..1 through the air phase (f8 take-off .. f16 touchdown), None on the ground"""
    return (f - 8) / 8.0 if 8 < f < 16 else None


def _hop_body_z(f):
    if f <= 8:
        return C.track([(0, 0.0), (5, -0.024), (8, 0.012)], f)
    if f < 16:
        u = (f - 8) / 8.0                        # ballistic: through 0.012 (f8) and 0.016 (f16), apex HOP_APEX
        z0, z1 = 0.012, 0.016
        return (1 - u) * z0 + u * z1 + 4 * (HOP_APEX - 0.5 * (z0 + z1)) * u * (1 - u)
    return C.track([(16, 0.016), (18, -0.016), (20, 0.0)], f)


def hop(f, ip=False, N=HOP_N):
    """two-footed hop of 0.30 m: crouch 5, push-off 3, air 8 (apex 6.8 cm, wings twitch half open), land 4"""
    P = C.stand()
    ry = _hop_root_y(f)
    P.root_pos = Vector((0, ry, 0))
    bz = _hop_body_z(f)
    pitch = C.track([(0, 0.0), (5, 14.0), (8, 4.0), (12, -4.0), (16, 6.0), (18, 8.0), (20, 0.0)], f)
    P.body_rot = (pitch, 0, 0)
    P.body_off = Vector((0, 0, bz))
    hd = C.track([(0, 0.0), (5, 1.0), (8, -0.4), (12, -0.6), (16, 0.6), (18, 0.4), (20, 0.0)], f)
    C.look(P, pitch=-pitch * 0.8 + 6 * hd)
    w = C.track([(0, 0.0), (7, 0.0), (10, 1.0), (13, 0.8), (17, 0.0)], f)
    for s in SIDES:
        P.wings[s] = R.WingPose(fold=1.0 - 0.38 * w, elev=38 * w, sweep=-4 * w)   # a half-open twitch
    P.tailbase = (8 * C.track([(0, 0.0), (7, 0.0), (10, 1.0), (15, 0.3), (18, 1.0), (20, 0.0)], f), 0, 0)
    P.tail_spread = 0.25 * w
    air = _hop_air(f)
    for s in SIDES:
        rest = C.rest_mtp(s)
        if air is None:
            wy = 0.0 if f <= 8 else -HOP_DIST
            C.set_foot(P, s, (rest.x, wy, rest.z))
        else:
            # root-frame path from the take-off spot (behind) to the landing spot (just ahead), tucked up in between
            y0 = 0.0 - _hop_root_y(8)
            y1 = -HOP_DIST - _hop_root_y(16)
            e = R.smoother(air)
            h = 0.050 * math.sin(math.pi * air)
            P.legs[s] = R.LegPose(Vector((rest.x, R.lerp(y0, y1, e), rest.z + h + 0.0 * bz)), 0.0,
                                  0.8 * math.sin(math.pi * air))
    P = _fin(P)
    if ip:
        P.root_pos = Vector((0, 0, 0))
    return P


# ================================================================================================= turns
def _turn_setup(sign):
    """2 steps: the inside foot first (f5-13), then the other (f15-23); root yaw 0 -> 90 over f3-25"""
    first, second = ("L", "R") if sign > 0 else ("R", "L")
    tr = {}
    for s, (a, b) in ((first, (5, 13)), (second, (15, 23))):
        r = C.rest_mtp(s)
        c, sn = math.cos(math.radians(90 * sign)), math.sin(math.radians(90 * sign))
        end = (r.x * c - r.y * sn, r.x * sn + r.y * c, r.z)
        tr[s] = C.FootTrack([(-10, a, (r.x, r.y, r.z), 0.0), (b, 40, end, 90.0 * sign)], lift=0.028, grip=0.7)
    return tr


_TURN = {}


def _turn_yaw(f, sign):
    return 90.0 * sign * R.smoother((f - 3) / 22.0)


def turn(f, sign, N=TURN_N):
    """turn 90 deg on the spot in 2 steps; the head leads the body by 4 f"""
    tr = _TURN.setdefault(sign, _turn_setup(sign))
    P = C.stand()
    P.root_yaw = _turn_yaw(f, sign)
    lead = 90.0 * sign * R.smoother(f / 22.0) - P.root_yaw        # the head's turn runs 3-4 f ahead
    step = C.track([(0, 0.0), (5, 1.0), (23, 1.0), (28, 0.0)], f)
    P.body_rot = (6 * step, 0, 0.25 * lead)
    P.body_off = Vector((0, 0, -0.005 * step))
    C.look(P, pitch=-5 * step, yaw=0.75 * lead, roll=0.12 * lead)
    P.tailbase = (0, -0.08 * lead, 0)
    for s in SIDES:
        pos, yaw, grip, _pl = tr[s].at(f)
        C.set_foot(P, s, pos, yaw, grip)
    return _fin(P)


# ================================================================================================= build / QA
QA_EXTRA = {"Walk": dict(boundary=None), "Walk_IP": dict(boundary=None)}
_PLANTED = {}


def build(rig):
    global RIG
    RIG = rig
    _KEY_CACHE.clear(); _WALK.clear(); _TURN.clear()
    out = []
    spec = [("Idle", IDLE_N, idle, True), ("Idle_Look", LOOK_N, idle_look, True), ("Caw", CAW_N, caw, False),
            ("Eat", EAT_N, eat, True), ("Drink", DRINK_N, drink, True),
            ("Walk", WALK_N, lambda f: walk(f), True), ("Walk_IP", WALK_N, lambda f: walk(f, ip=True), True),
            ("Hop", HOP_N, lambda f: hop(f), True), ("Hop_IP", HOP_N, lambda f: hop(f, ip=True), True),
            ("Turn_L90", TURN_N, lambda f: turn(f, 1.0), False), ("Turn_R90", TURN_N, lambda f: turn(f, -1.0), False)]
    for name, n, fn, loop in spec:
        rig.make_clip(name, n, fn, loop=loop)
        out.append(name)
    return out


def planted_fn(name):
    if name in ("Idle", "Idle_Look", "Caw", "Eat", "Drink"):
        return lambda s, f: True
    if name == "Walk":
        tr = _WALK.setdefault("tr", _walk_tracks())
        return lambda s, f: tr[s].planted(f)
    if name == "Hop":
        return lambda s, f: f <= 8 or f >= 16
    if name in ("Turn_L90", "Turn_R90"):
        tr = _TURN.setdefault(1.0 if name == "Turn_L90" else -1.0, _turn_setup(1.0 if name == "Turn_L90" else -1.0))
        return lambda s, f: tr[s].planted(f)
    return None                                  # the _IP twins slide by definition


if __name__ == "__main__":
    import raven_anim as _R  # noqa: F401
    C.run_family(sys.modules[__name__], os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(HERE))),
                                                     "build", "raven", "stage_b.blend"))
