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

hostname
lscpu
echo "VTune no PATH:"
command -v vtune || true
vtune --version || true
echo "Permissão de contadores:"
cat /proc/sys/kernel/perf_event_paranoid 2>/dev/null || true
echo "Eventos de CPU disponíveis:"
perf list --no-desc 2>/dev/null | head -n 80 || true
