# VTune: lookup do Quantize (off, automático e OpenMP SIMD)

Este experimento investiga a regressão observada no job 824931 quando o
`omp simd` força a vetorização do laço de lookup do Quantize. Ele preserva a
função `quantize_lut` usada naquela campanha e compara três builds Haswell:
`off-avx2` (vetorizador de laços desligado), `auto-avx2` (GCC decide) e
`omp-avx2` (pragma explícito). `off-avx2` **não** significa que toda instrução
SSE/AVX esteja proibida; significa que `-fno-tree-vectorize` foi usado.

Na campanha 824931, imagem de 6000×6000, `static`, dez amostras por caso,
a mediana da fase `lookup` foi:

| Threads | off-avx2 | auto-avx2 | omp-avx2 |
| ---: | ---: | ---: | ---: |
| 1 | 38,69 ms | 38,93 ms | 64,24 ms |
| 20 | 3,82 ms | 3,68 ms | 4,32 ms |

Fonte: `resultados_pcad_hype_vectorization_824931/vectorization_summary.csv`,
variante `quantize_lut`, fase `lookup`. O GCC confirmou a vetorização do laço
de pixels apenas em `omp-avx2`. O objetivo aqui é investigar por que ela não
reduziu o tempo, sem presumir previamente qual instrução ou gargalo causou a
regressão.

## Execução no PCAD

Após enviar estas alterações ao repositório e atualizá-lo no frontend, a
partir da raiz do projeto:

```bash
sbatch scripts/pcad_hype_vtune_quantize_lookup.sbatch
```

Para recuperar **somente Hotspots** de uma campanha cujos controles e perfis
HPC já estejam completos (como o job 825087), use:

```bash
sbatch --export=ALL,QUANTIZE_VTUNE_ONLY_HOTSPOTS=1 \
  scripts/pcad_hype_vtune_quantize_lookup.sbatch
```

Esse modo recompila os três builds no próprio diretório temporário, mas pula
as dez amostras de controle e todas as coletas HPC. As coletas Hotspots usam
`sampling-mode=hw`: no VTune 2021.1.1 do hype, o modo padrão baseado em Pin
falha ao encontrar a seção ELF `.relr.dyn` do carregador do sistema.

O job solicita um nó hype exclusivo, com 20 CPUs, e usa a imagem
`images/6000x6000.png`. O limite é de duas horas; não é uma previsão de
duração. Para usar outra imagem já presente no projeto:

```bash
sbatch --export=ALL,QUANTIZE_VTUNE_IMAGE=images/4000x3000.png \
  scripts/pcad_hype_vtune_quantize_lookup.sbatch
```

Não há dependência de `python` no job. O script compila em diretório temporário
próprio para não modificar os builds da raiz nem conflitar com outros jobs.
Registra compilador, host, CPU, ambiente OpenMP, commit, hashes dos fontes e
da imagem, diagnósticos GCC e montagem dos três executáveis. Usa
`OMP_DYNAMIC=FALSE`, `OMP_SCHEDULE=static` e 1/20 threads; não altera afinidade
ou política NUMA herdada do ambiente, mas salva as variáveis OpenMP presentes.
Uma cópia dos fontes relevantes fica em `source/` para consultar as linhas
mesmo depois que o diretório temporário for removido.

## O que é medido

O modo `--profile-quantize-lookup N` do executável prepara o Grayscale e os
extremos **uma vez**, fora da repetição. Antes de cada chamada a `quantize_lut`,
restaura os mesmos bytes de entrada. Registra separadamente o tempo de
restauração e o tempo do lookup e valida a última saída byte a byte contra a
implementação original. O wrapper `profile_quantize_lookup_kernel` evita que
a chamada inteira desapareça por inlining; o OpenMP pode aparecer no VTune
como uma função worker `._omp_fn.*`.

O job primeiro faz **dez controles sem VTune por build/thread**, alternando a
ordem dos builds. Seus tempos ficam em `control_raw.csv` (fase
`lookup_average`, uma iteração por amostra) e suas medianas em
`control_medians.csv`; confira que a regressão se repete
antes de interpretar os perfis. Depois faz, para cada build/thread, uma coleta
Hotspots e uma HPC Performance. Cada coleta perfila 100 chamadas com uma
thread ou 500 chamadas com 20 threads. Os resultados são salvos em
`resultados_pcad_hype_vtune_quantize_<jobid>/`.

Por caso, consulte `hotspots_functions.txt`, `hotspots_summary.txt` e
`hpc-performance_summary.txt`. Os diretórios `hotspots/` e
`hpc-performance/` guardam os projetos VTune completos. Os arquivos
`<build>_compiler.txt` e `<build>_assembly.txt` permitem conferir o laço
vetorizado e as instruções emitidas. Uma falha em uma coleta não impede as
outras; o job termina com erro ao final se alguma falhou, e o log identifica
qual.

## Interpretação

1. Decida **qual build é mais rápido** pelo `control_raw.csv`, sem VTune, não
   pelo elapsed total da coleta perfilada.
2. No Hotspots, examine o laço de pixels em `quantize_lut` e a função worker
   OpenMP. Compare tempo de CPU e linhas/instruções quentes; tempo de CPU
   acumulado entre threads não é tempo decorrido.
3. Nos relatórios HPC, examine indicadores de memória e execução **na função
   relevante**, se disponíveis. O resumo global inclui restaurações de buffer,
   preparo da imagem e validação; portanto, seus percentuais não pertencem
   exclusivamente ao lookup. Com 20 threads, esse cuidado é especialmente
   importante porque a restauração pode representar parte substancial da
   coleta.
4. Cruze isso com o relatório GCC e a montagem. O VTune localiza custo, mas
   não prova por si só que uma instrução AVX2 particular é sua causa. CPI não
   é usado como comparação principal entre `off`, `auto` e `omp`, pois a
   vetorização muda o trabalho realizado por instrução.

O modo isolado também pode ser testado sem VTune:

```bash
make SIMD=auto-avx2 vectorization
OMP_NUM_THREADS=1 OMP_SCHEDULE=static \
  build/auto-avx2/vectorization_benchmark --image images/6000x6000.png \
  --operation Quantize quantize_lookup_controle.csv \
  --profile-quantize-lookup 1
```
