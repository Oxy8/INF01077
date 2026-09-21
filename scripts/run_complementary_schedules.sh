#!/usr/bin/env bash
# Campanha curta de confirmação de schedule para operações regulares.
# A ordem das configurações e operações é rotacionada em cada repetição.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

OUTPUT_DIR="${1:-resultados_schedules_complementares}"
IMAGE="${COMPLEMENTARY_SCHEDULE_IMAGE:-images/6000x6000.png}"
TIMED_REPETITIONS="${COMPLEMENTARY_SCHEDULE_REPETITIONS:-10}"
RAW_CSV="$OUTPUT_DIR/benchmark_raw.csv"
REFERENCE_HASHES="$OUTPUT_DIR/reference_hashes.csv"
AFFINITY_LOG="$OUTPUT_DIR/openmp_affinity.log"

[[ "$TIMED_REPETITIONS" =~ ^[1-9][0-9]*$ ]] || { echo 'COMPLEMENTARY_SCHEDULE_REPETITIONS deve ser inteiro positivo.' >&2; exit 2; }
[[ -f "$IMAGE" ]] || { echo "Imagem ausente: $IMAGE" >&2; exit 2; }
[[ ! -e "$OUTPUT_DIR" ]] || { echo "O diretório de saída já existe: $OUTPUT_DIR" >&2; exit 2; }
mkdir -p "$OUTPUT_DIR"

# Esta afinidade vale somente para o experimento de confirmação. Ela é salva
# no CSV e no log para impedir que migração de threads se confunda com schedule.
export OMP_DYNAMIC=FALSE
export OMP_PLACES=cores
export OMP_PROC_BIND=close
export OMP_DISPLAY_AFFINITY=true

{
    printf 'image=%s\nthreads=20\nrepetitions=%s\n' "$IMAGE" "$TIMED_REPETITIONS"
    printf 'OMP_DYNAMIC=%s\nOMP_PLACES=%s\nOMP_PROC_BIND=%s\nOMP_DISPLAY_AFFINITY=%s\n' \
        "$OMP_DYNAMIC" "$OMP_PLACES" "$OMP_PROC_BIND" "$OMP_DISPLAY_AFFINITY"
} > "$OUTPUT_DIR/configuration.txt"

make -B SIMD=off-avx2 all
make -B SIMD=omp-avx2 all

OPERATIONS=(Adjust_Brightness Flip_Horizontal Negative Equalize_Histogram Gaussian_11x11 Zoom_In)
SCHEDULES=(static dynamic,1 dynamic,16)

for operation in "${OPERATIONS[@]}"; do
    OMP_NUM_THREADS=1 OMP_SCHEDULE=static build/off-avx2/image_benchmark \
        --image "$IMAGE" /dev/null --operations "$operation" --hash-only \
        --write-hashes "$REFERENCE_HASHES" 2>>"$AFFINITY_LOG"
done

run_one() {
    local operation="$1" schedule="$2" repetition="$3" warmup="$4"
    local tag="schedule-confirm-${operation}-${schedule//,/x}-r${repetition}"
    local args=(--image "$IMAGE" "$RAW_CSV" --operations "$operation" --run-id "$tag" --repeat "$repetition" --reference-hashes "$REFERENCE_HASHES")
    [[ "$warmup" -eq 1 ]] && args+=(--warmup)
    OMP_NUM_THREADS=20 OMP_SCHEDULE="$schedule" build/omp-avx2/image_benchmark "${args[@]}" \
        2> >(tee -a "$AFFINITY_LOG" >&2)
}

echo 'Aquecendo cada operação e schedule...'
for schedule in "${SCHEDULES[@]}"; do
    for operation in "${OPERATIONS[@]}"; do
        run_one "$operation" "$schedule" 0 1
    done
done

echo "Executando $TIMED_REPETITIONS repetições intercaladas..."
for ((repetition = 1; repetition <= TIMED_REPETITIONS; repetition++)); do
    schedule_offset=$(((repetition - 1) % ${#SCHEDULES[@]}))
    operation_offset=$(((repetition - 1) % ${#OPERATIONS[@]}))
    for ((schedule_position = 0; schedule_position < ${#SCHEDULES[@]}; schedule_position++)); do
        schedule="${SCHEDULES[$(((schedule_position + schedule_offset) % ${#SCHEDULES[@]}))]}"
        for ((operation_position = 0; operation_position < ${#OPERATIONS[@]}; operation_position++)); do
            operation="${OPERATIONS[$(((operation_position + operation_offset) % ${#OPERATIONS[@]}))]}"
            run_one "$operation" "$schedule" "$repetition" 0
        done
    done
done

python3 summarize_results.py --raw "$RAW_CSV" --out "$OUTPUT_DIR/benchmark_summary.csv"
echo "Campanha concluída: $OUTPUT_DIR"
