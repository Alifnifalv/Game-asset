"""Which animal the pipeline builds: the young cow (calf, default), the adult cow or the Rottweiler (dog).

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
  dog   the male Rottweiler: tools/dog/ builds its own mesh (SDF anatomy), rig and clips at final size (no stage E);
        the exporter and the validator are shared. Objects RottweilerRig / Rottweiler_LOD0..2 / M_Rottweiler_Body /
        M_Rottweiler_Eye; output Unity/Rottweiler, intermediates in build/dog/.
  raven the common raven: tools/raven/ (SDF body + modelled feather strips on per-feather bones, its own rig, textures
        and clips) at final size; shared exporter and validator. Objects RavenRig / Raven_LOD0..2 / M_Raven_Body /
        M_Raven_Feather / M_Raven_Eye; output Unity/Raven, intermediates in build/raven/.
The calf/cow Blender object names stay CalfRig / Calf_LOD0..2 / M_Calf_Body / M_Calf_Eye through stages A-D for both animals
(every tool relies on them); only stage E renames the cow's.
"""
import os

ASSET = os.environ.get("ASSET", "calf").strip().lower()
if ASSET not in ("calf", "cow", "dog", "raven"):
    raise SystemExit(f"ASSET must be 'calf', 'cow', 'dog' or 'raven' (got {ASSET!r})")
IS_COW = ASSET == "cow"
IS_DOG = ASSET == "dog"       # the Rottweiler: its own mesh/rig/clip pipeline (tools/dog/), shared exporter + validator
IS_RAVEN = ASSET == "raven"   # the raven: its own pipeline (tools/raven/), shared exporter + validator

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAME = {"cow": "Cow", "dog": "Rottweiler", "raven": "Raven"}.get(ASSET, "Calf")     # exported file / object prefix
BUILD = os.path.join(ROOT, "build", ASSET) if ASSET != "calf" else os.path.join(ROOT, "build")
UNITY_DIR = os.path.join(ROOT, "Unity", NAME)
TEX = "T_" + NAME                                      # texture prefix: T_Calf_BaseColor / T_Cow_BaseColor
TEX_EYE = "T_" + NAME + "Eye"

# Adult Simmental cow: withers ~1.42 m (GiM "Cow" adult female). The authoring rig has withers ~1.0 m.
FINAL_SCALE = 1.42 if IS_COW else 1.0
# Dynamic similarity (equal Froude number): a body S times larger moves with cycle times sqrt(S) longer.
TIME_SCALE = FINAL_SCALE ** 0.5

# face attribute orig_part values (0-4 shared, see CLAUDE.md; 5-6 exist only on the cow)
PART_HORN, PART_UDDER = 5, 6
