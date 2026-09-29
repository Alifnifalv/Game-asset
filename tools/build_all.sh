#!/usr/bin/env bash
# Full pipeline: cow.glb -> Unity/Calf (young cow, default) or Unity/Cow (adult cow, --asset cow): FBX + GLB + textures;
# --asset dog: the Rottweiler (tools/dog/: SDF anatomy -> mesh, rig, textures, clips) -> Unity/Rottweiler.
# Logs in build/logs/ (calf), build/cow/logs/ (cow) or build/dog/logs/ (dog).
# Usage: bash tools/build_all.sh [--asset calf|cow|dog] [--tex-res 4096] [--skip-textures]
set -euo pipefail
cd "$(dirname "$0")/.."
RES=4096; SKIP_TEX=0; ASSET=calf
while [[ $# -gt 0 ]]; do
  case "$1" in
    --asset) ASSET="$2"; shift 2;;
    --tex-res) RES="$2"; shift 2;;
    --skip-textures) SKIP_TEX=1; shift;;
    *) echo "unknown arg $1"; exit 2;;
  esac
done
export ASSET          # read by tools/asset_profile.py in every step
case "$ASSET" in
  calf) B=build; OUT=Unity/Calf; NAME=Calf;;
  cow)  B=build/cow; OUT=Unity/Cow; NAME=Cow;;
  dog)  B=build/dog; OUT=Unity/Rottweiler; NAME=Rottweiler;;
  *) echo "unknown asset $ASSET (calf|cow|dog)"; exit 2;;
esac
mkdir -p "$B/logs"
run() { local name="$1"; shift; echo "[build_all] $name ..."; local t0=$SECONDS
        if ! "$@" > "$B/logs/$name.log" 2>&1; then echo "[build_all] $name FAILED (see $B/logs/$name.log)"; tail -20 "$B/logs/$name.log"; exit 1; fi
        echo "[build_all] $name ok ($((SECONDS - t0)) s)"; }
if [[ $ASSET == dog ]]; then       # the Rottweiler has its own stages A-D (tools/dog/), then the shared export
  run stage_a    python3 tools/dog/dog_stage_a.py --out "$B/stage_a.npz"
  run stage_b    python3 tools/dog/dog_stage_b.py --in "$B/stage_a.npz" --out "$B/stage_b.blend"
  if [[ $SKIP_TEX -eq 0 ]]; then
    run textures python3 tools/dog/dog_textures.py --mesh "$B/stage_a.npz" --in "$B/stage_b.blend" \
                   --out "$B/stage_c.blend" --tex-dir "$B/textures" --res "$RES"
  else
    run textures python3 tools/dog/dog_textures.py --mesh "$B/stage_a.npz" --in "$B/stage_b.blend" \
                   --out "$B/stage_c.blend" --tex-dir "$B/textures" --res "$RES" --relink-only
  fi
  run animations python3 tools/dog/dog_animations.py --in "$B/stage_c.blend" --out "$B/stage_d.blend"
  SRC="$B/stage_d.blend"
  run export     python3 tools/export_unity.py --in "$SRC" --out-dir "$OUT" --tex-dir "$B/textures"
  run validate   python3 tools/validate_export.py --fbx "$OUT/$NAME.fbx" --glb "$OUT/$NAME.glb" --src "$SRC" \
                   --json "$B/logs/validate_report.json" --render-dir "$B/export_check"
  grep -E "PASS|FAIL|WARN" "$B/logs/validate.log" | tail -5 || true
  stamp=$(date +%Y%m%d-%H%M%S)
  cp "$B/logs/validate.log" "$B/logs/validate-$stamp.log"
  cp "$B/logs/validate_report.json" "$B/logs/validate_report-$stamp.json" 2>/dev/null || true
  echo "[build_all] done -> $OUT"
  exit 0
fi
run stage_a    python3 tools/calf_stage_a.py
run stage_b    python3 tools/calf_stage_b.py --in "$B/stage_a.blend" --out "$B/stage_b.blend"
if [[ $SKIP_TEX -eq 0 ]]; then
  run textures python3 tools/calf_textures.py --in "$B/stage_b.blend" --out "$B/stage_c.blend" --tex-dir "$B/textures" --res "$RES"
else
  # stage C stores its own copy of the mesh: rebuild it from the NEW stage B with the existing materials
  # (refuses if stage B's UV layout changed, since the old textures would no longer fit)
  run relink   python3 tools/relink_materials.py --stage-b "$B/stage_b.blend" --old-c "$B/stage_c.blend" --out "$B/stage_c.blend"
fi
if [[ $ASSET == calf ]]; then    # the optional URP shell fur exists for the calf only
  run fur_tex  python3 tools/calf_fur_textures.py --in "$B/stage_b.blend" --tex-dir "$B/textures"
fi
run animations python3 tools/calf_animations.py --in "$B/stage_c.blend" --out "$B/stage_d.blend"
SRC="$B/stage_d.blend"
if [[ $ASSET == cow ]]; then     # stage E: uniform scale to the adult's size + Calf* -> Cow* names
  run scale    python3 tools/scale_asset.py --in "$B/stage_d.blend" --out "$B/stage_e.blend"
  SRC="$B/stage_e.blend"
fi
run export     python3 tools/export_unity.py --in "$SRC" --out-dir "$OUT" --tex-dir "$B/textures"
run validate   python3 tools/validate_export.py --fbx "$OUT/$NAME.fbx" --glb "$OUT/$NAME.glb" --src "$SRC" \
                 --json "$B/logs/validate_report.json" --render-dir "$B/export_check"
grep -E "PASS|FAIL|WARN" "$B/logs/validate.log" | tail -5 || true
stamp=$(date +%Y%m%d-%H%M%S)             # keep every validation result (the next build overwrites validate.log)
cp "$B/logs/validate.log" "$B/logs/validate-$stamp.log"
cp "$B/logs/validate_report.json" "$B/logs/validate_report-$stamp.json" 2>/dev/null || true
echo "[build_all] done -> $OUT"
