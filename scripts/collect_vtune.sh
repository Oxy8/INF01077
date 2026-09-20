#!/usr/bin/env bash
# Execute dentro de uma alocação exclusiva no hype, após escolher a configuração
# que apresentou maior diferença nos CSVs. Esta coleta não entra no benchmark.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/scripts/vtune_env.sh"

ANALYSIS="${VTUNE_ANALYSIS:-hotspots}"
RESULT_DIR="${VTUNE_RESULT_DIR:-resultados_vtune/${ANALYSIS}_$(date +%Y%m%d_%H%M%S)}"
IMAGE="${VTUNE_IMAGE:-images/controls/control_half_noise_6000x6000.png}"
OPERATIONS="${VTUNE_OPERATIONS:-adaptive}"
SCHEDULE="${VTUNE_SCHEDULE:-dynamic,16}"
THREADS="${VTUNE_THREADS:-20}"
VTUNE_BIN="${VTUNE_BIN:-vtune}"
SIMD="${VTUNE_SIMD:-omp-avx2}"
PROFILE_ITERATIONS="${VTUNE_PROFILE_ITERATIONS:-1}"
VTUNE_KNOBS="${VTUNE_KNOBS:-}"

command -v "$VTUNE_BIN" >/dev/null || { echo "VTune não encontrado neste nó. Consulte slurm-vtune-preflight-<job>.out para identificar o módulo necessário." >&2; exit 1; }
case "$SIMD" in
    off|off-avx2|omp|omp-avx2) ;;
    *) echo "VTUNE_SIMD deve ser off, off-avx2, omp ou omp-avx2." >&2; exit 2 ;;
esac
make SIMD="$SIMD" all
mkdir -p "$(dirname "$RESULT_DIR")"
vtune_args=(-collect "$ANALYSIS" -result-dir "$RESULT_DIR")
if [[ -n "$VTUNE_KNOBS" ]]; then
    # A variável aceita pares completos, por exemplo:
    # '-knob collect-memory-bandwidth=true -knob analyze-openmp=true'.
    read -r -a knobs <<< "$VTUNE_KNOBS"
    vtune_args+=("${knobs[@]}")
fi

benchmark_args=(--image "$IMAGE" /tmp/vtune_benchmark.csv --operations "$OPERATIONS"
    --run-id "vtune-${ANALYSIS}-${SIMD}" --repeat 0 --warmup)
if [[ "$PROFILE_ITERATIONS" != "1" ]]; then
    benchmark_args+=(--profile-iterations "$PROFILE_ITERATIONS")
fi

OMP_NUM_THREADS="$THREADS" OMP_SCHEDULE="$SCHEDULE" \
"$VTUNE_BIN" "${vtune_args[@]}" -- "build/$SIMD/image_benchmark" "${benchmark_args[@]}"

echo "Coleta salva em $RESULT_DIR"
