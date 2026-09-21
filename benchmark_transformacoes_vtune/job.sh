#!/usr/bin/env bash
#SBATCH --partition=hype
#SBATCH --time=24:00:00
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=40
#SBATCH --exclusive
#SBATCH --job-name=vtune_transformacoes

set -euo pipefail

submission_dir="${SLURM_SUBMIT_DIR:-$PWD}"
if [[ -f "$submission_dir/benchmark_transformacoes_vtune/run.sh" ]]; then
    benchmark_dir="$submission_dir/benchmark_transformacoes_vtune"
elif [[ -f "$submission_dir/run.sh" &&
        "$(basename "$submission_dir")" == benchmark_transformacoes_vtune ]]; then
    benchmark_dir="$submission_dir"
else
    printf 'Execute sbatch a partir da raiz do repositorio ou de benchmark_transformacoes_vtune.\n' >&2
    exit 2
fi

export VTUNE_ROOT="${VTUNE_ROOT:-/home/intel/oneapi/vtune/2021.1.1}"
vtune_environment="${VTUNE_VARS:-$VTUNE_ROOT/vtune-vars.sh}"
if [[ ! -r "$vtune_environment" ]]; then
    printf 'Configuracao do VTune nao encontrada: %s\n' "$vtune_environment" >&2
    exit 2
fi

set +u
# shellcheck disable=SC1090
source "$vtune_environment"
set -u

printf 'No: %s | CPUs por tarefa: %s\n' \
    "$(hostname)" "${SLURM_CPUS_PER_TASK:-desconhecido}"
vtune -version

exec bash "$benchmark_dir/run.sh"
