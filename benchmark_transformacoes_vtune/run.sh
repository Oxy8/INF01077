#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_dir="$(cd -- "$script_dir/.." && pwd)"
default_vtune_root="/home/intel/oneapi/vtune/2021.1.1"
vtune_root="${VTUNE_ROOT:-$default_vtune_root}"
vtune_environment="${VTUNE_VARS:-$vtune_root/vtune-vars.sh}"

if ! command -v vtune >/dev/null 2>&1; then
    if [[ ! -r "$vtune_environment" ]]; then
        printf 'Configuracao do VTune nao encontrada: %s\n' "$vtune_environment" >&2
        exit 2
    fi
    # VTune's environment script is not safe under nounset.
    set +u
    # shellcheck disable=SC1090
    source "$vtune_environment"
    set -u
fi

if ! command -v vtune >/dev/null 2>&1; then
    printf 'O comando vtune nao esta disponivel.\n' >&2
    exit 2
fi
if ! command -v python3 >/dev/null 2>&1; then
    printf 'O comando python3 e necessario para consolidar os CSVs.\n' >&2
    exit 2
fi

cd "$repo_dir"
make -B vtune-schedule-benchmark VTUNE_DIR="$vtune_root"

binary="$repo_dir/build/image_schedule_vtune_benchmark"
calibration_source="$script_dir/repetitions.csv"
runs_dir="$script_dir/runs"
mkdir -p "$runs_dir"

if [[ -n "${RUN_DIR:-}" ]]; then
    mkdir -p "$RUN_DIR"
    run_dir="$(cd -- "$RUN_DIR" && pwd)"
else
    run_id="$(date -u +%Y%m%dT%H%M%SZ)-${SLURM_JOB_ID:-$$}"
    run_dir="$runs_dir/$run_id"
    mkdir "$run_dir"
fi
campaign_id="$(basename "$run_dir")"

if [[ ! -f "$run_dir/repetitions.csv" ]]; then
    cp "$calibration_source" "$run_dir/repetitions.csv"
fi
calibration_file="$run_dir/repetitions.csv"

transformations=()
iterations=()
while IFS=, read -r transformation workload_iterations _; do
    [[ "$transformation" == "Transformation" ]] && continue
    [[ -z "$transformation" ]] && continue
    if [[ ! "$workload_iterations" =~ ^[1-9][0-9]*$ ]]; then
        printf 'Iteracoes invalidas para %s em %s\n' "$transformation" "$calibration_file" >&2
        exit 2
    fi
    transformations+=("$transformation")
    iterations+=("$workload_iterations")
done < "$calibration_file"

mapfile -t binary_transformations < <("$binary" --list-transformations)
if [[ "${#transformations[@]}" -ne 18 ||
      "${#binary_transformations[@]}" -ne "${#transformations[@]}" ]]; then
    printf 'A configuracao e o executavel devem conter exatamente 18 transformacoes.\n' >&2
    exit 2
fi
for index in "${!transformations[@]}"; do
    if [[ "${transformations[$index]}" != "${binary_transformations[$index]}" ]]; then
        printf 'Transformacao divergente na posicao %d: CSV=%s executavel=%s\n' \
            "$index" "${transformations[$index]}" "${binary_transformations[$index]}" >&2
        exit 2
    fi
done

export OMP_DYNAMIC=FALSE
unset OMP_PLACES OMP_PROC_BIND GOMP_CPU_AFFINITY ONLY_ADAPTIVE

vtune_version="$(vtune -version 2>&1 | tr '\n' ';' | sed 's/;*$//')"
cpu_model="$(awk -F: '/model name/{sub(/^[[:space:]]+/, "", $2); print $2; exit}' /proc/cpuinfo)"
kernel="$(uname -srmo)"
host="$(hostname)"
git_commit="$(git -C "$repo_dir" rev-parse HEAD 2>/dev/null || printf unknown)"
if [[ -n "$(git -C "$repo_dir" status --porcelain 2>/dev/null || true)" ]]; then
    git_status="dirty"
else
    git_status="clean"
fi

help_text="$(vtune -help collect hpc-performance 2>&1 || true)"
printf '%s\n' "$help_text" > "$run_dir/vtune-hpc-help.txt"
knob_arguments=()
knob_labels=()
add_supported_knob() {
    local name="$1"
    local value="$2"
    if grep -Fq "$name" <<< "$help_text"; then
        knob_arguments+=("-knob" "$name=$value")
        knob_labels+=("$name=$value")
    fi
}
add_supported_knob enable-stack-collection true
add_supported_knob collect-memory-bandwidth true
add_supported_knob dram-bandwidth-limits true
add_supported_knob analyze-openmp true
add_supported_knob collect-affinity true
add_supported_knob enable-user-tasks true
vtune_knobs="${knob_labels[*]:-defaults}"

cat > "$run_dir/campaign.env" <<EOF
Campaign_ID=$campaign_id
Slurm_Job_ID=${SLURM_JOB_ID:-unset}
Host=$host
VTune_Version=$vtune_version
VTune_Root=$vtune_root
CPU_Model=$cpu_model
Kernel=$kernel
Affinity_Label=default_unset
OMP_DYNAMIC=$OMP_DYNAMIC
OMP_PLACES=unset
OMP_PROC_BIND=unset
GOMP_CPU_AFFINITY=unset
VTune_Knobs=$vtune_knobs
Git_Commit=$git_commit
Git_Status=$git_status
EOF

schedules_raw=("static")
schedules_normalized=("static")
schedule_kinds=("static")
schedule_chunks=("")
for ((chunk = 1; chunk <= 1024; chunk *= 2)); do
    schedules_raw+=("dynamic,$chunk")
    schedules_normalized+=("dynamic_$chunk")
    schedule_kinds+=("dynamic")
    schedule_chunks+=("$chunk")
done
threads_values=(20 40)

manifest_tmp="$run_dir/manifest.csv.tmp"
printf 'Collection_ID,Collection_Repetition,Num_Threads,OMP_Schedule_Raw,OMP_Schedule,Schedule_Kind,Chunk_Size,Transformation,Workload_Iterations\n' > "$manifest_tmp"
for index in "${!transformations[@]}"; do
    for threads in "${threads_values[@]}"; do
        for schedule_index in "${!schedules_raw[@]}"; do
            schedule_id="${schedules_normalized[$schedule_index]}"
            printf -v collection_id 'threads_%03d__%s__%s' \
                "$threads" "$schedule_id" "${transformations[$index]}"
            printf '%s,1,%d,"%s",%s,%s,%s,%s,%d\n' \
                "$collection_id" "$threads" "${schedules_raw[$schedule_index]}" \
                "$schedule_id" "${schedule_kinds[$schedule_index]}" \
                "${schedule_chunks[$schedule_index]}" "${transformations[$index]}" \
                "${iterations[$index]}" >> "$manifest_tmp"
        done
    done
done

manifest="$run_dir/manifest.csv"
if [[ -f "$manifest" ]]; then
    if ! cmp -s "$manifest" "$manifest_tmp"; then
        printf 'O manifesto existente nao corresponde a configuracao atual: %s\n' "$manifest" >&2
        rm -f "$manifest_tmp"
        exit 2
    fi
    rm -f "$manifest_tmp"
else
    mv "$manifest_tmp" "$manifest"
fi

expected_collections=$(($(wc -l < "$manifest") - 1))
if [[ "$expected_collections" -ne 432 ]]; then
    printf 'Manifesto invalido: %d colecoes; esperado: 432.\n' "$expected_collections" >&2
    exit 2
fi

finalized=0
finalize_partial_table() {
    local exit_status=$?
    if [[ "$finalized" -eq 0 && -f "$manifest" ]]; then
        python3 "$script_dir/aggregate.py" "$run_dir" || true
    fi
    return "$exit_status"
}
trap finalize_partial_table EXIT

report_csv() {
    local result_dir="$1"
    local report_name="$2"
    local output="$3"
    local group_by="${4:-}"
    local log_file="$output.log"
    rm -f "$output"
    local command=(vtune -report "$report_name" -r "$result_dir" -format csv
                   -csv-delimiter comma -report-output "$output")
    if [[ -n "$group_by" ]]; then
        command+=("-group-by" "$group_by")
    fi
    if ! "${command[@]}" > "$log_file" 2>&1; then
        rm -f "$output"
        return 1
    fi
    [[ -s "$output" ]]
}

supported_groupings() {
    local result_dir="$1"
    local report_name="$2"
    vtune -report "$report_name" -r "$result_dir" -group-by=? 2>&1 || true
}

load_report_capabilities() {
    local result_dir="$1"
    local capabilities="$run_dir/report-capabilities.env"
    frame_group=""
    task_supported=0
    hw_task_supported=0
    if [[ -f "$capabilities" ]]; then
        while IFS='=' read -r key value; do
            case "$key" in
                Frame_Group) frame_group="$value" ;;
                Task_Supported) task_supported="$value" ;;
                HW_Task_Supported) hw_task_supported="$value" ;;
            esac
        done < "$capabilities"
        [[ -n "$frame_group" ]] || return 1
        return 0
    fi

    local hotspots_groups hw_groups
    hotspots_groups="$(supported_groupings "$result_dir" hotspots)"
    hw_groups="$(supported_groupings "$result_dir" hw-events)"
    printf '%s\n' "$hotspots_groups" > "$run_dir/hotspots-groupings.txt"
    printf '%s\n' "$hw_groups" > "$run_dir/hw-events-groupings.txt"

    if grep -Fqi 'frame-domain' <<< "$hotspots_groups"; then
        frame_group="frame-domain,frame"
    elif grep -Eqi '(^|[^[:alnum:]-])frame([^[:alnum:]-]|$)' <<< "$hotspots_groups"; then
        frame_group="frame"
    else
        return 1
    fi
    if grep -Eqi '(^|[^[:alnum:]-])task([^[:alnum:]-]|$)' <<< "$hotspots_groups"; then
        task_supported=1
    fi
    if grep -Eqi '(^|[^[:alnum:]-])task([^[:alnum:]-]|$)' <<< "$hw_groups"; then
        hw_task_supported=1
    fi
    cat > "$capabilities" <<EOF
Frame_Group=$frame_group
Task_Supported=$task_supported
HW_Task_Supported=$hw_task_supported
EOF
}

write_collection_metadata() {
    local path="$1"
    local collection_id="$2"
    local threads="$3"
    local schedule_raw="$4"
    local schedule_normalized="$5"
    local transformation="$6"
    local workload_iterations="$7"
    cat > "$path" <<EOF
Campaign_ID=$campaign_id
Collection_ID=$collection_id
Collection_Repetition=1
Slurm_Job_ID=${SLURM_JOB_ID:-unset}
Host=$host
VTune_Version=$vtune_version
CPU_Model=$cpu_model
Kernel=$kernel
Num_Threads=$threads
OMP_Schedule_Raw=$schedule_raw
OMP_Schedule=$schedule_normalized
Transformation=$transformation
Workload_Iterations=$workload_iterations
Affinity_Label=default_unset
OMP_PLACES=unset
OMP_PROC_BIND=unset
GOMP_CPU_AFFINITY=unset
VTune_Knobs=$vtune_knobs
Git_Commit=$git_commit
Git_Status=$git_status
EOF
}

collection_complete() {
    local directory="$1"
    [[ -f "$directory/.complete" &&
       -s "$directory/metadata.env" &&
       -s "$directory/timings.csv" &&
       -d "$directory/result" &&
       -s "$directory/reports/summary.csv" &&
       -s "$directory/reports/hotspots.csv" &&
       -s "$directory/reports/hw-events.csv" &&
       -s "$directory/reports/frames.csv" ]]
}

check_storage_after_first_collection() {
    [[ -f "$run_dir/storage_estimate.txt" ]] && return 0
    local collection_dir="$1"
    local size_kb available_kb remaining_kb required_kb
    size_kb="$(du -sk "$collection_dir" | awk '{print $1}')"
    available_kb="$(df -Pk "$run_dir" | awk 'NR==2 {print $4}')"
    remaining_kb=$((size_kb * (expected_collections - 1)))
    required_kb=$((remaining_kb * 6 / 5))
    cat > "$run_dir/storage_estimate.txt" <<EOF
First_Collection_KB=$size_kb
Projected_Remaining_KB=$remaining_kb
Required_With_20_Percent_Headroom_KB=$required_kb
Available_KB=$available_kb
EOF
    if ((required_kb > available_kb)); then
        printf 'Espaco insuficiente: estimativa em %s\n' "$run_dir/storage_estimate.txt" >&2
        return 1
    fi
}

ensure_preflight() {
    [[ -f "$run_dir/preflight.ok" ]] && return 0
    printf 'Validando a primeira coleta e o formato dos relatorios VTune...\n'
    python3 "$script_dir/aggregate.py" "$run_dir" --expected-collections 432
    touch "$run_dir/preflight.ok"
}

run_collection() {
    local collection_id="$1"
    local threads="$2"
    local schedule_raw="$3"
    local schedule_normalized="$4"
    local transformation="$5"
    local workload_iterations="$6"
    local collection_dir="$run_dir/collections/$collection_id"

    if collection_complete "$collection_dir"; then
        printf 'Ja concluida: %s\n' "$collection_id"
        return 0
    fi

    rm -rf -- "$collection_dir"
    mkdir -p "$collection_dir/reports"
    write_collection_metadata "$collection_dir/metadata.env" "$collection_id" \
        "$threads" "$schedule_raw" "$schedule_normalized" "$transformation" \
        "$workload_iterations"

    local result_dir="$collection_dir/result"
    local timings="$collection_dir/timings.csv"
    printf 'Coleta %s | threads=%d | schedule=%s | transformacao=%s | iteracoes=%d\n' \
        "$collection_id" "$threads" "$schedule_raw" "$transformation" \
        "$workload_iterations"

    if ! OMP_NUM_THREADS="$threads" OMP_SCHEDULE="$schedule_raw" \
        vtune -collect hpc-performance -start-paused \
            "${knob_arguments[@]}" \
            -result-dir "$result_dir" \
            -- "$binary" \
                --folder "$repo_dir/images" \
                --output "$timings" \
                --collection-id "$collection_id" \
                --repetition 1 \
                --transformation "$transformation" \
                --iterations "$workload_iterations" \
            > "$collection_dir/collection.log" 2>&1; then
        printf 'Falha na coleta VTune. Veja %s\n' "$collection_dir/collection.log" \
            | tee "$collection_dir/failure.txt" >&2
        return 1
    fi

    local frame_group task_supported hw_task_supported
    if ! load_report_capabilities "$result_dir"; then
        printf 'O VTune nao disponibilizou agrupamento por frame.\n' \
            | tee "$collection_dir/failure.txt" >&2
        return 1
    fi

    if ! report_csv "$result_dir" summary "$collection_dir/reports/summary.csv"; then
        printf 'Falha ao exportar summary.\n' | tee "$collection_dir/failure.txt" >&2
        return 1
    fi
    if ! report_csv "$result_dir" hotspots "$collection_dir/reports/hotspots.csv" function; then
        printf 'Falha ao exportar hotspots.\n' | tee "$collection_dir/failure.txt" >&2
        return 1
    fi
    if ! report_csv "$result_dir" hw-events "$collection_dir/reports/hw-events.csv" function; then
        printf 'Falha ao exportar hw-events.\n' | tee "$collection_dir/failure.txt" >&2
        return 1
    fi
    if ! report_csv "$result_dir" hotspots "$collection_dir/reports/frames.csv" "$frame_group"; then
        printf 'Falha ao exportar frames.\n' | tee "$collection_dir/failure.txt" >&2
        return 1
    fi

    : > "$collection_dir/reports/unsupported-reports.txt"
    if [[ "$task_supported" -eq 1 ]]; then
        report_csv "$result_dir" hotspots "$collection_dir/reports/tasks.csv" task || \
            printf 'tasks\n' >> "$collection_dir/reports/unsupported-reports.txt"
        report_csv "$result_dir" hotspots "$collection_dir/reports/task-functions.csv" task,function || \
            printf 'task-functions\n' >> "$collection_dir/reports/unsupported-reports.txt"
    else
        printf 'tasks\ntask-functions\n' >> "$collection_dir/reports/unsupported-reports.txt"
    fi
    if [[ "$hw_task_supported" -eq 1 ]]; then
        report_csv "$result_dir" hw-events "$collection_dir/reports/task-hw-events.csv" task,function || \
            printf 'task-hw-events\n' >> "$collection_dir/reports/unsupported-reports.txt"
    else
        printf 'task-hw-events\n' >> "$collection_dir/reports/unsupported-reports.txt"
    fi

    touch "$collection_dir/.complete"
    return 0
}

mkdir -p "$run_dir/collections"
printf 'Resultados desta campanha: %s\n' "$run_dir"
printf 'VTune: %s\n' "$vtune_version"
printf 'Knobs: %s\n' "$vtune_knobs"

for transformation_index in "${!transformations[@]}"; do
    transformation="${transformations[$transformation_index]}"
    workload_iterations="${iterations[$transformation_index]}"
    for threads in "${threads_values[@]}"; do
        for schedule_index in "${!schedules_raw[@]}"; do
            schedule_raw="${schedules_raw[$schedule_index]}"
            schedule_normalized="${schedules_normalized[$schedule_index]}"
            printf -v collection_id 'threads_%03d__%s__%s' \
                "$threads" "$schedule_normalized" "$transformation"
            if collection_complete "$run_dir/collections/$collection_id"; then
                printf 'Ja concluida: %s\n' "$collection_id"
                ensure_preflight
                if [[ ! -f "$run_dir/storage_estimate.txt" ]]; then
                    check_storage_after_first_collection "$run_dir/collections/$collection_id"
                fi
                continue
            fi
            if ! run_collection "$collection_id" "$threads" "$schedule_raw" \
                "$schedule_normalized" "$transformation" "$workload_iterations"; then
                exit 1
            fi
            if [[ ! -f "$run_dir/storage_estimate.txt" ]]; then
                check_storage_after_first_collection "$run_dir/collections/$collection_id"
            fi
            ensure_preflight
        done
    done
done

python3 "$script_dir/aggregate.py" "$run_dir" \
    --require-complete --expected-collections 432
finalized=1
printf 'Campanha concluida: %s\n' "$run_dir/benchmark_transformacoes_vtune.csv"
