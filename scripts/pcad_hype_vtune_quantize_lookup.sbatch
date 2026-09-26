#!/usr/bin/env bash
# Quantize: off-avx2 / auto-avx2 / omp-avx2, apenas o lookup repetido.
# Usa as duas análises VTune já validadas no hype, sem knobs de instrumentação.
#SBATCH --job-name=vtune-quantize-lookup
#SBATCH --partition=hype
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=20
#SBATCH --exclusive
#SBATCH --time=02:00:00
#SBATCH --output=slurm-vtune-quantize-%j.out
#SBATCH --error=slurm-vtune-quantize-%j.err

set -euo pipefail

SUBMIT_DIR="${SLURM_SUBMIT_DIR:?Submeta a partir da raiz do repositório.}"
[[ -f "$SUBMIT_DIR/Makefile" && -f "$SUBMIT_DIR/577262-FPI-Relatorio2/vectorization_benchmark.cpp" ]] || {
    echo 'Submeta a partir da raiz do repositório.' >&2; exit 2;
}
IMAGE="${QUANTIZE_VTUNE_IMAGE:-images/6000x6000.png}"
[[ "$IMAGE" == images/* && "$IMAGE" != *..* && -f "$SUBMIT_DIR/$IMAGE" ]] || {
    echo "Imagem relativa à raiz não encontrada: $IMAGE" >&2; exit 2;
}

SCRATCH_BASE="${SLURM_TMPDIR:-/tmp}"
SCRATCH_BASE="$(cd "$SCRATCH_BASE" && pwd -P)"
WORK_DIR="$SCRATCH_BASE/${USER}_quantize_vtune_${SLURM_JOB_ID}"
RESULT_DIR="$SUBMIT_DIR/resultados_pcad_hype_vtune_quantize_${SLURM_JOB_ID}"
[[ ! -e "$WORK_DIR" && ! -e "$RESULT_DIR" ]] || {
    echo 'Diretório temporário ou de resultados já existe.' >&2; exit 2;
}
mkdir -p "$WORK_DIR/$(dirname "$IMAGE")" "$RESULT_DIR"
cleanup() {
    if [[ -d "$WORK_DIR" ]]; then
        local resolved
        resolved="$(cd "$WORK_DIR" && pwd -P)"
        if [[ "$resolved" == "$SCRATCH_BASE/${USER}_quantize_vtune_${SLURM_JOB_ID}" ]]; then
            rm -rf -- "$resolved"
        fi
    fi
}
trap cleanup EXIT

cp -a "$SUBMIT_DIR/Makefile" "$WORK_DIR/"
cp -a "$SUBMIT_DIR/577262-FPI-Relatorio2" "$WORK_DIR/"
cp -a "$SUBMIT_DIR/$IMAGE" "$WORK_DIR/$IMAGE"
mkdir -p "$RESULT_DIR/source"
cp "$WORK_DIR/577262-FPI-Relatorio2/vectorization_benchmark.cpp" \
   "$WORK_DIR/577262-FPI-Relatorio2/image_manipulation.cpp" \
   "$WORK_DIR/577262-FPI-Relatorio2/image_manipulation.h" "$RESULT_DIR/source/"
cp "$WORK_DIR/Makefile" "$RESULT_DIR/source/"
cd "$WORK_DIR"
source "$SUBMIT_DIR/scripts/vtune_env.sh"
command -v vtune >/dev/null 2>&1 || { echo "VTune não encontrado em $(hostname)." >&2; exit 127; }

hostname > "$RESULT_DIR/hostname.txt"
lscpu > "$RESULT_DIR/lscpu.txt"
g++ --version > "$RESULT_DIR/compiler.txt" 2>&1
vtune -version > "$RESULT_DIR/vtune_version.txt" 2>&1
git -C "$SUBMIT_DIR" rev-parse HEAD > "$RESULT_DIR/git_commit.txt" 2>/dev/null || true
if command -v sha256sum >/dev/null 2>&1; then
    sha256sum Makefile 577262-FPI-Relatorio2/vectorization_benchmark.cpp \
        577262-FPI-Relatorio2/image_manipulation.cpp "$IMAGE" > "$RESULT_DIR/source_and_image_sha256.txt"
fi

export OMP_DYNAMIC=FALSE OMP_SCHEDULE=static
env | grep '^OMP_' | sort > "$RESULT_DIR/openmp_environment.txt" || true

BUILDS=(off-avx2 auto-avx2 omp-avx2)
THREADS=(1 20)
for build in "${BUILDS[@]}"; do
    make -B DEBUG=1 SIMD="$build" COMPILER_DIAGNOSTICS=1 vectorization \
        > "$RESULT_DIR/${build}_build.log" 2>&1
    cp "build/$build/vectorization-experiment-all.log" "$RESULT_DIR/${build}_compiler.txt"
    if command -v objdump >/dev/null 2>&1; then
        objdump -d -C --no-show-raw-insn "build/$build/vectorization_benchmark" \
            > "$RESULT_DIR/${build}_assembly.txt"
    fi
done

# Controles sem VTune: dez amostras por build/thread, alternando a ordem dos
# builds. O modo com N=1 mede a mesma entrada e o mesmo lookup dos perfis.
CONTROL_CSV="$RESULT_DIR/control_raw.csv"
for threads in "${THREADS[@]}"; do
    for build in "${BUILDS[@]}"; do
        OMP_NUM_THREADS="$threads" "build/$build/vectorization_benchmark" \
            --image "$IMAGE" --operation Quantize "$CONTROL_CSV" \
            --profile-quantize-lookup 1 --warmup > /dev/null
    done
    for ((repeat=1; repeat<=10; ++repeat)); do
        offset=$(((repeat - 1) % ${#BUILDS[@]}))
        for ((index=0; index<${#BUILDS[@]}; ++index)); do
            build="${BUILDS[$(((index + offset) % ${#BUILDS[@]}))]}"
            OMP_NUM_THREADS="$threads" "build/$build/vectorization_benchmark" \
                --image "$IMAGE" --operation Quantize "$CONTROL_CSV" \
                --profile-quantize-lookup 1 --repeat "$repeat" \
                >> "$RESULT_DIR/control.log"
        done
    done
done

# CSV pequeno, com schedule=static e campos anteriores às flags sem vírgulas.
# Resume apenas as dez medidas não perfiladas da fase lookup.
awk -F, 'NR > 1 && $4 == "lookup_average" { print $7 "," $9 "," $11 }' "$CONTROL_CSV" |
    LC_ALL=C sort -t, -k1,1n -k2,2 -k3,3n |
    awk -F, '
        function emit() {
            if (n == 0) return
            median = (n % 2) ? values[(n + 1) / 2] : (values[n / 2] + values[n / 2 + 1]) / 2
            printf "%s,%s,%d,%.6f\n", previous_threads, previous_build, n, median
        }
        BEGIN { print "Threads,Build,Samples,Median_lookup_ms" }
        {
            if (n > 0 && ($1 != previous_threads || $2 != previous_build)) { emit(); n = 0 }
            previous_threads = $1; previous_build = $2; values[++n] = $3 + 0
        }
        END { emit() }
    ' > "$RESULT_DIR/control_medians.csv"
cat "$RESULT_DIR/control_medians.csv"

failures=0
for threads in "${THREADS[@]}"; do
    if [[ "$threads" -eq 1 ]]; then iterations=100; else iterations=500; fi
    for build in "${BUILDS[@]}"; do
        case_dir="$RESULT_DIR/${build}_t${threads}"
        mkdir -p "$case_dir"
        printf 'build=%s\nthreads=%s\nschedule=static\niterations=%s\nimage=%s\n' \
            "$build" "$threads" "$iterations" "$IMAGE" > "$case_dir/configuration.txt"
        for analysis in hotspots hpc-performance; do
            result="$case_dir/$analysis"
            echo "VTune: $build, $threads thread(s), $analysis"
            if OMP_NUM_THREADS="$threads" vtune -collect "$analysis" -result-dir "$result" -- \
                "build/$build/vectorization_benchmark" --image "$IMAGE" \
                --operation Quantize "$case_dir/profile.csv" \
                --profile-quantize-lookup "$iterations" --warmup \
                > "$case_dir/${analysis}.log" 2>&1; then
                vtune -report summary -r "$result" -report-output "$case_dir/${analysis}_summary.txt" \
                    > "$case_dir/${analysis}_report.log" 2>&1 || true
                if [[ "$analysis" == hotspots ]]; then
                    vtune -report hotspots -r "$result" \
                        -report-output "$case_dir/hotspots_functions.txt" \
                        >> "$case_dir/${analysis}_report.log" 2>&1 || true
                else
                    # Relatório opcional: nessa versão do VTune alguns campos
                    # HPC por função podem estar indisponíveis.
                    vtune -report bottom-up -r "$result" \
                        -report-output "$case_dir/hpc_bottom_up.txt" \
                        >> "$case_dir/${analysis}_report.log" 2>&1 || true
                fi
            else
                echo "Coleta falhou: $build, $threads thread(s), $analysis" >&2
                failures=$((failures + 1))
            fi
        done
    done
done

printf 'Resultados: %s\nColetas VTune com falha: %s\n' "$RESULT_DIR" "$failures"
((failures == 0))
