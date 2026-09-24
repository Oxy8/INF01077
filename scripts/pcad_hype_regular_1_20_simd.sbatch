#!/usr/bin/env bash
# Reexecuta a campanha regular mínima para separar efeito SIMD (AVX2) de
# escalabilidade: todas as 17 operações, static, 1 e 20 threads, 10 amostras.
# Também mede o kernel Gaussian 11x11 nos layouts AoS, SoA ingênuo e SoA
# separável. A conversão AoS<->SoA é registrada em fases próprias e não é
# somada ao tempo do kernel planar.
#SBATCH --job-name=openmp-regular-1-20
#SBATCH --partition=hype
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=20
#SBATCH --exclusive
#SBATCH --time=03:00:00
#SBATCH --output=slurm-regular-1-20-%j.out
#SBATCH --error=slurm-regular-1-20-%j.err

set -euo pipefail

SUBMIT_DIR="${SLURM_SUBMIT_DIR:?Execute sbatch a partir da raiz do projeto.}"
IMAGE="${REGULAR_1_20_IMAGE:-images/6000x6000.png}"
REPEATS="${REGULAR_1_20_REPEATS:-10}"
RESULT_DIR="$SUBMIT_DIR/resultados_pcad_hype_regular_1_20_${SLURM_JOB_ID}"
RAW="$RESULT_DIR/regular_raw.csv"
LAYOUT_RAW="$RESULT_DIR/layout_gaussian11_raw.csv"
HASHES="$RESULT_DIR/reference_hashes_off-avx2.txt"

[[ -f "$IMAGE" ]] || { echo "Imagem ausente: $IMAGE" >&2; exit 2; }
mkdir -p "$RESULT_DIR"
cd "$SUBMIT_DIR"

export OMP_DYNAMIC=FALSE
export OMP_SCHEDULE=static
# Não fixa places/bind: a campanha usa o mapeamento padrão do runtime, como
# solicitado. O ambiente efetivo é registrado para tornar isso auditável.
unset OMP_PLACES OMP_PROC_BIND

hostname > "$RESULT_DIR/hostname.txt"
lscpu > "$RESULT_DIR/lscpu.txt"
env | grep '^OMP_' | sort > "$RESULT_DIR/openmp_environment.txt" || true
g++ --version > "$RESULT_DIR/compiler.txt" 2>&1
printf 'Imagem=%s\nRepeticoes=%s\nSchedule=static\nThreads=1,20\nBuilds=off-avx2,omp-avx2\n' \
    "$IMAGE" "$REPEATS" > "$RESULT_DIR/configuration.txt"

make -B DEBUG=1 SIMD=off-avx2 all layout
make -B DEBUG=1 SIMD=omp-avx2 all layout

# Referência bit a bit produzida uma única vez pelo binário sem vetorização.
OMP_NUM_THREADS=1 build/off-avx2/image_benchmark --image "$IMAGE" "$RESULT_DIR/hashes_seed.csv" \
    --operations regular --run-id "reference" --repeat 0 --hash-only --write-hashes "$HASHES"

run_regular() {
    local build="$1" threads="$2" repeat="$3" warmup="$4"
    local warmup_flag=()
    [[ "$warmup" == 1 ]] && warmup_flag=(--warmup)
    OMP_NUM_THREADS="$threads" "build/$build/image_benchmark" --image "$IMAGE" "$RAW" \
        --operations regular --run-id "regular-1-20-$build-${threads}t" --repeat "$repeat" \
        --reference-hashes "$HASHES" "${warmup_flag[@]}"
}

run_layout() {
    local build="$1" threads="$2" repeat="$3" warmup="$4"
    local warmup_flag=()
    [[ "$warmup" == 1 ]] && warmup_flag=(--warmup)
    OMP_NUM_THREADS="$threads" "build/$build/layout_benchmark" --image "$IMAGE" "$LAYOUT_RAW" \
        --operation Gaussian_11x11 --profile-layout all --run-id "layout-1-20-$build-${threads}t" \
        --repeat "$repeat" "${warmup_flag[@]}"
}

for build in off-avx2 omp-avx2; do
    for threads in 1 20; do
        # Aquecimento não entra nos CSVs: evita a primeira criação de threads
        # nas dez amostras registradas e ainda preserva a validação por hash.
        run_regular "$build" "$threads" 0 1
        for repeat in $(seq 1 "$REPEATS"); do
            run_regular "$build" "$threads" "$repeat" 0
        done

        run_layout "$build" "$threads" 0 1
        for repeat in $(seq 1 "$REPEATS"); do
            run_layout "$build" "$threads" "$repeat" 0
        done
    done
done

cat > "$RESULT_DIR/LEIA_PRIMEIRO.txt" <<'EOF'
Escopo da campanha
==================
regular_raw.csv contém todas as 17 operações regulares, dez amostras por
build (off-avx2/omp-avx2) e por número de threads (1/20). É a fonte para
mediana, intervalo min--máx, speedup AVX2 e speedup/eficiência de threads.

layout_gaussian11_raw.csv contém fases separadas do Gaussian 11x11: AoS
direto, conversão AoS->SoA, SoA ingênuo, SoA separável (passadas horizontal e
vertical) e conversão de volta. Para comparar kernels, use somente as fases
do kernel; não some as conversões, que foram propositalmente medidas à parte.

Não use CPI para concluir sobre SIMD. A métrica principal é tempo por pixel
e a razão de medianas off-avx2 / omp-avx2. A compilação é independente do
número de threads; os relatórios detalhados do GCC vêm do job separado
pcad_hype_compiler_evidence.sbatch.
EOF

echo "Campanha de tempo salva em $RESULT_DIR"
