#!/usr/bin/env bash
# Diagnóstico causal curto: fases do Zoom, schedules do Flip e evidência do GCC.
# A campanha principal não é repetida; todos os casos usam 6000x6000 e 20
# núcleos físicos quando o objetivo é comparar schedules.
#SBATCH --job-name=openmp-diagnostics
#SBATCH --partition=hype
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=20
#SBATCH --exclusive
#SBATCH --time=02:00:00
#SBATCH --output=slurm-diagnostics-%j.out
#SBATCH --error=slurm-diagnostics-%j.err

set -euo pipefail

SUBMIT_DIR="${SLURM_SUBMIT_DIR:?Execute com sbatch a partir da raiz do projeto.}"
RESULT_DIR="$SUBMIT_DIR/resultados_pcad_hype_diagnostico_zoom_flip_compilador_${SLURM_JOB_ID}"
IMAGE="images/6000x6000.png"
ZOOM_RAW="$RESULT_DIR/zoom_phases_raw.csv"
FLIP_RAW="$RESULT_DIR/flip_raw.csv"
FLIP_THREADS="$RESULT_DIR/flip_threads_raw.csv"
REFERENCE_HASHES="$RESULT_DIR/reference_hashes.csv"

# O PCAD pode disponibilizar apenas python3. O resumo usa somente a biblioteca
# padrão (csv, statistics e argparse), sem pacotes instalados pelo usuário.
PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "$PYTHON_BIN" ]]; then
    for candidate in python3 python; do
        if command -v "$candidate" >/dev/null 2>&1; then
            PYTHON_BIN="$candidate"
            break
        fi
    done
fi
[[ -n "$PYTHON_BIN" ]] || { echo "Python 3 não encontrado; os CSVs brutos serão preservados, mas o resumo não pode ser gerado." >&2; exit 127; }

mkdir -p "$RESULT_DIR/compiler"
cd "$SUBMIT_DIR"
[[ -f "$IMAGE" ]] || { echo "Imagem ausente: $IMAGE" >&2; exit 2; }

hostname > "$RESULT_DIR/hostname.txt"
lscpu > "$RESULT_DIR/lscpu.txt"
g++ --version > "$RESULT_DIR/compiler.txt" 2>&1 || true
export OMP_DYNAMIC=FALSE
export OMP_PLACES=cores
export OMP_PROC_BIND=close
env | grep '^OMP_' | sort > "$RESULT_DIR/openmp_environment.txt" || true

# Builds de desempenho para os tempos e build adicional para a evidência do
# compilador. A última produz relatórios completos e assembly, não timings.
make -B SIMD=off-avx2 all diagnostics
make -B SIMD=omp-avx2 all diagnostics
make compiler-evidence
for build in off-avx2 omp-avx2; do
    for artifact in vectorization-core-all.log vectorization-layout-all.log layout_benchmark.asm; do
        [[ -f "build/$build/$artifact" ]] && cp -a "build/$build/$artifact" "$RESULT_DIR/compiler/${build}-${artifact}"
    done
done

# Hash de referência escalar e controle normal AVX2. As medições por fase usam
# o mesmo kernel, mas não acrescentam hash no caminho cronometrado.
OMP_NUM_THREADS=1 OMP_SCHEDULE=static build/off-avx2/image_benchmark \
    --image "$IMAGE" /dev/null --operations Zoom_In,Flip_Horizontal --hash-only \
    --write-hashes "$REFERENCE_HASHES"
OMP_NUM_THREADS=20 OMP_SCHEDULE=static build/omp-avx2/image_benchmark \
    --image "$IMAGE" /dev/null --operations Zoom_In,Flip_Horizontal --warmup \
    --reference-hashes "$REFERENCE_HASHES" > "$RESULT_DIR/validation.log" 2>&1

run_zoom() {
    local build="$1" threads="$2" schedule="$3" touch="$4" experiment="$5"
    OMP_NUM_THREADS="$threads" OMP_SCHEDULE="$schedule" "build/$build/diagnostic_runner" \
        --mode zoom --image "$IMAGE" --output "$ZOOM_RAW" --experiment "$experiment" \
        --touch "$touch" --repeats 10
}

# Efeito SIMD por fase e por quantidade de threads, todos em static.
for build in off-avx2 omp-avx2; do
    for threads in 1 2 4 8 12 16 20; do
        run_zoom "$build" "$threads" static fresh zoom-scaling-static
    done
done

# Separa custo da fila dinâmica, distribuição cíclica e first-touch da saída.
for schedule in static static,1 static,16 dynamic,1 dynamic,16 dynamic,64; do
    for touch in fresh pretouch-static; do
        run_zoom omp-avx2 20 "$schedule" "$touch" zoom-schedule-touch
    done
done

# Flip: a ordem dos cinco schedules é embaralhada em cada rodada; a cópia de
# restauração fica fora da janela de tempo. O CSV por thread permite observar
# se dynamic apenas compensa threads momentaneamente mais lentas.
OMP_NUM_THREADS=20 OMP_SCHEDULE=static build/omp-avx2/diagnostic_runner \
    --mode flip --image "$IMAGE" --output "$FLIP_RAW" --thread-output "$FLIP_THREADS" \
    --experiment flip-schedule-confirmation --touch fresh --repeats 12 --seed 823349

"$PYTHON_BIN" summarize_diagnostics.py \
    --zoom-raw "$ZOOM_RAW" --zoom-summary "$RESULT_DIR/zoom_phases_summary.csv" \
    --flip-raw "$FLIP_RAW" --flip-summary "$RESULT_DIR/flip_summary.csv"

printf 'Diagnóstico concluído: %s\n' "$RESULT_DIR"
