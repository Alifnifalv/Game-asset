"""Re-solve the leg IK of every bone action on the reshaped calf rig and bake it back to FK keys.

Why: cow.glb shipped a leg-IK rig baked to FK (the IK constraints are gone). Stage B warped the rest
pose (torso shortened, x * 0.9, legs thinned...), so the baked FK rotations no longer land the
lower-leg chain end exactly on the foot bone the hoof is skinned to (IKFrontLeg / IKBackLeg, animated
by their own location keys). This re-adds the IK, re-solves every key time and bakes it back to FK.

Per leg:
  helper bone  "IKTip.<leg>": child of the lower leg, head = lower-leg head, tail = rest head of the
               foot bone = the REAL chain end. (glTF stores no bone tails; the importer invented the
               lower-leg tail ~0.13 x withers below the foot-bone head, under the ground.) The helper
               is IK-locked on all axes, so it is a rigid extension of the lower leg.
  IK constraint on the helper: target = foot bone head, pole = PoleTarget.X / PoleTargetBack.X,
               chain = helper + lower leg + upper leg (= chain_count 2 over the real leg bones;
               --back-chain 3 adds BackLeg), no stretch. The pole angle is solved numerically so the
               constrained rest pose equals the rest pose (zero rotation drift).
  bake:        at every key time of every action (the 0.8-frame fractional keys that come from the
               30 fps glTF data are kept) the constrained pose is evaluated, the chain bones' pose
               matrices are converted to local rotation_quaternion keys (linear) and written back;
               then the constraints and helper bones are removed. Action names, key times, frame
               ranges, NLA tracks and the active action stay as they were.

Usage
  python3 tools/rebake_leg_ik.py --in build/stage_b.blend --out build/stage_b_anim_test.blend
  python3 tools/rebake_leg_ik.py --in cow.glb --dry-run     # validation: re-solve the ORIGINAL rig,
                                                             # report how far the IK result is from its baked keys
Options: --legs front.L,front.R,back.L,back.R   --back-chain 2|3   --actions Eating,Idle
"""
import argparse, math, os, re, sys
import bpy
from mathutils import Matrix, Quaternion, Vector

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

LEG_DEFS = {
    "front.L": dict(chain=["FrontUpperLeg.L", "FrontLowerLeg.L"], foot="IKFrontLeg.L", pole="PoleTarget.L", back_extra="FrontShoulder.L"),
    "front.R": dict(chain=["FrontUpperLeg.R", "FrontLowerLeg.R"], foot="IKFrontLeg.R", pole="PoleTarget.R", back_extra="FrontShoulder.R"),
    "back.L": dict(chain=["BackUpperLeg.L", "BackLowerLeg.L"], foot="IKBackLeg.L", pole="PoleTargetBack.L", back_extra="BackLeg.L"),
    "back.R": dict(chain=["BackUpperLeg.R", "BackLowerLeg.R"], foot="IKBackLeg.R", pole="PoleTargetBack.R", back_extra="BackLeg.R"),
}


def clean(n):
    return "Root" if n == "GLTF_created_0_rootJoint" else re.sub(r"_\d+$", "", n)


def channelbags(act):
    for l in act.layers:
        for s in l.strips:
            for cb in s.channelbags:
                yield cb


def key_times(act):
    return sorted({round(kp.co[0], 4) for cb in channelbags(act) for fc in cb.fcurves for kp in fc.keyframe_points})


def set_frame(sc, f):
    fi = int(math.floor(f + 1e-6))
    sc.frame_set(fi, subframe=float(f - fi))
    return bpy.context.evaluated_depsgraph_get()


def use_action(arm, act):
    ad = arm.animation_data or arm.animation_data_create()
    ad.action = act
    if act is not None and act.slots:
        slot = next((s for s in act.slots if s.identifier == "OB" + arm.name), None)
        if slot is None and ad.action_slot is None:
            slot = act.slots[0]
        if slot is not None:
            ad.action_slot = slot


def reset_pose(arm):
    for pb in arm.pose.bones:
        pb.matrix_basis = Matrix.Identity(4)


def qangle(a, b):
    return math.degrees(a.rotation_difference(b).angle)


# ------------------------------------------------------------------------------------------
def load(path):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    if os.path.splitext(path)[1].lower() in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=path)
    else:
        bpy.ops.wm.open_mainfile(filepath=path)
    sc = bpy.context.scene
    arm = max((o for o in sc.objects if o.type == "ARMATURE"), key=lambda o: len(o.data.bones))
    names = {clean(b.name): b.name for b in arm.data.bones}
    return sc, arm, names


def set_mode(arm, mode):
    bpy.context.view_layer.objects.active = arm
    arm.select_set(True)
    if arm.mode != mode:
        bpy.ops.object.mode_set(mode=mode)


def add_helpers(arm, names, legs):
    set_mode(arm, "EDIT")
    eb = arm.data.edit_bones
    for leg in legs:
        d = LEG_DEFS[leg]
        lo, ft = eb[names[d["chain"][-1]]], eb[names[d["foot"]]]
        h = eb.new("IKTip." + leg)
        h.head, h.tail = lo.head.copy(), ft.head.copy()
        h.align_roll(lo.z_axis)
        h.parent, h.use_connect, h.use_deform = lo, False, False
    set_mode(arm, "OBJECT")


def remove_helpers(arm, legs):
    set_mode(arm, "EDIT")
    eb = arm.data.edit_bones
    for leg in legs:
        b = eb.get("IKTip." + leg)
        if b:
            eb.remove(b)
    set_mode(arm, "OBJECT")


def add_constraints(arm, names, legs, chain_len, poles):
    cons = {}
    for leg in legs:
        d = LEG_DEFS[leg]
        pb = arm.pose.bones["IKTip." + leg]
        pb.rotation_mode = "QUATERNION"
        pb.lock_ik_x = pb.lock_ik_y = pb.lock_ik_z = True
        c = pb.constraints.new("IK")
        c.name = "IK_rebake"
        c.target, c.subtarget = arm, names[d["foot"]]
        if poles[leg]:
            c.pole_target, c.pole_subtarget = arm, names[poles[leg]]
        c.chain_count = 1 + chain_len[leg]
        c.use_tail, c.use_stretch = True, False
        c.iterations = 500
        cons[leg] = c
    return cons


def chain_bones(leg, names, chain_len):
    d = LEG_DEFS[leg]
    bones = list(d["chain"])
    if chain_len[leg] == 3:
        bones = [d["back_extra"]] + bones
    return [names[b] for b in bones]


def rest_drift(sc, arm, legs, chains):
    """max rotation (deg) of each leg chain away from rest, with no action and identity basis."""
    dg = set_frame(sc, sc.frame_current)
    ae = arm.evaluated_get(dg)
    out = {}
    for leg in legs:
        out[leg] = max(qangle(ae.pose.bones[b].matrix.to_quaternion(), arm.data.bones[b].matrix_local.to_quaternion())
                       for b in chains[leg])
    return out


def solve_pole_angles(sc, arm, legs, cons, chains):
    """numeric search: pole angle that reproduces the rest pose (min rotation drift)."""
    ad = arm.animation_data
    saved = ad.action if ad else None
    use_action(arm, None)
    reset_pose(arm)
    legs = [leg for leg in legs if cons[leg].pole_target is not None]
    best = {leg: (1e9, 0.0) for leg in legs}
    if not legs:
        return {}

    def scan(cands):
        for i in range(len(cands[legs[0]])):
            for leg in legs:
                cons[leg].pole_angle = cands[leg][i]
            dr = rest_drift(sc, arm, legs, chains)
            for leg in legs:
                if dr[leg] < best[leg][0]:
                    best[leg] = (dr[leg], cands[leg][i])
    scan({leg: [math.radians(a) for a in range(-180, 180, 2)] for leg in legs})
    for step in (0.1, 0.005, 0.0002):          # degrees
        centre = {leg: math.degrees(best[leg][1]) for leg in legs}
        n = 25
        scan({leg: [math.radians(centre[leg] + (k - n) * step) for k in range(2 * n + 1)] for leg in legs})
    for leg in legs:
        cons[leg].pole_angle = best[leg][1]
    final = rest_drift(sc, arm, legs, chains)
    if saved is not None:
        use_action(arm, saved)
    return {leg: (math.degrees(best[leg][1]), final[leg]) for leg in legs}


def local_basis(pbe, arm):
    """pose-space matrix of an evaluated pose bone -> its local basis (what the keys must hold)."""
    b = arm.data.bones[pbe.name]
    if pbe.parent is None:
        return b.matrix_local.inverted() @ pbe.matrix
    rest_rel = arm.data.bones[pbe.parent.name].matrix_local.inverted() @ b.matrix_local
    return rest_rel.inverted() @ pbe.parent.matrix.inverted() @ pbe.matrix


def tip_error(ae, arm, names, legs, wh):
    out = {}
    M = ae.matrix_world
    for leg in legs:
        d = LEG_DEFS[leg]
        lo = names[d["chain"][-1]]
        tip_local = arm.data.bones[lo].matrix_local.inverted() @ arm.data.bones[names[d["foot"]]].head_local
        out[leg] = (M @ (ae.pose.bones[lo].matrix @ tip_local) - M @ ae.pose.bones[names[d["foot"]]].head).length / wh
    return out


def knee_bend(ae, arm, names, leg, chain):
    """signed angle (deg) between the upper-leg axis and knee->chain-end, about the upper leg's X axis."""
    d = LEG_DEFS[leg]
    up, lo = ae.pose.bones[chain[-2]], ae.pose.bones[chain[-1]]
    tip_local = arm.data.bones[lo.name].matrix_local.inverted() @ arm.data.bones[names[d["foot"]]].head_local
    v = (lo.matrix @ tip_local - lo.head).normalized()
    u = up.y_axis.normalized()
    return math.degrees(u.angle(v)) * math.copysign(1.0, u.cross(v).dot(up.x_axis))


def fk_quat_at(act, bone, t):
    """quaternion stored in the action for `bone` at time t (evaluated fcurves)."""
    q = [1.0, 0.0, 0.0, 0.0]
    for cb in channelbags(act):
        for i in range(4):
            fc = cb.fcurves.find(f'pose.bones["{bone}"].rotation_quaternion', index=i)
            if fc:
                q[i] = fc.evaluate(t)
    return Quaternion(q).normalized()


def write_quat_keys(act, bone, times, quats):
    cb = next(channelbags(act))
    grp = cb.groups.get(bone) or cb.groups.new(bone)
    path = f'pose.bones["{bone}"].rotation_quaternion'
    for i in range(4):
        fc = cb.fcurves.find(path, index=i)
        if fc is None:
            fc = cb.fcurves.new(path, index=i)
            fc.group = grp
        kps = fc.keyframe_points
        while len(kps):
            kps.remove(kps[len(kps) - 1], fast=True)
        kps.add(len(times))
        co = []
        for t, q in zip(times, quats):
            co += [t, q[i]]
        kps.foreach_set("co", co)
        for kp in kps:
            kp.interpolation = "LINEAR"
        fc.update()


def withers(arm, names):
    """withers-height proxy from the rig (no mesh needed): Back bone head height above the lowest foot tip."""
    M = arm.matrix_world
    bl = arm.data.bones
    top = max((M @ bl[names[n]].head_local).z for n in ("Back", "Torso3") if n in names)
    feet = min((M @ bl[names[LEG_DEFS[l]["foot"]]].tail_local).z for l in LEG_DEFS)
    return top - feet


# ------------------------------------------------------------------------------------------
def rebake(sc, arm, names, legs, chain_len, poles, only_actions=None, write=True, log=print, max_fix=0.01):
    """max_fix: legs whose FK chain end is further than this (x withers) from the foot bone are NOT
    rebaked (their keys are left untouched): such a clip does not drive the leg through the foot
    bone (e.g. an FK-only clip that never keys the foot bones), so re-solving would rewrite it."""
    chains = {leg: chain_bones(leg, names, chain_len) for leg in legs}
    wh = withers(arm, names)
    ad = arm.animation_data
    saved_action = ad.action if ad else None
    saved_slot = ad.action_slot if ad else None
    saved_frame = sc.frame_current
    nla_mute = [(t, t.mute) for t in ad.nla_tracks] if ad else []
    for t, _ in nla_mute:
        t.mute = True
    rest_before = {b.name: b.matrix_local.copy() for b in arm.data.bones}

    add_helpers(arm, names, legs)
    cons = add_constraints(arm, names, legs, chain_len, poles)
    pa = solve_pole_angles(sc, arm, legs, cons, chains)
    for leg in legs:
        if leg in pa:
            log(f"  {leg}: chain {chains[leg]} -> foot {names[LEG_DEFS[leg]['foot']]}, pole {names[poles[leg]]}, "
                f"pole angle {pa[leg][0]:.4f} deg, rest drift {pa[leg][1]:.6f} deg")
        else:
            log(f"  {leg}: chain {chains[leg]} -> foot {names[LEG_DEFS[leg]['foot']]}, no pole (chain plane from the FK pose)")

    acts = [a for a in bpy.data.actions if any(fc.data_path.startswith("pose.bones") for cb in channelbags(a) for fc in cb.fcurves)]
    if only_actions:
        acts = [a for a in acts if a.name in only_actions]
    report = {}
    baked = {}
    for act in sorted(acts, key=lambda a: a.name):
        reset_pose(arm)
        use_action(arm, act)
        times = key_times(act)
        bones = [b for leg in legs for b in chains[leg]]
        q_new = {b: [] for b in bones}
        m_ik = []                # constrained pose matrices for later verification
        tip_ik = {leg: 0.0 for leg in legs}
        tip_fk = {leg: 0.0 for leg in legs}
        bend_ik = {leg: [] for leg in legs}
        bend_fk = {leg: [] for leg in legs}
        for t in times:
            dg = set_frame(sc, t)
            ae = arm.evaluated_get(dg)
            te = tip_error(ae, arm, names, legs, wh)
            for leg in legs:
                tip_ik[leg] = max(tip_ik[leg], te[leg])
                bend_ik[leg].append(knee_bend(ae, arm, names, leg, chains[leg]))
            m_ik.append({b: ae.pose.bones[b].matrix.copy() for b in bones})
            for b in bones:
                bas = local_basis(ae.pose.bones[b], arm)
                q = bas.to_quaternion().normalized()
                prev = q_new[b][-1] if q_new[b] else fk_quat_at(act, b, t)
                if q.dot(prev) < 0:
                    q.negate()
                q_new[b].append(q)
        # FK (input) tip error, measured with the IK constraints muted
        for c in cons.values():
            c.mute = True
        for t in times:
            dg = set_frame(sc, t)
            ae = arm.evaluated_get(dg)
            te = tip_error(ae, arm, names, legs, wh)
            for leg in legs:
                tip_fk[leg] = max(tip_fk[leg], te[leg])
                bend_fk[leg].append(knee_bend(ae, arm, names, leg, chains[leg]))
        for c in cons.values():
            c.mute = False
        change = {b: max(qangle(fk_quat_at(act, b, t), q) for t, q in zip(times, q_new[b])) for b in bones}
        bend = {leg: dict(fk=(min(bend_fk[leg]), max(bend_fk[leg])), ik=(min(bend_ik[leg]), max(bend_ik[leg])),
                          max_change=max(abs(a - b) for a, b in zip(bend_fk[leg], bend_ik[leg])),
                          sign_flips=sum(1 for a, b in zip(bend_fk[leg], bend_ik[leg]) if a * b < 0 and max(abs(a), abs(b)) > 0.5))
                for leg in legs}
        skipped = [leg for leg in legs if tip_fk[leg] > max_fix]
        keep = [b for leg in legs if leg not in skipped for b in chains[leg]]
        report[act.name] = dict(times=len(times), tip_fk_max=tip_fk, tip_ik_max=tip_ik, rot_change_deg=change, knee=bend,
                                skipped_legs=skipped)
        baked[act.name] = (act, times, {b: q_new[b] for b in keep}, [{b: m[b] for b in keep} for m in m_ik])
        log(f"  action {act.name}: {len(times)} key times {times[0]:g}..{times[-1]:g}")
        for leg in skipped:
            log(f"     WARNING {leg}: FK chain end is {tip_fk[leg]:.4f} x withers from the foot bone (> --max-fix {max_fix}); "
                f"this clip does not drive the leg through the foot bone -> leg left untouched")
        for leg in legs:
            log(f"     {leg}: chain-end->foot  FK(before) {tip_fk[leg]:.6f}  IK-solved {tip_ik[leg]:.6f}  x withers-proxy; "
                f"rotation change " + ", ".join(f"{clean(b)} {change[b]:.3f} deg" for b in chains[leg]))
            k = bend[leg]
            log(f"            knee bend FK {k['fk'][0]:.2f}..{k['fk'][1]:.2f} deg -> IK {k['ik'][0]:.2f}..{k['ik'][1]:.2f} deg "
                f"(max change {k['max_change']:.2f} deg, sign flips {k['sign_flips']})")

    # ---- remove the temporary rig parts
    for leg in legs:
        pb = arm.pose.bones["IKTip." + leg]
        for c in list(pb.constraints):
            pb.constraints.remove(c)
    remove_helpers(arm, legs)
    rest_err = max((rest_before[b.name].to_translation() - b.matrix_local.to_translation()).length +
                   qangle(rest_before[b.name].to_quaternion(), b.matrix_local.to_quaternion()) for b in arm.data.bones)
    assert len(arm.data.bones) == len(rest_before), "helper bones not removed"
    log(f"  helpers removed: {len(arm.data.bones)} bones, max rest-matrix change {rest_err:.2e}")

    if not write:
        for t, m in nla_mute:
            t.mute = m
        return report

    # ---- write FK keys and verify they reproduce the constrained poses
    for name, (act, times, q_new, m_ik) in baked.items():
        for b, qs in q_new.items():
            write_quat_keys(act, b, times, qs)
    for name, (act, times, q_new, m_ik) in baked.items():
        reset_pose(arm)
        use_action(arm, act)
        err_rot, tip_after = 0.0, {leg: 0.0 for leg in legs}
        for t, mk in zip(times, m_ik):
            dg = set_frame(sc, t)
            ae = arm.evaluated_get(dg)
            for b, m in mk.items():
                err_rot = max(err_rot, qangle(ae.pose.bones[b].matrix.to_quaternion(), m.to_quaternion()))
            te = tip_error(ae, arm, names, legs, wh)
            for leg in legs:
                tip_after[leg] = max(tip_after[leg], te[leg])
        report[name]["baked_vs_ik_max_deg"] = err_rot
        report[name]["tip_baked_max"] = tip_after
        log(f"  verify {name}: baked FK vs IK pose max {err_rot:.5f} deg; chain-end->foot after bake " +
            ", ".join(f"{leg} {v:.6f}" for leg, v in tip_after.items()))

    # ---- restore the file's animation state
    reset_pose(arm)
    for t, m in nla_mute:
        t.mute = m
    if ad is not None:
        ad.action = saved_action
        if saved_action is not None and saved_slot is not None:
            ad.action_slot = saved_slot
    sc.frame_set(saved_frame)
    return report


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", default=None)
    ap.add_argument("--legs", default="front.L,front.R,back.L,back.R")
    ap.add_argument("--back-chain", type=int, default=2, choices=(2, 3), help="real bones in the hind-leg IK chain")
    ap.add_argument("--front-chain", type=int, default=2, choices=(2, 3), help="real bones in the front-leg IK chain")
    ap.add_argument("--front-pole", default="PoleTarget",
                    help="PoleTarget (default: validated on cow.glb, pole angle -90 reproduces its baked front legs exactly) | none")
    ap.add_argument("--back-pole", default="none",
                    help="none (default: validated on cow.glb, reproduces its baked hind legs exactly) | PoleTargetBack | PoleTarget")
    ap.add_argument("--actions", default=None)
    ap.add_argument("--dry-run", action="store_true", help="solve + report only, do not write keys")
    ap.add_argument("--max-fix", type=float, default=0.01,
                    help="skip legs whose FK chain end is further than this from the foot bone (fraction of withers)")
    a = ap.parse_args(argv)
    legs = a.legs.split(",")
    chain_len = {leg: (a.back_chain if leg.startswith("back") else a.front_chain) for leg in legs}
    poles = {}
    for leg in legs:
        p = a.back_pole if leg.startswith("back") else a.front_pole
        poles[leg] = None if p.lower() == "none" else f"{p}.{leg[-1]}"

    sc, arm, names = load(a.inp)
    print(f"rebake_leg_ik: {a.inp}  armature {arm.name}  ({len(arm.data.bones)} bones)")
    rep = rebake(sc, arm, names, legs, chain_len, poles, a.actions.split(",") if a.actions else None,
                 write=not a.dry_run, max_fix=a.max_fix)
    if a.dry_run or not a.out:
        return rep
    out = os.path.abspath(a.out)
    if os.path.abspath(a.inp) == out:
        raise SystemExit("refusing to overwrite the input file")
    bpy.ops.wm.save_as_mainfile(filepath=out, compress=True)
    print("saved", out)
    return rep


if __name__ == "__main__":
    main(sys.argv[1:])
