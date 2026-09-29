# Game-asset: Young Cow (Calf), Adult Cow and Rottweiler for Unity

**Read this first, then `docs/WORKLOG.md` (current status, open issues, chronological log) and `docs/PLAN.md` (scope and phases).**
`docs/REFERENCES.md` describes the look target, and `docs/anim_lying.md` is the handoff for the lying clips.

## Goal
A game-ready **young cow (calf)** for a Unity game. The quality and content target is GiM Studio's *Animalia - Cow (young)*.
The user decided to **build it in-house**; do not suggest buying the GiM asset.
Scope: model + 4K PBR textures + LODs + rig + full animation set (walk/trot/gallop/turns, idles, graze, eat,
lie down / lying idle / get up, death, leap) + Unity import/setup.

**Adult cow (second asset, `Unity/Cow`):** the user asked for the adult cow as well ("cow like cub"). Look target: the
GiM adult female in `videoplayback.mp4` (a Simmental: red-pied, white head, short horns, udder). It is built by the same
tools with `ASSET=cow` (`bash tools/build_all.sh --asset cow`); see "Adult cow" below. The calf stays the default: every
tool behaves exactly as before without `ASSET`.

**Rottweiler (male) (third asset, `Unity/Rottweiler`):** the user asked for the male Rottweiler next ("now Rottweiler
(male)"), with references in `Rottweiler (male)/` (GiM *Animalia - Rottweiler* stills and `videoplayback (4).mp4`) and a
sample asset in `Rottweiler (male)/Dog/`. The sample (870 tris, 38-bone Rigify metarig, 9 clips) is far below the target,
so the dog has its **own pipeline in `tools/dog/`** (procedural SDF anatomy -> mesh, rig, textures, clips) and shares only
the exporter and validator: `bash tools/build_all.sh --asset dog`. See "Rottweiler" below.

## Repo layout
| Path | What |
|---|---|
| `cow.glb` | Source model (low-poly adult cow from Sketchfab, 43-bone quadruped rig, Eating + Idle clips). Read-only. |
| `Gemini_Generated_Image_*.png`, `2259689e-*.webp` | Side-view references of the GiM young cow (the PNG is the primary one) |
| `Young Cow animation preview.mp4`, `videoplayback (1).mp4` | GiM young cow animation previews (the second is the 1080p version) |
| `videoplayback.mp4` | GiM adult female cow animation preview |
| `tools/` | The whole pipeline, as headless Blender Python scripts (see below). `tools/clips/` holds the key-pose clip families. |
| `build/` | **gitignored** intermediates (`stage_a..d.blend`, `textures/`, `logs/`, test outputs); regenerate with the tools |
| `tools/asset_profile.py` | Which animal a run builds (`ASSET=calf` default, `ASSET=cow`): build dir, output dir, texture prefix, final scale. |
| `build/cow/`, `Unity/Cow/` | The adult cow's intermediates (gitignored) and deliverables (git-tracked: FBX, GLB, `Textures/`, `Editor/CowSetup.cs`, README). |
| `Rottweiler (male)/` | Rottweiler references (GiM stills `*.webp`, preview `videoplayback (4).mp4`) and the sample `Dog/` (DogGlb.glb, DogFBX.fbx, Dogs1.blend, BlackDog.png). Read-only. |
| `tools/dog/` | The Rottweiler pipeline (stages A-D, `clips/` families, `dog_views.py`); `build/dog/` its intermediates (gitignored), `Unity/Rottweiler/` its deliverables (git-tracked). |
| `Unity/Calf/` | Deliverables for Unity (FBX, GLB, textures, `Editor/CalfSetup.cs`, `Fur/`, README with import settings). **Git-tracked**, and rewritten by every full build. |
| `docs/` | `WORKLOG.md` (status, open issues, log), `PLAN.md` (scope/phases), `REFERENCES.md` (reference files, video timestamp index, the user's close-up spec), `anim_lying.md` (lying family handoff) |

## Environment (cloud container; nothing is preinstalled)
```bash
pip install bpy                       # Blender 5.0.1 as a Python module (no blender binary; download.blender.org is blocked)
pip install "numpy<2" pillow "opencv-python-headless<4.11" imageio imageio-ffmpeg trimesh   # bpy pins numpy 1.26
pip install scikit-image pymeshlab xatlas   # the Rottweiler's mesh stage (marching cubes, decimation, UV atlas)
apt-get install -y libopengl0               # pymeshlab's meshing filters need libOpenGL.so.0 (else "filter not found")
```
- Run scripts with `python3 tools/<script>.py` (they `import bpy`). Only Cycles on the CPU works (no GPU, no EEVEE).
- There are 4 shared cores: keep test renders **≤480 px at ≤12 samples**. `render_views.py` defaults to 24 samples, so
  pass `--samples 12`; `render_clip.py` (8) and the clip modules (6) are within budget.
- Blocked hosts: download.blender.org, youtube.com, gim.studio, assetstore.unity.com, docs.unity3d.com (the proxy answers
  403). PyPI and npm are reachable. For Unity API facts, use WebSearch.
- Unity is **not** available here. C#/shaders can't be run, so flag them as needing a Unity check.

## Pipeline
**One command:** `bash tools/build_all.sh` (422 s measured on the final-review build: the 4K textures take 276 s, the
validator 89 s). It logs each step to `build/logs/<step>.log`, ends with the validator summary and keeps a timestamped
copy of the validator log and report (`build/logs/validate-<stamp>.log`). It writes no log of its own output: redirect it
(the final-review run is `build/logs/build_all_run2.out`; `build_all.log` is checkpoint 01's). It **rewrites the
git-tracked `Unity/Calf/`**. The steps, in order:
```bash
python3 tools/calf_stage_a.py      # cow.glb -> build/stage_a.blend: strip hierarchy, remove horns/udder, join+weld, quads, clean bone names
python3 tools/calf_stage_b.py      # -> build/stage_b.blend: calf reshape (warp mesh + rest bones together), hoof soles on z=0, jaw/ear
                                   #    bones, ears/eyes/tail switch/forehead tuft, weight smoothing + tail/brisket repaint, UVs (packed),
                                   #    meters, 30 fps retime, LOD0/1/2 via subdivision, every LOD limited to 4 influences
python3 tools/calf_textures.py --in build/stage_b.blend --out build/stage_c.blend --tex-dir build/textures --res 4096
python3 tools/calf_fur_textures.py --in build/stage_b.blend --tex-dir build/textures
python3 tools/calf_animations.py --in build/stage_c.blend --out build/stage_d.blend   # all 25 clips (anim_lib + tools/clips/*);
                                   #    QA gate: exits 1 on a violation; writes its IK re-bake next to --out (build/stage_d_rebaked.blend)
python3 tools/export_unity.py --in build/stage_d.blend --out-dir Unity/Calf --tex-dir build/textures   # FBX + 4K Textures/, GLB with 2K textures
python3 tools/validate_export.py --fbx Unity/Calf/Calf.fbx --glb Unity/Calf/Calf.glb --src build/stage_d.blend \
        --json build/logs/validate_report.json --render-dir build/export_check      # build_all adds these two flags
```
**Fast clip QA** (5-8 s each; each builds its clips on `build/stage_b.blend`, prints QA and saves `test.blend` in the
directory you pass). Always pass the output flag: the default is a path from the session that wrote the module (OI-31).
`locomotion.py` and `imported_fix.py` save nothing unless you pass `--out`.
```bash
python3 tools/clips/idle_graze.py --no-render   --out-dir <scratch>/idle_graze
python3 tools/clips/actions.py    --no-render   --out-dir <scratch>/actions
python3 tools/clips/lying.py      --render none --scratch <scratch>/lying      # its default --render all takes ~10 min
python3 tools/clips/locomotion.py                           # Stand, Walk_Slow(_RM), turns + TURN/BLEND QA; saves only with --out <existing dir>/x.blend
python3 tools/clips/imported_fix.py --in build/stage_d_rebaked.blend   # Idle/Eating repair QA; the default --in (build/stage_b_rebaked.blend) is stale
```
Drop the no-render flag to get filmstrips and GIFs (3.5-10 min per family). `imported_fix.py` needs the IK re-bake of the
current stage B: `build/stage_d_rebaked.blend` from the last build, or `python3 tools/rebake_leg_ik.py --in
build/stage_b.blend --out <scratch>/rebaked.blend --actions Eating,Idle`.

Check tools:
- `tools/render_views.py`: contact-sheet stills (`--action NAME --frame N`). After an FBX import Blender names the
  actions `CalfRig|<clip>`, and an action that is not found silently renders the rest pose.
- `tools/render_clip.py`: filmstrip/GIF of an action with a root-tracking camera on a checker ground.
- `tools/silhouette_compare.py`: side silhouette against the reference (both scaled to the same bounding-box height).
- `tools/check_animation.py`: leg/foot consistency, stretch and loops.
- `tools/rebake_leg_ik.py`: re-solve leg IK for imported clips.

### Do not
- **Do not point experiments at `Unity/Calf/`, `Unity/Cow/`, `Unity/Rottweiler/` or `build/` (incl. `build/cow/`,
  `build/dog/`).** `build_all.sh` and `export_unity.py --out-dir Unity/Calf`
  overwrite the committed deliverable, and `build/logs/` is the record of the last full build (a manual validator run
  after the build once left `validate.log` at 172 PASS while `build_all.log` said 175). Give re-exports and validator
  runs a scratch `--out-dir` / `--json` / `--render-dir`. If you did overwrite them, re-run the full build before
  committing.
- **Do not run two `calf_animations.py` with the same `--out` at once.** Each writes its IK re-bake to
  `<out>_rebaked.blend` (a scratch `--out` keeps it out of `build/`; OI-27 is fixed). `build/stage_b_rebaked.blend` is a
  stale leftover from before that fix.
- **Use `build_all.sh --skip-textures` only when stage B's geometry and UVs did not change** (e.g. a weight edit). It
  keeps the old textures and re-links their materials onto the new stage B (`tools/relink_materials.py`); it refuses
  (exit 2) when the LOD0 UVs changed (OI-28 is fixed). After a shape change, re-bake the textures: the coat follows
  mesh landmarks.
- **Do not commit a build made with `--tex-res 2048`.** The export copies whatever is in `build/textures` into
  `Unity/Calf/Textures`, and the validator does not check their resolution (OI-29; its texture-memory check covers only
  the GLB, which is reduced to 2048 on purpose). Before committing, check that
  `python3 -c "from PIL import Image; print(Image.open('Unity/Calf/Textures/T_Calf_BaseColor.png').size)"` prints `(4096, 4096)`.
- Do not modify the reference media or `cow.glb`.

### Adult cow (`ASSET=cow`)
`bash tools/build_all.sh --asset cow` (about 7 min; logs in `build/cow/logs/`, run output `build/cow/logs/build_all_run.out`)
runs the same steps with `ASSET=cow` on `build/cow/` and writes `Unity/Cow/`. What differs (all switched by
`tools/asset_profile.py`):
- **Stage A** keeps the horns (base loops capped, rigid on `Head`, `orig_part` 5). **Stage B** uses `P_COW` (adult
  proportions: no torso compression, head/muzzle change, flank tuck or forehead tuft; a deeper barrel, finer legs than the
  low-poly source, dewlap, leaf ears, tail switch), shortens the horns (x0.82) and adds a modelled udder with four teats
  (closed islands, `orig_part` 6, rigid on the rear trunk bones). LOD0/1/2 58,080 / 14,520 / 3,376 tris.
- **Textures:** `_cow_layout()` in `calf_textures.py` (Simmental coat; tune `thr`, `back`, `rump`, `flank` there), dark
  slate hooves, grey-pink muzzle, horns cream with dark tips, pink udder; files `T_Cow_*`. No fur textures (no shell fur).
- **Authoring scale:** stages A-D, every clip family and every QA run at the calf's authoring height (withers ~1.0 m), so
  the tuned distances keep their meaning. The cow's trunk is longer: fore fetlocks 9 cm further forward, hind 11 cm
  further back. Clip code that places hooves at absolute positions shifts them by that (`lying.adapt_to_rig`).
- **Gaits:** `anim_gait.py` stretches every cycle x sqrt(1.42) = 1.19 (Walk 29 f, Trot 19, Gallop 17, Walk_Slow 43).
  Cow overrides in the families: `idle_graze.COW_GRAZE_NECK`, `actions` `DEAD` / `D_HIT` / `DL_HIT` (the head lands on
  its horn), `lying.adapt_to_rig`. The QA gate allows Idle 4 mm of IK gap on the cow (source over-reach, 3.84 mm).
- **Stage E** (`tools/scale_asset.py`): uniform scale x1.42 of rig, meshes and every location key (checked on every frame:
  max 0.014 mm float round-off) and renames `CalfRig`/`Calf_LOD*`/`M_Calf_*` to `CowRig`/`Cow_LOD*`/`M_Cow_*`. The export
  and validator read `build/cow/stage_e.blend`.
- **Unity:** `Unity/Cow/Editor/CowSetup.cs` = `CalfSetup.cs` with the cow's names and speeds (0.535 / 1.087 / 2.803 /
  5.137 m/s), no fur. Keep the two in sync when one changes.
- **Fast QA on the cow:** prefix the family commands with `ASSET=cow` and pass `--in build/cow/stage_b.blend` (their
  default input is the calf's stage B). Cow values (authoring scale; x1.42 on the final cow): Graze_Loop nose pad
  2.37-5.30 cm; Death head -0.57 cm, trunk -3.34 cm at the f33 impact; Death_Lying head +0.42 cm; lying legs >= -0.7 cm;
  the udder goes up to 14.2 cm below the ground while lying (hidden under the body); `JOINT limits: all OK`; Leap REACH
  5.0 mm, Death_Lying REACH 6.6 mm (the calf's are <= 0).
- **Gate for the cow:** as below, with `build/cow/logs/`; final-review build: see `docs/WORKLOG.md` (validator 266
  checks: the calf's 267 minus the shell-fur texture check).

### Rottweiler (`ASSET=dog`, `tools/dog/`)
`bash tools/build_all.sh --asset dog` (about 8 min; logs in `build/dog/logs/`, run output `build/dog/logs/build_all_run.out`)
writes `Unity/Rottweiler/`. Its own stages, then the shared `export_unity.py` / `validate_export.py`:
```bash
python3 tools/dog/dog_stage_a.py      # anatomy.py SDF (2 mm grid) -> marching cubes -> pymeshlab decimation; parts (draped ears,
                                      # eyeballs, claws, teeth, tongue); xatlas UV atlas; LOD1/2 decimated WITH UVs; skin weights
                                      # from the primitives' bones -> build/dog/stage_a.npz   (~90 s)
python3 tools/dog/dog_stage_b.py      # Blender: RottweilerRig (43 bones, unconnected) + Rottweiler_LOD0/1/2 -> stage_b.blend
python3 tools/dog/dog_textures.py --res 4096   # numpy atlas rasteriser + 3D-painted coat/markings, fur normal, SDF AO -> stage_c
python3 tools/dog/dog_animations.py   # every tools/dog/clips/*.py family, QA GATE (exit 1) -> stage_d.blend
```
- **Anatomy** (`anatomy.py`): joints `J` (meters, faces -Y, withers 0.66 m, authored at final size: no scale stage) and the
  SDF primitives, each tagged with its bone(s); the skin weights come from those tags (soft-min of the primitive distances,
  chains split along their bones), the lip line is split hard between Head and Jaw. Change the shape there, then rebuild.
  `sdf_preview.py` (5 s) + `dog_views.py` (clay contact sheet: side/front/back/top/3-4/head/paw) for shape work.
- **Face attribute `part`**: 0 coat, 1 mouth interior / eye socket (cut surfaces), 2 claw, 3 nose leather, 4 eyeball,
  5 paw pad, 6 tooth, 7 tongue, 8 ear. Materials `[0] M_Rottweiler_Body`, `[1] M_Rottweiler_Eye`.
- **Rig**: `Root` > `Hips` > `Spine1-3` > `Neck1-2` > `Head` > `Nose`, `Jaw` > `Tongue1-3`, `Ear1/2.X`, `Eye.X`;
  `Hips` > `Tail1-6`, `Thigh.X` > `Shin.X` > `HindFoot.X` > `HindToe.X`; `Spine3` > `Scapula.X` > `UpperArm.X` >
  `Forearm.X` > `FrontFoot.X` > `FrontToe.X`. Rolls: local X ~ -X world (flexion = rotation about local X).
  **Bones are never connected**: `export_unity.py`'s rig axis bake transforms edit bones one by one and a connected child
  drags its parent's tail twice (the first dog export was 1.37 m off).
- **Animation** (`dog_anim.py`): `Pose` -> analytic IK straight to FK keys (no constraints). Legs: `LegPose(mcp, pastern,
  toe, scap, pole, local)` in the root frame; the scapula swings with the leg (gain 0.75, clamped +-35 deg) and glides up to
  4 cm (no collarbone); 2-bone chain in the plane of the rest bend; the pastern/metatarsus is a hinge in that plane;
  `reach_pass` lowers the body where a paw is out of reach (reported as "body drop"); leg planes are kept continuous frame
  to frame. `Pose()` = rest (self-test 1e-6). Signs: `rot(pitch, yaw, roll)` pitch + = tip down (forward bone) / back-up
  (hanging bone), yaw + = to the dog's left; `pastern` + = the lower end swings back (carpus flexion; for the HOCK flexion is
  **negative**: the paw swings forward); `toe` + = tip down; `jaw` + = open; `local` 0..1 = paw angles in the ground or
  the body frame (a body rolled onto its side). `_common.timeline` blends key poses and lifts stepping paws.
- **Fast QA** (5-10 s): `ASSET=dog python3 tools/dog/dog_animations.py --in build/dog/stage_c.blend --out <scratch>/d.blend
  [--only locomotion,idles,sit_lie,actions]`; each family also runs standalone: `python3 tools/dog/clips/<family>.py --in
  build/dog/stage_b.blend --out-dir <scratch>`. Filmstrips: `python3 tools/render_clip.py <blend> <clip> <out> --rig
  RottweilerRig`.
- **Dog QA gate** (`dog_animations.py`): IK gap <= 0.1 mm, planted slide <= 0.1 mm (`_RM` gaits, idles, Jump stances),
  loop seam <= 0.01 mm, elbow/stifle/hock never bend backward (> 0.5 deg), carpus dorsiflexion <= 65 deg, leg-bone twist
  <= 12 deg per frame (the validator FAILs 15), LOD2 body and paws >= -2 cm.
- The validator reads the dog's key bones / limb regex / clip boundaries / size window from `AP.IS_DOG`
  (`validate_export.py`, after `STANDING_ENDS`).
- **Gate for the dog:** as below, with `build/dog/logs/` and the dog QA gate. First build (checkpoint 04): `QA GATE: pass
  (25 clips)`, validator **264 PASS / 0 FAIL / 0 WARN**, `T_Rottweiler_BaseColor` 4096. Stage B stops on a degenerate
  MikkTSpace tangent (a UV fold in a decimated LOD; stage A decimates LOD2 from LOD1 and repairs folds). Known values:
  body drop Walk 1.3 mm, Trot 15 mm, Gallop 67 mm (OI-51); leg twist max 11.4 deg/f (Death).

## Verification gate
A state is **verified-good** (and may become a checkpoint) when:
1. `bash tools/build_all.sh` finishes (every step prints `ok`). The animations step fails (exit 1) on a QA-gate violation.
2. The validator reports **0 FAIL** (the `SUMMARY:` line at the end of `build/logs/validate.log`, also printed by
   `build_all.sh`; it exits 1 on any FAIL). Final-review build (checkpoint 02): **267 PASS / 0 FAIL / 0 WARN**. No WARN
   is expected any more: read any WARN line before checkpointing. (Checkpoint 01's 175 / 0 / 1 came from an older,
   smaller validator.)
3. `build/logs/animations.log` shows `QA GATE: pass (25 clips)`, and the other QA lines of the build and each family's
   fast QA (commands above) are within the limits below.
4. The working tree is clean after the commit (the build rewrites `Unity/Calf/`, so commit it).

The `QA GATE` in `calf_animations.py` checks, for every clip: IK gap, planted slide on the `_RM` gaits, loop seams on the
cyclic clips, and knees/hocks bending backward (by more than 0.5°, the noise on straight legs). Nothing else fails the
build: read the other lines against this table.

| QA line | Limit | Known values that are fine (final-review build) |
|---|---|---|
| `QA … IK gap` | ≤ 0.1 mm (gate; Idle ≤ 3 mm) | Idle 2.27 mm: the source `cow.glb` clip cannot reach there either; all others ≤ 0.05 mm |
| `QA … planted slide` | ≤ 0.1 mm (gate, `_RM` gaits) | Measured only on Walk_Slow_RM/Walk_RM/Trot_RM/Gallop_RM (flat-hoof stance: the toe roll-off is not slide). The other clips print 0.00 **without measuring** (OI-30); the family QAs measure their own, and `imported_fix` measures Idle/Eating (`QA Idle (planted = fetlock <2 mm up)`). |
| `QA … fetlock loop seam` | ≤ 0.01 mm on loops (gate) | Meaningless on one-shots: Graze_Start/End 60 mm (the left fore steps 6 cm), LieDown/GetUp 182 mm, Death 669 mm (ends on its side, 0.79 m away), Death_Lying 436 mm |
| `QA … pastern drop below rest` | information only | Standing clips and gaits -0.0 mm; lying -5.8 mm; Death -6.8 mm; Death_Lying -13.4 mm |
| `EATING fix`, `QA Eating nose pad` (imported_fix) | nose pad min ≥ 1.5 cm (prints OK/BELOW) | LOD2 3.50 cm (the solve target), LOD0 3.83 cm (f92); f0 vs f180 0.0000 |
| `MESH … nose pad` (idle_graze) | no verdict; keep ≥ ~1.5 cm, as Eating | Graze_Loop 2.62-4.29 cm (LOD2); Graze_Start min 2.83, Graze_End min 3.10 |
| `TURN` (locomotion, also in the build log) | ends vs `Pose()` ≤ 0.001 mm; planted hoof within ~12° of the body yaw; LOD2 body and hooves never below rest | f56 0.0003 mm; root yaw ±90.000°; carpus 6.5-65.9°, hock 45.3-66.1° |
| `BLEND` (locomotion) | information only: a simulated Unity 1D blend of neighbouring children (plain Trot/Gallop pair) | Trot/Gallop w=0.5: skate 9.8 cm, fetlock -41 mm, same-side hoof tips ≥ 7.7 cm (1.3 cm at w=0.75). Stand/Walk_Slow w=0.25: skate 27.9 cm (blending with a static pose; 0-0.2 m/s only). `CalfSetup.cs` confines the Trot/Gallop crossfade to 3.2-3.6 m/s with time-scaled children, which this QA does not simulate. |
| `BOUNDARY`, `SEAM`, `HOLD`, `RESIDUAL` (families) | ≤ 0.001 mm / 0.001° (residual ≤ 1e-7) | Leap end vs `Pose()` 0.0004 mm and Death / Death_Lying start 0.0001 mm root-relative (float round-off); residual ≤ 6e-8; all others 0.0000 |
| `JOINT` (lying) | must end with `JOINT limits: all OK` (loaded fore fetlock ≥ -65°, standing carpus ≤ 25°, stifle ≤ 140°, hock ≥ -150°) | GetUp LF fetlock -61.3° is the tightest |
| `JOINTS` (idle_graze, actions) | carpus and hock bend > 0 (anatomical) on every frame | rest carpus 10.4°, rest hock 52.4°; Death_Lying carpus 20.4-108.9°, hock 80.2-148.1° |
| `FETLOCK` (actions) | loaded dorsal angle ≤ ~60° (rest front 28°, hind 14°) | Death RF 56° |
| `MESH` / `GROUND` (Calf_LOD2) | standing clips: non-hoof min z = rest (2.60 cm); lying and impact frames ≥ -2 cm | Death -1.04 cm (f33 impact), Death_Lying -1.19 cm (f25), Lying_Idle -0.9 cm. The dead head rests on the ground: head min Death -0.11 cm, Death_Lying -0.43 cm |
| `CONTACT` (actions) | a hoof may roll on an edge, not slide; totals ≲ 10 mm per hoof | Death 7-10 mm. Death_Lying LF 108 / RF 80 / LH 28 / RH 37 mm: the limp legs slide during the roll (OI-40, open) |
| `OVERLAP` (actions) | 0 LOD2 limb/tail polygon pairs; bone-capsule overlap ≤ 0 mm | Death -21.2 mm, Death_Lying -34.1 mm (clear). No such check runs on the gaits (Gallop legs cross: OI-36) |
| `REACH` (actions) | ≤ 0 mm (> 0 = the foot target was clamped) | -0.4 mm; Death_Lying -5.7 mm |

## Conventions (every tool relies on these)
- **Units and axes:** meters, Z up, and the calf **faces -Y** (Unity +Z after FBX export). Ground at z=0. Withers ≈1.0 m.
- **Timing:** 30 fps. Actions use integer frames, with `use_frame_range` set and `use_cyclic` set for loops.
- **Objects:** `CalfRig` (armature), with children `Calf_LOD0` (~47k tris), `Calf_LOD1` (~12k), `Calf_LOD2` (~2.7k). All LODs share one UV layout (`UVMap`), and every vertex has at most 4 bone influences (stage B), so Blender previews deform exactly as Unity.
- **Material slots:** `[0] M_Calf_Body`, `[1] M_Calf_Eye` (the exporter moves the body slot last for the fur). The face attribute `orig_part` holds 0 coat, 1 old light patches, 2 hooves, 3 nose pad, 4 eyeball (cow only: 5 horn, 6 udder and teats).
- **Names across animals:** both animals keep the calf's Blender names (`CalfRig`, `Calf_LOD*`, `M_Calf_*`) through stages A-D; only the cow's stage E renames them to `Cow*`.
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
  A pole guard (`Calf.POLE_MARGIN`, 15°) rotates a pole forward when the foot target comes close to it (it stopped the
  Gallop right-fore knee flip); the validator's per-frame twist check FAILs any leg or hoof twist over 15° per frame.
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
   are hard-coded in `CreateController`, a trigger one-shot from Idle/Locomotion is one entry in `OneShots`, and a Speed
   blend-tree child is one row of `Locomotion`). Update the clip, loop and root-motion tables and the Animator section in
   `Unity/Calf/README.md`.
4. Run the full build and the gate (the build's `QA GATE` covers the new clips automatically), then update the WORKLOG
   status and open-issues tables.

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
        --json <scratch>/validate_report.json          # expect 0 FAIL / 0 WARN (~50 s); --render-dir adds the 4 render checks
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
- Development branch: `claude/zealous-cray-le9agd` (the calf's history came from `claude/peaceful-lamport-fk2lw7`, merged in PR #1;
  the cow in PR #2).
- **Safe checkpoints (user rule):** whenever the repo reaches a verified-good state (see "Verification gate"), make a
  commit whose message starts with `CHECKPOINT NN: <short name>` and **push it**. Add a row to the "Checkpoints" table in
  `docs/WORKLOG.md`. (This environment's git proxy only allows pushing the working branch, so pushed tags are rejected
  with 403; checkpoints are therefore marked by commit message.) Find them with `git log --oneline --grep CHECKPOINT`;
  roll back with `git checkout <hash>`.
