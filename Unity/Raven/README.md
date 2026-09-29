# Common raven: Unity package notes

A game-ready common raven (*Corvus corax*): model with 3 LODs, modelled feathers, 4K PBR textures, a 122-bone rig and 24
clips (ground and flight). Look target: GiM Studio's *Animalia - Raven* (the stills and `videoplayback (6).mp4` in
`ravan/`; the measured spec is `docs/raven_reference.md`). It is built in-house by
`bash tools/build_all.sh --asset raven` (`tools/raven/`). Everything in this folder except `Editor/` and this README is
written by `tools/export_unity.py` and checked by `tools/validate_export.py`. Unity is not installed in the build
container, so the Unity-side steps are **[not verified in Unity]** (as for the calf, the cow and the Rottweiler).

The FBX conventions, import settings and LOD setup are the calf's (`Unity/Calf/README.md`, same exporter); this file
lists what differs for the raven: the rig, the feather material, the clips and the ground + air Animator.

## Folder contents

| File | What |
|---|---|
| `Raven.fbx` | Main asset: the `RavenRig` skeleton (122 bones), the skinned meshes `Raven_LOD0/1/2` and 24 takes named like the clips. |
| `Raven.glb` | glTF 2.0 binary: rig, `Raven_LOD0`, every clip, textures embedded at 2048 px (eye 1024); the feather material is `alphaMode MASK` (cutoff 0.5). |
| `Textures/` | Body set `T_Raven_*` and feather-atlas set `T_Raven_Feather_*`: `BaseColor` (sRGB; the feather one is RGBA, **A = cutout**), `Normal` (tangent space, OpenGL +Y), `MetallicSmoothness` (URP / Built-in: A = smoothness), `MaskMap` (HDRP: G = AO, A = smoothness), `SpecularSmoothness` (Specular setup: RGB = tinted F0, A = smoothness), `AO`, `Roughness` (4096); `T_RavenEye_BaseColor` (1024). |
| `Editor/RavenSetup.cs` | Menu **Tools > Raven > Setup Raven Asset**: importer settings (Generic rig, Root node = `Root`, per-clip loop / root motion), materials for URP / HDRP / Built-in (feathers cut out), `Raven.controller`, `Raven.prefab` (namespace `RavenAsset.EditorTools`, so it can live next to the other animals). |
| `Raven_export_manifest.json` | Export record (bones, clips with frame ranges / loop / root-motion flags, LOD triangle counts, weights, GLB texture reduction, FBX options). |

## The model

```
Raven               model root (Unity adds the LODGroup here)
├─ RavenRig         armature node: identity transform, scale 1; Root = the Avatar's root (root-motion) bone
├─ Raven_LOD0       SkinnedMeshRenderer, ~44k tris (body ~19k, feather strips ~25k)
├─ Raven_LOD1       SkinnedMeshRenderer, ~12k tris
└─ Raven_LOD2       SkinnedMeshRenderer,  ~3.3k tris (remiges, rectrices and a few coverts; the rest culled)
```
- Faces **+Z**, Y up, meters, stands on y = 0. Bill tip to tail tip 0.62 m, crown 0.39 m. The **bind pose has the wings
  spread** (span 1.08 m, the glide planform); every ground clip folds them, so the model preview in the Inspector shows
  a spread-winged bird while the Animator's Idle shows it perched.
- All-black plumage with a violet (head, mantle) / blue-violet (wings) sheen, warm brown-black breast and belly; slate-grey
  legs and feet with black claws; a dark umber iris in a pale-grey lid ring (separate eyeballs, `Eye.L/R`).
- Feathers: every remex, rectrix, covert, the alula, scapulars, throat hackles and nasal bristles are modelled strips
  (closed: an upper and a lower sheet with their own atlas slots), each rigid on its own bone or on its wing bone; the
  marginal and lesser coverts along the leading edge are a constant blend of the covert pivot bones (see Rig), so each
  turns about its own root when the wing folds.
- Materials, three submeshes per LOD (the exporter writes them in this order): `M_Raven_Feather` (**Cutout**: alpha
  clipping at 0.5 from the feather BaseColor alpha, back faces culled), `M_Raven_Eye`, `M_Raven_Body` (opaque).
- Skinning: at most 4 influences per vertex on every LOD (the Blender preview deforms exactly as Unity).

## Rig (122 bones)

`Root` (ground, root motion) > `Hips` (the body root) > `Spine1` > `Spine2` > `Neck1` > `Neck2` > `Neck3` > `Head` >
`Jaw`, `Throat` (hackles), `Eye.L/R`, `Lid.L/R` (unweighted, reserved for eyelids);
`Hips` > `TailBase` > `Tail` > `Rect1-6.L/R` (the 12 rectrices);
`Spine2` > `Shoulder.X` > `UpperArm.X` (+ `Tert1-3.X`, `CovU1-4.X`) > `Forearm.X` (+ `Sec1-6.X`, `CovF1-4.X`) > `Hand.X`
(+ `Prim01-10.X`, `Alula.X`, `CovH1-4.X`);
`Hips` > `Thigh.X` > `Shin.X` > `Tarsus.X` > `Toe1a-4a.X` > `Toe1b-4b.X`. `.L` is the raven's left. Bones are not
connected. Every clip is baked to FK keys on every frame (no constraints).
`Cov{U,F,H}1-4.X` are the covert pivot bones: per arm segment a 2 x 2 grid of bones at the corners of the leading-edge
covert band, keyed with the fold rotation of a reference remex (Tert2 / Sec3 / Prim01). The marginal and lesser coverts
are skinned to the four with the bilinear weights of their roots, so the blend is a rigid turn about each feather's own
root: in the fold they stay on the arm and lie along the folded remiges (rigid on a remex they would swing about its
base, 3-5 cm off). In the bind pose and the spread-wing clips they do not move. `Lid.L/R` are placeholders (no
weights, no keys: the raven does not blink yet and the dead eyes stay open).

## Clips

| Clip | Frames | Loop | Root motion | Notes |
|---|---|---|---|---|
| `Idle` | 120 | yes | - | perched: breathing, small head saccades, a tail flick |
| `Idle_Look` | 180 | yes | - | head saccades left / right / tilt |
| `Caw` | 45 | once | - | bow, bill open, hackles puff |
| `Eat` | 96 | yes | - | pecking bout, swallow, look |
| `Drink` | 90 | yes | - | dip, raise the bill to swallow |
| `Walk` / `Walk_IP` | 30 | yes | 0.16 m/s | one stride of 0.16 m |
| `Hop` / `Hop_IP` | 20 | yes | 0.45 m/s | two-footed hop, 0.30 m |
| `Turn_L90` / `Turn_R90` | 30 | once | yaw 90 deg | two steps on the spot |
| `Attack` | 48 | once | 0.15 m forward | crouch, wing flare, lunge-hop, recover |
| `Hit_L` / `Hit_R` | 15 | once | - | hit on the left / right side: flinch away, wings jerk half open |
| `Death_L` / `Death_R` | 45 | once | - | collapse onto the left / right side; the last frame is the dead pose |
| `TakeOff` | 45 | once | 5.1 m forward, 1.3 m up | crouch, spring, 2 climbing beats; ends on `Fly` frame 0 at 8 m/s |
| `Fly` / `Fly_IP` | 20 | yes | 8 m/s | one cruise wingbeat (GiM's 1.5 Hz) |
| `Glide` / `Glide_IP` | 120 | yes | 8 m/s | wings flat, fingers slotted, a slow float |
| `Glide_Bank_L` / `Glide_Bank_R` | 60 | yes | 8 m/s, yaw 37 deg/s | a coordinated 28 deg bank |
| `Land` | 45 | once | 4.8 m forward, 1.2 m down | glide-in, flare, braking beats, touchdown, fold to the standing pose |

`_IP` clips are in-place twins (Root still) of the root-motion clips; the Animator uses the root-motion ones. The
`_IP` gaits are for game code that moves the object itself at the clip's speed: played in place their feet slide by
design (Walk_IP about 5 mm per frame, Hop_IP up to 14 mm per frame). Ground clips start and end on the standing pose
(`Idle` frame 0; `Walk` starts in its own double-support phase); flight clips start and end on the neutral flight pose
(`Fly` frame 0), so the flight states hand over at the end of a wingbeat without a pose jump.
**Vertical root motion:** `TakeOff` climbs 1.30 m and `Land` descends 1.20 m (4.8 m forward), so a TakeOff -> flight ->
Land cycle ends 0.10 m above its start unless the game changes the altitude: clear `IsFlying` when the raven is 1.2 m
above the landing spot and snap to the ground on landing (or correct the height in `OnAnimatorMove`).
**Renaming:** all clip names used by the setup script are the constants of class `C` at the top of `RavenSetup.cs`,
and their loop / root-motion kinds are the `ClipSpec` rows below them (the manifest still wins for the loop and
root-motion flags). Change both there if the clip set changes.

## Import settings (set by `RavenSetup.cs`)

- Rig: Generic, Avatar from this model, **Root node = `Root`**, Strip Bones off (`Root` and `Lid.L/R` carry no weights).
- Per clip (Animation tab > Root Transform): rotation baked unless the clip turns (`Turn_L90/R90`, `Glide_Bank_L/R`);
  XZ baked unless it translates; **height (Y) applied only for `TakeOff` and `Land`** (the root climbs 1.3 m / descends
  1.2 m), baked for everything else. Loop Time from the manifest; Loop Pose off (the seams are exact).
- Textures: normal maps as Normal Map, data maps linear, BaseColors sRGB, 4096 max; the feather BaseColor keeps its
  alpha (Alpha Source = Input, not "Alpha is Transparency") with **Mip Maps Preserve Coverage** at 0.5, so the frayed
  feather edges do not erode at a distance.
- Materials: URP Lit / HDRP Lit / Built-in Standard, metallic workflow (the albedo carries the sheen tints). The
  feather material: URP `Alpha Clipping` 0.5, HDRP `Alpha Clipping` 0.5, Built-in `Rendering Mode = Cutout` 0.5; queue
  AlphaTest; single-sided (the strips are closed). `UseSpecularSetup = true` in the script switches URP / Built-in to
  the specular workflow with the `SpecularSmoothness` maps (spec 5.2).

## Animator Controller (built by `RavenSetup.cs`)

One layer, two groups of states (flat: every transition is a plain state-to-state one).

- Parameters: floats `Speed` (m/s on the ground), `Turn` (-1 left .. +1 right: ground turns and the air bank), `Flap`
  (0 glide .. 1 flapping; **default 1**), `WalkRate` / `HopRate` (playback speed of the gaits, default 1); bools
  `IsFlying`, `LookAround`, `Left` (the side for `Hit` / `Die`); triggers `Caw`, `Eat`, `Drink`, `Attack`, `Hit`, `Die`.
- **Ground** (tag `Ready`): `Idle` (default) -> `Walk` above 0.04 m/s; `Walk` -> `Hop` above 0.30 m/s and `Walk` ->
  `Idle` below 0.02 m/s, both only at a Walk double support (normalised time 0.28 / 0.78: f8.5 / f23.5 of 30, both feet down until f15 / f30); `Hop` -> `Walk` below
  0.26 m/s and `Hop` -> `Idle` below 0.02 m/s at the end of a hop (0.95, both feet down). Walk and Hop are **separate
  states, not a blend**: the alternating 30 f walk and the two-footed 20 f hop cannot be mixed (a normalised-time blend
  half-alternates the feet and skates them). They play at their export speeds (0.16 / 0.45 m/s); to follow other
  speeds set `WalkRate = Speed / 0.16` (about 0.7-1.4) and `HopRate = Speed / 0.45`. `Idle_Look` while `LookAround`.
  `Turn_L90` / `Turn_R90` from Idle while `Turn` < -0.5 / > 0.5 (repeats while held). One-shots `Caw`, `Eat`,
  `Drink`, `Attack` (triggers; `Eat` / `Drink` play one full bout), `Hit` -> `Hit_L` / `Hit_R` by `Left`; back to Idle
  / Walk at 95 %. `Die` -> `Death_L` / `Death_R` by `Left` (tag `Dead`, final) from every ground state.
- **Air** (tag `Air`): `IsFlying` = true -> `TakeOff` (from Idle / Walk / Hop / Idle_Look) -> `Fly` at the end of the
  climb (TakeOff ends exactly on Fly frame 0, pose, phase and speed). `Fly` (the wingbeat) and `Glide` (a 1D blend
  tree on `Turn`: -1 `Glide_Bank_L`, 0 `Glide`, +1 `Glide_Bank_R`) are **separate states**: `Fly` -> `Glide` when
  `Flap` < 0.5 at the end of a wingbeat (Fly f20 = Glide f0), `Glide` -> `Fly` when `Flap` > 0.5 (into the start of a
  beat). They are not blended on `Flap`: the 20 f beat and the 120 f glide would play at a common normalised speed (the
  beat 3x slower). `IsFlying` = false -> `Land` (from `Glide` at once, from `Fly` at the end of a wingbeat) -> Idle /
  Walk. Drive `Turn` with damping (`Animator.SetFloat("Turn", value, 0.3f, Time.deltaTime)`): the bank children
  (60 f) and `Glide` (120 f) blend at a common normalised speed.
- Game code: root motion is on. While flying, turn off gravity (or use a kinematic body): `TakeOff` / `Land` move the
  root vertically, `Fly` / `Glide` are level; altitude changes in cruise are the game's (or add them in
  `OnAnimatorMove`). `Hit` and `Die` have no air transitions (there is no `Death_Fly` clip yet): a trigger set in the
  air fires after landing unless it is reset (`Animator.ResetTrigger`).

## LODs

LODGroup thresholds 25 % / 8 % / 1 % of screen height (lower than the calf's: a 0.6 m bird), LOD1 and LOD2 decimated
from LOD0 with the same UV atlases. The feather strips are culled by their `Feather.lod` (`tools/raven/plumage.py`):
LOD1 drops some coverts, scapulars, hackles and bristles, LOD2 keeps the remiges, the rectrices and a few coverts
(the alula is not on LOD2: `Alula.L/R` have no weights there).

## Verification

Full build `bash tools/build_all.sh --asset raven` of 2026-09-29 (run output `build/raven/logs/build_all_run.out`,
about 6.6 min: stage A 56 s, stage B 1 s, textures 173 s, clips 8 s, export 46 s, validator 113 s):
- Raven QA gate (`tools/raven/raven_animations.py`): **pass (24 clips)**. TakeOff end vs `Fly` f0 0.0006 mm, Land end
  vs the standing pose 0.0009 mm.
- Validator: **268 PASS / 0 FAIL / 0 WARN**. Khronos glTF-Validator 0 errors / 0 warnings / 1 info
  (UNUSED_MESH_TANGENT). `T_Raven_BaseColor` 4096 x 4096 (all body and feather maps 4096, the eye 1024).
- LOD tris 43,580 / 11,778 / 3,286 (LOD0: body, claws, eyes and bill 18,848, feather strips 24,732). `Raven.fbx`
  30.3 MB, `Raven.glb` 18.7 MB (7 images: body and feather sets at 2048, eye 1024; about 140 MB decoded).
- Death_L / R: the dead toes follow the tarsus (`LegPose.local` = 1, blended in over f4-20). Leg twist 24.6 deg per
  frame (Shin, limit 25), toes 16.8 deg per frame, at most 77 deg against the tarsus (limit 90).
- Folded wing: the marginal / lesser coverts sit on the covert pivot bones (see Rig), so they stay on the arm when it
  folds (no longer a fanned stack of plates in front of the wrist).
- Spread wing: no see-through gaps in the wing in `Fly`, `Glide`, the banks, `TakeOff` or `Land`. Measured with the
  bird rendered from above and below (1 px = 6.25 mm2), counting enclosed background regions over 4 px: 0 on Fly
  f0/4/12/16, Glide f0/30/60, Glide_Bank_L f20 and Land f5, where the first build had 5, 3, 5 and 5. Fly f8 and TakeOff
  f30 (the upstroke, wings swept back beside the fanned tail) still show 4 regions each. These are gaps between the
  wing's trailing edge and the tail, not holes in a surface. A marginal-covert row now feathers the leading edge.
- Closed tail (Idle f0, LOD0): 0.059 / 0.062 / 0.064 m wide at 0.3 / 0.5 / 0.7 of its length, 0.037 m at the tip
  (spec 4.8: 0.055-0.065). The rectrix roots converge on the pygostyle and the closed angles are 0-1.6 deg. Flight
  tail fan: 0.80 (R6 about 29 deg off the axis; the banks 0.87, the glide 0.80-0.90).
- TakeOff lift-off: the leg push hands its speed to the root (0.6 m/s forward, 0.8 m/s up at f10). Spine1 speed rises
  steadily through the launch: 2.8, 4.3, 8.6, 16.1, 26.8, 37.0 and 44.7 mm per frame over f6-12. The first build
  dropped from 16 to 4 mm per frame at f10 and then jumped to 68.
- Raven-specific validator settings (`AP.IS_RAVEN` in `tools/validate_export.py`):
  - key bones Head, Toe3b.L/R, Hand.L/R and Rect1.L;
  - a twist gate on the leg chain (Thigh / Shin / Tarsus / toes) at 25 deg per frame;
  - wing bones, including the covert pivots, WARN above 60 deg per frame (FK fold slerps: fast but flip-free);
  - boundaries vs `Idle` f0 (ground one-shots, the TakeOff start, the Land end) and vs `Fly` / `Glide` f0 (flight
    loops, the TakeOff end, the Land start);
  - `TakeOff` / `Land` may move the Root vertically;
  - rest size window H 0.33-0.45 m, L 0.52-0.70 m, span 1.00-1.20 m;
  - a GLB texture-memory warning at 150 MB (two texture sets).

## Known issues / not verified
- Nothing has been imported into Unity yet (OI-01 applies). Unchecked: the importer settings, the Avatar root node,
  root motion (including TakeOff / Land's vertical motion), the Animator (Walk / Hop and Fly / Glide state switching,
  exit times, `WalkRate` / `HopRate`), the cutout feather materials in URP / HDRP / Built-in, and the LODGroup.
  `RavenSetup.cs` compiles with Roslyn against minimal Unity API stubs but has not run in Unity.
- Close up, the folded wing's carpal still reads as layered small covert plates: the leading-edge band folds as rigid
  feathers over the thick arm skin. It is no longer the fanned card stack of the first build. A fold corrective (a
  flatter folded arm skin, or a sculpted carpal mass) would smooth it.
- Walk has no start / stop clips: the Idle <-> Walk crossfade (at a double support) still slides a planted foot a few
  centimetres. `Lid.L/R` are placeholders.
- The feathers are single-sided closed strips: the underside has its own paler atlas slots. A Cull Off feather shader
  would halve the feather triangles but needs a custom shader (spec 5.2).
