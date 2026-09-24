# Análise complementar final: Zoom, Flip e Gaussiana

Esta nota incorpora os resultados dos jobs 823586 e 824167--824170. O painel
de figuras está em
[visualizacoes_pcad_hype_experimentos_finais_824167_824168_824169_824170](visualizacoes_pcad_hype_experimentos_finais_824167_824168_824169_824170/index.html).
Ela complementa, sem substituir, a análise principal em
[ANALISE_EVIDENCIAS.md](ANALISE_EVIDENCIAS.md).

## 1. SoA ingênuo: há evidência de pressão de cache/memória

### Evidência de código

O kernel SoA ingênuo ainda calcula 121 taps para cada pixel e cada canal. O
laço por x recebe OMP_SIMD em
[layout_benchmark.cpp](577262-FPI-Relatorio2/layout_benchmark.cpp), nas linhas
230--254. Portanto, ele não reduz a complexidade do algoritmo: apenas muda a
organização dos canais e força vetorização da redução 2D.

### Dados medidos

O job 824167 perfilou somente o layout selecionado por vez, com conversão e
validação fora da região longa. No build omp-avx2:

| Layout | Memory Bound | Cache Bound | DRAM bound |
| --- | ---: | ---: | ---: |
| AoS direto | 3,3% | 2,7% | 0,3% |
| SoA ingênuo | **9,4%** | **9,1%** | 0,4% |
| SoA separável | 27,3% | 9,3% | 38,8% |

Fonte: gaussian_layout_hpc.csv e
01_gaussian_hpc_memoria.svg no painel final.

### Conclusão e limite

O resultado sustenta que a regressão do SoA ingênuo com AVX2 não é conversão:
o kernel vetorizado tem pressão de memória/cache substancialmente maior que o
AoS direto. As métricas HPC são percentuais normalizados do trecho coletado,
não uma contagem direta de misses L1/L2; portanto, não isolam entre si spills,
redução vetorial, cache e latência. A formulação segura é: pressão de
cache/memória maior contribui para a escolha ruim de vetorização.

## 2. SoA separável: generalização para 3--11 taps

### Evidência de código

O programa novo
[gaussian_sizes_benchmark.cpp](577262-FPI-Relatorio2/gaussian_sizes_benchmark.cpp)
constrói pesos binomiais para 3, 5, 7, 9 e 11 taps. Para cada canal, faz uma
passada horizontal e uma vertical. Assim, a convolução reduz de N² para 2N
contribuições por pixel. Ele compara o resultado contra uma implementação
direta com os mesmos pesos e aborta se os hashes divergirem.

### Dados medidos

Foram cinco repetições por caso, sem VTune, usando as medianas abaixo. A
razão é AoS direto dividido pelo SoA separável, logo valor acima de 1 favorece
o separável:

| Taps | 20 threads, sem AVX2 | 20 threads, AVX2 |
| ---: | ---: | ---: |
| 3 | 0,87x | 0,93x |
| 5 | 1,22x | 1,29x |
| 7 | 1,52x | 1,73x |
| 9 | 1,63x | 2,25x |
| 11 | 2,50x | 2,92x |

Fontes: gaussian_tamanhos_mediana.csv,
gaussian_speedup_separavel.csv e as figuras 02 e 03 do painel.

Para 3x3, o custo do intermediário e das passadas extras ainda supera a
economia aritmética. A partir de 5x5, o benefício aparece e cresce com N,
exatamente como prevê a troca de N² por 2N.

O efeito isolado de AVX2 é outro gráfico: gaussian_efeito_avx2.csv e
03b_gaussian_efeito_avx2.svg comparam off-avx2 / omp-avx2 dentro do mesmo
kernel. Eles mostram que AVX2 não é o responsável pelas razões acima. AoS
direto piora aproximadamente 6--15% com AVX2; no separável, somente 9 taps
tem ganho claro (1,12x em uma thread e 1,22x em 20), enquanto 11 taps fica
perto de empate. As razões de 2x ou mais são, portanto, efeito do algoritmo
separável contra o direto.

### Limite metodológico

Este benchmark genérico usa acumuladores inteiros para preservar igualdade
exata. Ele é diferente do kernel 11x11 especializado de layout_benchmark.cpp.
Assim, ele valida generalização e tendência de desempenho, mas seus 2,92x não
substituem os 16,0x obtidos na implementação especializada 11x11. Não se deve
comparar os tempos absolutos entre esses dois executáveis.

O VTune aponta o separável AVX2 como 27,3% Memory Bound e 38,8% DRAM bound.
Isso é coerente com uma versão rápida: ao retirar grande parte do cálculo, a
banda passa a ser o teto mais visível, não uma prova de regressão.

## 3. Zoom: Hotspots confirma qual fase perde com dynamic

Todos os três casos do job 823586 rodaram 50 iterações de Zoom AVX2 com 20
threads. O Hotspots mediu CPU time acumulado:

| Fase | static | dynamic,1 | Variação dynamic,1 |
| --- | ---: | ---: | ---: |
| Cópia | 8,910 s | 9,376 s | +5% |
| Interpolação horizontal | 7,369 s | 8,210 s | +11% |
| Interpolação vertical | 11,063 s | 13,145 s | +19% |
| CPI total (somente diagnóstico) | 1,110 | 1,223 | +10% |

Fonte: zoom_hotspots_schedules.csv e
06_zoom_hotspots_schedules.svg.

Isso reforça a explicação obtida no benchmark com pré-toque: dynamic,1
fragmenta os blocos contíguos e introduz a fila dinâmica nas três fases. O
perfil mostra que a degradação não fica restrita ao dispatcher OpenMP.

O CPI não é usado para comparar SIMD com a versão scalar: uma instrução AVX2
faz trabalho em várias posições e altera o próprio denominador. Aqui ele é
apenas um indício secundário, pois compara o mesmo binário AVX2, com as
mesmas 20 threads, mudando somente o schedule. Mesmo nesse caso, a conclusão
de desempenho vem dos tempos sem profiler, e não do CPI.

Os tempos wall sob Hotspots não devem ser usados para decidir o schedule,
porque a amostragem altera a execução. A evidência principal continua sendo o
benchmark sem profiler: 17,34 ms para static e 29,97 ms para dynamic,1 após
pré-toque.

## 4. Flip: dynamic equaliza tempo, mas não corrige carga irregular

### Evidência de código

O Flip faz exatamente uma linha por iteração, em
[image_manipulation.cpp](577262-FPI-Relatorio2/image_manipulation.cpp), linhas
1024--1048. A versão perfilada conta linhas e cronometra cada thread. O
executável
[flip_profile_runner.cpp](577262-FPI-Relatorio2/flip_profile_runner.cpp)
permite preparar o buffer serialmente, em blocos static ou com runtime,
antes da janela medida.

### Duas réplicas independentes

Os jobs 824168 e 824169 repetiram os mesmos controles em alocações exclusivas
diferentes. Em 20 threads:

| Inicialização | static | dynamic,1 | Melhor |
| --- | ---: | ---: | --- |
| Serial | 6,78 ms | 6,22 ms | dynamic,1 (1,09x) |
| Paralela/static | **4,20 ms** | 4,53 ms | static (1,08x) |

Assim, o primeiro toque/colocação das páginas é causal para parte da vantagem
anterior de dynamic: quando as páginas já foram tocadas nos mesmos blocos
contíguos que static usa, a vantagem troca de lado.

Mas isso não explica toda a assimetria. Em 10 threads, todos no nó NUMA 0,
mesmo a inicialização paralela/static deu 9,20 ms para static e 8,38 ms para
dynamic,1. Static atribuiu precisamente 600 linhas a cada thread, mas o
coeficiente de variação de Work_ms foi 8--9%. Dynamic distribuiu 585--654
linhas e reduziu o CV para 0,02--0,04%, fazendo as threads terminarem juntas.
Fontes: flip_topologia_replicas.csv,
04_flip_primeiro_toque_20t.svg e 05_flip_desequilibrio_temporal.svg.

A conclusão é deliberadamente limitada: dynamic é reprodutivelmente melhor
para alguns mapeamentos deste Flip, porque compensa heterogeneidade temporal;
isto não revela irregularidade algorítmica por linha. Como 10 threads ficam
em um único nó NUMA, NUMA remoto não pode ser a única explicação. Para isolar
o restante, seria necessário repetir static com os lugares OpenMP rotacionados
entre núcleos e registrar a frequência por núcleo.
