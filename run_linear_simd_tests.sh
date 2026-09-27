#!/usr/bin/env bash
# Campanha controlada: sem LUT, SoA, convolução separável ou histograma privado.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"
OUTPUT_DIR="resultados_linear_simd"
QUICK=0
while (($#)); do
    case "$1" in
        --output) (($# >= 2)) || { echo 'Falta diretório após --output' >&2; exit 2; }; OUTPUT_DIR="$2"; shift 2 ;;
        --quick) QUICK=1; shift ;;
        --help)
            echo 'Uso: bash run_linear_simd_tests.sh [--output DIRETORIO_NOVO] [--quick]'
            echo 'Valida hashes; não sobrescreve resultados anteriores.'
            exit 0 ;;
        *) echo "Opção desconhecida: $1" >&2; exit 2 ;;
    esac
done
[[ ! -e "$OUTPUT_DIR" ]] || { echo "Diretório já existe: $OUTPUT_DIR" >&2; exit 2; }
mkdir -p "$OUTPUT_DIR"
OUTPUT_DIR="$(cd "$OUTPUT_DIR" && pwd)"

OPERATIONS=(Negative Adjust_Brightness Adjust_Contrast Equalize_Histogram
            Gaussian_11x11 Quantize Grayscale Zoom_In)
BUILDS=(off-avx2 auto-avx2 omp-avx2)
THREADS=(1 20)
IMAGES=(images/4000x3000.png images/6000x6000.png)
REPETITIONS=5
if ((QUICK)); then IMAGES=(images/poke.jpg); THREADS=(1); REPETITIONS=1; fi
for image in "${IMAGES[@]}" images/poke.jpg; do
    [[ -f "$image" ]] || { echo "Imagem ausente: $image" >&2; exit 1; }
done
command -v python3 >/dev/null 2>&1 || {
    echo 'python3 é necessário para validar os hashes entre builds.' >&2; exit 2;
}
BIN_SUFFIX=""
case "$(uname -s)" in MSYS*|MINGW*) BIN_SUFFIX=".exe" ;; esac

g++ --version > "$OUTPUT_DIR/compiler.txt" 2>&1
git rev-parse HEAD > "$OUTPUT_DIR/git_commit.txt" 2>/dev/null || true
if command -v sha256sum >/dev/null 2>&1; then
    sha256sum Makefile run_linear_simd_tests.sh \
        577262-FPI-Relatorio2/image_manipulation.cpp \
        577262-FPI-Relatorio2/vectorization_benchmark.cpp > "$OUTPUT_DIR/source_sha256.txt"
fi
if command -v lscpu >/dev/null 2>&1; then lscpu > "$OUTPUT_DIR/lscpu.txt"; fi
printf 'Imagens: %s\nOperações: %s\nThreads: %s\nRepetições: %s\n' \
    "${IMAGES[*]}" "${OPERATIONS[*]}" "${THREADS[*]}" "$REPETITIONS" > "$OUTPUT_DIR/protocol.txt"
printf 'Quantize, Grayscale e Zoom In são controles sem reescrita.\n' >> "$OUTPUT_DIR/protocol.txt"
printf 'Gaussiana: 121 coeficientes float; baseline por pixel e candidata por linha AoS.\n' >> "$OUTPUT_DIR/protocol.txt"

for build in "${BUILDS[@]}"; do
    make -B DEBUG=1 SIMD="$build" COMPILER_DIAGNOSTICS=1 vectorization
    cp "build/$build/vectorization-experiment-all.log" "$OUTPUT_DIR/$build-compiler-all.txt"
    cp "build/$build/vectorization-core-all.log" "$OUTPUT_DIR/$build-core-all.txt"
    grep -E 'vectorization_benchmark.cpp:[0-9]+:[0-9]+: (optimized: loop vectorized|missed:.*vectoriz)' \
        "$OUTPUT_DIR/$build-compiler-all.txt" > "$OUTPUT_DIR/$build-compiler-focus.txt" || true
done

export OMP_DYNAMIC=FALSE
export OMP_SCHEDULE=static
CSV="$OUTPUT_DIR/linear_simd_raw.csv"

# Saídas exatas na imagem pequena antes de gastar a reserva do nó.
for build in "${BUILDS[@]}"; do
    for operation in "${OPERATIONS[@]}"; do
        OMP_NUM_THREADS=1 "build/$build/vectorization_benchmark$BIN_SUFFIX" \
            --image images/poke.jpg --operation "$operation" \
            --clean-linearization --check-production "$CSV" --warmup
    done
done
echo 'Validação curta concluída.'

# Pré-voo nas imagens reais: detecta divergência entre builds antes das cinco
# repetições. Seu CSV é separado e não entra nas estatísticas de tempo.
PREFLIGHT_CSV="$OUTPUT_DIR/preflight_raw.csv"
for image in "${IMAGES[@]}"; do
    for operation in "${OPERATIONS[@]}"; do
        if [[ "$operation" == Zoom_In && "$image" == images/6000x6000.png ]]; then continue; fi
        for build in "${BUILDS[@]}"; do
            OMP_NUM_THREADS=1 "build/$build/vectorization_benchmark$BIN_SUFFIX" \
                --image "$image" --operation "$operation" --clean-linearization \
                --check-production "$PREFLIGHT_CSV" --repeat 1
        done
    done
done
python3 summarize_linear_simd.py --raw "$PREFLIGHT_CSV" \
    --out "$OUTPUT_DIR/preflight_summary.csv"
echo 'Pré-voo das imagens reais concluído; hashes idênticos entre builds.'

for image in "${IMAGES[@]}"; do
    for operation in "${OPERATIONS[@]}"; do
        # Zoom quadruplica a saída; repetir o protocolo anterior em 12 MP.
        if [[ "$operation" == Zoom_In && "$image" == images/6000x6000.png ]]; then continue; fi
        for threads in "${THREADS[@]}"; do
            for build in "${BUILDS[@]}"; do
                OMP_NUM_THREADS="$threads" "build/$build/vectorization_benchmark$BIN_SUFFIX" \
                    --image "$image" --operation "$operation" --clean-linearization \
                    "$CSV" --warmup
            done
            for ((repeat=1; repeat<=REPETITIONS; ++repeat)); do
                for ((index=0; index<${#BUILDS[@]}; ++index)); do
                    build="${BUILDS[$(((index + repeat - 1) % ${#BUILDS[@]}))]}"
                    OMP_NUM_THREADS="$threads" "build/$build/vectorization_benchmark$BIN_SUFFIX" \
                        --image "$image" --operation "$operation" --clean-linearization \
                        "$CSV" --repeat "$repeat"
                done
            done
        done
    done
done

python3 summarize_linear_simd.py --raw "$CSV" --out "$OUTPUT_DIR/linear_simd_summary.csv"
if ((!QUICK)); then
    python3 plot_linear_simd.py --raw "$CSV" --out "$OUTPUT_DIR/figures"
fi
echo "Campanha concluída: $OUTPUT_DIR"
