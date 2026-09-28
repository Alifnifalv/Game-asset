"""Repairs of the imported clips (cow.glb Idle / Eating, re-solved on the calf rig by tools/rebake_leg_ik.py).

    build(calf) -> []     (repairs bpy.data.actions["Idle"] in place; Idle is already in calf_animations' clip list)

Idle, left hind (review A3): the source steps the left hind hoof 93 mm forward (lift f24-33, 56 mm high) and then
SLIDES it back to its start spot while it is flat on the ground (f33-39, up to 24 mm/f). The repair keeps the
source's forward step, keeps the hoof world-locked where it lands, and brings it back with a real step while the
body's weight is shifted onto the right legs (body x -10 mm, f40-60): lift-off f46, touch-down f57, 35 mm lift,
zero velocity at both ends. Both steps get a toe-back hoof flex tied to the lift (flex = K h^2, 25 deg at the source's
56 mm peak; the hoof tip then never dips below its rest height). The leg chain (BackUpperLeg / BackLowerLeg) is
re-solved analytically on every frame whose target changed, keeping each frame's own bend plane and hock side from
the source bake, so the frames where nothing changed come out identical (continuity at both ends of the edit).

Also: a QA line for the imported clips with a planted-foot function (fetlock within 2 mm of its rest height), which
tools/calf_animations.py does not pass for them (it reported "planted slide 0.00 mm" for the sliding Idle).

Standalone: python3 tools/clips/imported_fix.py [--in build/stage_b_rebaked.blend] [--out DIR/test.blend]
  (the input must already hold the re-solved Idle, e.g. a copy made with tools/rebake_leg_ik.py)
"""
import argparse, math, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)
import bpy
from mathutils import Matrix, Quaternion, Vector
import anim_lib as A
from anim_lib import LEGS

LEG = "LH"
LAND = 33                 # source touch-down of the forward step (hoof flat on the ground from here)
BACK = (46, 57)           # return step: lift-off, touch-down
BACK_LIFT = 0.035         # m
FLEX_K = 25.0 / 0.0565 ** 2   # deg per m^2 of lift (25 deg at the source step's 56.5 mm)
PLANT_TOL = 0.002


def smoother(t):
    t = min(1.0, max(0.0, t))
    return t * t * t * (t * (6 * t - 15) + 10)


def _sample(calf, act, names):
    calf.use_action(act)
    lo, hi = int(act.frame_range[0]), int(act.frame_range[1])
    rows = []
    for f in range(lo, hi + 1):
        calf.sc.frame_set(f)
        ae = calf.arm.evaluated_get(bpy.context.evaluated_depsgraph_get())
        rows.append({n: ae.pose.bones[n].matrix.copy() for n in names})
    return rows


def _frame(d, n):
    """orthonormal frame (bone direction, bend-plane normal, third)"""
    d = d.normalized(); n = (n - d * n.dot(d)).normalized()
    return Matrix((d, n, d.cross(n))).transposed()


def fix_idle(calf, act):
    d = LEGS[LEG]
    up, lo_, foot, toe = d["chain"][0], d["chain"][1], d["foot"], d["toe"]
    top = calf.par[up]
    rows = _sample(calf, act, ["Root", top, up, lo_, foot])
    N = len(rows) - 1
    rest = calf.rest_head(foot)
    assert all((r["Root"].translation - calf.rest["Root"].translation).length < 1e-6 for r in rows), "Idle moves its Root"
    src = [r[foot].translation.copy() for r in rows]
    p_land = src[LAND].copy()
    # new fetlock track
    tgt, lift = [], []
    for f in range(N + 1):
        if f <= LAND:
            p = src[f].copy()
        elif f < BACK[0]:
            p = p_land.copy()
        elif f < BACK[1]:
            u = (f - BACK[0]) / float(BACK[1] - BACK[0])
            p = p_land.lerp(rest, smoother(u))
            p.z += BACK_LIFT * 16.0 * u * u * (1 - u) * (1 - u)
        else:
            p = rest.copy()
        tgt.append(p); lift.append(max(0.0, p.z - rest.z))
    l1, l2 = calf.bones[up].length, calf.bones[lo_].length
    q_up, q_lo, foot_b, toe_b = [], [], [], []
    for f, r in enumerate(rows):
        fl = FLEX_K * lift[f] ** 2
        M_foot = Matrix.Translation(tgt[f]) @ Matrix.Rotation(math.radians(fl), 4, "X") @ Matrix.Translation(-rest) @ calf.rest[foot]
        b_foot = (r["Root"] @ calf.rel(foot)).inverted() @ M_foot
        foot_b.append((b_foot.to_translation(), b_foot.to_quaternion()))
        toe_b.append((Vector(), calf.rot_about(toe, Vector((1, 0, 0)), 0.35 * fl)))
        Mu, Ml = r[up], r[lo_]
        par_u = r[top] @ calf.rel(up)
        if (tgt[f] - src[f]).length < 1e-7:
            q_up.append((Vector(), (par_u.inverted() @ Mu).to_quaternion()))
            q_lo.append((Vector(), ((Mu @ calf.rel(lo_)).inverted() @ Ml).to_quaternion()))
            continue
        S = Mu.translation.copy(); K0 = Ml.translation.copy(); T0 = src[f]; T = tgt[f]
        n = (K0 - S).cross(T0 - S).normalized()               # the source bake's bend plane at this frame
        v = T - S; dist = min(v.length, (l1 + l2) * 0.9999); u = v.normalized()
        a = (l1 * l1 - l2 * l2 + dist * dist) / (2 * dist); h = math.sqrt(max(0.0, l1 * l1 - a * a))
        w = n.cross(u).normalized()
        k0 = (K0 - S) - u * (K0 - S).dot(u)
        if w.dot(k0) < 0: w = -w                               # keep the hock on the source's side
        K = S + u * a + w * h
        R_up = _frame(K - S, n) @ _frame(K0 - S, n).transposed()
        R_lo = _frame(T - K, n) @ _frame(T0 - K0, n).transposed()
        Mu_new = Matrix.Translation(S) @ (R_up @ Mu.to_3x3()).to_4x4()
        Ml_new = Matrix.Translation(K) @ (R_lo @ Ml.to_3x3()).to_4x4()
        q_up.append((Vector(), (par_u.inverted() @ Mu_new).to_quaternion()))
        q_lo.append((Vector(), ((Mu_new @ calf.rel(lo_)).inverted() @ Ml_new).to_quaternion()))
    calf.write_curves(act, {up: q_up, lo_: q_lo, foot: foot_b, toe: toe_b})
    return tgt


def planted_by_height(calf, act, tol=PLANT_TOL):
    """planted_fn for clips without a gait model: a fetlock within `tol` of its rest height is planted"""
    hp = calf.hoof_positions(act, int(act.frame_range[1]))
    def fn(leg, f):
        return hp[f][leg][0].z - calf.rest_head(LEGS[leg]["foot"]).z < tol
    return fn


def qa(calf):
    out = {}
    for n in ("Idle", "Eating"):
        act = bpy.data.actions.get(n)
        if act is None: continue
        out[n] = calf.qa(act, int(act.frame_range[1]), planted_by_height(calf, act), label=n + " (planted = fetlock <2 mm up)")
    return out


def build(calf):
    act = bpy.data.actions.get("Idle")
    if act is None:
        print("imported_fix: no Idle action, nothing to do")
        return []
    fix_idle(calf, act)
    qa(calf)
    return []


if __name__ == "__main__":
    ROOT = os.path.dirname(TOOLS)
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src", default=os.path.join(ROOT, "build", "stage_b_rebaked.blend"))
    ap.add_argument("--out", default=None)
    a = ap.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:])
    calf = A.Calf(a.src)
    for n in ("Eating", "Idle"):
        A.complete_action(calf, bpy.data.actions[n])      # as tools/calf_animations.py does before the families
    print("before:"); qa(calf)
    build(calf)
    if a.out:
        calf.save(a.out); print("saved", a.out)
