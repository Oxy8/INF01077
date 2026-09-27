# Apresentação OpenMP: 10 minutos no total

## Roteiro vigente: jobs 825196 e 825200

Para a parte de SIMD (até cinco minutos), use o [relatório atualizado e seu
roteiro de slides](RELATORIO_SIMD_ABORDAGENS_825196_825200.md#três-exemplos-para-os-slides-de-simd).
O **primeiro mapa** agora é o [mapa das funções de produção do job 825196](resultados_pcad_hype_simd_followup_825196/visualizacoes/figures/01_simd_producao_atual_825196.svg),
com 36 MP e Zoom In. O **segundo** é o [mapa das variantes reestruturadas do
job 825200](resultados_pcad_hype_linear_simd_825200/figures/simd_mesma_variante_36mp.svg),
com 1 e 20 threads; Zoom In de 36 MP não foi medido nesse job. Os três exemplos
de código são Contrast, Gaussiana 11×11 e remapeamento do histograma.

## Roteiro anterior — histórico, não usar como apresentação final

Reservar **até cinco minutos para sua parte sobre SIMD** e os outros
**cinco minutos para a parte sobre static versus dynamic do colega**. O roteiro
abaixo detalha somente sua fala; o colega decide seus próprios slides. Não
gastar tempo explicando SoA, layout ou convolução separável. A família
Gaussiana aparece como **uma convolução RGB direta 11×11**, representativa
do padrão inicial.

## Slides e tempo

| Slide | Tempo | Figura e mensagem principal |
| --- | ---: | --- |
| 1. Contexto e threads | 0:35 | [Speedup das operações regulares com static](visualizacoes_pcad_hype_final_benchmark_principal/figures/00_speedup_total_operacoes_static.svg). Processamento de imagens em CPU com OpenMP; mais threads reduzem o tempo, com ganho abaixo do ideal. A [eficiência](visualizacoes_pcad_hype_final_benchmark_principal/figures/00_eficiencia_total_operacoes_static.svg) fica no material de apoio. |
| 2. Primeira tentativa com SIMD | 0:55 | [Mapa resumido da versão inicial](visualizacoes_pcad_hype_final_simd_avx2_adaptativo/figures/01_simd_avx2_resumo_apresentacao.svg). Os pragmas quase não mudaram os tempos na maioria das operações; Zoom In foi a exceção visível. |
| 3. O formato do laço | 1:10 | Projetar o contraste entre os dois trechos de Negative abaixo. Acrescentar uma frase sobre o laço da convolução RGB direta. |
| 4. Resultado da linearização isolada | 1:25 | [Mapa dos três laços ponto a ponto, 36 MP](visualizacoes_pcad_hype_vetorizacao_824931/figures/mapa_calor_builds_36mp.svg). Negative, Brightness e Contrast mantêm a aritmética original e mudam apenas a travessia para bytes contíguos. O GCC vetorizou os três automaticamente; o pragma acrescentou pouco. **Não** usar esse mapa para alegar ganho da reescrita inteira sobre o código antigo. |
| 5. Síntese e passagem ao colega | 0:30 | O pragma indica uma intenção; o GCC decide **qual laço** vetorizar. Os tempos mostram se essa decisão ajudou. Deixar a pergunta sobre schedules para a segunda metade. |

Sua fala planejada: **4:35**, com **0:25 de margem** até os cinco minutos.
O colega dispõe dos **cinco minutos restantes**; a apresentação inteira tem
**10:00**. O [mapa de 12 MP](visualizacoes_pcad_hype_vetorizacao_824931/figures/mapa_calor_builds_12mp.svg)
mostra os mesmos três laços; Zoom In e Quantize/VTune ficam como material de apoio
nos resultados detalhados, não nesse mapa de linearização isolada.

## Trechos para os slides 2 e 3

No código original, `OMP_SIMD` só se expande para `#pragma omp simd` no build
`omp-avx2`. O pragma foi colocado no laço de **pixels**, que ainda contém
um laço de três canais. Trecho de
[`apply_negative`](577262-FPI-Relatorio2/image_manipulation.cpp#L888):

```cpp
OMP_SIMD
for (int j = 0; j < img.width; ++j) {       // pixel
    const int index = (i * img.width + j) * 3;
    for (int channel = 0; channel < 3; ++channel)
        img.data[index + channel] = 255 - img.data[index + channel];
}
```

No [candidato reescrito](577262-FPI-Relatorio2/vectorization_benchmark.cpp#L180),
a linha RGB continua fisicamente intercalada, mas o laço interno percorre
todos os bytes contíguos. `EXP_SIMD` é o pragma somente em `omp-avx2`:

```cpp
#pragma omp parallel for schedule(runtime)
for (int y = 0; y < height; ++y) {
    Byte* row = data + static_cast<size_t>(y) * width * 3;
    EXP_SIMD
    for (int byte = 0; byte < width * 3; ++byte)
        row[byte] = static_cast<Byte>(255 - row[byte]);
}
```

O [GCC original](resultados_pcad_hype_compiler_evidence_824453/omp-avx2/image_manipulation.opt-info.txt)
não confirmou a vetorização do laço de pixels de Negative. No
[experimento novo](resultados_pcad_hype_vectorization_824931/auto-avx2-compiler-focus.txt),
o GCC confirmou `loop vectorized using 32 byte vectors` no laço de bytes
**sem o pragma explícito**. Brightness e Contrast receberam o mesmo
diagnóstico. No mapa novo de 36 MP, em 1 thread, `off/auto` mede
**3,68×, 6,48× e 6,19×**, respectivamente. `auto/omp` fica próximo de
`1,00×`. Comparar esses três builds no **mesmo código** isola o efeito do
vetorizador; comparar candidato e original inclui outras mudanças de código.

## A convolução: o que sabemos exatamente

Esta parte é apoio para perguntas; na fala, resumir em uma frase. A
[implementação original](577262-FPI-Relatorio2/image_manipulation.cpp#L517)
marca o laço de pixels com `OMP_SIMD`, mas cada pixel chama um auxiliar que
percorre linhas e colunas do kernel e acumula três canais RGB:

```cpp
OMP_SIMD
for (int x = radius; x < output_width - radius; ++x) {
    for (int dy = -radius; dy <= radius; ++dy)
        for (int dx = -radius; dx <= radius; ++dx) {
            sum_r += weight * input_rgb[...];
            sum_g += weight * input_rgb[... + 1];
            sum_b += weight * input_rgb[... + 2];
        }
    // normaliza e grava um pixel RGB
}
```

Esse pseudocódigo resume o ninho real: os `for(dy/dx)` estão no auxiliar
[`apply_11_by_11_convolution_to_pixel`](577262-FPI-Relatorio2/image_manipulation.cpp#L226).
Pixels de saída diferentes **não dependem** uns dos outros; em princípio,
SIMD entre pixels faz sentido. Entretanto, o GCC do
[job 824453](resultados_pcad_hype_compiler_evidence_824453/omp-avx2/image_manipulation.opt-info.txt)
reportou `multiple nested loops`/`vectorized 0 loops` para esse caminho
RGB direto. O compilador não transformou o ninho em um vetor de pixels de
saída. A [auditoria original](RELATORIO_LOOPS_SIMD_17_OPERACOES.md)
registra o mesmo resultado para os cinco tamanhos. O
[mapa original resumido](visualizacoes_pcad_hype_final_simd_avx2_adaptativo/figures/01_simd_avx2_resumo_apresentacao.svg)
mostra aproximadamente **1,00×** de `off-avx2/omp-avx2` nessa convolução
11×11: o pragma não trouxe ganho mensurável ali.

No experimento posterior, a
[convolução RGB direta](577262-FPI-Relatorio2/vectorization_benchmark.cpp#L303)
foi escrita com acumuladores inteiros. Aqui o GCC **vetorizou o laço
interno `dx`** com vetores de 32 bytes, tanto em
[`auto-avx2`](resultados_pcad_hype_vectorization_824931/auto-avx2-compiler-focus.txt)
como em [`omp-avx2`](resultados_pcad_hype_vectorization_824931/omp-avx2-compiler-focus.txt),
mas **não o laço `x` dos pixels de saída**. Vetorizar `dx` trabalha em
vários coeficientes usados para formar **um pixel**, com acumulação nos
mesmos `sum_r/g/b`. Vetorizar `x` permitiria trabalhar em **vários pixels
independentes** por vetor. São formas diferentes de usar SIMD; o relatório
GCC prova qual laço recebeu vetorização, não qual foi o custo de cada
instrução em tempo de execução.

O [CSV do job 824931](resultados_pcad_hype_vectorization_824931/vectorization_summary.csv)
mostra, para essa mesma variante direta em **36 MP, 1 thread**, medianas de
**7246 ms (`off`)**, **8904 ms (`auto`)** e **7754 ms (`omp`)**. Com 20
threads: **419, 514 e 448 ms**. Assim, nesta implementação,
`off/auto ≈ 0,81×` e `off/omp ≈ 0,93×`: a vetorização dos taps não tornou
o total mais rápido. O pragma melhora `omp` em relação a `auto`, mas não
fez o GCC vetorizar os pixels. A matemática e o escopo desse candidato
inteiro não são idênticos aos da função original em `float`; **não comparar
seus milissegundos diretamente com a campanha original**.

O motivo estrutural da dificuldade está documentado: ninho de laços dentro
de cada pixel, três acumuladores, RGB intercalado e normalização por pixel.
É plausível que a redução horizontal dos taps, o custo de reorganizar RGB
e o código gerado para aritmética inteira anulem a vantagem do vetor no
`dx`. Os dados atuais **não isolam qual desses custos domina**. Para
responder a essa última pergunta com mais precisão, seria necessário
comparar a montagem dos três builds e perfilar **somente a função direta**
com o mesmo tamanho de imagem e número de threads. Não é necessário para a
mensagem da sua parte de cinco minutos.

## Como ler os mapas e o que deixar de fora

O [mapa original para apresentação](visualizacoes_pcad_hype_final_simd_avx2_adaptativo/figures/01_simd_avx2_resumo_apresentacao.svg)
usa mediana de cinco execuções e mostra `off-avx2/omp-avx2` para 1, 2,
4, 8, 12, 16 e 20 threads. Acima de `1×`, `omp-avx2` foi mais rápido. O
mapa reúne os cinco tamanhos de Gaussiana em um único exemplo 11×11 RGB
direto. Flip e Rotate ficam fora da apresentação: as funções originais
não tinham `OMP_SIMD`, e as variantes novas não tiveram seus laços
principais vetorizados pelo GCC; ver as [auditorias do código original](RELATORIO_LOOPS_SIMD_17_OPERACOES.md)
e [das variantes experimentais](RELATORIO_LOOPS_SIMD_REESCRITAS_824931.md).

O [mapa de linearização de 36 MP](visualizacoes_pcad_hype_vetorizacao_824931/figures/mapa_calor_builds_36mp.svg)
compara 1 e 20 threads **somente para Negative, Brightness e Contrast**.
Os três builds têm o mesmo alvo Haswell:
`off-avx2` desliga vetorização automática de **laços**;
`auto-avx2` permite ao GCC decidir; `omp-avx2` acrescenta o pragma.
Cada célula é uma razão de medianas da **mesma variante**: `off/auto`,
`off/omp`, `auto/omp`. Azul significa que o denominador foi mais rápido;
laranja, mais lento. Os números tornam a leitura independente das cores.
A Gaussiana, Quantize e Equalize_Histogram foram retirados do mapa porque
suas variantes do job 824931 alteram a matemática ou a estratégia do algoritmo.
Grayscale e Zoom In também foram retirados: são controles que chamam as funções
de produção na revisão atual, e não candidatos linearizados. Eles continuam
nos gráficos técnicos e no CSV. Isso não quer
dizer que a função Grayscale seja exatamente a mesma compilada na campanha
inicial: entre os jobs 822851 e 824931, `apply_gray_scale_inplace` passou
a chamar o novo laço `apply_gray_scale_buffer` sobre ponteiro e dimensões
passados diretamente. A fórmula da luminância foi preservada, mas o formato
do código mudou. O gráfico inicial compara `off-avx2/omp-avx2` e mediu,
para Grayscale em 36 MP, **140,16/139,02 ms = 1,01×** em 1 thread; o CSV
do job 824931 compara `off-avx2/auto-avx2` na revisão atual e mediu
**78,02/61,07 ms = 1,28×**. Em 20 threads, as razões são aproximadamente
**1,00×** e **1,16×**, respectivamente. No job novo, `auto/omp ≈ 1,00×`
em 1 thread, e `off/omp` também é **1,28×**: a diferença para a campanha
inicial não é mero efeito de trocar o denominador de `omp` para `auto`.
Dentro do job novo, o ganho veio da vetorização automática, não de adicionar
o pragma. **Não há ensaio controlado que isole quanto da diferença entre
campanhas decorre da refatoração**, do protocolo ou do ambiente.

**Zoom In:** no código original, o
[GCC](resultados_pcad_hype_vectorization_824931/auto-avx2-original-core-compiler.txt)
confirmou vetorização da [interpolação vertical](577262-FPI-Relatorio2/image_manipulation.cpp#L710),
enquanto cópia e interpolação horizontal não receberam a mesma confirmação.
Na campanha nova de 12 MP, `off/auto` foi **1,40×** em 1 thread e cerca de
**1,00×** em 20. Isto pode ser dito em uma frase no slide 2 se houver
tempo; explicar as três fases consumiria um slide próprio.

**Quantize e VTune:** o pragma vetorizou o
[lookup indexado](577262-FPI-Relatorio2/vectorization_benchmark.cpp#L212),
mas os [controles isolados](resultados_pcad_hype_vtune_quantize_825087/control_medians.csv)
mediram **38,76 ms** (`auto`) contra **64,34 ms** (`omp`) em 1 thread.
Os [Hotspots](resultados_pcad_hype_vtune_quantize_825094/omp-avx2_t1/hotspots_functions.txt)
localizam a função quente. Deixar como reserva para perguntas. O resumo
HPC mede o processo inteiro e não demonstra sozinho a causa fina da
regressão. Nenhum novo job VTune é indispensável ao roteiro.

Fontes e reprodutibilidade: [auditoria de comparabilidade](AUDITORIA_COMPARABILIDADE_SIMD_824931.md),
[gráfico original](plot_resultados_avx.py),
[gráfico novo](plot_vetorizacao_824931.py),
[script da campanha](run_vectorization_tests.sh),
[Makefile](Makefile#L62) e
[auditoria de todos os laços reescritos](RELATORIO_LOOPS_SIMD_REESCRITAS_824931.md).
O job 824931 registra seu [commit](resultados_pcad_hype_vectorization_824931/git_commit.txt).
As linhas dos logs GCC se referem a esse commit; algumas funções mudaram de
linha no arquivo atual após a adição do experimento Quantize/VTune.
