# Auditoria de comparabilidade do segundo gráfico SIMD (job 824931)

## Conclusão

O usuário identificou uma confusão experimental real. O [CSV do job 824931](resultados_pcad_hype_vectorization_824931/vectorization_raw.csv) permite medir **off/auto/omp dentro da mesma variante**: a função executada é a mesma, e só as opções de compilação mudam. Mas o antigo segundo mapa agrupava variantes com transformações diferentes e podia levar à conclusão errada de que todas eram apenas “o código antigo linearizado para SIMD”. Comparar `original` com essas variantes não isola o efeito de SIMD. A igualdade dos hashes prova o mesmo *resultado*, não o mesmo algoritmo ou custo.

O [gerador corrigido](plot_vetorizacao_824931.py) agora usa, em `mapa_calor_builds_12mp.svg` e `mapa_calor_builds_36mp.svg`, **somente três variantes de linearização simples**. Os gráficos técnicos continuam mostrando as outras variantes como experimentos exploratórios, e os CSVs originais permanecem intactos.

## Auditoria do código medido

| Operação / variante do job | O que mudou frente à função de produção | Adequada para “só linearização”? |
| --- | --- | --- |
| Negative / `linear_bytes` | Remove `for(channel < 3)` e percorre `width*3` bytes contíguos; mantém `255 - valor`. | **Sim**. |
| Adjust_Brightness / `linear_bytes` | Mesma soma de 127 e mesma saturação; percorre bytes da linha. | **Sim**. |
| Adjust_Contrast / `linear_bytes` | Mesmo fator `1.5f`, conversão e saturação; percorre bytes da linha. | **Sim**. |
| Quantize / `quantize_lut` | Substitui a fórmula por pixel por uma **tabela de 256 entradas** e consulta indexada. | **Não**: pré-cálculo/lookup é outra estratégia, não apenas linearização. |
| Equalize_Histogram / `private_histogram` | Troca a redução OpenMP do histograma por 256 bins privados por thread e fusão; além disso, lineariza o remapeamento. | **Não**: a estratégia de contagem também mudou. |
| Gaussian_3x3…11x11 / `aos_direct`, `soa_direct` | Substitui coeficientes e acumuladores `float` por pesos binomiais e acumuladores inteiros; no SoA muda também o layout. | **Não**. Nem a variante `aos_direct` representa “mesma convolução só linearizada”. |
| Gaussian_3x3…11x11 / `aos_separable`, `soa_separable` | Além da aritmética inteira, decompõe a convolução 2D em duas passadas 1D; SoA também muda layout. | **Não**: reduz a complexidade algorítmica. |
| Flip_Horizontal / `out_of_place` | Substitui transformação in-place por buffer de saída separado. | **Não**: muda movimentação, alocação e padrão de escrita. |
| Rotate_CW, Rotate_CCW / `blocked` | Acrescenta tiling de 32×32 e outra ordem de travessia. | **Não**: é otimização de localidade. |
| Grayscale, Zoom_In / `original` | Não são candidatas reescritas nesse benchmark; chamam a versão de produção do **commit do job 824931**. | **Controle**, não evidência de ganho da linearização. |

Código: [linearização e variantes](577262-FPI-Relatorio2/vectorization_benchmark.cpp), [funções de produção](577262-FPI-Relatorio2/image_manipulation.cpp), [runner da campanha](run_vectorization_tests.sh). O [relatório de loops](RELATORIO_LOOPS_SIMD_REESCRITAS_824931.md) e os [diagnósticos GCC](resultados_pcad_hype_vectorization_824931/auto-avx2-compiler-focus.txt) identificam quais laços foram de fato vetorizados. `-fno-tree-vectorize` desliga a vetorização automática de laços, não toda instrução vetorial da arquitetura.

## O que ainda é válido e o que deve ser retirado da apresentação

- **Válido:** em cada linha `linear_bytes`, comparar `off-avx2`, `auto-avx2` e `omp-avx2` mede o efeito do compilador/pragma **no mesmo código e com o mesmo alvo Haswell**. Os três casos são o núcleo do mapa corrigido.
- **Limite dessa inferência:** `off-avx2` desliga o vetorizador de laços do GCC; não garante ausência literal de qualquer instrução SIMD nem que toda diferença de tempo provenha só das instruções vetoriais. Os relatórios GCC/assembly identificam o laço realmente transformado.
- **Válido, mas outra pergunta:** comparar os três builds de `quantize_lut`, `private_histogram` ou `aos_direct` mostra o efeito da vetorização **nesses algoritmos alternativos**. Esses números continuam úteis nos gráficos detalhados e no caso Quantize/VTune.
- **Inválido:** atribuir `original / quantize_lut`, `original / private_histogram` ou `original / aos_separable` exclusivamente a SIMD ou à linearização. Também não comparar tempos absolutos de `aos_direct` inteiro com a Gaussiana original `float` como se fossem o mesmo kernel.
- **Não controlado entre campanhas:** a função de produção Grayscale mudou de estrutura entre os jobs antigos e 824931. Sua razão entre builds em 824931 é válida, mas a diferença para o primeiro gráfico não demonstra sozinha o efeito da reescrita.

## Como ampliar o segundo gráfico sem misturar fatores

O job 824931 **não contém** dados para colocar Quantize, histograma ou convolução tradicional no mapa “somente linearização”. Isso exige nova execução, sem alterar retroativamente o CSV:

1. **Quantize:** manter grayscale, mínimo/máximo e a fórmula `new_luminance_bin`/`round` originais. Mudar apenas o percurso do laço final para um índice linear de pixels (não uma LUT). Cronometrar as mesmas fases na versão antiga e candidata; validar hashes para `off/auto/omp`.
2. **Equalize_Histogram:** manter `compute_normalized_cummulative_histogram` original, inclusive a redução de 256 bins. Linearizar **somente o remapeamento** como um laço de `width*height*3` bytes; relatar o tempo da fase e do total separadamente. A contagem indexada não vira SIMD seguro simplesmente por acrescentar pragma.
3. **Gaussiana 11×11:** manter os 121 coeficientes `float` e a mesma regra de arredondamento. Comparar o laço por pixel com a variante AoS que, para cada tap, varre a linha de bytes de saída (`float_row_aos` no benchmark atual). Confirmar equivalência exata e mostrar tempo do kernel; alocação/conversão precisam ter escopo idêntico ou ser exibidas em fases separadas. O [follow-up preparado](README_SIMD_FOLLOWUP.md) já mede variantes `float` diretas, mas seus resultados ainda não são os do job 824931.

Em todos os casos, apresentar duas razões diferentes com nomes claros: **efeito da reestruturação** = `tempo(original, build X) / tempo(candidata, build X)` e **efeito da vetorização** = `tempo(candidata, off) / tempo(candidata, auto ou omp)`. Mesmo com uma mudança restrita ao laço, a primeira razão **não** é apenas ganho SIMD; inclui overheads escalares, endereçamento e código gerado. O protocolo deve manter imagem, threads, schedule, compilador, flags, política de aquecimento, quantidade de amostras e validação de saída idênticos.

**Atualização:** a [nova campanha enxuta](README_LINEAR_SIMD.md) implementa a alternativa sem lookup, histograma privado ou convolução inteira/separável. Ela opta por **não criar** uma candidata artificial para Quantize, Grayscale ou Zoom In: esses três ficam como controles. Também não introduz SoA. O roteiro acima permanece como possibilidade futura, não como descrição de resultados já coletados.
