# Work log: calf asset

Newest status first, then a chronological log. Each entry: what, why, how it was verified, open issues.

## Current status (update on every milestone)
| Area | State | Where |
|---|---|---|
| Geometry (calf reshape, eyes, UVs, LODs) | Done, tuned against the side-view silhouette | `tools/calf_stage_a.py`, `tools/calf_stage_b.py` |
| Rig upgrade | Jaw + Ear.L/R done; lower-leg tails fixed; 30 fps | `tools/calf_stage_b.py` |
| Coat textures | Done (2048 verified); hooves changed to pale horn; final 4K run -> `build/textures`, `build/stage_c.blend` | `tools/calf_textures.py` |
| Existing clips on the reshaped rig (Eating/Idle) | Done: leg IK re-solved (0 mm hoof gap; Idle front.R 2.3 mm unreachable in the source too) | `tools/check_animation.py`, `tools/rebake_leg_ik.py` |
| Unity export + validator | Done: 117 PASS / 0 FAIL / 1 WARN on the 10-clip stage D; Khronos glTF validator 0 errors | `tools/export_unity.py`, `tools/validate_export.py`, `Unity/Calf/README.md` |
| New animation set | Gaits done: Walk/Trot/Gallop (RM + in place), TurnLeft90/Right90. Key-pose families in progress | `tools/calf_animations.py`, `tools/anim_lib.py`, `tools/anim_gait.py`, `tools/clips/` |
| Export rig | Hooves re-parented under the lower legs for engine blending (world motion unchanged, 0.000 mm) | `anim_lib.reparent_hooves_for_export` |
| Unity setup script | Written; can't be compiled here, needs one Unity check | `Unity/Calf/Editor/CalfSetup.cs` (menu Tools > Calf > Setup Calf Asset) |
| Key-pose clip families | In progress (workflow: author → adversarial review → fix): idle_graze, lying, actions | `tools/clips/*.py` |
| Fur (optional, URP) | Shader + component + fur mask/noise textures written; needs a Unity compile check | `Unity/Calf/Fur/`, `tools/calf_fur_textures.py` |

## Log

### 2026-09-28: session 1
**Context gathered**
- `cow.glb` is a Sketchfab export of a low-poly stylised adult cow: 7 flat-colour meshes (~1.5k verts, all triangles, no UVs/textures), a 43-bone rig and 2 clips (`Eating`, `Idle`). It has horns, an udder and a stray `Icosphere`.
- The references are GiM Studio renders/videos of the *Animalia* young cow: red-pied (orange-brown and white) coat, white forehead blaze, white shoulder band, white belly/hip band/lower legs, pale muzzle, pale hooves, large ears, hornless.
- The user first asked for a plan to animate the cow like the video, then asked to **edit the model into a calf**. The final target is the Animalia Cow pack quality, and the user **rejected buying it: build in-house**.

**Environment**
- Installed Blender 5.0.1 as `pip install bpy` (the Blender site is blocked). OpenCV was pinned below 4.11 for numpy 1.26.
- YouTube, gim.studio and assetstore.unity.com are blocked, so the user added the videos to the repo instead.

**Stage A** (`tools/calf_stage_a.py`)
- Removed the Sketchfab empties, `Icosphere`, horns, udder island and the cartoon eye decals.
- Joined the parts, welded 206 duplicated seam verts, and recovered quads (854 quads + 396 tris).
- Renamed bones (stripped the `_NN` suffixes; `GLTF_created_0_rootJoint` → `Root`) and fixed the action data paths.
- Finding: `IKFrontLeg/IKBackLeg` + `FF/FFB` are **weighted** (hooves). They are feet bones parented to Root, not helpers.

**Stage B** (`tools/calf_stage_b.py`)
- One spatial warp is applied to both mesh and rest-pose bones, so skinning and the baked clips stay valid:
  - Torso shortened (compression 0.72 between the legs), x scaled ×0.9.
  - Head ×1.22 about the head joint, widened ×1.1, muzzle shortened ×0.84, ears ×1.2.
  - Deeper throat ×1.28, flank tuck-up, legs/tail thinned radially toward their bones.
- The udder hole was filled.
- Eye sockets were widened ×1.55, and UV-sphere eyeballs were placed with planar eye UVs (0.5,0.5 = cornea).
- Smart UV project on the cage, then scale ×0.225 to meters (withers ≈1.0 m).
- LOD0 = subdiv 2 (46.8k tris), LOD1 = subdiv 1 (11.7k), LOD2 = cage (2.7k). All share UVs.
- Verified with `tools/silhouette_compare.py` against the Gemini side view. The L/H aspect went from 1.66 → 1.59 (the reference is 1.54, walking with its head lowered).
- Rig upgrade:
  - Added `Jaw` and `Ear.L/R` (children of Head). Their region weights are defined in the original cow space: the full region weight goes to the new bone and the other influences are scaled by (1-w).
  - Verified by posing: the ears rotate as a unit, and the jaw opens the chin region.
  - Lower-leg leaf tails moved onto the fetlock (the foot bone head lies on the bone line, so the rest orientation is unchanged).
  - Clips retimed ×1.25 to integer frames at 30 fps (Eating 0–180, Idle 0–100).

**Animation groundwork**
- `tools/anim_gait.py`: gait maths for walk (lateral 4-beat), trot (diagonal) and gallop (transverse, right lead), with speeds from Froude numbers at calf scale. Self-test: 0 mm planted-foot slide, exact loop continuity.
- `tools/anim_lib.py`:
  - `Calf` class: exact FK maths, `Pose` → bone basis, leg IK with auto-solved pole angles, bake-to-FK, root-motion/in-place variants, QA (IK gap, hoof ground penetration, planted slide, loop seam).
  - `gait_pose_fn`: world-space foot planner (a planted foot = home position at mid-stance), which also supports turning in place.

**Decisions**
- Keep the original 43 bones (compatibility with the existing clips), plus Jaw/Ears.
- Author at 30 fps. Unity uses a Generic rig with `Root` as the root node. Clips will ship in root-motion and in-place versions.
- `build/` is gitignored (regenerable). Deliverables go to `Unity/Calf/`.

### 2026-09-28: session 1, animation system
- The **Blender 5 headless gotcha** cost time: `pose_bone.keyframe_insert` on a new action silently writes nothing (no slot). `Calf.new_action` builds slot + layer + keyframe strip + channelbag explicitly, and `write_curves` bulk-writes the fcurves with `foreach_set`.
- **Leg reach.** The front legs are straight at rest (elbow→fetlock 0.489 m chain vs a 0.487 m drop), so an elbow-rooted IK can't place a foot forward or back. The fix has three parts:
  - A virtual scapula pivot 0.28 m above the elbow is rotated to aim the leg at the foot. The hind femur aims about the hip.
  - `Calf.reach_pass` vaults the body (height + pitch, dilated + Gaussian-smoothed, loop-aware) so planted legs always reach.
  - Swing targets are clamped to the chain reach.

  Result for Walk/Trot/Gallop RM: IK gap <0.1 mm, planted-foot slide 0 mm, loop seam 0 mm. The walk stride was shortened to 0.74 m / 24 frames (0.93 m/s) so the calf doesn't crouch.
- **Turning in place:** the world-space foot planner (planted foot = home position at mid-stance) handles a yawing root. TurnLeft90/TurnRight90 have 0 mm slide.
- **Subagent findings** (`tools/check_animation.py`, `tools/rebake_leg_ik.py`):
  - The reshape caused 1–4.6 mm hoof separation in Eating/Idle; the IK re-bake fixes it.
  - Hind legs reproduce the source best with no pole.
  - The source skinning stretches the withers about 2× when grazing. Smoothing the Torso3/Neck1/FrontShoulder weights is still open.
- **Imported clips don't key every bone.** Unkeyed bones inherit the previous clip's pose, in Blender and in Unity transitions. `complete_action` keys all missing channels at rest.
- **Unity blending.** Hooves hang off Root in the source rig, so blend trees would blend hoof positions and leg rotations separately and the hooves would detach. `reparent_hooves_for_export` re-parents the hooves under the lower legs and re-bakes (world change 0.000 mm).
- `tools/calf_animations.py` assembles everything into `build/stage_d.blend`. `tools/render_clip.py` renders root-tracking filmstrips/GIFs on a checker ground (makes sliding visible).

### 2026-09-28: fur + UV packing
- **URP shell fur** (`Unity/Calf/Fur/CalfShellFur.shader`, `CalfFur.cs`):
  - Shells are extra material instances on `Calf_LOD0`. Unity redraws the LAST submesh once per extra material, so the **exporter must put `M_Calf_Body` last**.
  - The fallback copies the body submesh to a child renderer and needs Read/Write on the model.
  - Fur is LOD0 only; shells cast no shadows.
- `tools/calf_fur_textures.py` writes `T_Calf_FurMask` (R = length: 0 on the nose, hooves and eyes; 0.35 coat; up to 1.0 on the forehead tuft and tail switch; 16 px island padding) and a tileable `T_Fur_Noise`.
- **UV packing:** stage B now runs `uv.pack_islands(shape_method=CONCAVE)` after smart project. UV coverage went 44% → 63% (≈1.4× texel density).

### 2026-09-28: clip family `idle_graze` (Idle_LookAround, Graze_Start/Loop/End, Call)
**What:** `tools/clips/idle_graze.py` (picked up by `tools/calf_animations.py`; `build(calf)` returns the 5 names).
| Clip | Frames | Content |
|---|---|---|
| `Idle_LookAround` | loop 150 | Pose() → look left → centre → look right → Pose(); head leads neck by 5 f, weight shift/body yaw lag 7 f; ears prick toward the look + independent flicks (L f30, R f88, L f124); tail swish f58–100; 3 breaths |
| `Graze_Start` | 42 | Pose() → GRAZE; neck leads, head extension lags; front end dips; left fore steps 6 cm forward (f12–27, as in the GiM grazing footage) |
| `Graze_Loop` | loop 120 | GRAZE; 3 × (bite dip + jaw grab → tear jerk → 2 chews) with left/right muzzle sweeps (~9 cm) between bites; ear flicks, tail swish, 2 breaths |
| `Graze_End` | 40 | GRAZE → Pose(); muzzle leads up, chews while rising, left fore steps back (f13–27), ears prick |
| `Call` | 72 | Pose() → inhale/head dip → neck stretches forward and a little up, head extends, jaw ≥85 % open f22–43 (0.7 s, slight vibrato), ears back, tail lifts → Pose() |

**How:** shared constant poses `stand_pose()` (= Pose()) and `graze_pose()`; per-channel monotone-cubic key curves (`Curve`, no overshoot) plus `group_blend` (a separate blend weight per body part = overlapping action) plus overlays (breathing, ear flicks, tail waves, foot step). Boundary frames return the shared poses verbatim, and the QA prints how far the raw curves are from them there (0). The standalone `__main__` prints `calf.qa`, a Calf_LOD2 mesh ground check (non-hoof / hoof per leg / nose pad / head), signed carpus/hock bend, a pop check (2nd difference of every bone, wrapped for loops) and boundary/seam diffs, then renders strips + GIFs.

**Gotchas found (useful for every family):**
- **Pose() already clamps the front hooves ~2 mm up.** The straight front legs are asked 3 mm more than 0.99 × chain at rest (the `pose_to_basis` clamp is 0.992): front fetlock z 90.6 mm vs 88.6 mm rest. With a `stance_fn`, `reach_pass` lowers the body on standing frames (dilated/smoothed over ±5 f), so the shared Pose() boundary frames would differ between clips. This family therefore passes no `stance_fn` and never raises the elbows (body z ≤ 0, no nose-up pitch).
- **Carpus sensitivity:** the front legs are nearly straight (15° carpus bend at rest). Each 1 cm the elbow drops costs about 15° more carpus flexion. Lower the "front end" with `Torso3` (withers/neck only) and a small body pitch, not with body z.
- **`Torso`/`Torso2` pitch moves the front legs** (`FrontShoulder.*` are children of `Torso2`). A −0.8° Torso pitch lifted the front hooves 7 mm. Keep Torso : Torso2 ≈ 1 : −1.67 so the elbow height is unchanged.
- **Hoof flex near the ground pushes the toe INTO the ground first:** the hoof chain hangs ~22° off vertical, so small flex swings the tip down (up to 9 mm). Tie flex to lift height (flex ∝ h²).
- Calf_LOD2 hoof vertices sit at z −1.3 cm at rest; judge hoof contact relative to each leg's rest minimum. The non-hoof minimum (1.45 cm) is the pastern skin.
- `Pose.ears`: x + = tip forward, y + = tip down, z = twist (verified by render). `Pose.head` roll + = left ear down (the opposite of body roll).
- The nose pad (`orig_part` 3) is the lowest head point when grazing. GRAZE nose ≈ 4 cm up, ~40 cm ahead of the front hooves.

**QA** (`python3 tools/clips/idle_graze.py`, build/stage_b.blend):
| Clip | IK gap | Planted slide | Planted hoof vs rest | Nose pad z | Carpus bend | Pops (non-ear/leg) |
|---|---|---|---|---|---|---|
| Idle_LookAround | 0.00 mm | 0.05 mm | ≤2.1 mm (= Pose() clamp) | 52.9–66.4 cm | 15.1–17.5° | 0.29°/f² |
| Graze_Start | 0.02 | 0.01 | ≤2.1 | 3.05–58.3 | 15.1–58.5° (swing leg) | 0.26 |
| Graze_Loop | 0.00 | 0.00 | 0.0 | 3.27–6.23 | 16.5–26.8° | 3.67 (tear jerk, intended) |
| Graze_End | 0.02 | 0.08 | ≤2.1 | 3.98–63.3 | 15.1–56.8° | 0.57 |
| Call | 0.00 | 0.01 | ≤2.1 | 50.2–76.1 | 15.1–17.6° | 1.43 |
- Hock bend stays 51.5–54.8°. The knees always bend in the anatomical direction. Nothing goes below its rest height (non-hoof min z 1.45 cm = rest).
- Both loop seams, and every Pose()/GRAZE boundary (Start end = Loop start, Loop end = End start, Pose() at the standing ends), are 0.0000 mm / 0.0000°.
- Tail swish clearance to the rump/thigh verts is ≥3.5 cm.
- Fetlock "loop seam" 60 mm on Graze_Start/End is expected (not loops; the left fore moves 6 cm).

**Open:**
- The source skinning bulges the withers when the neck pitches hard: the neck bend is spread over Torso3 + Neck1–3 to limit it; weight smoothing is still open.
- The jaw is a single hinge, so there is no lateral chewing.
- There are no eyelids, so there are no blinks.

### 2026-09-28: lying clip family (LieDown / Lying_Idle / GetUp)
- `tools/clips/lying.py` builds `LieDown` (120 f), `Lying_Idle` (150 f loop) and `GetUp` (120 f), with no root motion.
  - Lying down is front end first: left carpus, then right carpus, then the hindquarters sink onto the right hip.
  - Getting up is hind end first: rump up on the knees, then the left fore, then the right.
  - `LYING` is sternal recumbency, both fore legs folded, pelvis rolled onto the right hip, hind legs folded to the left.
- New techniques in the module:
  - per-foot Hermite tracks with true zero-tangent stops, so planted hooves hold exactly;
  - a per-frame "knee lock" that solves body z/roll so a kneeling carpus stays on its ground point;
  - a Calf_LOD2 mesh ground check, a pop detector, and exact seam checks between the clips.
- QA:
  - IK gap ≤0.05 mm; planted hoof slide ≤0.01 mm; locked carpus drift ≤7 mm;
  - mesh non-hoof min z ≥ -1.1 cm; clip seams 0.000 mm.
- Rig findings are in `docs/anim_lying.md`:
  - body roll tilts the front IK planes (the poles are children of Body);
  - spine roll sign is opposite to body roll;
  - ear axes;
  - the library's reach clamp makes `Pose()` differ from the armature rest by 9 mm / 3° in the fore legs.

### 2026-09-28: texture + export agents finished
- **Textures** (`tools/calf_textures.py`):
  - Rest-position, normal and part maps are baked in Cycles. The coat is a numpy procedural anchored to rig and mesh landmarks: white shoulder band, brisket, belly, hip band, lower legs, tail and forehead blaze; orange barrel, rump, neck and head; pale muzzle with nostrils.
  - Fur-strand height is baked into a tangent-space normal (MikkTSpace, OpenGL). UV islands have unlimited padding.
  - Output is deterministic. A 2048 run takes about 70 s; the 4096 run is estimated at 4–5 min and 3–4 GB.
  - Hoof colour changed to pale horn (HD reference frames) after the run.
- **Export** (`tools/export_unity.py`, `tools/validate_export.py`):
  - Takes are exported through **NLA strips, one per action**. Blender 5's "All Actions" mode names takes `CalfRig|X` and leaked 198 mm of pose between takes in a test.
  - The exporter pre-rotates the rig rest so `CalfRig` has identity rotation in Unity (the FBX apply-transform option doesn't cover armatures). The unweighted PoleTarget helpers are dropped.
  - **Subdivided LODs carry up to 7–8 influences.** The exporter refits over-limit vertices to their best 4 bones against poses sampled from all clips. The worst case drops from 41 → 23.5 mm vs Blender (Gallop, brisket midline). Open item: limit and refit the weights in stage B so Blender previews equal Unity.
  - The body submesh is exported last (the fur needs this).
  - The validator reads the FBX/GLB directly with FBX/glTF transform maths (0.001 mm vs source), re-imports both, runs Khronos gltf-validator (npm, in build/node_tools) and renders comparisons.
- **Follow-ups done:**
  - Hoof soles lifted onto z=0 in stage B (the source sank them 4.5 mm front / 12 mm hind).
  - `CalfSetup.cs` now sets `optimizeBones=false` (Strip Bones would remove the unweighted `Root` motion node) and `importTangents=Import`.
