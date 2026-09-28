#!/usr/bin/env bash
# Memory Bound das 17 operações originais, na mesma imagem/build/schedule do
# gráfico de eficiência. Coletas VTune NÃO são usadas como amostras de tempo.
# As cópias de entrada são preparadas com a coleta pausada. A região VTune
# contém somente chamadas da operação; o limite de memória abaixo restringe
# quantas cópias coexistem. Bottom-up permite separar as fases da operação.
#SBATCH --job-name=openmp-hpc-regular
#SBATCH --partition=hype
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=20
#SBATCH --exclusive
#SBATCH --time=04:00:00
#SBATCH --output=slurm-hpc-regular-%j.out
#SBATCH --error=slurm-hpc-regular-%j.err

set -euo pipefail
export LC_ALL=C

SUBMIT_DIR="${SLURM_SUBMIT_DIR:?Execute sbatch a partir da raiz do projeto.}"
IMAGE="${REGULAR_HPC_IMAGE:-images/6000x6000.png}"
RESULT_DIR="$SUBMIT_DIR/resultados_pcad_hype_hpc_regular_memory_${SLURM_JOB_ID}"
VTUNE_ROOT=/home/intel/oneapi/vtune/2021.1.1
VTUNE_SDK="$VTUNE_ROOT/sdk"
TARGET_PROFILE_MS="${REGULAR_HPC_PROFILE_MS:-3000}"
CONTROL_REPEATS="${REGULAR_HPC_CONTROL_REPEATS:-5}"
MAX_PROFILE_GIB="${REGULAR_HPC_MAX_GIB:-24}"

cd "$SUBMIT_DIR"
[[ -f "$IMAGE" ]] || { printf 'Imagem ausente: %s\n' "$IMAGE" >&2; exit 2; }
[[ "$TARGET_PROFILE_MS" =~ ^[0-9]+$ && "$TARGET_PROFILE_MS" -gt 0 ]] || { echo 'REGULAR_HPC_PROFILE_MS deve ser inteiro positivo.' >&2; exit 2; }
[[ "$CONTROL_REPEATS" =~ ^[1-9][0-9]*$ ]] || { echo 'REGULAR_HPC_CONTROL_REPEATS deve ser inteiro positivo.' >&2; exit 2; }
[[ "$MAX_PROFILE_GIB" =~ ^[1-9][0-9]*$ ]] || { echo 'REGULAR_HPC_MAX_GIB deve ser inteiro positivo.' >&2; exit 2; }
[[ -r "$VTUNE_SDK/include/ittnotify.h" && -r "$VTUNE_SDK/lib64/libittnotify.a" ]] || {
    printf 'SDK ITT ausente em %s (include/ittnotify.h ou lib64/libittnotify.a).\n' "$VTUNE_SDK" >&2
    exit 2
}

source scripts/vtune_env.sh
command -v vtune >/dev/null 2>&1 || { echo 'VTune não encontrado no nó.' >&2; exit 127; }
if [[ -r "$VTUNE_ROOT/lib64/runtime/libittnotify_collector.so" ]]; then
    export INTEL_LIBITTNOTIFY64="$VTUNE_ROOT/lib64/runtime/libittnotify_collector.so"
fi
mkdir -p "$RESULT_DIR"

# Reproduz a campanha principal: nenhuma política explícita de afinidade/NUMA.
unset OMP_PLACES OMP_PROC_BIND OMP_DISPLAY_AFFINITY
export OMP_DYNAMIC=FALSE OMP_SCHEDULE=static
hostname > "$RESULT_DIR/hostname.txt"
lscpu > "$RESULT_DIR/lscpu.txt"
g++ --version > "$RESULT_DIR/compiler.txt" 2>&1
vtune -version > "$RESULT_DIR/vtune_version.txt" 2>&1
env | grep '^OMP_' | sort > "$RESULT_DIR/openmp_environment.txt" || true
git rev-parse HEAD > "$RESULT_DIR/git_commit.txt" 2>/dev/null || true
available_kib="$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)"
[[ "$available_kib" =~ ^[0-9]+$ ]] || { echo 'MemAvailable não disponível.' >&2; exit 2; }
memory_budget_bytes="$(awk -v avail="$available_kib" -v cap="$MAX_PROFILE_GIB" 'BEGIN {
    a=avail*1024/4; b=cap*1024*1024*1024; printf "%.0f", (a<b?a:b)
}')"
printf 'image=%s\nbuild=off\nschedule=static\nthreads=1,20\ncontrol_repeats=%s\nprofile_target_ms=%s\nmemory_budget_bytes=%s\n' \
    "$IMAGE" "$CONTROL_REPEATS" "$TARGET_PROFILE_MS" "$memory_budget_bytes" > "$RESULT_DIR/protocol.txt"

# O perfil usa exatamente o código das operações originais com símbolos -g.
# Só o runner recebe chamadas ITT para iniciar/parar a coleta; -O3 e o build
# off (-fno-tree-vectorize) continuam os mesmos da campanha principal.
make -B DEBUG=1 SIMD=off VTUNE_ITT=1 VTUNE_SDK="$VTUNE_SDK" all
BINARY=build/off-itt/image_benchmark
REFERENCE_HASHES="$RESULT_DIR/reference_hashes.csv"
OMP_NUM_THREADS=1 "$BINARY" --image "$IMAGE" /dev/null --operations regular \
    --hash-only --write-hashes "$REFERENCE_HASHES"
PRIOR_HASHES=resultados_pcad_hype_final_regular_avx2_5reps_822851/reference_hashes.csv
image_name="$(basename "$IMAGE")"
if [[ -f "$PRIOR_HASHES" ]] && grep -q "^${image_name}," "$PRIOR_HASHES"; then
    grep "^${image_name}," "$PRIOR_HASHES" | LC_ALL=C sort > "$RESULT_DIR/prior_image_hashes.csv"
    grep "^${image_name}," "$REFERENCE_HASHES" | LC_ALL=C sort > "$RESULT_DIR/current_image_hashes.csv"
    diff -u "$RESULT_DIR/prior_image_hashes.csv" "$RESULT_DIR/current_image_hashes.csv" > "$RESULT_DIR/hash_comparison.diff" || {
        echo 'As saídas divergem da campanha principal; não são diretamente comparáveis.' >&2
        exit 2
    }
    printf 'hashes=match_with_%s\n' "$PRIOR_HASHES" >> "$RESULT_DIR/protocol.txt"
else
    printf 'hashes=internal_reference_only\n' >> "$RESULT_DIR/protocol.txt"
fi

OPERATIONS=(
    Adjust_Brightness Adjust_Contrast Equalize_Histogram Flip_Horizontal
    Flip_Vertical Gaussian_3x3 Gaussian_5x5 Gaussian_7x7 Gaussian_9x9
    Gaussian_11x11 Grayscale Negative Quantize Rotate_CCW Rotate_CW
    Zoom_In Zoom_Out
)

printf 'Operation,Threads,Control_median_ms,Profile_iterations,Input_preparation_ms,Sampled_kernel_ms,Input_bytes,State,Case_dir\n' > "$RESULT_DIR/manifest.csv"
printf 'Operation,Threads,Memory_Bound_pct,Control_median_ms,Profile_iterations,Sampled_kernel_ms,State\n' > "$RESULT_DIR/memory_bound_17.csv"
failed=0
for operation in "${OPERATIONS[@]}"; do
    for threads in 1 20; do
        case_name="${operation}_t${threads}"
        case_dir="$RESULT_DIR/$case_name"
        mkdir -p "$case_dir"
        export OMP_NUM_THREADS="$threads"
        printf 'operation=%s\nthreads=%s\nbuild=off\nschedule=static\nimage=%s\n' \
            "$operation" "$threads" "$IMAGE" > "$case_dir/configuration.txt"

        "$BINARY" --image "$IMAGE" /dev/null --operations "$operation" \
            --warmup --reference-hashes "$REFERENCE_HASHES" > "$case_dir/warmup.log" 2>&1
        for ((repeat=1; repeat<=CONTROL_REPEATS; repeat++)); do
            "$BINARY" --image "$IMAGE" "$case_dir/control_raw.csv" --operations "$operation" \
                --run-id "${case_name}-control" --repeat "$repeat" \
                --reference-hashes "$REFERENCE_HASHES" >> "$case_dir/control.log" 2>&1
        done

        # Mediana do tempo do KERNEL (coluna 18), não do processo inteiro.
        control_median="$(awk -F, 'NR>1 { v[++n]=$18+0 } END {
            if (n<1) exit 2;
            for (i=1;i<=n;i++) for (j=i+1;j<=n;j++) if (v[i]>v[j]) { t=v[i];v[i]=v[j];v[j]=t }
            if (n%2) printf "%.6f",v[(n+1)/2]; else printf "%.6f",(v[n/2]+v[n/2+1])/2
        }' "$case_dir/control_raw.csv")"
        requested_iterations="$(awk -v target="$TARGET_PROFILE_MS" -v ms="$control_median" 'BEGIN {
            if (ms<=0) exit 2;
            n=int(target/ms+0.999999); if (n<2) n=2; if (n>400) n=400; print n
        }')"
        input_bytes="$(awk -F, 'NR==2 {printf "%.0f", $4*$5*3; exit}' "$case_dir/control_raw.csv")"
        # Conservadoramente, cada iteração pode reter entrada e saída. Zoom_In
        # produz até ~4× os pixels, portanto reserva orçamento de 5×.
        factor=2
        if [[ "$operation" == Zoom_In ]]; then factor=5; fi
        budget_iterations="$(awk -v bytes="$memory_budget_bytes" -v input="$input_bytes" -v factor="$factor" 'BEGIN {
            if (input<=0) exit 2; print int(bytes/(input*factor))
        }')"
        (( budget_iterations >= 2 )) || { echo "Memória insuficiente para $case_name (mínimo: 2 entradas)." >&2; exit 2; }
        iterations="$requested_iterations"
        if (( iterations > budget_iterations )); then iterations="$budget_iterations"; fi
        printf 'control_median_ms=%s\nprofile_iterations=%s\ninput_bytes=%s\nreserved_factor=%s\n' \
            "$control_median" "$iterations" "$input_bytes" "$factor" >> "$case_dir/configuration.txt"
        printf '[%s] VTune HPC: %s repetições; controle mediano %s ms\n' "$case_name" "$iterations" "$control_median"

        state=ok
        if ! vtune -collect hpc-performance -start-paused \
            -result-dir "$case_dir/hpc_performance" -- \
            "$BINARY" --image "$IMAGE" /dev/null --operations "$operation" \
            --profile-all-regular --profile-iterations "$iterations" --warmup \
            --reference-hashes "$REFERENCE_HASHES" > "$case_dir/vtune.log" 2>&1; then
            state=collection_failed
            failed=1
        else
            if ! vtune -report summary -r "$case_dir/hpc_performance" \
                -report-output "$case_dir/summary.txt" > "$case_dir/report.log" 2>&1; then
                state=report_failed
                failed=1
            fi
            # O relatório por função ajuda a distinguir fases internas de
            # operações com mais de um kernel, como Zoom_In e Quantize.
            vtune -report hotspots -group-by function -format csv \
                -r "$case_dir/hpc_performance" \
                -report-output "$case_dir/hotspots_functions.csv" \
                >> "$case_dir/report.log" 2>&1 || true
        fi
        grep '^PROFILE_REGION,' "$case_dir/vtune.log" > "$case_dir/profile_region.csv" || true
        phase="$(awk -F, '/^PROFILE_REGION,/ {print $4 "," $5 "," $6; exit}' "$case_dir/profile_region.csv")"
        if [[ -z "$phase" ]]; then
            phase=',,'
            if [[ "$state" == ok ]]; then state=missing_region; failed=1; fi
        fi
        if [[ "$state" == ok ]] && ! grep -q 'Memory Bound' "$case_dir/summary.txt"; then
            state=missing_memory_bound
            failed=1
        fi
        memory_bound=''
        if [[ -f "$case_dir/summary.txt" ]]; then
            memory_bound="$(awk '$1=="Memory" && $2=="Bound:" {gsub(/%/,"",$3); print $3; exit}' "$case_dir/summary.txt")"
        fi
        if [[ "$state" == ok && ! "$memory_bound" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
            state=invalid_memory_bound
            failed=1
        fi
        printf '%s,%s,%s,%s,%s,%s,%s\n' "$operation" "$threads" "$control_median" "$iterations" "$phase" "$state" "$case_name" >> "$RESULT_DIR/manifest.csv"
        sampled_kernel_ms="$(awk -F, '/^PROFILE_REGION,/ {print $5; exit}' "$case_dir/profile_region.csv")"
        printf '%s,%s,%s,%s,%s,%s,%s\n' "$operation" "$threads" "$memory_bound" "$control_median" "$iterations" "$sampled_kernel_ms" "$state" >> "$RESULT_DIR/memory_bound_17.csv"
        # O primeiro caso funciona como sonda das APIs ITT/VTune. Se falhar,
        # não desperdiçamos a reserva repetindo 33 coletas que também falharão.
        if [[ "$case_name" == Adjust_Brightness_t1 && "$state" != ok ]]; then
            printf 'A sonda inicial falhou (%s); verifique %s.\n' "$state" "$case_dir/vtune.log" >&2
            exit 1
        fi
    done
done

printf 'Resultados: %s\n' "$RESULT_DIR"
printf 'As regiões amostradas excluem decodificação, cópias de entrada e hash.\n'
exit "$failed"
