#!/usr/bin/env bash
# Valida e mede a generalização da convolução gaussiana separável para 3, 5,
# 7, 9 e 11 taps. Não usa VTune: este job mede medianas reprodutíveis.
#SBATCH --job-name=openmp-gaussian-sizes
#SBATCH --partition=hype
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=20
#SBATCH --exclusive
#SBATCH --time=02:00:00
#SBATCH --output=slurm-gaussian-sizes-%j.out
#SBATCH --error=slurm-gaussian-sizes-%j.err

set -euo pipefail
SUBMIT_DIR="${SLURM_SUBMIT_DIR:?Execute sbatch a partir da raiz do projeto.}"
IMAGE="${GAUSSIAN_SIZES_IMAGE:-images/6000x6000.png}"
RESULT_DIR="$SUBMIT_DIR/resultados_pcad_hype_gaussian_separavel_tamanhos_${SLURM_JOB_ID}"
mkdir -p "$RESULT_DIR"
cd "$SUBMIT_DIR"
[[ -f "$IMAGE" ]] || { echo "Imagem ausente: $IMAGE" >&2; exit 2; }
export OMP_DYNAMIC=FALSE OMP_PLACES=cores OMP_PROC_BIND=close
hostname > "$RESULT_DIR/hostname.txt"; lscpu > "$RESULT_DIR/lscpu.txt"
env | grep '^OMP_' | sort > "$RESULT_DIR/openmp_environment.txt" || true
g++ --version > "$RESULT_DIR/compiler.txt" 2>&1 || true
make -B SIMD=off-avx2 gaussian-sizes
make -B SIMD=omp-avx2 gaussian-sizes

RAW="$RESULT_DIR/gaussian_sizes_raw.csv"
for build in off-avx2 omp-avx2; do
    binary="build/$build/gaussian_sizes_benchmark"
    for threads in 1 20; do
        for taps in 3 5 7 9 11; do
            OMP_NUM_THREADS="$threads" OMP_SCHEDULE=static "$binary" --image "$IMAGE" "$RAW" --taps "$taps" --warmup
            for repeat in 1 2 3 4 5; do
                OMP_NUM_THREADS="$threads" OMP_SCHEDULE=static "$binary" --image "$IMAGE" "$RAW" --taps "$taps"
            done
        done
    done
done
python3 summarize_gaussian_sizes.py --raw "$RAW" --out "$RESULT_DIR/gaussian_sizes_summary.csv"
echo "Generalização separável concluída: $RESULT_DIR"
