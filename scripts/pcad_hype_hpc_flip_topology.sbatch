#!/usr/bin/env bash
# Testa se o ganho de dynamic no Flip vem de colocação/primeiro toque e da
# distribuição entre sockets. O VTune mede apenas pares de flips; a cópia não
# entra no trecho longo coletado.
#SBATCH --job-name=openmp-hpc-flip-topology
#SBATCH --partition=hype
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=20
#SBATCH --exclusive
#SBATCH --time=02:00:00
#SBATCH --output=slurm-hpc-flip-topology-%j.out
#SBATCH --error=slurm-hpc-flip-topology-%j.err

set -euo pipefail
SUBMIT_DIR="${SLURM_SUBMIT_DIR:?Execute sbatch a partir da raiz do projeto.}"
IMAGE="${HPC_FLIP_IMAGE:-images/6000x6000.png}"
RESULT_DIR="$SUBMIT_DIR/resultados_pcad_hype_hpc_flip_topology_${SLURM_JOB_ID}"
mkdir -p "$RESULT_DIR"
cd "$SUBMIT_DIR"
source scripts/vtune_env.sh
command -v vtune >/dev/null || { echo "VTune não encontrado em $(hostname)." >&2; exit 127; }
[[ -f "$IMAGE" ]] || { echo "Imagem ausente: $IMAGE" >&2; exit 2; }

export OMP_DYNAMIC=FALSE OMP_PLACES=cores OMP_PROC_BIND=close OMP_DISPLAY_AFFINITY=TRUE
hostname > "$RESULT_DIR/hostname.txt"; lscpu > "$RESULT_DIR/lscpu.txt"
env | grep '^OMP_' | sort > "$RESULT_DIR/openmp_environment.txt" || true
make -B DEBUG=1 SIMD=omp-avx2 flip-profile

run_case() {
    local index="$1" threads="$2" schedule="$3" init="$4" case_dir
    case_dir="$RESULT_DIR/$(printf '%02d_t%s_%s_%s' "$index" "$threads" "${schedule/,/_}" "$init")"; mkdir -p "$case_dir"
    printf 'threads=%s\nschedule=%s\ninit=%s\niterations=500\nimage=%s\n' "$threads" "$schedule" "$init" "$IMAGE" > "$case_dir/configuration.txt"
    OMP_NUM_THREADS="$threads" OMP_SCHEDULE="$schedule" build/omp-avx2/flip_profile_runner --image "$IMAGE" --iterations 1 --init "$init" --thread-csv "$case_dir/threads.csv" > "$case_dir/control.log" 2>&1
    OMP_NUM_THREADS="$threads" OMP_SCHEDULE="$schedule" vtune -collect hpc-performance -result-dir "$case_dir/hpc_performance" -- \
        build/omp-avx2/flip_profile_runner --image "$IMAGE" --iterations 500 --init "$init" > "$case_dir/vtune.log" 2>&1
    vtune -report summary -r "$case_dir/hpc_performance" -report-output "$case_dir/summary.txt"
    vtune -report hw-events -r "$case_dir/hpc_performance" -format=csv -report-output "$case_dir/hw_events.csv" || true
}

index=0
# 10 threads cobre um socket físico; 20 usa os dois. Para 20, compara a
# preparação serial atual com o first-touch paralelo em blocos contíguos.
for threads in 10 20; do
    for schedule in static dynamic,1; do
        for init in serial parallel-static; do
            run_case "$index" "$threads" "$schedule" "$init"; index=$((index + 1))
        done
    done
done
# Controle adicional: preenche a entrada usando a própria política dinâmica.
run_case "$index" 20 dynamic,1 parallel-runtime
echo "Coletas HPC de Flip/topologia salvas em $RESULT_DIR"
