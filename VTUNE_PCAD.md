# VTune no PCAD / hype

As coletas VTune explicam os benchmarks, mas não substituem as amostras de
tempo da campanha principal. No PCAD, a versão disponível é o VTune 2021.1.1
em nós `hype`, e há duas rotas que foram validadas separadamente.

## Coletas preservadas

| Resultado | Análise | Estado |
| --- | --- | --- |
| `resultados_pcad_hype_vtune_823234` | Hotspots, amostragem de hardware | 9 coletas concluídas |
| `resultados_pcad_hype_hpc_probe_823328` | HPC Performance, 4000x3000, todas as operações, 40 threads, `static` | concluída |
| `resultados_pcad_hype_hpc_probe_823332` | HPC Performance, adaptativo em `rain_paisage`, 20 threads, `static` | concluída |
| `resultados_pcad_hype_hpc_probe_823333` | HPC Performance, adaptativo em `rain_paisage`, 20 threads, `dynamic,4` | concluída |

Os diretórios acima e os respectivos `summary.txt` são os dados a utilizar.
Os logs e diretórios de tentativas abortadas foram removidos: o diagnóstico
relevante ficou documentado nesta página.

## Por que a configuração atual funciona

| Etapa | Tentativa anterior | Evidência | Configuração mantida |
| --- | --- | --- | --- |
| Ambiente | `source vtune-vars.sh` sob `set -u` | `ZSH_VERSION: unbound variable` no job 823137 | `vtune_env.sh` suspende `nounset` somente durante o `source` do caminho oficial do PCAD. |
| Hotspots | Modo padrão por instrumentação | O motor Pin do VTune 2021 abortou ao ler `.relr.dyn` (`unknown section type 0x13`) nos jobs 823145 e 823146. | `collect_vtune*.sh` força `sampling-mode=hw`; os 9 perfis do job 823234 encerraram normalmente. |
| HPC Performance | Campanha grande, copiada para `/tmp`, com aquecimento/repetições e knobs experimentais | Nos jobs 823139, 823160, 823161, 823210, 823225 e 823233 a coleta começou e abortou com `stack smashing detected`; alguns também iniciaram a calibração de pico de banda. | `pcad_hype_hpc_probe.sbatch` faz uma única execução normal, compilada com `-O3 -g`, diretamente no diretório submetido e chama somente `vtune -collect hpc-performance`, sem knobs. Os jobs 823328, 823332 e 823333 concluíram. |

As tentativas HPC que falharam alteravam mais de uma variável ao mesmo tempo.
Portanto, não é correto atribuir o aborto a um único fator, como a cópia em
`/tmp` ou `--warmup`. A conclusão experimental é mais restrita: **neste
VTune/ambiente, a invocação mínima sem knobs é estável; adicionar knobs de
afinidade ou de banda não foi validado e não deve ser usado no trabalho.**

O probe HPC ainda mostra que a coleta não é limitada por DRAM na forma que
esse VTune consegue observar com hyperthreading ativo: nos probes adaptativos,
a banda média observada ficou abaixo de 1 GB/s, contra cerca de 58--59 GB/s de
referência por pacote. A métrica `DRAM Bound` permanece indisponível nessa
plataforma com HT ativo. Use isso como indício complementar, não como prova de
ausência de gargalo de memória.

## Como repetir uma coleta válida

No frontend, envie o job; não é necessário carregar VTune ali:

```bash
cd ~/teste/INF01077
sbatch scripts/pcad_hype_vtune.sbatch
```

Isso executa Hotspots por amostragem de hardware em 20 threads: adaptativo
(`static`, `dynamic,4`, `dynamic,256`), Grayscale e Gaussian (AoS/SoA, sem e
com AVX2) e Zoom In (sem e com AVX2). Para uma verificação curta:

```bash
sbatch --time=00:20:00 scripts/pcad_hype_vtune.sbatch --smoke
```

Para HPC Performance, use o coletor mínimo. A configuração padrão é 40
threads, `static`, imagem 4000x3000 e todas as operações:

```bash
sbatch scripts/pcad_hype_hpc_probe.sbatch
```

Para o contraste já validado do filtro adaptativo, envie os dois jobs
independentemente:

```bash
sbatch -c 20 --export=ALL,HPC_PROBE_IMAGE=images/rain_paisage.jpg,HPC_PROBE_OPERATIONS=adaptive,HPC_PROBE_THREADS=20,HPC_PROBE_SCHEDULE=static scripts/pcad_hype_hpc_probe.sbatch
sbatch -c 20 --export=ALL,HPC_PROBE_IMAGE=images/rain_paisage.jpg,HPC_PROBE_OPERATIONS=adaptive,HPC_PROBE_THREADS=20,HPC_PROBE_SCHEDULE=dynamic4 scripts/pcad_hype_hpc_probe.sbatch
```

Cada coleta produz `resultados_pcad_hype_hpc_probe_<jobid>/`, contendo o
controle sem VTune, o resultado bruto e `summary.txt`. Não passe opções
adicionais para `vtune` nem misture essas coletas com os CSVs de benchmark.

## Leitura dos resultados

```bash
vtune -report summary -r resultados_pcad_hype_vtune_823234/00_adaptive_dynamic4_hotspots
vtune -report hotspots -r resultados_pcad_hype_vtune_823234/06_gaussian_omp_avx2_hotspots
vtune -report summary -r resultados_pcad_hype_hpc_probe_823333/hpc_performance
```

No Hotspots, compare quais funções concentram CPU e a utilização efetiva dos
núcleos. No HPC Performance, use CPI, utilização dos núcleos e as métricas de
memória que estiverem disponíveis, registrando explicitamente a limitação de
`DRAM Bound` sob hyperthreading.
