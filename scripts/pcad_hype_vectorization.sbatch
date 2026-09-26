#!/usr/bin/env bash
#SBATCH --job-name=openmp-vectorization
#SBATCH --partition=hype
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=20
#SBATCH --exclusive
#SBATCH --time=1-00:00:00
#SBATCH --output=slurm-vectorization-%j.out
#SBATCH --error=slurm-vectorization-%j.err
set -euo pipefail

SUBMIT_DIR="${SLURM_SUBMIT_DIR:?Submeta a partir da raiz do repositório.}"
[[ -f "$SUBMIT_DIR/Makefile" && -f "$SUBMIT_DIR/run_vectorization_tests.sh" ]] || {
    echo 'Submeta a partir da raiz do repositório.' >&2; exit 2;
}
SCRATCH_BASE="${SLURM_TMPDIR:-/tmp}"
SCRATCH_BASE="$(cd "$SCRATCH_BASE" && pwd -P)"
WORK_DIR="$SCRATCH_BASE/${USER}_vectorization_${SLURM_JOB_ID}"
RESULT_DIR="$SUBMIT_DIR/resultados_pcad_hype_vectorization_${SLURM_JOB_ID}"
[[ ! -e "$WORK_DIR" && ! -e "$RESULT_DIR" ]] || {
    echo 'Diretório temporário ou de resultados já existe.' >&2; exit 2;
}
mkdir -p "$WORK_DIR/images"
cleanup() {
    if [[ -d "$WORK_DIR" ]]; then
        resolved="$(cd "$WORK_DIR" && pwd -P)"
        if [[ "$resolved" == "$SCRATCH_BASE/${USER}_vectorization_${SLURM_JOB_ID}" ]]; then
            rm -rf -- "$resolved"
        fi
    fi
}
trap cleanup EXIT
cp -a "$SUBMIT_DIR/Makefile" "$SUBMIT_DIR/run_vectorization_tests.sh" \
      "$SUBMIT_DIR/summarize_vectorization_results.py" "$WORK_DIR/"
cp -a "$SUBMIT_DIR/577262-FPI-Relatorio2" "$WORK_DIR/"
cp -a "$SUBMIT_DIR/images/4000x3000.png" "$SUBMIT_DIR/images/6000x6000.png" \
      "$SUBMIT_DIR/images/poke.jpg" "$WORK_DIR/images/"
cd "$WORK_DIR"
hostname
bash ./run_vectorization_tests.sh --output "$RESULT_DIR"
git -C "$SUBMIT_DIR" rev-parse HEAD > "$RESULT_DIR/git_commit.txt" 2>/dev/null || true
echo "Resultados: $RESULT_DIR"
