#!/usr/bin/env bash
# Reescritas isoladas: original vs candidato, 1/20 threads, static, três builds.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

OUTPUT_DIR="resultados_vetorizacao"
QUICK=0
while (($#)); do
    case "$1" in
        --output) (($# >= 2)) || { echo 'Falta diretório após --output' >&2; exit 2; }; OUTPUT_DIR="$2"; shift 2 ;;
        --quick) QUICK=1; shift ;;
        --help)
            echo 'Uso: bash run_vectorization_tests.sh [--output DIRETORIO_NOVO] [--quick]'
            echo 'A saída deve ser um diretório inexistente; resultados prévios nunca são apagados.'
            exit 0 ;;
        *) echo "Opção desconhecida: $1" >&2; exit 2 ;;
    esac
done
[[ ! -e "$OUTPUT_DIR" ]] || { echo "Diretório de saída já existe: $OUTPUT_DIR" >&2; exit 2; }
mkdir -p "$OUTPUT_DIR"
OUTPUT_DIR="$(cd "$OUTPUT_DIR" && pwd)"

OPERATIONS=(Negative Adjust_Brightness Adjust_Contrast Quantize Equalize_Histogram
            Flip_Horizontal Rotate_CW Rotate_CCW Grayscale Zoom_In
            Gaussian_3x3 Gaussian_5x5 Gaussian_7x7 Gaussian_9x9 Gaussian_11x11)
BUILDS=(off-avx2 auto-avx2 omp-avx2)
THREADS=(1 20)
IMAGES=(images/4000x3000.png images/6000x6000.png)
if ((QUICK)); then THREADS=(1); IMAGES=(images/poke.jpg); fi

for image in "${IMAGES[@]}" images/poke.jpg; do
    [[ -f "$image" ]] || { echo "Imagem ausente: $image" >&2; exit 1; }
done

g++ --version > "$OUTPUT_DIR/compiler.txt" 2>&1
git rev-parse HEAD > "$OUTPUT_DIR/git_commit.txt" 2>/dev/null || true
if command -v sha256sum >/dev/null 2>&1; then
    sha256sum Makefile 577262-FPI-Relatorio2/image_manipulation.cpp \
        577262-FPI-Relatorio2/vectorization_benchmark.cpp > "$OUTPUT_DIR/source_sha256.txt"
fi
if command -v lscpu >/dev/null 2>&1; then lscpu > "$OUTPUT_DIR/lscpu.txt"; fi
env | grep '^OMP_' | sort > "$OUTPUT_DIR/openmp_environment_before.txt" || true

for build in "${BUILDS[@]}"; do
    make -B DEBUG=1 SIMD="$build" COMPILER_DIAGNOSTICS=1 vectorization
    cp "build/$build/vectorization-experiment-all.log" "$OUTPUT_DIR/$build-compiler.txt"
    cp "build/$build/vectorization-core-all.log" "$OUTPUT_DIR/$build-original-core-compiler.txt"
    grep -E 'vectorization_benchmark.cpp:[0-9]+:[0-9]+: (optimized: loop vectorized|missed:.*vectoriz)' \
        "$OUTPUT_DIR/$build-compiler.txt" > "$OUTPUT_DIR/$build-compiler-focus.txt" || true
    if command -v objdump >/dev/null 2>&1; then
        objdump -d -C --no-show-raw-insn "build/$build/vectorization_benchmark" > "$OUTPUT_DIR/$build-assembly.txt"
    fi
done

export OMP_DYNAMIC=FALSE
export OMP_SCHEDULE=static
CSV="$OUTPUT_DIR/vectorization_raw.csv"

# Primeiro, todos os casos devem produzir saídas válidas na imagem pequena.
for build in "${BUILDS[@]}"; do
    for operation in "${OPERATIONS[@]}"; do
        OMP_NUM_THREADS=1 "build/$build/vectorization_benchmark" \
            --image images/poke.jpg --operation "$operation" "$CSV" --warmup --check-production
    done
done
echo 'Validação curta de todos os builds concluída.'

for image in "${IMAGES[@]}"; do
    for operation in "${OPERATIONS[@]}"; do
        # Zoom In quadruplica a saída; não repetir a imagem de 36 MP nesta
        # campanha de vetorização, para limitar RAM e não mudar o protocolo.
        if [[ "$operation" == Zoom_In && "$image" == images/6000x6000.png ]]; then continue; fi
        repetitions=10
        if [[ "$operation" == Gaussian_* && "$image" == images/6000x6000.png ]]; then repetitions=5; fi
        if ((QUICK)); then repetitions=1; fi
        for threads in "${THREADS[@]}"; do
            for build in "${BUILDS[@]}"; do
                OMP_NUM_THREADS="$threads" "build/$build/vectorization_benchmark" \
                    --image "$image" --operation "$operation" "$CSV" --warmup
            done
            for ((repeat=1; repeat<=repetitions; ++repeat)); do
                # Alterna a ordem dos builds entre repetições; os kernels de
                # um mesmo build seguem ordem fixa e isso fica documentado.
                offset=$(((repeat - 1) % ${#BUILDS[@]}))
                for ((index=0; index<${#BUILDS[@]}; ++index)); do
                    build="${BUILDS[$(((index + offset) % ${#BUILDS[@]}))]}"
                    OMP_NUM_THREADS="$threads" "build/$build/vectorization_benchmark" \
                        --image "$image" --operation "$operation" "$CSV" --repeat "$repeat"
                done
            done
        done
    done
done
if command -v python3 >/dev/null 2>&1; then
    python3 summarize_vectorization_results.py --raw "$CSV" --out "$OUTPUT_DIR/vectorization_summary.csv"
else
    echo 'python3 indisponível; CSV bruto salvo, resumo pode ser gerado depois.' >&2
fi
echo "Campanha concluída: $CSV"
