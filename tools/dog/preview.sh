#!/usr/bin/env bash
# Fast likeness preview of the Rottweiler into a SCRATCH folder (never build/ or Unity/): stages A-D with 1K textures,
# then the reference comparisons (tools/dog/dog_compare.py). About 3-4 min on the 4 shared cores.
# Usage: bash tools/dog/preview.sh <scratch_dir> [--only preset,preset] [--no-compare] [--no-anim-gate]
set -euo pipefail
cd "$(dirname "$0")/../.."
OUT="$1"; shift
ONLY=""; COMPARE=1
while [[ $# -gt 0 ]]; do
  case "$1" in
    --only) ONLY="$2"; shift 2;;
    --no-compare) COMPARE=0; shift;;
    *) echo "unknown arg $1"; exit 2;;
  esac
done
case "$(realpath -m "$OUT")" in
  "$(realpath build)"*|"$(realpath Unity)"*) echo "preview.sh: use a scratch folder, not build/ or Unity/"; exit 2;;
esac
mkdir -p "$OUT"
export ASSET=dog
step() { local n="$1"; shift; local t0=$SECONDS
         if ! "$@" > "$OUT/$n.log" 2>&1; then echo "[preview] $n FAILED ($OUT/$n.log)"; tail -15 "$OUT/$n.log"; exit 1; fi
         echo "[preview] $n ok ($((SECONDS - t0)) s)"; }
step stage_a    python3 tools/dog/dog_stage_a.py --out "$OUT/stage_a.npz"
step stage_b    python3 tools/dog/dog_stage_b.py --in "$OUT/stage_a.npz" --out "$OUT/stage_b.blend"
step textures   python3 tools/dog/dog_textures.py --mesh "$OUT/stage_a.npz" --in "$OUT/stage_b.blend" \
                  --out "$OUT/stage_c.blend" --tex-dir "$OUT/tex" --res 1024 --preview "$OUT/atlas.png"
# the QA gate result is reported, but a preview continues to the comparison even when it fails
if python3 tools/dog/dog_animations.py --in "$OUT/stage_c.blend" --out "$OUT/stage_d.blend" > "$OUT/animations.log" 2>&1; then
  echo "[preview] animations ok: $(grep 'QA GATE' "$OUT/animations.log")"
else
  echo "[preview] animations: $(grep 'QA GATE' "$OUT/animations.log" || tail -3 "$OUT/animations.log")"
fi
if [[ $COMPARE -eq 1 && -f "$OUT/stage_d.blend" ]]; then
  if [[ -n "$ONLY" ]]; then
    step compare python3 tools/dog/dog_compare.py "$OUT/stage_d.blend" "$OUT/compare" --only "$ONLY"
  else
    step compare python3 tools/dog/dog_compare.py "$OUT/stage_d.blend" "$OUT/compare"
  fi
  echo "[preview] comparisons in $OUT/compare (sheet.png)"
fi
