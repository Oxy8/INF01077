#!/usr/bin/env bash
# Hotspots por amostragem de hardware apenas para a decisão Zoom/static/dynamic.
# O coletor mínimo é a rota validada no VTune 2021.1.1 do Hype.
#SBATCH --job-name=openmp-vtune-zoom
#SBATCH --partition=hype
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=20
#SBATCH --exclusive
#SBATCH --time=01:00:00
#SBATCH --output=slurm-vtune-zoom-%j.out
#SBATCH --error=slurm-vtune-zoom-%j.err

set -euo pipefail

SUBMIT_DIR="${SLURM_SUBMIT_DIR:?Execute com sbatch a partir da raiz do projeto.}"
RESULT_DIR="$SUBMIT_DIR/resultados_pcad_hype_vtune_zoom_schedules_${SLURM_JOB_ID}"
IMAGE="images/6000x6000.png"
REFERENCE_HASHES="$RESULT_DIR/reference_hashes.csv"

mkdir -p "$RESULT_DIR"
cd "$SUBMIT_DIR"
source scripts/vtune_env.sh
command -v vtune >/dev/null 2>&1 || { echo "VTune não encontrado no nó $(hostname)." >&2; exit 127; }
[[ -f "$IMAGE" ]] || { echo "Imagem ausente: $IMAGE" >&2; exit 2; }

hostname > "$RESULT_DIR/hostname.txt"
lscpu > "$RESULT_DIR/lscpu.txt"
g++ --version > "$RESULT_DIR/compiler.txt" 2>&1 || true
vtune -version > "$RESULT_DIR/vtune_version.txt" 2>&1 || true
export OMP_DYNAMIC=FALSE
export OMP_PLACES=cores
export OMP_PROC_BIND=close
env | grep '^OMP_' | sort > "$RESULT_DIR/openmp_environment.txt" || true

make -B DEBUG=1 SIMD=off-avx2 all
make -B DEBUG=1 SIMD=omp-avx2 all
OMP_NUM_THREADS=1 OMP_SCHEDULE=static build/off-avx2/image_benchmark \
    --image "$IMAGE" /dev/null --operations Zoom_In --hash-only --write-hashes "$REFERENCE_HASHES"

collect_zoom() {
    local label="$1" schedule="$2"
    OMP_NUM_THREADS=20 OMP_SCHEDULE="$schedule" build/omp-avx2/image_benchmark \
        --image "$IMAGE" /dev/null --operations Zoom_In --warmup \
        --reference-hashes "$REFERENCE_HASHES" > "$RESULT_DIR/${label}_control.log" 2>&1
    VTUNE_ANALYSIS=hotspots VTUNE_SIMD=omp-avx2 VTUNE_IMAGE="$IMAGE" VTUNE_OPERATIONS=Zoom_In \
        VTUNE_THREADS=20 VTUNE_SCHEDULE="$schedule" VTUNE_PROFILE_ITERATIONS=50 \
        VTUNE_REFERENCE_HASHES="$REFERENCE_HASHES" VTUNE_RESULT_DIR="$RESULT_DIR/$label" \
        bash scripts/collect_vtune.sh > "$RESULT_DIR/${label}_collect.log" 2>&1
    vtune -report summary -r "$RESULT_DIR/$label" > "$RESULT_DIR/${label}_summary.txt"
    vtune -report hotspots -r "$RESULT_DIR/$label" > "$RESULT_DIR/${label}_hotspots.txt"
}

collect_zoom 00_zoom_static static
collect_zoom 01_zoom_dynamic1 dynamic,1
collect_zoom 02_zoom_dynamic16 dynamic,16

printf 'Hotspots do Zoom concluído: %s\n' "$RESULT_DIR"
