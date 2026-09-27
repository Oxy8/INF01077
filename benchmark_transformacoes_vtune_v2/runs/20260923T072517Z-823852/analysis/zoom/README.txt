Zoom In e Zoom Out: análise dos chunks dinâmicos pequenos
==========================================================

O que foi medido
-----------------

- Speedup: média geométrica, entre as imagens, da mediana static dividida pela mediana do schedule.
- Eventos: soma dos endereços pertencentes às funções da transformação no relatório hw-events, dividida por Workload_Iterations.
- Razão de evento: contagem por passagem do schedule dividida pela contagem por passagem de static, no mesmo número de threads.
- L1 pending: ciclos amostrados em CYCLE_ACTIVITY.STALLS_L1D_PENDING.
- L2 pending: ciclos amostrados em CYCLE_ACTIVITY.STALLS_L2_PENDING.
- Store-buffer stalls: ciclos amostrados em RESOURCE_STALLS.SB.
- Fração do clock: 100 × evento / CPU_CLK_UNHALTED.THREAD, usando as mesmas funções e o mesmo schedule.

Uma passagem corresponde a aplicar a transformação às 13 imagens. Os valores são estimativas do VTune, e não tempos exclusivos que possam ser somados entre si. L1, L2 e SB podem contar o mesmo ciclo e seus percentuais não devem ser somados.

Resultados em dynamic 1
------------------------

20 threads:
- Ampliação: speedup original=0.369×; sob VTune=0.513× (posição 3/18, da maior perda para o maior ganho); L1 pending/static=3.04×; L2 pending/static=2.93×; store-buffer stalls/static=10.37×.
  Nos frames: CPU-time dynamic/static=2.00×; CPI dynamic/static=2.03×; núcleos ativos=19.67 (static=18.44); Memory Bound=34.9% (static=26.5%); Store Bound=36.8% (static=12.3%).
- Redução: speedup original=0.869×; sob VTune=0.918× (posição 4/18, da maior perda para o maior ganho); L1 pending/static=1.10×; L2 pending/static=1.07×; store-buffer stalls/static=0.67×.
  Nos frames: CPU-time dynamic/static=1.10×; CPI dynamic/static=1.07×; núcleos ativos=19.62 (static=19.26); Memory Bound=11.8% (static=6.6%); Store Bound=9.1% (static=1.1%).

40 threads:
- Ampliação: speedup original=0.162×; sob VTune=0.171× (posição 1/18, da maior perda para o maior ganho); L1 pending/static=4.57×; L2 pending/static=2.91×; store-buffer stalls/static=2.20×.
  Nos frames: CPU-time dynamic/static=5.93×; CPI dynamic/static=5.75×; núcleos ativos=39.11 (static=36.89); Memory Bound=34.6% (static=21.5%); Store Bound=47.6% (static=18.1%).
- Redução: speedup original=0.589×; sob VTune=0.675× (posição 2/18, da maior perda para o maior ganho); L1 pending/static=1.69×; L2 pending/static=1.20×; store-buffer stalls/static=2.59×.
  Nos frames: CPU-time dynamic/static=1.50×; CPI dynamic/static=1.49×; núcleos ativos=38.21 (static=37.65); Memory Bound=21.3% (static=8.2%); Store Bound=19.8% (static=2.2%).

Interpretação
-------------

A perda de Zoom Out com 20 threads não foi reproduzida: o benchmark original mediu 0.869× em dynamic 1, enquanto a coleta VTune mediu 0.918×. Os contadores dessa coleta não explicam aquela perda original. Com 40 threads, as perdas de Zoom In (0.162× original; 0.171× VTune) e Zoom Out (0.589× original; 0.675× VTune) aparecem nos dois experimentos e podem ser relacionadas aos eventos abaixo.

Zoom In executa três laços paralelos sobre uma saída com aproximadamente quatro vezes mais pixels: escreve posições pares, preenche lacunas horizontais e depois linhas ímpares. Chunks muito pequenos redistribuem as linhas entre threads em cada fase. Os aumentos simultâneos de ciclos com L1/L2 pendentes e de stalls do store buffer, junto ao CPI maior, mostram pressão no caminho de stores e na hierarquia de memória dentro da transformação.

Zoom Out lê blocos 2x2 de duas linhas da entrada e grava uma linha de saída. O trabalho por pixel de saída é regular, portanto dynamic não oferece um ganho relevante de balanceamento. Quando seus eventos e CPI sobem, o custo de distribuir muitos chunks e as esperas de memória/stores ficam sem um benefício que os compense. Estes contadores não distinguem, sozinhos, cache misses, contenção e mudança de posse das linhas de cache.

Em 40 threads e dynamic 1, a quantidade de instruções nas funções praticamente não mudou: Zoom In=1.000× static e Zoom Out=1.000× static. Os stores retirados também não explicam a elevação dos stalls: Zoom In=0.974× e Zoom Out=1.008× static. Ao mesmo tempo, os núcleos ativos aumentaram ligeiramente. Portanto, os dados descartam mais trabalho algorítmico e falta global de threads como explicações principais. O sinal dominante é cada instrução custar mais ciclos, acompanhado de mais esperas na hierarquia de memória e no caminho de stores; o overhead do runtime OpenMP, que o filtro por função não mede, também pode contribuir.

As matrizes de comparação mostram que um fator isolado pode ser enganoso. Escala de cinza, por exemplo, tem uma grande razão de L1 em 40 threads porque a referência static era muito pequena, mas L2 não cresce e o CPI permanece próximo de static. As rotações têm grandes razões de store-buffer stalls e também apresentam uma anomalia de desempenho própria. Nos zooms, a conclusão vem do conjunto coerente de sinais: perda de tempo reproduzida, instruções constantes, paralelismo preservado, CPI maior e aumento simultâneo dos eventos relevantes.

Transformações in-place fazem uma passagem linear sem criar uma saída ampliada; os Gaussianos reutilizam mais dados e fazem muito mais cálculo por item, diluindo o custo do runtime; o Gaussiano adaptativo tem trabalho irregular e pode recuperar esse custo com melhor balanceamento.

O resultado sustenta que os chunks pequenos pioraram os zooms por elevar o custo por instrução e a espera ligada à memória/stores, sem falta de threads ativas. Ele não demonstra page faults nem permite atribuir toda a perda a uma única cache.

Nos chunks muito grandes, os eventos agregados caem porque há menos threads e menos ciclos ativos ao mesmo tempo, mas o speedup também cai. Esse extremo é explicado pela perda de paralelismo e deve ser separado do comportamento de chunks pequenos.

Limites
-------

- Os eventos são contadores amostrados e multiplexados pelo VTune; diferenças grandes e repetidas são mais confiáveis que variações pequenas.
- O filtro por símbolo inclui as funções dos zooms e exclui malloc, runtime OpenMP, kernel, leitura e restauração das imagens. Esses custos ainda afetam o tempo, mas não as contagens mostradas.
- L1/L2 pending contam ciclos com requisições pendentes; não equivalem diretamente a número de misses nem à latência média de cada acesso.
- RESOURCE_STALLS.SB indica ciclos em que a alocação de execução ficou bloqueada por falta de entradas no store buffer; não é uma contagem de stores.
- Cada condição foi coletada em um processo separado e há uma coleta por condição. A campanha demonstra associação entre schedule, eventos e tempo, sem isolar efeitos de ordem, alocador ou colocação NUMA.
- Células vazias nas matrizes significam evento ausente ou referência static igual a zero, não ausência comprovada do gargalo.
