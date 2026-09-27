# Rodada complementar de SIMD — convolução float direta

Esta campanha repete as **oito operações do primeiro mapa de apresentação**:
`Adjust_Brightness`, `Adjust_Contrast`, `Equalize_Histogram`,
`Gaussian_11x11`, `Grayscale`, `Negative`, `Quantize` e `Zoom_In`.
Mantém a imagem de 6000×6000, `OMP_SCHEDULE=static`, threads
**1, 2, 4, 8, 12, 16 e 20**, um aquecimento e **cinco amostras** por
configuração. Os três builds têm o mesmo alvo Haswell:

| Build | Propósito |
| --- | --- |
| `off-avx2` | Desliga a vetorização automática de laços (`-fno-tree-vectorize`); isso não elimina toda instrução vetorial. |
| `auto-avx2` | GCC escolhe os laços a vetorizar, sem os pragmas explícitos. |
| `omp-avx2` | Acrescenta os pragmas OpenMP SIMD explícitos ao mesmo código. |

As oito funções de produção **não foram alteradas**. Seus tempos ficam em
`original_raw.csv`, com hashes comparados ao `off-avx2`. No mesmo job, a
Gaussiana 11×11 recebe quatro implementações **float e diretas**, com os
mesmos 121 coeficientes da função de produção, em
[`vectorization_benchmark.cpp`](577262-FPI-Relatorio2/vectorization_benchmark.cpp):
Como no primeiro mapa, usa `single_channel=false` e `clamp_offset=false`.
É uma **nova medição das funções na revisão atual**; não atribua diferenças
em relação ao mapa antigo somente às novas variantes, pois o código de
produção mudou entre campanhas.

| Variante | Organização | Escopo do tempo `total` |
| --- | --- | --- |
| `float_pixel_outer` | Pragma no pixel de saída, como no código inicial | Kernel com saída pré-alocada; referência das variantes float. |
| `float_tap_products` | Pragma nos 11 produtos de cada linha do kernel; soma serial na ordem original | Kernel com saída pré-alocada. |
| `float_row_aos` | Para cada tap, percorre a linha de bytes RGB de saída; SIMD atravessa pixels/canais | Kernel com saída pré-alocada. |
| `float_row_soa` | Mesma varredura, separando R/G/B | Conversão AoS→SoA + kernel + conversão SoA→AoS; as fases ficam separadas no CSV. |

`float_tap_reduction` permanece disponível no executável apenas para
diagnóstico, **fora do job formal**: no teste local com `poke.jpg`, o pragma
`reduction` mudou 11 bytes em 1 nível de cor. A variante
`float_tap_products` preservou todos os bytes. O job formal exige saída
**exata** das quatro variantes escolhidas; uma divergência interrompe o
resumo. Um `--check-production` na validação inicial também confere que
`float_pixel_outer` reproduz a Gaussiana `float` de produção.

## Submissão no PCAD

Depois de enviar as mudanças ao repositório e atualizar o checkout no
frontend, a partir da raiz do projeto:

```bash
job=$(sbatch --parsable scripts/pcad_hype_simd_followup.sbatch)
echo "$job"
squeue -j "$job"
```

O job usa um nó `hype` exclusivo com 20 CPUs, limite de um dia, e grava
`resultados_pcad_hype_simd_followup_ID/`. Não depende de outro job. O script
não fixa afinidade nem política NUMA. Para validar antes, no ambiente Linux:

```bash
bash run_simd_followup_tests.sh --quick --output resultados_simd_followup_checagem
```

O diretório de saída deve ser novo. A campanha salva os CSVs brutos, hashes,
medianas, mínimo/máximo, relatórios do GCC, flags e os gráficos em
`visualizacoes/index.html`.

## Leitura correta

- Nos mapas das **funções originais**, cada razão compara builds da mesma
  função (`off/auto`, `auto/omp` ou `off/omp`).
- Nos mapas das **variantes float**, a razão compara `float_pixel_outer`
  à outra organização **dentro do mesmo build**. O SoA inclui suas
  conversões no total; `gaussian_float_raw.csv` também separa `kernel`.
- Não usar milissegundos absolutos da função de produção para medir o ganho
  da reordenação: aquela função inclui alocação interna; as variantes float
  recebem buffers pré-alocados. Também não atribuir ao SIMD um ganho que
  aparece já no build `off-avx2`.
- `optimized: loop vectorized` nos relatórios GCC identifica o laço
  escolhido; apenas as medições mostram se a escolha foi vantajosa.
