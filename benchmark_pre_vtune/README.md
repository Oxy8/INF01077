# Execução curta para testes com VTune

Esta pasta fornece uma execução simples do programa para experimentar o Intel VTune. O programa usa uma imagem, 40 threads, escalonamento `static` e aplica uma vez cada uma das 18 transformações. Cada transformação recebe novamente a imagem original.

Primeiro compile o executável existente:

```sh
./benchmark_pre_vtune/build.sh
```

Depois execute:

```sh
./benchmark_pre_vtune/run.sh
```

Por padrão, a execução usa `images/4000x3000.png` e grava os tempos em um novo CSV dentro de `benchmark_pre_vtune/results/`.

É possível escolher outra imagem como único argumento:

```sh
./benchmark_pre_vtune/run.sh images/8k.jpeg
```

`8k.jpeg` termina mais rapidamente; uma imagem maior mantém o processo ativo por mais tempo. A execução não define afinidade de CPU, portanto variáveis externas como `OMP_PLACES` e `OMP_PROC_BIND` permanecem sob controle do ambiente usado para iniciar o programa.

## VTune HPC Performance no Slurm

Na Hype, envie o job a partir da raiz do repositório:

```sh
sbatch benchmark_pre_vtune/job.sh
```

Ou, dentro desta pasta:

```sh
sbatch job.sh
```

O job solicita 40 CPUs em um nó exclusivo, carrega o VTune 2021.1.1 indicado no enunciado, recompila o benchmark com `-O2 -g` e executa a análise `hpc-performance`. Os dados do VTune e `summary.txt` são gravados em uma pasta única dentro de `benchmark_pre_vtune/vtune_results/`. A execução também produz seu CSV normal em `benchmark_pre_vtune/results/`.
