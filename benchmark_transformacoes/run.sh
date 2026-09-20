#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_dir="$(cd -- "$script_dir/.." && pwd)"

cd "$repo_dir"

runs_dir="$script_dir/runs"
mkdir -p "$runs_dir"
export MPLCONFIGDIR="$runs_dir/.matplotlib_cache"

# Check plotting dependencies before starting the long benchmark campaign.
python3 -c 'import pandas, matplotlib, seaborn' >/dev/null
make schedule-benchmark

run_dir="$runs_dir/$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir "$run_dir"
csv_path="$run_dir/benchmark_transformacoes.csv"

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

python3 "$script_dir/plot.py" "$csv_path"
printf 'CSV e gráficos concluídos em: %s\n' "$run_dir"
