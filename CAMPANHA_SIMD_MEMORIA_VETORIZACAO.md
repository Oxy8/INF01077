# Campanha complementar: SIMD, vetorização e memória

Esta campanha responde separadamente três perguntas que não devem ser
misturadas: desempenho observado, código que o compilador emitiu e pressão de
memória/cache.

## Desenho

| Coleta | Casos | Métrica principal | Limite |
| --- | --- | --- | --- |
| Tempo | 17 operações regulares; off-avx2 e omp-avx2; 1 e 20 threads; static; 10 amostras | mediana de ms/pixel e razão das medianas | não contém contadores |
| Layout Gaussiana | AoS direto, SoA ingênuo e SoA separável; 1 e 20 threads; 10 amostras | tempo de cada fase; kernels sem conversão | somente 11x11 especializado |
| Vetorização GCC | os fontes dos kernels regulares e Gaussianas, nos dois builds | mensagens accepted/missed, dump da passagem vect, assembly/objdump | estático: não mede tempo |
| Memória/perf | as 17 operações; dois builds; 1 e 20 threads; 5 amostras por grupo de eventos | misses por pixel e MPKI | regular/ inclui PNG, backup e hash |
| Memória/perf Gaussiana | três layouts 11x11 com repetição longa | misses por pixel do kernel dominante | não é diretamente comparável ao tempo de outro executável |

A configuração de OpenMP fixa apenas o que o experimento exige:
`OMP_NUM_THREADS`, `OMP_DYNAMIC=FALSE` e `OMP_SCHEDULE=static`.
`OMP_PLACES` e `OMP_PROC_BIND` são removidos para manter o mapeamento
padrão do runtime; o ambiente resultante é salvo em cada diretório.

## Execução no PCAD

Da raiz do repositório no frontend, envie os três jobs independentes:

```bash
sbatch scripts/pcad_hype_compiler_evidence.sbatch
sbatch scripts/pcad_hype_regular_1_20_simd.sbatch
sbatch scripts/pcad_hype_regular_memory_1_20.sbatch
```

Eles podem ficar na fila ao mesmo tempo. Para reduzir o tempo solicitado na
coleta de memória durante um teste inicial, use, por exemplo:

```bash
sbatch --export=ALL,REGULAR_MEMORY_REPEATS=1 scripts/pcad_hype_regular_memory_1_20.sbatch
```

A campanha final usa dez repetições de tempo e cinco de memória; a segunda
coleta é mais longa porque o `perf` executa cada operação separadamente para
cada grupo de eventos. Cada job cria um diretório
`resultados_pcad_hype_..._<jobid>`.

## Como interpretar

SIMD não pode ser julgado por CPI entre o binário scalar e o AVX2. Uma
instrução vetorial executa várias posições de dados e modifica tanto o
numerador quanto o denominador do CPI. Para o ganho SIMD, use:

1. mediana de tempo por pixel e `speedup = mediana(off-avx2) / mediana(omp-avx2)`;
2. instruções por pixel, se os contadores estiverem disponíveis;
3. misses L1/LLC por pixel e MPKI como suporte para a hipótese de cache;
4. relatórios do GCC e assembly para confirmar quais loops foram vetorizados,
   com qual largura e quais laços foram recusados.

CPI pode aparecer, no máximo, como indício secundário ao comparar o mesmo
binário, mesmo algoritmo e mesma contagem de threads. Mesmo nesse recorte,
tempo wall, speedup e eficiência de paralelização são as métricas conclusivas.

Nos dados de `regular/`, `perf` mede o processo inteiro: carga da imagem,
backup, transformação e hash. É útil para verificar se uma operação como
Zoom ou Flip é globalmente limitada por cache/memória, mas não prova que cada
miss pertence ao laço do kernel. Para essa atribuição, use
`gaussian11_kernel/`, cuja repetição longa da variante selecionada domina a
coleta.
