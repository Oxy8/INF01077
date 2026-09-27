# SIMD no processamento de imagens: pragma inicial e reorganização dos laços

Este relatório usa o job **825196** como referência das funções de produção na revisão atual, o job **825200** para as variantes com laços reestruturados e o job **825290** para confirmar Zoom In e medir Quantize sem incluir Grayscale. O objetivo é distinguir três efeitos: mudar a organização do código, permitir vetorização automática ao GCC e acrescentar o pragma explícito. A seção final seleciona três transformações para a apresentação de aproximadamente cinco minutos dedicada a SIMD.

## Como ler os resultados

- `off-avx2`: alvo Haswell, mas vetorização automática de **laços** desativada por `-fno-tree-vectorize`. O nome não significa ausência absoluta de instruções vetoriais.
- `auto-avx2`: mesmo alvo e código, vetorização automática permitida, sem `EXP_SIMD`/`OMP_SIMD`.
- `omp-avx2`: mesmo alvo e código, com os pragmas OpenMP SIMD explícitos.
- Uma razão `tempo A / tempo B` **maior que 1** favorece B. Cada célula abaixo divide **medianas**, não combina tempos de execuções individuais.
- `#pragma omp parallel for schedule(runtime)` distribui iterações entre threads; `#pragma omp simd` pede vetorização das iterações de um laço. São decisões distintas.

### O que o primeiro mapa divide — e como os três builds foram compilados

O [primeiro mapa final](visualizacoes_simd_finais/01_abordagem_original.svg) mostra **`mediana(off-avx2) / mediana(omp-avx2)`**, e **não** `off-avx2 / auto-avx2`. Por exemplo, a célula `Grayscale, 1 thread` do job 825290 divide 77,98 ms por 60,94 ms ≈ 1,28×; `Zoom In, 1 thread` do mesmo job divide 349,96 ms por 284,74 ms ≈ 1,23×. Uma célula acima de 1× indica que `omp-avx2` foi mais rápido. Esse contraste junta a vetorização automática habilitada **e** a possível contribuição dos pragmas. Para separar os efeitos, o [segundo mapa final](visualizacoes_simd_finais/02_abordagem_linearizada.svg) também mostra `off/auto` e `auto/omp` dentro de cada variante. A [proveniência por célula](visualizacoes_simd_finais/dados_mapas.csv) impede confundir jobs e escopos.

O [script executado no job](run_simd_followup_tests.sh#L53) chamou, a partir da raiz do projeto, estes comandos (um por build):

```bash
make -B DEBUG=1 SIMD=off-avx2  COMPILER_DIAGNOSTICS=1 all vectorization
make -B DEBUG=1 SIMD=auto-avx2 COMPILER_DIAGNOSTICS=1 all vectorization
make -B DEBUG=1 SIMD=omp-avx2  COMPILER_DIAGNOSTICS=1 all vectorization
```

`-B` força a recompilação; `all` produz `build/<build>/image_benchmark` e `vectorization` produz `build/<build>/vectorization_benchmark`. Para **todos** os arquivos C++ desses executáveis, o [Makefile](Makefile#L36) passou `-O3 -Wall -Wextra -std=c++17 -fopenmp -ffp-contract=off -g`, acrescidos exatamente dos seguintes parâmetros de cada build:

| Build | Parâmetros adicionais passados ao GCC | Significado |
| --- | --- | --- |
| `off-avx2` | `-DOMP_EXPLICIT_SIMD=0 -fno-tree-vectorize -march=haswell` | Alvo AVX2/Haswell, mas sem a passada de vetorização automática de laços; o macro `OMP_SIMD` fica vazio. |
| `auto-avx2` | `-DOMP_EXPLICIT_SIMD=0 -march=haswell` | Mesmo alvo; o GCC pode vetorizar automaticamente, mas `OMP_SIMD` fica vazio. |
| `omp-avx2` | `-DOMP_EXPLICIT_SIMD=1 -march=haswell` | Mesmo alvo e vetorização automática habilitada; `OMP_SIMD` expande para `_Pragma("omp simd")`. |

Como `COMPILER_DIAGNOSTICS=1`, a compilação de `image_manipulation.cpp` acrescentou `-fopt-info-vec-all=build/<build>/vectorization-core-all.log`, e a de `vectorization_benchmark.cpp` acrescentou `-fopt-info-vec-all=build/<build>/vectorization-experiment-all.log`. Essas opções **geram relatórios**, não constituem uma quarta modalidade de SIMD. O Makefile também passa `-I577262-FPI-Relatorio2`, macros que registram o build/flags no CSV e `-MMD -MP` para dependências; a ligação usa `g++ -fopenmp`. Os builds de benchmark usam o mesmo código-fonte, mas os pragmas são ativados somente no terceiro caso. A [versão do compilador registrada](resultados_pcad_hype_simd_followup_825196/compiler.txt) e as flags por execução em [original_raw.csv](resultados_pcad_hype_simd_followup_825196/original_raw.csv) permitem auditar o ambiente efetivamente usado, não apenas a receita do Makefile.

A campanha anterior **822851** pertence a uma revisão mais antiga e **não fornece o mapa principal deste relatório**. Seu [mapa histórico](visualizacoes_pcad_hype_final_simd_avx2_adaptativo/figures/01_simd_avx2_resumo_apresentacao.svg) continua acessível apenas para rastrear a evolução, não para ser apresentado como controle do 825200. Para quantificar o efeito de SIMD, compare builds **dentro da mesma campanha e variante**. Os jobs 825196 e 825200 ainda rodaram em nós distintos e registraram hashes distintos de `vectorization_benchmark.cpp` ([825196](resultados_pcad_hype_simd_followup_825196/source_sha256.txt), [825200](resultados_pcad_hype_linear_simd_825200/source_sha256.txt)), embora o hash de `image_manipulation.cpp` seja igual. Não dividir tempos absolutos de um job pelos do outro.

## 1. Abordagem original: pragma nos laços sem reescrita experimental

![Mapa final da abordagem original: tempo off-avx2 dividido por omp-avx2, 36 MP, static](visualizacoes_simd_finais/01_abordagem_original.svg)

O mapa final usa **1 e 20 threads**, os dois pontos comuns a todas as campanhas recentes. Negative, Brightness, Contrast, Convolução 11×11 e Equalize original vêm do [job 825196](resultados_pcad_hype_simd_followup_825196/original_raw.csv), com cinco medições. Zoom de produção, Grayscale e Quantize **sem Grayscale** vêm do [job 825290](resultados_pcad_hype_simd_phase_zoom_825290/protocol.txt): 20 medições para Zoom e dez para as demais. A tabela de [proveniência e medianas](visualizacoes_simd_finais/dados_mapas.csv) identifica cada linha. Flip e rotações não aparecem porque seus laços originais não receberam o pragma. `off/omp` mede o efeito combinado de permitir vetorização e usar os pragmas; `auto/omp` é a comparação apropriada para perguntar o que o pragma acrescentou ao GCC automático. Grayscale foi refatorado antes dessas campanhas, mas não foi reescrito no experimento 825200.

| Função original | `off/omp`, 1 thread | `off/omp`, 20 threads | Leitura |
| --- | ---: | ---: | --- |
| Negative | 1,03× | 1,03× | Efeito pequeno. |
| Adjust_Brightness | 0,99× | 0,99× | Sem ganho. |
| Adjust_Contrast | 1,01× | 1,01× | Efeito pequeno. |
| Equalize_Histogram | 1,00× | 0,99× | Sem ganho no total. |
| Gaussian_11x11 | 1,00× | 0,96× | O pragma no laço de pixels não acelerou a convolução. |
| Grayscale | 1,28× | 1,17× | Job 825290; GCC vetorizou o laço atual; `auto/omp` ≈ 1. |
| Quantize **sem Grayscale** | 1,01× | 0,99× | Job 825290; sem ganho relevante do pragma no tempo isolado. |
| Zoom_In | 1,23× | 1,05× | Job 825290; o antigo salto de 1,33× em 20 threads não se repetiu. |

O problema não é uma dependência matemática entre pixels em Negative, Contrast ou Gaussiana. O pragma estava posicionado antes do laço de **pixels**, cujo corpo ainda continha trabalho por canal ou um ninho inteiro de convolução. No caso de Contrast, o [código de produção](577262-FPI-Relatorio2/image_manipulation.cpp#L901) era:

```cpp
#pragma omp parallel for schedule(runtime)
for (int i = 0; i < img.height; ++i) {
    OMP_SIMD                         // #pragma omp simd apenas em omp-avx2
    for (int j = 0; j < img.width; ++j) {  // pixels: o GCC não vetorizou este laço
        const int index = (i * img.width + j) * 3;
        for (int channel = 0; channel < 3; ++channel) {
            const float value = img.data[index + channel] * contrast_factor;
            img.data[index + channel] =
                static_cast<unsigned char>(std::clamp(static_cast<int>(value), 0, 255));
        }
    }
}
```

O [diagnóstico GCC do próprio job 825196](resultados_pcad_hype_simd_followup_825196/omp-avx2-core-focus.txt) registra `multiple nested loops` no laço de pixels de Contrast (linha 907), de Brightness (1016) e da Gaussiana (523). Ele **não confirma** que esses laços foram vetorizados. Em contraste, confirma vetores de 32 bytes no laço atual de Grayscale (linha 979). O ganho de Grayscale em `off/omp` não é ganho *incremental* do pragma: no mesmo job, `off/auto` ≈ 1,29× e `auto/omp` ≈ 0,99× em uma thread. O caso Zoom In exige análise das suas fases, não a conclusão genérica de que todo pragma funcionou; ver [auditoria dos laços originais](RELATORIO_LOOPS_SIMD_17_OPERACOES.md).

**O Quantize foi vetorizado? Parcialmente.** A [função de produção](577262-FPI-Relatorio2/image_manipulation.cpp#L1072) primeiro chama Grayscale quando necessário, depois procura luminâncias mínima e máxima e, por fim, remapeia cada pixel para um nível. Tanto o [relatório `auto-avx2`](resultados_pcad_hype_simd_followup_825196/auto-avx2-core-focus.txt) quanto o [relatório `omp-avx2`](resultados_pcad_hype_simd_followup_825196/omp-avx2-core-focus.txt) marcam o laço interno da **busca min/max, linha 1079**, como `loop vectorized using 32 byte vectors` (também há versão de 16 bytes). Já o laço de **remapeamento, linha 1104**, aparece como `missed` nos dois relatórios; o pragma está sobre esse laço em `omp-avx2`, mas não fez o GCC vetorizá-lo. A comparação conclusiva para o Quantize é agora a medição **sem Grayscale** do job 825290, na seção 3.

## 2. Segunda abordagem: expor laços longos e independentes

Na campanha **825200**, a aritmética ponto a ponto, os 121 pesos `float` da Gaussiana e a contagem/normalização do histograma foram mantidos. Mudou-se a ordem em que os elementos são percorridos. Cada configuração teve aquecimento, cinco medições e validação exata dos bytes de saída. [Protocolo](resultados_pcad_hype_linear_simd_825200/protocol.txt), [amostras brutas](resultados_pcad_hype_linear_simd_825200/linear_simd_raw.csv) e [resumo](resultados_pcad_hype_linear_simd_825200/linear_simd_summary.csv). O mapa final complementa essas variantes com as medidas mais recentes dos controles, sem confundir o Quantize completo com seu tempo após Grayscale.

![Mapa final da abordagem linearizada, 36 MP, com os controles mais recentes](visualizacoes_simd_finais/02_abordagem_linearizada.svg)

Este mapa mostra `off/auto`, `off/omp` e `auto/omp` **dentro da mesma variante**, em 1 e 20 threads. As três operações de bytes e a Convolução 11×11 por linha vêm do job 825200, assim como **Equalize com remapeamento linear**. O **Equalize original**, Quantize sem Grayscale, Grayscale e o controle Zoom com saída pré-alocada vêm do job 825290. As duas linhas Equalize são implementações distintas, não repetições da mesma medição. Cada razão é calculada dentro do mesmo job e da mesma implementação; **não** se dividem milissegundos de jobs distintos. Os [hashes das fontes](resultados_pcad_hype_simd_phase_zoom_825290/source_sha256.txt) são compatíveis para `image_manipulation.cpp` nas três campanhas, e para `vectorization_benchmark.cpp` entre 825200 e 825290. A [tabela de proveniência](visualizacoes_simd_finais/dados_mapas.csv) registra amostras, tempos e escopo de cada linha.

| Variante medida | `off/auto` 1 t | `auto/omp` 1 t | `off/auto` 20 t | `auto/omp` 20 t |
| --- | ---: | ---: | ---: | ---: |
| Negative, bytes lineares | 3,65× | 1,00× | 1,11× | 1,02× |
| Brightness, bytes lineares | 6,67× | 1,00× | 1,54× | 0,97× |
| Contrast, bytes lineares | 6,11× | 1,00× | 2,74× | 1,00× |
| Equalize original, job 825290 | 1,00× | 1,00× | 1,01× | 0,99× |
| Equalize, remapeamento linear, **total** | 1,00× | 1,08× | 1,02× | 1,03× |
| Convolução 11×11, linha AoS | 4,00× | 1,01× | 4,21× | 1,01× |
| Quantize **sem Grayscale**, job 825290 | 1,02× | 0,98× | 1,01× | 0,99× |
| Grayscale, job 825290 | 1,28× | 1,00× | 1,17× | 1,00× |
| Zoom In, saída pré-alocada, job 825290 | 1,38× | 1,01× | 1,01× | 1,00× |

As razões foram recalculadas das **amostras brutas**, depois arredondadas a duas casas. Não atribuir o ganho `original/candidata` exclusivamente a SIMD: a estrutura do laço também mudou. A [tabela do efeito estrutural](resultados_pcad_hype_simd_phase_zoom_825290/figures_segundo_mapa/efeito_estrutura.csv) compara implementações **dentro do mesmo build** e responde a outra pergunta.

### 2.1 Operações ponto a ponto: Contrast representa Negative e Brightness

No [candidato Contrast](577262-FPI-Relatorio2/vectorization_benchmark.cpp#L213), a linha RGB continua no formato intercalado `RGBRGB…` (AoS). Não há SoA, lookup nem nova fórmula. Sai o laço de três canais por pixel; entra um laço sobre todos os bytes adjacentes da linha:

```cpp
void contrast_linear(Byte* data, int width, int height) {
    #pragma omp parallel for schedule(runtime)
    for (int y = 0; y < height; ++y) {
        Byte* row = data + static_cast<size_t>(y) * width * 3;
        EXP_SIMD  // #pragma omp simd apenas no build omp-avx2
        for (int byte = 0; byte < width * 3; ++byte) {  // LAÇO VETORIZADO
            const float value = row[byte] * 1.5f;
            row[byte] = static_cast<Byte>(
                std::clamp(static_cast<int>(value), 0, 255));
        }
    }
}
```

O laço `y` continua distribuído por OpenMP; o laço `byte` oferece operações independentes sobre posições consecutivas. O [GCC em `auto-avx2`](resultados_pcad_hype_linear_simd_825200/auto-avx2-compiler-focus.txt) registra na linha 218 `loop vectorized using 32 byte vectors` e também uma versão de 16 bytes. As linhas 199 e 208 confirmam o mesmo tipo de laço para Negative e Brightness. O [log `omp-avx2`](resultados_pcad_hype_linear_simd_825200/omp-avx2-compiler-focus.txt) também confirma 32 bytes. As mensagens `missed` para o laço externo ou para uma análise do acesso **não anulam** o `optimized` do laço interno. Vetores de 32 bytes dizem a largura da operação escolhida, não que cada instrução processe 32 multiplicações `float` de uma vez: o GCC ainda precisa converter bytes, fazer a aritmética e limitar a faixa.

Como controle de interpretação, na imagem de 36 MP com uma thread, `original/linear_bytes` em `auto-avx2` é **7,75×** para Negative, **13,16×** para Brightness e **9,10×** para Contrast. Esses números incluem a mudança da estrutura do código; a coluna `off/auto` da tabela principal é a comparação apropriada para perguntar o que a vetorização acrescentou **ao novo laço**. Em 20 threads, os ganhos `off/auto` são menores, coerentes com uma parcela maior do tempo sendo limitada por trânsito de dados, concorrência e custos fixos; este ensaio sozinho não separa essas causas.

### 2.2 Gaussiana 11×11: SIMD ao longo da linha, não dentro do pixel

O [código original](577262-FPI-Relatorio2/image_manipulation.cpp#L520) coloca `OMP_SIMD` no laço de `i`, e cada iteração chama [`apply_11_by_11_convolution_to_pixel`](577262-FPI-Relatorio2/image_manipulation.cpp#L226). Dentro da função, dois laços sobre `k` e `l` realizam 121 contribuições para **um único pixel RGB**, com três acumuladores `float`. O GCC reportou o ninho como obstáculo à vetorização do laço de pixels. Tentar apenas vetorizar os 11 produtos de `l` não é equivalente a processar vários pixels de saída por vetor.

Na [variante controlada por linha](577262-FPI-Relatorio2/vectorization_benchmark.cpp#L520), o kernel continua sendo a convolução **direta** com 121 pesos `float` e layout AoS. Cada thread dispõe de acumuladores temporários para uma linha; para cada peso, percorre bytes de **muitos pixels de saída**:

```cpp
#pragma omp parallel
{
    std::vector<float> sums(static_cast<size_t>(row_bytes)); // privado por thread
    #pragma omp for schedule(runtime)
    for (int y = 0; y < output.height; ++y) {
        std::fill(sums.begin(), sums.end(), 0.0f);
        for (int k = -5; k <= 5; ++k)
            for (int l = -5; l <= 5; ++l) {
                const float weight = GAUSSIAN_KERNEL_11X11[5 + k][5 + l];
                const Byte* source = /* linha de entrada deslocada por k,l */;
                EXP_SIMD
                for (int byte = 0; byte < row_bytes; ++byte) // LAÇO VETORIZADO
                    sums[byte] += weight * source[byte];
            }
        // converter os acumuladores e gravar a linha RGB de saída
    }
}
```

O bloco acima abrevia somente o cálculo do ponteiro e a gravação final; o [trecho integral](577262-FPI-Relatorio2/vectorization_benchmark.cpp#L520) está no código. `k` e `l` percorrem os pesos em ordem, preservando a sequência de soma de cada byte de saída. O [GCC `auto-avx2`](resultados_pcad_hype_linear_simd_825200/auto-avx2-compiler-focus.txt) registra na linha 534 `loop vectorized using 32 byte vectors`; o [GCC `omp-avx2`](resultados_pcad_hype_linear_simd_825200/omp-avx2-compiler-focus.txt) confirma o mesmo na linha 535. A vetorização atravessa **posições da linha** para um peso fixo, não os 11 taps que produzem um pixel. Nenhuma separação horizontal/vertical do filtro foi aplicada.

O controle mais esclarecedor é o resultado **dentro do job 825200**, 36 MP e uma thread:

| Implementação do kernel, saída pré-alocada | `off-avx2` | `auto-avx2` | `omp-avx2` |
| --- | ---: | ---: | ---: |
| Por pixel (`pixel_outer`) | 9,26 s | 9,26 s | 9,28 s |
| Por linha AoS (`row_linear_aos`) | 11,49 s | 2,87 s | 2,84 s |

Sem vetorização automática, a candidata por linha foi **mais lenta**: o buffer de acumuladores e a nova organização têm custo. Com o GCC vetorizando a linha, ela fica **4,00×** mais rápida que sua própria versão `off` e **3,23×** mais rápida que `pixel_outer` no mesmo build `auto`. O pragma adicional representa apenas **1,01×**. Em 20 threads, `row_linear_aos` cai de 666,6 ms (`off`) para 158,3 ms (`auto`) e 156,9 ms (`omp`); as cinco amostras têm [mínimo e máximo no CSV](resultados_pcad_hype_linear_simd_825200/linear_simd_summary.csv). A saída foi validada byte a byte contra `pixel_outer` e contra a função de produção no pré-voo. As duas variantes desse ensaio recebem a saída pré-alocada: não comparar esses segundos diretamente ao tempo da função de produção que aloca seu próprio buffer.

O [job 825196](resultados_pcad_hype_simd_followup_825196/simd_followup_summary.csv) fornece um teste secundário, não uma razão cruzada com o 825200. Nele, `float_tap_products` (produtos de 11 taps por pixel, soma serial preservada) piorou de 9,27 para 11,13 s entre `off` e `omp`, em uma thread. `float_row_aos` repetiu o ganho qualitativo, de 11,50 para 2,62 s. `float_row_soa` também foi rápido, mas **inclui conversões de layout** no `total`; não é evidência isolada da linearização AoS. Isso reforça que **qual dimensão do laço** é vetorizada importa mais que apenas obter alguma instrução vetorial.

Houve também uma tentativa **diretamente no laço mais interno `l`**: [`float_tap_reduction`](577262-FPI-Relatorio2/vectorization_benchmark.cpp#L464) usa `#pragma omp simd reduction(+:sum_r,sum_g,sum_b)`. A redução é necessária porque as 11 iterações atualizam os mesmos acumuladores; um `omp simd` simples declararia independência que não existe. Essa variante ficou **fora do job formal**: a [validação local](README_SIMD_FOLLOWUP.md) encontrou 11 bytes com diferença de um nível de cor, pois a redução vetorial muda a ordem das somas em ponto flutuante. `float_tap_products` preservou a ordem da soma e a saída exata, mas não trouxe ganho. Assim, não se deve dizer que nunca tentamos SIMD nos taps; o que não existe é uma medição formal comparável da redução com tolerância numérica relaxada.

### 2.3 Histograma: o remapeamento fica vetorizável, a contagem não

A função de produção [Equalize_Histogram](577262-FPI-Relatorio2/image_manipulation.cpp#L861) primeiro chama `compute_normalized_cummulative_histogram`; depois remapeia cada pixel por meio de um laço de três canais. O experimento [825200](577262-FPI-Relatorio2/vectorization_benchmark.cpp#L735) chama a **mesma** função de contagem, redução e normalização. Só troca a travessia da fase final:

```cpp
void histogram_remap_linear(Byte* data, int width, int height,
                            const unsigned int bins[256]) {
    #pragma omp parallel for schedule(runtime)
    for (int y = 0; y < height; ++y) {
        Byte* row = data + static_cast<size_t>(y) * width * 3;
        EXP_SIMD
        for (int byte = 0; byte < width * 3; ++byte) // LAÇO VETORIZADO EM omp-avx2
            row[byte] = static_cast<Byte>(bins[row[byte]]);
    }
}
```

O acesso à **imagem** é linear; o acesso aos 256 `bins` continua indexado pelo valor do pixel. Por isso não se deve descrevê-lo como uma simples soma vetorial contígua. No [log `auto-avx2`](resultados_pcad_hype_linear_simd_825200/auto-avx2-compiler-focus.txt), a linha 295 tem `data ref analysis failed` e não apresenta confirmação de vetorização desse laço. No [log `omp-avx2`](resultados_pcad_hype_linear_simd_825200/omp-avx2-compiler-focus.txt), a mesma linha também contém um diagnóstico `missed` de análise, **mas** registra `optimized: loop vectorized using 32 byte vectors` para o laço. Isso confirma uma versão vetorizada; não prova que o lookup se tornou barato.

Em 36 MP e uma thread, o `remap` mediano passa de aproximadamente **58,17 ms** (`auto`) para **47,21 ms** (`omp`), cerca de **1,23×**. Já a fase `count_and_normalize` fica próxima de **90,7 ms** nas três builds. No `total`, a diferença vira **148,93 → 137,99 ms**, ou **1,08×**. Com 20 threads, o ganho total `auto/omp` é cerca de **1,03×**; nesse ponto a dispersão das cinco medições recomenda não alegar um ganho estável de poucos por cento. Não afirmar que o pragma vetorizou a **contagem**: ela contém atualizações indexadas à mesma tabela e uma redução OpenMP, não o laço linear mostrado acima.

## 3. Confirmação complementar: Quantize sem Grayscale e Zoom In

O job **825290** usou `static`, os mesmos três builds Haswell, aquecimento e saída validada byte a byte. As [medidas de fases](resultados_pcad_hype_simd_phase_zoom_825290/phase_summary.csv) têm dez repetições em 36 MP. Para Quantize, a medida principal abaixo é **`production_after_gray`**: a entrada foi convertida para cinza *antes* do cronômetro, e o tempo é o da própria função `quantize_gray` aplicada a essa entrada. Portanto, **Grayscale não entra nesse tempo**. Não se subtraiu uma mediana de outra; as fases `minmax` e `remap` foram medidas separadamente em réplicas validadas, para localizar o custo, e não devem ser somadas como substitutas do tempo de produção. [Protocolo](resultados_pcad_hype_simd_phase_zoom_825290/protocol.txt) e [amostras brutas](resultados_pcad_hype_simd_phase_zoom_825290/phase_raw.csv).

| Quantize, 36 MP | `off-avx2` | `auto-avx2` | `omp-avx2` | Leitura |
| --- | ---: | ---: | ---: | --- |
| Sem Grayscale, 1 thread | 403,63 ms | 394,79 ms | 401,29 ms | `off/auto` = 1,02×; `off/omp` = 1,01×. |
| Sem Grayscale, 20 threads | 24,96 ms | 24,76 ms | 25,13 ms | Os três builds ficam praticamente iguais. |
| Busca min/max, 1 thread | 23,97 ms | 15,02 ms | 15,16 ms | Vetorização automática ajuda esta fase. |
| Remapeamento, 1 thread | 379,77 ms | 379,88 ms | 386,10 ms | O pragma não acelerou a fase dominante. |

Assim, **a conclusão para Quantize sem Grayscale é ausência de ganho relevante do SIMD explícito no tempo da operação**. O GCC vetorizou min/max, mas o remapeamento, que ocupa a maior parte do tempo, não recebeu vetorização confirmada; com uma thread, `omp` chega a ser cerca de 1,6% mais lento que `auto` no remapeamento isolado. O ganho de aproximadamente 4% do `off/omp` para o **Quantize completo** no job 825196 não deve ser usado como evidência de ganho do remapeamento: aquele tempo também incluía Grayscale. A [figura das fases](resultados_pcad_hype_simd_phase_zoom_825290/figures/quantize_equalize_fases.svg) serve apenas como apoio; para a conclusão principal, usar a linha “Sem Grayscale” da tabela.

Para **Zoom In de produção**, o job 825290 repetiu cada ponto **20 vezes**, incluindo 17–19 threads, e alternou a ordem dos pontos entre rodadas. A razão `off/auto` caiu progressivamente; `auto/omp` permaneceu perto de 1. São tempos da função completa, **com sua alocação interna**, calculados de [zoom_production_summary.csv](resultados_pcad_hype_simd_phase_zoom_825290/zoom_production_summary.csv) e verificáveis nas [amostras brutas](resultados_pcad_hype_simd_phase_zoom_825290/zoom_production_raw.csv):

| Threads | `off-avx2` | `auto-avx2` | `omp-avx2` | `off/auto` |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 349,96 ms | 285,91 ms | 284,74 ms | 1,22× |
| 12 | 42,54 ms | 37,10 ms | 36,92 ms | 1,15× |
| 16 | 31,66 ms | 29,16 ms | 28,94 ms | 1,09× |
| 19 | 28,04 ms | 26,29 ms | 26,18 ms | 1,07× |
| 20 | 27,77 ms | 26,34 ms | 26,35 ms | 1,05× |

O **1,33× em 20 threads** do job 825196 não se reproduziu: com mais repetições, o ganho mediano é **1,05×**, e os pontos 17–20 seguem a queda gradual, sem salto isolado. Isso não identifica uma causa única para a anomalia antiga; indica que ela não é um resultado estável para apresentar. Ver [curva por threads](resultados_pcad_hype_simd_phase_zoom_825290/figures/zoom_36mp_builds_por_threads.svg) e [dispersão](resultados_pcad_hype_simd_phase_zoom_825290/figures/zoom_36mp_dispersao.svg).

O controle de Zoom In com **saída pré-alocada** é uma medição distinta: em 36 MP, `off/auto` = **1,38×** com 1 thread, mas **1,01×** com 20 threads; `auto/omp` ≈ **1,00×** nos dois casos. Ele preenche a linha Zoom do segundo mapa e reforça a conclusão de que o ganho vem da vetorização permitida ao compilador, não principalmente do pragma. Como o escopo exclui a alocação interna, **não comparar seus milissegundos diretamente com os da tabela de produção**.

## Conclusões que os dados permitem

1. Nas funções de produção medidas pelo 825196, permitir vetorização pouco mudou a maioria dos tempos; **Grayscale e Zoom In são exceções visíveis**. A diferença `auto/omp` próxima de 1 em ambos indica que seus ganhos não vêm principalmente de acrescentar o pragma. O job 825290 confirma o ganho de Zoom com uma thread e mostra que, em 20 threads, ele é pequeno e decrescente, não o salto de 1,33× visto antes. Os diagnósticos GCC apontam o ninho de laços como obstáculo para Contrast, Brightness e Gaussiana. Isso **não** quer dizer que SIMD seja inútil para essas operações.
2. Nos candidatos ponto a ponto e na Gaussiana por linha, o GCC vetorizou laços contíguos **mesmo sem pragma**, e as medições `off/auto` mostram ganhos claros. O ganho do programa inteiro ao trocar original por candidata também contém o efeito da estrutura do código.
3. O histograma mostra a exceção instrutiva: o pragma confirmou vetorização do **remapeamento** que o GCC automático não confirmou, mas a fase de contagem limita o ganho do tempo total.
4. O Quantize **sem Grayscale** praticamente não se beneficia do pragma no tempo de produção: min/max vetoriza automaticamente, mas o remapeamento dominante não foi confirmado como vetorizado e não acelerou. O ganho do Quantize completo misturava sua conversão inicial para cinza.
5. Os relatórios do GCC identificam a escolha do laço e a largura de 32 bytes; não fornecem, sozinhos, a contagem dinâmica de instruções ou a causa microarquitetural exata de cada diferença. O protocolo dos jobs não foi um estudo de montagem/VTune isolando cada instrução.
6. A campanha controlada não reexecutou Gaussian_3x3, 5x5, 7x7 e 9x9. O resultado de 11×11 não deve ser apresentado como medição de todos os tamanhos.

## Três exemplos para os slides de SIMD

A apresentação completa dura dez minutos, dos quais **até cinco** ficam para esta parte; a comparação entre `static` e `dynamic` ocupa o restante. Três trechos de código bastam. O relatório acima fica como material de apoio, não como roteiro para projetar todas as tabelas.

| Tempo sugerido | Exibir | Frase central |
| --- | --- | --- |
| 0:35 | Problema e builds `off/auto/omp` | “SIMD é uma hipótese de paralelismo dentro do núcleo; vamos observar o que o GCC realmente gerou.” |
| 0:55 | [Primeiro mapa final, abordagem original](visualizacoes_simd_finais/01_abordagem_original.svg) | “A maioria pouco mudou; Grayscale e Zoom ganharam com a vetorização. O Zoom em 20 threads agora usa a confirmação de 1,05×; Quantize aparece sem Grayscale.” |
| 0:55 | **Contrast** original → laço de bytes, com linha 218 do log GCC | “O novo laço expõe muitos bytes independentes e contíguos; o GCC usa vetores de 32 bytes automaticamente.” |
| 1:05 | **Gaussiana** por pixel → por linha, com a tabela 9,26/11,49/2,87 s | “Vetorizar 11 coeficientes de um pixel não é o mesmo que vetorizar muitos pixels; a segunda organização permitiu o ganho.” |
| 0:45 | **Histograma**: código do remapeamento e fases | “O remapeamento vetorizou com pragma, mas a contagem domina parte do tempo total.” |
| 0:35 | [Segundo mapa final, abordagem linearizada](visualizacoes_simd_finais/02_abordagem_linearizada.svg) e passagem | “Código favorável + decisão do compilador + medição: os três são necessários para interpretar SIMD.” |

Total: aproximadamente **4:50**, com pequena margem. Para o slide, mostre apenas as linhas marcadas `LAÇO VETORIZADO` e seus equivalentes antigos; deixe os logs completos, a análise de Quantize **sem Grayscale** e o [mapa de 12 MP](resultados_pcad_hype_simd_phase_zoom_825290/figures_segundo_mapa/simd_mesma_variante_12mp.svg) para perguntas. Não chamar a Gaussiana por linha de “SoA” ou “separável”: ela é **AoS e convolução direta**.
