#!/usr/bin/env bash
# Full pipeline: cow.glb -> Unity/Calf (young cow, default) or Unity/Cow (adult cow, --asset cow): FBX + GLB + textures;
# --asset dog: the Rottweiler (tools/dog/: SDF anatomy -> mesh, rig, textures, clips) -> Unity/Rottweiler;
# --asset raven: the common raven (tools/raven/: SDF body + feather strips, 122-bone rig, textures, clips) -> Unity/Raven.
# Logs in build/logs/ (calf), build/cow/logs/ (cow), build/dog/logs/ (dog) or build/raven/logs/ (raven).
# Usage: bash tools/build_all.sh [--asset calf|cow|dog|raven] [--tex-res 4096] [--skip-textures]
#                                [--build-dir DIR] [--out-dir DIR]   (dog / raven: a scratch build, intermediates and
#                                                                     deliverables elsewhere; defaults build/<asset>, Unity/<Name>)
set -euo pipefail
cd "$(dirname "$0")/.."
RES=4096; SKIP_TEX=0; ASSET=calf; BDIR=""; ODIR=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --asset) ASSET="$2"; shift 2;;
    --tex-res) RES="$2"; shift 2;;
    --skip-textures) SKIP_TEX=1; shift;;
    --build-dir) BDIR="$2"; shift 2;;
    --out-dir) ODIR="$2"; shift 2;;
    *) echo "unknown arg $1"; exit 2;;
  esac
done
export ASSET          # read by tools/asset_profile.py in every step
case "$ASSET" in
  calf) B=build; OUT=Unity/Calf; NAME=Calf;;
  cow)  B=build/cow; OUT=Unity/Cow; NAME=Cow;;
  dog)  B=build/dog; OUT=Unity/Rottweiler; NAME=Rottweiler;;
  raven) B=build/raven; OUT=Unity/Raven; NAME=Raven;;
  *) echo "unknown asset $ASSET (calf|cow|dog|raven)"; exit 2;;
esac
if [[ -n $BDIR || -n $ODIR ]]; then     # calf_stage_a.py has no --out: the calf / cow always build in build/(cow/)
  [[ $ASSET == dog || $ASSET == raven ]] || { echo "--build-dir / --out-dir: dog or raven only"; exit 2; }
  if [[ -n $BDIR ]]; then B="$BDIR"; fi
  if [[ -n $ODIR ]]; then OUT="$ODIR"; fi
fi
mkdir -p "$B/logs"
run() { local name="$1"; shift; echo "[build_all] $name ..."; local t0=$SECONDS
        if ! "$@" > "$B/logs/$name.log" 2>&1; then echo "[build_all] $name FAILED (see $B/logs/$name.log)"; tail -20 "$B/logs/$name.log"; exit 1; fi
        echo "[build_all] $name ok ($((SECONDS - t0)) s)"; }
if [[ $ASSET == dog || $ASSET == raven ]]; then   # own stages A-D (tools/dog/ or tools/raven/), then the shared export
  T=tools/$ASSET                   # tools/dog/dog_*.py, tools/raven/raven_*.py (same command lines)
  run stage_a    python3 "$T/${ASSET}_stage_a.py" --out "$B/stage_a.npz"
  run stage_b    python3 "$T/${ASSET}_stage_b.py" --in "$B/stage_a.npz" --out "$B/stage_b.blend"
  if [[ $SKIP_TEX -eq 0 ]]; then
    run textures python3 "$T/${ASSET}_textures.py" --mesh "$B/stage_a.npz" --in "$B/stage_b.blend" \
                   --out "$B/stage_c.blend" --tex-dir "$B/textures" --res "$RES"
  else
    run textures python3 "$T/${ASSET}_textures.py" --mesh "$B/stage_a.npz" --in "$B/stage_b.blend" \
                   --out "$B/stage_c.blend" --tex-dir "$B/textures" --res "$RES" --relink-only
  fi
  run animations python3 "$T/${ASSET}_animations.py" --in "$B/stage_c.blend" --out "$B/stage_d.blend"
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
