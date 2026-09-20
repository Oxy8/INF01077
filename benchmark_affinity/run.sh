#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_dir="$(cd -- "$script_dir/.." && pwd)"
dynamic_chunk="${AFFINITY_DYNAMIC_CHUNK:-16}"
if [[ ! "$dynamic_chunk" =~ ^[1-9][0-9]*$ ]]; then
    printf 'AFFINITY_DYNAMIC_CHUNK deve ser um inteiro positivo.\n' >&2
    exit 2
fi

cd "$repo_dir"
make schedule-benchmark

runs_dir="$script_dir/runs"
mkdir -p "$runs_dir"
run_dir="$runs_dir/$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir "$run_dir"

export OMP_DYNAMIC=FALSE
unset ONLY_ADAPTIVE

{
    printf 'Affinity=%s\n' "${BENCHMARK_AFFINITY_LABEL:-unspecified}"
    printf 'OMP_PLACES=%s\n' "${OMP_PLACES:-unset}"
    printf 'OMP_PROC_BIND=%s\n' "${OMP_PROC_BIND:-unset}"
    printf 'OMP_DYNAMIC=%s\n' "$OMP_DYNAMIC"
    printf 'Threads=40\n'
    printf 'Schedules=static,dynamic,%s\n' "$dynamic_chunk"
    printf 'Repetitions=5\n'
    printf 'Images=%s\n' "$repo_dir/images"
    printf 'SLURM_JOB_ID=%s\n' "${SLURM_JOB_ID:-unset}"
    printf 'SLURM_CPUS_PER_TASK=%s\n' "${SLURM_CPUS_PER_TASK:-unset}"
    printf 'SLURM_CPU_BIND=%s\n' "${SLURM_CPU_BIND:-unset}"
    printf 'Host=%s\n' "$(hostname)"
    if [[ -r "/proc/$$/status" ]]; then
        while IFS= read -r status_line; do
            case "$status_line" in
                Cpus_allowed_list:*|Mems_allowed_list:*) printf '%s\n' "$status_line" ;;
            esac
        done < "/proc/$$/status"
    fi
} > "$run_dir/config.txt"

printf 'Resultados desta execução: %s\n' "$run_dir"
for transformation in Adaptive_Gaussian Negative; do
    case "$transformation" in
        Adaptive_Gaussian) csv_path="$run_dir/adaptive_gaussian.csv" ;;
        Negative) csv_path="$run_dir/negative.csv" ;;
    esac

    for repetition in {1..5}; do
        for schedule in static "dynamic,$dynamic_chunk"; do
            printf '%s | repetição %d/5 | 40 threads | %s\n' \
                "$transformation" "$repetition" "$schedule"
            OMP_NUM_THREADS=40 OMP_SCHEDULE="$schedule" \
                "$repo_dir/build/image_schedule_benchmark" \
                --folder "$repo_dir/images" "$csv_path" "$repetition" \
                --transformation "$transformation"
        done
    done
    printf 'CSV concluído: %s\n' "$csv_path"
done
