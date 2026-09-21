#!/usr/bin/env bash
# Coleta VTune do experimento AoS/SoA. Os perfis usam --warmup porque os CSVs
# de tempo oficiais não devem conter execuções instrumentadas.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/scripts/vtune_env.sh"

ANALYSIS="${VTUNE_ANALYSIS:-hotspots}"
RESULT_DIR="${VTUNE_RESULT_DIR:-resultados_vtune/layout_${ANALYSIS}_$(date +%Y%m%d_%H%M%S)}"
IMAGE="${VTUNE_IMAGE:-images/6000x6000.png}"
OPERATION="${VTUNE_LAYOUT_OPERATION:-Gaussian_11x11}"
SCHEDULE="${VTUNE_SCHEDULE:-static}"
THREADS="${VTUNE_THREADS:-20}"
VTUNE_BIN="${VTUNE_BIN:-vtune}"
SIMD="${VTUNE_SIMD:-omp-avx2}"
PROFILE_ITERATIONS="${VTUNE_PROFILE_ITERATIONS:-1}"
VTUNE_KNOBS="${VTUNE_KNOBS:-}"

command -v "$VTUNE_BIN" >/dev/null || { echo "VTune não encontrado neste nó. Rode o preflight." >&2; exit 1; }
case "$SIMD" in
    off|off-avx2|omp|omp-avx2) ;;
    *) echo "VTUNE_SIMD deve ser off, off-avx2, omp ou omp-avx2." >&2; exit 2 ;;
esac
case "$OPERATION" in
    Grayscale|Gaussian_11x11) ;;
    *) echo "VTUNE_LAYOUT_OPERATION deve ser Grayscale ou Gaussian_11x11." >&2; exit 2 ;;
esac

make SIMD="$SIMD" layout
mkdir -p "$(dirname "$RESULT_DIR")"
vtune_args=(-collect "$ANALYSIS" -result-dir "$RESULT_DIR")
if [[ "$ANALYSIS" == "hotspots" && "$VTUNE_KNOBS" != *"sampling-mode="* ]]; then
    vtune_args+=(-knob sampling-mode=hw)
fi
if [[ -n "$VTUNE_KNOBS" ]]; then
    read -r -a knobs <<< "$VTUNE_KNOBS"
    vtune_args+=("${knobs[@]}")
fi

OMP_NUM_THREADS="$THREADS" OMP_SCHEDULE="$SCHEDULE" \
"$VTUNE_BIN" "${vtune_args[@]}" -- "build/$SIMD/layout_benchmark" \
    --image "$IMAGE" /tmp/vtune_layout.csv --operation "$OPERATION" \
    --run-id "vtune-layout-${OPERATION}-${SIMD}" --repeat 0 \
    --profile-iterations "$PROFILE_ITERATIONS" --warmup

echo "Coleta salva em $RESULT_DIR"
