"""Build the complete calf animation set.

python3 tools/calf_animations.py [--in build/stage_b.blend] [--out build/stage_d.blend] [--no-families] [--no-gate]
  The pipeline (tools/build_all.sh) passes --in build/stage_c.blend (stage B + textured materials); the default
  --in stage_b.blend gives a stage D without textures. The intermediate IK re-bake is written next to --out
  (<out>_rebaked.blend), so scratch runs never touch build/.

Pipeline
  1. re-solve leg IK of the imported clips (Eating, Idle) on the reshaped rig   (tools/rebake_leg_ik.py)
  2. gaits from tools/anim_gait.py: Walk/Trot/Gallop with root motion (*_RM) + in place
  3. clip families: every tools/clips/*.py whose name does not start with "_", in sorted filename order; each exposes
     build(calf) -> [action names]. Current families: actions (Death, Death_Lying, Leap, HeadShake), idle_graze
     (Idle_LookAround, Graze_Start/Loop/End, Call), imported_fix (repairs Idle/Eating in place, returns []),
     locomotion (Stand, Walk_Slow(_RM), TurnLeft90, TurnRight90), lying (LieDown, Lying_Idle, GetUp)
  4. QA gate on the authoring hierarchy (fails the build with exit code 1 unless --no-gate):
     - IK gap (lower-leg tip vs hoof bone) <= 0.1 mm on every clip (Idle <= 3 mm: the source over-reaches at f40)
     - planted-hoof slide <= 0.1 mm on the root-motion gaits (flat-hoof stance; toe roll-off is not slide)
     - loop seam <= 0.01 mm on cyclic clips
     - joint gate: no knee (carpus) or hock bends backward on any frame (clips.actions.joint_bends)
  5. export rig: hoof bones re-parented under the lower legs, every clip re-baked (engine blending safe), world-space
     hoof motion verified unchanged; save
"""
import argparse, importlib, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

ap = argparse.ArgumentParser()
_BUILD = os.path.join(ROOT, "build", "cow") if os.environ.get("ASSET", "calf").lower() == "cow" else os.path.join(ROOT, "build")
ap.add_argument("--in", dest="src", default=os.path.join(_BUILD, "stage_b.blend"))
ap.add_argument("--out", default=os.path.join(_BUILD, "stage_d.blend"))
ap.add_argument("--no-families", action="store_true")
ap.add_argument("--no-gate", action="store_true", help="print QA violations but do not fail")
a = ap.parse_args()

rebaked = os.path.splitext(os.path.abspath(a.out))[0] + "_rebaked.blend"
subprocess.run([sys.executable, os.path.join(HERE, "rebake_leg_ik.py"), "--in", a.src, "--out", rebaked,
                "--actions", "Eating,Idle"], check=True, stdout=subprocess.DEVNULL)

import bpy
import anim_lib as A, anim_gait as G, asset_profile as AP

calf = A.Calf(rebaked)
made = ["Eating", "Idle"]
for n in made:                      # imported clips leave some bones unkeyed -> key them at rest
    A.complete_action(calf, bpy.data.actions[n])
for g in (G.WALK, G.TROT, G.GALLOP):
    N, fn = A.gait_pose_fn(calf, g, cycles=1)
    act = calf.make_clip(g.name + "_RM", N, fn, stance_fn=A.planted_fn_for(g), loop=True)
    calf.duplicate_in_place(act, g.name)
    made += [g.name + "_RM", g.name]

if not a.no_families:
    for fn in sorted(os.listdir(os.path.join(HERE, "clips"))):
        if fn.endswith(".py") and not fn.startswith("_"):
            mod = importlib.import_module("clips." + fn[:-3])
            names = mod.build(calf)
            print(f"family {fn}: {names}")
            made += [n for n in names if n not in made]

# ---------------------------------------------------------------- QA gate (authoring hierarchy)
from clips.actions import joint_bends
violations = []
for n in made:
    act = bpy.data.actions[n]
    frames = int(act.frame_range[1])
    g = next((g for g in G.GAITS.values() if n == g.name + "_RM"), None)   # in-place clips slide by design
    r = calf.qa(act, frames, A.flat_planted_fn_for(g) if g else None, label=n)
    # Idle: the source clip over-reaches (right fore f46-55, straight leg): calf 2.27 mm; the adult cow keeps the
    # source proportions and reaches 3.84 mm at authoring scale (5.5 mm on the final 1.42x cow)
    gap_lim = (0.004 if AP.IS_COW else 0.003) if n == "Idle" else 0.0001
    if r["gap"] > gap_lim: violations.append(f"{n}: IK gap {r['gap']*1000:.2f} mm > {gap_lim*1000:.1f}")
    if g and r["slide"] > 0.0001: violations.append(f"{n}: planted slide {r['slide']*1000:.2f} mm")
    if act.use_cyclic and r["seam"] > 0.00001: violations.append(f"{n}: loop seam {r['seam']*1000:.3f} mm")
    jb = joint_bends(calf, act, frames)
    bad = [(leg, f, round(v, 1)) for leg, vals in jb.items() for f, v in enumerate(vals) if v < -0.5]   # 0.5 deg: numeric noise on straight legs
    if bad: violations.append(f"{n}: knee/hock bends backward {bad[:4]}")
if violations:
    print("QA GATE: %d violation(s)" % len(violations))
    for v in violations: print("  -", v)
    if not a.no_gate:
        sys.exit(1)
else:
    print("QA GATE: pass (%d clips)" % len(made))

# ---------------------------------------------------------------- export rig
before = {n: calf.hoof_positions(bpy.data.actions[n], int(bpy.data.actions[n].frame_range[1])) for n in made}
A.reparent_hooves_for_export(calf, [bpy.data.actions[n] for n in made])
worst = 0.0
for n in made:
    after = calf.hoof_positions(bpy.data.actions[n], int(bpy.data.actions[n].frame_range[1]))
    for rb, ra in zip(before[n], after):
        for leg in A.LEGS:
            worst = max(worst, (rb[leg][0] - ra[leg][0]).length, (rb[leg][1] - ra[leg][1]).length)
print(f"export rig: hooves re-parented under lower legs; max world-space hoof change {worst*1000:.3f} mm")
if worst > 0.0001 and not a.no_gate:
    sys.exit("export rig changed world-space hoof motion")
for n in [x.name for x in bpy.data.actions if x.name not in made]:
    bpy.data.actions.remove(bpy.data.actions[n])
calf.save(a.out)
print("saved", a.out, "clips (%d):" % len(made), made)
