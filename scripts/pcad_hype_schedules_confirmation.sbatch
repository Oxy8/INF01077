#!/usr/bin/env bash
#SBATCH --job-name=openmp-sched-confirm
#SBATCH --partition=hype
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=20
#SBATCH --exclusive
#SBATCH --time=01:30:00
#SBATCH --output=slurm-sched-confirm-%j.out
#SBATCH --error=slurm-sched-confirm-%j.err

set -euo pipefail

SUBMIT_DIR="${SLURM_SUBMIT_DIR:?Execute com sbatch a partir da raiz do projeto.}"
JOB_ROOT="${SLURM_TMPDIR:-/tmp}/${USER}_openmp_schedules_${SLURM_JOB_ID}"
WORK_DIR="$JOB_ROOT/project"
RESULT_DIR="$SUBMIT_DIR/resultados_pcad_hype_schedules_${SLURM_JOB_ID}"

cleanup() { rm -rf -- "$JOB_ROOT"; }
trap cleanup EXIT

mkdir -p "$WORK_DIR" "$RESULT_DIR"
cp -a "$SUBMIT_DIR/Makefile" "$SUBMIT_DIR/summarize_results.py" "$WORK_DIR/"
cp -a "$SUBMIT_DIR/577262-FPI-Relatorio2" "$WORK_DIR/"
mkdir -p "$WORK_DIR/images" "$WORK_DIR/scripts"
cp -a "$SUBMIT_DIR/images/6000x6000.png" "$WORK_DIR/images/"
cp -a "$SUBMIT_DIR/scripts/run_complementary_schedules.sh" "$WORK_DIR/scripts/"

cd "$WORK_DIR"
hostname > "$RESULT_DIR/hostname.txt"
lscpu > "$RESULT_DIR/lscpu.txt"
g++ --version > "$RESULT_DIR/compiler.txt" 2>&1 || true

bash scripts/run_complementary_schedules.sh resultados_schedules_complementares
cp -a resultados_schedules_complementares/. "$RESULT_DIR/"
echo "Resultados copiados para $RESULT_DIR"
