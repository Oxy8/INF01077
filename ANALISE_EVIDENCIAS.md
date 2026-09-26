# Respostas fundamentadas às perguntas de desempenho

Este documento responde às nove perguntas com uma separação deliberada entre
**evidência medida**, **explicação sustentada** e **inferência que ainda precisa
de experimento**. Ele usa as campanhas finais listadas em
[`RESULTADOS.md`](RESULTADOS.md), incluindo as coletas complementares 823586
e 824167--824170.

**Atualização após os jobs 824453 e 824454:** a recompilação e dez novas
medições corrigem a conclusão antiga sobre Grayscale. A implementação atual
ganha 1,277× com AVX2 em uma thread e 1,159× em 20 threads; o GCC confirma
vetorização do loop por pixel. Consulte
[`ANALISE_SIMD_824453_824454.md`](ANALISE_SIMD_824453_824454.md) para a
comparação completa. Os números de 822851 abaixo permanecem como registro
histórico da versão anterior do código.

## Convenções e rastreabilidade

- `off-avx2`: vetorização automática desativada com `-fno-tree-vectorize`.
- `omp-avx2`: `#pragma omp simd` explícito e `-march=haswell`, portanto AVX2
  está disponível ao compilador. O pragma é definido em
  `image_manipulation.cpp:27-30`.
- Os tempos abaixo são medianas, acompanhadas de mínimo--máximo nos CSVs. A
  campanha regular e a de layout têm cinco repetições; Zoom diagnóstico tem
  dez; a confirmação de schedules tem dez; o Flip diagnóstico tem doze.
- Saídas foram validadas por hash onde os kernels têm resultado idêntico. O
  diagnóstico Zoom/Flip possui as referências em
  `resultados_pcad_hype_diagnostico_zoom_flip_compilador_823585/reference_hashes.csv`;
  a campanha de layout valida AoS e SoA ingênuo por hash e permite erro máximo
  de 1 nível no separável, pela mudança controlada de ordem de soma
  (`layout_benchmark.cpp:543-546`).

As figuras mencionadas são SVGs locais. Por exemplo,
`visualizacoes_pcad_hype_final_diagnosticos/figures/02_zoom_speedup_avx2.svg`.
As tabelas citadas estão no subdiretório `tables/` da mesma visualização ou no
diretório de resultados explicitamente indicado.

---

## 1. Por que o Zoom In, com uma thread, beneficia-se tanto de SIMD/AVX2?

### Premissa da pergunta

Ela vem da campanha regular: em `6000x6000.png`, `static`, uma thread, o Zoom
passou de **349,38 ms** (`off-avx2`, intervalo 348,17--350,07) para
**283,49 ms** (`omp-avx2`, 270,94--285,24): **1,23×**. Veja
`01_simd_ganho_por_operacao.svg` em
`visualizacoes_pcad_hype_final_benchmark_principal/figures/` e as linhas
correspondentes de `benchmark_summary.csv` em 822851.

### Evidência de código

O Zoom é feito em três fases, todas com paralelismo por linha e `OMP_SIMD` no
laço interno:

```cpp
// image_manipulation.cpp:710-720
#pragma omp parallel for schedule(runtime)
for (int j = 1; j < new_height; j += 2) {
    OMP_SIMD
    for (int i = 0; i < new_width; i++) {
        int index = (j * new_width + i) * 3;
        destination[index] = (destination[index - new_width * 3]
                            + destination[index + new_width * 3]) / 2;
        // repete para G e B
    }
}
```

Embora essa seja a fase chamada de “vertical”, os *lanes* SIMD avançam em
`i`: processam pixels adjacentes **horizontalmente** em cada uma das duas
linhas de entrada. As linhas acima e abaixo são distantes entre si, mas cada
carga dentro de uma linha é contígua entre os lanes. AVX2 pode, portanto,
operar sobre vários pixels da linha por instrução.

### Evidência medida por fase

O diagnóstico de dez repetições isola cópia, interpolação horizontal e
vertical em `zoom_phases_summary.csv`, e é visualizado em:

- `01_zoom_escalabilidade_total.svg`;
- `03_zoom_fases_sem_avx2.svg`;
- `04_zoom_fases_com_avx2.svg`.

Para uma thread:

| Fase | `off-avx2` | `omp-avx2` | Razão off/AVX2 |
| --- | ---: | ---: | ---: |
| Cópia dos pixels originais | 179,99 ms | 179,90 ms | 1,00× |
| Interpolação horizontal | 58,11 ms | 58,36 ms | 1,00× |
| Interpolação vertical | 110,95 ms | 47,16 ms | **2,35×** |
| Total | 349,06 ms | 285,57 ms | **1,22×** |

Portanto, o ganho não vem de “todo o Zoom”: vem quase inteiramente da
interpolação vertical. Ela produz aproximadamente o dobro de pixels da fase
horizontal: a horizontal só preenche lacunas nas linhas originais; a vertical
preenche todas as colunas das linhas intermediárias. Sem SIMD, 110,95 ms
contra 58,11 ms é aproximadamente essa proporção de trabalho. Com AVX2, a
fase vertical passa a 47,16 ms, abaixo da horizontal.

### Conclusão e limite da evidência

Há evidência forte de que AVX2 acelera a fase vertical, onde o laço interno
tem acessos lineares em `i` e trabalho aritmético simples. O job 823585 não
trouxe relatórios textuais utilizáveis, mas o job **824453** corrigiu essa
lacuna: o GCC reporta vetorização de 32 bytes no loop vertical, e o assembly
da função contém cargas, somas e stores vetoriais com registradores `ymm`.
O relatório não mostra vetorização equivalente da cópia e da interpolação
horizontal.

---

## 2. Por que outras operações não se beneficiam de SIMD?

### Premissa da pergunta

O gráfico `01_simd_ganho_por_operacao.svg` mostra Zoom como o maior ganho
geométrico agregado (**1,119×** em 42 comparações), enquanto Grayscale é
**0,966×**, Adjust Brightness **0,968×**, e muitas outras operações ficam
próximas de 1×. A tabela é
`visualizacoes_pcad_hype_final_benchmark_principal/tables/simd_por_operacao.csv`.

Na implementação usada em 822851, o recorte Grayscale na imagem de 36 MP foi:

| Operação/configuração | `off-avx2` | `omp-avx2` | Resultado |
| --- | ---: | ---: | --- |
| Grayscale, 1 thread | 140,16 ms | 139,02 ms | 1,008× |
| Grayscale, 20 threads | 9,747 ms | 9,747 ms | 1,000× |
| Negative, 1 thread | 105,23 ms | 101,98 ms | 1,032× |

Essas linhas são de `benchmark_summary.csv` da campanha 822851; o gráfico de
contexto é `02_simd_matriz_36mp_static.svg`.

### Evidência de código e explicação

Grayscale trabalha sobre RGB intercalado:

```cpp
// estrutura do laço atual em image_manipulation.cpp:975-987
for (int i = 0; i < width; i++) {
    int index = (j * width + i) * 3;
    unsigned char r = data[index];
    unsigned char g = data[index + 1];
    unsigned char b = data[index + 2];
    unsigned char gray = (unsigned char)(0.299*r + 0.587*g + 0.114*b);
    data[index] = data[index + 1] = data[index + 2] = gray;
}
```

Há independência entre pixels. Um pixel ocupa três bytes e exige três cargas,
conversões/cálculo em ponto flutuante e três stores. O agrupamento de RGB em
vetores exige embaralhamento, mas isso não impediu um ganho na implementação
atual: o assembly de 824453 mostra `vpshufb`/`vpermq` e o loop por pixel
vetorizado em 32 bytes. No job 824454, as medianas foram **78,044/61,115 ms
(1,277×)** em uma thread e **6,165/5,319 ms (1,159×)** em 20.

Entre as campanhas, o commit `cdace49` extraiu o corpo do Grayscale para
`apply_gray_scale_buffer(unsigned char*, int, int)`. O relatório otimizado de
822851 não registra vetorização do loop por pixel; o de 824453 registra o
loop vetorizado. Os hashes de saída do Grayscale para 36 MP
coincidem entre as campanhas. Essa mudança de código/compilação é uma
explicação plausível para a mudança de desempenho, mas não foi isolada num
teste A/B de revisões no mesmo job.

O VTune da versão anterior mediu Grayscale AVX2 com `Memory Bound = 30,2%`,
`Cache Bound = 11,6%` e alta banda de DRAM durante 35,3% do tempo. Isso é
evidência de pressão de memória naquele perfil, mas não prova que o código
atual deixou de ganhar com SIMD. Veja
`02_hpc_dram_bandwidth.svg` e a tabela
`visualizacoes_pcad_hype_final_experimentos_complementares/tables/hpc_metricas.csv`.

Em contraste, o Zoom possui uma fase com cálculo de média simples que o
vetorizador explorou eficazmente. A horizontal do próprio Zoom ilustra que
nem todo laço com `omp simd` recebe ganho: ela avança `i += 2`
(`image_manipulation.cpp:697-708`), logo lê e grava pixels alternados, com
salto de 6 bytes por canal em RGB. Isso cria stores estriados e maior custo de
organização de dados para AVX2, e mediu praticamente 1,00× na Tabela da
pergunta 1.

### Conclusão e limite

Não existe uma causa única para as demais operações. Em 824453, o GCC
confirma vetorização do Grayscale e da fase vertical do Zoom, mas não do
loop principal de Negative, Brightness ou das Gaussianas diretas. Um pragma
`omp simd` no fonte não basta para concluir que houve vetorização útil do
loop. O job 824453 fornece a coleta de compilação que faltava em 823585. O
[job 824542](ANALISE_MEMORIA_824542.md) acrescenta contadores de cache da
implementação atual, mas os das operações regulares incluem o processo
inteiro. Eles ainda não isolam banda DRAM nem o kernel de cada operação.

---

## 3. Por que, com 20 threads, o Zoom quase não beneficia de SIMD? Por que o ganho cai ao aumentar threads?

### Premissa e evidência medida

`02_zoom_speedup_avx2.svg` mostra a razão `off-avx2 / omp-avx2` caindo de
**1,222×** em uma thread para **1,039×** em 20 threads:

| Threads | 1 | 2 | 4 | 8 | 12 | 16 | 20 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Speedup AVX2 do Zoom | 1,222× | 1,226× | 1,189× | 1,067× | 1,042× | 1,062× | 1,039× |

Os dados são `tables/zoom_escalabilidade.csv` do painel diagnóstico. A
tendência não é perfeitamente monótona entre 12 e 16, mas a queda global é
inequívoca.

### Explicação sustentada

Com uma thread, a parte vetorizável da interpolação vertical domina um trecho
significativo do tempo e AVX2 reduz esse trecho. Com 20 threads, os dois
builds passam a disputar recursos compartilhados: controladores de memória,
DRAM, cache de último nível e interconexão entre sockets. A parcela acelerável
fica limitada pelo restante do programa (cópia, overhead/barreiras OpenMP e
banda), uma aplicação prática da lei de Amdahl.

O VTune mede essa transição:

| Zoom | Memory Bound | Cache Bound | DRAM alta banda | Núcleos físicos efetivos |
| --- | ---: | ---: | ---: | ---: |
| `off-avx2`, 1 thread | 12,5% | 8,4% | 0,0% | 0,989 |
| `omp-avx2`, 1 thread | 24,8% | 12,8% | 0,0% | 0,996 |
| `off-avx2`, 20 threads | 42,3% | 20,7% | 58,5% | 11,747 |
| `omp-avx2`, 20 threads | **60,4%** | **29,0%** | **61,7%** | 11,684 |

Fonte: `hpc_metricas.csv`, gráfico `01_hpc_memory_bound.svg`. AVX2 deixa o
cálculo local mais rápido, então chega mais cedo à limitação de memória. Isso
explica por que o ganho de wall-clock não permanece próximo a 2,35× mesmo na
fase vertical, e por que ele se estreita ao aumentar o paralelismo.

### Limite

O VTune reporta `NUMA: % of Remote Accesses: 0,0%` nessas coletas de Zoom;
portanto, esta evidência sustenta banda/cache compartilhados, não uma
explicação por tráfego NUMA remoto. A utilização efetiva (~11,7 de 20) sugere
que overhead, desequilíbrio ou limites de memória também existem, mas não os
separa quantitativamente.

---

## 4. Qual é o efeito exato de `static` e `dynamic` em operações regulares?

### Semântica no código

Os laços elegíveis usam `schedule(runtime)`, por exemplo no Negative:

```cpp
// image_manipulation.cpp:888-897
#pragma omp parallel for schedule(runtime)
for (int i = 0; i < img.height; i++) {
    OMP_SIMD
    for (int j = 0; j < img.width; j++) { ... }
}
```

Assim, `OMP_SCHEDULE` decide a distribuição das **linhas**:

- `static`: divide antecipadamente blocos contíguos; quase não há custo de
  escalonamento;
- `static,k`: distribui blocos de `k` linhas de modo cíclico, ainda sem fila
  dinâmica;
- `dynamic,k`: threads retiram blocos de `k` linhas de uma fila compartilhada;
  equilibra tempo, mas custa sincronização e pode prejudicar localidade.

### Evidência controlada

A resposta deve dar mais peso à confirmação de dez repetições, intercaladas e
com afinidade controlada, que ao primeiro gráfico de cinco repetições. A
tabela `schedules_confirmacao.csv` e a figura
`03_schedules_confirmacao.svg` trazem:

| Operação, 20 threads, AVX2 | static | dynamic,1 | dynamic,16 | Conclusão observável |
| --- | ---: | ---: | ---: | --- |
| Adjust Brightness | 12,266 ms | 12,256 ms | 12,377 ms | empate prático |
| Equalize Histogram | 13,185 ms | 13,353 ms | 13,206 ms | empate prático |
| Negative | 7,795 ms | 7,777 ms | 7,852 ms | empate prático |
| Gaussian 11×11 | 553,178 ms | 556,911 ms | 562,786 ms | static ligeiramente melhor |
| Zoom In | 26,532 ms | 82,696 ms | 31,930 ms | dynamic piora muito |
| Flip Horizontal | 5,843 ms | 5,390 ms | 5,531 ms | dynamic melhora |

Portanto, não há uma regra de que `static` sempre vence uma carga regular,
nem de que `dynamic` melhora todas. Para três kernels curtos, as diferenças
estão dentro de intervalos sobrepostos; para Gaussian e Zoom, o custo/localidade
do dynamic domina; Flip é a exceção confirmada e é discutido na pergunta 9.

### Contraste útil: operação irregular

No filtro adaptativo, o tempo por linha depende do mapa de detalhes e da janela
escolhida. Em `rain_paisage.jpg`, `dynamic,16` foi **1,353×** mais rápido que
static (4305,43 → 3182,26 ms, build escalar); em `control_half_noise`,
**1,330×** (802,64 → 603,52 ms). Os números estão em
`adaptive_static_vs_dynamic16_20_threads.csv` e na figura
`07_adaptativo_static_vs_dynamic16.svg`. Esse é o caso que corresponde à
vantagem clássica de `dynamic`: carga de trabalho realmente desigual.

---

## 5. Por que algumas operações aparentemente regulares melhoram com `dynamic`?

### Premissa

O gráfico amplo de cinco repetições,
`03_schedules_regulares_20_threads.svg`, mostrava ganhos de aproximadamente
10--16% para Brightness, Contrast, Negative, Quantize e Flip. A pergunta é
correta porque, olhando apenas a contagem de pixels, essas operações parecem
uniformes.

### O que a confirmação permite concluir

A campanha controlada reduz substancialmente essa lista. Brightness, Negative
e Equalize Histogram passaram a ter intervalos sobrepostos entre static e
dynamic; portanto, os ganhos preliminares não são evidência suficiente de
vantagem estável. Isso é exatamente por que a mediana e as dez repetições
intercaladas foram introduzidas.

O único ganho reproduzido é Flip Horizontal; não é resultado de uma carga
aritmética irregular por linha, mas de heterogeneidade de **tempo efetivo** por
thread, evidenciada na pergunta 9. Para o adaptativo, a melhora é de fato
causada por carga irregular.

Também é possível haver diferenças de memória/topologia mesmo em kernels de
mesmo número de operações por pixel: páginas podem estar mais próximas de um
socket, a banda pode saturar de forma desigual e caches podem sofrer pressão
diferente. Isso é uma hipótese plausível, não uma explicação provada para cada
um dos ganhos preliminares. A configuração usada fixa as threads
(`OMP_PLACES=cores`, `OMP_PROC_BIND=close`); `dynamic` redistribui chunks, não
move threads entre CPUs durante o laço.

---

## 6. Por que o SoA ingênuo torna Gaussian 11×11 muito pior que AoS direto?

### Premissa e medição que a confirma

O gráfico apropriado é
`visualizacoes_pcad_hype_final_layout_aos_soa/figures/01_kernels_6000x6000_Gaussian_11x11_omp-avx2.svg`,
que mede só o kernel, sem conversão. Em 20 threads:

| Layout/build | Kernel Gaussian 11×11 |
| --- | ---: |
| AoS direto, `off-avx2` | 531,41 ms |
| SoA ingênuo, `off-avx2` | 534,08 ms |
| AoS direto, `omp-avx2` | 531,27 ms |
| SoA ingênuo, `omp-avx2` | **1072,85 ms** |

Logo, a conversão não é a explicação: ela custa apenas 6,04 ms de AoS→SoA e
5,50 ms de volta, enquanto o kernel SoA ingênuo sozinho custa 1072,85 ms.
Essas fases estão na tabela `fases_20_threads.csv` e na figura
`03_fases_20t_6000x6000_Gaussian_11x11.svg`.

### Evidência de código

O SoA ingênuo ainda faz a convolução 2D direta: para cada pixel de saída,
acumula 11×11 = 121 coeficientes para cada canal. O laço está em
`layout_benchmark.cpp:230-254` e contém `OMP_SIMD` no laço de `x`:

```cpp
for (int y = 5; y < height - 5; ++y) {
    OMP_SIMD
    for (int x = 5; x < width - 5; ++x) {
        float sum_red = 0.0f;
        // 121 contribuições para R, G e B
    }
}
```

Ao forçar SIMD nesse padrão de 121 taps, o resultado é consistente com uma
estratégia desfavorável para este processador/layout: o mesmo kernel fica
quase duas vezes mais lento, enquanto AoS direto permanece estável. A
evidência é experimental, não apenas visual: sem SIMD, AoS e SoA ingênuo são
praticamente iguais; a regressão aparece somente com `omp simd`. O relatório
completo posterior do GCC (job 824453) registra vetorização de 8 bytes
associada a um laço de taps, mas isso, sozinho, não atribui a regressão a uma
única decisão interna do compilador.

### O que agora foi medido e o que continua aberto

O job HPC 824167 mediu os três layouts com a conversão fora da região longa.
No build `omp-avx2`, SoA ingênuo teve 9,4% de Memory Bound e 9,1% de Cache
Bound, contra 3,3% e 2,7% no AoS direto. Isso dá suporte quantitativo à
hipótese de maior pressão de cache/memória no kernel vetorizado ingênuo e
elimina a conversão como explicação.

Esses percentuais do VTune não são contagem direta de misses L1 ou L2. Os
[contadores do job 824542](ANALISE_MEMORIA_824542.md) mostram, no processo
com SoA ingênuo, aproximadamente 54% mais instruções e 64–66% mais misses
de leitura na LLC com AVX2, mas não mais misses de leitura na L1. Isso
fortalece a conclusão de um kernel com maior custo de instruções e pressão
em cache profundo; não separa em segundos os efeitos de redução vetorial,
spills, latência e tráfego DRAM.

---

## 7. O que o SoA separável faz e por que é tão eficiente?

### Evidência de código

Um kernel gaussiano 11×11 é separável: a matriz 2D equivale ao produto de um
vetor horizontal de 11 pesos pelo mesmo vetor vertical. Em vez de 121
contribuições por canal/pixel, o algoritmo executa:

1. uma passada horizontal de 11 contribuições e armazena uma soma intermediária;
2. uma passada vertical de 11 contribuições sobre esse intermediário;
3. normalização ao final.

Portanto, reduz de 121 para **22 contribuições por canal/pixel**. Isso está
implementado em `layout_benchmark.cpp:260-302`; a composição de três canais e
das duas passadas está em `layout_benchmark.cpp:309-324`.

```cpp
// layout_benchmark.cpp:321-322
times.horizontal_ms += measure_ms([&] {
    gaussian_11_horizontal_pass(*inputs[channel], intermediate, width, height);
});
times.vertical_ms += measure_ms([&] {
    gaussian_11_vertical_pass(intermediate, *outputs[channel], output_width, output_height);
});
```

Cada canal SoA é um vetor contínuo. Em ambas as passadas, o laço vetorizado
avança em `x` sobre vetores contínuos, sem desentrelaçar RGB e sem a redução
2D de 121 taps do método ingênuo. A melhoria é principalmente algorítmica;
SoA e SIMD tornam essas duas passadas lineares particularmente favoráveis.

### Evidência medida

Em 20 threads, imagem 6000×6000:

| Método | `off-avx2` | `omp-avx2` |
| --- | ---: | ---: |
| AoS direto | 531,41 ms | 531,27 ms |
| SoA ingênuo | 534,08 ms | 1072,85 ms |
| SoA separável | **44,81 ms** | **33,19 ms** |

Com AVX2, a versão separável é **16,0×** mais rápida que AoS direto no
kernel. Mesmo contando conversão de ida e volta, o total é 43,38 ms, ainda
12,3× menor que AoS direto. Na mesma medição, a passada horizontal custa 17,77
ms e a vertical 15,43 ms. Fonte: `kernels_por_layout.csv`,
`fases_20_threads.csv`, figuras `01_kernels_6000x6000_Gaussian_11x11_omp-avx2.svg`
e `03_fases_20t_6000x6000_Gaussian_11x11.svg`.

### Atualização e limite

O job 824170 validou hashes e cinco repetições para 3×3, 5×5, 7×7, 9×9 e
11×11. Na implementação genérica, a razão AoS direto / separável em 20
threads foi 0,87×, 1,22×, 1,52×, 1,63× e 2,50× sem AVX2; com AVX2, 0,93×,
1,29×, 1,73×, 2,25× e 2,92×. O cruzamento ocorre em 5×5 e o benefício cresce
com N. Consulte o painel final e gaussian_sizes_summary.csv.

Esse executável genérico usa acumuladores inteiros e não é o mesmo kernel
11×11 especializado de layout_benchmark.cpp. Portanto, os números confirmam
generalização e tendência, mas não substituem o speedup especializado de
16,0×. O ganho enorme continua sendo principalmente algorítmico (121 para 22
contribuições), com SIMD favorecendo as duas passadas lineares.

O gráfico novo 03b_gaussian_efeito_avx2.svg separa corretamente os efeitos:
ele compara off-avx2 / omp-avx2 dentro do mesmo algoritmo. Nesse executável,
AVX2 não apresenta ganho sistemático. AoS direto piora de aproximadamente 6%
a 15%; no SoA separável, somente 9 taps tem ganho claro (1,12× em uma thread
e 1,22× em 20), e 11 taps fica próximo de empate (1,04× e 1,01×). Portanto,
as razões de até 2,92× no gráfico de separabilidade são AoS direto /
separável, isto é, ganho algorítmico, não ganho de AVX2.

---

## 8. Por que o Zoom In decai tanto com `dynamic`?

### Premissa e dados

Na confirmação de schedules, Zoom em 20 threads passou de 26,53 ms com static
para 82,70 ms com `dynamic,1` (**3,12× mais lento**). Com `dynamic,16`, foi
31,93 ms (**20% mais lento**). Os intervalos não se sobrepõem. Ver
`03_schedules_confirmacao.svg` e `schedules_confirmacao.csv`.

O diagnóstico por fase reproduz o mecanismo e elimina uma suspeita importante:
o custo de primeira alocação/páginas. A figura
`05_zoom_schedules_pretouch.svg` compara páginas “fresh” com saída pré-tocada
por static, fora da janela. Em 20 threads e AVX2:

| Schedule | fresh | pré-toque static |
| --- | ---: | ---: |
| static | 21,21 ms | 17,34 ms |
| static,1 | 70,70 ms | 28,83 ms |
| dynamic,1 | 72,16 ms | 29,97 ms |
| dynamic,16 | 27,17 ms | 28,72 ms |
| dynamic,64 | 23,51 ms | 28,58 ms |

### Explicação sustentada

O Zoom não tem custo variável por linha: `dynamic,1` não tem desequilíbrio
aritmético para corrigir. Ele acrescenta uma aquisição de fila por linha em
cada uma das três fases e destrói a divisão contígua natural de trabalho. A
fase de cópia é particularmente exposta: com dados fresh, ela sobe de 10,41
ms (`static`) para 54,12 ms (`dynamic,1`).

O pré-toque demonstra que uma grande parte desse contraste fresh é
primeira-escrita de páginas: após pré-tocar, a cópia de `dynamic,1` cai para
8,80 ms. Ainda assim, o total `dynamic,1` continua 29,97 ms contra 17,34 ms
de static porque a fila por linha e a pior localidade permanecem. `dynamic,64`
reduz o custo de fila, mas não vence static.

Também há um controle especialmente esclarecedor: `static,1` e `dynamic,1`
ambos distribuem uma linha por vez; o primeiro mede 28,83 ms e o segundo
29,97 ms após pré-toque. A diferença restante é predominantemente a fila
dinâmica; a diferença enorme entre static e chunk 1 é a perda de blocos
contíguos/localidade e não apenas a fila. As fases estão em
`06_zoom_fases_schedules.svg` e `zoom_schedule_pretouch.csv`.

---

## 9. Por que Flip Horizontal parece melhorar com `dynamic`? É reprodutível?

### Premissa e reprodutibilidade

A campanha controlada de dez repetições confirmou o sinal:

| Schedule | Mediana | Intervalo | static / schedule |
| --- | ---: | ---: | ---: |
| static | 5,843 ms | 5,706--5,971 | 1,000× |
| dynamic,1 | **5,390 ms** | 5,351--5,634 | **1,084×** |
| dynamic,16 | 5,531 ms | 5,436--5,570 | 1,056× |

Os intervalos de dynamic não se sobrepõem ao de static nessa coleta. Isso
reproduz a observação inicial; os jobs 824168 e 824169 acrescentaram duas
alocações exclusivas independentes e testaram a preparação das páginas.

O diagnóstico posterior fortalece a evidência: fez 12 rodadas pareadas, com
ordem dos cinco schedules embaralhada. A figura
`08_flip_razoes_pareadas.svg` mostra `static / dynamic,1` acima de 1× nas 12
rodadas; as medianas são 5,231 ms (static) e 4,802 ms (dynamic,1), razão
**1,089×**. Arquivos: `flip_raw.csv`, `flip_summary.csv` e
`tables/flip_razoes_pareadas_por_rodada.csv`.

### Evidência de distribuição de trabalho

O Flip processa uma linha por iteração:

```cpp
// image_manipulation.cpp:1024-1029
#pragma omp parallel for schedule(runtime)
for (int j = 0; j < img.height; j++) {
    flip_horizontal_row(img, j);
}
```

No diagnóstico, static deu exatamente **300 linhas** a cada uma das 20
threads; portanto, a carga algorítmica foi equilibrada. Porém, o tempo médio
das threads 0--9 foi 4,51 ms, contra 5,10 ms nas threads 10--19. Com
`dynamic,1`, o runtime atribuiu aproximadamente 318 linhas ao primeiro grupo
e 282 ao segundo, e ambos terminaram perto de 4,71 ms. Veja
`09_flip_linhas_por_thread.svg`, `10_flip_tempo_por_thread.svg` e
`tables/flip_por_thread.csv`.

Isso explica a melhora observada em parte: dynamic equilibra **tempo de
término**, não número de linhas. Com inicialização serial em 20 threads, a
mediana foi 6,78 ms para static e 6,22 ms para dynamic,1. Quando o buffer foi
pré-tocado com parallel-static, o sinal inverteu: 4,20 ms contra 4,53 ms,
favorecendo static. O primeiro toque/colocação das páginas é, portanto, uma
causa demonstrada para parte do efeito.

Ainda resta uma assimetria em 10 threads: mesmo dentro do primeiro nó NUMA,
dynamic,1 ficou em 8,38 ms contra 9,20 ms de static após pre-touch. Static
atribuiu 600 linhas a cada thread, mas o CV temporal foi 8--9%; dynamic
redistribuiu 585--654 linhas e reduziu o CV para 0,02--0,04%. Logo, dynamic
compensa heterogeneidade temporal do mapeamento neste nó, mas não uma carga
algoritmicamente irregular. Para isolar a causa restante, seria necessário
rotacionar os lugares OpenMP entre núcleos e registrar frequência por núcleo.


---

## Síntese para uso no relatório

1. AVX2 foi decisivo no Zoom porque acelerou a interpolação vertical; não foi
   um ganho uniforme do programa.
2. A implementação atual de Grayscale ganhou 1,277× em uma thread e 1,159×
   em 20. O GCC gerou um loop vetorial de 32 bytes, mesmo com RGB intercalado.
   A conclusão antiga de empate se refere ao código da campanha 822851.
3. Ao escalar Zoom, o ganho AVX2 cai. O job 824542 não aponta aumento
   seletivo dos misses de leitura L1 nessa transição, mas não mediu banda
   DRAM nem separou contadores por fase; pressão de memória compartilhada
   permanece hipótese, não conclusão demonstrada.
4. `static` é a escolha de referência para cargas uniformes; `dynamic` é
   valioso para carga irregular e pode compensar heterogeneidade da plataforma,
   como no Flip, mas tem custo e pode destruir localidade, como no Zoom.
5. SoA não é automaticamente mais rápido. SoA ingênuo com convolução direta
   piorou ao forçar SIMD; SoA separável venceu porque muda o algoritmo de 121
   para 22 contribuições por pixel e então oferece loops lineares favoráveis.

Os jobs que executam todas as coletas adicionais propostas neste documento
estão descritos em [`EXPERIMENTOS_COMPLEMENTARES_FINAIS.md`](EXPERIMENTOS_COMPLEMENTARES_FINAIS.md).
