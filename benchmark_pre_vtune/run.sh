#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_dir="$(cd -- "$script_dir/.." && pwd)"
binary="$repo_dir/build/image_benchmark"
image_path="${1:-$repo_dir/images/4000x3000.png}"

if [[ ! -x "$binary" ]]; then
    printf 'Executável não encontrado. Rode primeiro: %s/build.sh\n' "$script_dir" >&2
    exit 2
fi
if [[ ! -f "$image_path" ]]; then
    printf 'Imagem não encontrada: %s\n' "$image_path" >&2
    exit 2
fi

results_dir="$script_dir/results"
mkdir -p "$results_dir"
csv_path="$results_dir/run-$(date -u +%Y%m%dT%H%M%SZ)-$$.csv"

export OMP_NUM_THREADS=40
export OMP_DYNAMIC=FALSE
export OMP_SCHEDULE=static
unset ONLY_ADAPTIVE

printf 'Imagem: %s\n' "$image_path"
printf 'Threads: %s | Schedule: %s\n' "$OMP_NUM_THREADS" "$OMP_SCHEDULE"
printf 'CSV: %s\n' "$csv_path"

# exec makes the benchmark replace this shell, leaving a single clear process
# for an external profiler to launch and observe.
exec "$binary" --image "$image_path" "$csv_path"
