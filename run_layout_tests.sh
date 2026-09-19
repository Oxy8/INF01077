#!/usr/bin/env bash
# Experimento isolado de layout para testar se separar R/G/B melhora o kernel
# SIMD de grayscale e Gaussian_11x11. Static é mantido fixo: schedule não é
# variável de estudo.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

THREADS=(1 2 4 8 12 16 20)
TIMED_REPETITIONS=(1 2 3 4 5)
REGULAR_IMAGES=("images/4000x3000.png" "images/6000x6000.png")
OPERATIONS=("Grayscale" "Gaussian_11x11")
BUILD_VARIANTS=("off" "off-avx2" "omp" "omp-avx2")
OUTPUT_DIR="resultados_layout"
ARCH="${ARCH:-}"
OVERWRITE=0

usage() {
    cat <<'EOF'
Uso: ./run_layout_tests.sh [opções]

  --output DIRETORIO  Diretório novo para CSVs e resumo.
  --overwrite         Permite substituir o diretório de saída informado.
  --help              Mostra esta ajuda.

O experimento compara Grayscale e Gaussian_11x11 estáticos. Grayscale usa
RGB intercalado (AoS) e SoA; Gaussian acrescenta SoA separável. Cada caso é
construído como escalar, escalar Haswell, omp simd genérico e omp simd com
AVX2. Conversão AoS→SoA, kernel e SoA→AoS são cronometrados em linhas
distintas; alocação e cópias de restauração não entram.
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --output) OUTPUT_DIR="$2"; shift 2 ;;
        --overwrite) OVERWRITE=1; shift ;;
        --help) usage; exit 0 ;;
        *) echo "Opção desconhecida: $1" >&2; usage >&2; exit 2 ;;
    esac
done

if [[ -e "$OUTPUT_DIR" ]]; then
    if [[ "$OVERWRITE" -ne 1 ]]; then
        echo "O diretório '$OUTPUT_DIR' já existe. Use --overwrite para substituí-lo." >&2
        exit 2
    fi
    rm -rf -- "$OUTPUT_DIR"
fi
mkdir -p "$OUTPUT_DIR"

for image in "${REGULAR_IMAGES[@]}"; do
    [[ -f "$image" ]] || { echo "Imagem ausente: $image" >&2; exit 1; }
done

echo "Compilando as variantes para o experimento de layout..."
make clean
for variant in "${BUILD_VARIANTS[@]}"; do
    make SIMD="$variant" ARCH="$ARCH" layout
done

RAW_CSV="$OUTPUT_DIR/layout_raw.csv"

run_one() {
    local binary="$1"
    local simd="$2"
    local threads="$3"
    local operation="$4"
    local image="$5"
    local repetition="$6"
    local warmup="$7"
    local tag="layout-${operation}-simd_${simd}-t${threads}-r${repetition}-$(basename "$image")"
    local args=(--image "$image" "$RAW_CSV" --operation "$operation" --run-id "$tag" --repeat "$repetition")
    if [[ "$warmup" -eq 1 ]]; then args+=(--warmup); fi
    OMP_NUM_THREADS="$threads" OMP_SCHEDULE=static "$binary" "${args[@]}"
}

binary_for_simd() {
    printf '%s\n' "build/$1/layout_benchmark"
}

for threads in "${THREADS[@]}"; do
    for simd in "${BUILD_VARIANTS[@]}"; do
        binary="$(binary_for_simd "$simd")"
        for operation in "${OPERATIONS[@]}"; do
            for image in "${REGULAR_IMAGES[@]}"; do
                run_one "$binary" "$simd" "$threads" "$operation" "$image" 0 1
            done
        done
    done

    # Rotacionar a ordem das variantes reduz viés por aquecimento residual,
    # frequência do processador ou pressão de memória.
    for repetition in "${TIMED_REPETITIONS[@]}"; do
        offset=$(((repetition - 1) % ${#BUILD_VARIANTS[@]}))
        configs=()
        for ((position = 0; position < ${#BUILD_VARIANTS[@]}; position++)); do
            configs+=("${BUILD_VARIANTS[$(((position + offset) % ${#BUILD_VARIANTS[@]}))]}")
        done
        for simd in "${configs[@]}"; do
            binary="$(binary_for_simd "$simd")"
            for operation in "${OPERATIONS[@]}"; do
                for image in "${REGULAR_IMAGES[@]}"; do
                    run_one "$binary" "$simd" "$threads" "$operation" "$image" "$repetition" 0
                done
            done
        done
    done
done

python3 summarize_layout_results.py --raw "$RAW_CSV" --out "$OUTPUT_DIR/layout_summary.csv"
echo "Experimento de layout finalizado. Dados brutos: $RAW_CSV"
echo "Resumo: $OUTPUT_DIR/layout_summary.csv"
