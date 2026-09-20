#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_dir="$(cd -- "$script_dir/.." && pwd)"

cd "$repo_dir"

runs_dir="$script_dir/runs"
mkdir -p "$runs_dir"

make schedule-benchmark

run_dir="$runs_dir/$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir "$run_dir"
csv_path="$run_dir/benchmark_transformacoes.csv"

{
    printf 'Affinity=%s\n' "${BENCHMARK_AFFINITY_LABEL:-unspecified}"
    printf 'OMP_PLACES=%s\n' "${OMP_PLACES:-unset}"
    printf 'OMP_PROC_BIND=%s\n' "${OMP_PROC_BIND:-unset}"
    printf 'SLURM_JOB_ID=%s\n' "${SLURM_JOB_ID:-unset}"
    printf 'SLURM_CPUS_PER_TASK=%s\n' "${SLURM_CPUS_PER_TASK:-unset}"
    printf 'Host=%s\n' "$(hostname)"
} > "$run_dir/config.txt"

export OMP_DYNAMIC=FALSE
unset ONLY_ADAPTIVE

schedules=(static)
for ((chunk = 1; chunk <= 1024; chunk *= 2)); do
    schedules+=("dynamic,$chunk")
done

printf 'Resultados desta execução: %s\n' "$run_dir"
for repetition in {1..5}; do
    for threads in 20 40; do
        for schedule in "${schedules[@]}"; do
            printf 'Repetição %d/5 | %d threads | %s\n' "$repetition" "$threads" "$schedule"
            OMP_NUM_THREADS="$threads" OMP_SCHEDULE="$schedule" \
                "$repo_dir/build/image_schedule_benchmark" \
                --folder "$repo_dir/images" "$csv_path" "$repetition"
        done
    done
done

printf 'CSV concluído em: %s\n' "$csv_path"
