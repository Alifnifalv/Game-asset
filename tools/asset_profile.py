"""Which animal the pipeline builds: the young cow (calf, default) or the adult cow.

Select it with the environment variable ASSET=calf|cow (tools/build_all.sh --asset cow sets it). Every tool imports
this module, so one build runs one profile end to end.

Both animals come from cow.glb and share the rig, the clip code and the exporter. Differences:
  calf  stage B reshapes the adult source into a calf (withers 1.0 m); no stage E; Unity/Calf, build/
  cow   stage A keeps the horns; stage B keeps the adult proportions and adds a modelled udder with four teats; the
        Simmental coat (tools/calf_textures.py cow branch); adult gait timing (tools/anim_gait.py). The whole
        authoring pipeline (stages A-D, every clip family and QA) runs at the calf's AUTHORING scale (withers
        ~1.0 m), so every tuned distance in the clip code keeps its meaning. Stage E (tools/scale_asset.py) then
        scales the finished rig, meshes and clips uniformly by FINAL_SCALE (exact: rotations unchanged, locations
        scaled) and renames Calf* -> Cow*. Output: Unity/Cow, intermediates in build/cow/.
The Blender object names stay CalfRig / Calf_LOD0..2 / M_Calf_Body / M_Calf_Eye through stages A-D for both animals
(every tool relies on them); only stage E renames the cow's.
"""
import os

ASSET = os.environ.get("ASSET", "calf").strip().lower()
if ASSET not in ("calf", "cow"):
    raise SystemExit(f"ASSET must be 'calf' or 'cow' (got {ASSET!r})")
IS_COW = ASSET == "cow"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAME = "Cow" if IS_COW else "Calf"                     # exported file / object prefix
BUILD = os.path.join(ROOT, "build", "cow") if IS_COW else os.path.join(ROOT, "build")
UNITY_DIR = os.path.join(ROOT, "Unity", NAME)
TEX = "T_" + NAME                                      # texture prefix: T_Calf_BaseColor / T_Cow_BaseColor
TEX_EYE = "T_" + NAME + "Eye"

# Adult Simmental cow: withers ~1.42 m (GiM "Cow" adult female). The authoring rig has withers ~1.0 m.
FINAL_SCALE = 1.42 if IS_COW else 1.0
# Dynamic similarity (equal Froude number): a body S times larger moves with cycle times sqrt(S) longer.
TIME_SCALE = FINAL_SCALE ** 0.5

# face attribute orig_part values (0-4 shared, see CLAUDE.md; 5-6 exist only on the cow)
PART_HORN, PART_UDDER = 5, 6
