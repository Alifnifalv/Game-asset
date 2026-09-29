# Cow (adult Simmental): Unity package notes (DRAFT)

The adult companion of the calf in `Unity/Calf`: a red-pied Simmental cow with horns and udder, built by the same
pipeline (`bash tools/build_all.sh --asset cow`) from the same source rig. Look target: GiM Studio's adult female cow
(`videoplayback.mp4` in the repo root). Everything in this folder except `Editor/` and this README is written by
`tools/export_unity.py` and checked by `tools/validate_export.py`. Unity is not installed in the build container, so the
Unity-side steps are **[not verified in Unity]**, exactly as for the calf.

**The import settings, materials, Animator Controller layout, LOD setup and export decisions are the calf's** (same rig,
same clip set, same exporter): read `Unity/Calf/README.md` for the details and substitute `Cow` for `Calf`. This file
lists what differs.

## Folder contents

| File | What |
|---|---|
| `Cow.fbx` | Main asset (15.0 MB): the `CowRig` skeleton (42 bones, identical names and hierarchy to the calf's `CalfRig`), the skinned meshes `Cow_LOD0/1/2` and 25 takes named like the clips. |
| `Cow.glb` | glTF 2.0 binary (16.5 MB): rig, `Cow_LOD0`, every clip, textures embedded at 2048 px (eye 1024). |
| `Textures/` | `T_Cow_BaseColor`, `T_Cow_Normal`, `T_Cow_MetallicSmoothness` (URP), `T_Cow_MaskMap` (HDRP), `T_Cow_AO`, `T_Cow_Roughness` (4096) and `T_CowEye_BaseColor` (1024). Same packing as the calf's. |
| `Editor/CowSetup.cs` | Menu **Tools > Cow > Setup Cow Asset**: the calf's `CalfSetup.cs` with the cow's names, the cow's gait speeds and no shell-fur material (namespace `CowAsset.EditorTools`, so both assets can live in one project). Creates `Materials/M_Cow_Body`, `Materials/M_Cow_Eye`, `Cow.controller` and `Cow.prefab`. |
| `Cow_export_manifest.json` | Export record (bones, clips with frame ranges / loop / root-motion flags, LOD triangle counts, weights, GLB texture reduction, FBX options). |

No `Fur/` folder: the adult's coat is short and sleek, so there is no shell fur.

## The model

```
Cow                   model root (Unity adds the LODGroup here)
├─ CowRig             armature node: identity transform, scale 1; Root = the Avatar's root (root-motion) bone
├─ Cow_LOD0           SkinnedMeshRenderer, 58,080 tris
├─ Cow_LOD1           SkinnedMeshRenderer, 14,520 tris
└─ Cow_LOD2           SkinnedMeshRenderer,  3,376 tris
```
- Faces **+Z**, Y up, meters, stands on y = 0. **2.57 m long, 1.44 m high (withers ~1.42 m; the horn tips are about as
  high), 0.79 m wide** across the horns and ears.
- Horns (short, curved up and out, cream with dark tips), an udder with four teats (pink skin), dark slate hooves,
  white head, light red-tan coat with irregular white patches, white belly / lower legs / tail.
- Materials: two submeshes per LOD, `M_Cow_Eye` then `M_Cow_Body` (the exporter keeps the body last, as for the calf).
- Skinning: at most 4 influences per vertex on every LOD. The horns are rigid on `Head`; the udder is rigid on the rear
  trunk bones (it does not shear when the thighs swing).

## Clips

The same 25 clips as the calf, with the same names, loop flags and root-motion kinds (the table in
`Unity/Calf/README.md` "Clips"). Differences:
- **Gaits are adult-paced** (cycle times x1.19, dynamic similarity for a body 1.42x the calf's size):

  | Clip | Frames | Cycle | Root travel per cycle | Speed (blend-tree threshold) |
  |---|---|---|---|---|
  | `Walk_Slow(_RM)` | 43 | 1.43 s | 0.767 m | 0.535 m/s |
  | `Walk(_RM)` | 29 | 0.97 s | 1.051 m | 1.087 m/s |
  | `Trot(_RM)` | 19 | 0.63 s | 1.775 m | 2.803 m/s |
  | `Gallop(_RM)` | 17 | 0.57 s | 2.911 m | 5.137 m/s |
  | `Stand` | 43 | 1.43 s | 0 | 0 (as long as `Walk_Slow_RM`) |

  The Trot/Gallop crossfade is kept inside 3.84-4.21 m/s by the time-scaled children (`Trot_RM` x1.37, `Gallop_RM`
  x0.82), as for the calf.
- The key-pose clips (idle, graze, lie down / lying / get up, death, leap, turns, call, head shake) keep the calf's
  timing. Their poses were re-fitted to the adult's body: the grazing neck is lowered less (her longer head reaches the
  grass: nose pad 3.4-7.5 cm above the ground in `Graze_Loop`), the lying hind legs are placed for her longer trunk,
  and the dead head rests on its lower horn and cheek (`Death`, `Death_Lying`).
- Other root motion (Unity space): Leap +2.055 m forward (+Z); Death +1.147 m to her right (+X, the Root ends under the
  carcass); Death_Lying +0.241 m X, -0.540 m Z; TurnLeft90 / TurnRight90 -90 / +90 degrees of yaw, no translation.

## Animator Controller, LODs, materials

As the calf (`Unity/Calf/README.md`), with these values:
- Speed thresholds 0 / 0.535 / 1.087 / 2.803 / (3.84) / (4.21) / 5.137 m/s; Idle -> Locomotion above 0.1 m/s.
- LOD thresholds 35% / 12% / 2% of screen height (the cow is 1.42x taller than the calf, so each LOD switches at a
  greater distance).
- Materials: `M_Cow_Body` (URP Lit / HDRP Lit / Standard, the calf's texture mapping), `M_Cow_Eye` (smoothness 0.92).

## Verification

`bash tools/build_all.sh --asset cow` of 2026-09-29 (565 s; `build/cow/logs/`): QA gate pass (25 clips), stage E scale
exact to 0.014 mm, validator **266 PASS / 0 FAIL / 0 WARN** (the calf's 267 checks minus its shell-fur texture check).
- Rest: 2.566 m long, 1.438 m high, 0.789 m wide, lowest point +1.4 mm, faces +Z; 42 bones; LODs 58,080 / 14,520 /
  3,376 tris.
- Skin on all 1,756 frames: FBX (every LOD) within 0.018 mm of the Blender source, GLB within 0.069 mm.
- Every take matches the source on every frame; root travel as in "Clips"; the Root never leaves the ground plane.
- Per-frame twist of leg / hoof bones at most 13.9 deg (Death_Lying; limit 15).
- GLB: 16.5 MB, textures at 2048 (eye 1024); Khronos glTF-Validator 0 errors, 0 warnings, 1 info (unused eye tangents).
- Render check: source, FBX and GLB on Call f35 have identical bounding boxes.
- `CowSetup.cs` differs from `CalfSetup.cs` only in names, the speed table and the removed fur material; it has not been
  compiled or run here (the calf script was compiled against Unity stubs).

## Known issues / notes
- Everything in `Unity/Calf/README.md` "Not verified: needs a Unity check" applies here too (OI-01).
- While lying, the udder lies inside the ground plane (up to 20 cm below it at the lowest point): it is hidden under
  the body on flat ground, like a real cow's udder pressed aside, but it can show on a slope.
- The key-pose clips run at the calf's tempo (see "Clips").
- Idle's right fore reaches 5.5 mm short of its hoof on frames 46-55 (the source clip over-reaches; the calf has the
  same at 2.3 mm).
