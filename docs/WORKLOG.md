# Work log: calf asset

Newest status first, then a chronological log. Each entry: what, why, how it was verified, open issues.

## Current status (update on every milestone)
State after the **final multi-lens review**: fixes integrated and rebuilt with `bash tools/build_all.sh` on 2026-09-28
18:16-18:23 (422 s; its output is in `build/logs/build_all_run2.out`). It becomes **CHECKPOINT 02** when committed (hash
pending, see "Checkpoints"). Every open item is in "Open issues" below (IDs `OI-nn`).

| Area | State | Where |
|---|---|---|
| Geometry (calf reshape, eyes, UVs, LODs) | Done. LOD0/1/2 46,752 / 11,688 / 2,688 tris, one `UVMap`. 1.57 m long, 1.01 m high (withers; ear tips 0.97 m), 0.60 m wide (ears; body 0.41 m). Hoof soles on z = 0 (LOD0 min z 0.2 mm, no vertex below). Final review: smaller head (`head_scale` 0.97, `neck_deepen` 1.10), thin cupped ears (`ear_scale` 1.40), smaller eyes (`eye_open` 0.85, `eye_protrude` 0.25), tail switch, forehead tuft. | `tools/calf_stage_a.py`, `tools/calf_stage_b.py` |
| Rig | Done. 46 bones (43 source + `Jaw`, `Ear.L/R`); lower-leg tails on the fetlock; 30 fps. Export rig (stage D, FBX, GLB): hooves re-parented under the lower legs (world change 0.000 mm), 42 bones (the 4 pole helpers are dropped). | `tools/calf_stage_b.py`, `anim_lib.reparent_hooves_for_export` |
| Skin weights | Done. Stage B smooths the withers/neck (813faea), re-splits the tail chain (`Tail5` now weighted), repaints the brisket midline and limits **every LOD to 4 influences**, so Blender previews equal Unity. The exporter only normalises; the validator's every-frame skin check gives 0.005 mm (FBX) / 0.049 mm (GLB). | `tools/calf_stage_b.py`, `tools/weight_utils.py` |
| Textures | Done at 4096: BaseColor, Normal, Roughness, AO, MaskMap (HDRP), MetallicSmoothness (URP); eye 1024; fur mask + noise. Final review: jaw/ear regions, iris and lid rim, shoulder band, blaze, tail switch, hooves, neck/throat folds in the normal map, nostrils and mouth line, orange tone. `T_Calf_Height` is authoring-only and not exported. The GLB embeds 2048 copies. | `tools/calf_textures.py`, `tools/calf_fur_textures.py` |
| Animation set | Done: **25 clips**. Idle and Eating (imported; leg IK re-solved; Idle's left-hind slide and Eating's muzzle height repaired), Stand, Walk_Slow/Walk/Trot/Gallop (in place + `_RM`), TurnLeft90/Right90 (56 f, eased), Idle_LookAround, Graze_Start/Loop/End, Call, HeadShake, LieDown, Lying_Idle, GetUp, Death, Death_Lying, Leap. | `tools/calf_animations.py`, `tools/anim_lib.py`, `tools/anim_gait.py`, `tools/clips/` |
| Key-pose clip families | Done and reviewed: `actions` (Death, Leap, HeadShake, Death_Lying), `idle_graze`, `imported_fix` (repairs Idle/Eating, no new clips), `locomotion` (Stand, Walk_Slow(_RM), turns, Unity blend-tree QA), `lying`. The build's QA gate reads `QA GATE: pass (25 clips)`. The family QAs reproduce on the rebuilt stage B (lying `JOINT limits: all OK`; seams and boundaries 0.0000 mm, root-relative ends ≤ 0.0004 mm). | `tools/clips/*.py`, `docs/anim_lying.md` |
| Unity export + validator | Done. **267 PASS / 0 FAIL / 0 WARN** (`build/logs/validate.log`; `build_all.sh` passes `--render-dir`, which adds the 4 render checks). Every frame of every clip is checked: bones (with an off-axis point), skins with the engines' maths, root motion, twist. Khronos glTF-Validator: 0 errors. FBX 14.0 MB; GLB 14.3 MB (2048 textures, single-sided). | `tools/export_unity.py`, `tools/validate_export.py` |
| Unity setup script, Animator, shell fur | Fixed after the review (U1-U10) and integrated: Death_Lying, time-scaled Trot/Gallop children (3.2-3.6 m/s crossfade), 0.35 s Lying_Idle → GetUp, 0.25 s Death blend. The current `CalfSetup.cs` compiles with Roslyn (C# 9) against Unity stubs; the review version also ran against fakes (90 + 12 checks); the shader compiles with DXC (1032 variants). Not run in Unity (OI-01). | `Unity/Calf/Editor/CalfSetup.cs`, `Unity/Calf/Fur/` |
| Unity verification | **Not done.** Needs a machine with Unity (OI-01). | `Unity/Calf/README.md` "Not verified" |
| One-command build | Done: `bash tools/build_all.sh` (422 s: textures 276 s, validator 89 s). The animations step fails on a QA-gate violation; `--skip-textures` re-links the old materials and refuses if the stage-B UVs changed; each run keeps a timestamped copy of the validator log. Read the "Do not" list in CLAUDE.md first (OI-29, OI-33). | `tools/build_all.sh`, `tools/relink_materials.py` |
| Final multi-lens review | **Done**: 5 lenses (likeness, animation, export rig, unity code, docs), each "ship with fixes"; 58 findings fixed or deferred; integrated, retuned for the smaller head and rebuilt (log entry of the same name below). What stays open is OI-35..OI-43. | "Log" below |

**Adult cow (second asset, 2026-09-29):** `bash tools/build_all.sh --asset cow` builds an adult Simmental cow into
`Unity/Cow` from the same source, tools and clip code (see CLAUDE.md "Adult cow"). Build of 2026-09-29 (565 s): QA gate
pass (25 clips), validator **266 PASS / 0 FAIL / 0 WARN**. The calf build is unchanged by it (rebuilt the same day:
see the log entry "adult cow").

| Area (cow) | State | Where |
|---|---|---|
| Geometry | Done. Adult proportions of the source (no calf reshape), deeper barrel, dewlap, horns kept (x0.82, rigid on Head), modelled udder + 4 teats (rigid on the rear trunk). LOD0/1/2 58,080 / 14,520 / 3,376 tris. Final size 2.57 m long, 1.44 m high, 0.79 m wide. | `calf_stage_a.py`, `calf_stage_b.py` (`P_COW`, `add_udder`) |
| Textures | Done at 4096: Simmental coat (`_cow_layout`), cream horns with dark tips, pink udder, dark slate hooves, grey-pink muzzle. No fur textures. | `calf_textures.py` |
| Animation set | Done: the calf's 25 clips on the cow rig at authoring scale; adult gait timing (x1.19); cow fits in graze (neck), lying (hind feet for the longer trunk), Death / Death_Lying (head on its horn). | `anim_gait.py`, `clips/*.py` |
| Scale + names | Done: stage E, x1.42 (exact to 0.014 mm), `Cow*` names. | `scale_asset.py` |
| Unity | `CowSetup.cs` (calf script with cow names/speeds, no fur) and README written; not compiled or run (OI-01). | `Unity/Cow/` |

## Open issues
One list for the whole project. The dated log entries and `Unity/Calf/README.md` "Known issues" point here; close items here.
Severity: major = visible in normal gameplay or blocks a use case; minor = close-up or polish; note = accepted.

| ID | Area | Issue | Sev. | Source | Status |
|---|---|---|---|---|---|
| OI-01 | Unity | Nothing has been imported or run in Unity: FBX import, Avatar and Root node, root motion (`_RM`, turns, Leap, Death, Death_Lying), the time-scaled blend-tree children, loop-match lights, clip compression, URP/HDRP material look, LODGroup, `CalfSetup.cs`, `CalfFur.cs` and the shell-fur shader. | major | README "Not verified"; PLAN "Known limits" | open: needs a machine with Unity (the C# compiles against stubs, the shader with DXC) |
| OI-02 | Skin | Stage B limits only the cage (LOD2) to 4 influences; subdivision gives LOD0/LOD1 up to 7. The export refit leaves a 23.7 mm max deviation from the Blender skin (Gallop f14, brisket midline), so Blender previews differ from Unity. | - | export entry; README "Known issues"; `export.log` | **closed** (final review EXP-2): stage B repaints the brisket midline and limits every LOD to 4 influences; the exporter only normalises; validator skin 0.005 mm (FBX) / 0.049 mm (GLB) on every frame, 0 WARN. |
| OI-03 | Skin | The withers/neck crease when the neck pitches down (grazing). | - | session-1 animation entry; idle_graze "Open" | **closed**: 813faea Laplacian smoothing of Torso2/3, Neck1-3, FrontShoulder (`calf_stage_b.py`). GRAZE nose pad re-measured at checkpoint 01: 3.27-6.23 cm, unchanged. |
| OI-04 | Hooves | README: the hind hoof soles sit 12 mm below y = 0. | - | README "Known issues" | **closed**: stage B lifts the soles (LOD0 min z 0.0002 m: hind soles +0.2 mm, front +1.1 mm; validator ground 0.0002). The README note was removed in the final-review docs refresh. |
| OI-05 | Death | No root motion. | - | actions "Open" | **closed**: the Root drifts 0.787 m to the calf's right (actions rework). |
| OI-06 | Leap | The lead fore is reach-clamped 2.3 cm and slaps down at 50 mm/f. | - | actions "Open" | **closed**: 15 mm/f on the last airborne frame, no clamp. |
| OI-07 | Death | Lower-leg crossing and tail contact were checked visually only. | - | actions "Open" | **closed**: OVERLAP QA (LOD2 limb pairs 0, bone capsules clear). |
| OI-08 | Leap | No in-place Leap (root motion only). | minor | actions "Open" | open |
| OI-09 | Death | No `Dead_Idle` loop. It must reuse `death_fn`'s hook/post functions with `dead_pose()`. | minor | actions "Open" | open |
| OI-10 | Lying | The lying calf is 0.40 m behind its standing Root (LieDown/GetUp have no root motion), so the collider is offset while lying. (Death_Lying does move the Root: 0.17 m to the right and 0.38 m back, so it ends under the carcass.) | minor | lying "Open"; `anim_lying.md` | open: collider offset, or root motion on LieDown/GetUp |
| OI-11 | Death | The topple takes 22 frames; the GiM calf falls in about 13-15 frames with looser, splayed legs. | minor | actions "Open"; final review A11 | open (deferred: a rework of Death, not a parameter change) |
| OI-12 | Graze | idle_graze minor 1: the muzzle never touches the ground. Now (after A12a and the smaller-head retune) the Graze_Loop nose pad is 2.62-4.29 cm on LOD2 (LOD0 2.94-4.55; checkpoint 01: 3.27-6.23), and each bite dips only ~0.4 cm. | minor | idle_graze review | open (improved) |
| OI-13 | Graze | idle_graze minor 2: the right fore is "over at the knee" in GRAZE (carpus 26.8°). | minor | idle_graze review | open |
| OI-14 | Graze | idle_graze minor 3: abrupt step lift-off (the stepping fetlock jumps 8.6 mm on Graze_Start f12 / Graze_End f13; the QA's SMOOTH line still shows IKFrontLeg.L 8.60 / 9.36 mm/f² there). | minor | idle_graze review | open |
| OI-15 | Graze | idle_graze minor 4: the tear jerk snaps in one frame (Graze_Loop f11/f53/f87). | - | idle_graze review | **closed** (final review A12b): `flick()` eases in; head pitch rate 0.9 → 3.1 → 5.1 → 2.9°/f (was -0.9 → -5.9 → -3.4). |
| OI-16 | Graze | idle_graze minor 5: the swing hoof grazes the ground on LOD2 only. | minor | idle_graze review | open |
| OI-17 | Idle/Graze | idle_graze minor 6: the fly-swat tail swish is weak (tip ±8-12 cm). | - | idle_graze review | **closed** (final review A10): anim_lib swings the hanging tail bones about the right axis; tip range Idle_LookAround -27/+37 cm, Graze_Loop ±32 cm; the gaits swing too. |
| OI-18 | Mesh | idle_graze minor 7: no mouth interior; the Call jaw stretches the lips into a sheet. | minor | idle_graze review | open |
| OI-19 | Graze | idle_graze minor 8: Graze_End steps the left fore 6 cm backward. | minor | idle_graze review; final review A12c | open (deferred: a forward shuffle needs root motion on Graze_End) |
| OI-20 | Rig | The jaw is a single hinge (no lateral chewing); there are no eyelids (no blinks). | minor | idle_graze "Open" | open |
| OI-21 | Lying | GetUp's left-fore plant is the tightest joint (fetlock -61°, limit -65); the hind swings lift only 1-2 cm; folded fore cannons hide in the transition frames; the tail does not wrap the body. | note | `anim_lying.md` | accepted |
| OI-22 | Leap/Death | Leap: the hind hocks absorb to 85-89° for 2-3 frames. Death: the trunk impact is a one-frame stop. | note | actions "Open" | accepted (intended) |
| OI-23 | Fur | PLAN's alpha fur cards (forehead tuft, ear fringe, tail switch) do not exist (`grep -ri "fur card" tools/` finds nothing). Only the optional URP shell fur exists; since the final review the forehead tuft and the tail switch are modelled in the stage-B mesh. | minor | PLAN | not started |
| OI-24 | Textures | PLAN's anatomical landmark detail in the normal map (shoulder, hip points, knees, hocks, neck folds) is not done. The final review (L10) added neck/throat skin folds and a mouth-line crease to the fur-strand height; shoulder/hip points, knees and hocks are missing (a 3-6 cm bump gives under 2° of normal tilt, so they need geometry). | minor | PLAN "Known limits" | open (partly done) |
| OI-25 | Rig | PLAN phase 3's persistent Blender IK authoring rig was not built. IK exists only inside `anim_lib` and `rebake_leg_ik.py`, and every clip is baked to FK. | note | PLAN | accepted deviation |
| OI-26 | Unity | PLAN's "speed/turn blend tree": `CalfSetup.cs` builds a Speed-only blend tree (Stand, Walk_Slow_RM, Walk_RM, Trot_RM, Gallop_RM plus time-scaled Trot/Gallop copies), with turns as trigger states. | note | PLAN | accepted deviation |
| OI-27 | Pipeline | `calf_animations.py` always writes `build/stage_b_rebaked.blend`, whatever `--out` says. A scratch run still writes into `build/`, and parallel runs race on that file (this happened during the final review). | - | final review DOC-04a | **closed**: the re-bake goes next to `--out` (`<out>_rebaked.blend`; the build writes `build/stage_d_rebaked.blend`). `build/stage_b_rebaked.blend` is a stale leftover. |
| OI-28 | Pipeline | `build_all.sh --skip-textures` re-runs stages A/B but reuses the old `build/stage_c.blend` (a full copy of the previous stage B), so stage-B edits never reach stage D or the FBX. | - | DOC-04b | **closed**: `--skip-textures` rebuilds stage C from the new stage B with the old materials (`tools/relink_materials.py`) and refuses (exit 2) if the LOD0 UVs changed. |
| OI-29 | Pipeline | Nothing checks texture resolution: `--tex-res 2048` copies 2K maps into the committed `Unity/Calf/Textures`, and the validator still reports 0 FAIL. | major | DOC-04c | open (code); rule in CLAUDE.md "Do not". The validator's new texture-memory check covers only the GLB, whose textures are reduced to 2048 on purpose. |
| OI-30 | QA | The clip QA gives no pass/fail verdict or exit code. The build log's `planted slide 0.00 mm` is measured only for Walk_RM/Trot_RM/Gallop_RM; the other 18 clips get no `planted_fn`. | major | DOC-05 | partly fixed: `calf_animations.py` now has a hard QA gate (`QA GATE:` line, exit 1): IK gap, planted slide on the four `_RM` gaits (flat-hoof stance), loop seams, knees/hocks bending backward. Still open: the other 21 clips print `planted slide 0.00 mm` unmeasured (the family QAs and `imported_fix` measure their own). |
| OI-31 | QA | The clip modules default their output to one session's scratchpad path. `lying.py` defaults to `--render all` (~10 min). | minor | DOC-09 | open (code); pass `--out-dir` / `--scratch` and `--render none`. Also: `imported_fix.py` defaults `--in` to the stale `build/stage_b_rebaked.blend` (pass `build/stage_d_rebaked.blend`), and `locomotion.py --out` needs an existing directory. |
| OI-32 | Tools | `render_views.py` silently renders the rest pose when `--action` is not found, and Blender's FBX importer names the actions `CalfRig\|<clip>`. | minor | DOC-10 | open (code); documented in the docstring |
| OI-33 | Pipeline | `build_all.sh` / `export_unity.py` overwrite the git-tracked `Unity/Calf` and `build/logs`. A manual validator run after build_all left `validate.log` at 172 PASS while `build_all.log` says 175. | minor | DOC-13 | partly fixed: `build_all.sh` keeps timestamped copies (`validate-<stamp>.log`, `validate_report-<stamp>.json`). It still rewrites `Unity/Calf` (by design) and writes no `build_all.log` itself (redirect its output). Rule in CLAUDE.md "Do not". |
| OI-34 | Review | Findings of the final multi-lens review (likeness, animation, export rig, unity, docs). | - | final review | **closed**: 58 findings fixed or deferred (log entry "final multi-lens review integrated"); what stays open is OI-35..OI-43. |
| OI-35 | Death_Lying | The 'agonal gasp' keys are absolute (f4 neck [-4,-4,-3]). Since the lying head was raised (L5: LYING neck [-9,-10,-9], head (18,4,-4)), the head drops from f0 (41 → 30 cm by f5) instead of lifting first. | minor | final review (Death retune) | open: make the gasp keys relative to `lying()` |
| OI-36 | Gallop | In the gathered phase (f1-3) the same-side forearm and shin pass through each other: 64 LOD2 polygon pairs, 85 mm bone-capsule overlap. It predates the final review. | minor | final review, animation fix round | open: needs a redesign of the gait body motion |
| OI-37 | Gaits | The fore legs crouch under load: loaded carpus bend up to ~60° in the walk, 85° in the trot and 90° in the gallop, because `Calf.reach_pass` lowers the whole body to its worst frame. | major | final review, animation fix round | open: per-frame vault or fetlock drop |
| OI-38 | Gaits | Review A8 remainder: the hind hock locks straight at toe-off for 2-3 frames in the trot and 4-5 in the gallop (the walk is fixed). Two attempts made the Trot/Gallop blend or the fore fetlocks worse. | minor | final review A8 | open (deferred: gait redesign) |
| OI-39 | Walk | Review A11: the Walk cycle is 24 f (0.8 s) against about 41 f in the GiM walk. A slower Walk would overlap Walk_Slow (36 f, 0.45 m/s), which now covers the slow cadence. | minor | final review A11 | deferred |
| OI-40 | Death_Lying | The limp hooves slide along the ground during the roll: CONTACT totals LF 108, RF 80, LH 28, RH 37 mm (LF 24.9 mm/f at the f31 impact), where Death stays within 7-10 mm per hoof. | minor | actions QA on the final build | open |
| OI-41 | Mesh | Review L12: the top line and underline (rump, tail head, girth) differ from GiM. The fix moves rest bones (hips, tail chain) and needs every gait and family QA re-run. | minor | final review L12 | deferred |
| OI-42 | Tools | Review L14: `silhouette_compare.py` still scales by bounding-box height. The reviewer's withers-normalised version (GrabCut mask, Walk f10, IoU and pattern agreement) was not ported; its scripts lived in the session scratchpad. | minor | final review L14 | deferred |
| OI-43 | Unity | Review U6b: stale one-shot triggers are not reset automatically (that needs a runtime `StateMachineBehaviour` file). The README documents the `IsTag("Ready")` / `ResetTrigger` pattern. | minor | final review U6b | deferred |
| OI-45 | Cow | The key-pose clips (idle, graze, lie down / get up, death, leap, turns, call, head shake) run at the calf's tempo; only the gaits are adult-paced (x1.19). A time stretch would need every family's frame-indexed keys and QA re-timed. | minor | adult cow | open |
| OI-46 | Cow | While lying the udder goes up to 14.2 cm (authoring; 20 cm final) below the ground: hidden under the body on flat ground, visible on slopes. There is no udder bone to push it aside. | minor | adult cow lying QA | open |
| OI-47 | Cow | Idle IK gap 3.84 mm at authoring scale (5.5 mm final), right fore f46-55: the source clip over-reaches on its own proportions. The gate allows 4 mm for the cow's Idle. | note | adult cow QA gate | accepted |
| OI-48 | Cow | Death: the trunk goes 3.34 cm (authoring; 4.7 cm final) below the ground on the f33 impact frame (calf 1.04 cm); Leap and Death_Lying clamp a planted foot target by 5.0 / 6.6 mm (authoring; the calf's never clamp). | minor | adult cow actions QA | open |
| OI-49 | Cow | The coat is procedural (domain-warped noise patches with the GiM layout biases), not a patch-for-patch copy of the GiM cow; the horns are the source's, shortened. No shell fur or fur cards. | note | adult cow | accepted |
| OI-44 | Git | This environment's git proxy refuses tag pushes (403), so checkpoints are commits whose message starts with `CHECKPOINT NN:`. | note | CLAUDE.md checkpoint rule | accepted |

## Checkpoints (safe, pushed)
Marked by commits whose message starts with `CHECKPOINT NN:` (`git log --oneline --grep CHECKPOINT`). The asset content is identical to the commit hash listed.

| # | Asset content at | State |
|---|---|---|
| 01 | `cdcf752` (+ docs-only commits after it) | Full pipeline from cow.glb → `Unity/Calf`: calf mesh (3 LODs), 4K textures, 21 clips, FBX + GLB. Validator 175 PASS / 0 FAIL / 1 WARN as `build_all.sh` runs it (172 PASS without `--render-dir`; the WARN is the 4-influence skin, Gallop max 23.7 mm). Final multi-lens review in progress. |
| 02 | `0dc4c35` (deliverable) + docs/tool fixes in the CHECKPOINT 02 commit | Final review integrated: 25 clips, validator 267 PASS / 0 FAIL / 0 WARN, QA gate pass |
| 03 | the CHECKPOINT 03 commit | Adult cow added (`Unity/Cow`, `--asset cow`): 25 clips, validator 266 / 0 / 0, QA gate pass; calf rebuilt unchanged (267 / 0 / 0) |

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
  - The source skinning stretches the withers about 2× when grazing. Smoothing the Torso3/Neck1/FrontShoulder weights is still open. *[Done later in 813faea: OI-03, closed.]*
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
- *[Superseded by c4fbcaa: the clamp is now 0.9985 × chain and `Pose()` == rest, see the "Update at checkpoint 01" note under the QA table below.]*
  **Pose() already clamps the front hooves ~2 mm up.** The straight front legs are asked 3 mm more than 0.99 × chain at rest (the `pose_to_basis` clamp is 0.992): front fetlock z 90.6 mm vs 88.6 mm rest. With a `stance_fn`, `reach_pass` lowers the body on standing frames (dilated/smoothed over ±5 f), so the shared Pose() boundary frames would differ between clips. This family therefore passes no `stance_fn` and never raises the elbows (body z ≤ 0, no nose-up pitch).
- **Carpus sensitivity:** the front legs are nearly straight (15° carpus bend at rest; 10.4° since c4fbcaa). Each 1 cm the elbow drops costs about 15° more carpus flexion. Lower the "front end" with `Torso3` (withers/neck only) and a small body pitch, not with body z.
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
- **Update at checkpoint 01** (after c4fbcaa: reach clamp 0.9985 × chain, so `Pose()` == rest). Re-run with
  `python3 tools/clips/idle_graze.py --no-render --out-dir <scratch>` on the 15:00 `build/stage_b.blend`: the
  "Planted hoof vs rest" column is now 0.0 mm for every clip (no clamp), and the rest carpus bend is **10.4°**
  (carpus ranges: Idle_LookAround 10.4-17.5°, Graze_Start 10.4-58.5°, Graze_Loop 16.5-26.8°, Graze_End 10.4-56.8°,
  Call 10.4-17.6°). Nose pad z, pops, seams and boundaries are unchanged (0.0000 mm / 0.0000°). With the new clamp,
  a `stance_fn` no longer moves `Pose()` frames (the fore legs rest at 0.996 × chain, below the 0.997 vault
  threshold), but the "never raise the elbows" rule still holds: while a fore hoof is planted, an elbow may rise only
  ~0.5 mm before `reach_pass` lowers the body (±5 f) and ~1.2 mm before the clamp lifts the hoof.

**Open:**
- The source skinning bulges the withers when the neck pitches hard: the neck bend is spread over Torso3 + Neck1–3 to limit it; weight smoothing is still open. *[Done in 813faea: OI-03, closed.]*
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
  - the library's reach clamp makes `Pose()` differ from the armature rest by 9 mm / 3° in the fore legs *[fixed in c4fbcaa: `Pose()` == rest]*.

### 2026-09-28: texture + export agents finished
- **Textures** (`tools/calf_textures.py`):
  - Rest-position, normal and part maps are baked in Cycles. The coat is a numpy procedural anchored to rig and mesh landmarks: white shoulder band, brisket, belly, hip band, lower legs, tail and forehead blaze; orange barrel, rump, neck and head; pale muzzle with nostrils.
  - Fur-strand height is baked into a tangent-space normal (MikkTSpace, OpenGL). UV islands have unlimited padding.
  - Output is deterministic. A 2048 run takes about 70 s; the 4096 run is estimated at 4–5 min and 3–4 GB.
  - Hoof colour changed to pale horn (HD reference frames) after the run.
- **Export** (`tools/export_unity.py`, `tools/validate_export.py`):
  - Takes are exported through **NLA strips, one per action**. Blender 5's "All Actions" mode names takes `CalfRig|X` and leaked 198 mm of pose between takes in a test.
  - The exporter pre-rotates the rig rest so `CalfRig` has identity rotation in Unity (the FBX apply-transform option doesn't cover armatures). The unweighted PoleTarget helpers are dropped.
  - **Subdivided LODs carry up to 7–8 influences.** The exporter refits over-limit vertices to their best 4 bones against poses sampled from all clips. The worst case drops from 41 → 23.5 mm vs Blender (Gallop, brisket midline). Open item: limit and refit the weights in stage B so Blender previews equal Unity (OI-02; at checkpoint 01 the 21-clip refit gives 23.7 mm, Gallop f14).
  - The body submesh is exported last (the fur needs this).
  - The validator reads the FBX/GLB directly with FBX/glTF transform maths (0.001 mm vs source), re-imports both, runs Khronos gltf-validator (npm, in build/node_tools) and renders comparisons.
- **Follow-ups done:**
  - Hoof soles lifted onto z=0 in stage B (the source sank them 4.5 mm front / 12 mm hind).
  - `CalfSetup.cs` now sets `optimizeBones=false` (Strip Bones would remove the unweighted `Root` motion node) and `importTangents=Import`.

### 2026-09-28: adversarial review of clip family `idle_graze` (commit b0e7536)
- **Verdict: pass, with minor issues only.** No blocker or major issue was found. Re-ran `python3 tools/clips/idle_graze.py --no-render` on the current `build/stage_b.blend` (13:13, hooves on z=0). Then measured independently on Calf_LOD0, LOD1 and LOD2 (evaluated meshes; the reviewer's harness lived in that session's scratchpad and is gone; the family QA now prints equivalent checks).
- **Confirmed:**
  - Weight-bearing hooves hold:
    - fetlock slide ≤0.08 mm;
    - every planted hoof **vertex** drifts ≤2.5 mm in xy (skin deformation only);
    - front hooves bob ≤3 mm vertically, which is the known 2 mm `Pose()` reach clamp *[gone since c4fbcaa: planted hoof off its rest height 0.0 mm]*.
  - Mesh ground: LOD0 non-hoof min z is 22.4 mm in every clip, the same as rest.
  - Clearances stay positive: tail to thigh ≥27 mm, head to fore legs ≥9 cm, ears to legs ≥17 cm.
  - Loop seams and Pose()/GRAZE boundaries are 0.0000 mm / 0°. The Root is never keyed.
  - Carpus and hock always bend the anatomical way. Ear and head-roll sign conventions are verified numerically.
- **Minor findings** (handed to the fix step):
  1. **The muzzle never touches the ground.** LOD0 nose pad is 3.8–6.6 cm in `Graze_Loop` and each bite dips only about 7 mm. In the GiM reference (13–21 s) the muzzle rests on the ground. The source `Eating` clip is also ≥4.7 cm. At gameplay distance the gap barely shows.
  2. **The right fore is "over at the knee" in GRAZE.**
     - Carpus is 26.8° (15° in `Pose()`). The cannon slopes 17° instead of 10°, and the fetlock is 7° more dorsiflexed (−38° vs −31°).
     - The cause: the elbow drops about 15 mm (body pitch plus body z).
     - Real cattle keep the loaded carpus straight.
  3. **The step lift-off is abrupt.** At `Graze_Start` f12 and `Graze_End` f13, the stepping fetlock jumps 8.6 mm in the first frame. The cannon's world-space jerk is 7.3°/f².
  4. **The tear jerk snaps in one frame.** At `Graze_Loop` f11, f53 and f87, `flick()` starts at full speed: face pitch moves 1.1 → **6.5** → 3.7°/f, and the head's world jerk is 5.4°/f².
  5. **The swing hoof grazes the ground on LOD2 only.** On LOD2 the stepping hoof comes back to 0 or −1 mm mid-swing (Start f15–16 and f22; End f16 and f22–23). LOD0 clears it by ≥7 mm.
  6. **The fly-swat swish is weak.** The tail tip moves only ±8–12 cm sideways (Idle f64–84, Graze_Loop f56–76), so it barely reads from behind.
  7. **The mesh has no mouth interior.** The only boundary edges are at the eyes. The 24° jaw in `Call` therefore stretches the lip skin into a flat sheet, most visible from the front.
  8. **`Graze_End` walks the left fore backward 6 cm,** an unusual move for cattle. An alternative is a forward shuffle with root motion.
- **Re-check after the pending stage B rebuild:** commit 813faea smooths the withers/neck weights, so the GRAZE nose height and the neck crest can shift. *[Re-checked at checkpoint 01 (idle_graze QA on the 15:00 stage B): nose pad 3.27-6.23 cm in Graze_Loop, unchanged. The crest was not re-rendered.]*

### 2026-09-28: clip family `actions` (Death, Leap, HeadShake)
**What:** `tools/clips/actions.py` (picked up by `tools/calf_animations.py`; `build(calf)` returns the 3 names). Standalone: `python3 tools/clips/actions.py [--no-render] [--only Death,...]` builds on `build/stage_b.blend`, prints the QA below, saves `<scratchpad>/actions/test.blend` (falls back to `build/clip_tests/actions/`) and renders strips + GIFs (~4 min with renders, ~5 s without).

| Clip | Frames | Content |
|---|---|---|
| `Death` | 70, no root motion | Pose() → flinch (head up, ears back, tail clamps, f0-4) → sway right with a right-fore (f5-11) and right-hind (f11-18) stagger step → fore legs buckle (carpi fold forward, chest drops, f12-27) → topples onto its **right** side with gravity acceleration (roll 13° f22 → 87° impact f35), legs lose tension from f22-26 and are carried out to its left → small bounce/roll-back, head hits the ground f38 and bounces, ears flop → right-hind reflex stretch f41-52 → `dead_pose()` held exactly f60-70. As in the GiM reference (26.8-27.5 s: falls onto its right side, legs out, head down). |
| `Leap` | 40, root motion 1.447 m (-Y) | crouch with weight back (hips -8 cm, f0-7) → fore feet lift first (f7/f8) and tuck (carpus ≤114°) → explosive hind push (body 0 → 2.7 m/s f8-14) → hind take-off f13/f14 → ballistic flight f14-24 (g = 9.81, apex +9 cm body, ~30 cm hoof clearance), head up/extended like the reference gallop, **buck**: hind legs kicked out back and up (f18-24, rump twist) → fore feet reach and land f24/f25 → body vaults over the fore legs while the rear drops (pitch +12° → -3°) → hind feet land f29/f30 → absorb → Pose() at the new root. |
| `HeadShake` | 36 | head dips → 2.5 shake cycles (7-frame period ≈ 4.3 Hz; head roll ±30°, yaw ±9°) that start at the withers/neck base and travel to the head (0.3-1.8 f lag), ears flap ±38° with ~1/4-period lag (anti-phase L/R), loose jaw, tail flick f8-28, ear flick f24 → Pose(). |

**How:**
- Per-channel Hermite curves (`Curve`: monotone Fritsch-Carlson slopes, or explicit in/out slopes for impacts; `VCurve` per component), `hermite_path` for foot swings. Boundary frames return the shared poses verbatim (`stand_pose()`, `stand_pose(root)`, `dead_pose(calf)`); residuals of the raw curves there are ≤6e-8.
- `make_clip_ex` = `Calf.make_clip` (no reach pass) + a per-frame basis hook. Death uses it to turn the **hoof bones with the trunk** once a leg goes limp: anim_lib keeps hooves upright (root yaw + flex only), so on its side the hooves would stick up. The IK targets only the hoof bone head, so re-orienting it about the head does not change the solve.
- Death limp legs: foot target = lerp(planted world position, dead foot carried by the trunk (leg-parent frame Torso2/Back), detach weight); fetlock height clamped so the rotated hoof (Calf_LOD2 hoof verts) never goes below its rest height.
- Leap: world-space foot planner. Root = COG path integrated from a speed curve (`LEAP_V`); planted feet are fixed world points; swings are Hermite paths in the root frame with **world velocity ~0 at touch-down** (the hoof retracts at body speed) and a toe-off tangent at lift-off; keys can be timed as fraction of the swing, frames after lift-off or frames before touch-down.

**Gotchas (useful for other families):**
- Conventions checked by FK probes + renders: `flex` + = toe back; `ears` x + = tip forward, y + = tip down, z twist; head roll + = left ear down; body roll + = right side down; **spine roll + = LEFT side down**; **tail side + = tip toward the calf's RIGHT (-X)** (the Pose docstring says left).
- Front leg reach: `top_rot` barely moves the elbow (`FrontShoulder` is a 4 cm bone at the elbow). Use `glide` (or `auto_top`) to move the elbow.
- Lying on the side: the lower ear points straight into the ground (-12 cm) unless folded back (`R = (-50, -40, 0)`). The upper ear base sits ~25 cm up.
- Leap reach budget (hip→fetlock ≤ ~0.636 m with `auto_top`): the COG may travel only ~0.26 m before the hind feet leave. A fore foot landing 0.27 m ahead at 2.7 m/s needs a nose-down, low front end at touch-down (with a ~2 cm reach clamp for 2-3 airborne frames on the lead fore). After touch-down the elbow must follow the vault arc of a nearly straight leg, otherwise the carpus folds 100°+ (cattle carpi lock under load). Keys were derived from elbow/hip height targets.
- The hind hooves must rise with the hips right after take-off (the leg is at full extension), otherwise they are clamped for several frames.

**QA** (`python3 tools/clips/actions.py`, build/stage_b.blend after the hoof-sole / weight-smoothing rebuild):

| Clip | IK gap | Planted slide | Planted hoof vs rest | Non-hoof min z (LOD2) | Carpus / hock bend | Worst planted reach excess |
|---|---|---|---|---|---|---|
| Death | 0.04 mm | 0.01 mm | ≤2.1 mm (Pose() clamp) | -1.51 cm (f35 impact, head/ear); dead pose -0.11 cm; head 0.26 cm | 15-143° / 52-111° | 3 mm (f0 = Pose() clamp) |
| Leap | 0.03 | 0.01 | ≤2.1 | 2.60 cm (= rest) | 15-114° / 15-118° | 3 mm (Pose() clamp) |
| HeadShake | 0.00 | 0.00 | ≤2.1 | 2.60 cm | 15° / 52° | 3 mm |
- All clips start at Pose() (0.0000 mm / 0.0000°); Leap and HeadShake end at Pose() root-relative (≤0.0007 mm). Death f60 = f70 exactly. Carpus/hock bends are positive (anatomical) on every frame; Death measures them in the trunk frame so they stay meaningful on the side. Hoof min z never goes below rest (-0.31 cm vs -0.12 rest in Death).
- **Update at checkpoint 01** (after c4fbcaa; `python3 tools/clips/actions.py --no-render --out-dir <scratch>`): the
  "Planted hoof vs rest" column is 0.0 mm and the "reach excess" column -0.4 mm for all three clips (the `Pose()` clamp
  is gone); the rest carpus is 10.4°. The numbers after the actions rework are in the rework entry below.
- Largest per-frame rotation 2nd differences (intended): Death Body 7.4°/f² at the impact (f35); Leap FrontLowerLeg.L 47.6°/f² at the lead fore touch-down (f24; the hoof comes in 5 cm/frame and stops) and IKBackLeg.R 96 mm/f² at the hind take-off (f14); HeadShake Head 27.8°/f² (a ±30° 4.3 Hz shake is ~24°/f² by itself), ears ≤35.8°/f².
- `calf.qa` "fetlock loop seam" is meaningless for these non-loop clips (Death 394 mm here, 669 mm after the rework, which added the 0.79 m root drift: the calf ends lying on its side).

**Open:**
- Death has no root motion (the body ends 0.30 m to the calf's right of the Root). If gameplay needs the capsule to follow, add a Root drift. *[Closed by the rework: 0.787 m root drift (OI-05).]*
- The lead fore (LF) is reach-clamped by up to 2.3 cm for 2-3 airborne frames before touch-down, and its hoof arrives with 5 cm/frame then stops (a hoof "slap"). Reducing the leap speed (2.7 m/s) would soften this. *[Closed by the rework: 15 mm/f, no clamp (OI-06).]*
- No in-place variant of Leap was made (root motion only). *[Still open: OI-08.]*
- Lower-leg crossing on the side and tail contact were checked visually only (the tail rests ≥9 cm up on the thighs, no clearance metric). *[Closed by the rework: OVERLAP QA (OI-07).]*

### 2026-09-28: adversarial review of clip family `lying` (commit 9dd402a)
- **Verdict: needs fixes (3 major, 2 minor).** Re-ran `python3 tools/clips/lying.py --render none` on the current `build/stage_b.blend` (13:13). The author's QA reproduces: IK gap ≤0.05 mm, planted slide ≤0.01 mm, carpus lock drift ≤7.1 mm, and every seam (LieDown end = Lying_Idle start/end = GetUp start; both standing ends vs `make_clip(Pose())`) at 0.000 mm / 0.000°. LOD2 non-hoof min z is now −1.0 cm; LOD0 is −0.3 cm. Root is never moved.
- The reviewer measured independently: joint angles about the body's side axis, LOD0/LOD1 evaluated meshes, ray-parity "inside the skin" tests, and debug renders coloured by bone. The harness (`measure.py`, `inside2.py`, `rview.py`, …) was in that session's scratchpad (`review_lying/`), was never committed and is gone. The lying QA now includes the JOINT, GROUND and INSIDE checks that replaced it.
- **Major findings** (handed to the fix step):
  1. **Weight-bearing fore legs buckle past anatomical limits.** The hoof is held flat at its rest spot while the chest drops, so the fetlock hyperextends. (Rest fetlock is −31°; real limit about −65°.)
     - LieDown RF, planted f0–34: fetlock −71° → **−117° (f35)**, carpus 124°. The carpus sits 6 cm off the ground and 17.5 cm ahead of the fetlock, *below* the fetlock.
     - GetUp LF, planted f68+: fetlock **−121 to −124° (f63–70)**, still beyond −70° until f92. Carpus at z 5.8 cm, 17.6 cm ahead of the hoof.
     - GetUp RF, planted f87: fetlock −85 to −89°.
     - During the sniff the loaded carpi are already 38–46°.
     - Suggested fixes: let the hoof roll onto the toe (flex) as the knee goes down; for GetUp, plant the fore hoof ahead of the knee with a short corrective step later, or raise the chest before planting.
  2. **Hind stifle hyperflexion during the rump drop and the gather.** The femur-to-tibia joint angle closes to **14–17°**: RH stifle bend 163° at LieDown f86 and 166° at GetUp f18 (rest bend 60°, LYING 131/139°). The hock stays 27–30 cm high while the hip drops from 0.70 to 0.34 m, so the gaskin disappears into the thigh: 41% (LieDown f84) and 49% (GetUp f18) of the right thigh/gaskin LOD1 verts are inside the trunk. Suggested fix: bring the hind hooves forward, or let the hocks go back and down, while the rump sinks.
  3. **In LYING the fore cannons and hooves are inside the forearm and brisket.** On LOD1, 63–64% of each FrontLowerLeg's verts are inside the forearm and 55–57% of each hoof (FF) is inside the brisket/neck skin. Both fore legs read as stumps ending at the knee from the front, side and below (renders `rv_ly_fore.png`, `rv_ly_below.png`). The reference shows the fore cannons and hooves visible in front of the chest. Suggested fix: move the folded cannon beside or under the forearm with less than full carpus flexion, or stretch one fore leg as in the reference.
- **Minor:**
  - LieDown f35: the knee lock switching on reverses the chest from −6.1 to +2.0 mm/f (a 3.6 mm rebound).
  - The hind hooves are dragged 13–16 cm along the ground, dipping up to 7.6 mm below it (LOD0): LieDown f84–96 and GetUp f8–22.

### 2026-09-28: adversarial review of clip family `actions` (commit 8a12fde)
- **Verdict: needs fixes (4 major, 6 minor).** Re-ran `python3 tools/clips/actions.py --no-render` on the current `build/stage_b.blend` (13:13). The author's QA reproduces exactly:
  - IK gap ≤0.04 mm and planted slide ≤0.01 mm; LOD2 non-hoof min −1.51 cm (Death f35); LOD0 −1.17 cm (right ear, impact), within the 2 cm limit.
  - Every start vs Pose() is 0.0000 mm; Leap/HeadShake end vs Pose() ≤0.0007 mm; Death hold f60 = f70; Leap root 1.447 m.
  - Carpus and hock are always bent the anatomical way.
- Measured independently: LOD0/LOD2 evaluated meshes (BVH self-overlap by bone region, hoof-vertex ground contact and slide), bone-capsule clearances, signed fetlock angles, world-space pops. New render angles: right-front 3/4, top, right-back and close-ups. Reference frames: death 26.8–27.9 s every 1/15 s; gallop 8.6–13.4 s. Harness and renders were in that session's scratchpad (`review_actions/`: `probe_mesh.py`, `hoofslide.py`, `bones.py`, `capsule.py`, `worldpop.py`, `still.py`, `st_*.png`, `r_*.png`), were never committed and are gone. The actions QA now includes the CONTACT, OVERLAP, FETLOCK and REACH checks that replaced them.
- **HeadShake passes:** hooves static (0.0 mm), no mesh overlaps on LOD2, and the ±30° roll at 4.3 Hz is plausible for fly-shaking.
- **Major findings** (handed to the fix step):
  1. **Death, f14–26: the weight-bearing fore fetlocks hyperextend.** The hooves are kept flat and planted while the carpi fold 66–139°. Fetlock angle (cannon vs pastern) goes from 28° at rest to LF 69° (f15), 84° (f20) and 89° (f22), and to RF 71 → 102° (f15–25). The real limit is about 65°; Leap landing peaks at 46°. The lower leg reads as a "Z": the knee is forward, the cannon runs back to an upright hoof (`st_buckle.png`). This is the same fault the `lying` review found. Suggested fix: as the carpus folds past ~60°, roll the hoof onto its toe and then onto the dorsal wall (flex the fetlock), or plant the knees.
  2. **Death, f23–35: the hooves skate along the ground during the topple.** `planted()` ends when the detach ramp starts, so the author's slide QA stops measuring there. After that, hooves within 8 mm of the ground (LOD0) travel: RH **509 mm** (up to 90 mm/f, f27–34), LF 214 mm (f23–29, the up-hill leg, which should lift), RF 140 mm. This happens while body roll is only 13–55° and the chest is still held up. Suggested fix: keep each foot world-locked until it unloads, then lift it along an arc with the trunk (≥2–3 cm clearance). Let the down-side legs fold rather than slide.
  3. **Death dead pose (held f60–70, from f33 on): the hind lower legs interpenetrate.** The LH cannon/pastern sits inside the RH cannon: bone axes are 28 mm apart against 53 mm of summed radius, so about 25 mm of overlap. The hooves overlap by 20 mm, and the LF hoof is 8 mm into the RF cannon. See `st_dead3.png` and `st_fetlock.png`. Suggested fix: move the upper hind foot (DEAD feet LH) about 5 cm further out or forward, or add a clearance term.
  4. **Leap, f24→25: the front end rebounds at the fore touch-down.** The head's vertical speed flips from −75 to +92 mm/f in one frame: world acceleration 167 mm/f², the largest in the clip and above Death's impact (102). Body pitch rate jumps from 0 to −6.5°/f (keys 24: 12.5°, 25: 6.0°). The head bobs up 9 cm on the first contact frame (`r_Leap_land.png`). Suggested fix: carry the pitch rate through the contact and let the neck/head keep sinking for 2–3 frames before it recovers.
- **Minor:**
  - **Tail7 buried in the down-side gaskin** from f35 on: 31 mm axis distance against 63 mm of summed radius. The WORKLOG's "tail rests ≥9 cm up" is wrong.
  - **Sideways fetlock bends** in the fall and the dead pose: LF −51° and LH −44° out of the cannon's flexion plane (RF +35–38° at f28–30). The hook turns the hooves with the trunk, not with the cannon. Orient the hooves from the baked lower-leg bone instead.
  - **Death stagger-step hoof flick is under-reported:** FF.R world 40.6°/f², IKFrontLeg.R 30°/f² at f8. The author's "largest pop" summary lists only Body.
  - **Leap lead-fore hoof slap (known):** 117 → 50 → 0 mm/f at f22–25.
  - **Module docstring is stale:** it says Death 72 f with the hold f62–72, and Leap 42 f with a ~15 cm apex. The code has 70 f with the hold f60–70, and 40 f with a +9 cm apex.
  - **Death differs from the reference.** Death has no root motion (known), and its collapse is slow: 35 f to impact against about 12–15 f in the GiM reference, where the legs stay straight.

### 2026-09-28: lying clip family reworked after its review (fixes e8bc810: 3 major + 2 minor)
- **What:** `tools/clips/lying.py` was largely rewritten on the same framework (Hermite body/foot tracks, knee lock,
  `solve_body`). The design, rig findings and QA are in `docs/anim_lying.md` (read it first when touching the family).
  - Clips are now `LieDown` 150 f, `Lying_Idle` 150 f loop, `GetUp` 150 f, still with no root motion.
  - `LYING` now stretches both fore legs forward (the GiM reference) and lies `LY_B` = 0.40 m behind the standing
    body (was 0.20).
  - Seams are still exact (0.000 mm / 0.000°).
- **Key techniques** (all inside the module; anim_lib is untouched):
  - `make_clip_ex` keys the IK poles per frame. A free fore leg's pole rotates with the leg (the carpus always flexes
    anatomically, including a leg stretched forward); a kneeling leg's pole lies in its knee plane (the knee stays
    exactly on its contact under body roll: drift 0.04 mm, was 7 mm); hind poles rotate with the stifle→fetlock line (no
    hock flip).
  - `leg_state` predicts the baked IK analytically (knee ≤0.03 mm, hock ≤1.2 mm error). Key poses are solved against
    joint angles.
  - Hoof pivots let a loaded hoof roll on its toe with zero contact slide.
  - A C1 `reach_guard` keeps loaded fore legs off the library's reach clamp (0.992 × chain then; 0.9985 since c4fbcaa).
  - `fit_femur` keeps the hind joints in range.
- **QA** (new `JOINT` line with limits, all OK):
  - Loaded fore fetlock: −52 / −61° (LieDown / GetUp; limit −65; was −117 / −124).
  - Standing carpus: 24 / 15° (sniff was 38–46).
  - Stifle: ≤135.5° (was 163–166). Hock: ≥−146°.
  - LYING fore cannons/hooves inside the skin (LOD1): 0% (was 56–64%).
  - Thigh inside the trunk: 9% at LieDown f84 (was 41%) and 15% at GetUp f18 (was 49%).
  - Chest decelerates into the knee contact with no rebound. Hind hooves are lifted, not dragged: LOD0 +0.2..+12 mm
    while moving (was −7.6 mm).
  - Planted slide ≤0.04 mm; pivot drift 0.00 mm; LOD2 body min z ≥ −0.8 cm; max bone accel 34 mm/f².
- **Gotchas found:**
  - `anim_lib.blend_pose` returns a Pose with `auto_top=True`; reset it in auto_top-off families.
  - *[Superseded by c4fbcaa: `Pose()` == rest now.]* Every `Pose()` frame holds the fore hooves ~2 mm up (the reach clamp is below the rest reach); a loaded hoof
    settles those 2 mm when the elbow comes closer, so let that happen gradually.
- **Open:**
  - The lying calf is 0.40 m behind its standing root (Unity collider offset while lying, or add root motion).
  - GetUp's left-fore plant is the tightest joint (−61°).
  - Hind swings lift only 1–2 cm (more lift over-folds the hock while the rump is down).
  - Folded fore legs still hide their cannons during the transition frames.

### 2026-09-28: actions clip family reworked after its review (fixes 9fe4076: 4 major + 6 minor)
**What:** `tools/clips/actions.py`: Death rebuilt around a physical topple, the Leap landing re-derived, the QA
extended. HeadShake is unchanged (it passed the review). `Unity/Calf/Editor/CalfSetup.cs`: Death is now
`RootMotion.Translate` (it has root motion). `Unity/Calf/README.md` root-motion notes updated for Leap/Death.
Run: `python3 tools/clips/actions.py --no-render` (~6 s: builds on `build/stage_b.blend`, prints QA, saves
`<scratchpad>/actions/test.blend`); drop `--no-render` for strips + GIFs (~5 min).

**Death: how it works now** (`DeathModel`, all world space, then made root-relative):
- Flinch f0-4 → right-fore (f3-9) and right-hind (f5-11) stagger steps with the body swaying right → from f11 the
  body topples **over the right hooves**: a rigid pendulum about the right hooves' lateral sole edges (gravity,
  k = 0.15 m, time-scaled to land exactly at f33), plus 3 cm of leg give. Rotating about a pivot is written as
  anim_lib's rotation about the COG plus moving the COG on the arc. The pre-topple curves hand over at f11 with
  matching position and velocity.
- The right hooves never slide. They tip onto their lateral wall about the LOD0 lateral sole edge (`_HOOF_EDGE`,
  fetlock = W − q·edge). The left legs unload at f11/12, rise first and then follow the trunk, keeping the leg shape
  they had at lift-off. At f25-40 they flop in the trunk frame into the dead pose, in front of the lower legs.
  The upper-hind twitch at f40-53 moves forward and up, away from the lower leg.
- Root motion: the Root drifts 0.79 m to the calf's right (f9-41), so it ends under the carcass (the COG path
  demands it: straight legs pivoting on planted hooves land the body ~0.75 m to the side, as in the GiM reference).
- Hoof orientation: a basis hook for the planted, stepping and tipping hooves. A **post-bake pass** orients the limp
  upper hooves from the baked cannon (plus a relaxed flex about the cannon's hinge axis), so the fetlock never
  bends sideways. The orientation only exists after IK, so Death is built 3 times (`DEATH_PASSES`); each pass feeds
  the previous pass's cannon orientation into the ground clamp. f60-70 is exactly `dead_pose(calf, root_end)`.
- `dead_pose(calf, root=None)` is root-relative (body_off.x = 0). A future Dead_Idle clip must reuse `death_fn`'s
  hook/post functions to get the same hoof orientation.

**Leap: how it works now:**
- The landing is expressed as front (elbow line) and rear (hip line) height keys (`LEAP_HF`/`LEAP_HR`, handover
  from the flight curves at f19), plus a neck lag (`LEAP_NECK_LAG`). The values come from an optimisation (scratch
  `leapopt2.py`, not committed) with these constraints: COG exactly ballistic until the fore contact; fore leg
  ≤ 12-17 mm compressed at contact and ≤ ~50 mm after it; the rear cannot decelerate while both hind feet are in
  the air; hip no more than 9 cm below rest; smooth head, pitch, elbow and hip.
- Fore feet land 8 cm short of their final spot (`LEAP_SHORT`) and take a small balancing step (LF f31-36,
  RF f33-38). This gives a smaller leg angle at contact, so less stiff-leg vault rebound, and the spot is reachable
  one frame early. The last 3 airborne frames are world-anchored keys (`tdw`), so the hooves decelerate and come
  down almost vertically.
- Hind feet now land at f26/27 (was 29/30): after the fore contact the rear keeps falling, faster than g, and cannot
  be held in the air for 5 frames. The hind legs trail and kick back right after take-off (f15-19), then swing
  through. Hind toe-off: the hooves roll onto the toe tip over the last 3 planted frames (`toe_pivot_fetlock`, which
  accounts for the toe bone's extra 0.35·flex). The first swing key follows 55% of the root's advance (`offw`), so
  there is no velocity kink and no reach clamp at lift-off.

**Review findings → result** (my QA plus the reviewer's own scripts re-run on the new build):

| Finding | Before | After |
|---|---|---|
| Death fore fetlock hyperextension while loaded | LF 89°, RF 102° | LF 52°, RF 56° (limit ~60; rest 28/31) |
| Death hooves skating in the topple (LOD0 in-contact slide, total) | RH 509, LF 214, RF 140 mm | RH 10, RF 8-10, LF 0-9, LH 7 mm; rolling hooves ≤ 0.8 mm/f |
| Death dead-pose leg interpenetration | 25 mm capsule overlap, 14+6 LOD2 pairs | 0 LOD2 limb pairs on every frame; capsule clearance ≥ 22 mm |
| Leap fore touch-down rebound | head −75 → +92 mm/f (167 mm/f²); Body 6.5°/f² | head −56, −28, −9, −2, 0, +4 mm/f (≤ 28 mm/f²); Body 4.5°/f² |
| Death tail tip in the lower gaskin | 29-32 mm overlap | tail lies on the ground behind the legs (min z 0.9 cm, capsules clear) |
| Death sideways fetlock bend | 35-51° | ≤ 6° on every frame |
| Death stagger-step hoof flick | FF.R 40.6°/f² | 11.3°/f² (flex 15·h²); SMOOTH now lists the top 4 per-bone pops |
| Leap lead-fore hoof slap (last airborne frame) | 50 mm (reach-clamped 2.3 cm) | LF 15, RF 15, hind 18 mm; no reach clamp |
| Stale docstring | 72 f / 42 f / 15 cm apex | rewritten (clips, conventions, extensions, QA) |
| Death root motion / slow collapse | none; 35 f to impact | 0.79 m; impact f33 (topple f11-33 is gravity-timed) |
| (found here) Leap hind take-off fetlock | RH 67.5°, BackLowerLeg.R 44.6°/f², IKBackLeg.R 96 mm/f² | 49°, 25.6°/f², no lift-off kink |

- Unchanged and still exact: IK gap ≤ 0.04 mm; flat-planted slide ≤ 0.01 mm; every start = Pose() (0.0000 mm);
  Leap/HeadShake end = Pose() root-relative (≤ 0.0007 mm); Death f60 = f70; raw-vs-shared residual ≤ 6e-8; Leap
  root 1.447 m; carpus/hock always anatomical (Death carpus 15-68°, hock 47-83°; Leap 15-114° / 18-115° in flight).
- Ground: Death LOD2 non-hoof min −1.06 cm (the trunk at the impact, f33); dead pose ≈ 0; head ≥ 0.26 cm. Hoof
  verts ≥ −0.8 cm (LOD2 cage around the LOD0 pivot edge). Every leg keeps ≥ 23 mm reach margin while resting.
- New QA lines in `run_qa`: CONTACT (LOD0 hoof skating; rolling on an edge passes, sliding fails), OVERLAP (LOD2
  limb/tail self-intersections + bone capsules), FETLOCK (signed dorsal angle, max while loaded, out-of-plane),
  REACH for all resting legs in Death, top-4 SMOOTH pops.

**Gotchas (useful for other families):**
- An unreachable foot target is silently clamped by anim_lib. In the lying pose the upper legs' shoulder/hip is
  25-30 cm up, so they reach less far than the lower legs. Check reach for **every** leg in held poses.
- Trunk-following hoof orientation gives sideways fetlock bends. Follow the baked cannon instead (post-bake pass).
- Ballistic flight + fore contact: the rear accelerates down faster than g, so the hind feet must land within
  ~2 frames. At 2.7 m/s and 30 fps a hoof can only arrive with ~0 world speed if its spot is reachable one frame
  early: land short and correct with a step.
- Tail signs lying on the right side: side + = toward the ground, lift + = tip swings back (+Y).

**Open:**
- Death's topple from tipping start to impact is 22 frames (gravity from a 5° lean at 1.5°/f). The GiM reference
  drops in ~13-15 frames with a looser, leg-splaying collapse.
- CalfSetup.cs (Death → Translate) needs the usual Unity compile check (OI-01). No in-place Leap (OI-08) and no Dead_Idle loop (OI-09).
- Leap: the hind hocks absorb to ~85-89° for 2-3 frames after landing. The Death trunk impact is a one-frame stop
  (Body tail point 143 mm/f² at f33; intended).

### 2026-09-28: clip families finished, library fixes, one-command build
- **Clip families** (workflow: author → adversarial review → fix):
  - idle_graze passed review. Its 8 minor findings are still open (OI-12..19): muzzle about 4 cm above the grass, right fore over at the knee in GRAZE, abrupt step lift-off, a one-frame tear jerk, the swing hoof grazing the ground on LOD2, a weak tail swish, no mouth interior, and a backward step in Graze_End.
  - lying fixed 3 major + 2 minor (joint limits, fore legs stretched forward in LYING, knee lock 0.04 mm, hoof pivots). It keys the PoleTarget helpers per frame; these are dropped on export.
  - actions fixed 4 major + 6 minor. Death is now a gravity topple over the right hooves, with root motion to the right so the capsule follows the body (`CalfSetup.cs`: Death is `RootMotion.Translate`). The Leap landing is smoothed.
  - Details and QA tables: `docs/anim_lying.md` and the family entries above.
- **anim_lib fixes:**
  - The reach clamp went 0.992 → 0.9985 × chain and the vault threshold 0.99 → 0.997. The straight front legs rest at 0.996, so a `Pose()` frame now equals the rest pose; before, the hooves were 2 mm up with 3° of knee bend. The walk crouch halved: body 17–36 mm down instead of 34–58.
  - `keyed_pose_fn` "hold" keys now have a true zero tangent.
- **The security warning from the workflow was benign:** the harness blocked a subagent's foreground `sleep 200`. Nothing was pushed or deleted by agents.
- **`tools/build_all.sh`** runs the whole pipeline (A → B → textures → fur textures → animations → export → validate).

### 2026-09-28: final review, docs lens (fixes DOC-01..14)
**What:** the docs were brought up to the checkpoint-01 state, so that a new agent reads current facts first.
- `docs/WORKLOG.md`: the "Current status" table was rewritten from the checkpoint (21 clips; 175 PASS with renders / 172
  without; every family done and reviewed; Unity verification not done; final review in progress). There is now one
  "Open issues" table (OI-01..34) that merges the 9 "Open:" blocks, the README "Known issues" and the PLAN gaps. Fixed
  items are closed there, and the dated entries are annotated (smoothing done in 813faea, Death root motion, the
  Leap clamp, the GRAZE re-check, the idle_graze minors listed as 8, the stale `Pose()` clamp facts, the scratch
  harness paths). The checkpoint row now says 175 PASS (172 without `--render-dir`).
- `CLAUDE.md`: a "Do not" list for the pipeline traps (OI-27..29, OI-33), a "Verification gate" with per-line limits and
  known values, the fast family QA commands, the authoring and export rigs as separate bone lists, the `Pose` sign
  conventions, a "References" summary, an "Extending" section (new family, coat change, re-export), docs.unity3d.com
  blocked (use WebSearch), a render budget of ≤12 samples, and a measured build time of 375 s.
- `docs/REFERENCES.md` (new): the reference files with resolution/fps, a timestamp index of `videoplayback (1).mp4`
  (checked on a contact sheet: the video cuts from Death straight to lying and shows no lie-down), the user's close-up
  spec as a checklist, and a frame-grab command.
- `docs/anim_lying.md`: the reach clamp is 0.9985 × chain and `Pose()` equals the rest pose; the rest carpus is 10.4°;
  the QA table was refreshed; the standalone command now carries `--render none --scratch`.
- `docs/PLAN.md`: a status per deliverable and per phase, Call/HeadShake added, and the deviations stated (fur cards
  and landmark normal detail not started; no persistent IK rig; a Speed-only blend tree).
- Tool docstrings: `calf_animations.py` (no `--only`, stage C input, the rebaked side effect, what the QA table does not
  measure), `calf_stage_b.py` (46 bones), `export_unity.py` (Height not copied, no resolution check, scratch dev
  command), `calf_textures.py` (dev command on the current stage B), `silhouette_compare.py` (bounding-box scaling),
  `render_views.py` (FBX action names, silent rest pose, sample budget), and the `anim_lib.Pose` sign comments
  (ears, head roll, spine roll).

**Verification** (everything written to the session scratchpad `review/docs_fix/`, nothing to `build/` or `Unity/Calf/`):
- Family QAs re-run with the HEAD (137fb8b) tools on the 15:00 `build/stage_b.blend`: lying `JOINT limits: all OK`, seams
  0.000 mm; LOD2 non-hoof min z -0.7 / -0.9 / -0.7 cm; standing carpus 10.6°. idle_graze: carpus from 10.4°, boundaries
  0.0000, Graze_Loop nose pad 3.27-6.23 cm. actions: REACH -0.4 mm, Death root 0.787 m, Leap 1.447 m. About 5 s each.
- FK probe (HEAD `anim_lib`): ears y+20 moves the tip 72 mm down and x+20 moves it 71 mm forward; tail side+10 moves
  Tail7 47 mm to -X; spine roll + lowers the left ear, body roll + the right one, head roll + the left one.
- Rig probe: stage B/C 46 bones with the feet under `Root`; stage D feet under the lower legs; `Body` head z 0.205 m;
  LOD0 top at the withers (z 1.014, y -0.28; ear tips 0.977); LOD0/LOD1 up to 7 influences, LOD2 4.
- The documented recipes were run: a re-export into a scratch folder plus validation gives 172 PASS / 0 FAIL / 1 WARN
  (Gallop f14 23.691 mm), the same as the checkpoint, with `Unity/Calf` and `build/logs` untouched. The texture
  preview loop at 1024 takes 19 s cold and 12 s cached. The frame-grab one-liner works. `calf_animations.py --only`
  is rejected by argparse.

**Not fixed here** (code, or files owned by other lenses; handed to the orchestrator): the code side of OI-27..33, the
stale 0.992 / "~2 mm" clamp facts in the `tools/clips/{idle_graze,actions,lying}.py` docstrings and comments, the
`tools/clips/__init__.py` docstring, and the stale `Unity/Calf/README.md` items (the 12 mm hoof note, 172 vs 175 PASS,
the "ear tips" height).

### 2026-09-28: final multi-lens review integrated and rebuilt (checkpoint 02)
**Review round.** One reviewer and one fixer per lens, on checkpoint 01. Each fixer changed only its own files and handed
the rest to the orchestrator. The reviewers' harnesses and renders were in the session scratchpad (`review/<lens>`,
`review/<lens>_fix`) and are not committed. Every lens gave the verdict **ship with fixes**:

| Lens | Findings | Fixed by the lens | Deferred (what happened to it) |
|---|---|---|---|
| likeness | 14 (8 major, 6 minor) | L1-L4, L6-L11, L13 | L5 lying head (landed, see below); L12 top line (OI-41); L14 silhouette tool (OI-42) |
| animation | 13 (6 major, 7 minor) | A1-A6, A9, A10, A13; parts of A8, A11, A12 | A7 (landed in `CalfSetup.cs`); A8 remainder (OI-38); A11 walk re-time (OI-39) and Death timing (OI-11); A12c (OI-19) |
| export rig | 7 (1 major, 6 minor) | EXP-1 (validator gate), EXP-2, EXP-4, EXP-5 | EXP-3 (fixed by the new turns, A6); EXP-6 and the EXP-2 source fix (landed in stage B); EXP-7 (README, done in this refresh) |
| unity code | 10 (2 major, 8 minor) | U1-U10 | U6b trigger auto-reset (OI-43); U4 clip easing (done by A6) |
| docs | 14 (8 major, 6 minor) | DOC-01, DOC-02, DOC-04..14 (entry above) | DOC-03 (README, done in this refresh) |

**What changed** (finding IDs in brackets):
- Stage B: `head_scale` 1.22 → 0.97 and `neck_deepen` 1.28 → 1.10 (poll to nose 0.35 × withers, as GiM) [L4];
  `ear_scale` 1.2 → 1.4 with flattened, cupped leaves (~8 mm thick, no self-intersection) [L8]; `eye_open` 1.55 → 0.85,
  `eye_protrude` 0.32 → 0.25 (opening 78 → 35 mm) [L2]; tail switch (`tail_switch` 1.8) [L6]; forehead tuft [L7]; tail
  chain weights re-split so `Tail5` is weighted [EXP-6]; brisket midline repainted and **every LOD limited to 4
  influences** (Blender == Unity; the old skin WARN is gone) [EXP-2]; optional `--in/--out`.
- Textures: Jaw/Ear bake regions (orange jaw and throat, pale inner ears) [L1]; darker iris and a pale lid rim [L2];
  shoulder band and brisket [L3]; tail switch [L6]; blaze [L7]; hoof horn, coronet and cleft [L9]; normal-map bump ×3
  plus neck/throat folds and a mouth crease [L10]; nostrils and mouth line [L11]; orange tones [L13]. The lens measured
  pattern agreement 0.789 → 0.855, white 35.4 → 28.0% (GiM 28.5%), rest silhouette IoU 0.678 → 0.697. Bake caches with
  the old region layout are rejected.
- anim_lib / anim_gait: IK pole guard (the Gallop right-fore carpus flip; FrontUpperLeg.R twist 173° → 1.5° per frame)
  [A2, EXP-1]; a root-yaw bug in the leg-top aiming [A6]; the tail swing axis (tails now swing) [A10]; the heel roll-off
  pivots on the toe tip, plus `flat_planted_fn_for` for the slide QA [A9]; Gallop re-phased by 5/7 so it blends with the
  trot (simulated 50/50 blend skate 42 → 9.8 cm) [A1] and head held higher [A11]; new `WALK_SLOW` gait [A4].
- Clip families: new `imported_fix` (Idle left-hind slide 93 → 0 mm [A3]); new `locomotion` (Stand, Walk_Slow(_RM)
  [A4]; TurnLeft90/Right90 re-authored as 56 f eased turns that start and end on `Pose()` [A6]; blend-tree QA [A1]);
  `Death_Lying` in `actions` [A5]; GetUp hind steps land cleanly [A13]; graze `flick()` eased [A12b].
- Export and validator: the validator checks every frame (bones with an off-axis point, per-frame twist, one-shot ends
  vs Idle, skins with the engines' maths, root motion, GLB single-sided and texture memory, render bounding boxes)
  [EXP-1, EXP-2, EXP-4, EXP-5]; the exporter refit covers every frame (now a no-op: the source is within 4 influences);
  the GLB embeds 2048 textures and is single-sided (35.9 → 14.3 MB) [EXP-4].
- Unity: Root Motion Node cleared and the Rig Root node set [U1]; shell-fur passes, shadows and keywords [U2, U3]; turn
  transitions [U4]; Idle as its own state and the Speed tree with Stand / Walk_Slow_RM [U5]; explicit Die transitions,
  controller rebuilt in place, state tags [U6]; LODGroup thresholds [U7]; README [U8]; non-URP projects [U9]; shared
  shell materials [U10].

**Integration by the orchestrator** (changes in files no lens owned, plus the hand-offs):
- `calf_stage_b.py`: the EXP-6 tail re-split, the brisket repaint and the 4-influence limit on every LOD.
- `calf_animations.py`: the old turn loop removed (the `locomotion` family builds the turns); a hard QA gate (IK gap,
  planted slide on the `_RM` gaits with the flat-hoof stance, loop seams, knees/hocks bending backward) that exits 1; the
  re-bake written next to `--out` (OI-27).
- `build_all.sh`: `--skip-textures` re-links the old materials onto the new stage B (`tools/relink_materials.py`) and
  refuses if the UVs changed (OI-28); timestamped validator logs (OI-33).
- `CalfSetup.cs`: Death_Lying from LieDown / Lying_Idle (0.3 s), a 0.25 s Death blend, Lying_Idle → GetUp 0.35 s [A7],
  and time-scaled Trot_RM ×1.37 / Gallop_RM ×0.82 children so the Trot/Gallop crossfade stays inside 3.2-3.6 m/s [A1].
  Re-compiled with Roslyn (C# 9) against the Unity stubs; not re-run against the fakes.
- L5 and a retune for the smaller head (the animation lens had tuned GRAZE, Eating and the dead head on the old, bigger
  head):
  - GRAZE neck 26.5/29.5/26.5, head -43, Torso3 8: Graze_Loop nose pad 2.62-4.29 cm on LOD2 (the lens-round GRAZE on
    the new head: 6.91-8.98 cm). The Head bone briefly tips to ~96° below horizontal at Graze_Start f33 (the face just
    past vertical; not checked in a render).
  - Eating: `imported_fix.fix_eating` adds 15.9° of neck pitch (Head -15.9°) weighted by how far the head is down: nose
    pad min 11.35 → 3.50 cm (LOD2) and 11.67 → 3.83 cm (LOD0), loop seam unchanged. The descent is ~30% faster.
  - Lying [L5]: LYING neck [-9,-10,-9], head (18,4,-4): Head midpoint 0.376 → 0.557 m. The kneeling sniff is back to
    3.9 cm (`kn_low`, new `kn_key`); `ly_turn` and GetUp `prep` retuned (details in `docs/anim_lying.md`).
  - Death / Death_Lying: the dead head rests on the ground (Death: -0.11 cm at the f36 hit, 0.0 cm held; Death_Lying:
    0.0 cm from f48). The Death_Lying trunk-contact solve ignores head vertices, and its upper hind leg now lies in
    front of the lower one (capsule clearance 34.1 mm).
- The docs-lens docstring hand-offs in `tools/clips/*.py` (0.9985 clamp). `tools/clips/__init__.py` was not changed.

**Rebuild** (`bash tools/build_all.sh`, 2026-09-28 18:16-18:23, 422 s; stdout in `build/logs/build_all_run2.out`):
- Steps: stage_a 1 s, stage_b 3 s, textures 276 s, fur_tex 2 s, animations 24 s, export 27 s, validate 89 s.
- `QA GATE: pass (25 clips)`; export rig: max world-space hoof change 0.000 mm.
- Validator **267 PASS / 0 FAIL / 0 WARN** (source 3, anim 36, FBX raw 110, skin 4, FBX re-import 40, GLB raw 38, GLB
  re-import 31, Khronos 1, render 4). Checkpoint 01's 175 / 0 / 1 came from the older, smaller validator; the counts are
  not comparable.
- Files: FBX 14.0 MB, GLB 14.3 MB, `Unity/Calf` 66 MB; the shipped textures are 4096 (checked with PIL).
- Docs refresh (this entry, `Unity/Calf/README.md`, CLAUDE.md, PLAN, REFERENCES, `anim_lying.md`): the family fast QAs
  were re-run on the rebuilt `build/stage_b.blend` (18:16) into the session scratchpad (idle_graze, actions, lying,
  locomotion; `imported_fix` on `build/stage_d_rebaked.blend`), 5-8 s each. They reproduce the numbers above and in the CLAUDE.md
  gate table. The actions QA shows the Death_Lying hooves sliding 28-108 mm during the roll (OI-40).

**Open after this round:** OI-35 (Death_Lying gasp), OI-36 (Gallop leg interpenetration), OI-37 (fore legs crouch under
load), OI-38, OI-39 and OI-41..43 (deferred review items), OI-40 (Death_Lying hoof slide), and the older open rows
(OI-01, the Unity import, first).
**Next:** commit as CHECKPOINT 02, then one Unity import pass on a machine with Unity (OI-01).

### 2026-09-29: adult cow (`--asset cow`, checkpoint 03)
**What.** The user asked for "cow like cub": the adult cow next to the calf, built by the same pipeline. Look target:
the GiM adult female in `videoplayback.mp4` (Simmental; index and colours in `docs/REFERENCES.md`).
- `tools/asset_profile.py`: `ASSET=calf|cow` selects the build dir (`build/`, `build/cow/`), output (`Unity/Calf`,
  `Unity/Cow`), texture prefix and final scale. Without `ASSET` every tool behaves as before.
- Stage A keeps the horns (base loops capped, rigid on Head, `orig_part` 5). Stage B `P_COW`: no calf reshape; flank
  -0.12 (deeper barrel), legs 0.84-0.97 of the low-poly source, dewlap 1.16, ears 1.15, tail switch 1.7, horns x0.82,
  and `add_udder()`: an ellipsoid udder with a median groove plus four teats (closed islands, `orig_part` 6, weights
  copied from the nearest belly vertex restricted to the trunk bones).
- `calf_textures.py` `_cow_layout()`: tan base; white head (tan ears and poll), throat / brisket / belly (height rising
  to the udder), legs below mid-forearm / stifle, tail below its root; irregular white patches from domain-warped fBm
  with a lower threshold over the back behind the withers and on the flank, higher on the neck and shoulder, speckles
  along patch borders. Horns (base -> tip gradient, rings), udder (skin, veins, pink teats), dark slate hooves.
- Animation at the calf's authoring height (withers ~1.0 m), then stage E (`scale_asset.py`) x1.42 and `Cow*` names:
  a uniform scale is exact for a skinned animated rig (checked every frame: 0.014 mm float round-off). Gaits x1.19 cycle
  time (dynamic similarity): 0.535 / 1.087 / 2.803 / 5.137 m/s final. Cow fits: graze neck 23.3/26.3/23.3 deg (nose pad
  2.37-5.30 cm authoring), lying hoof positions shifted by the rig's own fetlocks (`lying.adapt_to_rig`: fore -9.1 cm,
  hind +11.0 cm; lying legs went from -11.0 to -0.7 cm), dead head on its horn (`DEAD`, `D_HIT`, `DL_HIT`: Death head
  -9.61 -> -0.57 cm, Death_Lying -8.47 -> +0.42 cm). QA gate: the cow's Idle may have 4 mm of IK gap (3.84 mm).
- Exporter / validator: texture names and defaults from the profile; the body-material check accepts `M_Cow_Body`; the
  size plausibility window scales with the profile. `build_all.sh --asset cow` adds the scale step and skips the fur
  textures. Unity: `Unity/Cow/Editor/CowSetup.cs` (namespace `CowAsset.EditorTools`, menu Tools > Cow), README.

**Verification.** `bash tools/build_all.sh --asset cow` (565 s, `build/cow/logs/build_all_run.out`): every step ok,
`QA GATE: pass (25 clips)`, validator 266 PASS / 0 FAIL / 0 WARN (FBX skin 0.018 mm, GLB 0.069 mm, Khronos 0 errors),
`T_Cow_BaseColor` 4096. Family QA on the cow's stage B: all BOUNDARY / SEAM / RESIDUAL 0.0000 (Leap end 0.0006 mm
root-relative); lying `JOINT limits: all OK` (GetUp LF fetlock -60.6 deg); TURN f56 0.0005 mm; the new cow values are in
CLAUDE.md "Adult cow". Calf: `bash tools/build_all.sh` rebuilt after the change (`build/logs/build_all_run3.out`, 419 s):
`QA GATE: pass (25 clips)`, validator 267 PASS / 0 FAIL / 0 WARN, as checkpoint 02. Its textures equal the committed ones
except one texel of BaseColor and one of Normal (1/255: bake noise); the FBX / manifest differ only in export
timestamps. The committed `Unity/Calf` (checkpoint 02) was therefore kept as is.
Renders (walk, death filmstrips; export contact sheets) checked by eye against the GiM stills (28 s, 11.5 s).

**Open.** OI-45..OI-49 (tempo of the key-pose clips, udder in the ground while lying, Idle source over-reach, Death
impact frame and two reach clamps, procedural coat). OI-01 covers `CowSetup.cs` too (not compiled here: no C# compiler
in this session).

