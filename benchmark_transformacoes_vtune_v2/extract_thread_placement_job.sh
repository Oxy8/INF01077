#!/usr/bin/env bash
#SBATCH --partition=hype
#SBATCH --time=24:00:00
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --job-name=placement_vtune_v2
#SBATCH --output=placement-vtune-v2-%j.out

set -euo pipefail

submission_dir="${SLURM_SUBMIT_DIR:-$PWD}"
if [[ -f "$submission_dir/benchmark_transformacoes_vtune_v2/extract_thread_placement.py" ]]; then
    benchmark_dir="$submission_dir/benchmark_transformacoes_vtune_v2"
elif [[ -f "$submission_dir/extract_thread_placement.py" &&
        "$(basename "$submission_dir")" == benchmark_transformacoes_vtune_v2 ]]; then
    benchmark_dir="$submission_dir"
else
    printf 'Run sbatch from the repository root or benchmark_transformacoes_vtune_v2.\n' >&2
    exit 2
fi

default_run="$benchmark_dir/runs/20260923T072517Z-823852"
run_dir="${RUN_DIR:-$default_run}"
if [[ "$run_dir" != /* ]]; then
    run_dir="$submission_dir/$run_dir"
fi

if [[ ! -f "$run_dir/manifest.csv" ]]; then
    printf 'Campaign manifest not found: %s/manifest.csv\n' "$run_dir" >&2
    exit 2
fi
if ! find "$run_dir/collections" -mindepth 2 -maxdepth 2 \
        -type d -name result -print -quit 2>/dev/null | grep -q .; then
    printf 'No raw VTune result directories found under: %s/collections\n' "$run_dir" >&2
    printf 'The consolidated campaign CSV is insufficient for this extraction.\n' >&2
    exit 2
fi

vtune_root="${VTUNE_ROOT:-/home/intel/oneapi/vtune/2021.1.1}"
vtune_environment="${VTUNE_VARS:-$vtune_root/vtune-vars.sh}"
if [[ ! -r "$vtune_environment" ]]; then
    printf 'VTune environment not found: %s\n' "$vtune_environment" >&2
    exit 2
fi

set +u
# shellcheck disable=SC1090
source "$vtune_environment"
set -u

job_id="${SLURM_JOB_ID:-manual}"
log_path="$run_dir/extract-thread-placement-$job_id.log"

printf 'Node: %s | CPUs: %s\n' "$(hostname)" "${SLURM_CPUS_PER_TASK:-1}"
printf 'Campaign: %s\n' "$run_dir"
printf 'Log: %s\n' "$log_path"
vtune -version

python3 "$benchmark_dir/extract_thread_placement.py" "$run_dir" 2>&1 | tee "$log_path"

