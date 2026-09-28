# Game-asset: Young Cow (Calf) for Unity

**Read this first, then `docs/WORKLOG.md` (current status, open issues, chronological log) and `docs/PLAN.md` (scope and phases).**
`docs/REFERENCES.md` describes the look target, and `docs/anim_lying.md` is the handoff for the lying clips.

## Goal
A game-ready **young cow (calf)** for a Unity game. The quality and content target is GiM Studio's *Animalia - Cow (young)*.
The user decided to **build it in-house**; do not suggest buying the GiM asset.
Scope: model + 4K PBR textures + LODs + rig + full animation set (walk/trot/gallop/turns, idles, graze, eat,
lie down / lying idle / get up, death, leap) + Unity import/setup.

## Repo layout
| Path | What |
|---|---|
| `cow.glb` | Source model (low-poly adult cow from Sketchfab, 43-bone quadruped rig, Eating + Idle clips). Read-only. |
| `Gemini_Generated_Image_*.png`, `2259689e-*.webp` | Side-view references of the GiM young cow (the PNG is the primary one) |
| `Young Cow animation preview.mp4`, `videoplayback (1).mp4` | GiM young cow animation previews (the second is the 1080p version) |
| `videoplayback.mp4` | GiM adult female cow animation preview |
| `tools/` | The whole pipeline, as headless Blender Python scripts (see below). `tools/clips/` holds the key-pose clip families. |
| `build/` | **gitignored** intermediates (`stage_a..d.blend`, `textures/`, `logs/`, test outputs); regenerate with the tools |
| `Unity/Calf/` | Deliverables for Unity (FBX, GLB, textures, `Editor/CalfSetup.cs`, `Fur/`, README with import settings). **Git-tracked**, and rewritten by every full build. |
| `docs/` | `WORKLOG.md` (status, open issues, log), `PLAN.md` (scope/phases), `REFERENCES.md` (reference files, video timestamp index, the user's close-up spec), `anim_lying.md` (lying family handoff) |

## Environment (cloud container; nothing is preinstalled)
```bash
pip install bpy                       # Blender 5.0.1 as a Python module (no blender binary; download.blender.org is blocked)
pip install "numpy<2" pillow "opencv-python-headless<4.11" imageio imageio-ffmpeg trimesh   # bpy pins numpy 1.26
```
- Run scripts with `python3 tools/<script>.py` (they `import bpy`). Only Cycles on the CPU works (no GPU, no EEVEE).
- There are 4 shared cores: keep test renders **≤480 px at ≤12 samples**. `render_views.py` defaults to 24 samples, so
  pass `--samples 12`; `render_clip.py` (8) and the clip modules (6) are within budget.
- Blocked hosts: download.blender.org, youtube.com, gim.studio, assetstore.unity.com, docs.unity3d.com (the proxy answers
  403). PyPI and npm are reachable. For Unity API facts, use WebSearch.
- Unity is **not** available here. C#/shaders can't be run, so flag them as needing a Unity check.

## Pipeline
**One command:** `bash tools/build_all.sh` (375 s measured: the 4K textures take 276 s, the validator 54 s). It logs each
step to `build/logs/<step>.log` and ends with the validator summary. It **rewrites the git-tracked `Unity/Calf/`**.
The steps, in order:
```bash
python3 tools/calf_stage_a.py      # cow.glb -> build/stage_a.blend: strip hierarchy, remove horns/udder, join+weld, quads, clean bone names
python3 tools/calf_stage_b.py      # -> build/stage_b.blend: calf reshape (warp mesh + rest bones together), hoof soles on z=0, jaw/ear
                                   #    bones, weight smoothing, eyes, UVs (packed), meters, 30 fps retime, LOD0/1/2 via subdivision
python3 tools/calf_textures.py --in build/stage_b.blend --out build/stage_c.blend --tex-dir build/textures --res 4096
python3 tools/calf_fur_textures.py --in build/stage_b.blend --tex-dir build/textures
python3 tools/calf_animations.py --in build/stage_c.blend --out build/stage_d.blend   # all clips (anim_lib + tools/clips/*)
python3 tools/export_unity.py --in build/stage_d.blend --out-dir Unity/Calf --tex-dir build/textures
python3 tools/validate_export.py --fbx Unity/Calf/Calf.fbx --glb Unity/Calf/Calf.glb --src build/stage_d.blend \
        --json build/logs/validate_report.json --render-dir build/export_check      # build_all adds these two flags
```
**Fast clip QA** (about 5 s each; each builds its clips on `build/stage_b.blend`, prints QA and saves `test.blend` in the
directory you pass). Always pass the output flag: the default is a path from the session that wrote the module.
```bash
python3 tools/clips/idle_graze.py --no-render   --out-dir <scratch>/idle_graze
python3 tools/clips/actions.py    --no-render   --out-dir <scratch>/actions
python3 tools/clips/lying.py      --render none --scratch <scratch>/lying      # its default --render all takes ~10 min
```
Drop the no-render flag to get filmstrips and GIFs (3.5-10 min per family).

Check tools:
- `tools/render_views.py`: contact-sheet stills (`--action NAME --frame N`). After an FBX import Blender names the
  actions `CalfRig|<clip>`, and an action that is not found silently renders the rest pose.
- `tools/render_clip.py`: filmstrip/GIF of an action with a root-tracking camera on a checker ground.
- `tools/silhouette_compare.py`: side silhouette against the reference (both scaled to the same bounding-box height).
- `tools/check_animation.py`: leg/foot consistency, stretch and loops.
- `tools/rebake_leg_ik.py`: re-solve leg IK for imported clips.

### Do not
- **Do not point experiments at `Unity/Calf/` or `build/`.** `build_all.sh` and `export_unity.py --out-dir Unity/Calf`
  overwrite the committed deliverable, and `build/logs/` is the record of the last full build (a manual validator run
  after the build once left `validate.log` at 172 PASS while `build_all.log` said 175). Give re-exports and validator
  runs a scratch `--out-dir` / `--json` / `--render-dir`. If you did overwrite them, re-run the full build before
  committing.
- **Do not run `calf_animations.py` twice at once, and do not rely on `--out` to keep it out of `build/`.** It always
  writes `build/stage_b_rebaked.blend` (OI-27).
- **Do not use `build_all.sh --skip-textures` after a stage-B change.** It re-runs stages A/B but keeps the old
  `build/stage_c.blend`, which is a full copy of the *previous* stage B plus materials. The animations and the FBX are
  built from it, so the stage-B edit is silently lost (OI-28). `--skip-textures` is only safe when stage A/B did not
  change.
- **Do not commit a build made with `--tex-res 2048`.** The export copies whatever is in `build/textures` into
  `Unity/Calf/Textures`, and the validator does not check resolution (OI-29). Before committing, check that
  `python3 -c "from PIL import Image; print(Image.open('Unity/Calf/Textures/T_Calf_BaseColor.png').size)"` prints `(4096, 4096)`.
- Do not modify the reference media or `cow.glb`.

## Verification gate
A state is **verified-good** (and may become a checkpoint) when:
1. `bash tools/build_all.sh` finishes (every step prints `ok`).
2. The validator reports **0 FAIL** (`SUMMARY:` line in `build/logs/build_all.log`; it exits 1 on any FAIL). Checkpoint 01:
   175 PASS / 0 FAIL / 1 WARN. The only accepted WARN is the 4-influence skin deviation (23.7 mm at Gallop f14).
3. The build's clip QA (`QA <clip>:` lines in `build/logs/animations.log`) and each family's fast QA (commands above)
   are within the limits below.
4. The working tree is clean after the commit (the build rewrites `Unity/Calf/`, so commit it).

Nothing computes a pass/fail verdict for the clip QA yet (OI-30): read the lines against this table.

| QA line | Limit | Known values that are fine (checkpoint 01) |
|---|---|---|
| `QA … IK gap` | ≤ 0.1 mm | Idle 2.27 mm: the source `cow.glb` clip cannot reach there either |
| `QA … planted slide` | ≤ 0.1 mm | The build log measures only Walk_RM/Trot_RM/Gallop_RM; the other clips print 0.00 **without measuring** (OI-30). The family QAs measure their own clips. |
| `QA … fetlock loop seam` | 0.00 mm on loops | Meaningless on one-shots: Graze_Start/End 60 mm (the left fore steps 6 cm), LieDown/GetUp 182 mm, Death 669 mm (ends on its side, 0.79 m away) |
| `QA … pastern drop below rest` | information only | Hoof flex/roll: gaits -1.5 to -4.2 mm, lying -5.8 mm, Death -6.8 mm |
| `BOUNDARY`, `SEAM`, `HOLD`, `RESIDUAL` (families) | ≤ 0.001 mm / 0.001° (residual ≤ 1e-7) | Leap end vs `Pose()` 0.0004 mm root-relative (float round-off); all others 0.0000 |
| `JOINT` (lying) | must end with `JOINT limits: all OK` (loaded fore fetlock ≥ -65°, standing carpus ≤ 25°, stifle ≤ 140°, hock ≥ -150°) | GetUp LF fetlock -61.3° is the tightest |
| `JOINTS` (idle_graze, actions) | carpus and hock bend > 0 (anatomical) on every frame | rest carpus 10.4°, rest hock 52.4° |
| `FETLOCK` (actions) | loaded dorsal angle ≤ ~60° (rest front 28°, hind 14°) | Death RF 56° |
| `MESH` / `GROUND` (Calf_LOD2) | standing clips: non-hoof min z = rest (2.60 cm); lying and impact frames ≥ -2 cm | Death -1.04 cm (f33 impact), Lying_Idle -0.9 cm |
| `CONTACT` (actions) | a hoof may roll on an edge, not slide; totals ≲ 10 mm per hoof | Death 7-10 mm |
| `OVERLAP` (actions) | 0 LOD2 limb/tail polygon pairs; bone-capsule overlap ≤ 0 mm | - |
| `REACH` (actions) | ≤ 0 mm (> 0 = the foot target was clamped) | -0.4 mm |

## Conventions (every tool relies on these)
- **Units and axes:** meters, Z up, and the calf **faces -Y** (Unity +Z after FBX export). Ground at z=0. Withers ≈1.0 m.
- **Timing:** 30 fps. Actions use integer frames, with `use_frame_range` set and `use_cyclic` set for loops.
- **Objects:** `CalfRig` (armature), with children `Calf_LOD0` (~47k tris), `Calf_LOD1` (~12k), `Calf_LOD2` (~2.7k). All LODs share one UV layout (`UVMap`).
- **Material slots:** `[0] M_Calf_Body`, `[1] M_Calf_Eye` (the exporter moves the body slot last for the fur). The face attribute `orig_part` holds 0 coat, 1 old light patches, 2 hooves, 3 nose pad, 4 eyeball.
- **Bones** (46 in stage B/C/D: the 43 source bones + `Jaw`, `Ear.L/R`; `.L` is +X):
  - Main chain: `Root` (ground, at the origin; the root-motion node), `Body` (the body root: its head is near the ground
    at z 0.205 m, and anim_lib pitches/rolls the body about a virtual COG at (0, -0.05, 0.68)), then the spine `Back`,
    `Torso`, `Torso2`, `Torso3` (running from rump to chest), then `Neck1-3`, `Head`, `Jaw`, `Ear.L/R`, `Tail1-7` (from `Back`).
  - Front legs: `FrontShoulder.X` (a child of `Torso2`), `FrontUpperLeg.X`, `FrontLowerLeg.X`.
  - Hind legs: `BackShoulder.X`, `BackLeg.X` (femur), `BackUpperLeg.X`, `BackLowerLeg.X`.
  - Feet: `IKFrontLeg.X` with its child `FF.X` (front), `IKBackLeg.X` with its child `FFB.X` (hind). They carry the hoof weights.
    - **Authoring rig (stage B/C, anim_lib, every clip module):** the feet are parented to `Root`.
    - **Export rig (stage D, FBX, GLB):** `calf_animations.py` re-parents `IKFrontLeg.X` under `FrontLowerLeg.X` and
      `IKBackLeg.X` under `BackLowerLeg.X` and re-bakes every clip (world change 0.000 mm), so engine blending can't detach the hooves.
  - `PoleTarget(Back).X` are unweighted IK pole helpers parented to `Body`. The exporter drops them: the FBX/GLB have 42 bones.
- **Leg IK:** the lower-leg bones end exactly at the foot bone head (the fetlock); stage B fixes the importer-invented tails.
  There is no persistent IK rig in the .blend: anim_lib adds the IK constraints per clip (lower leg → foot bone, pole =
  PoleTarget bones, chain 2, pole angle auto-solved), **bakes them to FK** and removes them. Exported clips have no constraints.
  anim_lib clamps a foot target at 0.9985 × chain (the straight fore legs rest at 0.996), so `Pose()` equals the rest pose.
- **`anim_lib.Pose` signs** (checked by FK probes): `body_rot` = (pitch + nose down, roll + right side down, yaw + left);
  spine roll + = **left** side down; head roll + = left ear down; `ears` = (x + tip forward, y + tip down, z twist);
  `tail` = (side + = tip to the calf's **right** (-X), lift + = tip back/up); `flex` + = toe back.

## References
The look target, reference files, a timestamp index of `videoplayback (1).mp4` and a frame-grab command are in
`docs/REFERENCES.md`. The user's close-up spec (not on disk): orange-brown head; a fluffy **white** forehead tuft between
the ears; big dark amber-brown eyes with a pale rim; a pale pink muzzle with darker nostrils; ears orange outside and pale
pink inside with a fur fringe; the lying calf shows a white belly and legs with one front leg stretched forward.

## Extending
**Add a clip family**
1. Create `tools/clips/<family>.py` with `build(calf) -> list[str]`. `calf_animations.py` imports every `tools/clips/*.py`
   whose name does not start with `_`, in sorted filename order, after the imported clips and the gaits, and calls
   `build` with the shared `anim_lib.Calf`. Copy the structure of `idle_graze.py`: boundary poses returned verbatim
   (`stand_pose()` = `Pose()`), `calf.make_clip(name, N, pose_fn, loop=...)` (it sets `use_frame_range` and
   `use_cyclic = loop`; the manifest's `cyclic` flag and Unity's Loop Time come from that), root motion by animating
   `Pose.root_pos` / `root_yaw` (the manifest's `root_motion` is set when the Root moves).
2. Give it a standalone `__main__`: build on `build/stage_b.blend`, print QA (at least `calf.qa` with a `planted_fn`, a
   LOD2 ground check and boundary/seam diffs), take `--out-dir` and a no-render flag, and default to a path under
   `build/` or a temp dir, never a session path. Add its fast QA command to "Pipeline" and its limits to the gate table.
3. Unity: add the clip to `ClipSpec` in `Unity/Calf/Editor/CalfSetup.cs` (loop and root-motion kind; the Animator states
   are hard-coded in `CreateController`, and a trigger one-shot from Idle/Locomotion is one entry in `OneShots`). Update
   the clip, loop and root-motion tables and the Animator section in `Unity/Calf/README.md`.
4. Run the full build and the gate, then update the WORKLOG status and open-issues tables.

**Change the coat** (`tools/calf_textures.py`)
- Colours: the `C_*` constants in `_coat_chunk()` (`C_OR`, `C_OR_RED`, `C_OR_LT` orange; `C_WH`, `C_WH_GREY`, `C_DIRT`
  white; more part colours next to them), written as sRGB 0-255 through `srgb2lin`. The eye colours are the `C_IRIS*`,
  `C_PUP`, `C_SCL` and `C_RIM` constants in `eye_texture()`.
- Layout: the patch shapes in `_coat_chunk()` are distances and ellipses relative to the landmarks from
  `compute_landmarks()` (rest bones and mesh profile), so they follow geometry edits.
- Preview loop (about 20 s, then 12 s with the cache, at 1024; writes only into `<scratch>`):
  ```bash
  python3 tools/calf_textures.py --in build/stage_b.blend --out <scratch>/stage_c_test.blend --tex-dir <scratch>/tex \
          --res 1024 --cache <scratch>/bake1024.npz --preview <scratch>/prev.png --textures-only
  ```
  `--preview` writes an orthographic numpy preview, `--cache` keeps the Cycles data bakes (delete it after any stage-B change),
  and `--textures-only` skips the normal-map bake and the blend save.
- Then run the full build: stage C carries the materials, so textures, animations, export and validation must all
  re-run. If the forehead tuft or the tail switch moved, `calf_fur_textures.py` must re-run too (the build does that).

**Re-export only** (no rebuild, into a scratch folder; about 35 s):
```bash
python3 tools/export_unity.py --in build/stage_d.blend --out-dir <scratch>/Calf --tex-dir build/textures
python3 tools/validate_export.py --fbx <scratch>/Calf/Calf.fbx --glb <scratch>/Calf/Calf.glb --src build/stage_d.blend \
        --json <scratch>/validate_report.json          # 172 PASS / 1 WARN at checkpoint 01; --render-dir adds 3 checks
```

## Blender 5 API gotchas
- Actions are layered and slotted: fcurves live in `action.layers[].strips[].channelbags[].fcurves`, not `action.fcurves`. After `animation_data.action = act`, also set `animation_data.action_slot = act.slots[0]` when the action has slots.
- The glTF importer invents leaf-bone tails and imports 30 fps samples onto a 24 fps timeline (0.8-frame spacing); stage B fixes both.
- A mesh parented to the armature inherits the armature's scale. When scaling both, unparent first (stage B does this).
- `render.render()` works headless with Cycles; Workbench/EEVEE need a GPU context and fail.
- Blender's FBX importer names imported actions `<armature>|<take>` (`CalfRig|Walk`).

## Working rules
- Never modify the reference media or `cow.glb`.
- Keep the tools deterministic and parameterised (`--in`/`--out`), because each stage is re-run when an earlier stage changes.
- After each milestone, update the "Current status" and "Open issues" tables in `docs/WORKLOG.md`, append a log entry
  (what changed, why, verification numbers, next steps) and commit.
- Development branch: `claude/peaceful-lamport-fk2lw7`.
- **Safe checkpoints (user rule):** whenever the repo reaches a verified-good state (see "Verification gate"), make a
  commit whose message starts with `CHECKPOINT NN: <short name>` and **push it**. Add a row to the "Checkpoints" table in
  `docs/WORKLOG.md`. (This environment's git proxy only allows pushing the working branch, so pushed tags are rejected
  with 403; checkpoints are therefore marked by commit message.) Find them with `git log --oneline --grep CHECKPOINT`;
  roll back with `git checkout <hash>`.
