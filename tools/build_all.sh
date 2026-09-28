#!/usr/bin/env bash
# Full calf pipeline: cow.glb -> Unity/Calf (FBX + GLB + textures). Logs in build/logs/.
# Usage: bash tools/build_all.sh [--tex-res 4096] [--skip-textures]
set -euo pipefail
cd "$(dirname "$0")/.."
RES=4096; SKIP_TEX=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --tex-res) RES="$2"; shift 2;;
    --skip-textures) SKIP_TEX=1; shift;;
    *) echo "unknown arg $1"; exit 2;;
  esac
done
mkdir -p build/logs
run() { local name="$1"; shift; echo "[build_all] $name ..."; local t0=$SECONDS
        if ! "$@" > "build/logs/$name.log" 2>&1; then echo "[build_all] $name FAILED (see build/logs/$name.log)"; tail -20 "build/logs/$name.log"; exit 1; fi
        echo "[build_all] $name ok ($((SECONDS - t0)) s)"; }
run stage_a    python3 tools/calf_stage_a.py
run stage_b    python3 tools/calf_stage_b.py
if [[ $SKIP_TEX -eq 0 ]]; then
  run textures python3 tools/calf_textures.py --in build/stage_b.blend --out build/stage_c.blend --tex-dir build/textures --res "$RES"
else
  # stage C stores its own copy of the mesh: rebuild it from the NEW stage B with the existing materials
  # (refuses if stage B's UV layout changed, since the old textures would no longer fit)
  run relink   python3 tools/relink_materials.py --stage-b build/stage_b.blend --old-c build/stage_c.blend --out build/stage_c.blend
fi
run fur_tex    python3 tools/calf_fur_textures.py --in build/stage_b.blend --tex-dir build/textures
run animations python3 tools/calf_animations.py --in build/stage_c.blend --out build/stage_d.blend
run export     python3 tools/export_unity.py --in build/stage_d.blend --out-dir Unity/Calf --tex-dir build/textures
run validate   python3 tools/validate_export.py --fbx Unity/Calf/Calf.fbx --glb Unity/Calf/Calf.glb --src build/stage_d.blend \
                 --json build/logs/validate_report.json --render-dir build/export_check
grep -E "PASS|FAIL|WARN" build/logs/validate.log | tail -5 || true
stamp=$(date +%Y%m%d-%H%M%S)             # keep every validation result (the next build overwrites validate.log)
cp build/logs/validate.log "build/logs/validate-$stamp.log"
cp build/logs/validate_report.json "build/logs/validate_report-$stamp.json" 2>/dev/null || true
echo "[build_all] done -> Unity/Calf"
