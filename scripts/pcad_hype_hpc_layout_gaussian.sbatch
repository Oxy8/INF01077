#!/usr/bin/env bash
# Compara AoS direto, SoA ingênuo e SoA separável no VTune HPC Performance.
# Cada coleta repete somente o kernel selecionado; conversões e validação ficam
# fora da parte longa do perfil.
#SBATCH --job-name=openmp-hpc-layout
#SBATCH --partition=hype
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=20
#SBATCH --exclusive
#SBATCH --time=02:00:00
#SBATCH --output=slurm-hpc-layout-%j.out
#SBATCH --error=slurm-hpc-layout-%j.err

set -euo pipefail
SUBMIT_DIR="${SLURM_SUBMIT_DIR:?Execute sbatch a partir da raiz do projeto.}"
IMAGE="${HPC_LAYOUT_IMAGE:-images/6000x6000.png}"
RESULT_DIR="$SUBMIT_DIR/resultados_pcad_hype_hpc_layout_gaussian_${SLURM_JOB_ID}"
mkdir -p "$RESULT_DIR"
cd "$SUBMIT_DIR"
source scripts/vtune_env.sh
command -v vtune >/dev/null || { echo "VTune não encontrado em $(hostname)." >&2; exit 127; }
[[ -f "$IMAGE" ]] || { echo "Imagem ausente: $IMAGE" >&2; exit 2; }

export OMP_DYNAMIC=FALSE OMP_PLACES=cores OMP_PROC_BIND=close OMP_DISPLAY_AFFINITY=TRUE
hostname > "$RESULT_DIR/hostname.txt"; lscpu > "$RESULT_DIR/lscpu.txt"
env | grep '^OMP_' | sort > "$RESULT_DIR/openmp_environment.txt" || true
g++ --version > "$RESULT_DIR/compiler.txt" 2>&1 || true
vtune -version > "$RESULT_DIR/vtune_version.txt" 2>&1 || true
make -B DEBUG=1 SIMD=off-avx2 layout
make -B DEBUG=1 SIMD=omp-avx2 layout

iterations_for() {
    case "$1" in aos) echo 8 ;; soa-naive) echo 4 ;; soa-separable) echo 100 ;; esac
}
run_case() {
    local index="$1" build="$2" layout="$3" iterations case_dir
    iterations="$(iterations_for "$layout")"
    case_dir="$RESULT_DIR/$(printf '%02d_%s_%s' "$index" "$build" "$layout")"; mkdir -p "$case_dir"
    printf 'build=%s\nlayout=%s\nthreads=20\nschedule=static\nprofile_iterations=%s\nimage=%s\n' "$build" "$layout" "$iterations" "$IMAGE" > "$case_dir/configuration.txt"
    OMP_NUM_THREADS=20 OMP_SCHEDULE=static "build/$build/layout_benchmark" --image "$IMAGE" "$case_dir/control.csv" --operation Gaussian_11x11 --profile-layout "$layout" --warmup > "$case_dir/control.log" 2>&1
    OMP_NUM_THREADS=20 OMP_SCHEDULE=static vtune -collect hpc-performance -result-dir "$case_dir/hpc_performance" -- \
        "build/$build/layout_benchmark" --image "$IMAGE" "$case_dir/profile.csv" --operation Gaussian_11x11 --profile-layout "$layout" --profile-iterations "$iterations" --warmup > "$case_dir/vtune.log" 2>&1
    vtune -report summary -r "$case_dir/hpc_performance" -report-output "$case_dir/summary.txt"
    vtune -report hw-events -r "$case_dir/hpc_performance" -format=csv -report-output "$case_dir/hw_events.csv" || true
}

index=0
for build in off-avx2 omp-avx2; do
    for layout in aos soa-naive soa-separable; do
        run_case "$index" "$build" "$layout"; index=$((index + 1))
    done
done
echo "Coletas HPC de layout salvas em $RESULT_DIR"
