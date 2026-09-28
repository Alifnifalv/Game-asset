# Game-asset: Young Cow (Calf) for Unity

**Read this first, then `docs/WORKLOG.md` (what was done, why, and what's next) and `docs/PLAN.md` (scope and phases).**

## Goal
A game-ready **young cow (calf)** for a Unity game. The quality and content target is GiM Studio's *Animalia - Cow (young)*.
The user decided to **build it in-house**; do not suggest buying the GiM asset.
Scope: model + 4K PBR textures + LODs + rig + full animation set (walk/trot/gallop/turns, idles, graze, eat,
lie down / lying idle / get up, death, leap) + Unity import/setup.

## Repo layout
| Path | What |
|---|---|
| `cow.glb` | Source model (low-poly adult cow from Sketchfab, 43-bone quadruped rig, Eating + Idle clips). Read-only. |
| `Gemini_Generated_Image_*.png`, `2259689e-*.webp` | Side-view references of the GiM young cow (coat pattern, proportions) |
| `Young Cow animation preview.mp4`, `videoplayback (1).mp4` | GiM young cow animation previews (the second is the 1080p version) |
| `videoplayback.mp4` | GiM adult female cow animation preview |
| `tools/` | The whole pipeline, as headless Blender Python scripts (see below) |
| `build/` | **gitignored** intermediates (`stage_a.blend`, `stage_b.blend`, snapshots, test outputs); regenerate with the tools |
| `Unity/Calf/` | Deliverables for Unity (FBX, GLB, textures, README with import settings) |
| `docs/` | `PLAN.md` (scope/phases), `WORKLOG.md` (chronological log + current status) |

## Environment (cloud container; nothing is preinstalled)
```bash
pip install bpy                       # Blender 5.0.1 as a Python module (no blender binary; download.blender.org is blocked)
pip install "numpy<2" pillow "opencv-python-headless<4.11" imageio imageio-ffmpeg trimesh   # bpy pins numpy 1.26
```
- Run scripts with `python3 tools/<script>.py` (they `import bpy`). Only Cycles on the CPU works (no GPU, no EEVEE). There are 4 cores: keep test renders ≤480 px at ≤24 samples.
- Blocked hosts: download.blender.org, youtube.com, gim.studio, assetstore.unity.com. PyPI and npm are reachable.
- Unity is **not** available here. C#/shaders can't be compiled, so flag them as needing a Unity check.

## Pipeline (run in order)
```bash
python3 tools/calf_stage_a.py      # cow.glb -> build/stage_a.blend: strip hierarchy, remove horns/udder, join+weld, quads, clean bone names
python3 tools/calf_stage_b.py      # -> build/stage_b.blend: calf reshape (warp mesh + rest bones together), jaw/ear bones, eyes,
                                   #    UVs, meters, 30 fps retime, LOD0/1/2 via subdivision
python3 tools/calf_textures.py --in build/stage_b.blend --out build/stage_c.blend --tex-dir build/textures --res 4096
python3 tools/calf_animations.py   # (WIP) builds the animation set with tools/anim_lib.py + tools/anim_gait.py
python3 tools/export_unity.py ...  # -> Unity/Calf/ (FBX + GLB + textures); then tools/validate_export.py
```
Check tools: `tools/render_views.py` (contact-sheet renders), `tools/silhouette_compare.py` (side silhouette vs the reference),
`tools/check_animation.py` (leg/foot consistency, stretch, loops), `tools/rebake_leg_ik.py` (re-solve leg IK for imported clips).

## Conventions (every tool relies on these)
- **Units and axes:** meters, Z up, and the calf **faces -Y** (Unity +Z after FBX export). Ground at z=0. Withers ≈1.0 m.
- **Timing:** 30 fps. Actions use integer frames, with `use_frame_range` set and `use_cyclic` set for loops.
- **Objects:** `CalfRig` (armature), with children `Calf_LOD0` (~47k tris), `Calf_LOD1` (~12k), `Calf_LOD2` (~2.7k). All LODs share one UV layout (`UVMap`).
- **Material slots:** `[0] M_Calf_Body`, `[1] M_Calf_Eye`. The face attribute `orig_part` holds 0 coat, 1 old light patches, 2 hooves, 3 nose pad, 4 eyeball.
- **Bones:**
  - Main chain: `Root` (ground; root-motion node), `Body` (COG), then the spine `Back`, `Torso`, `Torso2`, `Torso3` (running from rump to chest), then `Neck1-3`, `Head`, `Jaw`, `Ear.L/R`, `Tail1-7`.
  - Front legs: `FrontShoulder.X`, `FrontUpperLeg.X`, `FrontLowerLeg.X`.
  - Hind legs: `BackShoulder.X`, `BackLeg.X` (femur), `BackUpperLeg.X`, `BackLowerLeg.X`.
  - **Feet are separate bones parented to `Root`:** `IKFrontLeg.X` with its child `FF.X` (front), and `IKBackLeg.X` with its child `FFB.X` (hind). They carry the hoof weights.
  - `PoleTarget(Back).X` are unweighted IK pole helpers.
  - `.L` is +X.
- **Leg IK:** the lower-leg bones end exactly at the foot bone head (the fetlock); stage B fixes the importer-invented tails. Authoring uses IK (lower leg → foot bone, pole = PoleTarget bones, chain 2, pole angle auto-solved), which is then **baked to FK**. Exported clips have no constraints.

## Blender 5 API gotchas
- Actions are layered and slotted: fcurves live in `action.layers[].strips[].channelbags[].fcurves`, not `action.fcurves`. After `animation_data.action = act`, also set `animation_data.action_slot = act.slots[0]` when the action has slots.
- The glTF importer invents leaf-bone tails and imports 30 fps samples onto a 24 fps timeline (0.8-frame spacing); stage B fixes both.
- A mesh parented to the armature inherits the armature's scale. When scaling both, unparent first (stage B does this).
- `render.render()` works headless with Cycles; Workbench/EEVEE need a GPU context and fail.

## Working rules
- Never modify the reference media or `cow.glb`.
- Keep the tools deterministic and parameterised (`--in`/`--out`), because each stage is re-run when an earlier stage changes.
- After each milestone, **append to `docs/WORKLOG.md`** (what changed, why, verification numbers, next steps) and commit.
- Development branch: `claude/peaceful-lamport-fk2lw7`.
