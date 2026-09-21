#!/bin/bash
#SBATCH --job-name=hello_vtune
#SBATCH --nodes=1
#SBATCH --exclusive
#SBATCH --partition=hype
#SBATCH --time=00:20:00
#SBATCH --output=slurm-vtune-%j.out
#SBATCH --error=slurm-vtune-%j.err


# Carrega o VTune da mesma forma que o seu script original
source /home/intel/oneapi/vtune/2024.1.1/vtune-vars.sh || true

echo "Compilando o Hello World..."
g++ -O3 -march=native -fopenmp hello_hpc.cpp -o hello_hpc

echo "Rodando sem VTune para garantir que o binário funciona..."
OMP_NUM_THREADS=20 ./hello_hpc

echo "Rodando COM VTune HPC-Performance (SEM coleta de largura de banda)..."
# Desligamos o memory-bandwidth propositalmente como fizemos antes
vtune -collect hpc-performance \
      -knob collect-memory-bandwidth=false \
      -knob collect-affinity=true \
      -result-dir resultados_hello_hpc \
      -- env OMP_NUM_THREADS=20 ./hello_hpc

echo "Finalizado."
