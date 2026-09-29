# Young Cow (Calf) for Unity: Build Plan

**Decision:** build in-house. Target quality and content: GiM Studio *Animalia - Cow (young)*.
References are in the repo root: `Gemini_Generated_Image_*.png`, `2259689e-*.webp`, `Young Cow animation preview.mp4`,
`videoplayback (1).mp4` (young cow, 1080p) and `videoplayback.mp4` (adult female cow). Details, a video timestamp index and the
user's close-up spec: `docs/REFERENCES.md`.
Everything is produced by Python scripts in `tools/`, which drive Blender 5 headless (`bpy`), so each stage is repeatable and tunable.

## Deliverable (what "done" means)
Status after the final multi-lens review (the 2026-09-28 18:16 build, to become checkpoint 02). The open items are tracked in `docs/WORKLOG.md` "Open issues" (`OI-nn`).

| Area | Target | Status |
|---|---|---|
| Mesh | Young cow, real scale (~1.0 m withers), LOD0 ~45k tris, LOD1 ~12k tris, LOD2 ~2.7k tris; eyes as separate spheres | done (46.8k / 11.7k / 2.7k); head, ears and eyes re-proportioned, tail switch and forehead tuft modelled in the final review |
| Textures | 4K BaseColor / Normal (OpenGL) / HDRP MaskMap / URP MetallicSmoothness; eye texture; red-pied coat matching the refs | done (anatomical normal detail partly done: neck/throat folds and a mouth crease only, OI-24) |
| Fur | Unity shell-fur material for LOD0 (URP), plus alpha fur cards for the forehead tuft, ear fringe and tail switch | partial: shell fur written (not run in Unity); fur cards not started (OI-23); the tuft and tail switch are mesh shapes |
| Rig | Existing 43-bone quadruped rig (kept for compatibility) + Jaw + Ear.L/R bones; Generic rig in Unity with `Root` as the root node | done (46 bones; 42 exported); every LOD limited to 4 influences, so Blender previews equal Unity |
| Animations | Walk, Trot, Gallop, TurnLeft/TurnRight, Idle, Idle_LookAround, Graze_Start/Loop/End, Eating, Call, HeadShake, LieDown, Lying_Idle, GetUp, Death, Leap. Locomotion exported with and without root motion. 30 fps | done: 25 clips (Call, HeadShake, Stand, Walk_Slow(_RM) and Death_Lying were added to the plan); no in-place Leap (OI-08), no Dead_Idle (OI-09) |
| Unity | FBX + textures; Editor script that builds materials, the LODGroup, an Animator Controller (speed/turn blend tree + states) and a prefab | written and compiled against Unity stubs, not run in Unity (OI-01). The controller has a Speed-only blend tree (Stand, Walk_Slow_RM, Walk_RM, Trot_RM, Gallop_RM plus time-scaled Trot/Gallop copies); turns are trigger states (OI-26) |

## Phases

1. **Model.** *Done.* Reshape the adult cow cage into a calf (`calf_stage_a.py`, `calf_stage_b.py`): proportions matched to the side-view silhouette, eyes, UVs, LODs.
2. **Textures.** *Done.* Procedural coat from a baked rest-position map (`calf_textures.py`): white blaze, shoulder band, belly, hip band, white lower legs, tail switch, pale muzzle and hooves, and a fur-direction normal map.
3. **Rig upgrade.** *Done, with one deviation.* Add Jaw (chewing while grazing) and Ear.L/R (ear flicks), with weights from head-region distance fields. Re-add leg IK (chains to the IKFrontLeg/IKBackLeg targets) as a Blender authoring rig, and bake to FK for export.
   Deviation: there is no persistent IK authoring rig. `tools/anim_lib.py` (and `rebake_leg_ik.py` for the imported clips) adds the IK constraints per clip, bakes them to FK and removes them (OI-25).
4. **Animation set.** *Done (25 clips).* Built by a procedural quadruped gait generator:
   - Foot phase offsets: walk is a lateral 4-beat, trot diagonal pairs, gallop a transverse 4-beat with suspension.
   - Foot arcs are solved with IK. The spine, neck and head counter-motion and the tail sway follow the gait phase.
   - Stride length and cadence are tuned per gait at calf scale.

   Poses and transitions (graze, lie down, get up, death, leap) are keyframed from key poses with IK. A cow gets up **hind end first** and lies down **front knees first**.
   Loops are checked for seamless first/last frames. Root-motion versions move `Root`; in-place versions keep it at the origin.
5. **Fur and shading.** *Partial.* URP shell-fur shader (8–16 shells, density/length from a fur mask) on LOD0: written, not run in Unity. Fur cards generated in Blender: not started (OI-23).
6. **Unity integration.** *Done except the Unity-side check.* Exporter + validator (`export_unity.py`, `validate_export.py`), plus a Unity Editor setup script and `Unity/Calf/README.md`. Nothing has been imported into Unity yet (OI-01).
7. **Review.** *Done.* Multi-lens adversarial review of each phase: visual match to the refs, rig/skin integrity, animation quality (foot sliding, ground contact, loop seams), Unity import readiness. Each clip family had its own review. The final multi-lens review of checkpoint 01 (likeness, animation, export rig, unity code, docs; each "ship with fixes") was integrated and rebuilt; what stays open is in the WORKLOG (OI-35..OI-43).

## Known limits of this approach (and mitigations)

- **No sculpted high-poly.** Anatomy comes from the reshaped cage plus procedural normal detail. Mitigation: add anatomical landmarks (shoulder, hip points, knees, hocks, neck folds) as displacement baked into the normal map. *Partly done: the normal map carries fur-strand height plus neck/throat folds and a mouth crease; the shoulder/hip points, knees and hocks are missing (OI-24).*
- **Unity isn't available in this container.** C# and shaders are written against the documented URP/Unity APIs. Here they can only be compiled against stubs (Roslyn) and the URP ShaderLibrary (DXC), not run. Plan one Unity import pass on a dev machine to confirm them.
- **Animation is procedural plus key poses, not mocap.** Gaits are physically structured and cleanly looped. Transitions will need an animator's polish pass for hero close-ups.
