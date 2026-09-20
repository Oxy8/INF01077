#!/bin/bash

#SBATCH --partition=hype
#SBATCH --time=24:00:00
#SBATCH --cpus-per-task=40
#SBATCH --exclusive
#SBATCH --job-name=scheduling_all_transformations

cd /home/ekuster/INF01077/benchmark_transformacoes

bash run.sh
