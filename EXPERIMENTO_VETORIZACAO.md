# Experimento isolado de reescritas para SIMD

Este experimento **não modifica nem substitui** as 17 implementações de
`image_manipulation.cpp`. O executável novo contém candidatos independentes e
chama as funções originais como referências. Não misture estas amostras com
campanhas antigas: compilador, algoritmo e escopo cronometrado podem diferir.

## Como executar

Na raiz do projeto, em Linux com GCC, OpenMP e `make`:

```bash
bash run_vectorization_tests.sh --quick --output resultados_vetorizacao_teste
bash run_vectorization_tests.sh --output resultados_vetorizacao_completa
```

O diretório informado precisa **não existir**. O script nunca apaga resultados
anteriores e não executa `make clean`. Para o PCAD, após enviar os arquivos ao
repositório e atualizar a cópia no frontend:

```bash
sbatch scripts/pcad_hype_vectorization.sbatch
```

O job escreve em `resultados_pcad_hype_vectorization_JOBID`, com CSV bruto,
resumo, versão do compilador, relatórios completos de vetorização e disassembly
dos três builds. Cada build tem também `compiler-focus.txt` com as linhas
mais relevantes do relatório; para decidir qual laço foi vetorizado, confira
as linhas no fonte e consulte o relatório completo quando houver ambiguidade.
O script usa `python3` apenas para o resumo; caso não esteja
disponível, o CSV bruto permanece utilizável. A compilação/execução local no
Windows serve para conferir saída, mas a decisão final do GCC deve ser lida no
relatório do **GCC do nó hype**, usando as flags efetivas salvas no CSV.
O modo `--quick` usa uma imagem pequena e apenas uma amostra: serve para
compilação e correção, **não** para inferir desempenho.

## Comparações que o CSV permite

Os builds usam o mesmo alvo `-march=haswell` e `-ffp-contract=off`:

| Build | `omp simd` explícito | Vetorização automática | Pergunta |
|---|---|---|---|
| `off-avx2` | não | desativada com `-fno-tree-vectorize` | referência sem vetorizador de laços |
| `auto-avx2` | não | ativada | efeito da vetorização automática |
| `omp-avx2` | sim | ativada | efeito adicional do pragma |

Não chame o primeiro build de “sem nenhuma instrução SIMD”: bibliotecas e
operações escalares de ponto flutuante podem usar instruções da família SSE/AVX.
Uma linha `optimized` no GCC demonstra vetorização de um **laço específico**,
não de toda a operação nem necessariamente ganho de desempenho.

As operações são: três ponto a ponto (`Negative`, `Adjust_Brightness`,
`Adjust_Contrast`), `Quantize`, `Equalize_Histogram`, `Flip_Horizontal`, as duas
rotações, cinco Gaussianas (3/5/7/9/11), e os controles positivos `Grayscale`
e `Zoom_In`. O filtro adaptativo, Flip Vertical e Zoom Out não foram reescritos.

O protocolo padrão usa imagens de 12 e 36 MP, 1 e 20 threads,
`OMP_SCHEDULE=static`, uma execução de aquecimento e dez amostras. Para
Gaussianas em 36 MP são cinco amostras; Zoom In em 36 MP é omitido porque a
saída quadruplica o número de pixels. A ordem dos builds alterna entre
repetições. Para as Gaussianas, a ordem **interna** das quatro variantes é
fixa; diferenças pequenas entre variantes merecem uma campanha pareada com
ordem rotacionada antes de uma conclusão causal.

`vectorization_raw.csv` contém uma linha por fase; `Phase=total` soma apenas
as fases pertinentes. Hash, comparação, carregamento da imagem, cópia de
restauração e alocação de buffers das candidatas (exceto quando a fase
`allocation` é explícita) estão fora do tempo de kernel. O hash e a diferença
gravados em cada fase correspondem à **saída final da variante**, não ao estado
intermediário daquela fase.

Nas Gaussianas, `aos_direct` é a referência **inteira binomial**. As quatro
variantes `aos_direct`, `soa_direct`, `aos_separable` e `soa_separable` têm de
produzir exatamente os mesmos bytes. Isso separa o efeito do layout do efeito
do algoritmo separável. A linha `production_float` mede adicionalmente a
implementação original: pode divergir por arredondamento e inclui alocação
interna, portanto **não** use seu tempo como se fosse outro kernel pré-alocado.
`Max_Abs_Error` torna a diferença numérica explícita. Para as demais operações,
a saída da variante deve coincidir byte a byte com a função original.

As passadas separáveis novas fazem o tap ser o laço externo **dentro de cada
linha**: para cada tap, acrescentam sua contribuição a todos os pixels
contíguos da linha. Assim, uma Gaussiana 11×11 efetua onze contribuições
horizontais e onze verticais por pixel, mantendo a mesma ordem de soma para
cada pixel. O laço interno marcado `omp simd` é agora o de bytes/pixels, não
o de taps. Isso foi confirmado no teste local com GCC 14; o relatório do
GCC 12 do PCAD ainda precisa confirmar o mesmo resultado naquele ambiente.

No histograma, a contagem candidata usa histogramas privados por thread, mas
continua sendo um acesso indexado pelos dados; **não há garantia de SIMD na
contagem**. A fase de remapeamento também pode não vetorizar devido à tabela
indexada. A finalidade é testar e documentar isso, não pressupor sucesso.

No Flip e nas rotações, a variante cria um buffer de saída. Para Flip, o
original trabalha no lugar; para rotações, o original também aloca uma nova
imagem. Compare `kernel` e `total` separadamente: memória extra e custo de
alocação fazem parte da interpretação. Nas rotações, o original inclui
alocação/liberação internas no seu `total`, enquanto o candidato discrimina a
alocação; os dois totais não têm gerenciamento de memória perfeitamente
idêntico.

`vectorization_summary.csv` mostra mediana, mínimo, máximo e razões entre
builds **da mesma variante**, além da razão entre referência e candidato no
mesmo build. Razão maior que 1 significa menor tempo no denominador. Não
atribua ganho a AVX2 sem cruzar essa razão com o laço correspondente no
relatório do compilador.
