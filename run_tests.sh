#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

THREADS=(1 2 4 8 12 16 20)
TIMED_REPETITIONS=(1 2 3 4 5)
REGULAR_IMAGES=("images/4000x3000.png" "images/6000x6000.png")
ADAPTIVE_REAL_IMAGES=("images/sky.jpg" "images/stars.jpg" "images/rain_paisage.jpg" "images/firework.jpg")
ADAPTIVE_CONTROL_IMAGES=(
    "images/controls/control_smooth_6000x6000.png"
    "images/controls/control_noise_6000x6000.png"
    "images/controls/control_half_noise_6000x6000.png"
    "images/controls/control_bands_256_6000x6000.png"
)
ADAPTIVE_IMAGES=("${ADAPTIVE_REAL_IMAGES[@]}" "${ADAPTIVE_CONTROL_IMAGES[@]}")

OUTPUT_DIR="resultados_experimentos"
ARCH="${ARCH:-}"
OVERWRITE=0
RUN_REGULAR=1
RUN_ADAPTIVE=1
RUN_SMT=1
SMOKE=0

usage() {
    cat <<'EOF'
Uso: ./run_tests.sh [opções]

  --output DIRETORIO  Diretório novo para CSVs e resumo.
  --overwrite         Permite substituir o diretório de saída informado.
  --regular-only      Executa apenas as 17 operações não adaptativas.
  --adaptive-only     Executa apenas o filtro adaptativo.
  --smt-only          Executa apenas a sensibilidade 20 versus 40 threads.
  --skip-smt          Não executa a sensibilidade de hyperthreading.
  --smoke             Executa uma verificação curta de ponta a ponta.
  --help              Mostra esta ajuda.
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --output) OUTPUT_DIR="$2"; shift 2 ;;
        --overwrite) OVERWRITE=1; shift ;;
        --regular-only) RUN_ADAPTIVE=0; RUN_SMT=0; shift ;;
        --adaptive-only) RUN_REGULAR=0; RUN_SMT=0; shift ;;
        --smt-only) RUN_REGULAR=0; RUN_ADAPTIVE=0; RUN_SMT=1; shift ;;
        --skip-smt) RUN_SMT=0; shift ;;
        --smoke) SMOKE=1; RUN_SMT=0; shift ;;
        --help) usage; exit 0 ;;
        *) echo "Opção desconhecida: $1" >&2; usage >&2; exit 2 ;;
    esac
done

RAW_CSV="$OUTPUT_DIR/benchmark_raw.csv"
REFERENCE_HASHES="$OUTPUT_DIR/reference_hashes.csv"

if [[ -e "$OUTPUT_DIR" ]]; then
    if [[ "$OVERWRITE" -ne 1 ]]; then
        echo "O diretório '$OUTPUT_DIR' já existe. Use --overwrite para substituí-lo." >&2
        exit 2
    fi
    rm -rf -- "$OUTPUT_DIR"
fi
mkdir -p "$OUTPUT_DIR"

echo "Compilando variantes SIMD..."
make clean
make SIMD=off ARCH="$ARCH" all generator
make SIMD=omp ARCH="$ARCH" all
make SIMD=off ARCH="$ARCH" generate-controls

for image in "${REGULAR_IMAGES[@]}" "${ADAPTIVE_IMAGES[@]}"; do
    [[ -f "$image" ]] || { echo "Imagem ausente: $image" >&2; exit 1; }
done

BASELINE="build/off/image_benchmark"
SIMD_OFF="build/off/image_benchmark"
SIMD_OMP="build/omp/image_benchmark"

make_reference() {
    echo "Gerando hashes de referência..."
    if [[ "$SMOKE" -eq 1 ]]; then
        OMP_NUM_THREADS=1 OMP_SCHEDULE=static "$BASELINE" --image "images/4000x3000.png" --operations Grayscale --hash-only --write-hashes "$REFERENCE_HASHES"
        OMP_NUM_THREADS=1 OMP_SCHEDULE=static "$BASELINE" --image "images/controls/control_half_noise_6000x6000.png" --operations adaptive --hash-only --write-hashes "$REFERENCE_HASHES"
        return
    fi
    for image in "${REGULAR_IMAGES[@]}"; do
        OMP_NUM_THREADS=1 OMP_SCHEDULE=static "$BASELINE" --image "$image" --operations regular --hash-only --write-hashes "$REFERENCE_HASHES"
    done
    for image in "${ADAPTIVE_IMAGES[@]}"; do
        OMP_NUM_THREADS=1 OMP_SCHEDULE=static "$BASELINE" --image "$image" --operations adaptive --hash-only --write-hashes "$REFERENCE_HASHES"
    done
}

run_one() {
    local binary="$1"
    local simd="$2"
    local threads="$3"
    local schedule="$4"
    local image="$5"
    local operations="$6"
    local repetition="$7"
    local warmup="$8"
    local tag="${operations}-simd_${simd}-t${threads}-${schedule//,/x}-r${repetition}-$(basename "$image")"
    local args=(--image "$image" "$RAW_CSV" --operations "$operations" --run-id "$tag" --repeat "$repetition" --reference-hashes "$REFERENCE_HASHES")
    if [[ "$warmup" -eq 1 ]]; then args+=(--warmup); fi
    OMP_NUM_THREADS="$threads" OMP_SCHEDULE="$schedule" "$binary" "${args[@]}"
}

binary_for_simd() {
    [[ "$1" == "off" ]] && printf '%s\n' "$SIMD_OFF" || printf '%s\n' "$SIMD_OMP"
}

run_regular_campaign() {
    local configs=("off:static" "omp:static" "off:dynamic,1" "omp:dynamic,1" "off:dynamic,16" "omp:dynamic,16")
    echo "Iniciando campanha das operações regulares..."
    for threads in "${THREADS[@]}"; do
        for config in "${configs[@]}"; do
            local simd="${config%%:*}" schedule="${config#*:}" binary
            binary="$(binary_for_simd "$simd")"
            for image in "${REGULAR_IMAGES[@]}"; do
                run_one "$binary" "$simd" "$threads" "$schedule" "$image" regular 0 1
            done
        done
        for repetition in "${TIMED_REPETITIONS[@]}"; do
            local offset=$(((repetition - 1) % ${#configs[@]}))
            for ((position = 0; position < ${#configs[@]}; position++)); do
                local config="${configs[$(((position + offset) % ${#configs[@]}))]}"
                local simd="${config%%:*}"
                local schedule="${config#*:}"
                local binary
                binary="$(binary_for_simd "$simd")"
                for image in "${REGULAR_IMAGES[@]}"; do
                    run_one "$binary" "$simd" "$threads" "$schedule" "$image" regular "$repetition" 0
                done
            done
        done
    done
}

run_adaptive_campaign() {
    local chunk_configs=("off:static" "omp:static" "off:dynamic,1" "omp:dynamic,1" "off:dynamic,4" "omp:dynamic,4" "off:dynamic,16" "omp:dynamic,16" "off:dynamic,64" "omp:dynamic,64" "off:dynamic,256" "omp:dynamic,256")
    echo "Iniciando varredura de chunks do filtro adaptativo..."
    for config in "${chunk_configs[@]}"; do
        local simd="${config%%:*}" schedule="${config#*:}" binary
        binary="$(binary_for_simd "$simd")"
        for image in "${ADAPTIVE_IMAGES[@]}"; do
            run_one "$binary" "$simd" 20 "$schedule" "$image" adaptive 0 1
        done
    done
    for repetition in "${TIMED_REPETITIONS[@]}"; do
        local offset=$(((repetition - 1) % ${#chunk_configs[@]}))
        for ((position = 0; position < ${#chunk_configs[@]}; position++)); do
            local config="${chunk_configs[$(((position + offset) % ${#chunk_configs[@]}))]}"
            local simd="${config%%:*}" schedule="${config#*:}" binary
            binary="$(binary_for_simd "$simd")"
            for image in "${ADAPTIVE_IMAGES[@]}"; do
                run_one "$binary" "$simd" 20 "$schedule" "$image" adaptive "$repetition" 0
            done
        done
    done

    echo "Iniciando escalabilidade static versus dynamic,16 do adaptativo..."
    for threads in 1 2 4 8 12 16; do
        local scale_configs=("off:static" "omp:static" "off:dynamic,16" "omp:dynamic,16")
        for config in "${scale_configs[@]}"; do
            local simd="${config%%:*}" schedule="${config#*:}" binary
            binary="$(binary_for_simd "$simd")"
            for image in "${ADAPTIVE_IMAGES[@]}"; do
                run_one "$binary" "$simd" "$threads" "$schedule" "$image" adaptive 0 1
            done
        done
        for repetition in "${TIMED_REPETITIONS[@]}"; do
            local offset=$(((repetition - 1) % ${#scale_configs[@]}))
            for ((position = 0; position < ${#scale_configs[@]}; position++)); do
                local config="${scale_configs[$(((position + offset) % ${#scale_configs[@]}))]}"
                local simd="${config%%:*}" schedule="${config#*:}" binary
                binary="$(binary_for_simd "$simd")"
                for image in "${ADAPTIVE_IMAGES[@]}"; do
                    run_one "$binary" "$simd" "$threads" "$schedule" "$image" adaptive "$repetition" 0
                done
            done
        done
    done
}

run_smt_campaign() {
    local workload_specs=(
        "images/6000x6000.png|Grayscale"
        "images/6000x6000.png|Gaussian_11x11"
        "images/controls/control_half_noise_6000x6000.png|adaptive"
    )
    echo "Iniciando sensibilidade de hyperthreading..."
    for workload_spec in "${workload_specs[@]}"; do
        local workload_image="${workload_spec%%|*}"
        local workload_operations="${workload_spec#*|}"
        for threads in 20 40; do
            local schedules=(static dynamic,16)
            for schedule in "${schedules[@]}"; do
                run_one "$SIMD_OMP" omp "$threads" "$schedule" "$workload_image" "$workload_operations" 0 1
            done
            for repetition in "${TIMED_REPETITIONS[@]}"; do
                local offset=$(((repetition - 1) % ${#schedules[@]}))
                for ((position = 0; position < ${#schedules[@]}; position++)); do
                    local schedule="${schedules[$(((position + offset) % ${#schedules[@]}))]}"
                    run_one "$SIMD_OMP" omp "$threads" "$schedule" "$workload_image" "$workload_operations" "$repetition" 0
                done
            done
        done
    done
}

make_reference

if [[ "$SMOKE" -eq 1 ]]; then
    run_one "$SIMD_OFF" off 1 static "images/4000x3000.png" Grayscale 0 1
    run_one "$SIMD_OFF" off 1 static "images/4000x3000.png" Grayscale 1 0
    run_one "$SIMD_OMP" omp 2 dynamic,1 "images/controls/control_half_noise_6000x6000.png" adaptive 1 0
else
    [[ "$RUN_REGULAR" -eq 1 ]] && run_regular_campaign
    [[ "$RUN_ADAPTIVE" -eq 1 ]] && run_adaptive_campaign
    [[ "$RUN_SMT" -eq 1 ]] && run_smt_campaign
fi

python3 summarize_results.py --raw "$RAW_CSV" --out "$OUTPUT_DIR/benchmark_summary.csv"
echo "Campanha finalizada. Dados brutos: $RAW_CSV"
echo "Resumo: $OUTPUT_DIR/benchmark_summary.csv"
