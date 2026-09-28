# Lying clip family (LieDown / Lying_Idle / GetUp): handoff notes

Module: `tools/clips/lying.py` (loaded by `tools/calf_animations.py` like every `tools/clips/*.py` family; `build(calf)`
returns `['LieDown', 'Lying_Idle', 'GetUp']`).
Standalone test: `python3 tools/clips/lying.py [--render none|all] [--step 4] [--scratch DIR] [--no-inside]` builds the
three clips on `build/stage_b.blend` (~3 s), prints QA, saves `<scratch>/test.blend` and renders
`<scratch>/<Clip>_{left,threequarter}.{png,gif}` (~10 min with renders on the shared 4-core CPU).
Always pass both flags for a QA run: `--render none` (the default is `all`, ~10 min) and `--scratch <your scratch dir>`
(the default is a hard-coded path from the session that wrote the module): `python3 tools/clips/lying.py --render none
--scratch <scratch>/lying` (~5 s).

History: first version 9dd402a; adversarial review e8bc810 (3 major, 2 minor); this rework fixes all five findings
(see "Review findings" below). The module was largely rewritten; the framework (Hermite body/foot tracks, knee lock,
`solve_body`) is kept. Final multi-lens review (after checkpoint 01): the LYING head is held up (L5) and the head keys
around it were retuned for the smaller stage-B head (see "Final review retune" below).

## Clips (30 fps, no root motion: Root stays at the origin)
| Clip | Frames | Content |
|---|---|---|
| `LieDown` | 0-150, one-shot | `Pose()` -> sniff (f14) -> rock back (f24, stop) -> left fore rolls onto its toe, lifts (f19) and folds; chest drops onto the left carpus (f34) while the loaded right fore rolls onto its toe -> right fore lifts (f36) and its carpus goes down (f48) -> kneel, sniff: muzzle ~4 cm above the ground (f56) -> hindquarters sink onto the right hip, hocks back and down, hind hooves planted (f56-84) -> hind hooves lifted into the lying spots (f85-98), chest settles (f98) -> left fore stretched forward (f102-122), right fore (f112-132) -> head comes up (f114-150) -> `LYING` (f150) |
| `Lying_Idle` | 0-150, loop | `LYING` + 3 breaths, 8 cud chews (jaw, pause while listening), look left / down / right, ear flicks, one tail flick (unchanged overlays) |
| `GetUp` | 0-150, one-shot | `LYING` -> head up a little more (f8) -> left fore folded back under onto its knee (f4-22), right (f10-28) -> hind hooves lifted and gathered beside/behind the belly, pelvis unrolls, rump starts rising (f26-40) -> lunge forward on the knees, rump up (f40-62) -> each hind hoof steps forward under the hips (f56-70) -> roll onto the right knee, left fore steps forward and plants toe first at its rest spot (f70-84), heel down by f104 -> push (f92) -> right fore steps, toe first (f92-106), heel down by f120 -> rise (f110), up (f126), settle -> `Pose()` (f150) |

Shared poses: `stand()` (== `Pose()`), `lying(calf)` (LYING), `lying_folded(calf)` (lying body, fore legs folded under).
Seams are exact (0.000 mm / 0.000 deg): LieDown end = Lying_Idle start/end = GetUp start; LieDown start and GetUp end
equal a `make_clip(Pose())` frame.

`Death_Lying` (in `tools/clips/actions.py`, not this module) also starts from `lying(calf)` with this family's pole rule
(frame 0 = Lying_Idle f0 exactly), and its end hind feet are placed relative to LYING's. A change to LYING therefore
changes Death_Lying: re-run the actions QA (BOUNDARY, OVERLAP). Its first 'agonal gasp' keys are absolute, so since the
L5 head raise the head drops from f0 (41 -> 30 cm by f5) instead of lifting first (WORKLOG OI-35).

`LYING` = sternal recumbency: the chest upright on the sternum, **both fore legs stretched forward on the ground** (the
right hoof tucked in under the chin, as in the GiM reference 28-40 s), the pelvis rolled onto the right hip (`Back`
roll -14 deg with a `Torso` counter-roll), hind legs folded to the left (left hind on top), tail hanging with a tip
curl, and the **head held up** level with / above the back as in GiM (neck -9/-10/-9 deg, head pitch 18 deg: Head
bone midpoint z 0.557 m, back top 0.58 m, poll/ears up to 0.75 m). The lying body is `LY_B` = 0.40 m behind the standing body.

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
  (0.9985 x chain since c4fbcaa; 0.992 when this family was written) and the planted hoof lifts or slides. `guard_cap`
  eases the cap from the rest reach to the unclamped `D_STAND` over LieDown's sniff. Treat it as a safety net: fix keys
  that trip it (a keyed bulge clamped by it is a velocity kink).

## Rig facts learnt here (apply to other families too)
- The fore leg geometry makes a loaded carpus buckle fast: forearm 0.312 m, cannon 0.178 m. The rest elbow-fetlock
  distance is 0.996 x chain; 25 deg of carpus bend is reached with about 1 cm of elbow drop, and a 5 cm drop over a
  flat hoof already gives fetlock -58 deg. A chest that goes down must either keep the hoof ahead of the elbow or roll
  the hoof onto its toe.
- anim_lib clamps a foot target at **0.9985 x chain** (since c4fbcaa; it was 0.992) and its body-vault pass acts above
  0.997 x chain. The fore legs rest at 0.996 x chain, so a `Pose()` frame **equals the rest pose**: the fore hooves sit
  on their true contact and the rest carpus bend is **10.4 deg** (it was 15 deg, with the hooves held ~2 mm up). A
  planted fore leg has little slack: its elbow can rise only ~0.5 mm before `reach_pass` (with a `stance_fn`) lowers
  the body, and ~1.2 mm before the clamp lifts the hoof. So standing clips still must not raise the elbows while the
  fore hooves are planted. The old advice to let a loaded hoof "settle the 2 mm" gradually no longer applies (the
  LieDown sniff still eases `guard_cap` from the rest reach to `D_STAND`, which is harmless).
- `anim_lib.blend_pose` returns a fresh `Pose()` with `auto_top=True`. Reset it (`auto_top = False`) when blending
  poses of an auto_top-off family, or the scapula/femur auto-aim switches on for that key.
- Spine roll sign is opposite to `body_rot` roll: spine roll + = LEFT side down (`body_rot` roll + = right side down).
- Ears `Vector(a, b, c)`: a + = forward / - = back; b + = droop down / - = up; c - = opening turns forward.
- Hoof sole contact points (rest armature space): front toe y -0.405, heel -0.352; hind toe 0.364, heel 0.424.
- The front `FrontUpperLeg` weights cover a 16 x 27 cm block of the brisket, so a fully folded cannon (carpus 156 deg)
  disappears inside the forearm. Folded fore legs are fine in transitions, but a held pose should stretch them.

## QA (`python3 tools/clips/lying.py --render none --scratch <scratch>`, final-review stage B: measured on build/stage_b.blend of 2026-09-28 17:46 after the L5 retune; the lines it prints are identical on the rebuilt stage B of 18:16)
| Check | LieDown | Lying_Idle | GetUp |
|---|---|---|---|
| IK gap / planted fetlock slide | 0.05 / 0.00 mm | 0.00 / 0.00 mm | 0.04 / 0.00 mm |
| Locked carpus slide | 0.04 mm | - | 0.03 mm |
| Loaded hoof pivot drift (toe) | 0.00 mm | - | 0.00 mm |
| Loaded fore fetlock min (limit -65; rest -31) | -51.9 | -15.1 | -61.3 |
| Standing loaded carpus max (limit 25; rest 10.4) | 23.9 (lift-off) | - | 10.6 |
| Stifle bend max (limit 140; rest 60) | 135.5 | 134.0 | 134.0 |
| Hock bend min (limit -150; rest -52) | -145.7 | -145.7 | -145.8 |
| `actions.joint_bends` carpus / hock min (must stay > 0) | 10.4 / 52.4 | 21.1 / 128.7 | 9.7 / 49.0 |
| LOD2 non-hoof min z (trunk) | -0.7 cm | -0.9 cm | -0.7 cm |
| LOD2 head-region min z | +3.9 cm (f56 sniff) | +19.8 cm | +13.7 cm (f54 lunge) |
| Head bone midpoint z | 0.209 m (f56) .. 0.557 m (f150) | 0.503 .. 0.576 m (0.557 at the seam) | 0.557 m (f0) .. 0.890 m |
| Swinging hoof min z (vs rest baseline) | -0.1 cm | - | -0.3 cm |
| Max bone accel all / trunk+head (mm/f^2) | 30 / 12 | 26 (ear flick) / 2.5 | 34 / 9 |
| Fore cannons/hooves inside the skin in LYING (LOD1) | - | 0% | - |

Seams (all 0.000 mm / 0.000 deg): LieDown end -> Lying_Idle start, Lying_Idle loop, Lying_Idle end -> GetUp start,
LieDown start and GetUp end vs a `make_clip(Pose())` frame. `JOINT limits: all OK`.

## Final review retune (L5 and the smaller head)
The final review made the stage-B head smaller (head_scale 1.22 -> 0.97, neck_deepen 1.28 -> 1.10) and asked (L5) for
the lying head to be held up like GiM's instead of hanging low. The rest bones did not move (the Head bone midpoint is
the same on both geometries), only the mesh did, so the same keys now leave the muzzle about 7 cm higher.
| Key (function, frame) | Before | After | Why |
|---|---|---|---|
| `lying()` LYING (LieDown f150, Lying_Idle, GetUp f0) | neck 0/1/1, head pitch 6 | neck -9/-10/-9, head pitch 18 | L5: head up level with / above the back |
| `lie_down` `kn_low` (f56, kneeling sniff, stop) | neck 6/8/6, head pitch 10 | neck 11/12/11, head pitch 14 | the muzzle reaches ~4 cm again |
| `lie_down` `kn_key` (f48, right carpus lands, stop) | `kn`: neck 0/2/2, head (6, 0, 0) | neck 5/7/6, head (9, -1, 1) | the head is already on its way down, so the dip into the sniff is no faster than before |
| `lie_down` `ly_turn` (f134) | neck 2/3/2, head pitch 7 | neck -3/-3/-3, head pitch 11 | the head comes up over f112-150 (peak 14.8 mm/f), not all in the last 16 frames (23.3 mm/f) |
| `get_up` `prep` (f8) | neck -4/-4/-2, head pitch 0 | neck -11/-12/-10, head pitch 12 | keeps the "head up" beat; the old values would lower the head from the new LYING |

Bone-based rows (Head midpoint, speeds, accelerations) are identical on both geometries for the same keys (the rest
bones did not change); the mesh rows (LOD2 head region) are not.
| Measurement | Checkpoint 01 (old head, old keys) | New stage B, old keys | New stage B, L5 LYING only | New stage B, retuned (final) |
|---|---|---|---|---|
| Lying_Idle Head bone midpoint z (f0 / range) | 0.376 / 0.316-0.402 m | same | 0.557 / 0.503-0.576 m | 0.557 / 0.503-0.576 m |
| LieDown LOD2 head-region min z (f56) | +3.8 cm | +10.9 cm | +10.9 cm | +3.9 cm (the nose pad) |
| Lying_Idle LOD2 head-region min z | +7.1 cm | +13.9 cm | +19.8 cm | +19.8 cm |
| GetUp LOD2 head-region min z (f54) | +6.5 cm | +13.7 cm | +13.7 cm | +13.7 cm (keys there unchanged) |
| LieDown head rise into LYING: Head midpoint z, peak speed | 0.31 (f114) -> 0.38 m, 11.9 mm/f | same | 0.30 (f123) -> 0.56 m, 23.3 mm/f | 0.30 (f112) -> 0.56 m, 14.8 mm/f |
| LieDown dip into the sniff (f34-70): peak Head midpoint speed | 23.8 mm/f | same | 23.8 mm/f | 22.6 mm/f |
| GetUp f0-40: Head midpoint z max, peak speed | 0.472 m (f8), 18.0 mm/f | same | 0.557 m (f0), 18.6 mm/f | 0.602 m (f7), 18.6 mm/f |
| Max trunk/head accel LieDown / Lying_Idle / GetUp (mm/f^2) | 12 / 2.6 / 9 | 12.0 / 2.6 / 9.0 | 12.0 / 2.5 / 8.8 | 12.0 / 2.5 / 8.8 (a one-step dip into the sniff, without `kn_key`, gives 19.5 in LieDown) |

- The Lying_Idle look-around overlays are relative to LYING and were kept: the neck pitch stays within -11.4..-6.2
  deg per bone and the summed neck yaw within -18.7..+32 deg. Renders of f0/f40/f78/f116 (side, front, 3/4, head
  close-up) show no crease or over-bend at the neck.
- The standing sniff (f14) keeps its keys: its head-region min is 31 cm. It never reached the ground; the muzzle
  goes down at the kneeling sniff (f56), which is the LieDown head minimum.
- GetUp: the head goes 0.557 -> 0.602 m (f7) -> 0.352 m (f28, fore legs folded), 0.13 m more of a drop than before
  (it was 0.472 -> 0.352 m). The later keys (fold, gather, lunge, rise) are unchanged.

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
  forward again, but in Unity the collider/capsule may need an offset while lying (WORKLOG OI-10). Alternative: root
  motion on LieDown/GetUp. (Death_Lying does have root motion: it ends 0.17 m to the right and 0.38 m back.)
- The GetUp left-fore plant is the tightest joint: fetlock -61 deg around f98 (limit -65), and carpus about 100 deg
  while the chest is still low.
- The hind swings lift only 1-2 cm at mid-move. More lift folds the hock past its limit while the rump is on the ground.
- Folded fore legs still hide their cannons inside the forearm/brisket in the transition frames (LieDown f98-112, GetUp
  f22-70), where cattle really do fold them.
- The tail rests by hanging with its tip curled on the ground (`LYING_TAIL`); it does not wrap around the body.
- The anim_lib qa "fetlock loop seam" (182 mm) is meaningless for the one-shot clips.
- Clips are checked on `build/stage_b.blend` (authoring rig). `calf_animations.py` then re-parents the hooves for export
  (world hoof change 0.000 mm, `build/logs/animations.log`), and the validator matches the FBX/GLB to stage D to
  ≤0.05 mm (GLB; FBX ≤0.004 mm).
