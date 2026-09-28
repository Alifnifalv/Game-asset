# Young Cow (Calf) for Unity: Plan

Target quality: GiM Studio **Animalia - Cow (pack)** (Unity Asset Store #170739). References are in the repo root:
`Gemini_Generated_Image_*.png`, `2259689e-*.webp`, `Young Cow animation preview.mp4`, `videoplayback (1).mp4` (young cow, 1080p),
`videoplayback.mp4` (adult female cow).

## 1. Build or buy

| | Animalia Cow (GiM) | This repo's calf (built from `cow.glb`) |
|---|---|---|
| Cost | Young cow $99.99, pack (female + young) €165.60 (store prices at time of writing) | Free; you own the result (check `cow.glb`'s Sketchfab licence) |
| Mesh | Sculpted high-poly baked to game mesh, LODs | Reshaped low-poly cage, subdivided (LOD0 ~47k tris) |
| Textures | 4K, photo-sourced, semi-procedural shader, gFur fur | Procedural red-pied coat, 4K BaseColor/Normal/Mask |
| Rig | Production rig with Maya/Max animation rigs, ragdoll | Original 43-bone quadruped rig, IK baked to FK |
| Animations | Full set at 60 fps, with and without root motion | 2 clips (Eating, Idle) carried over |

**Recommendation:** if the calf is a close-up or hero animal in an AAA-looking game, **buy the Animalia pack**.
Matching it in-house takes a sculpt, retopology, bake, Substance texturing, fur grooming, and a 20+ clip animation set.
That is roughly 6–10 weeks for a senior creature artist plus a creature animator, which costs far more than the asset.
Use the calf built here as a free placeholder, a background/herd animal, or a far LOD, and as a pipeline you control.

## 2. What the Animalia young cow has that this calf does not (gap list)

1. **Anatomy.** Muscle and bone landmarks (scapula, hip points, knees, hocks), skin folds on the neck, and a sculpted face with eyelids, nostrils and lips. Here they are only approximated by the silhouette and normal-map detail.
2. **Fur.** GiM uses gFur shells plus fur-strand textures. Unity options: a URP/HDRP shell-fur shader (8–16 shells on LOD0 only), or hair cards for the forehead tuft, ear fringe and tail switch.
3. **Animation set.** From the preview videos: walk, trot, canter/gallop, leap, graze (head down, loop), eat, idle, look around, ear/tail secondary motion, lie down, lying idle, get up, death. Every locomotion clip comes with and without root motion.
4. **Rig.** Ear, jaw, eyelid and tail-dynamics bones, plus a ragdoll setup.

## 3. Animation plan (next phase)

Tooling: Blender (installed as the `bpy` Python module in the cloud container) for procedural and keyframed clips. For hand-keyed polish, use Blender with Rigify or AutoRig Pro on a workstation. Mocap for quadrupeds is rarely worth the cost.

| Priority | Clip | Method | Notes |
|---|---|---|---|
| P0 | Walk (in place + root motion) | Procedural gait generator: foot phase offsets (LH, LF, RH, RF lateral sequence), foot arcs with IK, spine/neck counter-motion, head bob | Lets the calf move in game at all |
| P0 | Trot | Same generator, diagonal pairs | |
| P0 | Idle variations | Layer ear flicks, tail swish, breathing, weight shifts on the existing Idle | Cheap and adds life |
| P1 | Graze loop | Neck/head down pose + jaw/chew cycle (needs a jaw bone) | Existing "Eating" clip covers part of this |
| P1 | Lie down / lying idle / get up | Key poses + IK, hand-tuned | Needs the most animator time |
| P2 | Gallop, leap, turn in place, death | Keyframed | |

Unity side: Generic rig, `Root` as root node. Build an Animator Controller with a speed blend tree (idle → walk → trot → gallop) and a turn parameter. Use root motion for locomotion, and foot IK (Animation Rigging package, TwoBoneIK per leg with a ground raycast) for uneven terrain. Use a LODGroup built from `Calf_LOD0..2`.

## 4. Calf model pipeline in this repo (current phase)

`tools/calf_stage_a.py` → `tools/calf_stage_b.py` → `tools/calf_textures.py` → `tools/export_unity.py` → `tools/validate_export.py`.
See `Unity/Calf/README.md` for the import settings and `docs/CALF_PIPELINE.md` for how each stage works and how to tune it.
