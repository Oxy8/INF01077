#!/usr/bin/env bash
# Produz evidência do GCC por arquivo-fonte e por build. Esta coleta não usa
# VTune: -fopt-info e o dump da passagem vect registram o que o compilador
# aceitou ou recusou vetorizar, e o assembly permite confirmar AVX/AVX2.
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
RESULT_DIR="$SUBMIT_DIR/resultados_pcad_hype_compiler_evidence_${SLURM_JOB_ID}"
PROJECT_DIR="$SUBMIT_DIR/577262-FPI-Relatorio2"
mkdir -p "$RESULT_DIR"
cd "$SUBMIT_DIR"

command -v g++ >/dev/null
hostname > "$RESULT_DIR/hostname.txt"
g++ --version > "$RESULT_DIR/compiler.txt" 2>&1

COMMON_FLAGS=(
    "-I$PROJECT_DIR" -O3 -g -Wall -Wextra -std=c++17 -fopenmp
    -ffp-contract=off -fdiagnostics-color=never
)

compile_source() {
    local build="$1" source="$2" base out_dir
    base="$(basename "$source" .cpp)"
    out_dir="$RESULT_DIR/$build"
    mkdir -p "$out_dir"

    local simd_flags=()
    if [[ "$build" == "off-avx2" ]]; then
        simd_flags=(-DOMP_EXPLICIT_SIMD=0 -fno-tree-vectorize -march=haswell)
    else
        simd_flags=(-DOMP_EXPLICIT_SIMD=1 -march=haswell)
    fi

    # Os diagnósticos vão para stderr deliberadamente. Assim cada arquivo tem
    # seu próprio log e nenhum -fopt-info concorre pelo mesmo destino.
    g++ "${COMMON_FLAGS[@]}" "${simd_flags[@]}" \
        -fopt-info-vec-all \
        "-fdump-tree-vect-details=$out_dir/$base.vect.txt" \
        -c "$PROJECT_DIR/$source" -o "$out_dir/$base.o" \
        2> "$out_dir/$base.opt-info.txt"

    # Assembly Intel com informação de origem, para conferir instruções como
    # ymm/vadd/vmul e localizar os loops informados pelo relatório.
    g++ "${COMMON_FLAGS[@]}" "${simd_flags[@]}" \
        -S -fverbose-asm -masm=intel "$PROJECT_DIR/$source" \
        -o "$out_dir/$base.s"
    objdump -d -C -Mintel "$out_dir/$base.o" > "$out_dir/$base.objdump.txt"

    {
        printf 'Arquivo: %s\n' "$source"
        printf '\nLaços aceitos/recusados pelo vetorizador:\n'
        grep -E 'vectorized|not vectorized|missed:' "$out_dir/$base.opt-info.txt" || true
        printf '\nInstruções AVX/AVX2 no assembly:\n'
        grep -E '\<v[a-z0-9]+' "$out_dir/$base.objdump.txt" | head -n 160 || true
    } > "$out_dir/$base.resumo.txt"
}

for build in off-avx2 omp-avx2; do
    compile_source "$build" image_manipulation.cpp
    compile_source "$build" layout_benchmark.cpp
    compile_source "$build" gaussian_sizes_benchmark.cpp
done

cat > "$RESULT_DIR/LEIA_PRIMEIRO.txt" <<'EOF'
Como interpretar:
1. *.opt-info.txt: cada mensagem possui arquivo:linha e diz se o GCC
   vectorized ou missed/not vectorized, em geral com a razão.
2. *.vect.txt: detalhe da passagem interna vect do GCC; é mais verboso.
3. *.s e *.objdump.txt: confirmação da instrução emitida. Procure registradores
   ymm e instruções v* no build omp-avx2; o build off-avx2 não deve conter
   vetorização automática.

Loops de interesse:
- image_manipulation.cpp: Zoom horizontal e vertical;
- layout_benchmark.cpp: gaussian_11_aos, gaussian_11_planar e as passadas
  horizontal/vertical separáveis.
- gaussian_sizes_benchmark.cpp: versões generalizadas de 3, 5, 7, 9 e 11
  taps. Este arquivo distingue a evidência do kernel especializado daquela
  produzida pelos tamanhos generalizados.
EOF

echo "Evidência do compilador salva em $RESULT_DIR"
