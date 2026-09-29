"""Raven flight clips (spec 2.4, 6.3, 6.6; GiM video 16.8-23.4 s, stills 0a423e61 / f6338d68).

  ASSET=raven python3 tools/raven/clips/flight.py [--in <stage_b.blend>] [--out-dir <scratch>] [--only Fly,Glide]

Naming (spec 6.6): the plain name has ROOT MOTION, `_IP` is its in-place twin (Root still; exported as its own clip).
  Fly / Fly_IP                loop 20 f. One cruise beat (_common.flap): downstroke 10.4 f fully extended, upstroke
                              9.6 f with the wrist flexed, the hand swept back and the slots open; 128 deg amplitude;
                              body bob 1 cm. Fly: Root forward (-Y) at 8 m/s.
  Glide / Glide_IP            loop 120 f. Wings near flat, fingers slotted and curled up, tail half spread, +-1.5 cm
                              float twice per loop, small primary flex / tail and roll trims. Glide: 8 m/s.
  Glide_Bank_L / _R           loop 60 f, root motion: a HELD coordinated 28 deg bank about the flight path (yaw rate
                              g tan(bank) / V = 37 deg/s at 8 m/s, radius 12.3 m, 75 deg per loop), inner wing
                              slightly flexed and lowered, tail twisted into the turn, head level and looking into the
                              turn. Meant as blend-tree / cross-fade partners of Glide (the roll-in is the blend), so
                              they start and end on the banked pose, NOT on fly_neutral (QA_EXTRA boundary None).
  TakeOff                     one-shot 45 f from stand(): crouch 6 (the wings unfold and rise while crouching), spring
                              + first downstroke (the feet leave at f10), 2 climbing beats (tops f7, f21, f40; downstrokes
                              6 f), legs trailing then tucked; ends on fly_neutral() at Fly's phase (mid-downstroke) with
                              Fly's 8 m/s. Root: 5.1 m forward, 1.3 m up.
  Land                        one-shot 45 f from fly_neutral() (8 m/s, Glide / Fly speed): glide-in, flare (body up
                              to 50 deg, tail spread and down, legs forward, toes open), 2 braking beats, touchdown at
                              f32, fold and settle onto stand() by f45. Root: 4.8 m forward, 1.2 m down.

Boundaries: Fly / Glide (and their _IP twins) start and end on fly_neutral() (QA_EXTRA boundary 'fly'): they start at
the mid-downstroke (flap_neutral_phase), where flap() adds nothing, and every glide trim is 0 at f0. TakeOff starts on
stand() and ends on fly_neutral(); Land the reverse. raven_animations checks one reference per clip, so the second end
is checked here (BOUNDARY2 lines; build() raises when it is off by more than 0.01 mm).
Root-motion continuity: TakeOff ends at Fly's 8 m/s (vertical speed 0) and Land starts at 8 m/s (level).

QA printed by build() (information): FEATHERS = the deepest remex mid-point / tip inside the trunk SDF over the clip
(carried by the Hips; the folded stand() wing itself reads +7.3 mm: keep every clip at or below that). The flap keeps
the inner wing off the flank with a pronation that grows through the lower half of the downstroke (the tertials
otherwise swing 5 cm into the flank at the bottom), and passes 30 % of an up-stroke's elevation (10 % down) to
Shoulder.X so the scapulars follow the raised wing (shoulder_share).
Wing-ground clearance (run_family's GROUND, feathers): TakeOff >= 6 cm (a shallower first downstroke), Land >= 3.6 cm
(a shallower second braking beat).
"""
import math, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
import bpy  # noqa: F401,E402
from mathutils import Quaternion, Vector  # noqa: E402
import raven_anim as R  # noqa: E402
import _common as C  # noqa: E402

FPS = R.FPS
V_FLY = 8.0                     # m/s, Fly / Glide / the end of TakeOff / the start of Land
G = 9.81
FLY_N = 20
GLIDE_N = 120
BANK_N = 60
BANK_DEG = 28.0
TAKEOFF_N = 45
LAND_N = 45
LIFTOFF = 10                    # TakeOff: the feet leave the ground
TOUCHDOWN = 32                  # Land: the feet touch
TAKEOFF_RISE, TAKEOFF_RUN = 1.30, 5.1
LAND_DROP = 1.20                # the Land run (4.8 m) follows from the speed profile (land_speed)
TAU = 2 * math.pi

QA_EXTRA = {
    "Fly": dict(boundary="fly"), "Fly_IP": dict(boundary="fly"),
    "Glide": dict(boundary="fly"), "Glide_IP": dict(boundary="fly"),
    # the banks are held (blend-tree children of Glide): their ends are the banked pose, not fly_neutral
    "Glide_Bank_L": dict(boundary=None), "Glide_Bank_R": dict(boundary=None),
    "TakeOff": dict(boundary="stand", ends="start"),
    "Land": dict(boundary="fly", ends="start"),
}
SECOND_END = {"TakeOff": ("end", "fly"), "Land": ("end", "stand")}


def planted_fn(name):
    if name == "TakeOff":
        return lambda s, f: 0 <= f <= LIFTOFF
    if name == "Land":
        return lambda s, f: TOUCHDOWN <= f <= LAND_N
    return None


# ------------------------------------------------------------------------------------------------ helpers
def attitude(pitch, bank=0.0, heading=0.0):
    """body_rot (pitch, roll, yaw) for raven_anim.body_matrix = Rz(yaw) Rx(pitch) Ry(-roll): the trunk pitched `pitch`
    (+ = nose down, from the rest pose), then banked `bank` deg about the WORLD flight path (Y; + = right wing down)
    and turned `heading` (+ = left). (body_rot's own roll turns about the pitched trunk axis, 28 deg off the path.)"""
    M = R.Rz(heading) @ R.Ry(-bank) @ R.Rx(pitch)
    e = M.to_3x3().to_euler("YXZ")                     # matrix = Rz(z) Rx(x) Ry(y)
    return (math.degrees(e.x), -math.degrees(e.y), math.degrees(e.z))


def hermite(p0, v0, p1, v1, u, T):
    """cubic Hermite at u in [0, 1] between (p0, v0) and (p1, v1); velocities per second, T = duration (s)"""
    u2, u3 = u * u, u * u * u
    return ((2 * u3 - 3 * u2 + 1) * p0 + (u3 - 2 * u2 + u) * v0 * T + (-2 * u3 + 3 * u2) * p1
            + (u3 - u2) * v1 * T)


def root_to_body(P, v):
    """inverse of raven_anim.body_point: a root-frame point -> the rest body frame of pose P"""
    M = R.T(P.body_off) @ R.T(R.COG) @ R.body_matrix(*P.body_rot) @ R.T(-R.COG)
    return (M.inverted() @ Vector(v).to_4d()).to_3d()


def ramp(f, f0, f1):
    """smootherstep 0 -> 1 over [f0, f1]"""
    return R.smoother((f - f0) / (f1 - f0)) if f1 > f0 else float(f >= f1)


def wing_mix(w0, w1, t_arm, t_elbow, t_wrist, t_feath, t_rest):
    """per-channel blend of two WingPoses: the fold amounts on their own timing (the wing unfolds joint by joint),
    the shoulder / feather channels on t_rest"""
    L = R.lerp
    return R.WingPose(fold=0.0, arm=L(w0.get("arm"), w1.get("arm"), t_arm),
                      elbow=L(w0.get("elbow"), w1.get("elbow"), t_elbow),
                      wrist=L(w0.get("wrist"), w1.get("wrist"), t_wrist),
                      feathers=L(w0.get("feathers"), w1.get("feathers"), t_feath),
                      elev=L(w0.elev, w1.elev, t_rest), sweep=L(w0.sweep, w1.sweep, t_rest),
                      twist=L(w0.twist, w1.twist, t_rest), spread=L(w0.spread, w1.spread, t_rest),
                      slot=L(w0.slot, w1.slot, t_rest), finger_up=L(w0.finger_up, w1.finger_up, t_rest),
                      hand_twist=L(w0.hand_twist, w1.hand_twist, t_rest))


def flapped_wing(phase, **kw):
    """the fly_neutral wing with one flap() applied (both sides equal)"""
    P = R.fly_neutral()
    C.flap(P, phase, bob=0.0, **kw)
    return P.wings["L"]


def unfold(f, f0, f1, w_open, reverse=False):
    """the folded stand() wing opening to w_open over [f0, f1] (or closing when reverse): the arm lifts off the flank
    first, then the elbow and the wrist open and the wing rises, the feathers fan last (no pop, no feather through
    the flank)"""
    d = f1 - f0
    if reverse:                                # closing: time runs backwards through the opening
        f = f0 + f1 - f
    t = lambda a, b: ramp(f, f0 + a * d, f0 + b * d)
    return wing_mix(R.WingPose(fold=1.0), w_open, t(0.0, 0.65), t(0.10, 0.80), t(0.20, 0.95), t(0.25, 1.0),
                    t(0.10, 1.0))


def stabilise_head(P, body_pitch, ref_pitch, k=0.85):
    """keep the head near level when the trunk pitches away from ref_pitch (+ = nose down)"""
    return C.look(P, pitch=-(body_pitch - ref_pitch) * k)


class Signs:
    """FK-probed signs (per rig): head roll that lifts the left eye, tail roll that lowers the left rectrices"""

    def __init__(self, rig):
        def z_of(P, bone, tail=True):
            M = rig.solve(P)
            m = M[bone]
            return (m @ Vector((0, rig.length[bone] if tail else 0, 0, 1))).z

        def headx(P):
            M = rig.solve(P)
            return M["Head"].to_3x3().col[0].z * (1 if M["Head"].to_3x3().col[0].x > 0 else -1)
        P0 = R.fly_neutral()
        P1 = R.fly_neutral(); P1.head = (P1.head[0], P1.head[1], 10.0)
        # + when a + head roll raises the bird's LEFT side of the head
        self.head_roll = 1.0 if headx(P1) > headx(P0) else -1.0
        P2 = R.fly_neutral(); P2.tailbase = (0, 0, 10.0)
        # + when a + tail roll LOWERS the left rectrices
        self.tail_roll = 1.0 if z_of(P2, "Rect6.L") < z_of(P0, "Rect6.L") else -1.0
        print(f"[flight] signs: head roll {self.head_roll:+.0f} (left up), tail roll {self.tail_roll:+.0f} (left down)")


SHOULDER_UP, SHOULDER_DOWN = 0.30, 0.10   # share of the wing elevation taken by Shoulder.X (the scapular tract)


def shoulder_share(rig, P, base_elev=R.FLY_WING["elev"], k=1.0):
    """move part of each wing's elevation (relative to base_elev) from the humerus to Shoulder.X, so the scapulars
    and the marginal coverts lift with a raised wing instead of the covert block lifting off them (the wing direction
    is unchanged: both turn about the body's long axis)"""
    for s in R.SIDES:
        w = P.wings[s]
        e = w.elev - base_elev
        a = k * e * (SHOULDER_UP if e > 0 else SHOULDER_DOWN)
        if abs(a) < 1e-9:
            continue
        w.elev -= a
        sx = 1.0 if s == "L" else -1.0
        Rs = rig.rest[f"Shoulder.{s}"].to_3x3()
        Rw = Quaternion((0, -1, 0), R.rad(a) * sx).to_matrix()
        q = (Rs.inverted() @ Rw @ Rs).to_quaternion()
        P.extra[f"Shoulder.{s}"] = q
    return P


# ------------------------------------------------------------------------------------------------ Fly
def fly_pose(f, rm=True, rig=None):
    P = R.fly_neutral()
    C.flap(P, C.flap_neutral_phase() + f / FLY_N)
    if rig is not None:
        shoulder_share(rig, P)
    if rm:
        P.root_pos = Vector((0, -V_FLY * f / FPS, 0))
    return P


# ------------------------------------------------------------------------------------------------ Glide
def glide_pose(f, rm=True, rig=None):
    """fly_neutral + small periodic trims (every term is 0 at f0 and periodic in 120 f)"""
    P = R.fly_neutral()
    t = f / GLIDE_N
    s2, c2 = math.sin(TAU * 2 * t), 1 - math.cos(TAU * 2 * t)          # 2 floats per loop (60 f = 2 s)
    s1 = math.sin(TAU * t)
    s3 = 1 - math.cos(TAU * 3 * t)
    P.body_off = P.body_off + Vector((0, 0, 0.015 * s2))
    P.body_rot = attitude(28.0 + 1.0 * s2, 1.8 * s1)             # pitch and roll trims
    for sd, sg in (("L", 1.0), ("R", -1.0)):
        w = P.wings[sd]
        w.elev += 1.5 * c2 + 1.2 * sg * s1                    # dihedral 2-5 deg, the roll trim on the wings
        w.finger_up += 2.5 * s3                                 # the fingertips flex under the gusts
        w.twist += -1.0 * s2
        w.sweep += 1.5 * s2
    P.tail_spread += 0.05 * c2
    P.tailbase = (1.5 * s2, 0.0, 2.5 * s1)
    C.look(P, pitch=-1.0 * s2, yaw=6.0 * s1)
    if rig is not None:
        shoulder_share(rig, P)
    if rm:
        P.root_pos = Vector((0, -V_FLY * f / FPS, 0))
    R.tuck_legs(P)
    return P


# ------------------------------------------------------------------------------------------------ Glide_Bank
def bank_pose(f, side, sg, rm=True, rig=None):
    """held coordinated bank (side 'L' = left turn = left wing down)"""
    P = R.fly_neutral()
    t = f / BANK_N
    k = 1.0 if side == "L" else -1.0
    bank = -k * BANK_DEG + 1.0 * math.sin(TAU * t)             # + = right wing down
    omega = math.degrees(G * math.tan(math.radians(BANK_DEG)) / V_FLY)   # deg/s
    P.body_off = P.body_off + Vector((0, 0, 0.008 * math.sin(TAU * t)))
    P.body_rot = attitude(28.0, bank, 0.0)
    inner, outer = (side, "R" if side == "L" else "L")
    wi, wo = P.wings[inner], P.wings[outer]
    wi.arm, wi.elbow, wi.wrist, wi.feathers = 0.04, 0.10, 0.16, 0.08      # the inner wing slightly flexed
    wi.elev -= 3.0; wi.sweep -= 4.0; wi.finger_up += 4.0
    wo.elev += 2.0; wo.twist += 2.0; wo.finger_up += 2.0
    for w in (wi, wo):
        w.finger_up += 2.0 * math.sin(TAU * 2 * t)
    P.tail_spread = R.FLY_TAIL_SPREAD + 0.07                 # the turn opens the fan a little more
    P.tailbase = (0.0, 0.0, sg.tail_roll * 12.0 * k)          # tail twisted into the turn
    C.look(P, yaw=6.0 * k, roll=sg.head_roll * BANK_DEG * k)      # the head stays (near) level
    R.tuck_legs(P)
    if rig is not None:
        shoulder_share(rig, P)
    if rm:
        yaw = k * omega * f / FPS
        rad = V_FLY / math.radians(omega)
        a = math.radians(yaw)
        # the path: start heading -Y, turning around the centre (k * rad, 0): to the bird's left (+X) for L
        P.root_pos = Vector((k * rad * (1 - math.cos(a)), -rad * math.sin(abs(a)), 0.0))
        P.root_yaw = yaw
    return P


# ------------------------------------------------------------------------------------------------ TakeOff
T_TOPS = (7.0, 21.0, TAKEOFF_N - 0.5 * C.FLAP_DOWN * FLY_N)   # wing tops: 14 f, then 18.8 f (the last = Fly timing)
TO_DOWN = 6.0                                                   # take-off downstrokes (spec 6.3: about 6 f)
TO_ELEV = dict(up_elev=64.0, down_elev=68.0, pron=26.0)
TO_DOWN1 = 42.0                                                 # the first (ground-effect) downstroke


def takeoff_phase(f):
    """(phase, down fraction, flap kwargs) of the take-off beats; None before the first top"""
    t1, t2, t3 = T_TOPS
    if f < t1:
        return None
    if f < t2:          # the first downstroke is shallower: the bird is still within 20 cm of the ground
        return (f - t1) / (t2 - t1), TO_DOWN / (t2 - t1), dict(TO_ELEV, fold_up=0.55, down_elev=TO_DOWN1)
    if f < t3:
        return (f - t2) / (t3 - t2), TO_DOWN / (t3 - t2), dict(TO_ELEV, fold_up=0.60)
    return (f - t3) / FLY_N, C.FLAP_DOWN, {}


TO_V0 = (0.60, 0.80)            # root speed (forward, up; m/s) at the lift-off = the speed the leg push reaches


def takeoff_root(f):
    if f <= LIFTOFF:
        return Vector((0, 0, 0))
    T = (TAKEOFF_N - LIFTOFF) / FPS
    u = (f - LIFTOFF) / (TAKEOFF_N - LIFTOFF)
    y = hermite(0.0, TO_V0[0], TAKEOFF_RUN, V_FLY, u, T)
    z = hermite(0.0, TO_V0[1], TAKEOFF_RISE, 0.0, u, T)
    return Vector((0, -y, z))


TO_CROUCH, TO_LAUNCH = Vector((0, 0.012, -0.032)), Vector((0, -0.020, 0.008))


def takeoff_body_off(f):
    """Hips offset of the take-off: the crouch (f0-6, eased), then the leg push (f6 -> LIFTOFF) as a Hermite from rest
    to the root's lift-off speed TO_V0, so the body carries its velocity into the launch (a C.track key at the lift-off
    would stop it there for a frame), then (after the lift-off, the root carrying the speed) eased to the flight offset"""
    if f <= 6:
        return Vector(C.track([(0, (0, 0, 0)), (6, tuple(TO_CROUCH))], f))
    if f <= LIFTOFF:
        T = (LIFTOFF - 6) / FPS
        u = (f - 6) / (LIFTOFF - 6)
        v1 = (0.0, -TO_V0[0], TO_V0[1])                       # root frame: forward = -Y
        return Vector([hermite(TO_CROUCH[i], 0.0, TO_LAUNCH[i], v1[i], u, T) for i in range(3)])
    return Vector(C.track([(LIFTOFF, tuple(TO_LAUNCH)), (20, (0, 0, 0.05)), (TAKEOFF_N, (0, 0, 0.05))], f))


def takeoff_pose(rig, f):
    S, F = R.stand(), R.fly_neutral()
    wb = ramp(f, 4, 30)                                      # neck / head / tail carriage: stand -> flight
    P = R.blend(S, F, wb)
    pitch = C.track([(0, 0.0), (10, 24.0), (16, 20.0), (30, 22.0), (TAKEOFF_N, 28.0)], f)
    P.body_rot = (pitch, 0.0, 0.0)
    P.body_off = takeoff_body_off(f)
    stabilise_head(P, pitch, R.lerp(0.0, 28.0, wb), k=0.6)
    C.look(P, pitch=-8.0 * math.sin(math.pi * ramp(f, 0, 10)))            # looks up and ahead on the spring
    # wings
    ph = takeoff_phase(f)
    if ph is None:
        w_top = flapped_wing(0.0, **dict(TO_ELEV, fold_up=0.55), down=TO_DOWN / (T_TOPS[1] - T_TOPS[0]))
        for s in R.SIDES:
            P.wings[s] = unfold(f, 0.0, T_TOPS[0], w_top)
    else:
        phase, down, kw = ph
        for s in R.SIDES:
            P.wings[s] = F.wings[s].copy()
        C.flap(P, phase, down=down, bob=0.0, **kw)
    # tail: spread and pressed down in the take-off downstrokes, half spread at the end
    fan = C.track([(0, 0.0), (6, 0.5), (10, 1.0), (30, 0.9), (TAKEOFF_N, R.FLY_TAIL_SPREAD)], f)
    P.tail_spread = fan
    press = C.track([(0, 0.0), (8, 12.0), (30, 6.0), (TAKEOFF_N, 0.0)], f)
    P.tailbase = (P.tailbase[0] + press, P.tailbase[1], P.tailbase[2])
    shoulder_share(rig, P, k=ramp(f, 1, T_TOPS[0]))
    # root
    P.root_pos = takeoff_root(f)
    # legs: planted until the lift-off (thigh fitted to the reach), then trailing and tucked
    if f <= LIFTOFF:
        for s in R.SIDES:
            P.legs[s] = R.LegPose(C.rest_mtp(s), grip=0.0)
        C.fit_thigh(rig, P)
    else:
        P0 = takeoff_pose(rig, LIFTOFF)
        wl = ramp(f, LIFTOFF, 30)
        for s in R.SIDES:
            # the foot leaves the ground where the body carried it at the lift-off, trails a little, then tucks
            hang = R.body_point(P, root_to_body(P0, C.rest_mtp(s)) + Vector((0, 0.015, 0.02)) * ramp(f, LIFTOFF, 18))
            tuck = R.body_point(P, R._side(R.FLY_TUCK, s))
            P.legs[s] = R.LegPose(hang.lerp(tuck, wl), grip=ramp(f, LIFTOFF, 18),
                                  thigh=R.lerp(P0.legs[s].thigh, R.FLY_TUCK_THIGH, wl))
    return P


# ------------------------------------------------------------------------------------------------ Land
L_TOPS = (18.0, 25.0, float(TOUCHDOWN))       # the braking beats: 7 f each, the wings up at the touchdown
L_DOWN = 3.5
L_ELEV = dict(up_elev=58.0, down_elev=50.0, fold_up=0.35)
L_DOWN_ELEV = (50.0, 32.0)
L_BRAKE = R.WingPose(elev=4.0, sweep=14.0, twist=-4.0, finger_up=14.0, slot=10.0, spread=6.0)


def land_root(f):
    if f >= TOUCHDOWN:
        f = TOUCHDOWN
    # speed 8 m/s held to f4, then smootherstep down to 0 at the touchdown (integrated per frame, exact)
    y = 0.0
    for k in range(int(math.floor(f))):
        y += 0.5 * (land_speed(k) + land_speed(k + 1)) / FPS
    fr = f - math.floor(f)
    if fr > 0:
        k = math.floor(f)
        y += 0.5 * (land_speed(k) + land_speed(k + fr)) * fr / FPS
    u = f / TOUCHDOWN
    z = hermite(LAND_DROP, 0.0, 0.0, -0.4, u, TOUCHDOWN / FPS)
    return Vector((0, -y, z))


def land_speed(f):
    return V_FLY * (1.0 - ramp(f, 4, TOUCHDOWN))


def land_pose(rig, f):
    S, F = R.stand(), R.fly_neutral()
    wb = ramp(f, 30, LAND_N)                                 # carriage: flight -> stand after the touchdown
    P = R.blend(F, S, wb)
    pitch = C.track([(0, 28.0), (8, 22.0), (16, -18.0), (28, -22.0), (TOUCHDOWN, -12.0), (36, 8.0), (41, -2.0),
                     (LAND_N, 0.0)], f)
    P.body_rot = (pitch, 0.0, 0.0)
    P.body_off = Vector(C.track([(0, (0, 0, 0.05)), (16, (0, 0.02, 0.04)), (28, (0, 0.03, 0.02)),
                                 (TOUCHDOWN, (0, 0.02, 0.0)), (36, (0, -0.004, -0.028)), (41, (0, 0, 0.004)),
                                 (LAND_N, (0, 0, 0))], f))
    stabilise_head(P, pitch, R.lerp(28.0, 0.0, wb), k=0.75)
    # wings: glide-in, flare (the wings rise and sweep forward), 2 braking beats, then fold
    t1, t2, t3 = L_TOPS
    if f < t1:
        e = ramp(f, 6, t1)
        brake_top = _brake_wing(0.0)
        for s in R.SIDES:
            P.wings[s] = wing_mix(F.wings[s], brake_top, e, e, e, e, e)
    elif f <= t3:
        phase = (f - t1) / 7.0
        for s in R.SIDES:           # the second braking beat is shallower: the feet are about to touch
            P.wings[s] = _brake_wing(phase % 1.0 if f < t3 else 0.0, L_DOWN_ELEV[0 if f < t2 else 1])
    else:
        for s in R.SIDES:
            P.wings[s] = unfold(f, t3, LAND_N - 1, _brake_wing(0.0), reverse=True)
    # tail: spread and pressed down in the flare
    P.tail_spread = C.track([(0, R.FLY_TAIL_SPREAD), (12, 1.0), (TOUCHDOWN, 1.0), (40, 0.1), (LAND_N, 0.0)], f)
    press = C.track([(0, 0.0), (14, 18.0), (TOUCHDOWN, 14.0), (38, -6.0), (LAND_N, 0.0)], f)
    P.tailbase = (P.tailbase[0] + press, P.tailbase[1], P.tailbase[2])
    shoulder_share(rig, P, k=1.0 - ramp(f, L_TOPS[2], LAND_N - 2))
    P.root_pos = land_root(f)
    # legs: tucked -> lowered forward, toes open -> planted at the touchdown
    if f >= TOUCHDOWN:
        for s in R.SIDES:
            P.legs[s] = R.LegPose(C.rest_mtp(s), grip=0.0)
        C.fit_thigh(rig, P)
    else:
        wl = ramp(f, 6, 22)
        wd = ramp(f, 20, TOUCHDOWN)
        PT = land_pose(rig, TOUCHDOWN)
        for s in R.SIDES:
            tuck = R.body_point(P, R._side(R.FLY_TUCK, s))
            fwd = C.rest_mtp(s) + Vector((0, -0.07, 0.03))           # reaching forward, above the touchdown point
            down = C.rest_mtp(s)
            tgt = tuck.lerp(fwd, wl).lerp(down, wd)
            P.legs[s] = R.LegPose(tgt, grip=R.lerp(1.0, 0.1, ramp(f, 8, 20)),
                                  thigh=R.lerp(R.FLY_TUCK_THIGH, PT.legs[s].thigh, ramp(f, 10, TOUCHDOWN)))
    return P


def _brake_wing(phase, down_elev=None):
    P = R.fly_neutral()
    for s in R.SIDES:
        P.wings[s] = L_BRAKE.copy()
    kw = dict(L_ELEV)
    if down_elev is not None:
        kw["down_elev"] = down_elev
    C.flap(P, phase, down=L_DOWN / 7.0, bob=0.0, **kw)
    return P.wings["L"]


# ------------------------------------------------------------------------------------------------ build
def build(rig):
    sg = Signs(rig)
    names = []
    for name, rm in (("Fly", True), ("Fly_IP", False)):
        rig.make_clip(name, FLY_N, lambda f, rm=rm: fly_pose(f, rm=rm, rig=rig), loop=True)
        names.append(name)
    for name, rm in (("Glide", True), ("Glide_IP", False)):
        rig.make_clip(name, GLIDE_N, lambda f, rm=rm: glide_pose(f, rm=rm, rig=rig), loop=True)
        names.append(name)
    for side in "LR":
        name = f"Glide_Bank_{side}"
        rig.make_clip(name, BANK_N, lambda f, side=side: bank_pose(f, side, sg, rig=rig), loop=True)
        names.append(name)
    rig.make_clip("TakeOff", TAKEOFF_N, lambda f: takeoff_pose(rig, f), loop=False)
    names.append("TakeOff")
    rig.make_clip("Land", LAND_N, lambda f: land_pose(rig, f), loop=False)
    names.append("Land")
    for n in names:
        feather_report(rig, n)
    _check_second_ends(rig, names)
    return names


TRUNK_TAGS = ("trunk", "breast", "mantle", "belly", "vent", "rump")


def feather_depth(rig, P, _cache={}):
    """deepest penetration (m, > 0 = inside) of the remex mid-points and tips into the trunk SDF (rest frame, carried
    by the Hips), and the remex at that depth. The calami are rooted in the wing skin, so only the mid / tip count."""
    import numpy as np
    import raven_anatomy as A
    from sdf import eval_prims
    if "prims" not in _cache:
        _cache["prims"] = [q for q in A.body_prims() if q.op == "add" and q.tag in TRUNK_TAGS]
        _cache["len"] = {r[0]: r[3] for r in A.REMIGES}
    M = rig.solve(P)
    Hi = (M["Hips"] @ rig.rest["Hips"].inverted()).inverted()
    pts, who = [], []
    for s in R.SIDES:
        for n, L in _cache["len"].items():
            m = M[f"{n}.{s}"]
            for t in (0.5, 1.0):
                pts.append((Hi @ m @ Vector((0, L * t, 0, 1))).to_3d()[:])
                who.append(f"{n}.{s}@{t}")
    d = eval_prims(_cache["prims"], np.array(pts))
    i = int(np.argmin(d))
    return -float(d[i]), who[i]


def feather_report(rig, name):
    poses = rig.clip_poses[name]
    worst = (-1.0, "", 0)
    for f, P in enumerate(poses):
        d, w = feather_depth(rig, P)
        if d > worst[0]:
            worst = (d, w, f)
    base = max(feather_depth(rig, R.stand())[0], feather_depth(rig, R.fly_neutral())[0])
    print(f"FEATHERS {name}: deepest remex mid/tip into the trunk {worst[0] * 1000:+.1f} mm ({worst[1]}, f{worst[2]}); "
          f"stand/fly_neutral {base * 1000:+.1f} mm")
    return worst


def _check_second_ends(rig, names):
    import raven_animations as RA
    bad = []
    for name in names:
        if name not in SECOND_END:
            continue
        which, ref = SECOND_END[name]
        e0, e1 = RA.boundary_error(rig, bpy.data.actions[name], R.stand() if ref == "stand" else R.fly_neutral())
        e = e1 if which == "end" else e0
        print(f"BOUNDARY2 {name}: {which} {e:.4f} mm vs {ref}")
        if e > 0.01:
            bad.append(f"{name} {which} {e:.4f} mm vs {ref}")
    if bad:
        raise RuntimeError("flight boundary: " + "; ".join(bad))


if __name__ == "__main__":
    os.environ.setdefault("ASSET", "raven")
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE))))
    import asset_profile as AP  # noqa: E402
    C.run_family(sys.modules[__name__], os.path.join(AP.BUILD, "stage_b.blend"))
