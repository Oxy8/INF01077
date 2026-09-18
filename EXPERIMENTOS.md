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

A campanha completa usa três repetições cronometradas, uma execução de
aquecimento, threads `1,2,4,8,12,16,20`, `OMP_PLACES=cores` e
`OMP_PROC_BIND=close`:

```bash
bash run_tests.sh --output resultados_experimentos
```

O arquivo `benchmark_raw.csv` mantém cada medição individual e
`benchmark_summary.csv` contém mediana, mínimo, máximo, média, desvio-padrão
e speedup relativo ao `static` da mesma configuração.

## PCAD

No nó de login, submeta primeiro a verificação de VTune:

```bash
sbatch scripts/pcad_vtune_preflight.sbatch
```

Depois execute a bateria formal em nó hype exclusivo:

```bash
sbatch scripts/pcad_hype_benchmark.sbatch
```

O job fixa `ARCH=haswell`, coleta a topologia de CPU/NUMA e executa com
memória intercalada entre sockets. As coletas VTune devem ser feitas em uma
alocação exclusiva separada, por exemplo:

```bash
salloc -p hype -N 1 -c 20 --exclusive -t 02:00:00
bash scripts/collect_vtune.sh
```

É possível selecionar a coleta e o caso por variáveis de ambiente, por
exemplo `VTUNE_ANALYSIS=threading VTUNE_SCHEDULE=static`.
