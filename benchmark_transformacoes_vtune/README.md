# Benchmark VTune por transformação e escalonamento

Esta campanha coleta uma análise `hpc-performance` separada para cada combinação de:

- 18 transformações;
- 20 e 40 threads;
- `static` e `dynamic` com chunks de 1 a 1024.

São 432 coletas. Cada coleta executa uma transformação sobre todas as imagens. As repetições internas de `repetitions.csv` mantêm aproximadamente 20 segundos de trabalho no caso de calibração `40 threads + static`. A quantidade é mantida igual nos demais escalonamentos para que eles executem o mesmo trabalho.

## Execução no Slurm

A partir da raiz do repositório ou desta pasta:

```sh
sbatch benchmark_transformacoes_vtune/job.sh
```

ou:

```sh
sbatch job.sh
```

O job solicita um nó Hype exclusivo com 40 CPUs por 24 horas, carrega o VTune 2021.1.1 e deixa as variáveis de afinidade OpenMP sem definição para reproduzir a política padrão usada no benchmark original.

Não execute a campanha no nó de login. A coleta `hpc-performance` precisa do acesso aos contadores de hardware disponível dentro do job Slurm.

## Resultados e retomada

Cada execução cria:

```text
benchmark_transformacoes_vtune/runs/<data>-<job-id>/
```

O arquivo consolidado é `benchmark_transformacoes_vtune.csv`. Os diretórios em `collections/` preservam o resultado bruto do VTune, os relatórios CSV, os tempos por imagem e os logs.

Para retomar uma campanha interrompida, informe o caminho absoluto existente:

```sh
sbatch --export=ALL,RUN_DIR=/home/users/USUARIO/INF01077/benchmark_transformacoes_vtune/runs/PASTA \
    benchmark_transformacoes_vtune/job.sh
```

Uma coleta só é ignorada quando o resultado bruto, os tempos, os relatórios obrigatórios e o marcador `.complete` existem. Coletas incompletas são refeitas.

## Estrutura da tabela

A coluna `Record_Type` distingue:

- `collection`: resumo geral da coleta, com `Image=ALL`;
- `frame`: métricas dos intervalos instrumentados ao redor das transformações;
- `function`: hotspots e eventos de hardware por função/módulo;
- `timing`: tempo de uma transformação para uma imagem e repetição interna.

Todos os registros têm `Collection_ID`, permitindo relacionar tempos, configuração, relatórios e o diretório bruto. Métricas não fornecidas pelo processador ou pela versão do VTune ficam vazias e são relacionadas em `Unsupported_Metrics` ou `Unsupported_Reports`.

Com as 13 imagens atuais, a validação final espera 432 coletas e 240.864 registros de tempo. O primeiro resultado é usado como preflight para verificar os relatórios e estimar o espaço necessário antes de continuar.

## Build manual

Depois de carregar o ambiente do VTune:

```sh
make vtune-schedule-benchmark VTUNE_DIR=/home/intel/oneapi/vtune/2021.1.1
```

Esse target usa objetos separados com `-O2 -g`, `schedule(runtime)` e ITT. Os targets existentes continuam usando seus próprios objetos.
