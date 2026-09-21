#!/usr/bin/env bash
# Coletas HPC mínimas para explicar a diferença SIMD entre Zoom_In e Grayscale.
# Não acrescenta knobs ao VTune: a instalação 2021.1.1 do PCAD foi validada
# apenas com a invocação simples abaixo.
#SBATCH --job-name=openmp-hpc-simd
#SBATCH --partition=hype
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=20
#SBATCH --exclusive
#SBATCH --time=02:00:00
#SBATCH --output=slurm-hpc-simd-%j.out
#SBATCH --error=slurm-hpc-simd-%j.err

set -euo pipefail

SUBMIT_DIR="${SLURM_SUBMIT_DIR:?Execute com sbatch a partir da raiz do projeto.}"
IMAGE="${HPC_COMPLEMENTARY_IMAGE:-images/6000x6000.png}"
RESULT_DIR="$SUBMIT_DIR/resultados_pcad_hype_hpc_simd_${SLURM_JOB_ID}"
REFERENCE_HASHES="$RESULT_DIR/reference_hashes.csv"

mkdir -p "$RESULT_DIR"
[[ -f "$SUBMIT_DIR/$IMAGE" ]] || { echo "Imagem ausente: $IMAGE" >&2; exit 2; }

cd "$SUBMIT_DIR"
source "$SUBMIT_DIR/scripts/vtune_env.sh"
command -v vtune >/dev/null 2>&1 || { echo "VTune não encontrado no nó $(hostname)." >&2; exit 127; }

hostname > "$RESULT_DIR/hostname.txt"
lscpu > "$RESULT_DIR/lscpu.txt"
g++ --version > "$RESULT_DIR/compiler.txt" 2>&1 || true
vtune -version > "$RESULT_DIR/vtune_version.txt" 2>&1 || true

# -B evita reutilizar objetos compilados sem símbolos de depuração.
make -B DEBUG=1 SIMD=off-avx2 all
make -B DEBUG=1 SIMD=omp-avx2 all

# Referência comum: valida a saída normal, que é executada uma vez depois do
# kernel repetido no modo de profiling.
OMP_NUM_THREADS=1 OMP_DYNAMIC=FALSE OMP_SCHEDULE=static \
    build/off-avx2/image_benchmark --image "$IMAGE" /dev/null \
    --operations Zoom_In,Grayscale --hash-only --write-hashes "$REFERENCE_HASHES"

profile_iterations() {
    local operation="$1" threads="$2"
    case "$operation:$threads" in
        Zoom_In:1) echo 12 ;;
        Zoom_In:20) echo 120 ;;
        Grayscale:1) echo 25 ;;
        Grayscale:20) echo 350 ;;
        *) return 2 ;;
    esac
}

run_case() {
    local index="$1" operation="$2" simd="$3" threads="$4"
    local iterations case_name case_dir binary
    iterations="$(profile_iterations "$operation" "$threads")"
    case_name="$(printf '%02d_%s_%s_t%s' "$index" "$operation" "$simd" "$threads")"
    case_dir="$RESULT_DIR/$case_name"
    binary="build/$simd/image_benchmark"
    mkdir -p "$case_dir"

    {
        printf 'operation=%s\nsimd=%s\nthreads=%s\nschedule=static\nprofile_iterations=%s\nimage=%s\n' \
            "$operation" "$simd" "$threads" "$iterations" "$IMAGE"
        printf 'OMP_PLACES=%s\nOMP_PROC_BIND=%s\n' "${OMP_PLACES-unset}" "${OMP_PROC_BIND-unset}"
    } > "$case_dir/configuration.txt"

    echo "[$case_name] controle sem VTune"
    OMP_NUM_THREADS="$threads" OMP_DYNAMIC=FALSE OMP_SCHEDULE=static \
        "$binary" --image "$IMAGE" "$case_dir/control.csv" --operations "$operation" \
        --run-id "$case_name-control" --repeat 0 --warmup \
        --reference-hashes "$REFERENCE_HASHES" > "$case_dir/control.log" 2>&1

    echo "[$case_name] HPC Performance (${iterations} repetições internas do kernel)"
    OMP_NUM_THREADS="$threads" OMP_DYNAMIC=FALSE OMP_SCHEDULE=static \
        vtune -collect hpc-performance -result-dir "$case_dir/hpc_performance" -- \
        "$binary" --image "$IMAGE" "$case_dir/profile.csv" --operations "$operation" \
        --run-id "$case_name-profile" --repeat 0 --warmup \
        --profile-iterations "$iterations" --reference-hashes "$REFERENCE_HASHES" \
        > "$case_dir/vtune.log" 2>&1
    vtune -report summary -r "$case_dir/hpc_performance" \
        -report-output "$case_dir/summary.txt"
}

index=0
for operation in Zoom_In Grayscale; do
    for simd in off-avx2 omp-avx2; do
        for threads in 1 20; do
            run_case "$index" "$operation" "$simd" "$threads"
            ((index += 1))
        done
    done
done

echo "Coletas HPC concluídas: $RESULT_DIR"
