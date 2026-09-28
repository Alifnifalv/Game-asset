# Work log: calf asset

Newest status first, then a chronological log. Each entry: what, why, how it was verified, open issues.

## Current status (update on every milestone)
| Area | State | Where |
|---|---|---|
| Geometry (calf reshape, eyes, UVs, LODs) | Done, tuned against the side-view silhouette | `tools/calf_stage_a.py`, `tools/calf_stage_b.py` |
| Rig upgrade | Jaw + Ear.L/R done; lower-leg tails fixed; 30 fps | `tools/calf_stage_b.py` |
| Coat textures | In progress (subagent) | `tools/calf_textures.py` |
| Existing clips on the reshaped rig (Eating/Idle) | Done: leg IK re-solved (0 mm hoof gap; Idle front.R 2.3 mm unreachable in the source too) | `tools/check_animation.py`, `tools/rebake_leg_ik.py` |
| Unity export + validator | Queued (subagent) | `tools/export_unity.py`, `tools/validate_export.py` |
| New animation set | Gaits done: Walk/Trot/Gallop (RM + in place), TurnLeft90/Right90. Key-pose families in progress | `tools/calf_animations.py`, `tools/anim_lib.py`, `tools/anim_gait.py`, `tools/clips/` |
| Export rig | Hooves re-parented under the lower legs for engine blending (world motion unchanged, 0.000 mm) | `anim_lib.reparent_hooves_for_export` |
| Fur, Unity setup script | Not started | see `docs/PLAN.md` |

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
