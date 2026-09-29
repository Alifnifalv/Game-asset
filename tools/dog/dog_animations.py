"""Dog stage D: every Rottweiler clip, baked to FK keys, with a QA gate.

  python3 tools/dog/dog_animations.py [--in build/dog/stage_c.blend] [--out build/dog/stage_d.blend]

Imports every tools/dog/clips/*.py whose name does not start with '_' (sorted), calls build(rig) and then runs the
QA on each clip (tools/dog/dog_anim.qa_clip + joint_check).  QA GATE (exit 1 on a violation):
  IK gap <= 0.1 mm (every paw reaches its target: nothing was clamped)
  planted slide <= 0.1 mm where the family defines planted_fn (the _RM gaits, the idles, the Jump stances)
  loop seam <= 0.01 mm on cyclic clips (root-relative)
  joints: elbow / stifle / hock keep the bend direction of the rest pose (never bend backward by more than 0.5 deg),
          the carpus does not dorsiflex past 65 deg (a loaded dog carpus reaches ~60-70)
  leg twist: no leg bone rolls about its own axis by more than 12 deg between frames (validator FAIL: 15)
  ground: LOD2 non-paw min z >= -2 cm, paw min z >= -2 cm
Writes the manifest of clip ranges / loop / root motion into the blend's custom properties via the actions.
"""
import argparse, importlib, math, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "clips")); sys.path.insert(0, os.path.dirname(HERE))
os.environ.setdefault("ASSET", "dog")
import bpy
from mathutils import Vector
import asset_profile as AP
import dog_anim as D

LIMITS = dict(gap_mm=0.1, slide_mm=0.1, seam_mm=0.01, back_deg=0.5, carpus_ext_deg=65.0, body_min_cm=-2.0,
              paw_min_cm=-2.0, twist_deg=12.0)


def joint_angles(arm, leg):
    """signed bend angles (deg) of the leg joints about the leg plane normal: (upper-lower, lower-foot, foot-toe)"""
    L = D.LEGS[leg]
    pb = arm.pose.bones
    def d(b):
        return (pb[b].tail - pb[b].head).normalized()
    u, l, f, t = d(L["upper"]), d(L["lower"]), d(L["foot"]), d(L["toe"])
    n = u.cross(l)
    if n.length < 1e-6:
        n = Vector((1, 0, 0))
    n.normalize()
    def ang(a, b):
        return math.degrees(math.atan2(a.cross(b).dot(n), a.dot(b)))
    return ang(u, l), ang(l, f), ang(f, t)


def joint_check(rig, act):
    """min/max of the signed bends relative to the rest sign"""
    sc = bpy.context.scene
    arm = rig.arm
    rig.use_action(act)
    sc.frame_set(-10000)
    rest = {}
    for pbn in arm.pose.bones:
        pbn.matrix_basis.identity()
    bpy.context.view_layer.update()
    # rest bends from the rest matrices
    for k in D.LEGS:
        L = D.LEGS[k]
        def dr(b):
            return (rig.tail(b) - rig.head(b)).normalized()
        u, l, f = dr(L["upper"]), dr(L["lower"]), dr(L["foot"])
        n = u.cross(l).normalized()
        rest[k] = (math.degrees(math.atan2(u.cross(l).dot(n), u.dot(l))),
                   math.degrees(math.atan2(l.cross(f).dot(n), l.dot(f))))
    worst_back, worst_carpus = 0.0, 0.0
    self_where = [""]
    f0, f1 = int(act.frame_range[0]), int(act.frame_range[1])
    chain = [D.LEGS[k][r] for k in D.LEGS for r in ("upper", "lower", "foot", "toe")]
    prev = None
    joint_check.twist, joint_check.twist_where = 0.0, ""
    for fr in range(f0, f1 + 1):
        sc.frame_set(fr)
        # twist of every leg bone about its own axis between consecutive frames (the validator FAILs > 15 deg)
        cur = {b: arm.pose.bones[b].matrix.to_3x3() for b in chain}
        if prev is not None:
            for b in chain:
                y0, y1 = prev[b].col[1].normalized(), cur[b].col[1].normalized()
                x0 = y0.rotation_difference(y1) @ prev[b].col[0]
                tw = math.degrees(x0.angle(cur[b].col[0], 0.0))
                if tw > joint_check.twist:
                    joint_check.twist, joint_check.twist_where = tw, f"{b} f{fr - 1}->{fr}"
        prev = cur
        for k in D.LEGS:
            a1, a2, _ = joint_angles(arm, k)
            # main joint (elbow / stifle): must keep the rest sign
            if a1 * math.copysign(1, rest[k][0]) < 0 and abs(a1) > worst_back:
                worst_back = abs(a1); self_where[0] = f"{k} {'elbow' if k[0] == 'F' else 'stifle'} f{fr}"
            if k[0] == "H":           # hock: keeps its sign
                if a2 * math.copysign(1, rest[k][1]) < 0 and abs(a2) > worst_back:
                    worst_back = abs(a2); self_where[0] = f"{k} hock f{fr}"
            else:                     # carpus: extension past straight (the flexion side has the rest sign)
                ext = a2 * math.copysign(1, rest[k][1]) if rest[k][1] != 0 else 0
                worst_carpus = max(worst_carpus, ext)
    joint_check.where = self_where[0]
    return worst_back, worst_carpus


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default=os.path.join(AP.BUILD, "stage_c.blend"))
    ap.add_argument("--out", default=os.path.join(AP.BUILD, "stage_d.blend"))
    ap.add_argument("--only", default=None, help="comma list of families (debug)")
    a = ap.parse_args()
    t0 = time.time()
    bpy.ops.wm.open_mainfile(filepath=os.path.abspath(a.inp))
    bpy.context.scene.render.fps = D.FPS
    rig = D.DogRig()
    print(f"[anim] rest self-test: max basis deviation {rig.self_test():.2e}")
    fams = sorted(f[:-3] for f in os.listdir(os.path.join(HERE, "clips")) if f.endswith(".py") and not f.startswith("_"))
    if a.only:
        fams = [f for f in fams if f in a.only.split(",")]
    fails = []
    n = 0
    for fam in fams:
        mod = importlib.import_module(fam)
        names = mod.build(rig)
        n += len(names)
        for name in names:
            act = bpy.data.actions[name]
            pf = mod.planted_fn(name) if hasattr(mod, "planted_fn") else None
            r = D.qa_clip(rig, act, planted_fn=pf, verbose=False)
            back, carpus = joint_check(rig, act)
            rm = _root_travel(rig, act)
            line = (f"QA {name}: IK gap {r['gap_mm']:.3f} mm | planted slide {r['slide_mm']:.2f} mm | loop seam "
                    f"{r['seam_mm']:.3f} mm | body drop {act.get('dog_body_drop_mm', 0):.1f} mm | backward bend "
                    f"{back:.1f} deg {joint_check.where} | leg twist {joint_check.twist:.1f} deg/f {joint_check.twist_where} | carpus ext {carpus:.1f} deg | LOD2 min z body {r['body_min_cm']:.2f} cm, paws "
                    f"{r['paw_min_cm']:.2f} cm | root {rm:.3f} m | {'loop' if act.use_cyclic else 'once'} "
                    f"{int(act.frame_range[1]) + 1} f")
            print(line)
            bad = []
            if r["gap_mm"] > LIMITS["gap_mm"]: bad.append("IK gap")
            if r["slide_mm"] > LIMITS["slide_mm"]: bad.append("planted slide")
            if act.use_cyclic and r["seam_mm"] > LIMITS["seam_mm"]: bad.append("loop seam")
            if back > LIMITS["back_deg"]: bad.append("backward bend")
            if carpus > LIMITS["carpus_ext_deg"]: bad.append("carpus hyperextension")
            if joint_check.twist > LIMITS["twist_deg"]: bad.append("leg twist")
            if r["body_min_cm"] < LIMITS["body_min_cm"]: bad.append("body below ground")
            if r["paw_min_cm"] < LIMITS["paw_min_cm"]: bad.append("paw below ground")
            if bad:
                fails.append((name, bad))
    # rest pose on the timeline, no active action
    ad = rig.arm.animation_data
    if ad:
        ad.action = None
    for pbn in rig.arm.pose.bones:
        pbn.matrix_basis.identity()
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(a.out))
    print(f"[anim] {n} clips, wrote {a.out} ({time.time() - t0:.0f} s)")
    if fails:
        print("QA GATE: FAIL " + "; ".join(f"{nm}: {', '.join(b)}" for nm, b in fails))
        sys.exit(1)
    print(f"QA GATE: pass ({n} clips)")


def _root_travel(rig, act):
    rig.use_action(act)
    sc = bpy.context.scene
    sc.frame_set(int(act.frame_range[0]))
    a = D.eval_bone_heads(rig.arm, ["Root"])["Root"]
    sc.frame_set(int(act.frame_range[1]))
    b = D.eval_bone_heads(rig.arm, ["Root"])["Root"]
    return (b - a).length


if __name__ == "__main__":
    main()
