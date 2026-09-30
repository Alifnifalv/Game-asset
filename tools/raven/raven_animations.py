"""Raven stage D: every clip family (tools/raven/clips/*.py, sorted; names starting with '_' are helpers), the QA gate,
and the saved stage D blend.

  ASSET=raven python3 tools/raven/raven_animations.py [--in build/raven/stage_c.blend] [--out build/raven/stage_d.blend]
          [--only family,family]

A family module exposes
  build(rig) -> list[str]               the clip names it made (rig.make_clip(...))
  planted_fn(name) -> fn(side, f)       optional: True while that foot is planted (QA planted slide)
  QA_EXTRA = {clip: dict(...)}          optional gate overrides (e.g. a clip whose feet may leave the ground)

QA GATE (exit 1 on a violation): IK gap <= 0.1 mm (feet on target), planted slide <= 0.1 mm, loop seam <= 0.01 mm
(root-relative, every bone), clip boundaries: ground clips start and end on stand() (flight clips on fly_neutral())
within 0.01 mm / 0.05 deg unless the family says otherwise, rest self-test <= 1e-5.
"""
import argparse, importlib, math, os, sys, time
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "clips"))
sys.path.insert(0, os.path.dirname(HERE))
os.environ.setdefault("ASSET", "raven")
import bpy  # noqa: E402
import asset_profile as AP  # noqa: E402
import raven_anim as R  # noqa: E402

LIM = dict(gap_mm=0.1, slide_mm=0.1, seam_mm=0.01, boundary_mm=0.01)


def boundary_error(rig, act, pose):
    """max bone-head distance (root-relative, mm) between the clip's first/last frame and a reference pose"""
    M = rig.solve(pose)
    ref = {n: (M[n].to_translation() - M["Root"].to_translation()) for n in rig.order}
    poses = rig.clip_poses[act.name]
    out = []
    for P in (poses[0], poses[-1]):
        Mp = rig.solve(P)
        W = Mp["Root"].inverted()
        err = max(((W @ Mp[n]).to_translation() - (M["Root"].inverted() @ M[n]).to_translation()).length
                  for n in rig.order)
        out.append(err * 1000)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default=os.path.join(AP.BUILD, "stage_c.blend"))
    ap.add_argument("--out", default=os.path.join(AP.BUILD, "stage_d.blend"))
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    t0 = time.time()
    bpy.ops.wm.open_mainfile(filepath=os.path.abspath(a.inp))
    rig = R.RavenRig()
    st = rig.self_test()
    print(f"[anim] rest self-test {st:.2e}")
    fails = []
    if st > 1e-5:
        fails.append(f"rest self-test {st:.2e}")
    only = [x for x in a.only.split(",") if x]
    fams = sorted(f[:-3] for f in os.listdir(os.path.join(HERE, "clips")) if f.endswith(".py") and not f.startswith("_"))
    n_clips = 0
    for fam in fams:
        if only and fam not in only:
            continue
        mod = importlib.import_module(fam)
        names = mod.build(rig)
        extra = getattr(mod, "QA_EXTRA", {})
        for name in names:
            act = bpy.data.actions[name]
            pf = mod.planted_fn(name) if hasattr(mod, "planted_fn") else None
            res = R.qa_clip(rig, act, planted_fn=pf, label=f"{fam}/{name}")
            ex = extra.get(name, {})
            lim = dict(LIM, **{k: v for k, v in ex.items() if k in LIM})
            for k in ("gap_mm", "slide_mm", "seam_mm"):
                if k == "seam_mm" and not act.use_cyclic:
                    continue
                if res[k] > lim[k]:
                    fails.append(f"{name}: {k} {res[k]:.3f} > {lim[k]}")
            bnd = ex.get("boundary", "stand")
            if bnd:
                ref = R.stand() if bnd == "stand" else R.fly_neutral()
                e0, e1 = boundary_error(rig, act, ref)
                which = ex.get("ends", "both")
                errs = {"both": (e0, e1), "start": (e0,), "end": (e1,)}[which]
                print(f"BOUNDARY {name}: start {e0:.4f} mm, end {e1:.4f} mm vs {bnd} ({which})")
                if max(errs) > lim["boundary_mm"]:
                    fails.append(f"{name}: boundary {max(errs):.4f} mm vs {bnd}")
            n_clips += 1
    if fails:
        print("QA GATE: FAIL")
        for f in fails:
            print("  -", f)
    else:
        print(f"QA GATE: pass ({n_clips} clips)")
    rig.arm.animation_data.action = None
    for pb in rig.arm.pose.bones:
        pb.matrix_basis.identity()
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(a.out))
    print(f"[anim] wrote {a.out} ({time.time() - t0:.0f} s)")
    if fails:
        sys.exit(1)


if __name__ == "__main__":
    main()
