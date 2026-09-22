# VTune no PCAD / hype

As coletas VTune explicam os benchmarks, mas não substituem as amostras de
tempo da campanha principal. No PCAD, a versão disponível é o VTune 2021.1.1
em nós `hype`, e há duas rotas que foram validadas separadamente.

## Coletas preservadas

| Resultado | Análise | Estado |
| --- | --- | --- |
| `resultados_pcad_hype_final_vtune_hotspots_823234` | Hotspots, amostragem de hardware | 9 coletas concluídas |
| `resultados_pcad_hype_final_hpc_simd_zoom_grayscale_823348` | HPC Performance, Zoom In e Grayscale, 6000x6000, 1/20 threads, escalar/AVX2 | 8 coletas concluídas |

Os diretórios acima e os respectivos `summary.txt` são os dados a utilizar.
Os logs e diretórios de tentativas abortadas foram removidos: o diagnóstico
relevante ficou documentado nesta página.

## Por que a configuração atual funciona

| Etapa | Tentativa anterior | Evidência | Configuração mantida |
| --- | --- | --- | --- |
| Ambiente | `source vtune-vars.sh` sob `set -u` | `ZSH_VERSION: unbound variable` no job 823137 | `vtune_env.sh` suspende `nounset` somente durante o `source` do caminho oficial do PCAD. |
| Hotspots | Modo padrão por instrumentação | O motor Pin do VTune 2021 abortou ao ler `.relr.dyn` (`unknown section type 0x13`) nos jobs 823145 e 823146. | `collect_vtune*.sh` força `sampling-mode=hw`; os 9 perfis do job 823234 encerraram normalmente. |
| HPC Performance | Campanha grande, copiada para `/tmp`, com aquecimento/repetições e knobs experimentais | Nos jobs 823139, 823160, 823161, 823210, 823225 e 823233 a coleta começou e abortou com `stack smashing detected`; alguns também iniciaram a calibração de pico de banda. | A invocação mínima de `pcad_hype_hpc_probe.sbatch` foi validada primeiro. A campanha preservada usa `pcad_hype_hpc_simd_complementary.sbatch`, que mantém essa invocação simples e perfila uma operação por vez; as 8 coletas do job 823348 concluíram. |

As tentativas HPC que falharam alteravam mais de uma variável ao mesmo tempo.
Portanto, não é correto atribuir o aborto a um único fator, como a cópia em
`/tmp` ou `--warmup`. A conclusão experimental é mais restrita: **neste
VTune/ambiente, a invocação mínima sem knobs é estável; adicionar knobs de
afinidade ou de banda não foi validado e não deve ser usado no trabalho.**

No Hype, o VTune 2021.1.1 pode ocultar métricas de DRAM com hyperthreading
ativo. Portanto, CPI, utilização dos núcleos e os limites de memória que o
coletor efetivamente reportar são evidência complementar, não prova isolada de
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

Cada coleta do probe produz `resultados_pcad_hype_vtune_hpc_probe_<jobid>/`, contendo o
controle sem VTune, o resultado bruto e `summary.txt`. Não passe opções
adicionais para `vtune` nem misture essas coletas com os CSVs de benchmark.

## Leitura dos resultados

```bash
vtune -report summary -r resultados_pcad_hype_final_vtune_hotspots_823234/00_adaptive_dynamic4_hotspots
vtune -report hotspots -r resultados_pcad_hype_final_vtune_hotspots_823234/06_gaussian_omp_avx2_hotspots
vtune -report summary -r resultados_pcad_hype_final_hpc_simd_zoom_grayscale_823348/00_Zoom_In_off-avx2_t1/hpc_performance
```

No Hotspots, compare quais funções concentram CPU e a utilização efetiva dos
núcleos. No HPC Performance, use CPI, utilização dos núcleos e as métricas de
memória que estiverem disponíveis, registrando explicitamente a limitação de
`DRAM Bound` sob hyperthreading.
