#!/usr/bin/env bash
#SBATCH --job-name=openmp-vtune
#SBATCH --partition=hype
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=20
#SBATCH --exclusive
#SBATCH --time=04:00:00
#SBATCH --output=slurm-vtune-%j.out
#SBATCH --error=slurm-vtune-%j.err

# Campanha de explicação; não produz amostras de benchmark comparáveis.
set -euo pipefail

SMOKE_ONLY=0
case "${1:-}" in
    "") ;;
    --smoke) SMOKE_ONLY=1 ;;
    *) echo "Uso: sbatch scripts/pcad_hype_vtune.sbatch [--smoke]" >&2; exit 2 ;;
esac

SUBMIT_DIR="${SLURM_SUBMIT_DIR:?Execute com sbatch a partir da raiz do projeto.}"
JOB_ROOT="${SLURM_TMPDIR:-/tmp}/${USER}_vtune_${SLURM_JOB_ID}"
WORK_DIR="$JOB_ROOT/project"
RESULT_DIR="$SUBMIT_DIR/resultados_pcad_hype_vtune_${SLURM_JOB_ID}"

cleanup() {
    # Preserva qualquer coleta já finalizada caso um perfil posterior do VTune
    # falhe; o diretório temporário será removido em seguida.
    if [[ -d "$WORK_DIR/resultados_vtune" ]]; then
        cp -a "$WORK_DIR/resultados_vtune/." "$RESULT_DIR/" 2>/dev/null || true
    fi
    rm -rf -- "$JOB_ROOT"
}
trap cleanup EXIT

mkdir -p "$WORK_DIR" "$RESULT_DIR"
# Não copiar builds e resultados antigos para o SSD temporário do nó.
cp -a "$SUBMIT_DIR/Makefile" "$SUBMIT_DIR/577262-FPI-Relatorio2" \
    "$SUBMIT_DIR/scripts" "$SUBMIT_DIR/images" "$WORK_DIR/"
cd "$WORK_DIR"
source scripts/vtune_env.sh

if ! command -v vtune >/dev/null 2>&1; then
    echo "VTune não foi encontrado no nó $(hostname)." >&2
    echo "Envie primeiro: sbatch scripts/pcad_vtune_preflight.sbatch" >&2
    echo "Se o preflight mostrar um módulo, reenvie este job com:" >&2
    echo "  sbatch --export=ALL,VTUNE_MODULE=NOME_DO_MODULO scripts/pcad_hype_vtune.sbatch" >&2
    exit 127
fi

hostname > "$RESULT_DIR/hostname.txt"
lscpu > "$RESULT_DIR/lscpu.txt"
vtune --version > "$RESULT_DIR/vtune_version.txt" 2>&1
g++ --version > "$RESULT_DIR/compiler.txt" 2>&1 || true
env | grep '^OMP_' | sort > "$RESULT_DIR/openmp_environment.txt" || true
printf '%s\n' "${VTUNE_MODULE_LOADED:-PATH}" > "$RESULT_DIR/vtune_module.txt"

make SIMD=off generate-controls

# Controle obrigatório no mesmo nó, sem VTune. Se isto falhar, há um problema
# no programa; se passar e o VTune abortar, a falha pertence ao coletor antigo.
echo "Executando controle sem VTune..." | tee "$RESULT_DIR/controle_sem_vtune.log"
make SIMD=omp-avx2 all >> "$RESULT_DIR/controle_sem_vtune.log" 2>&1
OMP_NUM_THREADS=20 OMP_SCHEDULE=dynamic,4 build/omp-avx2/image_benchmark \
    --image images/rain_paisage.jpg /tmp/controle_sem_vtune.csv \
    --operations adaptive --run-id controle-sem-vtune --repeat 0 --warmup \
    >> "$RESULT_DIR/controle_sem_vtune.log" 2>&1
echo "Controle sem VTune concluído." | tee -a "$RESULT_DIR/controle_sem_vtune.log"

# No VTune 2021.1.1, collect-memory-bandwidth também dispara a calibração de
# pico que aborta neste nó. O perfil HPC abaixo mantém a caracterização de
# CPU/FPU e escalabilidade, mas sem a medição de largura de banda. Hotspots em
# hardware é a coleta estável para atribuir tempo aos kernels.
HPC_SAFE_KNOBS='-knob collect-affinity=true'

run_image_profile() {
    local name="$1"
    local analysis="$2"
    local simd="$3"
    local operation="$4"
    local image="$5"
    local schedule="$6"
    local iterations="$7"
    local knobs="$8"
    VTUNE_ANALYSIS="$analysis" VTUNE_SIMD="$simd" VTUNE_IMAGE="$image" \
        VTUNE_OPERATIONS="$operation" VTUNE_THREADS=20 VTUNE_SCHEDULE="$schedule" \
        VTUNE_PROFILE_ITERATIONS="$iterations" VTUNE_KNOBS="$knobs" \
        VTUNE_RESULT_DIR="resultados_vtune/$name" bash scripts/collect_vtune.sh
}

run_layout_profile() {
    local name="$1"
    local analysis="$2"
    local simd="$3"
    local operation="$4"
    local iterations="$5"
    local knobs="$6"
    VTUNE_ANALYSIS="$analysis" VTUNE_SIMD="$simd" VTUNE_IMAGE="images/6000x6000.png" \
        VTUNE_LAYOUT_OPERATION="$operation" VTUNE_THREADS=20 VTUNE_SCHEDULE=static \
        VTUNE_PROFILE_ITERATIONS="$iterations" VTUNE_KNOBS="$knobs" \
        VTUNE_RESULT_DIR="resultados_vtune/$name" bash scripts/collect_vtune_layout.sh
}

# Primeiro confirma que o coletor funciona sem a calibração de pico.
run_image_profile 00_adaptive_dynamic4_hotspots hotspots omp-avx2 adaptive images/rain_paisage.jpg dynamic,4 1 ''
run_image_profile 01_adaptive_dynamic4_hpc_smoke hpc-performance omp-avx2 adaptive images/rain_paisage.jpg dynamic,4 1 "$HPC_SAFE_KNOBS"

if [[ "$SMOKE_ONLY" -eq 1 ]]; then
    cp -a resultados_vtune/. "$RESULT_DIR/"
    echo "Smoke VTune concluído. Resultados copiados para $RESULT_DIR"
    exit 0
fi

# 2--4: adaptativo real, comparando balanceamento de static/dynamic,4 e
# aprofundando o melhor caso na hierarquia de memória.
run_image_profile 02_adaptive_static_hpc hpc-performance omp-avx2 adaptive images/rain_paisage.jpg static 1 "$HPC_SAFE_KNOBS"

# 4--5: Grayscale AoS/SoA. Repetição só do kernel dá amostras suficientes;
# conversões permanecem fora dessa janela, como no experimento de layout.
run_layout_profile 03_grayscale_off_avx2_hpc hpc-performance off-avx2 Grayscale 100 "$HPC_SAFE_KNOBS"
run_layout_profile 04_grayscale_omp_avx2_hpc hpc-performance omp-avx2 Grayscale 100 "$HPC_SAFE_KNOBS"

# 6--7: Gaussian inclui AoS direto, SoA ingênuo e separável no mesmo processo.
run_layout_profile 05_gaussian_off_avx2_hotspots hotspots off-avx2 Gaussian_11x11 3 ''
run_layout_profile 06_gaussian_omp_avx2_hotspots hotspots omp-avx2 Gaussian_11x11 3 ''

# 8--9: Zoom_In é repetido em buffer de saída pré-alocado, sem medir alocação.
run_image_profile 07_zoom_off_avx2_hpc hpc-performance off-avx2 Zoom_In images/6000x6000.png static 50 "$HPC_SAFE_KNOBS"
run_image_profile 08_zoom_omp_avx2_hpc hpc-performance omp-avx2 Zoom_In images/6000x6000.png static 50 "$HPC_SAFE_KNOBS"

cp -a resultados_vtune/. "$RESULT_DIR/"
echo "Resultados VTune copiados para $RESULT_DIR"
