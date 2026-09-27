#!/usr/bin/env bash
# Comparação mínima: mesma convolução float 11x11, com/sem reduction SIMD em l.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"
OUTPUT_DIR="resultados_convolucao_simd_interno"
QUICK=0
while (($#)); do
    case "$1" in
        --output) (($# >= 2)) || { echo 'Falta diretório após --output' >&2; exit 2; }; OUTPUT_DIR="$2"; shift 2 ;;
        --quick) QUICK=1; shift ;;
        --help)
            echo 'Uso: bash run_inner_simd_convolution.sh [--output DIRETORIO_NOVO] [--quick]'
            echo 'Campanha: 4000x3000.png, 1/20 threads, 3 medições; --quick: poke.jpg, 1 thread, 1 medição.'
            exit 0 ;;
        *) echo "Opção desconhecida: $1" >&2; exit 2 ;;
    esac
done
[[ ! -e "$OUTPUT_DIR" ]] || { echo "Diretório já existe: $OUTPUT_DIR" >&2; exit 2; }
mkdir -p "$OUTPUT_DIR"
OUTPUT_DIR="$(cd "$OUTPUT_DIR" && pwd)"

IMAGE="images/4000x3000.png"
THREADS=(1 20)
REPETITIONS=3
if ((QUICK)); then IMAGE="images/poke.jpg"; THREADS=(1); REPETITIONS=1; fi
[[ -f "$IMAGE" ]] || { echo "Imagem ausente: $IMAGE" >&2; exit 1; }
BUILDS=(auto-avx2 omp-avx2)
VARIANT="float_tap_reduction"
BIN_SUFFIX=""
case "$(uname -s)" in MSYS*|MINGW*) BIN_SUFFIX=".exe" ;; esac

g++ --version > "$OUTPUT_DIR/compiler.txt" 2>&1
if command -v sha256sum >/dev/null 2>&1; then
    sha256sum Makefile run_inner_simd_convolution.sh \
        577262-FPI-Relatorio2/vectorization_benchmark.cpp \
        577262-FPI-Relatorio2/image_manipulation.cpp > "$OUTPUT_DIR/source_sha256.txt"
fi
if command -v lscpu >/dev/null 2>&1; then lscpu > "$OUTPUT_DIR/lscpu.txt"; fi
env | grep '^OMP_' | sort > "$OUTPUT_DIR/openmp_environment_before.txt" || true
printf 'Imagem: %s\nVariável isolada: pragma omp simd reduction(+:sum_r,sum_g,sum_b) no laço l\nBuilds: %s\nThreads: %s\nRepetições: %s\nAquecimento: 1 por configuração\nSchedule: static\nMétrica: kernel com saída pré-alocada; decodificação e referência fora do cronômetro\nValidação: diferenças de bytes e erro máximo contra convolução float original\n' \
    "$IMAGE" "${BUILDS[*]}" "${THREADS[*]}" "$REPETITIONS" > "$OUTPUT_DIR/protocol.txt"

for build in "${BUILDS[@]}"; do
    make -B SIMD="$build" COMPILER_DIAGNOSTICS=1 vectorization
    cp "build/$build/vectorization-experiment-all.log" "$OUTPUT_DIR/$build-vectorization-all.log"
done
PRAGMA_LINE="$(awk '/^void float_tap_reduction\(/ {inside=1} inside && /#pragma omp simd reduction/ {print NR; exit}' \
    577262-FPI-Relatorio2/vectorization_benchmark.cpp)"
LOOP_LINE="$(awk '/^void float_tap_reduction\(/ {inside=1} inside && /for \(int l = -5/ {print NR; exit}' \
    577262-FPI-Relatorio2/vectorization_benchmark.cpp)"
[[ -n "$PRAGMA_LINE" && -n "$LOOP_LINE" ]] || { echo 'Laço interno não localizado.' >&2; exit 1; }
for build in "${BUILDS[@]}"; do
    {
        printf 'Build: %s | pragma: linha %s | laço l: linha %s\n' "$build" "$PRAGMA_LINE" "$LOOP_LINE"
        grep -E "vectorization_benchmark.cpp:($PRAGMA_LINE|$LOOP_LINE):.*(optimized: loop vectorized|missed: couldn't vectorize loop|missed: not vectorized)" \
            "$OUTPUT_DIR/$build-vectorization-all.log" | sort -u || true
    } > "$OUTPUT_DIR/$build-inner-loop-focus.txt"
done

export OMP_DYNAMIC=FALSE
export OMP_SCHEDULE=static
RAW_CSV="$OUTPUT_DIR/inner_simd_raw.csv"
for threads in "${THREADS[@]}"; do
    for build in "${BUILDS[@]}"; do
        OMP_NUM_THREADS="$threads" "build/$build/vectorization_benchmark$BIN_SUFFIX" \
            --image "$IMAGE" --operation Gaussian_11x11 \
            --float-convolution-variant "$VARIANT" "$RAW_CSV" \
            --warmup --check-production
    done
    for ((repeat=1; repeat<=REPETITIONS; ++repeat)); do
        # Alterna a ordem para reduzir viés de temperatura/frequência.
        for ((index=0; index<${#BUILDS[@]}; ++index)); do
            build="${BUILDS[$(((index + repeat - 1) % ${#BUILDS[@]}))]}"
            OMP_NUM_THREADS="$threads" "build/$build/vectorization_benchmark$BIN_SUFFIX" \
                --image "$IMAGE" --operation Gaussian_11x11 \
                --float-convolution-variant "$VARIANT" "$RAW_CSV" --repeat "$repeat"
        done
    done
done

if command -v python3 >/dev/null 2>&1; then
    python3 summarize_inner_simd_convolution.py "$RAW_CSV" \
        "$OUTPUT_DIR/inner_simd_summary.csv" "$REPETITIONS"
else
    echo 'python3 indisponível: CSV bruto salvo, resumo pode ser gerado depois.' >&2
fi
echo "Campanha concluída: $OUTPUT_DIR"
