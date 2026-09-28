"""Build the complete calf animation set.

python3 tools/calf_animations.py [--in build/stage_b.blend] [--out build/stage_d.blend] [--only walk,trot,...] [--no-families]

Pipeline
  1. re-solve leg IK of the imported clips (Eating, Idle) on the reshaped rig   (tools/rebake_leg_ik.py)
  2. gaits from tools/anim_gait.py: Walk/Trot/Gallop with root motion (*_RM) + in place, TurnLeft90/TurnRight90
  3. key-pose clip families from tools/clips/*.py (each exposes build(calf) -> [action names])
  4. export rig: hoof bones re-parented under the lower legs, every clip re-baked (engine blending safe)
  5. save; print a QA table (IK gap / planted slide / loop seam per clip)
"""
import argparse, importlib, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

ap = argparse.ArgumentParser()
ap.add_argument("--in", dest="src", default=os.path.join(ROOT, "build", "stage_b.blend"))
ap.add_argument("--out", default=os.path.join(ROOT, "build", "stage_d.blend"))
ap.add_argument("--no-families", action="store_true")
a = ap.parse_args()

rebaked = os.path.join(ROOT, "build", "stage_b_rebaked.blend")
subprocess.run([sys.executable, os.path.join(HERE, "rebake_leg_ik.py"), "--in", a.src, "--out", rebaked,
                "--actions", "Eating,Idle"], check=True, stdout=subprocess.DEVNULL)

import bpy
import anim_lib as A, anim_gait as G

calf = A.Calf(rebaked)
made = ["Eating", "Idle"]
for n in made:                      # imported clips leave some bones unkeyed -> key them at rest
    A.complete_action(calf, bpy.data.actions[n])
for g in (G.WALK, G.TROT, G.GALLOP):
    N, fn = A.gait_pose_fn(calf, g, cycles=1)
    act = calf.make_clip(g.name + "_RM", N, fn, stance_fn=A.planted_fn_for(g), loop=True)
    calf.duplicate_in_place(act, g.name)
    made += [g.name + "_RM", g.name]
for name, deg in (("TurnLeft90", 90.0), ("TurnRight90", -90.0)):
    N, fn = A.gait_pose_fn(calf, G.WALK, cycles=2, turn_deg=deg, speed_scale=0.0)
    calf.make_clip(name, N, fn, stance_fn=A.planted_fn_for(G.WALK), loop=False)
    made.append(name)

if not a.no_families:
    for fn in sorted(os.listdir(os.path.join(HERE, "clips"))):
        if fn.endswith(".py") and not fn.startswith("_"):
            mod = importlib.import_module("clips." + fn[:-3])
            names = mod.build(calf)
            print(f"family {fn}: {names}")
            made += names

# QA before re-parenting (authoring hierarchy)
for n in made:
    act = bpy.data.actions[n]
    frames = int(act.frame_range[1])
    g = next((g for g in (G.WALK, G.TROT, G.GALLOP) if n == g.name + "_RM"), None)   # in-place clips slide by design
    calf.qa(act, frames, A.planted_fn_for(g) if g else None, label=n)

before = {n: calf.hoof_positions(bpy.data.actions[n], int(bpy.data.actions[n].frame_range[1])) for n in made}
A.reparent_hooves_for_export(calf, [bpy.data.actions[n] for n in made])
worst = 0.0
for n in made:
    after = calf.hoof_positions(bpy.data.actions[n], int(bpy.data.actions[n].frame_range[1]))
    for rb, ra in zip(before[n], after):
        for leg in A.LEGS:
            worst = max(worst, (rb[leg][0] - ra[leg][0]).length, (rb[leg][1] - ra[leg][1]).length)
print(f"export rig: hooves re-parented under lower legs; max world-space hoof change {worst*1000:.3f} mm")
for n in [x.name for x in bpy.data.actions if x.name not in made]:
    bpy.data.actions.remove(bpy.data.actions[n])
calf.save(a.out)
print("saved", a.out, "clips:", made)
