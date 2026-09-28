# Calf (young cow): Unity package notes (DRAFT)

This is a draft. The files in this folder are produced by `tools/export_unity.py` and checked by
`tools/validate_export.py`. Unity is not installed in the build container, so none of the Unity-side
steps below have been tested in Unity. They are marked **[not verified in Unity]**. Everything else was
measured by the validator on the exported files (numbers are in "Verification" below).

## Folder contents

| File | What |
|---|---|
| `Calf.fbx` | Main asset. It contains the `CalfRig` skeleton, the skinned meshes `Calf_LOD0/1/2`, and one animation take per clip, named exactly like the clip (`Idle`, `Eating`, ...). |
| `Calf.glb` | glTF 2.0 binary for glTFast and other engines. It has the rig, `Calf_LOD0` only, every clip as a named animation, and the textures embedded. |
| `Textures/` | The texture set (see "Materials"). The FBX points to these files by relative path (`Textures/<file>`). |
| `Editor/CalfSetup.cs` | Editor script, menu **Tools > Calf > Setup Calf Asset**: sets up the importer, textures, materials, Animator Controller and prefab. Compiled here (C# 9) against stubs of the Unity API, and its controller / prefab logic was run against recording fakes; it has not run in Unity yet. |
| `Fur/` | Optional **URP-only** shell fur (`CalfFur.cs`, `CalfShellFur.shader`). It uses `T_Calf_BaseColor`, `T_Calf_FurMask` and `T_Fur_Noise`. See "Shell fur" below. The shader's HLSL compiles with DXC against the URP 12, 14 and 17 ShaderLibrary; it has not run in Unity yet. |
| `Calf_export_manifest.json` | Export record: source file, bones, dropped helper bones, clips with frame ranges, cyclic and root-motion flags, LOD triangle counts, skin-weight clean-up stats and the FBX options used. |

### Regenerating
```bash
python3 tools/export_unity.py --in build/stage_d.blend --out-dir Unity/Calf --tex-dir build/textures --validate
# or step by step
python3 tools/export_unity.py --in <blend> --out-dir Unity/Calf [--tex-dir build/textures]
python3 tools/validate_export.py --fbx Unity/Calf/Calf.fbx --glb Unity/Calf/Calf.glb --src <blend> \
        [--json report.json] [--render-dir build/export_check]
```
- The input can be any calf blend that follows the pipeline conventions (stage B, C or D).
- If the materials in the blend have no image textures yet, the exporter builds them from `--tex-dir`, which holds the `calf_textures.py` output.
- The source .blend is never modified.

## What is inside the FBX

```
Calf                  model root (Unity adds the LODGroup here)
├─ CalfRig            armature node: identity transform, scale 1
│  └─ Root            ground-level root bone = the Avatar's root node (root motion); Y up, at the origin
│     └─ Body ─ Back ─ Torso ─ Torso2 ─ Torso3 ─ Neck1..3 ─ Head (─ Jaw, Ear.L/R)
│        legs: FrontShoulder/FrontUpperLeg/FrontLowerLeg.X, BackShoulder/BackLeg/BackUpperLeg/BackLowerLeg.X
│        hooves (under the lower legs): FrontLowerLeg.X ─ IKFrontLeg.X ─ FF.X, BackLowerLeg.X ─ IKBackLeg.X ─ FFB.X
│        tail: Back ─ Tail1..7
├─ Calf_LOD0          SkinnedMeshRenderer, 46,752 tris
├─ Calf_LOD1          SkinnedMeshRenderer, 11,688 tris
└─ Calf_LOD2          SkinnedMeshRenderer,  2,688 tris
```
- **Units and axes:**
  - 1 unit = 1 m. The file declares Y up and UnitScaleFactor 100, so Unity's "Convert Units" gives a file scale of 1.0.
  - The calf faces **+Z** and stands on y = 0. It is 1.62 m long, 1.01 m high (ear tips) and 0.69 m wide across the ears.
  - Its left side (`.L` bones) is on Unity -X.
- **Transforms:** `CalfRig` and the three LOD nodes all have identity transforms (no -90° X rotation and no 100× scale).
- **Bones:** 42 bones (the source rig has 46; the 4 IK pole helpers are dropped, see below). No `_end` leaf bones.
  - The four IK pole helpers `PoleTarget.X` and `PoleTargetBack.X` are **not exported**. They have no weights, and the IK constraints that used them are baked into the clips, so nothing references them. Keeping them would add 4 animated transforms per calf for nothing. `--keep-helpers` puts them back.
- **Skinning:**
  - Every vertex has at most 4 bones, and its weights sum to 1.
- **Materials:** every LOD has two submeshes, in this order: `M_Calf_Eye`, then `M_Calf_Body`.
  - The body is deliberately **last**. `Fur/CalfFur.cs` appends shell-fur materials, and Unity draws extra materials on the last submesh.
  - Materials are remapped by name, so nothing else depends on the order.
  - All three LODs use the same bones, so one Animator drives every LOD.
- **Clips:**
  - There is one take per Blender action. Every take keys every bone on every frame and starts at time 0.
  - The frame rate is the scene's frame rate (30 fps for stage B/D).
  - Bones that a clip does not animate stay at the rest pose, so no pose leaks in from other clips.
  - 21 takes: `Idle`, `Idle_LookAround`, `Eating`, `Walk`, `Trot`, `Gallop` (in place), `Walk_RM`, `Trot_RM`, `Gallop_RM`
    (root motion), `TurnLeft90`, `TurnRight90`, `Graze_Start`, `Graze_Loop`, `Graze_End`, `Call`, `HeadShake`, `LieDown`,
    `Lying_Idle`, `GetUp`, `Death`, `Leap`. `Calf_export_manifest.json` has the list with frame ranges, loop and root-motion flags.

## Unity import settings (Model importer)  [not verified in Unity]

`Editor/CalfSetup.cs` (menu **Tools > Calf > Setup Calf Asset**) applies the settings below by script (the rows it
does not touch are Unity's defaults, e.g. Mesh Compression, Read/Write, Optimize Mesh). It also creates
the materials, the Animator Controller and `Calf.prefab` (see those sections). The tables say what each setting is and
why, so you can also set them by hand. Running the menu again is safe: the materials, `Calf.controller` and
`Calf.prefab` keep their asset GUIDs (hand edits to the controller and the prefab are replaced).

**Model tab**
| Setting | Value | Why |
|---|---|---|
| Scale Factor | 1 | The file is authored in meters. |
| Convert Units | On | UnitScaleFactor = 100, so the file scale is 1.0 and 1 unit = 1 m. |
| Bake Axis Conversion | Off | The file is already Y-up and the nodes are identity, so there is nothing to bake. Turning it on should be harmless. |
| Import BlendShapes | Off | There are no blend shapes. |
| Import Visibility / Cameras / Lights | Off | The file contains none. |
| Mesh Compression | Off (or Low) | Keeps the skinned vertex positions exact. |
| Read/Write | Off | |
| Optimize Mesh | Everything | |
| Keep Quads | Off | Unity triangulates quads on import. |
| Weld Vertices | On | |
| Index Format | Auto | LOD0 is about 27k vertices after UV and normal splits, so it fits 16-bit indices. |
| Normals | **Import** | Uses Blender's smooth and custom normals. |
| Tangents | **Import** | Uses the exported MikkTSpace tangents of the quad mesh, which is the exact basis the normal map was baked with (checked: 0.0000° difference). *Calculate Mikktspace* runs on Unity's triangulated mesh and should look practically identical, but *Import* is the exact match. |
| Swap UVs / Generate Lightmap UVs | Off | Skinned mesh, so no lightmapping. |

**Rig tab**
| Setting | Value |
|---|---|
| Animation Type | **Generic**. Humanoid does not apply to a quadruped. |
| Avatar Definition | Create From This Model |
| Root node | **Root** (listed as `CalfRig/Root`). This is the bone the per-clip *Root Transform* settings (Animation tab) apply to. `CalfSetup.cs` sets it through the serialized importer, the same field the Rig tab writes. |
| Skin Weights | Standard (4 Bones). The weights are already limited and normalised, so Unity changes nothing. |
| Strip Bones | **Off**. Root and Tail5 carry no weights but belong to the chains, so they must stay in the Avatar. |
| Optimize Game Objects | Optional. If you turn it on, expose `Head` (look-at, attachments) and `Root` under "Extra Transforms to Expose". |

**Animation tab**
- **General:**
  - Import Animation: On. Import Constraints: Off. Resample Curves: On.
  - Anim. Compression: Optimal. Rotation / Position / Scale error: 0.5 / 0.5 / 0.5.
  - Every frame is keyed in the file, so Unity's compressor decides what to keep.
  - **Motion > Root Motion Node: `<None>`**. A Root Motion Node overrides the per-clip Root Transform settings below (the
    clip inspector then hides them), so root motion comes from the Rig tab's Root node instead. `CalfSetup.cs` clears it
    (an earlier version of the script set it to `CalfRig/Root`).
- **Clip list:** Unity creates one clip per take, with the take's name.
- **Per clip:**
  - **Loop Time:** on for the cyclic clips (`cyclic: true` in the manifest): Idle, Idle_LookAround, Eating, Walk, Trot,
    Gallop and their `_RM` versions, Graze_Loop and Lying_Idle. Off for the turns and the one-shots (Graze_Start/End,
    Call, HeadShake, LieDown, GetUp, Death, Leap). `CalfSetup.cs` takes the flag from the manifest, so clips added later
    are set up too.
  - Cyclic clips repeat the first pose on the last frame, which is Unity's convention. The loop-match lights should be green.
  - **Loop Pose** can therefore stay **off**, which is what `CalfSetup.cs` does. Turn it on only if a light is red.
  - **Root motion** (Root node = Root):
    | Clip type | Root Rotation | Root Position (Y) | Root Position (XZ) |
    |---|---|---|---|
    | In place (every clip not listed below) | Bake Into Pose, Based Upon Original | Bake Into Pose, Original | Bake Into Pose |
    | Root motion (`*_RM`, Leap, Death) | Bake Into Pose, Original | Bake Into Pose, Original | **not baked**: the Animator (Apply Root Motion) moves the GameObject |
    | Turns (TurnLeft90/Right90) | **not baked**: the GameObject turns | Bake Into Pose, Original | Bake Into Pose |

    A take that is not in the script's table but has `root_motion: true` in the manifest gets neither rotation nor XZ baked.
  - Measured Root motion per cycle in Unity space:
    - Walk_RM: +0.74 m in Z. Trot_RM: +1.25 m in Z. Gallop_RM: +2.05 m in Z.
    - At 30 fps that is 0.925, 2.344 and 4.393 m/s. These are the Speed blend-tree thresholds (see "Animator Controller").
    - TurnLeft90: -90° yaw (to the left). TurnRight90: +90° yaw.
    - Leap: 1.45 m forward (+Z). Death: 0.79 m sideways to the calf's right (the body topples over its right hooves;
      the GameObject follows so its collider ends under the carcass).
    - Every other clip: 0.
  - Idle and Eating never move Root, so the bake settings make no difference for them.
- **Mirror:** Off. The rig is symmetric by name (`.L`/`.R`), but Generic clips cannot be mirrored anyway.

**Materials tab**
- Material Creation Mode: Import via MaterialDescription. Location: Use Embedded Materials.
- `CalfSetup.cs` creates `Materials/M_Calf_Body` and `Materials/M_Calf_Eye` for the active pipeline (URP Lit, HDRP Lit or
  Built-in Standard, set up as below) and assigns them under **Remapped Materials**. The FBX material slots have those
  exact names. By hand: create the two materials and remap them the same way.
- The auto-created materials use legacy/Standard mappings (DiffuseColor → base map, NormalMap → normal). Use them only as a preview.

## Materials and texture packing

`CalfSetup.cs` imports every texture with mipmaps, max size 4096 and *High Quality* compression (BC7 on desktop).
Only `*_BaseColor` is sRGB; every other map is linear. `*_Normal` gets Texture Type *Normal map*; everything else stays
*Default*. [not verified in Unity]

| Texture | Content | Import | URP Lit | HDRP Lit |
|---|---|---|---|---|
| `T_Calf_BaseColor.png` | coat, hooves and nose albedo, 4096 | sRGB | **Base Map** | **Base Color Map** |
| `T_Calf_Normal.png` | tangent-space normal map: OpenGL/+Y green (Unity's convention), MikkTSpace, 4096 | Normal map | **Normal Map** (scale 1) | **Normal Map** (Tangent) |
| `T_Calf_MetallicSmoothness.png` | RGB = 0 (no metal), A = smoothness, 4096 | linear | **Metallic Map**. Smoothness Source = *Metallic Alpha*, Smoothness slider 1 | - |
| `T_Calf_MaskMap.png` | R = metallic 0, G = AO, B = detail mask 1, A = smoothness, 4096 | linear | - | **Mask Map** (Metallic remap 0-0, AO remap 0-1, Smoothness remap 0-1) |
| `T_Calf_AO.png` | ambient occlusion (grayscale PNG), 4096 | linear, *Default* type. Not *Single Channel*: Lit reads occlusion from G, which an R8 / BC4 import leaves at 0 | **Occlusion Map** | (already in Mask Map G) |
| `T_Calf_Roughness.png` | roughness, 4096 | linear | not needed (Blender and glTF only) | not needed |
| `T_Calf_FurMask.png`, `T_Fur_Noise.png` | fur length mask (UV space, 1024) and tileable strand noise (256), from `tools/calf_fur_textures.py` | linear | shell fur material only (`M_Calf_Fur`) | - |
| `T_CalfEye_BaseColor.png` | eye: iris, horizontal pupil, sclera, 1024 | sRGB | **Base Map** of `M_Calf_Eye` | **Base Color Map** of `M_Calf_Eye` |

- **`M_Calf_Body`:**
  - Workflow Metallic, Surface Opaque, Receive Shadows on.
  - Smoothness is already encoded in the alpha channels above. In the 1024 test set it runs 0.16-0.29 over most of the texture (10th-90th percentile) and reaches about 0.6 in the glossiest areas (99th percentile).
  - Keep the Smoothness multiplier at 1.
- **`M_Calf_Eye`:**
  - Metallic 0, Smoothness about 0.93 (wet cornea).
  - URP: *Complex Lit* with Clear Coat Mask 1 is closest to the Blender eye (IOR 1.376 coat). Plain *Lit* at smoothness 0.95 is fine at game distance.
  - HDRP: Lit with Coat Mask 1.
  - The eye UV is planar: (0.5, 0.5) is the cornea centre.
- **Texture resolution:** body 4096 (use 2048 on mobile and consoles), eye 1024.

## Animator Controller (`Calf.controller`)  [not verified in Unity]

`CalfSetup.cs` builds it and assigns it to `Calf.prefab` (Apply Root Motion on). Running the setup again rebuilds it
in place: same asset, same GUID, so prefabs, scenes and Animator Override Controllers keep working, but hand edits are
replaced. Customise a copy, or use an Animator Override Controller.

**Parameters**
| Parameter | Type | Effect |
|---|---|---|
| `Speed` | float, m/s | Idle below 0.05, Locomotion above 0.1 (blend tree, see below) |
| `Graze` | bool | Graze_Start → Graze_Loop while set → Graze_End |
| `Lie` | bool | LieDown → Lying_Idle while set → GetUp |
| `Eat`, `Call`, `HeadShake`, `Leap`, `LookAround` | trigger | one-shot: Eating, Call, HeadShake, Leap, Idle_LookAround (each played once) |
| `TurnLeft`, `TurnRight` | trigger | TurnLeft90 / TurnRight90: the GameObject turns 90° in place (root motion) |
| `Die` | trigger | Death (no exit) |

**States and transitions**
- `Idle` (default state) and `Locomotion` carry the state tag **`Ready`**; `Death` has the tag **`Dead`**.
- Graze, Lie and the one-shots start from `Idle` or `Locomotion` (0.2 s blend; turns 0.15 s).
- At the end of a one-shot, Graze_End or GetUp the calf returns to `Locomotion` if `Speed` > 0.1, otherwise to `Idle`
  (exit time 0.95, 0.2 s blend; turns at exit time 1.0, 0.15 s).
- `Death` starts from every standing state: Idle, Locomotion, the three graze states and the one-shots except Leap. It
  is checked before the other transitions of those states. Die during a Leap waits for the landing. There is no lying
  death clip: while `Lie` is set, Die waits, so clear `Lie` too and the calf gets up and then dies.
- **Triggers stay set until a transition uses them.** The one-shot triggers are only used in `Idle` / `Locomotion`, so
  one set while grazing, lying or during another one-shot fires as soon as the calf is back. Set them only when
  `animator.GetCurrentAnimatorStateInfo(0).IsTag("Ready")`, or call `ResetTrigger`.

**Locomotion blend tree (`Speed`)**
- Children: `Walk_RM`, `Trot_RM`, `Gallop_RM`. The thresholds are the root speeds Unity measures on the imported clips
  (`Motion.averageSpeed`; the export values are 0.925, 2.344 and 4.393 m/s). The setup logs a warning if a clip shows
  no root motion (the Rig tab's Root node is not `Root`) or differs from the export value by more than 10%.
- At a threshold the calf moves at exactly `Speed`. Between two thresholds Unity plays the weighted average of the two
  cycle lengths, so the calf moves up to 9% slower than `Speed` (Walk/Trot midpoint: 1.63 → 1.49 m/s; Trot/Gallop: 2%).
- Below 0.925 m/s it walks at 0.925 m/s: there is no slower clip in this export. If the FBX has `Stand` and
  `Walk_Slow_RM` (0.45 m/s, same cycle length), the setup puts them below `Walk_RM` and 0-0.45 m/s is exact.
- `Idle` is not in the tree. As a child, its 3.3 s cycle stretched the 0.8 s walk: `Speed` 0.46 moved the calf at 0.18 m/s.
- The in-place `Walk`, `Trot` and `Gallop` are not used by the controller (for your own in-place setups).

**Turns**
- The GameObject turns by the root yaw of the clip: TurnLeft90 -90°, TurnRight90 +90°.
- During a blend Unity weights each state's root motion by its blend weight. The turns in this export yaw at a constant
  56°/s from the first frame, so the 0.15 s entry blend loses about 4°: one turn gives about 86°. Clips whose yaw eases
  in and out lose almost nothing (0.1°). For exact headings, snap the yaw when the state ends, or set the entry
  transitions to 0 s.

## LOD Group  [not verified in Unity]
- **Setup:**
  - The `_LOD0/_LOD1/_LOD2` suffixes make Unity create a **LODGroup** on the model root with these three renderers.
  - `CalfSetup.cs` sets the transitions below on `Calf.prefab`, on the importer's LODGroup (or on one it adds if the
    importer made none). By hand: select the LODGroup and drag the transition bars.
- **Suggested transitions** (screen-relative height; the calf is about 1 m tall):
  | LOD | Mesh | Tris | Use while the calf covers |
  |---|---|---|---|
  | LOD0 | Calf_LOD0 | 46.8k | > 35% of screen height (close-ups, hero shots) |
  | LOD1 | Calf_LOD1 | 11.7k | 35% - 12% |
  | LOD2 | Calf_LOD2 | 2.7k | 12% - 2% |
  | Culled | - | - | < 2% |
- **Fade Mode:** None (the default). Cross Fade with *Animate Cross-fading* hides the switch. URP Lit supports it from
  Unity 2022.2 (turn on LOD Cross Fade in the URP asset); the shell fur fades with the body. Keep None for large herds
  and on Unity 2021.3.
- **Animator Culling Mode:** *Cull Update Transforms*, or *Cull Completely* for background animals.
- **SkinnedMeshRenderers:** keep *Update When Offscreen* off.

## Shell fur (optional, URP only)  [not verified in Unity]

`Fur/CalfShellFur.shader` (`Calf/URP/ShellFur`) and `Fur/CalfFur.cs` draw the coat as `shells` (default 12) alpha-clipped
layers over the LOD0 body.

**Setup**
1. Run **Tools > Calf > Setup Calf Asset** in a URP project. It creates `Materials/M_Calf_Fur` with `T_Calf_BaseColor`
   (Base Color), `T_Calf_FurMask` (Fur Mask) and `T_Fur_Noise` (Strand Noise). By hand: a material with
   `Calf/URP/ShellFur` and those three textures.
2. Add **`CalfFur`** to the calf's root object (the one with the Animator) and assign `M_Calf_Fur` to *Fur Material*.
   The prefab does not include it: fur is for hero and close-up calves.
3. Tune *Shells* (4-24) and *Fur Length* (default 0.009 m) on the component, and droop, thinning, root occlusion, tip
   lightening and light wrap on the material. Call `Build()` after changing them at runtime.

**How it works**
- On Start it appends the shell materials to `Calf_LOD0`. The body is the last submesh, and Unity draws the last submesh
  once more for every extra material: no mesh copy and no extra skinning, and the fur disappears with LOD0.
- Calves with the same fur material, shell count and length share one set of shell materials. Disabling the component
  removes its shells; enabling it adds them back.
- If the body material is not found on `Calf_LOD0`, or the pipeline is not URP, it logs a warning and adds nothing.

**Rendering**
- Passes: `UniversalForwardOnly` (colour), `DepthOnly` and `DepthNormalsOnly`, all with the same vertex function. The fur
  therefore draws in the Forward, Forward+ and Deferred renderers and with Depth Priming. It also shows up in the depth
  and normals textures (SSAO). It does not write rendering layers (decal layers).
- Main light with shadows (cascades, soft shadows, the Screen Space Shadows feature), ambient probes and fog.
  Additional lights do not light the fur. The fur does not cast shadows; the body does.
- LOD Cross Fade is supported, and the passes have the XR single-pass-instanced (stereo) macros.
- Cost per calf: `shells` extra draws of the 46.8k-triangle LOD0 body in the colour pass, and the same again in each
  depth prepass URP runs.
- The HLSL of all 1032 variant/stage combinations compiles with DXC (D3D11 target) against the URP 12 (2021.3), 14
  (2022.3) and 17 (Unity 6) ShaderLibrary. The prepass and colour-pass vertex code compile to the same `SV_Position`
  instructions.

**Built-in or HDRP projects:** the shader's `PackageRequirements` block makes Unity skip it, so its URP includes cause no
errors; Unity prints a warning that the shader has no supported SubShader. `CalfFur` does nothing. Delete the `Fur/`
folder if you do not want the warning.

## glTF / glTFast  [not verified in Unity]
- `Calf.glb` uses the glTF convention: Y up, front = +Z, meters.
- In Unity with glTFast (`com.unity.cloud.gltfast`):
  - Set the import *Animation Method* to Mecanim to get AnimationClips named like the clips.
  - glTFast mirrors X when it converts to Unity's left-handed space, so the calf should face +Z as with the FBX.
- It has LOD0 only, 4 influences per vertex, and a PBR material:
  - baseColor, normal, occlusion, and roughness packed into metallicRoughness.
  - The eye uses baseColor only.
- Khronos glTF-Validator result: 0 errors and 0 warnings. There is one info: the eye primitive's tangents are unused because the eye has no normal map.

## Export decisions (Blender FBX exporter options)
| Option | Value | Reason |
|---|---|---|
| `axis_forward`, `axis_up` | `-Z`, `Y` | Blender -Y (the calf's front) becomes FBX +Z. Unity mirrors X, so the calf faces Unity +Z with Y up. |
| `apply_unit_scale`, `apply_scale_options` | True, `FBX_SCALE_ALL` | Coordinates stay in meters and UnitScaleFactor is 100 (1 file unit = 1 m). There is no 100× scale on any node. |
| `bake_space_transform` | True | Bakes the axis change into the mesh data, so the LOD nodes are identity. |
| rig axis bake (tool step) | - | `bake_space_transform` skips armatures. Blender would write `CalfRig` with a -90° X rotation. The tool therefore rotates the rest pose into FBX axes and gives the armature the inverse rotation, and the exporter's conversion cancels it. The result is exact: rest skeleton error 0.000 mm and identical takes. |
| `primary/secondary_bone_axis` | `Y`, `X` | Blender's native bone frame, so no correction matrix is applied to every key. Generic rigs don't care about bone axes. |
| `armature_nodetype` | `NULL` | The armature becomes a plain transform. `ROOT`/`LIMBNODE` would add an extra joint above Root. |
| `add_leaf_bones` | False | No `_end` bones in the Unity hierarchy. |
| `use_armature_deform_only` | True | Drops the unweighted PoleTarget helpers but keeps Root (the unweighted parent of weighted bones). |
| `bake_anim_use_nla_strips` | True (tool builds one strip per action) | Take name = strip name = action name. |
| `bake_anim_use_all_actions` | False | Tested in Blender 5: it does export every slotted action, but the takes are named `CalfRig|Eating`. Unkeyed channels also keep whatever pose was set at export time: a naive export from a file with an active action leaked 198 mm of head motion into another take. |
| `bake_anim_use_all_bones`, `force_startend_keying`, `step`, `simplify_factor` | True, True, 1, **0** | Every bone keyed on every frame with no lossy simplification (bone error ≤ 0.001 mm). Unity compresses afterwards. |
| `use_tspace`, `use_triangles` | True, False | Tangents are exported from the quad mesh, which is the exact normal-map bake basis. Quads stay quads. N-gons, if any, are triangulated first. |
| `mesh_smooth_type` | `FACE` | Writes normals plus smoothing groups. |
| `path_mode`, `embed_textures` | `RELATIVE`, False | Textures are referenced as `Textures/<file>`; they are not embedded. |
| skin weights (tool step) | refit to 4 | The subdivided LODs have up to 7-8 influences. Plain truncation, which is what Unity would do, moved neck and brisket vertices by up to 13 mm (Eating) and 41 mm (Gallop). The tool instead picks, for each vertex, the 4-bone subset and weights that best reproduce the original deformation over sampled poses from all clips. That brings the worst case down to 2.4 mm (Eating/Idle) and 23 mm (Gallop). |

## Verification (tools/validate_export.py)

The validator does three things:
1. It parses the FBX and GLB directly, which is what Unity's importers read. It evaluates every take with FBX and glTF transform maths.
2. It re-imports both files into clean Blender scenes.
3. It runs the Khronos glTF-Validator.

**Current export** (`build/stage_d.blend`: 21 clips at 30 fps, 42 bones, hooves under the lower legs;
`build/logs/validate.log`): **172 PASS, 0 FAIL, 1 WARN**.
- **Axes, units and transforms:** Y up, front +Z, UnitScaleFactor 100. `CalfRig` and `Calf_LOD0/1/2` have T=0, R=0, S=1.
  In Unity space, Head is at (0, 0.867, 0.805) and Tail7 at (0, 0.543, -0.543); the `.L` bones are on -X.
- **Bones:** 42 of the source's 46 (the 4 pole helpers dropped). The hierarchy matches the source, with no leaf bones.
  The rest skeleton matches to 0.001 mm (FBX maths) and 0.009 mm (Blender re-import).
- **LODs:** 46,752 / 11,688 / 2,688 tris, identical to the source. Every LOD has normals, tangents, binormals and UVMap,
  with submeshes in the order `M_Calf_Eye`, `M_Calf_Body`. The tangents differ from Blender's MikkTSpace by 0.0000°.
- **Skin:** at most 4 influences, at least 1. The weight sums are within 5.1e-8 of 1.
- **Takes:** 21, named exactly like the actions, with exact frame ranges. Every bone matches the source to 0.004 mm (FBX
  maths) and 0.010 mm (Blender re-import); GLB 0.043 mm. Root motion in Unity space: Walk_RM / Trot_RM / Gallop_RM
  +0.740 / +1.250 / +2.050 m in Z per cycle, Leap +1.447 m in Z, Death +0.787 m in X, TurnLeft90 -90°, TurnRight90 +90°,
  every other take 0.
- **The WARN** is the 4-influence skin against the source's up-to-8-influence skin (LOD0, 63 sampled frames): worst frame
  Gallop f14 with max 23.7 mm, 99.9th percentile 6.8 mm, mean 0.13 mm. See "Known issues".
- **GLB:** 35.9 MB, LOD0 only, 4 embedded PNGs. Khronos glTF-Validator 2.0.0-dev.3.10: 0 errors, 0 warnings, 1 info
  (UNUSED_MESH_TANGENT on the eye).

**Checked here without Unity**
- `CalfSetup.cs` and `CalfFur.cs` compile with Roslyn (C# 9, the Unity 2021.3 language level, no warnings) against stubs
  of the Unity 2021.3 / 2022.3 / 6 API members they use.
- The setup's model, controller and prefab code was run against recording fakes of the Unity editor API. Checked: the
  Rig root node is set and the Root Motion Node cleared, the per-clip settings match the manifest, the controller graph
  (every state gets back to Idle, Death sources, transition order, turn exit times), rebuilding in place keeps the asset
  and leaves no stale sub-assets, and the prefab's LOD thresholds.
- `CalfFur` was run against the same fakes: shared shells, rebuild, disable / enable, and the missing-body and non-URP
  guards.
- The shell-fur shader HLSL compiles with DXC for every variant on URP 12, 14 and 17 (see "Shell fur").

**Not verified: needs a Unity check**
- The actual Unity import:
  - LODGroup auto-creation.
  - The Rig tab's Root node, set through the serialized importer. The setup logs the root speed Unity measures on
    each `_RM` gait, and a warning if it is 0.
  - Root-motion behaviour of the `_RM` clips, the turns, Leap and Death.
  - The loop-match lights.
  - Clip compression error.
- That "Tangents: Import" keeps the handedness (w) from the exported binormals.
- URP and HDRP material look, the texture import settings, and the shell fur's look and cost.
- glTFast orientation, material mapping and clip import.

## Known issues / notes
- **Skin weights:**
  - In the source blend, LOD0 and LOD1 have up to 7-8 bone influences per vertex. Blender previews use all of them, while the game uses 4.
  - The export refit keeps the difference small for the current clips. The remaining gallop deviation sits on the brisket midline, which the source splits between both front legs.
  - The proper fix is upstream: limit the weights to 4 and clean up the brisket in stage B. Blender and Unity would then match exactly.
- **Hind hooves:** in the rest pose the hind hoof soles sit **12 mm below y = 0** (274 hoof vertices; also true in the source). Check this against the ground-contact logic before tuning foot IK or terrain alignment.
- **Blender FBX re-import:**
  - Blender's FBX importer connects bones whose head sits on the parent's tail and then ignores their translation keys. The validator disconnects them before comparing.
  - Unity is not affected, because it applies every translation key.
