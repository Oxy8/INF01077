#!/usr/bin/env bash
#SBATCH --job-name=openmp-layout
#SBATCH --partition=hype
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=20
#SBATCH --exclusive
#SBATCH --time=08:00:00
#SBATCH --output=slurm-layout-%j.out
#SBATCH --error=slurm-layout-%j.err

# Teste complementar: AoS (RGBRGB...), SoA ingênuo e SoA separável.
# Mantém a configuração intencionalmente padrão: não força NUMA, afinidade ou
# arquitetura, e deixa OMP_NUM_THREADS/OMP_SCHEDULE para o script da campanha.
set -euo pipefail

SUBMIT_DIR="${SLURM_SUBMIT_DIR:?Execute com sbatch a partir da raiz do projeto.}"
JOB_ROOT="${SLURM_TMPDIR:-/tmp}/${USER}_openmp_layout_${SLURM_JOB_ID}"
WORK_DIR="$JOB_ROOT/project"
RESULT_DIR="$SUBMIT_DIR/resultados_pcad_hype_layout_aos_soa_${SLURM_JOB_ID}"

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

bash ./run_layout_tests.sh --output resultados_layout

cp -a resultados_layout/. "$RESULT_DIR/"
for report in build/*/vectorization-core.log; do
    [[ -f "$report" ]] || continue
    variant="$(basename "$(dirname "$report")")"
    cp -a "$report" "$RESULT_DIR/vectorization-layout-${variant}.log"
done
echo "Resultados copiados para $RESULT_DIR"
