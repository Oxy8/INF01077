#!/usr/bin/env bash
# Coleta contadores por processo para TODAS as operações regulares em 1 e 20
# threads. Esta é uma medição de aplicação completa (decodificação, backup,
# kernel e hash); compare o mesmo caso entre builds/threads, mas não a
# apresente como contagem exclusiva do kernel. Para o caso de localidade mais
# importante, Gaussian 11x11 é repetido no executável de layouts com buffers
# pré-alocados e somente a variante selecionada dominando a janela.
#SBATCH --job-name=openmp-regular-memory
#SBATCH --partition=hype
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=20
#SBATCH --exclusive
#SBATCH --time=24:00:00
#SBATCH --output=slurm-regular-memory-%j.out
#SBATCH --error=slurm-regular-memory-%j.err

set -euo pipefail

SUBMIT_DIR="${SLURM_SUBMIT_DIR:?Execute sbatch a partir da raiz do projeto.}"
IMAGE="${REGULAR_MEMORY_IMAGE:-images/6000x6000.png}"
REPEATS="${REGULAR_MEMORY_REPEATS:-5}"
RESULT_DIR="$SUBMIT_DIR/resultados_pcad_hype_regular_memory_1_20_${SLURM_JOB_ID}"
HASHES="$RESULT_DIR/reference_hashes_off-avx2.txt"
OPERATIONS=(
    Grayscale Flip_Horizontal Adjust_Brightness Flip_Vertical Quantize
    Adjust_Contrast Negative Equalize_Histogram Zoom_In Zoom_Out Rotate_CW
    Rotate_CCW Gaussian_3x3 Gaussian_5x5 Gaussian_7x7 Gaussian_9x9 Gaussian_11x11
)

[[ -f "$IMAGE" ]] || { echo "Imagem ausente: $IMAGE" >&2; exit 2; }
mkdir -p "$RESULT_DIR"
cd "$SUBMIT_DIR"

command -v perf >/dev/null || { echo "perf não encontrado neste nó." >&2; exit 127; }
if ! perf stat -e cycles,instructions -- true > "$RESULT_DIR/perf_preflight.out" 2> "$RESULT_DIR/perf_preflight.err"; then
    echo "perf stat não tem permissão neste nó; veja perf_preflight.err." >&2
    exit 3
fi

export OMP_DYNAMIC=FALSE
export OMP_SCHEDULE=static
# Mantém o mapeamento padrão do runtime; não introduz afinidade manual nesta
# recampanha. O arquivo openmp_environment.txt registra o estado efetivo.
unset OMP_PLACES OMP_PROC_BIND

hostname > "$RESULT_DIR/hostname.txt"
lscpu > "$RESULT_DIR/lscpu.txt"
env | grep '^OMP_' | sort > "$RESULT_DIR/openmp_environment.txt" || true
g++ --version > "$RESULT_DIR/compiler.txt" 2>&1
perf list --no-desc > "$RESULT_DIR/perf_list.txt" 2>&1 || true
printf 'Imagem=%s\nRepeticoes por grupo=%s\nSchedule=static\nThreads=1,20\nBuilds=off-avx2,omp-avx2\n' \
    "$IMAGE" "$REPEATS" > "$RESULT_DIR/configuration.txt"

make -B DEBUG=1 SIMD=off-avx2 all layout
make -B DEBUG=1 SIMD=omp-avx2 all layout

OMP_NUM_THREADS=1 build/off-avx2/image_benchmark --image "$IMAGE" "$RESULT_DIR/hashes_seed.csv" \
    --operations regular --run-id "reference" --repeat 0 --hash-only --write-hashes "$HASHES"

BASIC_EVENTS='cycles,instructions,cache-references,cache-misses'
CACHE_EVENTS='L1-dcache-loads,L1-dcache-load-misses,LLC-loads,LLC-load-misses'
CACHE_EVENTS_AVAILABLE=1
if ! perf stat -e "$CACHE_EVENTS" -- true > /dev/null 2> "$RESULT_DIR/cache_events_preflight.err"; then
    CACHE_EVENTS_AVAILABLE=0
fi

run_regular_perf() {
    local build="$1" threads="$2" operation="$3" group="$4" events="$5" repeat="$6"
    local case_dir="$RESULT_DIR/regular/$operation/$build/${threads}t/$group"
    mkdir -p "$case_dir"
    printf 'scope=end-to-end (load+backup+kernel+hash)\noperation=%s\nbuild=%s\nthreads=%s\nschedule=static\nevents=%s\nimage=%s\n' \
        "$operation" "$build" "$threads" "$events" "$IMAGE" > "$case_dir/configuration.txt"
    OMP_NUM_THREADS="$threads" perf stat -x, --no-big-num -e "$events" \
        -o "$case_dir/perf_${repeat}.csv" -- \
        "build/$build/image_benchmark" --image "$IMAGE" "$case_dir/benchmark_${repeat}.csv" \
        --operations "$operation" --run-id "perf-$operation-$build-${threads}t-$group" --repeat "$repeat" \
        --reference-hashes "$HASHES" > "$case_dir/run_${repeat}.out" 2> "$case_dir/run_${repeat}.err"
}

# O profile-layout repete a variante escolhida com buffers já alocados. Ele é a
# coleta adequada para atribuir comportamento de cache ao kernel gaussiano.
layout_iterations() {
    case "$1" in
        aos) echo 25 ;;
        soa-naive) echo 12 ;;
        soa-separable) echo 400 ;;
    esac
}

run_layout_perf() {
    local build="$1" threads="$2" layout="$3" group="$4" events="$5" repeat="$6"
    local iterations case_dir
    iterations="$(layout_iterations "$layout")"
    case_dir="$RESULT_DIR/gaussian11_kernel/$layout/$build/${threads}t/$group"
    mkdir -p "$case_dir"
    printf 'scope=kernel-dominated (profile-layout)\nlayout=%s\nbuild=%s\nthreads=%s\nschedule=static\nprofile_iterations=%s\nevents=%s\nimage=%s\n' \
        "$layout" "$build" "$threads" "$iterations" "$events" "$IMAGE" > "$case_dir/configuration.txt"
    OMP_NUM_THREADS="$threads" perf stat -x, --no-big-num -e "$events" \
        -o "$case_dir/perf_${repeat}.csv" -- \
        "build/$build/layout_benchmark" --image "$IMAGE" "$case_dir/benchmark_${repeat}.csv" \
        --operation Gaussian_11x11 --profile-layout "$layout" --profile-iterations "$iterations" \
        --run-id "perf-gaussian11-$layout-$build-${threads}t-$group" --repeat "$repeat" --warmup \
        > "$case_dir/run_${repeat}.out" 2> "$case_dir/run_${repeat}.err"
}

for build in off-avx2 omp-avx2; do
    for threads in 1 20; do
        for operation in "${OPERATIONS[@]}"; do
            for repeat in $(seq 1 "$REPEATS"); do
                run_regular_perf "$build" "$threads" "$operation" basic "$BASIC_EVENTS" "$repeat"
                if [[ "$CACHE_EVENTS_AVAILABLE" == 1 ]]; then
                    run_regular_perf "$build" "$threads" "$operation" cache "$CACHE_EVENTS" "$repeat"
                fi
            done
        done
        for layout in aos soa-naive soa-separable; do
            for repeat in $(seq 1 "$REPEATS"); do
                run_layout_perf "$build" "$threads" "$layout" basic "$BASIC_EVENTS" "$repeat"
                if [[ "$CACHE_EVENTS_AVAILABLE" == 1 ]]; then
                    run_layout_perf "$build" "$threads" "$layout" cache "$CACHE_EVENTS" "$repeat"
                fi
            done
        done
    done
done

cat > "$RESULT_DIR/LEIA_PRIMEIRO.txt" <<'EOF'
Escopo e interpretação
======================
Há dois escopos deliberadamente separados:
1. regular/: aplicação completa por operação. Os contadores incluem carga PNG,
   cópia de backup, kernel e hash. Compare somente a mesma operação, build,
   threads e grupo de eventos. Isto identifica pressão global, mas não permite
   atribuir cada miss exclusivamente ao loop da transformação.
2. gaussian11_kernel/: a variante de layout escolhida é repetida com buffers
   pré-alocados; o kernel domina a janela. É a evidência adequada para AoS
   direto versus SoA ingênuo versus SoA separável.

Métricas principais
-------------------
- Tempo e speedup vêm de pcad_hype_regular_1_20_simd.sbatch, não de perf.
- Para cache, normalize misses por pixel de saída e, como apoio, use MPKI.
- Nunca conclua ganho SIMD por CPI: SIMD altera o número/tipo de instruções.
  CPI é no máximo diagnóstico secundário no mesmo binário e mesma contagem
  de threads; use tempo por pixel e razão de medianas para desempenho.
- Compare apenas arquivos do mesmo grupo (basic ou cache), pois perf não mede
  todos os eventos simultaneamente.
EOF

echo "Coleta de memória salva em $RESULT_DIR"
