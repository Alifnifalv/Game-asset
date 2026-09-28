# Lying clip family (LieDown / Lying_Idle / GetUp): handoff notes

Module: `tools/clips/lying.py` (loaded by `tools/calf_animations.py` like every `tools/clips/*.py` family; `build(calf)`
returns `['LieDown', 'Lying_Idle', 'GetUp']`).
Standalone test: `python3 tools/clips/lying.py [--render none|all] [--step 4] [--scratch DIR] [--no-inside]` builds the
three clips on `build/stage_b.blend` (~3 s), prints QA, saves `<scratch>/test.blend` and renders
`<scratch>/<Clip>_{left,threequarter}.{png,gif}` (~10 min with renders on the shared 4-core CPU).

History: first version 9dd402a; adversarial review e8bc810 (3 major, 2 minor); this rework fixes all five findings
(see "Review findings" below). The module was largely rewritten; the framework (Hermite body/foot tracks, knee lock,
`solve_body`) is kept.

## Clips (30 fps, no root motion: Root stays at the origin)
| Clip | Frames | Content |
|---|---|---|
| `LieDown` | 0-150, one-shot | `Pose()` -> sniff (f14) -> rock back (f24, stop) -> left fore rolls onto its toe, lifts (f19) and folds; chest drops onto the left carpus (f34) while the loaded right fore rolls onto its toe -> right fore lifts (f36) and its carpus goes down (f48) -> kneel, head low (f56) -> hindquarters sink onto the right hip, hocks back and down, hind hooves planted (f56-84) -> hind hooves lifted into the lying spots (f85-98), chest settles (f98) -> left fore stretched forward (f102-122), right fore (f112-132) -> head up -> `LYING` (f150) |
| `Lying_Idle` | 0-150, loop | `LYING` + 3 breaths, 8 cud chews (jaw, pause while listening), look left / down / right, ear flicks, one tail flick (unchanged overlays) |
| `GetUp` | 0-150, one-shot | `LYING` -> head up -> left fore folded back under onto its knee (f4-22), right (f10-28) -> hind hooves lifted and gathered beside/behind the belly, pelvis unrolls, rump starts rising (f26-40) -> lunge forward on the knees, rump up (f40-62) -> each hind hoof steps forward under the hips (f56-70) -> roll onto the right knee, left fore steps forward and plants toe first at its rest spot (f70-84), heel down by f104 -> push (f92) -> right fore steps, toe first (f92-106), heel down by f120 -> rise (f110), up (f126), settle -> `Pose()` (f150) |

Shared poses: `stand()` (== `Pose()`), `lying(calf)` (LYING), `lying_folded(calf)` (lying body, fore legs folded under).
Seams are exact (0.000 mm / 0.000 deg): LieDown end = Lying_Idle start/end = GetUp start; LieDown start and GetUp end
equal a `make_clip(Pose())` frame.

`LYING` = sternal recumbency: the chest upright on the sternum, **both fore legs stretched forward on the ground** (the
right hoof tucked in under the chin, as in the GiM reference 28-40 s), the pelvis rolled onto the right hip (`Back`
roll -14 deg with a `Torso` counter-roll), hind legs folded to the left (left hind on top), tail hanging with a tip
curl. The lying body is `LY_B` = 0.40 m behind the standing body.

## How it works (read before changing it)
- **Poles are keyed per frame** (`make_clip_ex` = anim_lib `make_clip` without the reach pass plus pole keys; the
  `PoleTarget*` bones are unweighted helpers that `export_unity.py` drops). The library leaves the poles on `Body`, which
  flips the carpus the wrong way on a fore leg stretched forward and flips the hock on a deeply folded hind leg.
  - free fore leg: the rest pole offset is rotated about the elbow by the leg's sagittal swing (`anterior_pole`), so the
    carpus always flexes anatomically;
  - kneeling fore leg: the pole lies in the plane (elbow, fetlock, knee contact) (`knee_pole`), so the carpus lands exactly on
    its contact whatever the body roll (the old limitation "no body roll while a knee is down" is gone);
  - hind leg: the rest pole offset is rotated about the stifle with the stifle->fetlock line (`hind_pole`).
  - At `Pose()` all poles sit at their rest position, so standing frames equal `make_clip(Pose())`.
- **`leg_state(calf, P)`** predicts the baked IK analytically with the same poles (knees within 0.03 mm and hocks
  within 1.2 mm of Blender's bake). It returns the joint positions and angles (fore carpus/fetlock, hind stifle/hock/
  fetlock, about the side axis, 0 = straight). Key poses are solved against it with `solve_body` (Gauss-Newton on body
  DOFs and `femur:<leg>`):
  - `knee_res`: elbow a forearm length from its knee contact;
  - `shell_res`: loaded elbow at `D_STAND` x chain from its hoof, so the carpus stays near its rest bend;
  - `fetlock_res`: loaded fore fetlock angle;
  - `hip_z_res`, `elbow_ahead_res`;
  - `solve_femur`: hock height;
  - `fit_femur`: smallest femur change inside the hind joint limits.
- **Per-leg foot tracks** (`clip_fn` + `hermite`): body/head/tail are whole-pose cubic Hermite keys and each foot is its
  own Hermite track of (fetlock offset, flex). `"stop"` keys have zero tangents, so a foot between two equal stops is
  held exactly.
- **Hoof pivots** (`pivots = {leg: [(a, b, "toe"|"heel", world point[, loaded])]}`): within [a, b] the fetlock follows
  from a fixed toe/heel contact and the track's flex (`foot_on_pivot`, `hoof_offset`: pastern turns by flex, the toe bone by
  1.35 x flex). A loaded hoof that must tilt rolls onto its toe instead of hyperextending the fetlock. `loaded=False`
  marks an unloading heel-lift (the reach guard ignores it).
- **Knee lock** (`lock`): kneeling carpi rest on fixed ground points `knee_points(calf)`, derived from the lying body. The
  carpus lies a forearm length ahead of the lying elbow, about 11 cm behind the standing fore hooves. Per frame, body
  z (+ roll for two knees) is solved so each elbow stays a forearm length from its contact. Keys at lock start/end
  frames satisfy it; touchdown keys are "stop" keys, so the chest decelerates into the contact without rebounding.
- **Reach guard** (`reach_guard`, in `clip_fn` for loaded fore legs): if the keys ever ask a loaded fore leg for more
  reach than its cap, body z is lowered to a C1 soft limit. Otherwise the library clamps the foot target toward the elbow
  (0.992 x chain) and the planted hoof lifts or slides. `guard_cap` eases the cap from the rest reach to the
  unclamped `D_STAND` over LieDown's sniff. Treat it as a safety net: fix keys that trip it (a keyed bulge clamped by it
  is a velocity kink).

## Rig facts learnt here (apply to other families too)
- The fore leg geometry makes a loaded carpus buckle fast: forearm 0.312 m, cannon 0.178 m. The rest elbow-fetlock
  distance is 0.996 x chain; 25 deg of carpus bend is reached with about 1 cm of elbow drop, and a 5 cm drop over a
  flat hoof already gives fetlock -58 deg. A chest that goes down must either keep the hoof ahead of the elbow or roll
  the hoof onto its toe.
- anim_lib clamps a foot target at 0.992 x chain, and the fore legs' rest reach is 0.996, so every `Pose()` frame holds
  the fore hooves about 2 mm above their true contact. When a loaded leg comes closer than 0.992, the hoof settles those
  2 mm. Make that happen gradually (LieDown does it over the sniff).
- `anim_lib.blend_pose` returns a fresh `Pose()` with `auto_top=True`. Reset it (`auto_top = False`) when blending
  poses of an auto_top-off family, or the scapula/femur auto-aim switches on for that key.
- Spine roll sign is opposite to `body_rot` roll: spine roll + = LEFT side down (`body_rot` roll + = right side down).
- Ears `Vector(a, b, c)`: a + = forward / - = back; b + = droop down / - = up; c - = opening turns forward.
- Hoof sole contact points (rest armature space): front toe y -0.405, heel -0.352; hind toe 0.364, heel 0.424.
- The front `FrontUpperLeg` weights cover a 16 x 27 cm block of the brisket, so a fully folded cannon (carpus 156 deg)
  disappears inside the forearm. Folded fore legs are fine in transitions, but a held pose should stretch them.

## QA (`python3 tools/clips/lying.py --render none`, build/stage_b.blend of 2026-09-28 13:13)
| Check | LieDown | Lying_Idle | GetUp |
|---|---|---|---|
| IK gap / planted fetlock slide | 0.05 / 0.01 mm | 0.00 / 0.00 mm | 0.04 / 0.04 mm |
| Locked carpus slide | 0.04 mm | - | 0.03 mm |
| Loaded hoof pivot drift (toe) | 0.00 mm | - | 0.00 mm |
| Loaded fore fetlock min (limit -65; rest -31) | -51.9 | -15.1 | -61.3 |
| Standing loaded carpus max (limit 25; rest 15) | 23.9 (lift-off) | - | 15.1 |
| Stifle bend max (limit 140; rest 60) | 135.5 | 134.0 | 134.0 |
| Hock bend min (limit -150; rest -52) | -145.7 | -145.7 | -145.8 |
| LOD2 non-hoof min z | -0.5 cm | -0.8 cm | -0.5 cm |
| Swinging hoof min z (vs rest baseline) | -0.1 cm | - | -0.4 cm |
| Max bone accel all / trunk+head (mm/f^2) | 30 / 12 | 29 (ear flick) / 2.6 | 34 / 9 |
| Fore cannons/hooves inside the skin in LYING (LOD1) | - | 0% | - |

## Review findings (e8bc810) and how they were fixed
1. **Loaded fore fetlock hyperextension** (-117/-124 deg). The lying body now lies 0.40 m back, so the knees land about
   11 cm behind the hooves. When lying down, the calf rocks back, so the loaded right fore stays ahead of its elbow; it
   rolls onto its toe (flex 9 deg), giving fetlock -52. When getting up, each fore hoof is planted toe first, ahead
   of the kneeling elbow, with the body rolled onto the other knee; the heel lowers as the body rises. The rise/up keys
   are solved on the fetlock and carpus (-61 worst). During the sniff the elbows keep their standing distance
   (carpus 17 deg).
2. **Stifle hyperflexion** (163-166 deg). The hocks travel back and down to the ground while the rump sinks, via femur
   swings solved per key; the rump lands with the metatarsus near horizontal. In GetUp the hind hooves are gathered beside
   and behind the belly, lift the rump there, then step forward under the hips. Stifle is 134-136 max. The right
   thigh/gaskin inside the trunk (LOD1) is 9% at LieDown f84 (was 41%) and 15% at GetUp f18 (was 49%, now the same as
   the LYING baseline).
3. **Fore cannons inside the brisket in LYING** (56-64%). LYING stretches both fore legs forward (0% inside). The
   new poles let a forward leg bend its knee upward (anatomical), which was the author's reason for keeping them folded.
4. **Chest rebound at the knee touchdown.** Touchdown keys are "stop" keys and the rock-back is a stop, so the chest
   eases into the contact (Torso3 vz -4.9, -0.2, -0.5 mm/f over f34-36; no reversal).
5. **Hind hooves dragged.** Every hind repositioning is a lifted swing (LOD0 min z +0.2 to +9.6 mm while moving, was
   -7.6 mm). In the lying spots the hind fetlocks are 5 mm higher (LOD0 hoof about 0 mm, was -5 mm).

## Known limitations / ideas
- The lying calf lies 0.40 m behind its standing position (no root motion). Real cattle end up about there, and rise
  forward again, but in Unity the collider/capsule may need an offset while lying. Alternative: root motion on
  LieDown/GetUp.
- The GetUp left-fore plant is the tightest joint: fetlock -61 deg around f98 (limit -65), and carpus about 100 deg
  while the chest is still low.
- The hind swings lift only 1-2 cm at mid-move. More lift folds the hock past its limit while the rump is on the ground.
- Folded fore legs still hide their cannons inside the forearm/brisket in the transition frames (LieDown f98-112, GetUp
  f22-70), where cattle really do fold them.
- The tail rests by hanging with its tip curled on the ground (`LYING_TAIL`); it does not wrap around the body.
- The anim_lib qa "fetlock loop seam" (182 mm) is meaningless for the one-shot clips.
- Clips were checked on `build/stage_b.blend` only, before `calf_animations.py` re-parents the hooves for export.
