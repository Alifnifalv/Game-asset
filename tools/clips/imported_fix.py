"""Repairs of the imported clips (cow.glb Idle / Eating, re-solved on the calf rig by tools/rebake_leg_ik.py).

    build(calf) -> []     (repairs bpy.data.actions["Idle"] and ["Eating"] in place; both are already in
                           calf_animations' clip list)

Idle, left hind (review A3): the source steps the left hind hoof 93 mm forward (lift f24-33, 56 mm high) and then
SLIDES it back to its start spot while it is flat on the ground (f33-39, up to 24 mm/f). The repair keeps the
source's forward step, keeps the hoof world-locked where it lands, and brings it back with a real step while the
body's weight is shifted onto the right legs (body x -10 mm, f40-60): lift-off f46, touch-down f57, 35 mm lift,
zero velocity at both ends. Both steps get a toe-back hoof flex tied to the lift (flex = K h^2, 25 deg at the source's
56 mm peak; the hoof tip then never dips below its rest height). The leg chain (BackUpperLeg / BackLowerLeg) is
re-solved analytically on every frame whose target changed, keeping each frame's own bend plane and hock side from
the source bake, so the frames where nothing changed come out identical (continuity at both ends of the edit).

Eating, muzzle height: the source clip was made for the adult cow's reach. On the final stage B (smaller calf head,
head_scale 0.97) its nose pad never comes lower than ~11.7 cm (4.7 cm with the old, bigger head): the calf ate air.
The repair adds a pitch offset to the neck (Neck1/2/3 share it 0.40/0.35/0.25, + = head lower) and the opposite pitch
to the Head, so the face keeps the source's angle to the ground and only the poll comes down. The offset is weighted
per frame by how far the head is down: d = (h0 - h) / (h0 - h_min) from the source nose-pad height h (h0 = the loop
start, head up; h_min = the lowest frame), w = smootherstep of d over 0.05..0.75, so w = 0 while the head is up
(including f0 = last frame: the loop seam is untouched) and 1 over the whole head-down stretch (the source's own
bob and chew motion is kept, only shifted down). The amplitude is solved (secant) so the clip's minimum nose-pad
height on Calf_LOD2 (the cage, the lowest LOD surface; LOD0/LOD1 sit ~3 mm higher) is EAT_TARGET = 3.5 cm. The legs
are not touched. The nose pad is measured on the evaluated mesh (faces with orig_part == 3). On the final stage B the
solve gives 15.9 deg of neck pitch (Head -15.9 deg), w = 1 on f20-131: nose pad min LOD2 11.35 -> 3.50 cm, LOD0
11.67 -> 3.83 cm (f92); LOD0 3.8-7.2 cm over f30-120 (the source's chew bobs are kept).

Also: QA lines for the imported clips: a planted-foot function (fetlock within 2 mm of its rest height), which
tools/calf_animations.py does not pass for them (it reported "planted slide 0.00 mm" for the sliding Idle), and the
Eating nose pad (min z per LOD, non-hoof LOD2 min z, first vs last frame).

Standalone: python3 tools/clips/imported_fix.py [--in build/stage_b_rebaked.blend] [--out DIR/test.blend]
  (the input must already hold the re-solved Idle/Eating of the CURRENT stage B, e.g. a scratch copy made with
  python3 tools/rebake_leg_ik.py --in build/stage_b.blend --out <scratch>/rebaked.blend --actions Eating,Idle;
  build/stage_b_rebaked.blend is only as fresh as the last calf_animations.py run)
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
from anim_lib import LEGS

LEG = "LH"
LAND = 33                 # source touch-down of the forward step (hoof flat on the ground from here)
BACK = (46, 57)           # return step: lift-off, touch-down
BACK_LIFT = 0.035         # m
FLEX_K = 25.0 / 0.0565 ** 2   # deg per m^2 of lift (25 deg at the source step's 56.5 mm)
PLANT_TOL = 0.002

EAT_NECK = (("Neck1", 0.40), ("Neck2", 0.35), ("Neck3", 0.25))   # share of the neck pitch offset (+ = head lower)
EAT_HEAD = -1.0           # Head pitch per degree of neck offset: -1 keeps the source's face angle
EAT_DOWN = (0.05, 0.75)   # the weight ramps from 0 to 1 over this range of d (0 = head up, 1 = lowest frame)
EAT_TARGET = 0.035        # m: minimum nose-pad height over the clip after the repair (Calf_LOD2)
EAT_LOD = "Calf_LOD2"
NOSE_LODS = ("Calf_LOD0", "Calf_LOD1", "Calf_LOD2")


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


class NosePad:
    """Ground clearance of one skinned LOD per frame of an action: min z of the nose pad (vertices of the faces with
    orig_part == 3) and of every non-hoof vertex (not on an orig_part == 2 face). anim_lib.Calf keeps the meshes
    un-deformed for speed, so the armature modifier is switched on only while measuring."""

    def __init__(self, obj):
        self.ob = bpy.data.objects[obj]
        me = self.ob.data
        part = np.zeros(len(me.polygons), np.int32)
        me.attributes["orig_part"].data.foreach_get("value", part)
        self.nose = np.zeros(len(me.vertices), bool)
        self.hoof = np.zeros(len(me.vertices), bool)
        for p in me.polygons:
            if part[p.index] == 3: self.nose[list(p.vertices)] = True
            elif part[p.index] == 2: self.hoof[list(p.vertices)] = True

    def track(self, calf, act):
        """-> (nose min z per frame, non-hoof min z per frame), frames frame_range[0]..[1]"""
        mods = [m for m in self.ob.modifiers if m.type == "ARMATURE"]
        was = [m.show_viewport for m in mods]
        for m in mods: m.show_viewport = True
        calf.use_action(act)
        nose, body = [], []
        try:
            for f in range(int(act.frame_range[0]), int(act.frame_range[1]) + 1):
                calf.sc.frame_set(f)
                oe = self.ob.evaluated_get(bpy.context.evaluated_depsgraph_get())
                co = np.empty(len(oe.data.vertices) * 3); oe.data.vertices.foreach_get("co", co)
                M = np.array(oe.matrix_world)
                z = co.reshape(-1, 3) @ M[2, :3] + M[2, 3]
                nose.append(float(z[self.nose].min())); body.append(float(z[~self.hoof].min()))
        finally:
            for m, s in zip(mods, was): m.show_viewport = s
        return nose, body


def eating_weights(h):
    """per-frame weight of the Eating offset from the source nose-pad heights h: 0 while the head is up (the loop
    start height h[0]), 1 over the head-down stretch, smootherstep between (see the module docstring)"""
    h0, hmin = h[0], min(h)
    lo, hi = EAT_DOWN
    return [smoother(((h0 - z) / (h0 - hmin) - lo) / (hi - lo)) for z in h]


def fix_eating(calf, act):
    assert int(act.frame_range[0]) == 0, "Eating must start at frame 0 (write_curves keys frames 0..N)"
    probe = NosePad(EAT_LOD)
    h, _ = probe.track(calf, act)
    hmin = min(h)
    w = eating_weights(h)
    share = EAT_NECK + (("Head", EAT_HEAD),)
    calf.use_action(act)
    src = {n: [] for n, _ in share}
    for f in range(len(h)):
        calf.sc.frame_set(f)
        for n in src:
            pb = calf.arm.pose.bones[n]
            src[n].append((pb.location.copy(), pb.rotation_quaternion.copy()))

    def apply(amp):
        # additive pitch about each bone's rest lateral axis, on top of the source's local rotation
        calf.write_curves(act, {n: [(loc, calf.rot_about(n, A.X, amp * k * w[f]) @ q) for f, (loc, q) in enumerate(src[n])]
                                for n, k in share})
        return min(probe.track(calf, act)[0])

    # secant on the amplitude (deg of neck pitch at w = 1); the minimum height is close to linear in it
    a0, m0 = 0.0, hmin
    a1 = 10.0
    m1 = apply(a1)
    for _ in range(12):
        if abs(m1 - EAT_TARGET) < 1e-4 or m1 == m0:
            break
        a0, m0, a1 = a1, m1, a1 + (EAT_TARGET - m1) * (a1 - a0) / (m1 - m0)
        m1 = apply(a1)
    full = [f for f, x in enumerate(w) if x >= 1.0]
    zero = [f for f, x in enumerate(w) if x <= 0.0]
    down = [f for f in zero if f < full[0]], [f for f in zero if f > full[-1]]
    print(f"EATING fix: nose pad min z ({EAT_LOD}) {hmin*100:.2f} cm (f{h.index(hmin)}) -> {m1*100:.2f} cm "
          f"(target {EAT_TARGET*100:.1f} cm) | neck pitch offset {a1:.2f} deg x w(f) (Neck1/2/3 "
          f"{'/'.join(f'{k:.2f}' for _, k in EAT_NECK)}), Head {EAT_HEAD*a1:+.2f} deg x w(f) | w = 0 on "
          f"f0-{down[0][-1] if down[0] else '-'} and f{down[1][0] if down[1] else '-'}-{len(w)-1}, 1 on f{full[0]}-{full[-1]}")
    return dict(amp=a1, src_min=hmin, new_min=m1, w=w)


def eating_qa(calf, act):
    """nose pad min z per LOD, LOD2 non-hoof min z, and the loop seam (first vs last frame, every bone)"""
    parts, lows = [], []
    body = None
    for n in NOSE_LODS:
        if n not in bpy.data.objects: continue
        nose, b = NosePad(n).track(calf, act)
        m = min(nose); lows.append(m)
        parts.append(f"{n[-4:]} {m*100:.2f} cm (f{nose.index(m)})")
        if n == "Calf_LOD2": body = min(b)
    calf.use_action(act)
    N = int(act.frame_range[1])
    st = []
    for f in (0, N):
        calf.sc.frame_set(f)
        st.append({pb.name: (pb.location.copy(), pb.rotation_quaternion.copy()) for pb in calf.arm.pose.bones})
    dl = max((st[0][n][0] - st[1][n][0]).length for n in st[0])
    da = max(math.degrees(st[0][n][1].rotation_difference(st[1][n][1]).angle) for n in st[0])
    lo = min(lows)
    print(f"QA Eating nose pad: min z {' | '.join(parts)} -> {'OK' if lo >= 0.015 else 'BELOW'} 1.5 cm | "
          f"LOD2 non-hoof min z {body*100:.2f} cm | f0 vs f{N}: max loc diff {dl*1000:.4f} mm, max rot diff {da:.4f} deg")
    return dict(nose_min=lo, body_min=body, seam=(dl, da))


def qa(calf):
    out = {}
    for n in ("Idle", "Eating"):
        act = bpy.data.actions.get(n)
        if act is None: continue
        out[n] = calf.qa(act, int(act.frame_range[1]), planted_by_height(calf, act), label=n + " (planted = fetlock <2 mm up)")
    act = bpy.data.actions.get("Eating")
    if act is not None:
        out["Eating_nose"] = eating_qa(calf, act)
    return out


def build(calf):
    act = bpy.data.actions.get("Idle")
    if act is None:
        print("imported_fix: no Idle action")
    else:
        fix_idle(calf, act)
    act = bpy.data.actions.get("Eating")
    if act is None:
        print("imported_fix: no Eating action")
    else:
        fix_eating(calf, act)
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
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        calf.save(a.out); print("saved", a.out)
