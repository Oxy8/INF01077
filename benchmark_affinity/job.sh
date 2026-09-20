#!/usr/bin/env bash
#SBATCH --partition=hype
#SBATCH --time=24:00:00
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=40
#SBATCH --exclusive
#SBATCH --job-name=affinity_denoiser_negative

set -euo pipefail

# Slurm executes a copy of the batch script; use the submission directory.
submission_dir="${SLURM_SUBMIT_DIR:-$PWD}"
if [[ -f "$submission_dir/benchmark_affinity/run.sh" ]]; then
    benchmark_dir="$submission_dir/benchmark_affinity"
elif [[ -f "$submission_dir/run.sh" && "$(basename "$submission_dir")" == benchmark_affinity ]]; then
    benchmark_dir="$submission_dir"
else
    printf 'Execute sbatch a partir da raiz do repositorio ou de benchmark_affinity.\n' >&2
    exit 2
fi
cd "$benchmark_dir"

unset GOMP_CPU_AFFINITY
printf 'Nó: %s | CPUs alocadas por tarefa: %s\n' "$(hostname)" "${SLURM_CPUS_PER_TASK:-desconhecido}"

for affinity in default close spread; do
    if [[ "$affinity" == default ]]; then
        unset OMP_PLACES OMP_PROC_BIND
    else
        export OMP_PLACES=cores
        export OMP_PROC_BIND="$affinity"
    fi
    export BENCHMARK_AFFINITY_LABEL="$affinity"

    printf '\nAfinidade: %s | OMP_PLACES=%s | OMP_PROC_BIND=%s\n' \
        "$affinity" "${OMP_PLACES:-unset}" "${OMP_PROC_BIND:-unset}"
    bash "$benchmark_dir/run.sh"
done

printf '\nAs três campanhas de afinidade foram concluídas.\n'
