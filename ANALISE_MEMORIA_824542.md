# Contadores de memória: job 824542

## O que foi coletado

O job [`pcad_hype_regular_memory_1_20.sbatch`](scripts/pcad_hype_regular_memory_1_20.sbatch)
rodou no **hype1**, imagem `6000x6000.png`, `schedule(static)`, builds
`off-avx2` e `omp-avx2`, com **1 e 20 threads**. Foram cinco execuções em cada
um de dois grupos de eventos (`basic` e `cache`) por configuração. Há **160
grupos de cinco**, ou **800 execuções do `perf stat`**: 680 para as 17 operações
regulares e 120 para as três variantes de layout do Gaussian 11×11. Os 680
CSVs das operações regulares dizem `Validation=passed`; os 120 processos de
layout encerraram sem erro de validação. Não há contagem ausente nos arquivos
`perf_*.csv` examinados. Configuração e protocolo originais:
[`configuration.txt`](resultados_pcad_hype_regular_memory_1_20_824542/configuration.txt)
e [`LEIA_PRIMEIRO.txt`](resultados_pcad_hype_regular_memory_1_20_824542/LEIA_PRIMEIRO.txt).

Os números abaixo são **medianas de cinco contagens**, não uma única execução.
Quando uma razão de contadores é `AVX/off`, valor acima de 1 significa que o
processo compilado com AVX2 contou **mais** daquele evento. O ganho de tempo
usa a convenção oposta, `tempo_off/tempo_AVX`: acima de 1 significa AVX2
**mais rápido**. O tempo mostrado para as operações regulares é o campo
`Elapsed_ms` do CSV do benchmark durante o grupo `basic`, **não** o tempo do
processo inteiro medido pelo `perf`.

### Limites indispensáveis

1. Em `regular/`, `perf` envolve o **processo completo**: leitura/decodificação
   PNG, cópia de entrada, operação e hash. O tempo `Elapsed_ms`, porém, cobre
   a operação. Portanto, os contadores não podem ser atribuídos diretamente
   ao laço dessa operação, sobretudo nas operações curtas.
2. Em `gaussian11_kernel/`, `--profile-layout` **repete** o layout escolhido
   (AoS 25 vezes, SoA ingênuo 12 e SoA separável 400), mas o executável ainda
   calcula uma referência e executa **uma vez cada um dos outros layouts**.
   As razões **dentro do mesmo layout** são úteis, mas nem elas são contadores
   exclusivos do kernel. Comparar totais brutos **entre** layouts, com números
   de iterações diferentes, seria incorreto. `--warmup` suprimiu o CSV de
   fases nessa coleta; os tempos de layout vêm do job 824454.
3. `cycles`, `instructions`, `cache-references` e `cache-misses` tiveram
   100% de tempo habilitado. No grupo de cache, `L1-dcache-loads` ficou
   habilitado em 53–75%, `L1-dcache-load-misses` em 48–71%, `LLC-loads` em
   47–54% e `LLC-load-misses` em 72–76%. O `perf` escalou as contagens
   multiplexadas; diferenças pequenas nesses eventos pedem cautela. Não
   calculamos MPKI cruzando `basic` e `cache`, pois são **execuções distintas**.
4. `LLC-load-misses` mede misses de **leitura** na cache de último nível. Não
   é uma medida de banda DRAM nem inclui toda escrita/prefetch; “mais LLC
   misses” não demonstra sozinho que um programa é *memory-bound*.

## Operações regulares: 17 comparações

Fonte: diretório
[`regular/`](resultados_pcad_hype_regular_memory_1_20_824542/regular/).
As duas colunas de ganho são medianas do tempo do kernel `off/AVX`; as
demais colunas são contagens do **processo inteiro** `AVX/off`.

| Operação | Ganho tempo 1t | Ganho tempo 20t | Instruções 1t/20t | LLC misses 1t/20t |
| --- | ---: | ---: | ---: | ---: |
| Adjust_Brightness | 0,99× | 0,99× | 0,96× / 0,96× | 1,26× / 1,34× |
| Adjust_Contrast | 1,02× | 1,02× | 0,96× / 0,96× | 1,30× / 1,27× |
| Equalize_Histogram | 1,00× | 1,00× | 0,96× / 0,96× | 1,30× / 1,31× |
| Flip_Horizontal | 1,00× | 0,99× | 0,96× / 0,96× | 1,27× / 1,25× |
| Flip_Vertical | 1,00× | 1,03× | 0,95× / 0,96× | 1,20× / 1,21× |
| Gaussian_3x3 | 0,99× | 0,99× | 0,98× / 0,98× | 1,34× / 1,31× |
| Gaussian_5x5 | 1,01× | 1,01× | 0,98× / 0,98× | 1,28× / 1,30× |
| Gaussian_7x7 | 1,00× | 1,00× | 0,99× / 0,99× | 1,27× / 1,34× |
| Gaussian_9x9 | 1,00× | 1,00× | 0,99× / 0,99× | 1,26× / 1,30× |
| Gaussian_11x11 | 1,00× | 1,00× | 0,99× / 0,99× | 1,29× / 1,28× |
| Grayscale | **1,28×** | **1,15×** | 0,91× / 0,91× | 1,30× / 1,32× |
| Negative | 1,03× | 1,02× | 0,96× / 0,96× | 1,27× / 1,34× |
| Quantize | 1,04× | 1,02× | 0,91× / 0,91× | 1,34× / 1,36× |
| Rotate_CCW | 1,00× | 1,01× | 0,96× / 0,96× | 1,14× / 1,17× |
| Rotate_CW | 1,00× | 0,98× | 0,96× / 0,96× | 1,14× / 1,18× |
| Zoom_In | **1,21×** | **1,06×** | 0,86× / 0,86× | 1,38× / 1,32× |
| Zoom_Out | 0,97× | 1,02× | 0,96× / 0,96× | 1,29× / 1,38× |

### Leitura correta do padrão

- **Grayscale e Zoom In:** na versão AVX2 há menos instruções no processo
  completo (aproximadamente 9% e 14%), mas os misses de leitura L1 ficam
  próximos dos controles: Grayscale 0,97×/1,05× e Zoom 0,98×/1,01× em 1t/20t.
  Os `LLC-load-misses` sobem, mas os kernels ficam mais rápidos. Portanto,
  esses dados **não** sustentam a explicação “SIMD ganhou porque eliminou
  misses de cache”. Confirme os laços efetivamente vetorizados no
  [`RELATORIO_LOOPS_SIMD_17_OPERACOES.md`](RELATORIO_LOOPS_SIMD_17_OPERACOES.md):
  todos os pixels do Grayscale e só a fase vertical do Zoom.
- **A perda de ganho do Zoom ao chegar a 20 threads continua sem causa de
  memória isolada.** Seus `L1-dcache-load-misses` não aumentam seletivamente
  com AVX2 nessa transição, e seus `LLC-load-misses` com AVX2 são cerca de
  3,17 milhões em 1t e 3,12 milhões em 20t. Os tempos do kernel passam de
  349,5/288,0 ms em 1t para 28,2/26,6 ms em 20t. A hipótese de saturação de
  banda/NUMA é plausível, mas exigiria banda DRAM e contadores por **fase**,
  não apenas estas contagens end-to-end.
- **O aumento de LLC misses com AVX2 é quase universal**, inclusive nos
  controles **Flip_Horizontal** (1,27×/1,25×), que não têm laço SIMD no código.
  Isso indica um componente comum às duas compilações — por exemplo, código
  de decodificação, cópia ou hash compilado diferentemente — ou outros efeitos
  globais. É uma **inferência**, não uma localização demonstrada dos misses.
  Não é lícito atribuir o aumento de 30% em Grayscale ou Gaussian ao seu
  próprio laço só olhando a tabela acima.
- **Gaussianas diretas** têm tempo e instruções quase iguais entre os builds.
  A auditoria do compilador informa que seus laços por pixel não foram
  vetorizados. Esta coleta não demonstra que sejam *memory-bound*: faltam
  banda efetiva e contadores exclusivos do kernel.

## Gaussian 11×11: comparação dentro de cada layout

Fonte: diretório
[`gaussian11_kernel/`](resultados_pcad_hype_regular_memory_1_20_824542/gaussian11_kernel/).
Cada linha compara **o mesmo layout, o mesmo número de iterações e threads**
entre os builds. As razões são **AVX/off para contagem total do processo**.
`cache-misses` é o evento genérico de `basic`; os L1/LLC são eventos de
`cache`, numa execução separada.

| Layout | Threads | Instruções | cache-misses | L1 load misses | LLC load misses |
| --- | ---: | ---: | ---: | ---: | ---: |
| AoS direto | 1 | 1,02× | 1,11× | 1,00× | 1,15× |
| AoS direto | 20 | 1,02× | 1,11× | 1,02× | 1,19× |
| SoA ingênuo | 1 | **1,54×** | **1,45×** | 0,95× | **1,64×** |
| SoA ingênuo | 20 | **1,54×** | **1,59×** | 0,97× | **1,66×** |
| SoA separável | 1 | **0,30×** | 1,36× | 1,00× | **2,27×** |
| SoA separável | 20 | **0,32×** | 2,03× | 1,00× | **3,64×** |

Para tornar as escalas concretas, em SoA ingênuo/1t as medianas do processo
foram **900,8 bilhões** de instruções e **4,7 milhões** de `LLC-load-misses`
sem SIMD, contra **1.390,1 bilhões** e **7,7 milhões** com AVX2. Em 20t,
foram 901,7/1.391,0 bilhões de instruções e 5,8/9,7 milhões de LLC misses.
Os intervalos das cinco amostras de LLC em 1t não se sobrepõem:
**4,6–5,0 milhões** sem SIMD, **7,4–8,0 milhões** com AVX2; em 20t,
**5,7–6,0** contra **9,5–10,4 milhões**. As diferenças não dependem de uma
amostra isolada.

O [job de tempos 824454](ANALISE_SIMD_824453_824454.md#gaussian-11x11-com-layouts)
mediu o **kernel**, sem conversão: o SoA ingênuo passou de **9,26 para 18,23 s**
em 1t e de **0,534 para 1,063 s** em 20t. O novo `perf` **reforça** que o
build AVX2 faz mais trabalho de máquina e gera mais misses de leitura na LLC.
Ele **não** mostra aumento de misses de leitura na L1; logo, não é correto
resumir a regressão como “dobrou porque a L1 falha mais”. O GCC havia
registrado uma escolha de vetorização desfavorável em um laço dos taps.
Mais instruções (incluindo preparação/redução vetorial) e mais acessos que
chegam à LLC são duas contribuições compatíveis com o tempo observado; esta
coleta não decompõe quantos segundos vêm de cada uma.

O **SoA separável** oferece um contraprova útil à explicação exclusivamente
por misses: no processo AVX2, as instruções caem para cerca de **30–32%** do
build sem SIMD, **mas os LLC load misses aumentam**, e o kernel mesmo assim
fica **2,44× mais rápido em 1t** e **1,36× em 20t**. O algoritmo reduz 121
contribuições por pixel a 22, e o GCC vetoriza as duas passadas. O
[perfil HPC anterior](visualizacoes_pcad_hype_experimentos_finais_824167_824168_824169_824170/tables/gaussian_layout_hpc.csv)
também apontava maior fração *DRAM-bound* para o separável AVX2.
Não se pode comparar as contagens brutas do SoA separável com as do ingênuo:
foram **400 versus 12** iterações selecionadas, além do trabalho comum.

O **AoS direto** é o controle algorítmico: tempo praticamente igual entre
builds (9,218/9,201 s em 1t e 0,531/0,531 s em 20t no job 824454),
instruções do processo praticamente iguais aqui (+2%). Isso concorda com a
ausência de vetorização do laço por pixel no relatório do GCC.

## O que ainda não está demonstrado

- **Banda DRAM/saturação NUMA do Zoom:** medir apenas miss counts não dá
  bytes/s. É preciso contar tráfego por controlador de memória (ou coletar
  Memory Access/HPC utilizável) e isolar cópia, interpolação horizontal e
  vertical, em 1t e 20t, com/sem AVX2. Os diagnósticos de tempo por fase já
  existem; faltam os contadores por fase.
- **Parcela exata de instruções e misses de cada layout gaussiano:** o
  `--profile-layout` atual ainda roda outros algoritmos uma vez. Para
  atribuição rigorosa, executar só o layout escolhido após preparar buffers,
  ou ligar/desligar os contadores ao redor de cada kernel. Repetir com a
  **mesma contagem de iterações** e um controle de uma iteração permitiria
  subtrair o custo fixo.
- **Por que o processo inteiro registra mais LLC misses no build AVX2 até
  quando a operação não usa SIMD:** perfilar carga PNG/backup/hash em janelas
  próprias, com `Flip_Horizontal` como controle, separaria a diferença comum
  daquela produzida pelo kernel.

Em suma: a nova coleta fortalece a explicação da regressão do **SoA ingênuo**
como uma combinação de mais instruções e mais misses em nível profundo de
cache. Ela **não** prova que a maior parte do tempo perdido seja espera por
DRAM, nem explica sozinha por que o ganho do **Zoom** encolhe em 20 threads.
