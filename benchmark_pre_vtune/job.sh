#!/usr/bin/env bash
#SBATCH --partition=hype
#SBATCH --time=00:30:00
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=40
#SBATCH --exclusive
#SBATCH --job-name=pre_vtune_hpc

set -euo pipefail

# Slurm executes a copy of this file. Accept submission from either the
# repository root or benchmark_pre_vtune itself.
submission_dir="${SLURM_SUBMIT_DIR:-$PWD}"
if [[ -f "$submission_dir/benchmark_pre_vtune/run.sh" ]]; then
    benchmark_dir="$submission_dir/benchmark_pre_vtune"
elif [[ -f "$submission_dir/run.sh" && "$(basename "$submission_dir")" == benchmark_pre_vtune ]]; then
    benchmark_dir="$submission_dir"
else
    printf 'Execute sbatch a partir da raiz do repositorio ou de benchmark_pre_vtune.\n' >&2
    exit 2
fi

repo_dir="$(cd -- "$benchmark_dir/.." && pwd)"
vtune_environment="/home/intel/oneapi/vtune/2021.1.1/vtune-vars.sh"

if [[ ! -r "$vtune_environment" ]]; then
    printf 'Configuracao do VTune nao encontrada: %s\n' "$vtune_environment" >&2
    exit 2
fi

# This is the VTune installation specified by the assignment for Hype nodes.
# shellcheck disable=SC1090
set +u
source "$vtune_environment"
set -u

if ! command -v vtune >/dev/null 2>&1; then
    printf 'O comando vtune nao ficou disponivel apos carregar %s\n' "$vtune_environment" >&2
    exit 2
fi

printf 'No: %s | CPUs alocadas por tarefa: %s\n' \
    "$(hostname)" "${SLURM_CPUS_PER_TASK:-desconhecido}"
vtune -version

# Force a profiling build so an older object compiled without -g is not reused.
CXXFLAGS='-O2 -g -Wall -Wextra' \
    make -B -C "$repo_dir" build/image_benchmark

results_root="$benchmark_dir/vtune_results"
mkdir -p "$results_root"
run_id="$(date -u +%Y%m%dT%H%M%SZ)-${SLURM_JOB_ID:-$$}"
result_dir="$results_root/hpc-$run_id"

printf 'Analise: hpc-performance\n'
printf 'Resultado VTune: %s\n' "$result_dir"

vtune \
    -collect hpc-performance \
    -result-dir "$result_dir" \
    -- "$benchmark_dir/run.sh"

vtune \
    -report summary \
    -r "$result_dir" \
    -report-output "$result_dir/summary.txt"

printf 'Analise concluida. Resumo: %s/summary.txt\n' "$result_dir"
