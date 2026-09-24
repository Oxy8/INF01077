#!/usr/bin/env bash
# Mede contadores de cache do Linux perf para os três layouts Gaussianos.
# O VTune HPC já indica Cache Bound; esta coleta acrescenta taxas observáveis
# de L1 e LLC, separadas por processo e sem a instrumentação do VTune.
#SBATCH --job-name=openmp-cache-counters
#SBATCH --partition=hype
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=20
#SBATCH --exclusive
#SBATCH --time=01:00:00
#SBATCH --output=slurm-cache-counters-%j.out
#SBATCH --error=slurm-cache-counters-%j.err

set -euo pipefail

SUBMIT_DIR="${SLURM_SUBMIT_DIR:?Execute sbatch a partir da raiz do projeto.}"
IMAGE="${CACHE_COUNTERS_IMAGE:-images/6000x6000.png}"
RESULT_DIR="$SUBMIT_DIR/resultados_pcad_hype_cache_counters_${SLURM_JOB_ID}"
mkdir -p "$RESULT_DIR"
cd "$SUBMIT_DIR"

command -v perf >/dev/null || { echo "perf não encontrado neste nó." >&2; exit 127; }
[[ -f "$IMAGE" ]] || { echo "Imagem ausente: $IMAGE" >&2; exit 2; }

export OMP_NUM_THREADS=20
export OMP_DYNAMIC=FALSE
export OMP_PLACES=cores
export OMP_PROC_BIND=close
export OMP_SCHEDULE=static

hostname > "$RESULT_DIR/hostname.txt"
lscpu > "$RESULT_DIR/lscpu.txt"
env | grep '^OMP_' | sort > "$RESULT_DIR/openmp_environment.txt" || true
g++ --version > "$RESULT_DIR/compiler.txt" 2>&1
perf list --no-desc > "$RESULT_DIR/perf_list.txt" 2>&1 || true

# Falha cedo com uma mensagem interpretável se os contadores forem bloqueados.
if ! perf stat -e cycles,instructions -- true > "$RESULT_DIR/perf_preflight.out" 2> "$RESULT_DIR/perf_preflight.err"; then
    echo "perf stat não tem permissão neste nó; veja perf_preflight.err." >&2
    exit 3
fi

make -B DEBUG=1 SIMD=off-avx2 layout
make -B DEBUG=1 SIMD=omp-avx2 layout

iterations_for() {
    case "$1" in
        aos) echo 25 ;;
        soa-naive) echo 12 ;;
        soa-separable) echo 400 ;;
    esac
}

run_perf() {
    local index="$1" build="$2" layout="$3" events_name="$4" events="$5"
    local case_dir iterations repeat
    iterations="$(iterations_for "$layout")"
    case_dir="$RESULT_DIR/$(printf '%02d_%s_%s_%s' "$index" "$build" "$layout" "$events_name")"
    mkdir -p "$case_dir"
    printf 'build=%s\nlayout=%s\nthreads=20\nschedule=static\nprofile_iterations=%s\nevents=%s\nimage=%s\n' \
        "$build" "$layout" "$iterations" "$events" "$IMAGE" > "$case_dir/configuration.txt"

    # Cinco processos independentes preservam as amostras brutas. O trecho
    # profile-layout domina a execução; warmup elimina a primeira execução.
    for repeat in 1 2 3 4 5; do
        OMP_NUM_THREADS=20 OMP_SCHEDULE=static perf stat -x, --no-big-num \
            -e "$events" -o "$case_dir/perf_$repeat.csv" -- \
            "build/$build/layout_benchmark" --image "$IMAGE" "$case_dir/benchmark_$repeat.csv" \
            --operation Gaussian_11x11 --profile-layout "$layout" \
            --profile-iterations "$iterations" --warmup \
            > "$case_dir/run_$repeat.out" 2> "$case_dir/run_$repeat.err"
    done
}

BASIC_EVENTS='cycles,instructions,cache-references,cache-misses'
CACHE_EVENTS='L1-dcache-loads,L1-dcache-load-misses,LLC-loads,LLC-load-misses'

# Verifica o segundo grupo sem interromper o job se a nomenclatura do kernel
# não oferecer L1/LLC. O grupo básico sempre é coletado.
CACHE_EVENTS_AVAILABLE=1
if ! perf stat -e "$CACHE_EVENTS" -- true > /dev/null 2> "$RESULT_DIR/cache_events_preflight.err"; then
    CACHE_EVENTS_AVAILABLE=0
fi

index=0
for build in off-avx2 omp-avx2; do
    for layout in aos soa-naive soa-separable; do
        run_perf "$index" "$build" "$layout" basic "$BASIC_EVENTS"
        index=$((index + 1))
        if [[ "$CACHE_EVENTS_AVAILABLE" == 1 ]]; then
            run_perf "$index" "$build" "$layout" cache "$CACHE_EVENTS"
            index=$((index + 1))
        fi
    done
done

cat > "$RESULT_DIR/LEIA_PRIMEIRO.txt" <<'EOF'
Os perf_*.csv são amostras brutas do perf stat no formato CSV.

Métricas a calcular por amostra:
- taxa de cache-miss = cache-misses / cache-references;
- misses L1 e LLC por pixel de saída (métrica primária);
- L1 MPKI = 1000 * L1-dcache-load-misses / instructions;
- LLC MPKI = 1000 * LLC-load-misses / instructions (métrica auxiliar).

Não use CPI para comparar builds SIMD com scalar: SIMD muda tanto a
quantidade quanto o tipo de instrução. Tempo por pixel e misses por pixel são
as métricas principais. CPI só pode ser anotado como diagnóstico secundário
dentro do mesmo binário, número de threads e algoritmo.

Compare apenas casos do mesmo grupo de eventos. Não compare o tempo do perf
entre layouts: cada layout deliberadamente usa número diferente de iterações
para dar ao contador uma janela longa e estável.
EOF

echo "Coleta de cache salva em $RESULT_DIR"
