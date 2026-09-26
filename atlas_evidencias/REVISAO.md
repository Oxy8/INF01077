# Revisão do atlas

O atlas é gerado por `python -B montar_atlas_evidencias.py` a partir de dados
locais. `python -B scripts/verify_atlas_evidencias.py` valida inventário, links,
SVGs, tabelas de suporte e razões centrais. Não há dependência de rede ou de
um servidor para consultar as páginas.

## Inventário e leitura

O inventário real contém **99 SVGs** de seis painéis preexistentes e **quatro**
capturas PNG na raiz. O plano inicial mencionava três capturas; nenhuma foi
excluída. As imagens em `images/` são entradas do benchmark, não capturas de
resultado. O manifesto `manifesto_figuras.json` registra, individualmente,
título/eixo, métrica, configuração inferível do nome/tabela, job, número de
amostras, tabela associada, gerador, estado e ressalva. As quatro figuras novas
ficam em `figures/`, separadas dos 103 originais.

Estados: **verificado** = SVG íntegro, dados locais e gerador identificados;
**corrigido** = figura com erro de leitura reparado no gerador;
**redundante** = recorte de uma campanha já representada em outro painel;
**histórico** = versão/campanha anterior que não se deve juntar à atual;
**não sustentado** = captura sem tabela/protocolo suficiente para sustentar
conclusão quantitativa sozinha. A verificação estrutural de um SVG não é uma
garantia de significância estatística. Para conclusões, use os intervalos e as
réplicas nos CSVs.

## Correções efetuadas

| Figura | Defeito | Correção | Dados brutos |
| --- | --- | --- | --- |
| `03_schedules_regulares_20_threads.svg` | Eixo dizia apenas “razão de medianas”, mas cada barra é a média geométrica de quatro razões (2 imagens × 2 builds) | Eixo agora explicita a média geométrica; o atlas prioriza também o mapa desagregado e a confirmação de 10 amostras | Inalterados |
| `04_flip_primeiro_toque_20t.svg` | Identificador do caso perdia o prefixo `t10`/`t20`, resultando em `NaN` e barras na borda | `plot_experimentos_finais.py` preserva o identificador inteiro; duas alocações aparecem corretamente de lados opostos de 1× | Inalterados |
| `05_flip_desequilibrio_temporal.svg` | Mesmo `NaN`; a antiga razão de CV gerava uma escala pouco legível | Dados corrigidos e exibição de CV de tempo por thread (%) para static e dynamic,1; não é “speedup” | Inalterados |

O CSV derivado `flip_topologia_replicas.csv` teve o campo `Case` corrigido;
medidas numéricas originais não mudaram. Os demais painéis continuam com os
próprios geradores. A figura `03b_gaussian_efeito_avx2.svg` já distinguia o
efeito de AVX2 **dentro do mesmo algoritmo** da razão
`03_gaussian_speedup_separavel.svg` entre algoritmos; o atlas os coloca lado a
lado e não chama a última de ganho SIMD.

## Cruzamentos novos

As figuras `regular_kernel_versus_llc_1t.svg` e `..._20t.svg` usam tempo do
**kernel** do job 824454 e misses LLC do **processo completo** no 824542.
A presença de Flip sem pragma SIMD como controle impede atribuir ao laço os
misses globais comuns ao build AVX2. `gaussian_instr_dentro_layout.svg` e
`gaussian_llc_dentro_layout.svg` comparam AVX/off apenas **dentro do mesmo
layout**. Não se comparam contagens brutas entre layouts, pois o job de perf
repetiu cada variante um número diferente de vezes. Os CSVs derivados
preservam cobertura dos eventos e tamanho de amostra.

`auditoria_recalculos.json` contém verificações independentes a partir dos CSVs
brutos: mediana(off)/mediana(AVX2) para Zoom, Grayscale e layouts Gaussianos;
e média geométrica das quatro razões de medianas de schedules para duas
operações. O gerador aborta se essas contas divergirem dos valores publicados.

Os quatro geradores não alterados foram executados em uma pasta temporária de
verificação; seus **61 SVGs** coincidiram byte a byte com os originais. Os
outros dois geradores foram executados para aplicar as correções acima. Todos
os 99 SVGs foram analisados como XML e inspecionados quanto a dimensões,
coordenadas horizontais fora da área de desenho e valores `NaN`/`Inf`. As quatro capturas
PNG foram abertas e revisadas. O verificador de HTML encontrou 700 vínculos
locais válidos após a geração final.

## Limites que permanecem

- Os relatórios GCC confirmam laços vetorizados, mas não a fração dinâmica de
  tempo em cada instrução. `off-avx2` versus `omp-avx2` combina pragma e
  vetorização automática.
- `perf stat` abrange decodificação PNG, cópias e hash além do kernel. Eventos
  L1/LLC foram multiplexados; faltam contadores exclusivos do kernel e banda
  por fase para atribuir uma causa exata à perda de ganho do Zoom em 20 threads.
- Os gráficos de Grayscale dos jobs 822851/822854 são históricos em relação
  ao código/medidas 824453/824454. Não houve A/B de revisões no mesmo job.
- VTune serve para diagnóstico; CPU time acumulado e tempo decorrido não são
  intercambiáveis, e coletas perfiladas não são amostras de benchmark.
- As quatro capturas PNG não têm associação reproduzível completa com CSV e
  protocolo. Estão no catálogo por completude, sem força probatória autônoma.
- A política do navegador automatizado bloqueou a abertura de páginas
  `file://`. A inspeção estrutural de todas as figuras e os links foi concluída,
  mas uma verificação visual humana no navegador local ainda é recomendada.
