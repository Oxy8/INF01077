#!/usr/bin/env bash
# Oito operações do primeiro mapa SIMD, sete pontos de threads, cinco amostras.
# A convolução float recebe quatro variantes isoladas; nenhuma função de
# produção é alterada. Usar somente em nó hype exclusivo.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"
OUTPUT_DIR="resultados_simd_followup"
QUICK=0
while (($#)); do
    case "$1" in
        --output) (($# >= 2)) || { echo 'Falta diretório após --output' >&2; exit 2; }; OUTPUT_DIR="$2"; shift 2 ;;
        --quick) QUICK=1; shift ;;
        --help)
            echo 'Uso: bash run_simd_followup_tests.sh [--output DIRETORIO_NOVO] [--quick]'
            echo 'Não sobrescreve resultados; --quick usa poke.jpg, uma thread e uma amostra.'
            exit 0 ;;
        *) echo "Opção desconhecida: $1" >&2; exit 2 ;;
    esac
done
[[ ! -e "$OUTPUT_DIR" ]] || { echo "Diretório já existe: $OUTPUT_DIR" >&2; exit 2; }
mkdir -p "$OUTPUT_DIR"
OUTPUT_DIR="$(cd "$OUTPUT_DIR" && pwd)"

IMAGE=images/6000x6000.png
THREADS=(1 2 4 8 12 16 20)
REPETITIONS=5
if ((QUICK)); then IMAGE=images/poke.jpg; THREADS=(1); REPETITIONS=1; fi
[[ -f "$IMAGE" ]] || { echo "Imagem ausente: $IMAGE" >&2; exit 1; }
OPERATIONS=(Adjust_Brightness Adjust_Contrast Equalize_Histogram Gaussian_11x11
            Grayscale Negative Quantize Zoom_In)
OPERATION_CSV="$(IFS=,; echo "${OPERATIONS[*]}")"
# A redução SIMD nos taps foi excluída da campanha formal: alterou bytes na
# validação curta. float_tap_products preserva a ordem original da soma.
VARIANTS=(float_pixel_outer float_tap_products float_row_aos float_row_soa)
BUILDS=(off-avx2 auto-avx2 omp-avx2)
BIN_SUFFIX=""
case "$(uname -s)" in MSYS*|MINGW*) BIN_SUFFIX=".exe" ;; esac

g++ --version > "$OUTPUT_DIR/compiler.txt" 2>&1
git rev-parse HEAD > "$OUTPUT_DIR/git_commit.txt" 2>/dev/null || true
if command -v sha256sum >/dev/null 2>&1; then
    sha256sum Makefile run_simd_followup_tests.sh 577262-FPI-Relatorio2/image_manipulation.h \
        577262-FPI-Relatorio2/image_manipulation.cpp \
        577262-FPI-Relatorio2/vectorization_benchmark.cpp \
        577262-FPI-Relatorio2/benchmark_runner.cpp > "$OUTPUT_DIR/source_sha256.txt"
fi
if command -v lscpu >/dev/null 2>&1; then lscpu > "$OUTPUT_DIR/lscpu.txt"; fi
env | grep '^OMP_' | sort > "$OUTPUT_DIR/openmp_environment_before.txt" || true
printf 'Imagem: %s\nOperações: %s\nThreads: %s\nRepetições: %s\n' \
    "$IMAGE" "$OPERATION_CSV" "${THREADS[*]}" "$REPETITIONS" > "$OUTPUT_DIR/protocol.txt"

for build in "${BUILDS[@]}"; do
    make -B DEBUG=1 SIMD="$build" COMPILER_DIAGNOSTICS=1 all vectorization
    cp "build/$build/vectorization-core-all.log" "$OUTPUT_DIR/$build-core-compiler.txt"
    cp "build/$build/vectorization-experiment-all.log" "$OUTPUT_DIR/$build-experiment-compiler.txt"
    grep -E 'image_manipulation.cpp:[0-9]+:[0-9]+: (optimized: loop vectorized|missed:.*vectoriz)' \
        "$OUTPUT_DIR/$build-core-compiler.txt" > "$OUTPUT_DIR/$build-core-focus.txt" || true
    grep -E 'vectorization_benchmark.cpp:[0-9]+:[0-9]+: (optimized: loop vectorized|missed:.*vectoriz)' \
        "$OUTPUT_DIR/$build-experiment-compiler.txt" > "$OUTPUT_DIR/$build-experiment-focus.txt" || true
done

export OMP_DYNAMIC=FALSE
export OMP_SCHEDULE=static
ORIGINAL_CSV="$OUTPUT_DIR/original_raw.csv"
FLOAT_CSV="$OUTPUT_DIR/gaussian_float_raw.csv"
HASHES="$OUTPUT_DIR/original_reference_hashes.csv"

# Primeiro estabelece uma referência do código de produção na própria imagem
# da campanha; cada execução posterior é verificada antes de escrever o CSV.
OMP_NUM_THREADS=1 "build/off-avx2/image_benchmark$BIN_SUFFIX" --image "$IMAGE" "$ORIGINAL_CSV" \
    --operations "$OPERATION_CSV" --hash-only --write-hashes "$HASHES"
for build in "${BUILDS[@]}"; do
    OMP_NUM_THREADS=1 "build/$build/image_benchmark$BIN_SUFFIX" --image "$IMAGE" "$ORIGINAL_CSV" \
        --operations "$OPERATION_CSV" --hash-only --reference-hashes "$HASHES"
    for variant in "${VARIANTS[@]}"; do
        OMP_NUM_THREADS=1 "build/$build/vectorization_benchmark$BIN_SUFFIX" \
            --image "$IMAGE" --operation Gaussian_11x11 --float-convolution-variant "$variant" \
            "$FLOAT_CSV" --warmup --check-production
    done
done
echo 'Validação de todas as operações/builds e variantes float concluída.'

for threads in "${THREADS[@]}"; do
    for build in "${BUILDS[@]}"; do
        OMP_NUM_THREADS="$threads" "build/$build/image_benchmark$BIN_SUFFIX" --image "$IMAGE" "$ORIGINAL_CSV" \
            --operations "$OPERATION_CSV" --reference-hashes "$HASHES" --warmup
        for variant in "${VARIANTS[@]}"; do
            OMP_NUM_THREADS="$threads" "build/$build/vectorization_benchmark$BIN_SUFFIX" \
                --image "$IMAGE" --operation Gaussian_11x11 --float-convolution-variant "$variant" \
                "$FLOAT_CSV" --warmup
        done
    done
    for ((repeat=1; repeat<=REPETITIONS; ++repeat)); do
        for ((index=0; index<${#BUILDS[@]}; ++index)); do
            build="${BUILDS[$(((index + repeat - 1) % ${#BUILDS[@]}))]}"
            OMP_NUM_THREADS="$threads" "build/$build/image_benchmark$BIN_SUFFIX" --image "$IMAGE" "$ORIGINAL_CSV" \
                --operations "$OPERATION_CSV" --reference-hashes "$HASHES" \
                --run-id simd-followup --repeat "$repeat"
            for ((offset=0; offset<${#VARIANTS[@]}; ++offset)); do
                variant="${VARIANTS[$(((offset + repeat - 1) % ${#VARIANTS[@]}))]}"
                OMP_NUM_THREADS="$threads" "build/$build/vectorization_benchmark$BIN_SUFFIX" \
                    --image "$IMAGE" --operation Gaussian_11x11 --float-convolution-variant "$variant" \
                    "$FLOAT_CSV" --repeat "$repeat"
            done
        done
    done
done
if command -v python3 >/dev/null 2>&1; then
    python3 summarize_simd_followup.py --original "$ORIGINAL_CSV" --float "$FLOAT_CSV" \
        --out "$OUTPUT_DIR/simd_followup_summary.csv"
    python3 plot_simd_followup.py --summary "$OUTPUT_DIR/simd_followup_summary.csv" \
        --out "$OUTPUT_DIR/visualizacoes"
else
    echo 'python3 indisponível; CSVs brutos íntegros, resumo pode ser gerado depois.' >&2
fi
echo "Campanha concluída: $OUTPUT_DIR"
