#!/usr/bin/env bash
#SBATCH --job-name=openmp-simd-bench
#SBATCH --partition=hype
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=20
#SBATCH --exclusive
#SBATCH --time=24:00:00
#SBATCH --output=slurm-openmp-%j.out
#SBATCH --error=slurm-openmp-%j.err

set -euo pipefail

SUBMIT_DIR="${SLURM_SUBMIT_DIR:?Execute com sbatch a partir da raiz do projeto.}"
JOB_ROOT="${SLURM_TMPDIR:-/tmp}/${USER}_openmp_${SLURM_JOB_ID}"
WORK_DIR="$JOB_ROOT/project"
RESULT_DIR="$SUBMIT_DIR/resultados_pcad_hype_${SLURM_JOB_ID}"

cleanup() {
    rm -rf -- "$JOB_ROOT"
}
trap cleanup EXIT

mkdir -p "$WORK_DIR" "$RESULT_DIR"
cp -a "$SUBMIT_DIR/." "$WORK_DIR/"
cd "$WORK_DIR"

hostname
lscpu > "$RESULT_DIR/lscpu.txt"
numactl --hardware > "$RESULT_DIR/numa.txt" 2>&1 || true
g++ --version > "$RESULT_DIR/compiler.txt" 2>&1 || true
env | grep '^OMP_' | sort > "$RESULT_DIR/openmp_environment.txt" || true

export OMP_PLACES=cores
export OMP_PROC_BIND=close
export ARCH=haswell

# Intercala páginas entre os dois sockets para que uma alocação NUMA local não
# favoreça acidentalmente uma política de schedule.
# Argumentos repassados pelo sbatch permitem dividir a campanha, por exemplo:
# sbatch scripts/pcad_hype_benchmark.sbatch --regular-only
numactl --interleave=all bash ./run_tests.sh --output resultados_experimentos "$@"

cp -a resultados_experimentos/. "$RESULT_DIR/"
cp -a build/omp/vectorization-core.log "$RESULT_DIR/vectorization.log" 2>/dev/null || true
echo "Resultados copiados para $RESULT_DIR"
