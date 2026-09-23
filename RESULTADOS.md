# Resultados preservados

Os diretórios abaixo são os dados que sustentam a versão final do relatório.
O identificador final é o job Slurm que os produziu; `pcad_hype` identifica a
origem no cluster PCAD, partição `hype`.

| Diretório | Conteúdo | Uso principal |
| --- | --- | --- |
| `resultados_pcad_hype_final_regular_avx2_5reps_822851` | 17 operações regulares, imagens de 12 e 36 MP, `static`, `dynamic,1` e `dynamic,16`, 5 repetições e builds escalar/SIMD/AVX2 | Escalabilidade, schedules e SIMD das operações regulares |
| `resultados_pcad_hype_final_adaptativo_chunks_avx2_5reps_822852` | Filtro adaptativo, imagens reais e controles, varredura de chunks, 5 repetições e builds SIMD/AVX2 | Carga irregular, `static` versus `dynamic` e tamanho de chunk |
| `resultados_pcad_hype_final_smt_avx2_5reps_822853` | Comparação 20 versus 40 threads | Apêndice sobre hyperthreading |
| `resultados_pcad_hype_final_layout_aos_soa_avx2_5reps_822854` | AoS direto, SoA ingênuo e SoA separável para Grayscale/Gaussian 11x11, com fases separadas | Efeito do layout e da convolução separável |
| `resultados_pcad_hype_final_vtune_hotspots_823234` | Nove coletas VTune Hotspots por amostragem de hardware | Hotspots e utilização de CPU |
| `resultados_pcad_hype_final_hpc_simd_zoom_grayscale_823348` | HPC Performance: Zoom In e Grayscale, 1/20 threads, escalar/AVX2 | Relação entre SIMD, paralelismo e memória |
| `resultados_pcad_hype_final_schedules_confirmacao_10reps_823349` | Confirmação de schedules: seis operações, 20 threads, 10 repetições intercaladas | Verificar ganhos/perdas de `dynamic` por mediana |

## Visualizações e relatório

| Diretório | Origem |
| --- | --- |
| `visualizacoes_pcad_hype_final_benchmark_principal` | Campanhas 822851, 822852 e 822853; gráficos gerais por mediana |
| `visualizacoes_pcad_hype_final_simd_avx2_adaptativo` | Recortes de AVX2, schedules e filtro adaptativo das campanhas 822851 e 822852 |
| `visualizacoes_pcad_hype_final_layout_aos_soa` | Campanha de layouts 822854, com kernel separado das conversões |
| `visualizacoes_pcad_hype_final_experimentos_complementares` | Campanhas HPC/SIMD 823348 e confirmação de schedules 823349 |
| `relatorio_final_dados_consolidados` | Tabelas consolidadas, validação e texto de resultados |

As figuras e tabelas usam **mediana** como estimativa central e preservam
mínimo--máximo. Os resultados de campanhas preliminares e as visualizações que
foram substituídas foram removidos para não serem confundidos com os dados
finais.

Para respostas rastreáveis às perguntas de interpretação — SIMD, schedules,
Zoom, Flip e layouts — consulte [`ANALISE_EVIDENCIAS.md`](ANALISE_EVIDENCIAS.md).
Os jobs que fecham as lacunas experimentais estão em
[`EXPERIMENTOS_COMPLEMENTARES_FINAIS.md`](EXPERIMENTOS_COMPLEMENTARES_FINAIS.md).

## Regenerar as visualizações

Na raiz do projeto:

```bash
python plot_resultados_pcad.py \
  --regular resultados_pcad_hype_final_regular_avx2_5reps_822851 \
  --adaptive resultados_pcad_hype_final_adaptativo_chunks_avx2_5reps_822852 \
  --smt resultados_pcad_hype_final_smt_avx2_5reps_822853 \
  --out visualizacoes_pcad_hype_final_benchmark_principal

python plot_resultados_avx.py \
  --regular resultados_pcad_hype_final_regular_avx2_5reps_822851 \
  --adaptive resultados_pcad_hype_final_adaptativo_chunks_avx2_5reps_822852 \
  --out visualizacoes_pcad_hype_final_simd_avx2_adaptativo

python plot_resultados_layout.py
python plot_experimentos_complementares.py
```

Os dois jobs diagnósticos adicionais estão descritos em
[`DIAGNOSTICOS_FINAIS.md`](DIAGNOSTICOS_FINAIS.md). Seus resultados devem ser
mantidos separados das campanhas principais, pois usam afinidade controlada e
medição por fase.
