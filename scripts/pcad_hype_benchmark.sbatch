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
CAMPAIGN="completa"
case " $* " in
    *" --regular-only "*) CAMPAIGN="regular" ;;
    *" --adaptive-only "*) CAMPAIGN="adaptativo" ;;
    *" --smt-only "*) CAMPAIGN="smt" ;;
esac
RESULT_DIR="$SUBMIT_DIR/resultados_pcad_hype_benchmark_${CAMPAIGN}_${SLURM_JOB_ID}"

cleanup() {
    rm -rf -- "$JOB_ROOT"
}
trap cleanup EXIT

mkdir -p "$WORK_DIR" "$RESULT_DIR"
cp -a "$SUBMIT_DIR/." "$WORK_DIR/"
cd "$WORK_DIR"

hostname
lscpu > "$RESULT_DIR/lscpu.txt"
g++ --version > "$RESULT_DIR/compiler.txt" 2>&1 || true
env | grep '^OMP_' | sort > "$RESULT_DIR/openmp_environment.txt" || true

# Argumentos repassados pelo sbatch permitem dividir a campanha, por exemplo:
# sbatch scripts/pcad_hype_benchmark.sbatch --regular-only
bash ./run_tests.sh --output resultados_experimentos "$@"

cp -a resultados_experimentos/. "$RESULT_DIR/"
for report in build/*/vectorization-core.log; do
    [[ -f "$report" ]] || continue
    variant="$(basename "$(dirname "$report")")"
    cp -a "$report" "$RESULT_DIR/vectorization-${variant}.log"
done
echo "Resultados copiados para $RESULT_DIR"
