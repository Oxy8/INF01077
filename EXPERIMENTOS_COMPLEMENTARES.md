# Experimentos complementares mínimos

Os resultados atuais já sustentam a vantagem do algoritmo separável para o
Gaussian 11x11 e o efeito de `dynamic` no filtro adaptativo. As coletas abaixo
só são necessárias para transformar hipóteses restantes em conclusões causais.

## 1. Zoom In e Grayscale: SIMD versus memória

Objetivo: separar o ganho de SIMD de limitação por memória e do overhead de
paralelismo. Executar a coleta HPC Performance mínima já validada, sempre com
`static`, imagem 6000x6000 e uma única operação.

| Operação | Builds | Threads | Coletas |
| --- | --- | --- | --- |
| `Zoom_In` | `off-avx2`, `omp-avx2` | 1, 20 | 4 |
| `Grayscale` | `off-avx2`, `omp-avx2` | 1, 20 | 4 |

Para cada resultado, comparar CPI, `Memory Bound`, `Cache Bound`, banda DRAM
observada e utilização efetiva. Com hyperthreading ligado, `DRAM Bound` pode
continuar indisponível; isso deve ser registrado, não estimado.

O script abaixo executa as oito coletas sequencialmente em uma única alocação.
Ele repete apenas o kernel sob o profiler para produzir uma amostra de cerca de
três segundos, mas ainda faz uma execução normal validada por hash em cada caso.
Isso evita que a inicialização, o carregamento da imagem e a escrita do CSV
dominem o perfil.

```bash
sbatch scripts/pcad_hype_hpc_simd_complementary.sbatch
```

Essas coletas permitem afirmar se a queda do ganho do Zoom vem de
banda/cache/uso dos núcleos; sem elas, a explicação permanece uma inferência
plausível baseada nos tempos e em Hotspots.

## 2. Ganhos inesperados de dynamic em operações regulares

Objetivo: verificar se um ganho restante após o reprocessamento por mediana é
um efeito reproduzível, e não dispersão de execução.

Executar somente as seis operações representativas abaixo, na imagem
6000x6000, build `omp-avx2`, 20 threads e dez repetições intercaladas por
configuração:

| Função | Razão da escolha |
| --- | --- |
| `Adjust_Brightness` | apresentou grande dispersão em `static` |
| `Flip_Horizontal` | mostrou vantagem consistente de dynamic nos dados brutos |
| `Negative` | kernel simples de referência |
| `Equalize_Histogram` | inclui o histograma com `#pragma omp ... reduction(+:hist[:256])` |
| `Gaussian_11x11` | carga longa e uniforme |
| `Zoom_In` | caso no qual `dynamic,1` é claramente prejudicial |

Para cada operação, medir `static`, `dynamic,1` e `dynamic,16`. Usar a mesma
afinidade em todos os pares de uma rodada (`OMP_PLACES=cores` e
`OMP_PROC_BIND=close`) e salvar `OMP_DISPLAY_AFFINITY=true`. Essa configuração
é deliberadamente um experimento de confirmação, separado da campanha padrão:
ela impede que migração de threads ou ocupação de hyperthreads seja confundida
com o efeito do schedule.

Reportar mediana, mínimo--máximo e razão das medianas. Só declarar vantagem de
um schedule quando a direção se repetir nas dez amostras e não depender de uma
configuração com intervalo muito mais largo.

O comando é:

```bash
sbatch scripts/pcad_hype_schedules_confirmation.sbatch
```

O resultado é salvo em `resultados_pcad_hype_schedules_<jobid>/`, com as dez
amostras brutas, resumo por mediana/mínimo/máximo e o mapeamento OpenMP em
`openmp_affinity.log`.

## 3. Generalização do filtro separável

Não é necessária para responder à questão do Gaussian 11x11. Caso o relatório
afirme que a técnica vale para todos os tamanhos gaussianos, implementar e
medir também as versões separáveis 3x3, 5x5, 7x7 e 9x9, nos mesmos quatro
builds e em 1 e 20 threads. Sem essas medições, a conclusão deve permanecer:
“o algoritmo separável foi validado experimentalmente para o Gaussian 11x11”.
