"""Clip family "locomotion": the extra clips of the Unity locomotion set, and a blend-tree QA.

    build(calf) -> ["Stand", "Walk_Slow_RM", "Walk_Slow", "TurnLeft90", "TurnRight90"]

Clips (30 fps)
  Stand        36 f loop, Pose() on every frame. The 0 m/s child of the Speed blend tree (review A4): Unity syncs the
               children of a 1D blend tree by normalized time and plays the weighted average of their lengths, so the
               100 f Idle as the 0 m/s child stretched the walk cycle and the root speed came out 2-3x lower than the
               Speed parameter. Stand is exactly as long as Walk_Slow, so the Stand / Walk_Slow mix moves at w x 0.45
               m/s. Idle becomes its own state (see the CalfSetup notes in the fix report).
  Walk_Slow_RM / Walk_Slow
               36 f loop, 0.54 m stride (0.45 m/s), 6 / 5 cm steps (anim_gait.WALK_SLOW): the child between Stand and
               Walk, so low speeds step instead of shuffling. Same footfall phases as Walk (they blend in phase).
  TurnLeft90 / TurnRight90
               56 f, root yaw +-90 deg (root motion: rotation only). Replaces the 2-cycle slice of the in-place walk
               that started and ended mid-stride (review A6). Now: frame 0 and frame 56 are exactly Pose() (under the
               final yaw); the root yaw eases in and out (smootherstep over the whole clip, 3 deg/f at the middle);
               each foot takes 3 steps (lateral walk sequence starting with the fore foot on the inside of the turn:
               LF, RH, RF, LH for a left turn), 8-frame swings 4 frames apart, rounds 16 frames apart. A planted hoof
               is placed at its home spot under the root yaw of the middle of its stance (first stance: 0 deg, last:
               the final yaw), which keeps every planted hoof within 12 deg of the body yaw (the old clip: 14 deg).
               The head leads into the turn (neck/head yaw = 6 frames of yaw rate), the body shifts its weight off
               the lifted feet (roll + sway), the tail lags. Planted legs that cannot reach are handled by a local
               body vault (lower + pitch) that is forced to 0 at both ends, so the ends stay exactly Pose().

Blend-tree QA (blend_tree_qa): simulates Unity's 1D blend tree on the export rig (hooves under the lower legs):
normalized-time sync, weighted duration, lerp / nlerp of the local bone transforms, blended root motion, for the
neighbour pairs of the Speed tree at w = .25 / .5 / .75. Reports per pair the longest hoof skate (fetlock within
6 mm of its rest height and moving), the worst mean skate speed, the lowest fetlock (below rest = sinking) and
the closest same-side fore/hind hoof tips. Run by build() when Walk / Trot / Gallop exist (tools/calf_animations.py
builds them before the families).

Standalone: python3 tools/clips/locomotion.py [--in build/stage_b.blend] [--out DIR/test.blend] [--no-gaits]
  builds Walk / Trot / Gallop (as calf_animations.py does) unless --no-gaits, then this family, prints the QA.
"""
import argparse, math, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)
import bpy
import numpy as np
from mathutils import Matrix, Quaternion, Vector
import anim_lib as A
import anim_gait as G
from anim_lib import Pose, LEGS

FPS = 30
STAND_N = G.WALK_SLOW.frames


def smooth(t):
    t = min(1.0, max(0.0, t)); return t * t * (3 - 2 * t)


def smoother(t):
    t = min(1.0, max(0.0, t)); return t * t * t * (t * (6 * t - 15) + 10)


def d_smoother(t):
    """derivative of smoother (per unit t)"""
    if t <= 0.0 or t >= 1.0:
        return 0.0
    return 30.0 * t * t * (t - 1.0) * (t - 1.0)


# ============================================================================== Stand / Walk_Slow
def stand_fn(f):
    return Pose()


def build_walk_slow(calf):
    g = G.WALK_SLOW
    N, fn = A.gait_pose_fn(calf, g, cycles=1)
    act = calf.make_clip(g.name + "_RM", N, fn, stance_fn=A.planted_fn_for(g), loop=True)
    calf.duplicate_in_place(act, g.name)
    return [g.name + "_RM", g.name]


# ============================================================================== turns
TURN_N = 56
TURN_ROUNDS = 3            # steps per foot
TURN_FIRST = 1             # first lift-off frame
TURN_GAP = 4               # frames between the lift-offs of consecutive feet
TURN_ROUND = 16            # frames between a foot's lift-offs
TURN_SWING = 8             # swing frames
TURN_LIFT = {"F": 0.07, "H": 0.055}
TURN_FLEX = {"F": 45.0, "H": 35.0}     # hoof flex at the top of the swing (flex ~ lift^2: no toe dip near the ground)
TURN_LEAD = 6.0            # the head leads the root yaw by this many frames of yaw rate
TURN_ROLL, TURN_SWAY = 1.5, 0.012      # weight shift off the lifted feet (deg per lifted foot, m)
TURN_FEMUR = 8.0           # hind femur protraction in the swing (deg)
ORDER = {+1: ("LF", "RH", "RF", "LH"), -1: ("RF", "LH", "LF", "RH")}


class TurnPlan:
    def __init__(self, calf, turn_deg):
        self.calf, self.turn = calf, turn_deg
        self.N = TURN_N
        sgn = 1 if turn_deg > 0 else -1
        self.rest = {leg: calf.rest_head(d["foot"]) for leg, d in LEGS.items()}
        self.steps = {leg: [] for leg in LEGS}       # leg -> [(lift, land)]
        for r in range(TURN_ROUNDS):
            for i, leg in enumerate(ORDER[sgn]):
                a = TURN_FIRST + r * TURN_ROUND + i * TURN_GAP
                self.steps[leg].append((a, a + TURN_SWING))
        assert max(b for s in self.steps.values() for _, b in s) < self.N
        # planted yaw of each stance: 0 before the first step, the final yaw after the last, else the root yaw at
        # the middle of the stance
        self.targets = {}
        for leg, st in self.steps.items():
            th = [0.0]
            for k, (a, b) in enumerate(st):
                if k == len(st) - 1:
                    th.append(self.turn)
                else:
                    th.append(self.yaw(0.5 * (b + st[k + 1][0])))
            self.targets[leg] = th

    def yaw(self, f):
        return self.turn * smoother(f / float(self.N))

    def yaw_rate(self, f):
        return self.turn * d_smoother(f / float(self.N)) / self.N

    def foot(self, leg, f):
        """(world fetlock, lift 0..1 of the peak, swing weight 0..1, planted?)"""
        st, th = self.steps[leg], self.targets[leg]
        k = sum(1 for a, _ in st if f >= a)           # steps started
        if k and f < st[k - 1][1]:
            a, b = st[k - 1]
            s = (f - a) / float(b - a)
            ang = th[k - 1] + (th[k] - th[k - 1]) * smoother(s)
            h = 16.0 * s * s * (1 - s) * (1 - s)
            p = Matrix.Rotation(math.radians(ang), 3, "Z") @ self.rest[leg]
            p.z += TURN_LIFT[leg[1]] * h
            return p, h, h, False
        return Matrix.Rotation(math.radians(th[k]), 3, "Z") @ self.rest[leg], 0.0, 0.0, True

    def planted(self, leg, f):
        return self.foot(leg, f)[3]

    def pose(self, f):
        P = Pose()
        if f <= 0 or f >= self.N:
            if f >= self.N:
                P.root_yaw = self.turn
                for leg in LEGS:
                    P.feet_world[leg] = Matrix.Rotation(math.radians(self.turn), 3, "Z") @ self.rest[leg]
            return P
        P.root_yaw = self.yaw(f)
        wl = wr = wf = 0.0
        for leg in LEGS:
            p, h, w, _ = self.foot(leg, f)
            P.feet_world[leg] = p
            P.flex[leg] = TURN_FLEX[leg[1]] * h * h
            if leg[0] == "L": wl += w
            else: wr += w
            if leg[1] == "H":
                P.femur[leg] = TURN_FEMUR * w
        lead = TURN_LEAD * self.yaw_rate(f)                      # deg, + = left
        P.neck_yaw = [0.25 * lead, 0.3 * lead, 0.3 * lead]
        P.head = Vector((0.0, 0.15 * lead, 0.0))
        P.body_rot = Vector((0.0, TURN_ROLL * (wl - wr), 0.0))   # roll + = right side down: off the lifted left feet
        P.body_off = Vector((-TURN_SWAY * (wl - wr), 0.0, 0.0))
        P.tail = [(-0.3 * lead * (0.4 + 0.15 * i), 0.0) for i in range(1, 8)]  # side + = tip to the right; the tip lags
        return P


def vault(calf, poses, planted, iters=6, window=3, ends=4):
    """lower (+ pitch) the body so planted legs reach, like Calf.reach_pass, but smoothed only over +-window frames
    and faded to exactly 0 over the first/last `ends` frames, so the boundary frames keep their exact pose"""
    n = len(poses)
    ys = calf.rest_head("FrontUpperLeg.L").y, calf.rest_head("BackLeg.L").y
    span = ys[1] - ys[0]
    env = [smooth(min(i, n - 1 - i) / float(ends)) for i in range(n)]
    worst_raw = 0.0
    for it in range(iters):
        df, dh = [0.0] * n, [0.0] * n
        for i, P in enumerate(poses):
            for leg, e in calf.reach_excess(P).items():
                if e > 0 and planted(leg, i):
                    if leg.endswith("F"): df[i] = max(df[i], e)
                    else: dh[i] = max(dh[i], e)
        if it == 0:
            worst_raw = max(df + dh)
        if max(df + dh) < 1e-4:
            break
        def dil_smooth(a):
            idx = lambda k: min(n - 1, max(0, k))
            dil = [max(a[idx(i + k)] for k in range(-window, window + 1)) for i in range(n)]
            w = [math.exp(-0.5 * (k / (window / 2.0)) ** 2) for k in range(-window, window + 1)]
            return [sum(w[k + window] * dil[idx(i + k)] for k in range(-window, window + 1)) / sum(w) for i in range(n)]
        df, dh = dil_smooth(df), dil_smooth(dh)
        for i, P in enumerate(poses):
            if env[i] <= 0.0: continue
            dz = -(df[i] + dh[i]) / 2.0 * 1.05 * env[i]
            pitch = math.degrees(math.atan2(df[i] - dh[i], span)) * 1.05 * env[i]
            P.body_off = P.body_off + Vector((0, 0, dz))
            P.body_rot = P.body_rot + Vector((pitch, 0, 0))
    return worst_raw


def build_turn(calf, name, turn_deg):
    plan = TurnPlan(calf, turn_deg)
    poses = [plan.pose(f) for f in range(plan.N + 1)]
    raw = vault(calf, poses, plan.planted)
    act = calf.make_clip(name, plan.N, lambda f: poses[f], loop=False)
    return act, plan, raw


# ============================================================================== blend-tree QA
TREE = [("Stand", None, G.WALK_SLOW.frames, 0.0), ("Walk_Slow", "Walk_Slow_RM", G.WALK_SLOW.frames, G.WALK_SLOW.stride),
        ("Walk", "Walk_RM", G.WALK.frames, G.WALK.stride), ("Trot", "Trot_RM", G.TROT.frames, G.TROT.stride),
        ("Gallop", "Gallop_RM", G.GALLOP.frames, G.GALLOP.stride)]


class ExportSampler:
    """local (loc, quat) of every bone per frame in the EXPORT hierarchy (hooves under the lower legs), numpy FK"""

    def __init__(self, calf):
        self.calf = calf
        self.names = [n for n in calf.order]
        self.idx = {n: i for i, n in enumerate(self.names)}
        par = dict(calf.par); par.update(A.HOOF_PARENT)
        self.par = [self.idx[par[n]] if par[n] else -1 for n in self.names]
        # FK order for the export hierarchy
        order, seen = [], set()
        def visit(i):
            if i in seen: return
            if self.par[i] >= 0: visit(self.par[i])
            seen.add(i); order.append(i)
        for i in range(len(self.names)): visit(i)
        self.order = order
        rest = [np.array(calf.rest[n]) for n in self.names]
        self.rest = np.array(rest)
        self.rel = np.array([np.linalg.inv(rest[self.par[i]]) @ rest[i] if self.par[i] >= 0 else rest[i]
                             for i in range(len(self.names))])
        self.cache = {}

    def clip(self, name):
        if name in self.cache: return self.cache[name]
        act = bpy.data.actions[name]; calf = self.calf
        calf.use_action(act)
        lo, hi = int(act.frame_range[0]), int(act.frame_range[1])
        L = np.zeros((hi - lo + 1, len(self.names), 7))
        for k, f in enumerate(range(lo, hi + 1)):
            calf.sc.frame_set(f)
            ae = calf.arm.evaluated_get(bpy.context.evaluated_depsgraph_get())
            P = [np.array(ae.pose.bones[n].matrix) for n in self.names]
            for i in range(len(self.names)):
                pi = self.par[i]
                M = np.linalg.inv(P[pi] @ self.rel[i]) @ P[i] if pi >= 0 else np.linalg.inv(self.rel[i]) @ P[i]
                q = Matrix(M.tolist()).to_quaternion()
                L[k, i, :3] = M[:3, 3]; L[k, i, 3:] = (q.w, q.x, q.y, q.z)
        for i in range(len(self.names)):            # consistent quaternion hemisphere over time
            for k in range(1, len(L)):
                if np.dot(L[k, i, 3:], L[k - 1, i, 3:]) < 0: L[k, i, 3:] *= -1
        self.cache[name] = L
        return L

    @staticmethod
    def blend(La, Lb, w):
        qa, qb = La[:, 3:], Lb[:, 3:].copy()
        s = np.sign(np.sum(qa * qb, axis=-1, keepdims=True)); s[s == 0] = 1
        qb = qb * s
        out = np.empty_like(La)
        out[:, :3] = La[:, :3] * (1 - w) + Lb[:, :3] * w
        q = qa * (1 - w) + qb * w
        out[:, 3:] = q / np.linalg.norm(q, axis=-1, keepdims=True)
        return out

    @staticmethod
    def sample(L, u):
        n = len(L) - 1; t = (u % 1.0) * n; i = int(math.floor(t)); f = t - i
        if i >= n: return L[n].copy()
        return ExportSampler.blend(L[i], L[i + 1], f)

    def fk(self, L):
        q = L[:, 3:]; w, x, y, z = q[:, 0], q[:, 1], q[:, 2], q[:, 3]
        B = np.zeros((len(L), 4, 4))
        B[:, 0, 0] = 1 - 2 * (y * y + z * z); B[:, 0, 1] = 2 * (x * y - z * w); B[:, 0, 2] = 2 * (x * z + y * w)
        B[:, 1, 0] = 2 * (x * y + z * w); B[:, 1, 1] = 1 - 2 * (x * x + z * z); B[:, 1, 2] = 2 * (y * z - x * w)
        B[:, 2, 0] = 2 * (x * z - y * w); B[:, 2, 1] = 2 * (y * z + x * w); B[:, 2, 2] = 1 - 2 * (x * x + y * y)
        B[:, :3, 3] = L[:, :3]; B[:, 3, 3] = 1
        P = np.zeros_like(B)
        for i in self.order:
            pi = self.par[i]
            P[i] = (P[pi] @ self.rel[i] @ B[i]) if pi >= 0 else self.rel[i] @ B[i]
        return P


def blend_tree_qa(calf, weights=(0.25, 0.5, 0.75), n=120, cycles=2, tol=0.006, log=print):
    S = ExportSampler(calf)
    have = {c for c, _, _, _ in TREE if c in bpy.data.actions}
    feet = {leg: (S.idx[d["foot"]], S.idx[d["toe"]]) for leg, d in LEGS.items()}
    toe_len = {leg: calf.bones[d["toe"]].length for leg, d in LEGS.items()}
    rest_z = {leg: calf.rest_head(d["foot"]).z for leg, d in LEGS.items()}
    iroot = S.idx["Root"]; rest_root_inv = np.linalg.inv(S.rest[iroot])
    out = []
    for (a, _, fa, sa), (b, _, fb, sb) in zip(TREE, TREE[1:]):
        if a not in have or b not in have:
            continue
        La, Lb = S.clip(a), S.clip(b)
        for w in weights:
            T = ((1 - w) * fa + w * fb) / FPS; D = (1 - w) * sa + w * sb
            rows = []
            for k in range(n * cycles + 1):
                u = k / n
                P = S.fk(S.blend(S.sample(La, u), S.sample(Lb, u), w))
                Rinv = np.linalg.inv(P[iroot] @ rest_root_inv)
                pts = {}
                for leg, (fi, ti) in feet.items():
                    M = Rinv @ P[fi]; Mt = Rinv @ P[ti]
                    tip = Mt[:3, 3] + Mt[:3, 1] * toe_len[leg]
                    pts[leg] = (M[:3, 3] + np.array([0, -D * u, 0]), tip + np.array([0, -D * u, 0]))
                rows.append(pts)
            dt = T / n
            worst = dict(skate=(0.0, ""), mean=0.0, sink=(1.0, ""), ipsi=1e9)
            for leg in LEGS:
                fet = np.array([r[leg][0] for r in rows])
                dz = fet[:, 2] - rest_z[leg]
                c = dz < tol
                v = np.linalg.norm(np.diff(fet[:, :2], axis=0), axis=1) / dt
                both = c[:-1] & c[1:]
                run = best = 0.0
                for i in range(len(v)):
                    run = run + v[i] * dt if both[i] else 0.0
                    best = max(best, run)
                if best > worst["skate"][0]: worst["skate"] = (best, leg)
                if both.any(): worst["mean"] = max(worst["mean"], float(v[both].mean()))
                if dz.min() < worst["sink"][0]: worst["sink"] = (float(dz.min()), leg)
            for s in "LR":
                d = min(np.linalg.norm(r[s + "F"][1] - r[s + "H"][1]) for r in rows)
                worst["ipsi"] = min(worst["ipsi"], d)
            out.append((a, b, w, worst))
            log(f"  BLEND {a:9s}/{b:9s} w={w:.2f}: {D / T:4.2f} m/s | longest hoof skate {worst['skate'][0]*100:5.1f} cm "
                f"({worst['skate'][1]}) | worst mean skate speed {worst['mean']:.2f} m/s | lowest fetlock "
                f"{worst['sink'][0]*1000:6.1f} mm vs rest ({worst['sink'][1]}) | same-side hoof tips >= {worst['ipsi']*100:.1f} cm")
    return out


# ============================================================================== QA
def turn_qa(calf, act, plan, raw_excess, log=print):
    N = plan.N
    calf.qa(act, N, plan.planted, label=act.name)
    # exact ends: frame 0 == Pose(), last frame == Pose() under the final yaw (root-relative)
    ref = calf.make_clip("__ref_pose", 0, lambda f: Pose(), loop=False)
    def states(a, frames):
        calf.use_action(a); out = []
        for f in frames:
            calf.sc.frame_set(f)
            ae = calf.arm.evaluated_get(bpy.context.evaluated_depsgraph_get())
            R = ae.pose.bones["Root"].matrix.inverted()
            out.append({pb.name: R @ pb.matrix for pb in ae.pose.bones})
        return out
    s0, sN = states(act, [0, N]); r = states(ref, [0])[0]
    def diff(a, b):
        return max((a[n].translation - b[n].translation).length for n in a) * 1000, \
            max(math.degrees(a[n].to_quaternion().rotation_difference(b[n].to_quaternion()).angle) for n in a)
    d0, dN = diff(s0, r), diff(sN, r)
    bpy.data.actions.remove(ref)
    calf.use_action(act); calf.sc.frame_set(N)
    ae = calf.arm.evaluated_get(bpy.context.evaluated_depsgraph_get())
    yaw_end = math.degrees(ae.pose.bones["Root"].matrix.to_euler().z)
    dev = 0.0
    for leg in LEGS:
        for f in range(N + 1):
            if plan.planted(leg, f):
                th = plan.targets[leg][sum(1 for a, _ in plan.steps[leg] if f >= a)]
                dev = max(dev, abs(th - plan.yaw(f)))
    log(f"  TURN {act.name}: f0 vs Pose() {d0[0]:.4f} mm / {d0[1]:.4f} deg | f{N} vs Pose() {dN[0]:.4f} mm / {dN[1]:.4f} deg"
        f" | root yaw end {yaw_end:.3f} deg | planted hoof vs body yaw <= {dev:.1f} deg | raw reach excess "
        f"{raw_excess*1000:.1f} mm (vaulted)")
    try:
        from clips.actions import MeshProbe, joint_bends
        jb = joint_bends(calf, act, N)
        carpus = [v for l in ("LF", "RF") for v in jb[l]]; hock = [v for l in ("LH", "RH") for v in jb[l]]
        mp = MeshProbe(calf); res = mp.check(act, N, plan.planted)
        log(f"  TURN {act.name}: carpus {min(carpus):.1f}..{max(carpus):.1f} deg, hock {min(hock):.1f}..{max(hock):.1f} "
            f"deg (+ = anatomical) | LOD2 body min z {res['body_min']*100:.2f} cm (rest {res['rest_body']*100:.2f}), "
            f"hoof min z {res['hoof_min']*100:.2f} cm (rest {res['rest_hoof']*100:.2f}), planted hoof z vs rest "
            f"<= {res['contact'][0]*1000:.1f} mm")
    except Exception as e:      # the mesh probe needs the Calf_LOD2 mesh
        log(f"  TURN {act.name}: mesh QA skipped ({e})")
    return dict(d0=d0, dN=dN, yaw_end=yaw_end, dev=dev)


# ============================================================================== build
def build(calf, log=print):
    made = []
    act = calf.make_clip("Stand", STAND_N, stand_fn, loop=True)
    made.append("Stand")
    made += build_walk_slow(calf)
    calf.qa(bpy.data.actions["Walk_Slow_RM"], G.WALK_SLOW.frames, A.flat_planted_fn_for(G.WALK_SLOW), label="Walk_Slow_RM")
    for name, deg in (("TurnLeft90", 90.0), ("TurnRight90", -90.0)):
        act, plan, raw = build_turn(calf, name, deg)
        turn_qa(calf, act, plan, raw, log=log)
        made.append(name)
    if all(n in bpy.data.actions for n in ("Walk", "Trot", "Gallop")):
        blend_tree_qa(calf, log=log)
    return made


if __name__ == "__main__":
    ROOT = os.path.dirname(TOOLS)
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src", default=os.path.join(ROOT, "build", "stage_b.blend"))
    ap.add_argument("--out", default=None)
    ap.add_argument("--no-gaits", action="store_true")
    a = ap.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:])
    calf = A.Calf(a.src)
    if not a.no_gaits:
        for g in (G.WALK, G.TROT, G.GALLOP):
            N, fn = A.gait_pose_fn(calf, g, cycles=1)
            act = calf.make_clip(g.name + "_RM", N, fn, stance_fn=A.planted_fn_for(g), loop=True)
            calf.duplicate_in_place(act, g.name)
    print("family locomotion:", build(calf))
    if a.out:
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        calf.save(a.out); print("saved", a.out)
