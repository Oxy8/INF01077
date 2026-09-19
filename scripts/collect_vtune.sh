#!/usr/bin/env bash
# Execute dentro de uma alocação exclusiva no hype, após escolher a configuração
# que apresentou maior diferença nos CSVs. Esta coleta não entra no benchmark.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

ANALYSIS="${VTUNE_ANALYSIS:-hotspots}"
RESULT_DIR="${VTUNE_RESULT_DIR:-resultados_vtune/${ANALYSIS}_$(date +%Y%m%d_%H%M%S)}"
IMAGE="${VTUNE_IMAGE:-images/controls/control_half_noise_6000x6000.png}"
OPERATIONS="${VTUNE_OPERATIONS:-adaptive}"
SCHEDULE="${VTUNE_SCHEDULE:-dynamic,16}"
THREADS="${VTUNE_THREADS:-20}"
VTUNE_BIN="${VTUNE_BIN:-vtune}"
SIMD="${VTUNE_SIMD:-omp-avx2}"

command -v "$VTUNE_BIN" >/dev/null || { echo "VTune não encontrado. Rode primeiro o preflight." >&2; exit 1; }
case "$SIMD" in
    off|off-avx2|omp|omp-avx2) ;;
    *) echo "VTUNE_SIMD deve ser off, off-avx2, omp ou omp-avx2." >&2; exit 2 ;;
esac
make SIMD="$SIMD" all
mkdir -p "$(dirname "$RESULT_DIR")"

OMP_NUM_THREADS="$THREADS" OMP_SCHEDULE="$SCHEDULE" \
"$VTUNE_BIN" -collect "$ANALYSIS" -result-dir "$RESULT_DIR" -- \
    "build/$SIMD/image_benchmark" --image "$IMAGE" /tmp/vtune_benchmark.csv \
    --operations "$OPERATIONS" --run-id "vtune-${ANALYSIS}-${SIMD}" --repeat 0

echo "Coleta salva em $RESULT_DIR"
