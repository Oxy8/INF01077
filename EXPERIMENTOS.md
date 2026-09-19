# Experimentos OpenMP

## Execução local

Compile uma variante isolada:

```bash
make SIMD=off all
make SIMD=omp all
```

`SIMD=off` usa `-fno-tree-vectorize`. `SIMD=omp` ativa os pragmas
`omp simd` e grava o relatório do compilador em
`build/omp/vectorization-core.log`.

Gere os controles determinísticos de 6000×6000 quando necessário:

```bash
make SIMD=off generate-controls
```

Faça uma validação curta da infraestrutura:

```bash
bash run_tests.sh --smoke --output resultados_smoke
```

A campanha completa usa cinco repetições cronometradas, uma execução de
aquecimento e threads `1,2,4,8,12,16,20`. A afinidade e a política NUMA ficam
nos padrões do ambiente OpenMP/Slurm:

```bash
bash run_tests.sh --output resultados_experimentos
```

O arquivo `benchmark_raw.csv` mantém cada medição individual e
`benchmark_summary.csv` contém mediana, mínimo, máximo, média, desvio-padrão
e speedup relativo ao `static` da mesma configuração.

## Experimento complementar: layout de pixels

`run_layout_tests.sh` testa a hipótese de que o layout intercalado usado pela
biblioteca (`RGBRGB...`, também chamado AoS) reduz a oportunidade de
vetorização. Ele usa `Grayscale` e `Gaussian_11x11`, `schedule(static)`, as
duas imagens regulares e os mesmos sete níveis de threads da campanha
principal. Para cada variante `SIMD=off` e `SIMD=omp`, há aquecimento e cinco
amostras medidas:

```bash
bash run_layout_tests.sh --output resultados_layout
```

O benchmark aloca `R[]`, `G[]` e `B[]` uma vez e registra as fases separadas:
`AoS_to_SoA`, `Kernel`, `SoA_to_AoS` e `End_to_End`. A cópia usada
para restaurar a entrada e as alocações não entram no tempo. Cada amostra
reconstrói a imagem RGB e compara seu hash ao resultado AoS; uma divergência
interrompe o resumo. Para Gaussian_11x11, ambos também são comparados à função
de produção, fora da janela cronometrada. Assim, a comparação central é entre
as duas linhas `Kernel`; o total mostra se uma eventual vantagem do kernel
compensa as conversões em uma aplicação que ainda recebe/devolve RGB.

## PCAD

No nó de login, submeta primeiro a verificação de VTune:

```bash
sbatch scripts/pcad_vtune_preflight.sbatch
```

Depois execute a bateria formal em nó hype exclusivo:

```bash
sbatch scripts/pcad_hype_benchmark.sbatch
```

Para executar apenas o teste de layout no mesmo tipo de nó:

```bash
sbatch scripts/pcad_hype_layout.sbatch
```

O job coleta a topologia de CPU e usa os padrões de afinidade, NUMA e
compilação do ambiente. As coletas VTune devem ser feitas em uma alocação
exclusiva separada, por exemplo:

```bash
salloc -p hype -N 1 -c 20 --exclusive -t 02:00:00
bash scripts/collect_vtune.sh
```

É possível selecionar a coleta e o caso por variáveis de ambiente, por
exemplo `VTUNE_ANALYSIS=threading VTUNE_SCHEDULE=static`.
