#!/usr/bin/env bash
# Evidência de compilador para Zoom e os kernels AoS/SoA. Não mede tempo.
#SBATCH --job-name=openmp-compiler-evidence
#SBATCH --partition=hype
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --time=00:20:00
#SBATCH --output=slurm-compiler-evidence-%j.out
#SBATCH --error=slurm-compiler-evidence-%j.err

set -euo pipefail
SUBMIT_DIR="${SLURM_SUBMIT_DIR:?Execute sbatch a partir da raiz do projeto.}"
RESULT_DIR="$SUBMIT_DIR/resultados_pcad_hype_compilador_${SLURM_JOB_ID}"
mkdir -p "$RESULT_DIR"
cd "$SUBMIT_DIR"

hostname > "$RESULT_DIR/hostname.txt"
g++ --version > "$RESULT_DIR/compiler.txt" 2>&1 || true
make -B DEBUG=1 COMPILER_DIAGNOSTICS=1 SIMD=off-avx2 layout all
make -B DEBUG=1 COMPILER_DIAGNOSTICS=1 SIMD=omp-avx2 layout all

for build in off-avx2 omp-avx2; do
    mkdir -p "$RESULT_DIR/$build"
    cp -a "build/$build/vectorization-core-all.log" "$RESULT_DIR/$build/" 2>/dev/null || true
    cp -a "build/$build/vectorization-layout-all.log" "$RESULT_DIR/$build/" 2>/dev/null || true
    objdump -d -C --no-show-raw-insn "build/$build/image_benchmark" > "$RESULT_DIR/$build/image_benchmark.asm"
    objdump -d -C --no-show-raw-insn "build/$build/layout_benchmark" > "$RESULT_DIR/$build/layout_benchmark.asm"
done
echo "Evidência do compilador salva em $RESULT_DIR"
