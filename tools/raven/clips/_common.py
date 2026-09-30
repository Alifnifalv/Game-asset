"""Shared key-pose tools for the raven clip families (the leading '_' keeps raven_animations.py from importing it as
a family).

  timeline(keys, f, lift=0.03)   keys = [(frame, Pose), ...]: eased (smootherstep) blend of neighbouring key poses;
                                 a foot that moves more than 1 cm between two keys is lifted on an arc (it steps)
  stand() / fly_neutral()        the boundary poses: every ground clip starts and ends on stand(), every flight clip on
                                 fly_neutral() (both from raven_anim)
  breathe / look / ruffle        additive layers (periodic in the clip length, so loops stay exact)
  flap(P, phase, amp, ...)       one wingbeat of the GiM cruise flap (spec 6.3): phase 0 = top of the stroke, FLAP_DOWN
                                 (0.52) = the bottom; flap_neutral_phase() (the mid-downstroke) adds nothing, so a
                                 flight loop started there begins and ends on its base pose (flap_offsets: the curves)

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


FLAP_DOWN = 0.52          # downstroke share of a cruise beat (10.4 of 20 f; spec 6.3)


def flap_neutral_phase(down=FLAP_DOWN):
    """the phase at which flap() adds nothing (mid-downstroke, wing level and fully extended): flight loops start there
    so that they begin and end on the unmodified pose (fly_neutral)"""
    return 0.5 * down


def flap_offsets(phase, down=FLAP_DOWN, up_elev=64.0, down_elev=64.0, fold_up=0.60, pron=22.0):
    """the wingbeat curves at `phase` (0 = top of the stroke, `down` = bottom). Every channel is 0 at the mid-downstroke
    (flap_neutral_phase) and continuous and periodic over the beat. Returns a dict of the WingPose deltas and the body
    bob (m) / pitch (deg)."""
    phase %= 1.0
    if phase < down:                      # downstroke: fully extended, fan closed to the glide fan, fast
        u = phase / down
        e = 0.5 - 0.5 * math.cos(math.pi * u)
        elev = up_elev - (up_elev + down_elev) * e
        c = math.cos(math.pi * u)                        # +1 top, 0 mid, -1 bottom
        flex = 0.0
        slot = 0.0
        spread = 0.0
        sweep = -9.0 * c                                 # stroke plane: the wing travels forward on the way down
        twist = pron * R.smooth((u - 0.5) / 0.5)          # pronation (leading edge down) through the lower half:
        #                                                   the inner wing / tertials stay off the flank at the bottom
        finger = 0.0
    else:                                  # upstroke: wrist flexed, hand swept back and in, slots open, fan half closed
        u = (phase - down) / (1 - down)
        e = 0.5 - 0.5 * math.cos(math.pi * u)
        elev = -down_elev + (up_elev + down_elev) * e
        k = math.sin(math.pi * u)
        flex = fold_up * k ** 0.8
        slot = 22.0 * k
        spread = -10.0 * k
        sweep = 9.0 * math.cos(math.pi * u)              # back from +9 (bottom) to -9 (top)
        twist = pron * (1.0 - e) - 10.0 * k              # back through supination (leading edge up) to the top
        finger = -8.0 * k                                # the unloaded fingertips relax
    bob = math.sin(TAU * (phase - 0.5 * down))           # 0 at the mid-downstroke, highest near the bottom
    return dict(elev=elev, flex=flex, slot=slot, spread=spread, sweep=sweep, twist=twist, finger=finger, bob=bob)


def flap(P, phase, amp=1.0, fold_up=0.60, down=FLAP_DOWN, bob=0.010, sides=R.SIDES, **kw):
    """add one wingbeat of the GiM cruise flap (spec 6.3: 19-20 f per beat, amplitude ~130 deg) to a flight pose.
    phase in [0, 1): 0 = top, `down` = bottom (downstroke 10-11 f of 20), then the upstroke with the wrist flexed, the
    hand swept back and the slots open. amp scales the elevation stroke; flap_neutral_phase() adds nothing, so a loop
    started there begins on the unmodified pose. kw: up_elev / down_elev (deg) for take-off and braking beats."""
    o = flap_offsets(phase, down, fold_up=fold_up, **kw)
    fl = o["flex"]
    for s in sides:
        w = P.wings[s]
        w.elev += o["elev"] * amp
        w.arm = w.get("arm") + 0.20 * fl
        w.elbow = w.get("elbow") + 0.55 * fl
        w.wrist = w.get("wrist") + 1.0 * fl
        w.feathers = w.get("feathers") + 0.60 * fl
        w.slot += o["slot"]
        w.spread += o["spread"]
        w.sweep += o["sweep"] - 10.0 * fl
        w.twist += o["twist"]
        w.finger_up += o["finger"]
    P.body_off = P.body_off + Vector((0, 0, bob * o["bob"]))
    return P


# ================================================================================================= ground-clip helpers
# (appended for the ground / actions families; nothing above uses them)
BILL_TIP = Vector((0.0, -0.3043, 0.3202))          # upper hook tip (rigid on Head), rest armature space
BILL_BASE = Vector((0.0, -0.238, 0.340))           # the rictus on the midline: bill axis = BILL_BASE -> BILL_TIP
LOW_TIP = Vector((0.0, -0.2978, 0.3190))           # lower mandible tip (rigid on Jaw)


def track(keys, f):
    """keys = [(frame, value), ...] (value: float or tuple); smootherstep between neighbouring keys, held outside"""
    if f <= keys[0][0]:
        return keys[0][1]
    if f >= keys[-1][0]:
        return keys[-1][1]
    for (f0, v0), (f1, v1) in zip(keys, keys[1:]):
        if f0 <= f <= f1:
            e = R.smoother((f - f0) / (f1 - f0)) if f1 > f0 else 1.0
            if isinstance(v0, (tuple, list)):
                return tuple(R.lerp(a, b, e) for a, b in zip(v0, v1))
            return R.lerp(v0, v1, e)
    return keys[-1][1]


def root_matrix(P):
    return R.T(P.root_pos) @ R.Rz(P.root_yaw)


def to_root(P, world):
    """world point -> the root frame of pose P"""
    return (root_matrix(P).inverted() @ Vector(world).to_4d()).to_3d()


def body_to_root(P, v):
    """a point given in the rest (body) frame, carried by the body transform (body_off, body_rot about COG) -> root
    frame (e.g. a foot target that should move with the body)"""
    B = R.body_matrix(*P.body_rot)
    M = R.T(P.body_off) @ R.T(R.COG) @ B @ R.T(-R.COG)
    return (M @ Vector(v).to_4d()).to_3d()


class FootTrack:
    """world-space foot plants for one foot: plants = [(f_on, f_off, (x, y, z), yaw_deg), ...] sorted; between two
    plants the foot swings (smootherstep in the plane, a sine arc of height `lift`, toes curl up to `grip`).
    at(f) -> (world pos, world yaw, grip, planted)"""

    def __init__(self, plants, lift=0.03, grip=0.6):
        self.plants = [(a, b, Vector(p), y) for a, b, p, y in plants]
        self.lift, self.grip = lift, grip

    def at(self, f):
        pl = self.plants
        if f <= pl[0][1]:
            return pl[0][2].copy(), pl[0][3], 0.0, pl[0][0] <= f
        for (a0, b0, p0, y0), (a1, b1, p1, y1) in zip(pl, pl[1:]):
            if b0 <= f <= a1:
                if a1 == b0:
                    return p1.copy(), y1, 0.0, True
                t = (f - b0) / (a1 - b0)
                e = R.smoother(t)
                p = p0.lerp(p1, e)
                d = (p1 - p0).xy.length
                p.z += min(self.lift, 0.012 + 0.4 * d) * math.sin(math.pi * t)
                return p, R.lerp(y0, y1, e), self.grip * math.sin(math.pi * t), False
            if a1 <= f <= b1:
                return p1.copy(), y1, 0.0, True
        return pl[-1][2].copy(), pl[-1][3], 0.0, True

    def planted(self, f):
        return self.at(f)[3]


def set_foot(P, s, pos_world, yaw_world=0.0, grip=0.0):
    """pin a foot: MTP target at a world point, toes at a world yaw (both converted to the root frame of P)"""
    lp = P.legs[s]
    P.legs[s] = R.LegPose(to_root(P, pos_world), yaw_world - P.root_yaw, grip, lp.thigh, lp.pole, lp.planted, lp.local)
    return P


def rest_foot_world(P0, s):
    """the rest MTP of pose P0 in world space (P0's root frame)"""
    return (root_matrix(P0) @ rest_mtp(s).to_4d()).to_3d()


def _knee(rig, P, s, thigh):
    B = R.body_matrix(*P.body_rot)
    W = root_matrix(P)
    Mh = W @ R.T(P.body_off) @ R.T(R.COG) @ B @ R.T(-R.COG) @ rig.rest["Hips"]
    th = f"Thigh.{s}"
    Mt = Mh @ rig.relm[th] @ R.rot(thigh).to_matrix().to_4x4()
    return (Mt @ Vector((0, rig.length[th], 0, 1))).to_3d(), W


def knee_foot(rig, P, s, thigh=None):
    lp = P.legs[s]
    k, W = _knee(rig, P, s, lp.thigh if thigh is None else thigh)
    tgt = W @ (lp.mtp if lp.mtp is not None else rest_mtp(s)).to_4d()
    return (tgt.to_3d() - k).length


def fit_thigh(rig, P, lo=0.125, hi=0.166):
    """swing each femur by the smallest angle that brings the knee-to-foot distance into [lo, hi] (the IK reach is
    0.1727): feet far behind / a body pitched nose-down get the knee swung back, feet tucked under get it forward.
    A pose already inside the window is returned unchanged (stand() stays exact)."""
    for s in R.SIDES:
        lp = P.legs[s]
        d0 = knee_foot(rig, P, s)
        if lo <= d0 <= hi:
            continue
        best = None
        for sgn in (1.0, -1.0):
            prev = d0
            for k in range(1, 91):
                d = knee_foot(rig, P, s, lp.thigh + sgn * k)
                if lo <= d <= hi:
                    # refine between k-1 and k
                    a, b = k - 1.0, float(k)
                    for _ in range(20):
                        m = 0.5 * (a + b)
                        dm = knee_foot(rig, P, s, lp.thigh + sgn * m)
                        if lo <= dm <= hi:
                            b = m
                        else:
                            a = m
                    if best is None or b < best[0]:
                        best = (b, sgn)
                    break
                if abs(d - (hi if d0 > hi else lo)) > abs(prev - (hi if d0 > hi else lo)) + 1e-9 and k > 30:
                    break
                prev = d
        if best is not None:
            lp.thigh += best[1] * best[0]
    return P


def bill_points(rig, P, M=None):
    """world positions of the upper bill tip, the lower mandible tip and the bill base for pose P"""
    M = M or rig.solve(P)
    H = M["Head"] @ rig.rest["Head"].inverted()
    J = M["Jaw"] @ rig.rest["Jaw"].inverted()
    return ((H @ BILL_TIP.to_4d()).to_3d(), (J @ LOW_TIP.to_4d()).to_3d(), (H @ BILL_BASE.to_4d()).to_3d())


def bill_low_z(rig, P):
    t, lt, _ = bill_points(rig, P)
    return min(t.z, lt.z)


def bill_angle(rig, P):
    """bill axis elevation in the sagittal plane of the root, degrees (+ = the tip above the base; continuous past
    -90: -120 = pointing down and back)"""
    t, _, b = bill_points(rig, P)
    d = root_matrix(P).to_3x3().inverted() @ (t - b)
    return math.degrees(math.atan2(d.z, -d.y))


def solve_look(rig, base, fn, target, lo=-90.0, hi=90.0, **look_kw):
    """find the look() pitch x in [lo, hi] with fn(rig, look(base.copy(), pitch=x)) == target (fn monotonic in x);
    returns the posed copy and x"""
    def ev(x):
        return fn(rig, look(base.copy(), pitch=x, **look_kw))
    a, b = lo, hi
    fa = ev(a) - target
    for _ in range(40):
        m = 0.5 * (a + b)
        fm = ev(m) - target
        if (fm > 0) == (fa > 0):
            a, fa = m, fm
        else:
            b = m
    x = 0.5 * (a + b)
    return look(base.copy(), pitch=x, **look_kw), x


def neck_bend(P, n, w=(0.45, 0.35, 0.20)):
    """bend the neck down by n deg (+ = forward-down), mostly at its base (the whole neck swings, no curl)"""
    nk = dict(P.neck)
    for k, wk in zip(("Neck1", "Neck2", "Neck3"), w):
        a, b, c = nk[k]; nk[k] = (a + n * wk, b, c)
    P.neck = nk
    return P


def solve_bill(rig, base, tip_z, angle, n_lo=-30.0, n_hi=95.0):
    """neck bend (neck_bend) and head pitch such that the bill axis points `angle` deg (- = down) and its lowest tip
    sits at tip_z; returns the posed copy"""
    def with_n(n):
        P = base.copy(); neck_bend(P, n)
        a, b = -110.0, 110.0                     # head pitch: the bill angle falls as the pitch rises
        for _ in range(40):
            m = 0.5 * (a + b)
            Q = P.copy(); Q.head = (P.head[0] + m, P.head[1], P.head[2])
            if bill_angle(rig, Q) > angle:
                a = m
            else:
                b = m
        Q = P.copy(); Q.head = (P.head[0] + 0.5 * (a + b), P.head[1], P.head[2])
        return Q
    a, b = n_lo, n_hi                            # the tip falls as the neck bends down
    for _ in range(40):
        m = 0.5 * (a + b)
        if bill_low_z(rig, with_n(m)) > tip_z:
            a = m
        else:
            b = m
    return with_n(0.5 * (a + b))


def tail_flick(P, f, f0, amp=10.0, dur=8):
    """a quick tail flick starting at f0: up by amp deg in dur/4, back over the rest; zero outside [f0, f0 + dur].
    NOTE (checked by render): for TailBase / Tail a positive rot() pitch lifts the tail tip (the bones point back)"""
    if f0 <= f <= f0 + dur:
        u = (f - f0) / dur
        k = math.sin(math.pi * min(u / 0.25, 1.0) * 0.5) if u < 0.25 else 0.5 + 0.5 * math.cos(math.pi * (u - 0.25) / 0.75)
        a, b, c = P.tailbase
        P.tailbase = (a + amp * k, b, c)
    return P


PART_GROUPS = {"body": (0, 1), "bill": (2,), "feet": (3, 4), "eye": (5,), "feather": (6, 7)}


def lod2_parts(obj_name=R.LOD2):
    """per-vertex group name array for LOD2 (from the face attribute `part`; a vertex takes its lowest-numbered
    group in PART_GROUPS order: feet over body, so the toe skin counts as feet)"""
    import numpy as np
    me = bpy.data.objects[obj_name].data
    fp = np.zeros(len(me.polygons), dtype=np.int32)
    me.attributes["part"].data.foreach_get("value", fp)
    grp = np.full(len(me.vertices), "", dtype=object)
    order = ["feet", "bill", "eye", "body", "feather"]
    rank = {g: i for i, g in enumerate(order)}
    for poly, p in zip(me.polygons, fp):
        g = next(k for k, v in PART_GROUPS.items() if p in v)
        for vi in poly.vertices:
            if grp[vi] == "" or rank[g] < rank[grp[vi]]:
                grp[vi] = g
    return grp


def ground_report(rig, act, step=1, verbose=True, obj_name=R.LOD2):
    """min z (cm) of each LOD2 part group over the clip, with the frame; also the lowest non-foot point"""
    import numpy as np
    grp = lod2_parts(obj_name)
    rig.use_action(act)
    sc = bpy.context.scene
    f0, f1 = int(act.frame_range[0]), int(act.frame_range[1])
    out = {}
    for f in range(f0, f1 + 1, step):
        sc.frame_set(f)
        z = R.lod_vertices(obj_name)[:, 2]
        for g in PART_GROUPS:
            sel = grp == g
            if not np.any(sel):
                continue
            m = float(z[sel].min())
            if g not in out or m < out[g][0]:
                out[g] = (m, f)
    if verbose:
        print(f"GROUND {act.name}: " + ", ".join(f"{g} {v[0] * 100:.2f} cm (f{v[1]})" for g, v in out.items()))
    return out


def run_family(mod, default_in, argv=None):
    """standalone QA of a family module: build on a stage B/C blend, QA every clip (gate numbers, boundaries, LOD2
    ground), save <out-dir>/test.blend"""
    import argparse
    import tempfile
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default=default_in)
    ap.add_argument("--out-dir", default=os.path.join(tempfile.gettempdir(), "raven_" + mod.__name__))
    ap.add_argument("--only", default="")
    ap.add_argument("--no-ground", action="store_true")
    a = ap.parse_args(argv)
    bpy.ops.wm.open_mainfile(filepath=os.path.abspath(a.inp))
    rig = R.RavenRig()
    names = mod.build(rig)
    only = [x for x in a.only.split(",") if x]
    extra = getattr(mod, "QA_EXTRA", {})
    for name in names:
        if only and name not in only:
            continue
        act = bpy.data.actions[name]
        pf = mod.planted_fn(name) if hasattr(mod, "planted_fn") else None
        R.qa_clip(rig, act, planted_fn=pf)
        ex = extra.get(name, {})
        bnd = ex.get("boundary", "stand")
        if bnd:
            ref = R.stand() if bnd == "stand" else R.fly_neutral()
            M = rig.solve(ref)
            Mi = M["Root"].inverted()
            errs = []
            for P in (rig.clip_poses[name][0], rig.clip_poses[name][-1]):
                Mp = rig.solve(P)
                Wi = Mp["Root"].inverted()
                errs.append(max(((Wi @ Mp[n]).to_translation() - (Mi @ M[n]).to_translation()).length
                                for n in rig.order) * 1000)
            print(f"BOUNDARY {name}: start {errs[0]:.4f} mm, end {errs[1]:.4f} mm vs {bnd} ({ex.get('ends', 'both')})")
        if not a.no_ground:
            ground_report(rig, act)
    rig.arm.animation_data.action = None
    os.makedirs(a.out_dir, exist_ok=True)
    out = os.path.join(a.out_dir, "test.blend")
    bpy.ops.wm.save_as_mainfile(filepath=out)
    print("wrote", out)


def pose_ground(rig, P, obj_name=R.LOD2, _cache={}):
    """LOD2 min z per part group for a single pose (the rig's action is cleared; pose bones set directly)"""
    import numpy as np
    if obj_name not in _cache:
        _cache[obj_name] = lod2_parts(obj_name)
    grp = _cache[obj_name]
    ad = rig.arm.animation_data
    if ad is not None:
        ad.action = None
    rig.apply(P)
    bpy.context.view_layer.update()
    z = R.lod_vertices(obj_name)[:, 2]
    return {g: float(z[grp == g].min()) for g in PART_GROUPS if np.any(grp == g)}


def settle_body(rig, P, legs_fn=None, target=-0.002, groups=("body", "feather"), iters=4):
    """lower / raise the body (body_off z) until the lowest vertex of `groups` sits at `target` (a lying body resting
    on the ground); legs_fn(P) re-places the feet after each move (e.g. feet carried by the body)"""
    for _ in range(iters):
        if legs_fn:
            legs_fn(P)
        g = pose_ground(rig, P)
        m = min(g[k] for k in groups if k in g)
        if abs(m - target) < 2e-4:
            break
        P.body_off = P.body_off + Vector((0, 0, target - m))
    if legs_fn:
        legs_fn(P)
    return P
