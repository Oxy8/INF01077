#!/usr/bin/env bash
#SBATCH --job-name=vtune-preflight
#SBATCH --partition=hype
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=20
#SBATCH --exclusive
#SBATCH --time=00:20:00
#SBATCH --output=slurm-vtune-preflight-%j.out
#SBATCH --error=slurm-vtune-preflight-%j.err

set -euo pipefail

ROOT_DIR="${SLURM_SUBMIT_DIR:?Execute com sbatch a partir da raiz do projeto.}"
source "$ROOT_DIR/scripts/vtune_env.sh"

hostname
lscpu
echo "VTune no PATH:"
command -v vtune || true
vtune --version || true
echo "Módulo VTune selecionado: ${VTUNE_MODULE_LOADED:-nenhum}"
echo "Análises HPC e Memory Access disponíveis:"
VTUNE_HELP_DIR="${SLURM_TMPDIR:-/tmp}/vtune-help-${SLURM_JOB_ID}"
mkdir -p "$VTUNE_HELP_DIR"
vtune -help collect hpc-performance > "$VTUNE_HELP_DIR/hpc-performance.txt" 2>&1 || true
vtune -help collect memory-access > "$VTUNE_HELP_DIR/memory-access.txt" 2>&1 || true
grep -E 'collect-memory-bandwidth|dram-bandwidth-limits|analyze-openmp|analyze-mem-objects' \
    "$VTUNE_HELP_DIR/hpc-performance.txt" "$VTUNE_HELP_DIR/memory-access.txt" 2>/dev/null || true
echo "Permissão de contadores:"
cat /proc/sys/kernel/perf_event_paranoid 2>/dev/null || true
echo "Eventos de CPU disponíveis:"
perf list --no-desc 2>/dev/null | head -n 80 || true
