"""Lying family: LieDown (150 f), Lying_Idle (150 f loop), GetUp (150 f). No root motion (Root stays at the origin).

python3 tools/clips/lying.py [--in build/stage_b.blend] [--out <scratch>/test.blend] [--scratch DIR]
                             [--render all|none|Clip,Clip] [--step 4]
builds the clips on the rig, prints QA and saves the blend:
  * anim_lib IK gap / planted fetlock slide, locked-knee slide, hoof-pivot (toe/heel contact) slide;
  * JOINT: baked joint angles about the side axis (carpus, fore/hind fetlock, stifle, hock), with the limits below;
  * GROUND: Calf_LOD2 mesh min z of body / hoof vertices (planted and swinging hooves);
  * INSIDE: LOD1 ray-parity test of fore cannons/hooves inside the body skin in LYING;
  * POP: bone-head acceleration spikes; SEAM: exact joins between the clips and against a make_clip(Pose()) frame.
Renders root-tracking filmstrips + GIFs (tools/render_clip.py, left and three-quarter views) unless --render none.

Biomechanics (cattle)
  * Lying down is FRONT end first. The calf sniffs the spot and rocks its weight back, fore legs braced forward. The
    left fore rolls onto its toe, lifts and folds, and the chest drops onto that carpus (front knee); meanwhile the
    loaded right fore rolls onto its toe. Then the right carpus goes down. The hindquarters sink down and back onto the
    RIGHT hip: the hocks travel back and down to the ground (hooves planted) until the rump is down, then the hind
    hooves are lifted into the lying spots. The chest follows the forearms back onto the sternum. Finally each fore
    leg is stretched forward, as in the GiM reference (28-40 s: both fore legs forward, the right hoof under the chin).
  * Getting up is HIND end first. The fore legs are folded back under onto the knees. The hind hooves are lifted and
    gathered beside/behind the belly while the pelvis unrolls. The calf lunges forward on its knees while the hind legs
    lift the rump; with the rump up each hind hoof steps forward under the hips. Then it rolls onto the right knee,
    steps the left fore forward (toe first), pushes, steps the right fore (toe first), rises and stands.
  * The carpus bends so the cannon folds BACKWARD (a kneeling cannon lies on the ground behind the knee, hoof flipped
    toe-back); the hock bends the other way.
  * Weight-bearing contacts never slide. Standing hooves are fixed at their toe (or heel) contact point: a loaded hoof
    that has to tilt rolls about that point (`pivots`) instead of hyperextending the fetlock. Kneeling carpi stay on
    fixed ground points (`knee_points`); the knee lock in `clip_fn` solves body height (+ roll for two knees) every frame
    so each elbow stays a forearm length from its contact. `reach_guard` lowers the body if the keys ever ask a loaded
    fore leg for more reach than it has (the library would clamp the foot target and lift/slide the hoof).
  * The lying body lies LY_B = 0.40 m behind the standing one (no root motion): the knees land ~11 cm behind the
    fore hooves, so a loaded fore hoof stays ahead of its elbow while the chest is low (lying down and stepping up).

Rig handling that differs from anim_lib.Calf.make_clip (see make_clip_ex)
  * The IK poles are keyed per frame (the PoleTarget bones are unweighted helpers, dropped at export). A free fore leg
    keeps its pole anterior to the elbow->fetlock line (the rest offset rotated by the leg's sagittal swing), so the
    carpus always flexes the anatomical way, also with the leg stretched forward (the Body-parented rest pole flips it).
    A kneeling leg gets a pole in the plane (elbow, fetlock, knee contact): the knee lands exactly on its contact
    whatever the body roll. Hind poles rotate with the stifle->fetlock line the same way (no hock flip when folded).
  * `leg_state` predicts the baked IK analytically (same poles; knees within 0.03 mm, hocks within 1.2 mm of the
    bake). Key poses are solved against it: knee contacts, loaded elbow distance, fore fetlock angle, hock height
    (`solve_femur`) and hind joint limits (`fit_femur`).

Joint limits used here (angle about the side axis; 0 = straight; the rest pose values in brackets)
  fore fetlock >= -65 deg when loaded [-31]; carpus <= 25 deg on a loaded standing leg [10.4]; stifle bend <= 140 deg [60];
  hock bend >= -150 deg [-52].
"""
import copy, math, os, sys
import numpy as np
import bpy
from mathutils import Vector, Matrix

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)
import anim_lib as A
from anim_lib import Pose, LEGS

FRONT = ("LF", "RF")
HIND = ("LH", "RH")
X_AX = Vector((1, 0, 0))
R_KNEE = 0.040          # carpus joint height when the knee rests on the ground (m)
R_FETLOCK = 0.034       # fetlock joint height when the cannon lies on the ground (m)
KNEEL_FLEX = 115.0      # hoof flex while the fore cannon lies on the ground behind the carpus (toe points back)
HIP_ROLL = -14.0        # Back (pelvis) roll when lying: right hip down (spine roll + = LEFT side down)
LY_B = 0.40             # the lying body lies this far back (+Y) of the standing body (knees land behind the hooves)
# hoof sole contact points (rest armature space, attached to the toe bone): toe tip and heel bulb
TOE_Y = {"F": -0.405, "H": 0.364}
HEEL_Y = {"F": -0.352, "H": 0.424}
SOLE_Z = 0.002
FETLOCK_MIN = -65.0     # loaded fore fetlock dorsiflexion limit (deg)
CARPUS_STAND_MAX = 25.0
STIFLE_MAX = 140.0
HOCK_MIN = -150.0       # hock bend limit (tibia/metatarsus at least 30 deg apart) [rest -52, LYING -144]


# ============================================================================ small helpers
def cp(P):
    return copy.deepcopy(P)


def fk(calf, P):
    """armature-space bone matrices of pose P (legs at their un-solved FK; tops/feet/body exact)"""
    calf.pose_to_basis(P)
    return calf._last_pose


def rest_foot(calf, leg):
    return calf.rest_head(LEGS[leg]["foot"])


def set_foot(calf, P, leg, world):
    """absolute armature-space fetlock target, stored as a root-frame offset (root never moves here)"""
    P.feet[leg] = Vector(world) - rest_foot(calf, leg)


def foot_world(calf, P, leg):
    return rest_foot(calf, leg) + P.feet.get(leg, Vector((0, 0, 0)))


def L1(calf, leg):
    return calf.bones[LEGS[leg]["chain"][0]].length


def L2(calf, leg):
    return calf.bones[LEGS[leg]["chain"][1]].length


def elbow_name(leg):
    return LEGS[leg]["chain"][0]


_DOF = {"x": ("body_off", 0), "y": ("body_off", 1), "z": ("body_off", 2),
        "pitch": ("body_rot", 0), "roll": ("body_rot", 1), "yaw": ("body_rot", 2)}


def _bump(P, dof, v):
    if dof.startswith("femur:"):
        leg = dof[6:]
        P.femur = dict(P.femur); P.femur[leg] = P.femur.get(leg, 0.0) + v
        return
    attr, i = _DOF[dof]
    vec = getattr(P, attr).copy(); vec[i] += v; setattr(P, attr, vec)


def solve_body(calf, P, residual_fns, dofs, iters=14, tol=1e-5):
    """Gauss-Newton on body DOFs (x y z pitch roll yaw, femur:<leg>) so that every residual_fn(P) -> 0.
    Residuals take the pose (they call fk / leg_state themselves)."""
    def res(Q):
        return np.array([f(Q) for f in residual_fns])
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


def sang(u, v, ax=X_AX):
    """signed angle (deg) from u to v about axis ax (both projected on the plane normal to ax)"""
    u = u - ax * u.dot(ax); v = v - ax * v.dot(ax)
    return math.degrees(math.atan2(u.cross(v).dot(ax), u.dot(v)))


# ============================================================================ hooves
def hoof_local(calf, leg, which):
    """rest armature-space point of the hoof sole attached to the toe bone: 'toe' tip or 'heel' bulb"""
    x = rest_foot(calf, leg).x
    return Vector((x, (TOE_Y if which == "toe" else HEEL_Y)[leg[1]], SOLE_Z))


def hoof_offset(calf, leg, flex, which):
    """vector fetlock -> hoof point `which` for hoof flex `flex` (anim_lib: the pastern turns by flex, the toe bone
    by another 0.35 flex, both about X; root yaw is 0 in this family)"""
    h = rest_foot(calf, leg); t = calf.rest_head(LEGS[leg]["toe"])
    R1 = Matrix.Rotation(math.radians(flex), 3, "X"); R2 = Matrix.Rotation(math.radians(1.35 * flex), 3, "X")
    return R1 @ (t - h) + R2 @ (hoof_local(calf, leg, which) - t)


def pivot_point(calf, leg, which="toe"):
    """world position of the hoof contact point of a hoof standing at rest"""
    return rest_foot(calf, leg) + hoof_offset(calf, leg, 0.0, which)


def foot_on_pivot(calf, leg, point, flex, which="toe"):
    """foot-track value (fetlock offset, flex) that puts hoof point `which` at world `point`"""
    F = Vector(point) - hoof_offset(calf, leg, flex, which)
    return (F - rest_foot(calf, leg), flex)


# ============================================================================ IK poles + analytic leg solve
def anterior_pole(calf, leg, E, F):
    """front pole for a free leg: the rest pole offset rotated about the elbow by the leg's sagittal swing, so it stays
    anterior to the elbow->fetlock line (the carpus flexes the anatomical way whatever the leg direction)"""
    d = LEGS[leg]
    e0 = calf.rest_head(d["chain"][0])
    rel = calf.rest_head(d["pole"]) - e0
    v = F - E; v0 = rest_foot(calf, leg) - e0
    ang = math.atan2(-v.y, -v.z) - math.atan2(-v0.y, -v0.z)
    return E + Matrix.Rotation(-ang, 3, "X") @ rel


def hind_pole(calf, leg, S, F):
    """hind pole: the rest pole offset rotated about the stifle by the sagittal swing of the stifle->fetlock line, so
    the hock never flips when the leg folds forward (the Body-parented rest pole can end up behind the line)"""
    d = LEGS[leg]
    s0 = calf.rest_head(d["chain"][0])
    rel = calf.rest_head(d["pole"]) - s0
    v = F - S; v0 = rest_foot(calf, leg) - s0
    ang = math.atan2(-v.y, -v.z) - math.atan2(-v0.y, -v0.z)
    return S + Matrix.Rotation(-ang, 3, "X") @ rel


def knee_pole(E, F, K):
    """pole in the plane (elbow, fetlock, knee contact), on the knee's side"""
    u = (F - E).normalized(); w = K - E; w = w - u * w.dot(u)
    return K + w.normalized() * 0.5


def front_pole(calf, P, leg, E, F):
    pole = anterior_pole(calf, leg, E, F)
    kn = getattr(P, "kneel", {}).get(leg)
    if kn and kn[1] > 0:
        pole = pole.lerp(knee_pole(E, F, kn[0]), kn[1])
    return pole


def two_bone(E, F, a_len, b_len, side_pt, toward=True):
    v = F - E; d = max(1e-6, v.length); u = v / d
    a = (a_len ** 2 - b_len ** 2 + d * d) / (2 * d); h = math.sqrt(max(0.0, a_len ** 2 - a * a))
    w = side_pt - E; w = w - u * w.dot(u); w.normalize()
    return E + u * a + (w if toward else -w) * h


def leg_state(calf, P):
    """Analytic prediction of the baked leg IK of pose P (same poles as make_clip_ex): per leg the joint positions
    and the joint angles about the side axis (deg, 0 = straight): fore carpus/fetlock, hind stifle/hock/fetlock."""
    calf.pose_to_basis(P)
    M = calf._last_pose; feet = calf._last_feet
    out = {}
    for leg, d in LEGS.items():
        F = feet[leg].copy()
        fl = P.flex.get(leg, 0.0)
        pastern = Matrix.Rotation(math.radians(fl), 3, "X") @ (calf.rest[d["foot"]].to_3x3() @ Vector((0, 1, 0)))
        toe = F + hoof_offset(calf, leg, fl, "toe"); heel = F + hoof_offset(calf, leg, fl, "heel")
        if leg in FRONT:
            E = M[d["chain"][0]].translation.copy()
            K = two_bone(E, F, L1(calf, leg), L2(calf, leg), front_pole(calf, P, leg, E, F), True)
            out[leg] = dict(E=E, K=K, F=F, toe=toe, heel=heel, carpus=sang(K - E, F - K), fetlock=sang(F - K, pastern),
                            reach=(F - E).length / calf.chain_len[leg])
        else:
            hip = M[d["top"]].translation.copy(); S = M[d["chain"][0]].translation.copy()
            H = two_bone(S, F, L1(calf, leg), L2(calf, leg), hind_pole(calf, leg, S, F), False)
            out[leg] = dict(hip=hip, S=S, H=H, F=F, toe=toe, heel=heel, stifle=sang(S - hip, H - S),
                            hock=sang(H - S, F - H), fetlock=sang(F - H, pastern), reach=(F - S).length / calf.chain_len[leg])
    out["M"] = M
    return out


def solve_femur(calf, P, leg, hock_z, iters=12):
    """femur swing (P.femur[leg]) that puts the hind hock at height hock_z (the hock travels on the circle around the
    fetlock; more femur = stifle forward = hock lower)"""
    P.femur = dict(P.femur); P.femur.setdefault(leg, 0.0)
    for _ in range(iters):
        z0 = leg_state(calf, P)[leg]["H"].z - hock_z
        if abs(z0) < 1e-5:
            break
        P.femur[leg] += 0.2
        z1 = leg_state(calf, P)[leg]["H"].z - hock_z
        P.femur[leg] -= 0.2
        if abs(z1 - z0) < 1e-9:
            break
        P.femur[leg] -= max(-15.0, min(15.0, z0 * 0.2 / (z1 - z0)))
    return P


def fit_femur(calf, P, leg, hock_min=HOCK_MIN + 4.0, stifle_max=STIFLE_MAX - 4.0, hock_z=0.03, span=40.0):
    """smallest change of the femur swing that keeps the hind leg inside its joint limits (hock bend >= hock_min,
    stifle bend <= stifle_max) with the hock at least hock_z above the ground; scans +-span deg in 0.5 deg steps"""
    P.femur = dict(P.femur); f0 = P.femur.get(leg, 0.0)
    best = None
    for k in range(int(2 * span) + 1):
        for sg in ((1,) if k == 0 else (1, -1)):
            P.femur[leg] = f0 + sg * 0.5 * k
            st = leg_state(calf, P)[leg]
            if st["hock"] >= hock_min and st["stifle"] <= stifle_max and st["H"].z >= hock_z:
                best = P.femur[leg]
                break
        if best is not None:
            break
    if best is None:
        print(f"  fit_femur {leg}: no femur swing within +-{span:.0f} deg meets the hind joint limits (kept {f0:.1f})")
    P.femur[leg] = f0 if best is None else best
    return P


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


def lifted(a, b, t=0.5, lift=0.03, flex=None):
    """foot-track value between a and b (fraction t), raised by `lift` (swing keys: no dragging along the ground)"""
    v = (a[0].lerp(b[0], t) + Vector((0, 0, lift)), a[1] + (b[1] - a[1]) * t if flex is None else flex)
    return v


def in_plan(plan, leg, f):
    return any(a <= f <= b for a, b in plan.get(leg, ()))


POLE_RAMP = 4           # frames over which the pole blends between the free and the kneeling rule


def lock_weight(lock, leg, f):
    w = 0.0
    for a, b in lock.get(leg, ()):
        if a <= f <= b:
            return 1.0
        if a - POLE_RAMP < f < a:
            w = max(w, A.ease((f - (a - POLE_RAMP)) / POLE_RAMP))
        if b < f < b + POLE_RAMP:
            w = max(w, A.ease(1 - (f - b) / POLE_RAMP))
    return w


def reach_guard(calf, P, legs, cap=0.0):
    """Loaded fore legs must not be asked for more reach than they have at rest (anim_lib would clamp the target
    toward the elbow and the planted hoof would lift/slide). Where the keyed elbow-fetlock distance d exceeds the
    cap D0, lower the body (z; + roll for two legs) to a C1 soft limit: d' = d - (d - D0)^2 / (4 w) for
    d < D0 + 2 w, else D0 + w. D0 = lerp(rest distance, D_STAND x chain, cap): at cap 0 standing frames at rest
    are unchanged; at cap 1 a loaded hoof stays below the library's clamp (0.9985 x chain since c4fbcaa; it was
    0.992, when Pose() held the fore hooves ~2 mm up)."""
    over = {}
    for leg in legs:
        d = (fk(calf, P)[elbow_name(leg)].translation - foot_world(calf, P, leg)).length
        D0 = A.lerp(_rest_reach(calf, leg), D_STAND * calf.chain_len[leg], cap); w = 0.0005 * calf.chain_len[leg]
        if d > D0 + 1e-7:
            over[leg] = d - (d - D0) ** 2 / (4 * w) if d < D0 + 2 * w else D0 + w
    if over:
        res = [(lambda Q, leg=leg, t=t: (fk(calf, Q)[elbow_name(leg)].translation - foot_world(calf, Q, leg)).length - t)
               for leg, t in over.items()]
        solve_body(calf, P, res, ["z"] if len(res) == 1 else ["z", "roll"])
    return P


def _rest_reach(calf, leg):
    key = ("reach", id(calf), leg)
    if key not in _CACHE:
        _CACHE[key] = (calf.rest_head(elbow_name(leg)) - rest_foot(calf, leg)).length
    return _CACHE[key]


def clip_fn(calf, body_keys, foot_keys, lock, pivots=None, overlays=(), planted=None, guard_cap=None):
    """pose function of a clip: whole-pose Hermite keys for body/head/tail, independent Hermite tracks per foot
    (so planted feet hold exactly while the body moves), hoof pivots (within [a, b] the fetlock follows from a fixed
    toe/heel contact and the track's flex), overlays, then the knee lock: while front `leg` is in a lock interval its
    carpus is held on the shared ground contact (fetlock target from the contact; body z, plus roll when both knees
    are down, solved so each elbow stays a forearm length from its contact). Keys at lock start/end frames satisfy
    the lock already, so it switches on/off without a pop."""
    body = hermite(body_keys, A.pose_combine)
    feet = {leg: hermite(k, _foot_combine) for leg, k in foot_keys.items()}
    pivots = pivots or {}
    planted = planted or {}

    def fn(f):
        P = body(f)
        for leg, tr in feet.items():
            P.feet[leg], P.flex[leg] = tr(f)
        for leg, ivs in pivots.items():
            for a, b, which, pt, *_ in ivs:
                if a <= f <= b:
                    P.feet[leg] = foot_on_pivot(calf, leg, pt, P.flex[leg], which)[0]
        for ov in overlays:
            P = ov(f, P)
        loaded = [leg for leg in FRONT if in_plan(planted, leg, f) or
                  any(iv[0] <= f <= iv[1] and (len(iv) < 5 or iv[4]) for iv in pivots.get(leg, ()))]
        if loaded and not any(in_plan(lock, leg, f) for leg in FRONT):
            reach_guard(calf, P, loaded, guard_cap(f) if guard_cap else 0.0)
        P.kneel = {leg: (knee_points(calf)[leg], lock_weight(lock, leg, f)) for leg in FRONT if lock_weight(lock, leg, f) > 0}
        legs = [leg for leg in FRONT if in_plan(lock, leg, f)]
        if legs:
            solve_body(calf, P, [knee_res(calf, leg) for leg in legs], ["z"] if len(legs) == 1 else ["z", "roll"])
            for leg in legs:
                kneel_leg(calf, P, leg)
        return P
    return fn


# ============================================================================ clip writer (anim_lib make_clip + poles)
def make_clip_ex(calf, name, frames, pose_fn, loop=False):
    """anim_lib.Calf.make_clip (no reach pass) that also keys the PoleTarget bones (front_pole / hind_pole) before
    the IK bake. At Pose() the poles land on their rest position, so standing frames equal a make_clip(Pose()) frame."""
    act = calf.new_action(name)
    poses = [pose_fn(f) for f in range(frames + 1)]
    chain_bones = [n for d in LEGS.values() for n in d["chain"]]
    for pb in calf.arm.pose.bones:
        pb.matrix_basis = Matrix.Identity(4)
    samples = {n: [] for n in calf.order if n not in chain_bones}
    for P in poses:
        B = calf.pose_to_basis(P)
        M = calf._last_pose
        for leg, d in LEGS.items():
            if leg in FRONT:
                pos = front_pole(calf, P, leg, M[d["chain"][0]].translation, calf._last_feet[leg])
            else:
                pos = hind_pole(calf, leg, M[d["chain"][0]].translation, calf._last_feet[leg])
            B[d["pole"]] = calf.basis_for(d["pole"], M, Matrix.Translation(pos) @ calf.rest[d["pole"]].to_3x3().to_4x4())
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
        ae = calf.arm.evaluated_get(bpy.context.evaluated_depsgraph_get())
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


# ============================================================================ residuals (key-pose solving)
def knee_res(calf, leg):
    K = knee_points(calf)[leg]; l1 = L1(calf, leg); n = elbow_name(leg)
    return lambda P: (fk(calf, P)[n].translation - K).length - l1


def elbow_ahead_res(calf, leg, dy):
    """elbow `dy` behind (+) the knee contact"""
    K = knee_points(calf)[leg]; n = elbow_name(leg)
    return lambda P: fk(calf, P)[n].translation.y - (K.y + dy)


def hip_z_res(calf, z):
    return lambda P: (lambda M: 0.5 * (M["BackLeg.L"].translation.z + M["BackLeg.R"].translation.z) - z)(fk(calf, P))


def shell_res(calf, leg, reach):
    """loaded fore leg: elbow at `reach` x chain length from its planted fetlock (carpus stays near its rest bend)"""
    n = elbow_name(leg)
    return lambda P: (fk(calf, P)[n].translation - foot_world(calf, P, leg)).length - reach * calf.chain_len[leg]


def fetlock_res(calf, leg, deg):
    return lambda P: (leg_state(calf, P)[leg]["fetlock"] - deg) / 100.0


def solve_flex_on_pivot(calf, P, leg, point, fetlock_deg, which="toe", lo=0.0, hi=100.0):
    """hoof flex (rolling about its toe/heel contact `point`) that gives the loaded fore fetlock angle `fetlock_deg`"""
    def g(fl):
        P.feet[leg], P.flex[leg] = foot_on_pivot(calf, leg, point, fl, which)
        return leg_state(calf, P)[leg]["fetlock"] - fetlock_deg
    if g(lo) >= 0:          # already within the limit with the hoof at `lo`
        return P
    for _ in range(40):
        mid = 0.5 * (lo + hi)
        if g(mid) < 0: lo = mid
        else: hi = mid
    g(0.5 * (lo + hi))
    return P


# ============================================================================ shared constant poses
def stand():
    """neutral standing pose == rest (auto_top off everywhere in this family so blends never switch mode)"""
    P = Pose()
    P.auto_top = False
    return P


# (tail values re-expressed for anim_lib's fixed tail swing axis, review A10: same tail shape as before, 0.000 mm)
LYING_TAIL = ((0.0, -8.0), (0.0, -5.0), (0.0, 0.0), (0.0, 5.0), (0.85, 9.96), (9.03, 23.58), (19.08, 24.09))
D_STAND = 0.990         # loaded standing fore leg: elbow-fetlock distance / chain length (rest 0.996, library clamp 0.9985)
EXT_REACH = 0.982       # fore leg stretched forward while lying (carpus ~20 deg, knee slightly up)
EXT_FLEX = -48.0        # its hoof points forward, sole facing forward/down
LY_FEET = {"LH": (0.26, 0.53), "RH": (0.00, 0.53)}     # lying hind fetlocks (x, y); the left hind lies on top
_CACHE = {}


def _lying_body(calf):
    """LYING body, head, tail and hind legs (the fore legs are added by the callers): sternal recumbency, the chest
    upright on the sternum, the pelvis rolled onto the right hip, hind legs folded to the left (left hind on top)."""
    P = stand()
    P.body_rot = Vector((-2.0, 0.0, 0.0))
    P.body_off = Vector((0.0, LY_B, -0.43))
    P.spine = {"Back": (0.0, 0.0, HIP_ROLL), "Torso": (0.0, 0.0, -HIP_ROLL)}
    P.neck = [2.0, 3.0, 2.0]
    P.neck_yaw = [3.0, 3.0, 2.0]
    P.head = Vector((4.0, 3.0, -5.0))
    P.ears = {"L": Vector((-10.0, 12.0, 0.0)), "R": Vector((-10.0, 12.0, 0.0))}
    P.tail = list(LYING_TAIL)
    P.femur = {"LH": 55.0, "RH": 57.0}
    for leg, (x, y) in LY_FEET.items():
        set_foot(calf, P, leg, (x, y, R_FETLOCK + 0.005))     # hoof resting on its dorsal wall at z ~ 0
        P.flex[leg] = -60.0
    return P


def knee_points(calf):
    """Carpus ground contacts shared by every kneeling frame of the family. Derived from the lying body: the carpus
    lies a forearm length ahead of the elbow (forearm folded forward on the ground)."""
    key = ("knees", id(calf))
    if key not in _CACHE:
        M = fk(calf, _lying_body(calf))
        K = {}
        for leg in FRONT:
            E = M[elbow_name(leg)].translation
            dz = E.z - R_KNEE
            K[leg] = Vector((E.x, E.y - math.sqrt(L1(calf, leg) ** 2 - dz * dz), R_KNEE))
        _CACHE[key] = K
    return _CACHE[key]


def carpus_on_ground(calf, P, leg, K):
    """fetlock target that puts the carpus of front `leg` at ground point K (cannon lying backward)."""
    l2 = L2(calf, leg)
    a = math.asin(max(-0.9, min(0.9, (K.z - R_FETLOCK) / l2)))
    set_foot(calf, P, leg, K + l2 * Vector((0, math.cos(a), -math.sin(a))))


def kneel_leg(calf, P, leg):
    """front leg kneeling on its carpus at the shared contact point (the elbow must be L1 from it)"""
    carpus_on_ground(calf, P, leg, knee_points(calf)[leg])
    P.flex[leg] = KNEEL_FLEX
    P.kneel = dict(getattr(P, "kneel", {})); P.kneel[leg] = (knee_points(calf)[leg], 1.0)


def extend_leg(calf, P, leg, reach=EXT_REACH, flex=EXT_FLEX, dx=0.0):
    """fore leg stretched forward on the ground from its current elbow (lying): fetlock `reach` x chain ahead,
    hoof resting on the ground"""
    E = fk(calf, P)[elbow_name(leg)].translation
    z = 0.004 - min(hoof_offset(calf, leg, flex, w).z for w in ("toe", "heel"))
    dist = reach * calf.chain_len[leg]
    dy = math.sqrt(max(0.0, dist * dist - (E.z - z) ** 2 - dx * dx))
    set_foot(calf, P, leg, (E.x + dx, E.y - dy, z))
    P.flex[leg] = flex
    if hasattr(P, "kneel"):
        P.kneel = {k: v for k, v in P.kneel.items() if k != leg}


def lying_folded(calf):
    """lying body with both fore legs folded under the chest (carpi on their contacts): the chest has just
    settled in LieDown; GetUp folds the legs back to it before rising."""
    P = _lying_body(calf)
    for leg in FRONT:
        kneel_leg(calf, P, leg)
    return P


def lying(calf):
    """LYING (LieDown end == Lying_Idle loop pose == GetUp start): sternal recumbency, both fore legs stretched
    forward on the ground (as in the GiM reference), pelvis rolled onto the right hip, hind legs folded to the left,
    head held up level with / above the back (GiM; neck raised, head pitched down to keep the face near vertical)."""
    key = ("lying", id(calf))
    if key not in _CACHE:
        P = _lying_body(calf)
        P.neck = [-9.0, -10.0, -9.0]
        P.head = Vector((18.0, 4.0, -4.0))
        extend_leg(calf, P, "LF", dx=0.015)
        extend_leg(calf, P, "RF", dx=0.045, reach=EXT_REACH - 0.02)    # right hoof tucked in under the chin
        P.kneel = {}
        _CACHE[key] = P
    return cp(_CACHE[key])


# ---------------------------------------------------------------------------- LieDown key poses
def sniff(calf):
    """standing, nose lowered toward the spot (the muzzle reaches the ground later, at the kneeling sniff kn_low in
    lie_down); the head drop comes from the neck, the elbows keep their standing distance to the hooves (loaded
    carpi stay near their rest bend)"""
    P = stand()
    P.body_off = Vector((0.0, 0.02, 0.0))
    P.body_rot = Vector((1.0, 0.0, 0.0))
    P.neck = [14.0, 16.0, 14.0]
    P.head = Vector((16.0, 0.0, 0.0))
    P.ears = {"L": Vector((12.0, 4.0, -8.0)), "R": Vector((12.0, 4.0, -8.0))}
    P.tail = [(0.0, -2.0)] * 7
    solve_body(calf, P, [shell_res(calf, "LF", D_STAND), shell_res(calf, "RF", D_STAND)], ["z", "roll"])
    return P


def rock_back(calf):
    """weight rocks back and onto the right fore (fore legs braced forward), the left fore lifts and folds"""
    P = sniff(calf)
    P.body_off = Vector((0.0, 0.10, P.body_off.z))
    P.body_rot = Vector((3.0, 2.5, 0.0))
    P.neck = [10.0, 12.0, 10.0]
    P.head = Vector((12.0, 0.0, 0.0))
    solve_body(calf, P, [shell_res(calf, "RF", D_STAND)], ["z"])
    K = knee_points(calf)["LF"]
    set_foot(calf, P, "LF", Vector((K.x, -0.29, 0.13)))
    P.flex["LF"] = 75.0
    return P


def kneel_left(calf):
    """left carpus touches down; the right fore still carries the chest, rolled onto its toe"""
    P = rock_back(calf)
    P.body_rot = Vector((10.0, -5.0, 0.0))
    P.neck = [2.0, 4.0, 4.0]
    P.head = Vector((8.0, 0.0, 0.0))
    kneel_leg(calf, P, "LF")
    P.feet["RF"], P.flex["RF"] = Vector((0, 0, 0)), 0.0
    solve_body(calf, P, [knee_res(calf, "LF"), elbow_ahead_res(calf, "LF", 0.06), hip_z_res(calf, 0.66)],
               ["y", "z", "pitch"])
    solve_flex_on_pivot(calf, P, "RF", pivot_point(calf, "RF"), -50.0)
    return P


def kneel(calf, hip=0.64, ahead=0.06):
    """both carpi on the ground, hind legs still standing: the classic kneeling pose"""
    P = kneel_left(calf)
    P.body_rot = Vector((P.body_rot.x, 0.0, 0.0))
    P.neck = [0.0, 2.0, 2.0]
    P.head = Vector((6.0, 0.0, 0.0))
    kneel_leg(calf, P, "RF")
    solve_body(calf, P, [knee_res(calf, "LF"), knee_res(calf, "RF"), elbow_ahead_res(calf, "LF", ahead),
                         hip_z_res(calf, hip)], ["y", "z", "pitch", "roll"])
    return P


def hind_lowering(calf):
    """hindquarters sinking down and back toward the right hip: the hocks travel back and down (hooves planted),
    the chest follows the forearms back"""
    P = kneel(calf)
    P.spine = {"Back": (0.0, 0.0, 0.4 * HIP_ROLL), "Torso": (0.0, 0.0, -0.4 * HIP_ROLL)}
    P.neck = [6.0, 6.0, 4.0]
    P.head = Vector((6.0, 1.0, 0.0))
    P.tail = [(0.0, -10.0), (0.0, -6.0), (0.0, -4.0), (-0.14, 0.0), (-0.02, 0.0), (0.44, -0.03), (0.36, -0.04)]
    solve_body(calf, P, [knee_res(calf, "LF"), knee_res(calf, "RF"), elbow_ahead_res(calf, "LF", 0.14),
                         hip_z_res(calf, 0.50)], ["y", "z", "pitch", "roll"])
    for leg in HIND:
        solve_femur(calf, P, leg, 0.20)
    return P


def rump_down(calf):
    """hindquarters resting on the right hip, hind hooves still where they stood (hocks on the ground behind them),
    chest nearly down"""
    P = lying_folded(calf)
    P.spine = {"Back": (0.0, 0.0, 0.85 * HIP_ROLL), "Torso": (0.0, 0.0, -0.85 * HIP_ROLL)}
    for leg in HIND:
        P.feet[leg] = Vector((0, 0, 0))
        P.flex[leg] = 0.0
    P.neck = [4.0, 4.0, 3.0]
    P.head = Vector((5.0, 2.0, -2.0))
    solve_body(calf, P, [knee_res(calf, "LF"), knee_res(calf, "RF"), elbow_ahead_res(calf, "LF", 0.22)],
               ["y", "z", "roll"])
    for leg in HIND:
        solve_femur(calf, P, leg, 0.10)
    return P


def fore_mid(calf, leg, dy, z, flex, clear=0.025):
    """swing key of a fore leg near its knee contact (dy ahead - / behind + of the contact, fetlock height z, raised
    so the hoof clears the ground by `clear`)"""
    K = knee_points(calf)[leg]
    z = max(z, clear - min(hoof_offset(calf, leg, flex, w).z for w in ("toe", "heel")))
    return (Vector((K.x, K.y + dy, z)) - rest_foot(calf, leg), flex)


# ============================================================================ clips
V0 = Vector((0, 0, 0))


def lie_down(calf, N=150):
    """FRONT end first: sniff the spot, rock back, left carpus down (the loaded right fore rolls onto its toe),
    right carpus down, hindquarters sink onto the right hip (hocks back and down, hooves planted), hind legs lifted
    into the lying spots, chest settles on the sternum, then each fore leg is stretched forward; head comes up."""
    S = stand()
    sn, rb, kl, kn = sniff(calf), rock_back(calf), kneel_left(calf), kneel(calf)
    hl, rd, lf, ly = hind_lowering(calf), rump_down(calf), lying_folded(calf), lying(calf)
    # kneeling sniff: the muzzle comes down to ~4 cm above the ground (f56); the head is already on its way down when
    # the right carpus lands (f48), so the dip into the sniff is no faster than before (trunk/head accel 12 mm/f^2)
    kn_key = cp(kn); kn_key.neck = [5.0, 7.0, 6.0]; kn_key.head = Vector((9.0, -1.0, 1.0))
    kn_low = cp(kn); kn_low.neck = [11.0, 12.0, 11.0]; kn_low.neck_yaw = [-2.0, -2.0, -1.0]; kn_low.head = Vector((14.0, -3.0, 2.0))
    lf_look = cp(lf); lf_look.neck = [4.0, 4.0, 3.0]; lf_look.neck_yaw = [4.0, 5.0, 4.0]; lf_look.head = Vector((8.0, 6.0, -4.0))
    # the head comes up over f112-150 to the high LYING head (not all in the last 16 frames)
    ly_turn = cp(ly); ly_turn.neck = [-3.0, -3.0, -3.0]; ly_turn.neck_yaw = [-2.0, -3.0, -2.0]; ly_turn.head = Vector((11.0, -2.0, -2.0))
    rest = (V0.copy(), 0.0)
    toeL, toeR = pivot_point(calf, "LF"), pivot_point(calf, "RF")
    hind_t0 = {"LH": 85, "RH": 86}
    hind_mid = {leg: lifted(rest, foot_of(lf, leg), 0.5, 0.025, -20.0) for leg in HIND}
    # rump settling while the hind hooves are lifted into the lying spots: femurs keep the hocks off the ground
    settle = A.blend_pose(rd, lf, 0.6)
    settle.auto_top = False          # blend_pose returns a fresh Pose() (auto_top on)
    for leg in HIND:
        settle.feet[leg], settle.flex[leg] = hind_mid[leg]
    solve_body(calf, settle, [knee_res(calf, "LF"), knee_res(calf, "RF")], ["z", "roll"])
    for leg in HIND:
        solve_femur(calf, settle, leg, 0.06)
        fit_femur(calf, settle, leg, hock_min=HOCK_MIN + 9.0)
    # left-fore lift-off: the right elbow stays at its standing distance (the keys must not over-reach the loaded leg)
    lo = A.blend_pose(sn, rb, 0.5); lo.auto_top = False
    lo.feet["LF"], lo.flex["LF"] = foot_on_pivot(calf, "LF", toeL, 22.0)
    solve_body(calf, lo, [shell_res(calf, "RF", D_STAND)], ["z"])
    body = [(0, S, "stop"), (14, sn), (19, lo), (24, rb, "stop"), (34, kl, "stop"), (48, kn_key, "stop"), (56, kn_low, "stop"),
            (70, hl), (84, rd), (93, settle), (98, lf, "stop"), (114, lf_look), (134, ly_turn), (N, ly, "stop")]
    toeL, toeR = pivot_point(calf, "LF"), pivot_point(calf, "RF")
    lift = foot_on_pivot(calf, "LF", toeL, 26.0); lift = (lift[0] + Vector((0.0, 0.015, 0.035)), 34.0)
    feet = {"LF": [(0, rest, "stop"), (14, rest, "stop"), (19, foot_on_pivot(calf, "LF", toeL, 22.0)),
                   (21, lift), (24, foot_of(rb, "LF")), (34, foot_of(kl, "LF"), "stop"), (102, foot_of(lf, "LF"), "stop"),
                   (112, fore_mid(calf, "LF", -0.15, 0.07, 30.0)), (122, foot_of(ly, "LF"), "stop"),
                   (N, foot_of(ly, "LF"), "stop")],
            "RF": [(0, rest, "stop"), (22, rest, "stop"), (34, foot_of(kl, "RF")),
                   (36, foot_on_pivot(calf, "RF", toeR, kl.flex["RF"] + 6.0)),
                   (40, fore_mid(calf, "RF", -0.10, 0.10, 45.0)), (44, fore_mid(calf, "RF", 0.08, 0.075, 100.0)),
                   (48, foot_of(kn, "RF"), "stop"),
                   (112, foot_of(lf, "RF"), "stop"), (122, fore_mid(calf, "RF", -0.15, 0.07, 30.0)),
                   (132, foot_of(ly, "RF"), "stop"), (N, foot_of(ly, "RF"), "stop")]}
    for leg, t0 in hind_t0.items():
        feet[leg] = [(0, rest, "stop"), (t0, rest, "stop"), (t0 + 6, hind_mid[leg]),
                     (t0 + 12, foot_of(lf, leg), "stop"), (N, foot_of(ly, leg), "stop")]
    lock = {"LF": [(34, 102)], "RF": [(48, 112)]}
    pivots = {"LF": [(14, 19, "toe", toeL, False)], "RF": [(22, 36, "toe", toeR)]}    # LF: heel lift while unloading
    planted = {"LF": [(0, 14), (122, N)], "RF": [(0, 22), (132, N)], "LH": [(0, 85), (97, N)], "RH": [(0, 86), (98, N)]}
    stand_ok = [(0, 16)]          # frames where both fore legs stand loaded (carpus limit)
    cap = lambda f: A.ease(f / 14.0)      # loaded-leg reach cap eases off the rest clamp over the sniff
    return N, clip_fn(calf, body, feet, lock, pivots, planted=planted, guard_cap=cap), dict(lock=lock, pivots=pivots, planted=planted, stand=stand_ok)


GATHER = {"LH": (0.17, 0.555), "RH": (-0.17, 0.555)}   # GetUp: hind hooves gathered beside/behind the belly (x, y)


def get_up(calf, N=150):
    """HIND end first: fold the fore legs back under onto the knees, gather the hind hooves beside the belly, lunge
    forward on the knees while the hind legs lift the rump, step each hind hoof forward under the hips, roll onto
    the right knee and step the left fore forward (toe first), push, step the right fore, rise, stand."""
    S, ly, lf = stand(), lying(calf), lying_folded(calf)
    rest = (V0.copy(), 0.0)
    gat = {leg: (Vector((x, y, rest_foot(calf, leg).z)) - rest_foot(calf, leg), 0.0) for leg, (x, y) in GATHER.items()}
    prep = cp(ly); prep.neck = [-11.0, -12.0, -10.0]; prep.head = Vector((12.0, 1.0, -2.0))     # head up a little more
    prep.ears = {"L": Vector((10.0, 0.0, -10.0)), "R": Vector((10.0, 0.0, -10.0))}
    folded = cp(lf); folded.neck = [2.0, 2.0, 1.0]; folded.head = Vector((4.0, 0.0, 0.0)); folded.ears = prep.ears
    gather = cp(lf)
    gather.spine = {"Back": (0.0, 0.0, 0.15 * HIP_ROLL), "Torso": (0.0, 0.0, -0.15 * HIP_ROLL)}
    gather.neck = [-2.0, -2.0, 0.0]; gather.head = Vector((0.0, 0.0, 0.0)); gather.ears = prep.ears
    for leg in HIND:
        gather.feet[leg], gather.flex[leg] = gat[leg]
    solve_body(calf, gather, [knee_res(calf, "LF"), knee_res(calf, "RF"), elbow_ahead_res(calf, "LF", 0.25),
                              hip_z_res(calf, 0.39)], ["y", "z", "pitch", "roll"])
    for leg in HIND:
        solve_femur(calf, gather, leg, 0.16)
        fit_femur(calf, gather, leg)
    lunge = kneel(calf, hip=0.52, ahead=0.12)
    lunge.spine = {"Back": (0.0, 0.0, 0.1 * HIP_ROLL), "Torso": (0.0, 0.0, -0.1 * HIP_ROLL)}
    lunge.neck = [8.0, 9.0, 7.0]; lunge.head = Vector((8.0, 0.0, 0.0))
    lunge.tail = [(0.0, -10.0), (0.0, -6.0), (0.0, -2.0), (0.06, 6.0), (0.68, 7.97), (1.28, 5.91), (1.07, 3.9)]
    for leg in HIND:
        lunge.feet[leg], lunge.flex[leg] = gat[leg]
        solve_femur(calf, lunge, leg, 0.19)
    kn = kneel(calf, hip=0.64, ahead=0.05)
    kn.neck = [4.0, 4.0, 3.0]; kn.head = Vector((4.0, 0.0, 0.0))
    for leg in HIND:
        solve_femur(calf, kn, leg, 0.24)
    kn2 = cp(kn); kn2.neck = [2.0, 2.0, 2.0]; kn2.head = Vector((2.0, 0.0, 0.0))
    # left fore steps up: body rolls onto the right knee (lifts the left elbow), hoof planted toe first at its rest spot
    step = cp(kn); step.body_rot = Vector((kn.body_rot.x - 2.0, 7.0, 0.0))
    step.neck = [0.0, 0.0, 0.0]; step.head = Vector((2.0, 0.0, 0.0))
    step.kneel = {"RF": (knee_points(calf)["RF"], 1.0)}
    toeL, toeR = pivot_point(calf, "LF"), pivot_point(calf, "RF")
    step.feet["LF"], step.flex["LF"] = foot_on_pivot(calf, "LF", toeL, 0.0)
    solve_body(calf, step, [knee_res(calf, "RF"), elbow_ahead_res(calf, "LF", 0.0)], ["z", "y"])
    solve_flex_on_pivot(calf, step, "LF", toeL, -58.0)
    push = cp(step); push.body_rot = Vector((step.body_rot.x - 2.0, 4.0, 0.0))
    push.neck = [-4.0, -4.0, -2.0]; push.head = Vector((0.0, 0.0, 0.0))
    solve_body(calf, push, [knee_res(calf, "RF"), fetlock_res(calf, "LF", -50.0)], ["z", "y"])
    # right fore comes up and plants toe first; the body rises on the fore hooves and the hind legs. Rise/up are
    # solved on the fore joints: the elbows stay far enough behind/above the hooves for the fetlock limit, then the
    # loaded legs straighten to their standing bend
    rise = stand(); rise.body_off = Vector((0.0, 0.08, -0.10)); rise.body_rot = Vector((6.0, 0.0, 0.0))
    rise.neck = [-6.0, -6.0, -4.0]; rise.head = Vector((-2.0, 0.0, 0.0))
    rise.feet["RF"], rise.flex["RF"] = foot_on_pivot(calf, "RF", toeR, 6.0)
    solve_body(calf, rise, [fetlock_res(calf, "LF", -45.0)], ["z"])
    up = stand(); up.body_off = Vector((0.0, 0.015, -0.02)); up.body_rot = Vector((1.5, 0.0, 0.0))
    up.neck = [-6.0, -5.0, -3.0]; up.head = Vector((-3.0, -2.0, 0.0))
    up.ears = {"L": Vector((6.0, -4.0, -6.0)), "R": Vector((6.0, -4.0, -6.0))}
    solve_body(calf, up, [shell_res(calf, "LF", D_STAND), shell_res(calf, "RF", D_STAND)], ["z", "roll"])
    settle = stand(); settle.neck = [1.0, 1.0, 1.0]; settle.head = Vector((1.0, 1.0, 0.0))
    body = [(0, ly, "stop"), (8, prep), (28, folded, "stop"), (40, gather), (52, lunge), (62, kn, "stop"),
            (70, kn2, "stop"), (84, step, "stop"), (92, push, "stop"), (110, rise), (126, up), (138, settle), (N, S, "stop")]
    feet = {"LF": [(0, foot_of(ly, "LF"), "stop"), (4, foot_of(ly, "LF"), "stop"),
                   (13, fore_mid(calf, "LF", -0.15, 0.07, 30.0)), (22, foot_of(lf, "LF"), "stop"),
                   (70, foot_of(lf, "LF"), "stop"), (77, fore_mid(calf, "LF", -0.02, 0.17, 80.0)),
                   (84, foot_of(step, "LF"), "stop"), (104, rest, "stop"), (N, rest, "stop")],
            "RF": [(0, foot_of(ly, "RF"), "stop"), (10, foot_of(ly, "RF"), "stop"),
                   (19, fore_mid(calf, "RF", -0.15, 0.07, 30.0)), (28, foot_of(lf, "RF"), "stop"),
                   (92, foot_of(lf, "RF"), "stop"), (99, fore_mid(calf, "RF", -0.06, 0.18, 80.0)),
                   (106, foot_on_pivot(calf, "RF", toeR, 14.0), "stop"), (111, foot_of(rise, "RF")), (120, rest, "stop"),
                   (N, rest, "stop")]}
    for leg, t0, t1 in (("LH", 26, 56), ("RH", 28, 61)):
        a = foot_of(ly, leg)
        # step forward under the hips (review A13): the hoof rises with little flex (a flexed hoof drags its toe),
        # travels high, and comes down onto its spot almost vertically with zero speed (it used to touch down 2 frames
        # early while still moving 29 / 18 mm/f and then rebound 8 mm)
        feet[leg] = [(0, a, "stop"), (t0, a, "stop"), (t0 + 6, lifted(a, gat[leg], 0.5, 0.02, -25.0)),
                     (t0 + 12, gat[leg], "stop"), (t1, gat[leg], "stop"),
                     (t1 + 3, lifted(gat[leg], rest, 0.35, 0.035, 10.0)), (t1 + 6, lifted(gat[leg], rest, 0.93, 0.03, 4.0)),
                     (t1 + 9, rest, "stop"), (N, rest, "stop")]
    # mid-gather: hind hooves in the air on their way under the belly; femurs keep the hind joints in range
    gm = A.blend_pose(folded, gather, 0.5); gm.auto_top = False
    gm.spine = {"Back": (0.0, 0.0, 0.25 * HIP_ROLL), "Torso": (0.0, 0.0, -0.25 * HIP_ROLL)}   # pelvis unrolls early: frees the right hind
    for leg in HIND:
        gm.feet[leg], gm.flex[leg] = hermite(feet[leg], _foot_combine)(33)
    for leg in FRONT:
        kneel_leg(calf, gm, leg)
    solve_body(calf, gm, [knee_res(calf, "LF"), knee_res(calf, "RF")], ["z", "roll"])
    for leg in HIND:
        fit_femur(calf, gm, leg)
    body.insert(3, (33, gm))
    lock = {"LF": [(22, 70)], "RF": [(28, 92)]}
    pivots = {"LF": [(84, 104, "toe", toeL)], "RF": [(106, 120, "toe", toeR)]}
    planted = {"LF": [(0, 4), (104, N)], "RF": [(0, 10), (120, N)],
               "LH": [(0, 26), (38, 56), (65, N)], "RH": [(0, 28), (40, 61), (70, N)]}
    stand_ok = [(128, N)]
    return N, clip_fn(calf, body, feet, lock, pivots, planted=planted), dict(lock=lock, pivots=pivots, planted=planted, stand=stand_ok)


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
    planted = {leg: [(0, N)] for leg in LEGS}
    return N, clip_fn(calf, body, feet, {}, {}, overlays=(overlay,), planted=planted), dict(lock={}, pivots={}, planted=planted, stand=[])


# ============================================================================ QA
def planted_from(plan):
    return lambda leg, f: in_plan(plan, leg, f)


def contact_frames(info, leg, f):
    """leg bears weight or rests on the ground: planted hoof, hoof pivot or knee lock"""
    return (in_plan(info["planted"], leg, f) or in_plan(info["lock"], leg, f)
            or any(iv[0] <= f <= iv[1] for iv in info["pivots"].get(leg, ())))


class GroundCheck:
    """Evaluates a cage mesh (default Calf_LOD2, armature modifier on): min z of body (non-hoof) vertices by region,
    and per-leg hoof vertices (orig_part == 2 faces) for planted and for swinging hooves."""

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
        self.hoof_rest = {leg: float(self.rest[m, 2].min()) for leg, m in self.leg_of.items()}

    def sample(self, act, frames):
        mods = [m for m in self.ob.modifiers if m.type == "ARMATURE"]
        old = [m.show_viewport for m in mods]
        for m in mods: m.show_viewport = True
        self.calf.use_action(act)
        rows = []
        mw = np.array(self.ob.matrix_world)
        for f in frames:
            self.calf.sc.frame_set(f)
            ev = self.ob.evaluated_get(bpy.context.evaluated_depsgraph_get())
            m = ev.to_mesh()
            co = np.zeros(len(m.vertices) * 3, np.float32); m.vertices.foreach_get("co", co)
            ev.to_mesh_clear()
            co = co.reshape(-1, 3) @ mw[:3, :3].T + mw[:3, 3]
            i = int(np.argmin(np.where(~self.hoof, co[:, 2], 9)))
            reg = {r: float(co[(self.region == r) & ~self.hoof, 2].min()) for r in ("trunk", "head", "leg", "tail")}
            rows.append(dict(f=f, body=float(co[i, 2]), body_at=self.rest[i].round(2).tolist(), region=reg,
                             hoof={leg: float(co[msk, 2].min()) for leg, msk in self.leg_of.items()}))
        for m, o in zip(mods, old): m.show_viewport = o
        return rows

    def report(self, act, frames, info, label=""):
        rows = self.sample(act, frames)
        worst = min(rows, key=lambda r: r["body"])
        msg = (f"GROUND {label or act.name}: non-hoof min z {worst['body']*100:+.1f} cm (f{worst['f']}, rest-vert "
               f"{[round(x, 2) for x in worst['body_at']]}) [" +
               ", ".join(f"{r} {min(w['region'][r] for w in rows)*100:+.1f}" for r in ("trunk", "head", "leg", "tail")) + "]")
        bad = [(r["f"], round(r["body"] * 100, 1)) for r in rows if r["body"] < -0.02]
        if bad:
            msg += f" | frames below -2 cm: {bad[:12]}{' ...' if len(bad) > 12 else ''}"
        hz = [r["hoof"][leg] for r in rows for leg in LEGS if in_plan(info["planted"], leg, r["f"])]
        if hz:
            msg += f" | planted hoof min z {min(hz)*100:+.1f} .. {max(hz)*100:+.1f} cm"
        sw = [(r["hoof"][leg] - min(0.0, self.hoof_rest[leg]), leg, r["f"]) for r in rows for leg in LEGS
              if not contact_frames(info, leg, r["f"])]
        if sw:
            m = min(sw)
            msg += f" | swinging hoof min z {m[0]*100:+.1f} cm ({m[1]} f{m[2]})"
        print(msg)
        return rows


def joint_series(calf, act, frames):
    """baked joint angles about the root side axis per frame (deg, 0 = straight; the reviewer's convention):
    fore carpus / fetlock, hind stifle / hock / fetlock"""
    calf.use_action(act)
    out = []
    for f in range(frames + 1):
        calf.sc.frame_set(f)
        ae = calf.arm.evaluated_get(bpy.context.evaluated_depsgraph_get())
        W = {pb.name: pb.matrix for pb in ae.pose.bones}
        ax = (W["Root"].to_3x3() @ X_AX).normalized()
        yd = lambda n: W[n].to_3x3() @ Vector((0, 1, 0))
        r = {}
        for leg, d in LEGS.items():
            up, lo = d["chain"]
            if leg in FRONT:
                r[leg + "_carpus"] = sang(yd(up), yd(lo), ax)
                r[leg + "_fetlock"] = sang(yd(lo), yd(d["foot"]), ax)
            else:
                r[leg + "_stifle"] = sang(yd(d["top"]), yd(up), ax)
                r[leg + "_hock"] = sang(yd(up), yd(lo), ax)
                r[leg + "_fetlock"] = sang(yd(lo), yd(d["foot"]), ax)
        out.append(r)
    return out


def joint_qa(calf, act, frames, info, label=""):
    js = joint_series(calf, act, frames)
    loaded = lambda leg, f: in_plan(info["planted"], leg, f) or any(iv[0] <= f <= iv[1] and (len(iv) < 5 or iv[4])
                                                                    for iv in info["pivots"].get(leg, ()))
    fet = [(js[f][leg + "_fetlock"], leg, f) for f in range(frames + 1) for leg in FRONT if loaded(leg, f)]
    car = [(js[f][leg + "_carpus"], leg, f) for a, b in info["stand"] for f in range(a, b + 1) for leg in FRONT]
    stf = [(js[f][leg + "_stifle"], leg, f) for f in range(frames + 1) for leg in HIND]
    carp_all = [js[f][leg + "_carpus"] for f in range(frames + 1) for leg in FRONT]
    hock_all = [js[f][leg + "_hock"] for f in range(frames + 1) for leg in HIND]
    msg = f"JOINT {label or act.name}:"
    if fet:
        m = min(fet); msg += f" loaded fore fetlock min {m[0]:.1f} ({m[1]} f{m[2]}) [limit {FETLOCK_MIN:.0f}]"
    if car:
        m = max(car); msg += f" | standing carpus max {m[0]:.1f} ({m[1]} f{m[2]}) [limit {CARPUS_STAND_MAX:.0f}]"
    m = max(stf); msg += f" | stifle max {m[0]:.1f} ({m[1]} f{m[2]}) [limit {STIFLE_MAX:.0f}]"
    hk = min((js[f][leg + "_hock"], leg, f) for f in range(frames + 1) for leg in HIND)
    msg += f" | hock min {hk[0]:.1f} ({hk[1]} f{hk[2]}) [limit {HOCK_MIN:.0f}] | carpus {min(carp_all):.0f}..{max(carp_all):.0f}"
    fl = [(js[f][leg + "_fetlock"], leg, f) for f in range(frames + 1) for leg in FRONT]
    msg += f" | fore fetlock (any) {min(fl)[0]:.0f} ({min(fl)[1]} f{min(fl)[2]})"
    print(msg)
    ok = ((not fet or min(fet)[0] >= FETLOCK_MIN - 0.5) and (not car or max(car)[0] <= CARPUS_STAND_MAX + 0.5)
          and max(stf)[0] <= STIFLE_MAX + 0.5 and min(carp_all) > -5.0 and max(hock_all) < 0.0 and hk[0] >= HOCK_MIN - 0.5)
    return js, ok


def pivot_qa(calf, act, info, label=""):
    """drift of the hoof contact point (toe tip / heel bulb, from the baked toe bone) over each pivot interval"""
    calf.use_action(act)
    worst, parts = 0.0, []
    for leg, ivs in info["pivots"].items():
        toe = LEGS[leg]["toe"]
        for a, b, which, pt, *fl in ivs:
            q = calf.rest[toe].inverted() @ hoof_local(calf, leg, which)
            w, p0 = 0.0, None
            for f in range(a, b + 1):
                calf.sc.frame_set(f)
                ae = calf.arm.evaluated_get(bpy.context.evaluated_depsgraph_get())
                p = ae.pose.bones[toe].matrix @ q
                p0 = p0 or p.copy()
                w = max(w, (p - p0).length)
            parts.append(f"{leg} {which} f{a}-{b}{'' if (not fl or fl[0]) else ' (unloading)'} {w*1000:.2f}")
            if not fl or fl[0]:
                worst = max(worst, w)
    if parts:
        print(f"PIVOT {label or act.name}: loaded hoof contact point drift (from the interval start) {worst*1000:.2f} mm ["
              + "; ".join(parts) + " mm]")
    return worst


def knee_qa(calf, act, frames, lock, label=""):
    """carpus (front knee) drift in xy and height while locked"""
    if not lock:
        return 0.0
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


def inside_qa(calf, act, frame, obj="Calf_LOD1", label=""):
    """fraction of fore cannon / hoof vertices (dominant bone FrontLowerLeg / IKFrontLeg / FF) that lie inside the
    closed skin (ray parity, 3 rays, 2 votes), e.g. a folded cannon swallowed by the forearm/brisket"""
    from mathutils.bvhtree import BVHTree
    ob = bpy.data.objects[obj]
    for m in ob.modifiers:
        if m.type == "ARMATURE": m.show_viewport = True
    gname = {g.index: g.name for g in ob.vertex_groups}
    dom = []
    for v in ob.data.vertices:
        best, bw = "", 0.0
        for g in v.groups:
            if g.weight > bw: best, bw = gname.get(g.group, ""), g.weight
        dom.append(best)
    calf.use_action(act); calf.sc.frame_set(frame)
    ev = ob.evaluated_get(bpy.context.evaluated_depsgraph_get()); me = ev.to_mesh()
    co = [ob.matrix_world @ v.co for v in me.vertices]
    nr = [(ob.matrix_world.to_3x3() @ v.normal).normalized() for v in me.vertices]
    bvh = BVHTree.FromPolygons(co, [tuple(p.vertices) for p in me.polygons]); ev.to_mesh_clear()
    for m in ob.modifiers:
        if m.type == "ARMATURE": m.show_viewport = False
    dirs = [Vector((0, 0, 1)), Vector((0.3, 0.2, 0.93)).normalized(), Vector((-0.3, -0.2, 0.93)).normalized()]
    res = {}
    for i, n in enumerate(dom):
        if not n.startswith(("FrontLowerLeg", "IKFrontLeg", "FF.")):
            continue
        p = co[i] + nr[i] * 0.003; votes = 0
        for d in dirs:
            o = p.copy(); k = 0
            for _ in range(64):
                hit = bvh.ray_cast(o, d)[0]
                if hit is None: break
                k += 1; o = hit + d * 1e-4
            votes += k % 2
        t = res.setdefault(n, [0, 0]); t[1] += 1; t[0] += votes >= 2
    print(f"INSIDE {label or act.name} f{frame} ({obj}): " +
          ", ".join(f"{n} {a}/{b} ({100*a/b:.0f}%)" for n, (a, b) in sorted(res.items())))
    return res


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


def pop_qa(calf, act, frames, loop=False, label="", body_only=False):
    """largest per-frame bone-head acceleration (2nd difference, mm/frame^2) and velocity: pops show as spikes.
    body_only: trunk/neck/head bones only (the chest must not rebound when a knee lands)"""
    calf.use_action(act)
    names = [pb.name for pb in calf.arm.pose.bones if not pb.name.startswith("PoleTarget")]   # unweighted IK helpers
    if body_only:
        names = [n for n in names if n in ("Body", "Back", "Torso", "Torso2", "Torso3", "Neck1", "Neck2", "Neck3", "Head")]
    pts = []
    for f in range(frames + 1):
        calf.sc.frame_set(f)
        ae = calf.arm.evaluated_get(bpy.context.evaluated_depsgraph_get())
        pts.append(np.array([list(ae.pose.bones[n].tail) for n in names]))
    P = np.array(pts)
    if loop:                       # frame N == frame 0: wrap around the seam
        P = np.concatenate([P[-2:-1], P, P[1:2]])
    acc = np.linalg.norm(P[2:] - 2 * P[1:-1] + P[:-2], axis=2).max(axis=1) * 1000
    vel = np.linalg.norm(P[1:] - P[:-1], axis=2).max(axis=1) * 1000
    i = int(np.argmax(acc))
    print(f"POP {label or act.name}{' (trunk/head)' if body_only else ''}: max accel {acc.max():.1f} mm/f^2 at "
          f"f{i + (0 if loop else 1)} | max speed {vel.max():.1f} mm/f")
    return acc, vel


# ============================================================================ build
CLIPS = {}      # name -> (frames, fn, loop, info); filled by build()


def build(calf):
    made = []
    _CACHE.clear()
    for name, maker, loop in (("LieDown", lie_down, False), ("Lying_Idle", lying_idle, True), ("GetUp", get_up, False)):
        N, fn, info = maker(calf)
        make_clip_ex(calf, name, N, fn, loop=loop)
        CLIPS[name] = (N, fn, loop, info)
        made.append(name)
    return made


if __name__ == "__main__":
    import argparse, subprocess, time
    ROOT = os.path.dirname(TOOLS)
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src", default=os.path.join(ROOT, "build", "stage_b.blend"))
    ap.add_argument("--scratch", default="/tmp/claude-0/-home-user-Game-asset/f3fb310f-97d7-5da4-a5e8-b863f47eb685/scratchpad/lying",
                    help="directory for the test blend and the renders")
    ap.add_argument("--out", default=None, help="test blend (default <scratch>/test.blend)")
    ap.add_argument("--render", default="all", help="'all', 'none' or comma list of clips")
    ap.add_argument("--step", type=int, default=4, help="render every n-th frame")
    ap.add_argument("--no-inside", action="store_true", help="skip the (slower) LOD1 inside-the-skin test")
    a = ap.parse_args()
    SCR = a.scratch
    os.makedirs(SCR, exist_ok=True)
    a.out = a.out or os.path.join(SCR, "test.blend")
    calf = A.Calf(a.src)
    t0 = time.time()
    names = build(calf)
    print(f"built {names} in {time.time() - t0:.1f} s")
    gc = GroundCheck(calf)
    all_ok = True
    for n in names:
        N, fn, loop, info = CLIPS[n]
        act = bpy.data.actions[n]
        calf.qa(act, N, planted_from(info["planted"]), label=n)
        knee_qa(calf, act, N, info["lock"], label=n)
        pivot_qa(calf, act, info, label=n)
        _, ok = joint_qa(calf, act, N, info, label=n)
        all_ok &= ok
        gc.report(act, range(0, N + 1, 2), info, label=n)
        pop_qa(calf, act, N, loop=loop, label=n)
        pop_qa(calf, act, N, loop=loop, label=n, body_only=True)
    if not a.no_inside:
        inside_qa(calf, bpy.data.actions["Lying_Idle"], 0, label="Lying_Idle")
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
    print("JOINT limits:", "all OK" if all_ok else "VIOLATED (see JOINT lines)")
    calf.save(a.out)
    todo = names if a.render == "all" else ([] if a.render == "none" else a.render.split(","))
    for n in todo:
        N = CLIPS[n][0]
        for side in ("left", "threequarter"):
            subprocess.run([sys.executable, os.path.join(TOOLS, "render_clip.py"), a.out, n,
                            os.path.join(SCR, f"{n}_{side}"), "--frames", f"0:{N}:{a.step}", "--res", "320",
                            "--samples", "6", "--side", side], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print("rendered", n, side)
