# Rottweiler (male): Unity package notes (DRAFT)

A game-ready male Rottweiler: model with 3 LODs, 4K PBR textures, a 43-bone rig and 25 clips. Look target: GiM
Studio's *Animalia - Rottweiler* (the stills and `videoplayback (4).mp4` in `Rottweiler (male)/`). It is built in-house
by `bash tools/build_all.sh --asset dog` (`tools/dog/`); the sample model in `Rottweiler (male)/Dog/` served only as a
reference for the rig layout and the sit/lie poses (its 870-triangle mesh is not used). Everything in this folder
except `Editor/` and this README is written by `tools/export_unity.py` and checked by `tools/validate_export.py`.
Unity is not installed in the build container, so the Unity-side steps are **[not verified in Unity]** (as for the
calf and the cow).

The FBX conventions, import settings, material mapping and LOD setup are the calf's (`Unity/Calf/README.md`, same
exporter); this file lists the Rottweiler's rig, clips and Animator.

## Folder contents

| File | What |
|---|---|
| `Rottweiler.fbx` | Main asset (13.9 MB): the `RottweilerRig` skeleton (43 bones), the skinned meshes `Rottweiler_LOD0/1/2` and 25 takes named like the clips. |
| `Rottweiler.glb` | glTF 2.0 binary (11.2 MB): rig, `Rottweiler_LOD0`, every clip, textures embedded at 2048 px (eye 1024). |
| `Textures/` | `T_Rottweiler_BaseColor` (sRGB), `T_Rottweiler_Normal` (tangent space, OpenGL +Y), `T_Rottweiler_MetallicSmoothness` (URP: A = smoothness), `T_Rottweiler_MaskMap` (HDRP: G = AO, A = smoothness), `T_Rottweiler_AO`, `T_Rottweiler_Roughness` (all 4096) and `T_RottweilerEye_BaseColor` (1024). |
| `Editor/RottweilerSetup.cs` | Menu **Tools > Rottweiler > Setup Rottweiler Asset**: importer settings (Generic rig, Root node = `Root`, per-clip loop / root motion), materials for URP / HDRP / Built-in, `Rottweiler.controller`, `Rottweiler.prefab` (namespace `RottweilerAsset.EditorTools`, so it can live next to the calf and cow). |
| `Rottweiler_export_manifest.json` | Export record (bones, clips with frame ranges / loop / root-motion flags, LOD triangle counts, weights, GLB texture reduction, FBX options). |

## The model

```
Rottweiler              model root (Unity adds the LODGroup here)
├─ RottweilerRig        armature node: identity transform, scale 1; Root = the Avatar's root (root-motion) bone
├─ Rottweiler_LOD0      SkinnedMeshRenderer, 46,848 tris
├─ Rottweiler_LOD1      SkinnedMeshRenderer, 10,992 tris
└─ Rottweiler_LOD2      SkinnedMeshRenderer,  3,106 tris
```
- Faces **+Z**, Y up, meters, stands on y = 0. Withers 0.66 m (FCI standard for a male: 61-68 cm), head top 0.89 m,
  **1.175 m long** (nose to the hanging tail), **0.889 m high**, **0.390 m wide**; trunk 0.74 m (point of shoulder to
  point of buttock).
- Black coat with a faint blue-grey sheen; mahogany tan markings: a spot over each eye, the cheeks, the sides of the
  muzzle and the chin (the bridge stays black), the throat, two triangles on the forechest, the fore legs from the toes
  to half-way up the forearm (higher on the inside), the hind legs from the toes up the front of the hock and the inside
  of the thighs, under the tail root. Black lips, nose leather and claws, dark pads, a natural (undocked) tail, pendant
  triangular ears.
- A real mouth: the lips part along the lip line and open onto an oral cavity with gums, a tongue (3 bones, it slides
  out for panting) and teeth (canines, incisors, a premolar ridge), so `Bark`, `Growl`, `Idle_Pant` and `Attack` open
  the mouth without stretching the lips. Separate eyeballs (their own material) that can look around (`Eye.L/R`).
- Materials: two submeshes per LOD, `M_Rottweiler_Eye` then `M_Rottweiler_Body` (the exporter keeps the body last).
- Skinning: at most 4 influences per vertex on every LOD (the Blender preview deforms exactly as Unity).

## Rig (43 bones)

`Root` (ground, root motion) > `Hips` (the body root) > `Spine1` > `Spine2` > `Spine3` > `Neck1` > `Neck2` > `Head` >
`Nose`, `Jaw` > `Tongue1-3`, `Ear1.L/R` > `Ear2.L/R`, `Eye.L/R`; `Hips` > `Tail1-6`;
`Spine3` > `Scapula.X` > `UpperArm.X` > `Forearm.X` > `FrontFoot.X` (pastern) > `FrontToe.X`;
`Hips` > `Thigh.X` > `Shin.X` > `HindFoot.X` (metatarsus) > `HindToe.X`. `.L` is the dog's left.
Every clip is baked to FK keys on every frame (no constraints), so engine blending cannot detach the paws.

## Clips

| Clip | Frames | Loop | Root motion | Notes |
|---|---|---|---|---|
| `Idle` | 120 | yes | - | breathing, weight shift, ear twitch, slow tail sway |
| `Idle_Pant` | 60 | yes | - | mouth open, tongue out, fast breaths |
| `Idle_LookAround` | 150 | yes | - | head turns left and right, ears alert |
| `Idle_Sniff` | 60 | yes | - | nose to the ground |
| `Eat` | 60 | yes | - | head down, chewing |
| `Growl` | 60 | yes | - | aggressive stance: head low, lips lifted, ears back, tail up |
| `Bark` | 40 | once | - | two barks |
| `Attack` | 34 | once | - | crouch, lunge, bite, shake |
| `PlayBow` | 64 | once | - | front down, rump up, fast wag |
| `Jump` | 44 | once | 1.60 m forward | crouch, take-off, flight, landing, settle |
| `Walk_Slow` / `_RM` | 34 | yes | 0.55 m/s | sniffing walk, head low |
| `Walk` / `_RM` | 20 | yes | 1.15 m/s | lateral-sequence walk |
| `Trot` / `_RM` | 16 | yes | 2.50 m/s | diagonal trot |
| `Gallop` / `_RM` | 12 | yes | 6.50 m/s | rotary gallop, right fore lead |
| `Sit_Start` / `Sit_Idle` / `Sit_End` | 36 / 90 / 30 | no / yes / no | - | sits square, pants, stands up |
| `Lie_Start` / `Lying_Idle` / `Lie_End` | 60 / 120 / 50 | no / yes / no | - | through the sit into a sphinx lie, and back |
| `Death` | 80 | once | - | staggers, buckles, falls onto its right side |

In-place gaits (no suffix) keep the Root still; `_RM` gaits move it at the listed speed. Start / End clips begin or end
exactly on the standing pose (`Idle` frame 0), and each idle loops on its own pose.

## Animator Controller (built by `RottweilerSetup.cs`)

- Parameters: `Speed` (float, m/s); bools `Sit`, `Lie`, `Sniff`, `Eat`, `Growl`, `Pant`; triggers `Bark`, `Attack`,
  `PlayBow`, `Jump`, `LookAround`, `Die`.
- `Idle` (default) <-> `Locomotion` (1D blend tree on `Speed`: Walk_Slow_RM 0.55, Walk_RM 1.15, Trot_RM 2.5, a
  time-scaled Trot_RM x1.4 (3.5), a time-scaled Gallop_RM x0.6 (3.9), Gallop_RM 6.5 m/s) above 0.1 m/s, back below 0.05.
- `Sit`: Sit_Start -> Sit_Idle -> (Sit cleared) Sit_End -> Idle/Locomotion. `Lie`: Lie_Start -> Lying_Idle ->
  Lie_End. The behaviour bools switch Idle to the matching loop (0.3 s blends).
- One-shots from Idle / Locomotion, back at 95 %. `Die` from every standing, sitting or lying state (the Death clip
  starts from the standing pose: from a sit or a lie it blends over 0.25 s).
- State tags: `Ready` (Idle, Locomotion) and `Dead` (Death), for game code.

## LODs

LODGroup thresholds 35 % / 12 % / 2 % of screen height (the calf's), LOD1 and LOD2 decimated from LOD0 with the same UV
atlas (one texture set).

## Verification

`bash tools/build_all.sh --asset dog` of 2026-09-29 (about 6 min; `build/dog/logs/`): dog QA gate pass (25 clips),
validator **264 PASS / 0 FAIL / 0 WARN**.
- Every take matches the source on every frame (~0.005 mm); skin on all 1,347 frames: FBX (every LOD) within 0.006 mm
  of the Blender source, GLB within 0.008 mm; at most 4 influences.
- Root travel: Jump 1.600 m along +Z; `_RM` gaits 0.623 / 0.767 / 1.333 / 2.600 m per cycle; the Root never leaves the
  ground plane and never pitches or rolls. Clip boundaries vs Idle f0 within 0.4 deg (Jump: 3.3 deg at the tail tip).
- Per-frame twist of leg bones at most 11.4 deg (Death; limit 15).
- GLB: Khronos glTF-Validator 0 errors, 0 warnings (1 info: unused eye tangents). Render check: source, FBX and GLB
  on Attack f15 have identical bounding boxes.

## Known issues / not verified
- Nothing has been imported into Unity (OI-01 applies): importer settings, Avatar root node, root motion, the Animator,
  materials in URP/HDRP, the LODGroup. `RottweilerSetup.cs` has not been compiled here (no C# compiler in the build
  container); it is the calf's script with the Rottweiler's tables and states.
- The mesh is procedural (signed-distance anatomy, marching cubes, decimated): it matches the Rottweiler's proportions
  and markings but not the sculpted detail of the GiM model (skin folds, muscle definition, fur cards).
- `Death` falls in 28 frames (GiM: faster); it has no root motion.
