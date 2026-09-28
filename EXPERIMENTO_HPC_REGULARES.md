# Última campanha VTune: Memory Bound das operações regulares

## Objetivo

Comparar as 17 operações originais da imagem `6000x6000.png` no build
`SIMD=off`, com `schedule(static)` e **1 ou 20 threads**, como nas curvas de
eficiência do benchmark principal. A campanha também repete cinco medições de
tempo **sem VTune** para conferir se o comportamento de escalabilidade se
reproduz no novo job. Tempos coletados sob VTune não entram nessa comparação.

O perfil usa `hpc-performance`, o mesmo tipo de análise que funcionou no hype.
Antes de iniciar a amostragem, o programa carrega a imagem e prepara cópias
independentes da entrada. O VTune começa pausado; uma chamada ITT inicia a
coleta imediatamente antes das transformações repetidas e outra a pausa logo
após. Assim, decodificação PNG, cópias de preparação e hash não entram no
resumo de Memory Bound. **Alocações que fazem parte da operação** continuam
incluídas, como no benchmark de tempo. A quantidade de cópias é limitada pelo
menor valor entre 24 GiB e um quarto da memória disponível no nó.
Como as chamadas perfiladas usam cópias independentes, o conjunto total de
memória em circulação pode ser maior que em uma medição isolada. Portanto,
o perfil é uma **evidência complementar** da operação, não uma reprodução
exata da hierarquia de cache da campanha principal; os controles de tempo
sem VTune verificam separadamente a reprodução da curva de eficiência.

## Executar no PCAD

Do computador local, entre no frontend; depois, na raiz do repositório lá:

```bash
ssh usuario@gppd-hpc.inf.ufrgs.br
cd ~/teste/INF01077
git pull --ff-only
sbatch scripts/pcad_hype_hpc_regular_memory.sbatch
```

O script exige o SDK ITT da instalação
`/home/intel/oneapi/vtune/2021.1.1/sdk`; se ele não existir no nó, encerra
com uma mensagem específica antes de executar a campanha. O job reserva um
nó hype exclusivo, com até quatro horas. Não fixa afinidade nem política NUMA,
reproduzindo a configuração geral anterior. Registra host, compilador, versão
do VTune, ambiente OpenMP e commit. Quando os hashes da campanha 822851
estiverem no repositório do PCAD, exige igualdade dos 17 resultados antes de
começar a coleta. O primeiro perfil também serve como sonda: se a integração
ITT/VTune não funcionar, o job para sem repetir o erro nas outras operações.

Uma sonda curta pode ser feita reduzindo o alvo e as repetições de controle,
sem substituir a campanha final:

```bash
sbatch --export=ALL,REGULAR_HPC_PROFILE_MS=500,REGULAR_HPC_CONTROL_REPEATS=1 \
  --time=01:00:00 scripts/pcad_hype_hpc_regular_memory.sbatch
```

## Saídas

O diretório `resultados_pcad_hype_hpc_regular_memory_JOBID/` conterá:

- `memory_bound_17.csv`: uma linha por operação e nível de threads, incluindo
  o percentual de Memory Bound, a mediana de controle e o estado da coleta;
- `manifest.csv`: número de repetições no perfil, tempo de preparação fora da
  coleta e tempo amostrado dos kernels;
- `OPERAÇÃO_t1/` e `OPERAÇÃO_t20/`: cinco tempos brutos sem VTune, relatório
  `summary.txt`, relatório por função `hotspots_functions.csv`, log e dados
  nativos `hpc_performance/` para abrir no VTune.

Depois de trazer o diretório para esta máquina, gere a comparação:

```bash
python3 plot_hpc_regular_memory.py \
  --result resultados_pcad_hype_hpc_regular_memory_JOBID
```

Ela cria um gráfico de Memory Bound em 1 e 20 threads, outro que compara os
tempos de controle com os da campanha principal, um diagrama que cruza
Memory Bound e eficiência em 20 threads e uma tabela com todos os valores.
Se houver casos incompletos, o gerador os omite e informa a cobertura; não
inventa valores.

## Como interpretar

`Memory Bound` é uma estimativa de **slots do pipeline afetados por esperas na
hierarquia de memória**, não a porcentagem do tempo total nem, por si só, uma
medida de saturação da DRAM. O gráfico permite testar se as operações com
menor eficiência tendem a apresentar mais Memory Bound em 20 threads. Ele não
prova causalidade automaticamente: alocações, trabalho serial, localidade,
distribuição entre sockets e custo de sincronização também podem reduzir a
eficiência. Em operações multifase, como Zoom In e Quantize, consulte ainda
o relatório por função. A comparação dos **tempos de controle** deve ser
verificada antes de cruzar os novos perfis com as curvas antigas.

Referências: [controle de coleta ITT da Intel](https://www.intel.com/content/www/us/en/docs/vtune-profiler/user-guide/2024-2/collection-control-api.html)
e [visão HPC Performance da Intel](https://www.intel.com/content/www/us/en/docs/vtune-profiler/user-guide/2023-0/hpc-performance-characterization-view.html).
