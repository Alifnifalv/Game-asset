# Lying clip family (LieDown / Lying_Idle / GetUp): handoff notes

Module: `tools/clips/lying.py` (loaded by `tools/calf_animations.py` like every `tools/clips/*.py` family).
Standalone test: `python3 tools/clips/lying.py [--render none|all] [--step 4] [--scratch DIR]` builds the three clips on
`build/stage_b.blend`, prints QA, saves `<scratch>/test.blend` and renders `<scratch>/<Clip>_{left,threequarter}.{png,gif}`.

## Clips
| Clip | Frames (30 fps) | Content |
|---|---|---|
| `LieDown` | 0-120, one-shot | `Pose()` -> sniff -> left carpus down (f35) -> right carpus down (f45) -> kneel -> hindquarters sink down/back onto the right hip (f54-84) -> chest settles (f96) -> head up -> `LYING` |
| `Lying_Idle` | 0-150, loop | `LYING` + 3 breaths, 8 cud chews (jaw, pause while listening), look left / down / right, ear flicks, one tail flick |
| `GetUp` | 0-120, one-shot | `LYING` -> gather hind legs under -> lunge on the knees, rump up first (f22-44) -> kneel -> left fore steps onto its hoof (f52-68) -> right fore (f70-87) -> rise, weight shift -> `Pose()` |

No root motion (Root stays at the origin). All three share `lying(calf)` / `stand()`; the seams are exact (0.000 mm):
LieDown end = Lying_Idle start/end = GetUp start, and LieDown start / GetUp end equal a `make_clip(Pose())` frame.

## How it works (read before changing it)
- **Per-leg foot tracks** (`clip_fn` + `hermite`): body/head/tail use whole-pose cubic Hermite keys; each foot has its
  own Hermite track. `"stop"` keys have zero tangents, so a foot between two equal stop keys is held exactly
  (planted-hoof slide is 0.01 mm). `anim_lib.keyed_pose_fn` "hold" is *not* a zero tangent: its Catmull-Rom dips on plateaus.
- **Knee lock**: kneeling carpi rest on fixed ground points `knee_points(calf)`, derived from the lying body (the carpus is
  a forearm length ahead of the elbow). While a leg is in its lock interval the fetlock target comes from the contact
  (cannon lying back, hoof flex 115 deg) and body z (+ roll when both knees are down) is solved per frame so
  |elbow - contact| = forearm length. Keys at lock start/end frames are solved to satisfy the lock, so it never pops.
- **Key poses** are built with `solve_body` (Gauss-Newton on body DOFs) from targets such as the knee distance, the elbow
  position relative to the knee, and the hip height.

## Rig facts learnt here (apply to other families too)
- The front IK poles are children of `Body`, in front of and below the elbow. **Body roll tilts the front IK planes** and
  drags a kneeling carpus sideways (it was 5-6 cm with 10 deg of roll). Keep `body_rot` roll at 0 whenever a front knee
  bears weight; the "lying on one hip" look comes from the `Back` (pelvis) roll -14 deg with a `Torso` counter-roll.
- For the same reason a fore leg stretched **forward** can only bend its carpus downward mid-transition, into the ground.
  The GiM reference lies with the upper fore leg stretched out. Here both fore legs stay folded, the standard cattle posture.
- Spine roll sign is opposite to `body_rot` roll: spine roll + = LEFT side down (`body_rot` roll + = right side down).
- Ears `Vector(a, b, c)`: a + = forward / - = back; b + = droop down / - = up; c - = opening turns forward (verified by renders).
- The library clamps foot targets at 0.992 x chain length, which is shorter than the fore legs' rest reach. A `Pose()` clip
  therefore differs from the armature rest by 9 mm / 3 deg in the fore legs. Every clip shares this, so chaining is exact.
- Rest-pose hoof mesh baseline (Calf_LOD2): front hooves -0.2 cm, hind hooves -1.3 cm below z=0.
- `render_clip.py` renders are plain white. For reading legs, a debug material colouring the mesh by dominant deform bone
  (vertex groups) helps a lot; the scratch renderer that did this was not committed.

## QA at the time of writing (`python3 tools/clips/lying.py --render none`)
| Check | LieDown | Lying_Idle | GetUp |
|---|---|---|---|
| IK gap (anim_lib qa) | 0.05 mm | 0.01 mm | 0.05 mm |
| Planted hoof slide | 0.01 mm | 0.00 mm | 0.01 mm |
| Locked carpus slide (xy) / height | 7.1 mm / 3.9-4.0 cm | 1.0 mm / 4.0 cm | 3.1 mm / 3.9-4.0 cm |
| Mesh non-hoof min z (LOD2) | -1.1 cm | -0.9 cm | -1.1 cm |
| Planted hoof-vertex min z | -1.3 .. -0.2 cm | -0.9 .. +0.8 cm | -1.3 .. 0.0 cm |
| Max bone accel / speed | 17 mm/f^2 / 51 mm/f | 29 (ear flick) / 46 | 35 / 66 (fore-leg steps) |

The anim_lib "fetlock loop seam" number (185 mm) is meaningless for the one-shot clips. It compares the first and last frames.

## Known limitations / ideas
- The 7 mm carpus drift in LieDown is lateral and spread over about 2 s. It comes from the pelvis roll / Torso counter-roll
  pivot offset.
- In GetUp the left fore is planted at its rest spot while the chest is still low, so its carpus is strongly bent forward
  for about 0.5 s. Planting further forward would need a corrective step back at the end, because the clip must end at `Pose()`.
- The tail rests on the ground by hanging with a tip curl (`LYING_TAIL`). It does not curl around the body as a real calf's often does.
- The clips were checked on `build/stage_b.blend`. `calf_animations.py` re-parents the hooves for export after all
  families are built; this family does not depend on that.
