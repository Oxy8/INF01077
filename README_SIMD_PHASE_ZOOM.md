# Campanha complementar: fases e Zoom In

Esta campanha **não modifica** `quantize_gray`, `equalize_histogram` ou `zoom_in_image`. O executável experimental mede o total da função de produção e, em outra cópia da mesma imagem, suas fases. Os laços finais das fases são réplicas da aritmética original; o programa exige saída final idêntica byte a byte. Por serem outro contexto de compilação e outro estado de cache, os tempos das fases ajudam a localizar custos, mas não devem ser somados para fabricar um tempo de produção.

## O que será medido

- `Quantize`, 36 MP, 1 e 20 threads: `production_total` (RGB), `grayscale`, `production_after_gray` (a própria função de produção sobre entrada já cinza), `minmax` e `remap`.
- `Equalize_Histogram`, 36 MP, 1 e 20 threads: `production_total`, contagem do histograma RGB (calcula luminância sem converter a imagem), acumulado/normalização de 256 posições e remapeamento RGB.
- `Zoom_In` de produção, 36 MP, `static`, 1, 2, 4, 8, 12, 16, 17, 18, 19 e 20 threads, vinte repetições em **cada** ponto. A ordem dos níveis de threads é invertida a cada rodada para testar a estabilidade do salto observado no job 825196 sem deixar 20 threads sempre por último.
- `Zoom_In` como controle do segundo mapa, 12 e 36 MP, 1 e 20 threads, dez repetições. A saída está pré-alocada; só o kernel entra no tempo. **Não misturar** esse tempo absoluto com o Zoom de produção, que inclui alocação.

Todas as configurações usam `off-avx2`, `auto-avx2` e `omp-avx2`, `OMP_SCHEDULE=static`, `OMP_DYNAMIC=FALSE`, aquecimento e validação por hash. A ordem dos builds gira entre repetições. São guardados tempos brutos, medianas e mínimo/máximo. O pré-voo verifica os três builds antes da campanha completa.

## Executar

Da raiz do repositório no frontend do PCAD:

```bash
sbatch scripts/pcad_hype_simd_phase_zoom.sbatch
```

O job grava `resultados_pcad_hype_simd_phase_zoom_JOBID/` na raiz, sem sobrescrever campanhas anteriores. Para uma validação local curta:

```bash
bash run_simd_phase_zoom_tests.sh --quick --output resultados_simd_phase_zoom_teste
```

O teste local é apenas funcional; não deve ser comparado em tempo com o nó hype. O job usa até quatro horas, um nó `hype` exclusivo e 20 CPUs. Não requer VTune nem `numactl`.

## Após baixar os resultados

O novo job já gera `phase_summary.csv`, `zoom_production_summary.csv`, `zoom_control_summary.csv` e três SVGs em `figures/`, incluindo a dispersão máximo/mínimo do Zoom. Para atualizar **uma cópia** do segundo mapa, combinando somente a linha Zoom do novo job com as demais linhas do job 825200:

```bash
python3 plot_linear_simd.py \
  --raw resultados_pcad_hype_linear_simd_825200/linear_simd_raw.csv \
  --zoom-raw resultados_pcad_hype_simd_phase_zoom_JOBID/zoom_control_raw.csv \
  --out resultados_pcad_hype_simd_phase_zoom_JOBID/figures_segundo_mapa
```

O SVG de 36 MP terá Zoom In; o de 12 MP substituirá apenas sua linha Zoom. As demais linhas continuam sendo dados do 825200 e são rotuladas como tal. Confira `source_sha256.txt`: para comparar dentro do mapa, `image_manipulation.cpp` e `vectorization_benchmark.cpp` devem ter o mesmo hash nas duas campanhas. Cada razão `off/auto`, `off/omp` ou `auto/omp` é calculada **dentro da mesma campanha e variante**, nunca dividindo milissegundos de jobs diferentes.
