# Auditoria dos laços SIMD das 17 operações regulares

## Escopo e como ler

Esta auditoria usa **somente a revisão atual** de
[`image_manipulation.cpp`](577262-FPI-Relatorio2/image_manipulation.cpp), a
lista de operações do [`benchmark_runner.cpp`](577262-FPI-Relatorio2/benchmark_runner.cpp#L91)
e o diagnóstico de `g++ 12.2.0` do job **824453**:
[`omp-avx2/image_manipulation.opt-info.txt`](resultados_pcad_hype_compiler_evidence_824453/omp-avx2/image_manipulation.opt-info.txt).
O job compilou com `-O3 -g -fopenmp -ffp-contract=off -march=haswell
-DOMP_EXPLICIT_SIMD=1 -fopt-info-vec-all` (ver
[`pcad_hype_compiler_evidence.sbatch`](scripts/pcad_hype_compiler_evidence.sbatch#L30)).
As operações foram também executadas, dez vezes por combinação de 1/20
threads e build, no job 824454. Este documento **não** avalia a implementação
SoA do benchmark de layout nem as bibliotecas `stb_image`/`libc` usadas para
entrada, cópias e alocação: trata dos laços da operação em si.

Legenda:

- **V32**: o GCC informa `optimized: loop vectorized using 32 byte vectors`
  para esse laço. Quando aparece também V16, é usualmente um caminho para
  resto/alinhamento; não se somam as larguras.
- **N**: o GCC informa `missed: couldn't vectorize loop`/`not vectorized`
  para esse laço, ou `vectorized 0 loops` na função correspondente.
- **ND**: o `for` existe no fonte, mas o relatório não o identifica como um
  laço vetorizado independente. Pode ter sido desenrolado, incorporado ou
  transformado; não é prova de que cada instrução da região seja escalar.
- **P**: laço OpenMP distribuído entre *threads*, mas **não** vetorizado como
  laço SIMD. Paralelismo entre threads e vetorização dentro de cada thread
  são questões distintas.
- `OMP_SIMD` é um pragma solicitado, não uma confirmação. `Simd_Eligible` no
  CSV é metadado do experimento, não resultado do compilador. Mensagens
  `basic block part vectorized` (SLP), `v*` em instrução escalar VEX e
  vetorização de um laço auxiliar não significam que a varredura de pixels
  foi vetorizada. O relatório descreve código gerado, não quantas instruções
  vetoriais foram executadas em tempo de execução.

Forma recorrente no código:

```cpp
#pragma omp parallel for schedule(runtime)
for (int y = 0; y < height; ++y) { // linhas: P
    OMP_SIMD
    for (int x = 0; x < width; ++x) { // pixels: verificar separadamente
        /* operação */
    }
}
```

## 1. Grayscale

Fonte: [`apply_gray_scale_buffer`, linhas 975–988](577262-FPI-Relatorio2/image_manipulation.cpp#L975).

```cpp
for (int j = 0; j < height; j++) {      // P, N para SIMD
    OMP_SIMD
    for (int i = 0; i < width; i++) {   // V32 + V16
        /* lê RGB, calcula luminância, escreve o mesmo cinza em R/G/B */
    }
}
```

O laço das linhas **977** não foi vetorizado (`multiple nested loops`);
divide linhas entre threads. O de pixels da linha **979** foi **V32 + V16**.
Assim, o RGB intercalado exigiu reorganização dos bytes, mas não impediu
SIMD nessa versão. Diagnóstico: `:977`, `:979`.

## 2. Flip_Horizontal

Fontes: [`flip_horizontal`, linha 1024](577262-FPI-Relatorio2/image_manipulation.cpp#L1024)
e [`flip_horizontal_row`, linha 723](577262-FPI-Relatorio2/image_manipulation.cpp#L723).

```cpp
for (int j = 0; j < img.height; j++)  // P, N para SIMD
    flip_horizontal_row(img, j);
// na função chamada:
for (int i = 0; i < img.width / 2; i++) // N
    /* troca o pixel i com width-1-i por três memcpy de 3 bytes */;
```

O laço de linhas **1026** distribui trabalho; o de pares simétricos **725**
faz as trocas. Ambos receberam `missed`. Não há `OMP_SIMD` aqui. A variante
instrumentada `flip_horizontal_profiled` tem outra distribuição de linhas
(**1040**) e chama **a mesma** função por linha; ela não é o caminho do
benchmark regular.

## 3. Adjust_Brightness

Fonte: [`adjust_brightness`, linhas 1010–1022](577262-FPI-Relatorio2/image_manipulation.cpp#L1010).

```cpp
for (int i = 0; i < img.height; i++) {   // P, N
    OMP_SIMD
    for (int j = 0; j < img.width; j++) { // N
        for (int channel = 0; channel < 3; channel++) // ND
            /* soma brilho e limita a [0,255] */;
    }
}
```

Linhas **1014** e **1016**: `missed`; o primeiro acusa controle no laço, o
segundo laços aninhados/latch. O laço de três canais **1018** não tem
confirmação de vetorização independente; não se deve inferir que ele tenha
ficado literalmente como um laço escalar após otimização.

## 4. Flip_Vertical

Fonte: [`flip_vertical`, linhas 1052–1071](577262-FPI-Relatorio2/image_manipulation.cpp#L1052).

```cpp
#pragma omp for schedule(runtime)
for (int j = 0; j < height / 2; j++) { // P, N
    /* troca linhas opostas com três memcpy de width*3 bytes */
}
```

O laço **1062** recebeu `missed`. A possível cópia vetorial *dentro* de
`memcpy` é outra questão; o relatório não comprova SIMD no laço de pares de
linhas. Não há `OMP_SIMD`.

## 5. Quantize

Fonte: [`quantize_gray`, linhas 1090–1114](577262-FPI-Relatorio2/image_manipulation.cpp#L1090).
Executa três etapas; não é apenas o `for` final:

| Etapa/laço | Papel | Diagnóstico |
| --- | --- | --- |
| Grayscale, linhas **977/979**, se a entrada ainda for RGB | Converte para cinza | **P/N** nas linhas; **V32 + V16** nos pixels, como na seção 1 |
| Min/max, linhas **1078/1079** | Busca extremos da luminância com reduções OpenMP | **P/N** nas linhas; **V32 + V16** no laço interno de pixels |
| Quantização, linhas **1102/1104** | Calcula faixa e novo valor com `round`, grava três canais | **P/N** nas linhas; **N** nos pixels apesar de `OMP_SIMD` |

Código decisivo:

```cpp
for (int j = 0; j < height; j++) {        // P, N
    for (int i = 0; i < width; i++) {     // V32 + V16: min/max
        /* reduction(min:local_min), reduction(max:local_max) */
    }
}
for (int j = 0; j < img.height; j++) {    // P, N
    OMP_SIMD
    for (int i = 0; i < img.width; i++) { // N: quantização final
        /* calcula bin, round, grava RGB */
    }
}
```

Portanto, dizer apenas “Quantize foi vetorizado” seria enganoso: a redução
min/max (e o Grayscale chamado inicialmente) foi vetorizada; o laço final de
quantização não. Há um caminho de retorno antecipado se `num_levels <= levels`.

## 6. Adjust_Contrast

Fonte: [`adjust_contrast`, linhas 901–916](577262-FPI-Relatorio2/image_manipulation.cpp#L901).

| Laço | Papel | Diagnóstico |
| --- | --- | --- |
| Linhas **905** | Distribui linhas | **P/N**, `control flow in loop` |
| Pixels **907** (`OMP_SIMD`) | Aplica fator de contraste | **N**, `multiple nested loops`/`latch block not empty` |
| Canais **909** | Multiplica e limita os três componentes | **ND**, sem laço vetorizado reportado |

O pragma está no laço de pixels, mas o relatório informa `vectorized 0 loops`
na região OpenMP correspondente.

## 7. Negative

Fonte: [`apply_negative`, linhas 888–899](577262-FPI-Relatorio2/image_manipulation.cpp#L888).

```cpp
for (int i = 0; i < img.height; i++) {   // P/N
    OMP_SIMD
    for (int j = 0; j < img.width; j++) { // N
        for (int channel = 0; channel < 3; channel++) // ND
            img.data[index + channel] = 255 - img.data[index + channel];
    }
}
```

Linhas **890** e **892**: `missed` (`control flow`, `multiple nested loops`,
`latch block not empty`). O laço curto de canais **894** não tem confirmação
de vetorização independente. Portanto, a simplicidade aritmética de
`255 - valor` não prova que **o laço por pixels** foi vetorizado.

## 8. Equalize_Histogram

Fontes: [`equalize_histogram`, linha 861](577262-FPI-Relatorio2/image_manipulation.cpp#L861),
[`compute_normalized_cummulative_histogram`, linha 876](577262-FPI-Relatorio2/image_manipulation.cpp#L876),
[`compute_histogram`, linha 918](577262-FPI-Relatorio2/image_manipulation.cpp#L918).
Para uma imagem RGB recém-carregada, o caminho executado é:

| Etapa/laço | Papel | Diagnóstico |
| --- | --- | --- |
| Inicialização **919** | Zera 256 contadores | Convertida pelo GCC em `memset`; não há laço de pixels vetorizado aqui |
| Histograma RGB **928/929** | Conta cada pixel por luminância em histograma com `reduction(+:hist[:256])` | **P/N** nas linhas; **N** nos pixels (`multiple nested loops`, acesso indexado/possível alias) |
| Redução gerada na linha do pragma **927** | Combina os 256 contadores privados das threads | **V32** reportado; **não é** a varredura RGB da linha 929 |
| Prefixo **880** | Soma acumulada `hist[i] += hist[i-1]` | **N**, dependência entre iterações |
| Normalização **883** | Escala 256 contadores e arredonda | **N**, diagnóstico aponta tipo/cálculo `float` não suportado nessa forma |
| Mapeamento **865/867/869** | Troca cada canal RGB pelo valor na tabela acumulada | **P/N** nas linhas; **N** nos pixels; canais **ND** |

Há também um caminho compilado para imagem previamente cinza (**943/944**)
e redução gerada na linha **942**; ele **não é o caminho RGB inicial** desta
operação no benchmark. Os dois avisos `optimized` em **927** e **942** são
justamente o exemplo de por que não se deve rotular toda a equalização como
“vetorizada”.

## 9. Zoom_In

Fonte: [`zoom_copy_source_pixels`, linha 685](577262-FPI-Relatorio2/image_manipulation.cpp#L685),
[`zoom_interpolate_horizontal`, linha 697](577262-FPI-Relatorio2/image_manipulation.cpp#L697),
[`zoom_interpolate_vertical`, linha 710](577262-FPI-Relatorio2/image_manipulation.cpp#L710).

| Fase/laços | Papel | Diagnóstico |
| --- | --- | --- |
| Cópia **687/689** | Distribui linhas; coloca pixels originais nas coordenadas pares ampliadas | **P/N** nas linhas; **N** nos pixels (`latch block not empty`), apesar de `OMP_SIMD` |
| Horizontal **699/701** | Distribui linhas pares; interpola colunas ímpares a partir dos vizinhos na mesma linha | **P/N** nas linhas; **N** no laço de pixels, apesar de `OMP_SIMD` |
| Vertical **712/714** | Distribui linhas ímpares; interpola cada pixel a partir das linhas vizinhas | **P/N** nas linhas; **V32 + V16** nos pixels |

Trecho representativo da última fase:

```cpp
for (int j = 1; j < new_height; j += 2) { // P/N
    OMP_SIMD
    for (int i = 0; i < new_width; i++) { // V32 + V16
        destination[index] = (destination[index - new_width*3]
                            + destination[index + new_width*3]) / 2;
        /* idem para os outros dois canais */
    }
}
```

O “Zoom vetorizado” significa **a fase vertical vetorizada**, não as três
fases. O diagnóstico mostra também tentativas recusadas em outros níveis do
ninho; elas não anulam o `optimized` explícito de **714**.

## 10. Zoom_Out

Fontes: [`zoom_out_image`, linhas 785–807](577262-FPI-Relatorio2/image_manipulation.cpp#L785)
e [`compute_rgb_avg_on_rectangle`, linhas 809–826](577262-FPI-Relatorio2/image_manipulation.cpp#L809).

| Laço | Papel | Diagnóstico |
| --- | --- | --- |
| Linhas de saída **791** | Distribui novas linhas | **P/N**, ninho com laços internos |
| Pixels de saída **795** | Calcula um retângulo médio por pixel novo | **N**, ninho e chamada ao auxiliar |
| Linhas do retângulo **812** | Percorre linhas da área original, com `break` na borda | **N/ND**; função auxiliar informa `vectorized 0 loops` |
| Pixels do retângulo **814** | Acumula R/G/B e conta pixels, com `break` na borda | **N/ND**, sem laço vetorizado reportado |

Não há `OMP_SIMD`; há paralelismo entre linhas de saída.

## 11. Rotate_CW

Fonte: [`rotate_90_degrees_clockwise`, linhas 640–657](577262-FPI-Relatorio2/image_manipulation.cpp#L640).

| Laço | Papel | Diagnóstico |
| --- | --- | --- |
| Linhas originais **646** | Distribui linhas entre threads | **P/N** |
| Colunas originais **647** | Lê RGB, calcula destino rotacionado e copia 3 bytes | **N**, `multiple nested loops`/iteração não computável na forma transformada |

O destino salta entre linhas da nova imagem à medida que `i` avança. Não há
`OMP_SIMD`.

## 12. Rotate_CCW

Fonte: [`rotate_90_degrees_counterclockwise`, linhas 659–676](577262-FPI-Relatorio2/image_manipulation.cpp#L659).

| Laço | Papel | Diagnóstico |
| --- | --- | --- |
| Linhas originais **665** | Distribui linhas | **P/N** |
| Colunas originais **666** | Lê RGB, calcula destino anti-horário e copia 3 bytes | **N**, `multiple nested loops`/iteração não computável na forma transformada |

Não há `OMP_SIMD`. As duas rotações têm fórmulas diferentes de destino, mas
o relatório não confirma vetorização de nenhum dos dois laços por pixels.

## 13–17. Gaussian_3x3, 5x5, 7x7, 9x9 e 11x11 (AoS direto)

O [`benchmark_runner.cpp`, linhas 66–80](577262-FPI-Relatorio2/benchmark_runner.cpp#L66)
chama `apply_N_by_N_convolution` com `single_channel=false` e
`clamp_offset=false`: **é o caminho RGB direto**, não o SoA separável. O
mesmo padrão de quatro laços é repetido em cinco especializações:

```cpp
#pragma omp parallel for schedule(runtime)
for (int j = raio; j < img.height - raio; ++j) { // linhas: P/N
    OMP_SIMD
    for (int i = raio; i < img.width - raio; ++i) { // pixels: N
        for (int k = -raio; k <= raio; ++k) {   // taps verticais: N/ND
            for (int l = -raio; l <= raio; ++l) { // taps horizontais: N/ND
                /* acumula pesos em sum_r, sum_g, sum_b */
            }
        }
    }
}
```

Os `for(k)`/`for(l)` estão no auxiliar `apply_N_by_N_convolution_to_pixel`,
que o GCC pode incorporar/desenrolar. A tabela identifica **todos os laços
escritos** na trajetória RGB de cada tamanho:

| Operação | Linhas P/N | Pixels N, com `OMP_SIMD` | Taps `k`/`l` no RGB | Resultado do vetorizador |
| --- | ---: | ---: | ---: | --- |
| **Gaussian_3x3** | [433](577262-FPI-Relatorio2/image_manipulation.cpp#L433) | [435](577262-FPI-Relatorio2/image_manipulation.cpp#L435) | [118/119](577262-FPI-Relatorio2/image_manipulation.cpp#L118) | `vectorized 0 loops`; pixel: `multiple nested loops`/controle |
| **Gaussian_5x5** | [455](577262-FPI-Relatorio2/image_manipulation.cpp#L455) | [457](577262-FPI-Relatorio2/image_manipulation.cpp#L457) | [149/150](577262-FPI-Relatorio2/image_manipulation.cpp#L149) | `vectorized 0 loops`; pixel: `multiple nested loops`/controle; `l` recebe `missed` |
| **Gaussian_7x7** | [477](577262-FPI-Relatorio2/image_manipulation.cpp#L477) | [479](577262-FPI-Relatorio2/image_manipulation.cpp#L479) | [180/181](577262-FPI-Relatorio2/image_manipulation.cpp#L180) | `vectorized 0 loops`; ninho de laços; `k`/`l` recebem `missed` em variantes incorporadas |
| **Gaussian_9x9** | [499](577262-FPI-Relatorio2/image_manipulation.cpp#L499) | [501](577262-FPI-Relatorio2/image_manipulation.cpp#L501) | [211/212](577262-FPI-Relatorio2/image_manipulation.cpp#L211) | `vectorized 0 loops`; ninho de laços; taps sem laço SIMD confirmado |
| **Gaussian_11x11** | [521](577262-FPI-Relatorio2/image_manipulation.cpp#L521) | [523](577262-FPI-Relatorio2/image_manipulation.cpp#L523) | [242/243](577262-FPI-Relatorio2/image_manipulation.cpp#L242) | `vectorized 0 loops`; ninho de laços; taps com `missed`/acesso complicado |

Existe, em cada auxiliar, outro par `k`/`l` para `single_channel=true`
(linhas **107/108**, **138/139**, **169/170**, **200/201**, **231/232**).
Ele é compilado, mas **não executado** pelas cinco operações Gaussian deste
benchmark. As rotinas de borda (`apply_gaussian_*_to_border_pixel`) também
não são chamadas por essas cinco operações: elas geram uma imagem menor,
percorrendo apenas os centros onde o kernel inteiro cabe.

“Não vetorizou o laço de pixels” não significa que o compilador não possa
emitir uma instrução vetorial isolada por SLP ou desenrolar os taps. O ponto
medido aqui é que **nenhum dos cinco laços por pixel recebeu a vetorização
SIMD pedida pelo pragma** no build analisado.

## Balanço

Entre os laços **por pixels** das 17 operações, o relatório confirma V32 em
**Grayscale**, **interpolação vertical do Zoom_In** e **busca min/max de
Quantize**. Em **Equalize_Histogram** há ainda V32 em um laço *gerado* para
combinar os bins da redução OpenMP, **não** na leitura de pixels. Os demais
laços por pixel têm diagnóstico de recusa ou não têm confirmação positiva.
Isso explica por que “compilado com AVX2” não equivale a “todas as 17
operações foram vetorizadas”.

Para atribuir custo ou ganho a cada laço, o próximo passo é correlacionar o
diagnóstico com desassemblagem **da função específica** e medições por fase;
o diagnóstico de compilação, sozinho, não mede tempo de execução de laços.
