# Young Cow (Calf) for Unity: Build Plan

**Decision:** build in-house. Target quality and content: GiM Studio *Animalia - Cow (young)*.
References are in the repo root: `Gemini_Generated_Image_*.png`, `2259689e-*.webp`, `Young Cow animation preview.mp4`,
`videoplayback (1).mp4` (young cow, 1080p) and `videoplayback.mp4` (adult female cow).
Everything is produced by Python scripts in `tools/`, which drive Blender 5 headless (`bpy`), so each stage is repeatable and tunable.

## Deliverable (what "done" means)

| Area | Target |
|---|---|
| Mesh | Young cow, real scale (~1.0 m withers), LOD0 ~45k tris, LOD1 ~12k tris, LOD2 ~2.7k tris; eyes as separate spheres |
| Textures | 4K BaseColor / Normal (OpenGL) / HDRP MaskMap / URP MetallicSmoothness; eye texture; red-pied coat matching the refs |
| Fur | Unity shell-fur material for LOD0 (URP), plus alpha fur cards for the forehead tuft, ear fringe and tail switch |
| Rig | Existing 43-bone quadruped rig (kept for compatibility) + Jaw + Ear.L/R bones; Generic rig in Unity with `Root` as the root node |
| Animations | Walk, Trot, Gallop, TurnLeft/TurnRight, Idle, Idle_LookAround, Graze_Start/Loop/End, Eating, LieDown, Lying_Idle, GetUp, Death, Leap. Locomotion exported with and without root motion. 30 fps |
| Unity | FBX + textures; Editor script that builds materials, the LODGroup, an Animator Controller (speed/turn blend tree + states) and a prefab |

## Phases

1. **Model.** Reshape the adult cow cage into a calf (`calf_stage_a.py`, `calf_stage_b.py`). Done: proportions matched to the side-view silhouette, eyes, UVs, LODs.
2. **Textures.** Procedural coat from a baked rest-position map (`calf_textures.py`): white blaze, shoulder band, belly, hip band, white lower legs, tail switch, pale muzzle and hooves, and a fur-direction normal map.
3. **Rig upgrade.** Add Jaw (chewing while grazing) and Ear.L/R (ear flicks), with weights from head-region distance fields. Re-add leg IK (chains to the IKFrontLeg/IKBackLeg targets) as a Blender authoring rig, and bake to FK for export.
4. **Animation set.** Built by a procedural quadruped gait generator:
   - Foot phase offsets: walk is a lateral 4-beat, trot diagonal pairs, gallop a transverse 4-beat with suspension.
   - Foot arcs are solved with IK. The spine, neck and head counter-motion and the tail sway follow the gait phase.
   - Stride length and cadence are tuned per gait at calf scale.

   Poses and transitions (graze, lie down, get up, death, leap) are keyframed from key poses with IK. A cow gets up **hind end first** and lies down **front knees first**.
   Loops are checked for seamless first/last frames. Root-motion versions move `Root`; in-place versions keep it at the origin.
5. **Fur and shading.** URP shell-fur shader (8–16 shells, density/length from a fur mask) on LOD0; fur cards generated in Blender.
6. **Unity integration.** Exporter + validator (`export_unity.py`, `validate_export.py`), plus a Unity Editor setup script and `Unity/Calf/README.md`.
7. **Review.** Multi-lens adversarial review of each phase: visual match to the refs, rig/skin integrity, animation quality (foot sliding, ground contact, loop seams), Unity import readiness.

## Known limits of this approach (and mitigations)

- **No sculpted high-poly.** Anatomy comes from the reshaped cage plus procedural normal detail. Mitigation: add anatomical landmarks (shoulder, hip points, knees, hocks, neck folds) as displacement baked into the normal map.
- **Unity isn't available in this container.** C# and shaders are written against the documented URP/Unity APIs but can't be compiled here. Plan one Unity import pass on a dev machine to confirm them.
- **Animation is procedural plus key poses, not mocap.** Gaits are physically structured and cleanly looped. Transitions will need an animator's polish pass for hero close-ups.
