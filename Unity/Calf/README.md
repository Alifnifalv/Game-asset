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
| `Editor/CalfSetup.cs` | Editor script, menu **Tools > Calf > Setup Calf Asset**: sets up the importer, textures, materials, Animator Controller and prefab. It has not been compiled here. |
| `Fur/` | Optional URP shell fur (`CalfFur.cs`, `CalfShellFur.shader`). It uses `T_Calf_FurMask` and `T_Fur_Noise`. It has not been compiled here. |
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
│  └─ Root            ground-level root bone = root-motion node (Y up, at the origin)
│     └─ Body ─ Back ─ Torso ─ Torso2 ─ Torso3 ─ Neck1..3 ─ Head (─ Jaw, Ear.L/R)
│        legs: FrontShoulder/FrontUpperLeg/FrontLowerLeg.X, BackShoulder/BackLeg/BackUpperLeg/BackLowerLeg.X
│        hooves: IKFrontLeg.X ─ FF.X, IKBackLeg.X ─ FFB.X      tail: Tail1..7
├─ Calf_LOD0          SkinnedMeshRenderer, 46,752 tris
├─ Calf_LOD1          SkinnedMeshRenderer, 11,688 tris
└─ Calf_LOD2          SkinnedMeshRenderer,  2,688 tris
```
- **Units and axes:**
  - 1 unit = 1 m. The file declares Y up and UnitScaleFactor 100, so Unity's "Convert Units" gives a file scale of 1.0.
  - The calf faces **+Z** and stands on y = 0. In the current stage B it is 1.62 m long, 1.03 m high to the ear tips and 0.69 m wide across the ears.
  - Its left side (`.L` bones) is on Unity -X.
- **Transforms:** `CalfRig` and the three LOD nodes all have identity transforms (no -90° X rotation and no 100× scale).
- **Bones:** 42 bones with the Jaw/Ear rig (39 on the older snapshot). No `_end` leaf bones.
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
  - The Blender clips at the time of writing: `Idle`, `Eating`, `Walk`, `Walk_RM`, `Trot`, `Trot_RM`, `Gallop`, `Gallop_RM`, `TurnLeft90`, `TurnRight90`. More key-pose families will be added. `Calf_export_manifest.json` has the current list.

## Unity import settings (Model importer)  [not verified in Unity]

`Editor/CalfSetup.cs` (menu **Tools > Calf > Setup Calf Asset**) applies most of the settings below by script. It
also creates the materials, an Animator Controller and a `Calf.prefab` with a LODGroup. The tables say what the
settings should be and why, and flag where the script differs.

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
| Tangents | **Import** (recommended) | Uses the exported MikkTSpace tangents of the quad mesh, which is the exact basis the normal map was baked with (checked: 0.0000° difference). `CalfSetup.cs` currently sets *Calculate Mikktspace*. That runs on Unity's triangulated mesh and should look practically identical, but *Import* is the exact match. |
| Swap UVs / Generate Lightmap UVs | Off | Skinned mesh, so no lightmapping. |

**Rig tab**
| Setting | Value |
|---|---|
| Animation Type | **Generic**. Humanoid does not apply to a quadruped. |
| Avatar Definition | Create From This Model |
| Root node | **Root** (listed as `CalfRig/Root`) |
| Skin Weights | Standard (4 Bones). The weights are already limited and normalised, so Unity changes nothing. |
| Strip Bones | Off (suggested). Root and Tail5 carry no weights but belong to the chains, so keep them in the Avatar. `CalfSetup.cs` leaves Unity's default (On). If the Root node or Tail5 is missing from the Avatar, switch it off. |
| Optimize Game Objects | Optional. If you turn it on, expose `Head` (look-at, attachments) and `Root` under "Extra Transforms to Expose". |

**Animation tab**
- **General:**
  - Import Animation: On. Import Constraints: Off. Resample Curves: On.
  - Anim. Compression: Optimal. Rotation / Position / Scale error: 0.5 / 0.5 / 0.5.
  - Every frame is keyed in the file, so Unity's compressor decides what to keep.
- **Clip list:** Unity creates one clip per take, with the take's name.
- **Per clip:**
  - **Loop Time:** turn it on for the cyclic clips (`cyclic: true` in the manifest): Idle, Eating, Walk, Trot, Gallop and their `_RM` versions, plus the looping key-pose clips. Leave it off for TurnLeft90, TurnRight90 and the one-shots.
  - Cyclic clips repeat the first pose on the last frame, which is Unity's convention. The loop-match lights should be green.
  - **Loop Pose** can therefore stay **off**, which is what `CalfSetup.cs` does. Turn it on only if a light is red.
  - **Root motion** (Root node = Root):
    | Clip type | Root Rotation | Root Position (Y) | Root Position (XZ) |
    |---|---|---|---|
    | In place (Idle, Eating, Walk, Trot, Gallop) | Bake Into Pose, Based Upon Original | Bake Into Pose, Original | Bake Into Pose |
    | Root motion (`*_RM`) | Bake Into Pose, Original | Bake Into Pose, Original | **not baked**: the Animator (Apply Root Motion) moves the GameObject |
    | Turns (TurnLeft90/Right90) | **not baked**: the GameObject turns | Bake Into Pose, Original | Bake Into Pose |
  - Measured Root motion per cycle in Unity space:
    - Walk_RM: +0.74 m in Z. Trot_RM: +1.25 m in Z. Gallop_RM: +2.05 m in Z.
    - At 30 fps that is 0.93, 2.34 and 4.39 m/s, the same as the Speed blend-tree thresholds in `CalfSetup.cs`.
    - TurnLeft90: -90° yaw (to the left). TurnRight90: +90° yaw.
    - Every other clip: 0.
  - Idle and Eating never move Root, so the bake settings make no difference for them.
- **Mirror:** Off. The rig is symmetric by name (`.L`/`.R`), but Generic clips cannot be mirrored anyway.

**Materials tab**
- Material Creation Mode: Import via MaterialDescription. Location: Use Embedded Materials.
- Create your own `M_Calf_Body` and `M_Calf_Eye` materials in the project, set up as below.
- Assign them under **Remapped Materials**. The FBX material slots have those exact names.
- The auto-created materials use legacy/Standard mappings (DiffuseColor → base map, NormalMap → normal). Use them only as a preview.

## Materials and texture packing

| Texture | Content | Import settings [not verified in Unity] | URP Lit | HDRP Lit |
|---|---|---|---|---|
| `T_Calf_BaseColor.png` | coat, hooves and nose albedo | sRGB, BC7 (or Normal Quality), max 4096 | **Base Map** | **Base Color Map** |
| `T_Calf_Normal.png` | tangent-space normal map: OpenGL/+Y green (Unity's convention), MikkTSpace | Texture Type **Normal map**, BC5 | **Normal Map** (scale 1) | **Normal Map** (Tangent) |
| `T_Calf_MetallicSmoothness.png` | RGB = 0 (no metal), A = smoothness | sRGB **off**, BC7 | **Metallic Map**. Smoothness Source = *Metallic Alpha*, Smoothness slider 1 | - |
| `T_Calf_MaskMap.png` | R = metallic 0, G = AO, B = detail mask 1, A = smoothness | sRGB **off**, BC7 | - | **Mask Map** (Metallic remap 0-0, AO remap 0-1, Smoothness remap 0-1) |
| `T_Calf_AO.png` | ambient occlusion | sRGB off, single channel (R), BC4 | **Occlusion Map** | (already in Mask Map G) |
| `T_Calf_Roughness.png` | roughness | - | not needed (Blender and glTF only) | not needed |
| `T_Calf_Height.png` | 16-bit fur-strand height (the normal map was baked from it) | - | not needed; optional height or detail map | optional |
| `T_Calf_FurMask.png`, `T_Fur_Noise.png` | fur length mask (UV space) and tileable strand noise, from `tools/calf_fur_textures.py` | sRGB off | optional shell fur material only | - |
| `T_CalfEye_BaseColor.png` | eye: iris, horizontal pupil, sclera | sRGB, max 1024 | **Base Map** of `M_Calf_Eye` | **Base Color Map** of `M_Calf_Eye` |

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

## LOD Group  [not verified in Unity]
- **Setup:**
  - The `_LOD0/_LOD1/_LOD2` suffixes make Unity create a **LODGroup** on the model root with these three renderers.
  - If it does not appear, add the LODGroup by hand and drag the three renderers in.
- **Suggested transitions** (screen-relative height; the calf is about 1 m tall):
  | LOD | Mesh | Tris | Use while the calf covers |
  |---|---|---|---|
  | LOD0 | Calf_LOD0 | 46.8k | > 35% of screen height (close-ups, hero shots) |
  | LOD1 | Calf_LOD1 | 11.7k | 35% - 12% |
  | LOD2 | Calf_LOD2 | 2.7k | 12% - 2% |
  | Culled | - | - | < 2% |
- These are the values `CalfSetup.cs` uses when it has to create the LODGroup itself.
- **Fade Mode:** Cross Fade with *Animate Cross-fading* hides the switch. Choose None for large herds.
- **Animator Culling Mode:** *Cull Update Transforms*, or *Cull Completely* for background animals.
- **SkinnedMeshRenderers:** keep *Update When Offscreen* off.

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

**Dev run** (build/stage_b_snapshot_v1.blend with the 1024 test textures, `--render-dir`): **81 PASS (3 of them render checks), 0 FAIL, 0 WARN**.
- **Axes, units and transforms:** the file is Y-up with front +Z. UnitScaleFactor is 100. `CalfRig` and `Calf_LOD0/1/2` have T=0, R=0, S=1. In Unity space, Head is at (0, 0.867, 0.831) and Tail7 at (0, 0.543, -0.601).
- **Bones:** 39 of 43 exported (the 4 pole helpers dropped). The hierarchy matches the source, with no leaf bones.
- **LODs:** 46,752 / 11,688 / 2,688 tris, identical to the source. Every LOD has normals, tangents, binormals and UVMap. The tangents differ from Blender's MikkTSpace by 0.0000°.
- **Skin:** at most 4 influences, at least 1. The weight sums are within 5e-8 of 1.
  - LOD0 deformation vs the source's 8-influence skin: max 1.6 mm, mean 0.014 mm.
- **Takes:** the names match the actions exactly and the frame ranges are exact.
  - Every bone position and bone axis matches the source to 0.001 mm (FBX maths) and 0.004 mm (Blender re-import).
  - GLB: 0.001 mm (glTF maths) and 0.003 mm (re-import).
  - The rest skeleton error is 0.000 mm.
- **Materials:** both slots are present. The FBX texture references resolve to `Textures/…`. The GLB embeds 4 PNGs.
- **Khronos gltf-validator 2.0.0-dev.3.10:** 0 errors, 0 warnings.
- **Renders:** contact sheets of the source, the FBX re-import and the GLB re-import on the same frame are identical (same bounding box to 1 mm).

**Current stage B copy** (30 fps, 46 bones with Jaw/Ears, Eating 0-180 / Idle 0-100, `--validate`): **78 PASS, 0 FAIL, 0 WARN**.

**Stage D copy** (10 clips at 30 fps, 42 bones, hooves re-parented under the legs): **117 PASS, 0 FAIL, 1 WARN**.
- The WARN is the 4-influence skin deviation: max 15 mm at Gallop_RM f14, 99.9th percentile 4.6 mm, mean 0.06 mm.

**Not verified: needs a Unity check**
- The actual Unity import:
  - LODGroup auto-creation.
  - Avatar and Root-node selection, including with Strip Bones.
  - Root-motion behaviour of the `_RM` and Turn clips.
  - The loop-match lights.
  - Clip compression error.
- That "Tangents: Import" keeps the handedness (w) from the exported binormals.
- URP and HDRP material look, and the texture import presets.
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
