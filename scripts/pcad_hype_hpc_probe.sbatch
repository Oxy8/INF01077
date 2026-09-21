#!/usr/bin/env bash
# Sonda mínima de HPC Performance. Replica o padrão que funcionou em outro
# trabalho no hype antes de voltar a misturar layouts, repetição interna e
# opções adicionais na campanha principal.
#SBATCH --job-name=openmp-hpc-probe
#SBATCH --partition=hype
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=40
#SBATCH --exclusive
#SBATCH --time=00:30:00
#SBATCH --output=slurm-hpc-probe-%j.out
#SBATCH --error=slurm-hpc-probe-%j.err

set -euo pipefail

IMAGE="${HPC_PROBE_IMAGE:-images/4000x3000.png}"
OPERATIONS="${HPC_PROBE_OPERATIONS:-all}"
THREADS="${HPC_PROBE_THREADS:-40}"
SCHEDULE="${HPC_PROBE_SCHEDULE:-static}"
SIMD="${HPC_PROBE_SIMD:-omp-avx2}"

# --export do Slurm separa valores por vírgula. Aceitar dynamic4 evita ter de
# escapar a vírgula na linha de submissão.
case "$SCHEDULE" in
    dynamic4) SCHEDULE='dynamic,4' ;;
    dynamic16) SCHEDULE='dynamic,16' ;;
    dynamic256) SCHEDULE='dynamic,256' ;;
esac

SUBMIT_DIR="${SLURM_SUBMIT_DIR:?Execute com sbatch a partir da raiz do projeto.}"
RESULT_DIR="$SUBMIT_DIR/resultados_pcad_hype_hpc_probe_${SLURM_JOB_ID}"
mkdir -p "$RESULT_DIR"

source "$SUBMIT_DIR/scripts/vtune_env.sh"
command -v vtune >/dev/null 2>&1 || { echo "VTune não encontrado." >&2; exit 127; }

hostname > "$RESULT_DIR/hostname.txt"
lscpu > "$RESULT_DIR/lscpu.txt"
vtune -version > "$RESULT_DIR/vtune_version.txt" 2>&1 || vtune --version > "$RESULT_DIR/vtune_version.txt" 2>&1

# Força recompilação com símbolos, sem remover -O3. Não usa knobs VTune.
make -B DEBUG=1 SIMD="$SIMD" all

export OMP_NUM_THREADS="$THREADS"
export OMP_DYNAMIC=FALSE
export OMP_SCHEDULE="$SCHEDULE"

CONTROL_CSV="$RESULT_DIR/controle_sem_vtune.csv"
PROFILE_CSV="$RESULT_DIR/benchmark_hpc.csv"
VTUNE_RESULT="$RESULT_DIR/hpc_performance"

echo "Controle sem VTune: imagem=$IMAGE operações=$OPERATIONS threads=$THREADS schedule=$SCHEDULE"
"build/$SIMD/image_benchmark" --image "$IMAGE" "$CONTROL_CSV" \
    --operations "$OPERATIONS" --run-id hpc-probe-control --repeat 0

echo "HPC Performance sem knobs adicionais:"
vtune -collect hpc-performance -result-dir "$VTUNE_RESULT" -- \
    "build/$SIMD/image_benchmark" --image "$IMAGE" "$PROFILE_CSV" \
    --operations "$OPERATIONS" --run-id hpc-probe --repeat 0

vtune -report summary -r "$VTUNE_RESULT" -report-output "$RESULT_DIR/summary.txt"
echo "Sonda concluída. Resultado: $VTUNE_RESULT"
