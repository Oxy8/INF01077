#!/usr/bin/env bash
# Campanha curta: fases Quantize/Equalize e repetição controlada de Zoom In.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"
OUTPUT_DIR=resultados_simd_phase_zoom
QUICK=0
while (($#)); do
    case "$1" in
        --output) (($# >= 2)) || { echo 'Falta diretório após --output' >&2; exit 2; }; OUTPUT_DIR="$2"; shift 2 ;;
        --quick) QUICK=1; shift ;;
        --help)
            echo 'Uso: bash run_simd_phase_zoom_tests.sh [--output DIRETORIO_NOVO] [--quick]'
            echo 'Quick: poke.jpg, uma thread e uma repetição; não sobrescreve resultados.'
            exit 0 ;;
        *) echo "Opção desconhecida: $1" >&2; exit 2 ;;
    esac
done
[[ ! -e "$OUTPUT_DIR" ]] || { echo "Diretório já existe: $OUTPUT_DIR" >&2; exit 2; }
command -v python3 >/dev/null 2>&1 || { echo 'python3 não encontrado.' >&2; exit 2; }
mkdir -p "$OUTPUT_DIR"
OUTPUT_DIR="$(cd "$OUTPUT_DIR" && pwd)"

ZOOM_IMAGE=images/6000x6000.png
CONTROL_IMAGES=(images/4000x3000.png images/6000x6000.png)
ZOOM_THREADS=(1 2 4 8 12 16 17 18 19 20)
PHASE_THREADS=(1 20)
REPETITIONS=10
ZOOM_REPETITIONS=20
if ((QUICK)); then
    ZOOM_IMAGE=images/poke.jpg
    CONTROL_IMAGES=(images/poke.jpg)
    ZOOM_THREADS=(1)
    PHASE_THREADS=(1)
    REPETITIONS=1
    ZOOM_REPETITIONS=1
fi
for image in "$ZOOM_IMAGE" "${CONTROL_IMAGES[@]}"; do
    [[ -f "$image" ]] || { echo "Imagem ausente: $image" >&2; exit 2; }
done
BIN_SUFFIX=""
case "$(uname -s)" in MSYS*|MINGW*) BIN_SUFFIX=.exe ;; esac

g++ --version > "$OUTPUT_DIR/compiler.txt" 2>&1
hostname > "$OUTPUT_DIR/hostname.txt"
env | grep '^OMP_' | sort > "$OUTPUT_DIR/openmp_environment_before.txt" || true
git rev-parse HEAD > "$OUTPUT_DIR/git_commit.txt" 2>/dev/null || true
if command -v sha256sum >/dev/null 2>&1; then
    sha256sum Makefile run_simd_phase_zoom_tests.sh \
        577262-FPI-Relatorio2/image_manipulation.cpp \
        577262-FPI-Relatorio2/vectorization_benchmark.cpp \
        577262-FPI-Relatorio2/simd_phase_benchmark.cpp > "$OUTPUT_DIR/source_sha256.txt"
    sha256sum "$ZOOM_IMAGE" "${CONTROL_IMAGES[@]}" > "$OUTPUT_DIR/input_sha256.txt"
fi
if command -v lscpu >/dev/null 2>&1; then lscpu > "$OUTPUT_DIR/lscpu.txt"; fi
{
    printf 'Zoom produção: %s; threads %s; %s repetições por ponto\n' \
        "$ZOOM_IMAGE" "${ZOOM_THREADS[*]}" "$ZOOM_REPETITIONS"
    printf 'Zoom controle: %s; threads 1 e 20; %s repetições\n' \
        "${CONTROL_IMAGES[*]}" "$REPETITIONS"
    printf 'Fases: Quantize e Equalize_Histogram, 36 MP, threads %s, %s repetições\n' \
        "${PHASE_THREADS[*]}" "$REPETITIONS"
    echo 'OMP_SCHEDULE=static; OMP_DYNAMIC=FALSE; builds off-avx2, auto-avx2 e omp-avx2.'
    echo 'Fases são réplicas da aritmética de produção, validadas byte a byte.'
    echo 'Quantize inclui Grayscale; Equalize calcula luminância na contagem, sem conversão prévia.'
    echo 'Zoom produção inclui alocação interna; Zoom controle mede somente kernel com saída pré-alocada.'
    echo 'Cada comando tem aquecimento. A ordem dos builds gira e a ordem de threads alterna entre rodadas.'
} > "$OUTPUT_DIR/protocol.txt"

BUILDS=(off-avx2 auto-avx2 omp-avx2)
for build in "${BUILDS[@]}"; do
    make -B DEBUG=1 SIMD="$build" COMPILER_DIAGNOSTICS=1 all vectorization simd-phases
    cp "build/$build/vectorization-core-all.log" "$OUTPUT_DIR/$build-core-compiler.txt"
    cp "build/$build/vectorization-experiment-all.log" "$OUTPUT_DIR/$build-experiment-compiler.txt"
    cp "build/$build/vectorization-simd-phases-all.log" "$OUTPUT_DIR/$build-phase-compiler.txt"
done

export OMP_DYNAMIC=FALSE
export OMP_SCHEDULE=static
ZOOM_CSV="$OUTPUT_DIR/zoom_production_raw.csv"
CONTROL_CSV="$OUTPUT_DIR/zoom_control_raw.csv"
PHASE_CSV="$OUTPUT_DIR/phase_raw.csv"
HASHES="$OUTPUT_DIR/zoom_reference_hashes.csv"

# Primeiro validar resultados completos com uma referência do próprio job.
OMP_NUM_THREADS=1 "build/off-avx2/image_benchmark$BIN_SUFFIX" --image "$ZOOM_IMAGE" "$ZOOM_CSV" \
    --operations Zoom_In --hash-only --write-hashes "$HASHES"
for build in "${BUILDS[@]}"; do
    OMP_NUM_THREADS=1 "build/$build/image_benchmark$BIN_SUFFIX" --image "$ZOOM_IMAGE" "$ZOOM_CSV" \
        --operations Zoom_In --hash-only --reference-hashes "$HASHES"
    for image in "${CONTROL_IMAGES[@]}"; do
        OMP_NUM_THREADS=1 "build/$build/vectorization_benchmark$BIN_SUFFIX" \
            --image "$image" --operation Zoom_In --clean-linearization --check-production \
            "$CONTROL_CSV" --warmup
    done
    for operation in Quantize Equalize_Histogram; do
        OMP_NUM_THREADS=1 "build/$build/simd_phase_benchmark$BIN_SUFFIX" \
            --image "$ZOOM_IMAGE" --operation "$operation" --csv "$PHASE_CSV" --warmup
    done
done
echo 'Pré-voo de hashes e fases concluído.'

# Repetição da primeira campanha: sete pontos originais e 17/18/19 threads.
for threads in "${ZOOM_THREADS[@]}"; do
    for build in "${BUILDS[@]}"; do
        OMP_NUM_THREADS="$threads" "build/$build/image_benchmark$BIN_SUFFIX" \
            --image "$ZOOM_IMAGE" "$ZOOM_CSV" --operations Zoom_In \
            --reference-hashes "$HASHES" --warmup
    done
done
for ((repeat=1; repeat<=ZOOM_REPETITIONS; ++repeat)); do
    ordered_threads=("${ZOOM_THREADS[@]}")
    if ((repeat % 2 == 0)); then
        ordered_threads=()
        for ((thread_index=${#ZOOM_THREADS[@]}-1; thread_index>=0; --thread_index)); do
            ordered_threads+=("${ZOOM_THREADS[$thread_index]}")
        done
    fi
    for threads in "${ordered_threads[@]}"; do
        for ((index=0; index<${#BUILDS[@]}; ++index)); do
            build="${BUILDS[$(((index + repeat - 1) % ${#BUILDS[@]}))]}"
            OMP_NUM_THREADS="$threads" "build/$build/image_benchmark$BIN_SUFFIX" \
                --image "$ZOOM_IMAGE" "$ZOOM_CSV" --operations Zoom_In \
                --reference-hashes "$HASHES" --run-id simd-phase-zoom --repeat "$repeat"
        done
    done
done

# Mesmo controle do segundo mapa, agora também em 36 MP.
for image in "${CONTROL_IMAGES[@]}"; do
    for threads in "${PHASE_THREADS[@]}"; do
        for build in "${BUILDS[@]}"; do
            OMP_NUM_THREADS="$threads" "build/$build/vectorization_benchmark$BIN_SUFFIX" \
                --image "$image" --operation Zoom_In --clean-linearization --check-production \
                "$CONTROL_CSV" --warmup
        done
        for ((repeat=1; repeat<=REPETITIONS; ++repeat)); do
            for ((index=0; index<${#BUILDS[@]}; ++index)); do
                build="${BUILDS[$(((index + repeat - 1) % ${#BUILDS[@]}))]}"
                OMP_NUM_THREADS="$threads" "build/$build/vectorization_benchmark$BIN_SUFFIX" \
                    --image "$image" --operation Zoom_In --clean-linearization \
                    "$CONTROL_CSV" --repeat "$repeat"
            done
        done
    done
done

# Não altera as operações originais: mede total e réplicas exatas das fases.
for operation in Quantize Equalize_Histogram; do
    for threads in "${PHASE_THREADS[@]}"; do
        for build in "${BUILDS[@]}"; do
            OMP_NUM_THREADS="$threads" "build/$build/simd_phase_benchmark$BIN_SUFFIX" \
                --image "$ZOOM_IMAGE" --operation "$operation" --csv "$PHASE_CSV" --warmup
        done
        for ((repeat=1; repeat<=REPETITIONS; ++repeat)); do
            for ((index=0; index<${#BUILDS[@]}; ++index)); do
                build="${BUILDS[$(((index + repeat - 1) % ${#BUILDS[@]}))]}"
                OMP_NUM_THREADS="$threads" "build/$build/simd_phase_benchmark$BIN_SUFFIX" \
                    --image "$ZOOM_IMAGE" --operation "$operation" --csv "$PHASE_CSV" \
                    --repeat "$repeat"
            done
        done
    done
done

python3 summarize_linear_simd.py --raw "$CONTROL_CSV" --out "$OUTPUT_DIR/zoom_control_summary.csv"
python3 summarize_simd_phase_zoom.py --production "$ZOOM_CSV" --phases "$PHASE_CSV" \
    --out "$OUTPUT_DIR"
if ((!QUICK)); then
    python3 plot_simd_phase_zoom.py --summary "$OUTPUT_DIR/zoom_production_summary.csv" \
        --phases "$OUTPUT_DIR/phase_summary.csv" --out "$OUTPUT_DIR/figures"
fi
echo "Campanha concluída: $OUTPUT_DIR"
