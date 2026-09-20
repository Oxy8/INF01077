# Experimentos OpenMP

## Execução local

Compile uma variante isolada:

```bash
make SIMD=off all
make SIMD=off-avx2 all
make SIMD=omp all
make SIMD=omp-avx2 all
```

As quatro variantes separam dois efeitos diferentes:

- `off`: controle escalar no alvo padrão, com auto-vetorização desativada;
- `off-avx2`: o mesmo controle escalar, gerado para Haswell (`-march=haswell`);
- `omp`: pragmas `omp simd` no alvo padrão;
- `omp-avx2`: pragmas `omp simd` para Haswell, habilitando AVX2 no hype.

As variantes `omp` gravam o relatório do compilador em
`build/<variante>/vectorization-core.log`. O controle `off-avx2` evita atribuir
ao SIMD explícito uma diferença causada apenas pelo alvo de compilação.
Para preservar hashes entre os alvos, a contração FMA fica desativada; isso não
desativa os vetores AVX2.

Gere os controles determinísticos de 6000×6000 quando necessário:

```bash
make SIMD=off generate-controls
```

Faça uma validação curta da infraestrutura:

```bash
bash run_tests.sh --smoke --output resultados_smoke
```

A campanha completa usa cinco repetições cronometradas, uma execução de
aquecimento e threads `1,2,4,8,12,16,20`. A afinidade e a política NUMA ficam
nos padrões do ambiente OpenMP/Slurm:

```bash
bash run_tests.sh --output resultados_experimentos
```

O arquivo `benchmark_raw.csv` mantém cada medição individual e
`benchmark_summary.csv` contém mediana, mínimo, máximo, média, desvio-padrão
e speedup relativo ao `static` da mesma configuração.

## Experimento complementar: layout de pixels

`run_layout_tests.sh` testa a hipótese de que o layout intercalado usado pela
biblioteca (`RGBRGB...`, também chamado AoS) reduz a oportunidade de
vetorização. Ele usa `Grayscale` e `Gaussian_11x11`, `schedule(static)`, as
duas imagens regulares e os mesmos sete níveis de threads da campanha
principal. Para cada uma das quatro variantes, há aquecimento e cinco amostras
medidas:

```bash
bash run_layout_tests.sh --output resultados_layout
```

O benchmark aloca `R[]`, `G[]` e `B[]` uma vez e registra as fases separadas:
`AoS_to_SoA`, `Kernel`, `SoA_to_AoS` e `End_to_End`. Para Gaussian 11×11 ele
inclui três soluções: AoS direto, SoA ingênuo de 121 contribuições por canal e
SoA separável (11 contribuições horizontais + 11 verticais por canal). O buffer
intermediário é reutilizado e as conversões, alocações e cópias de restauração
ficam fora do tempo do kernel. O resultado separável usa os mesmos pesos
binomiais inteiros; por mudar a ordem do arredondamento, aceita diferença
máxima de um nível em cada componente e registra essa diferença no CSV.

O padrão separável vale para outros tamanhos gaussianos ímpares cujos pesos
sejam separáveis (por exemplo 3×3, 5×5, 7×7 e 9×9): basta trocar o vetor
unidimensional de pesos e o normalizador. Ele não vale para uma convolução
arbitrária cujo kernel 2D não possa ser escrito como produto de dois vetores.

## PCAD

No nó de login, submeta primeiro a verificação de VTune:

```bash
sbatch scripts/pcad_vtune_preflight.sbatch
```

Depois execute a bateria formal em nó hype exclusivo:

```bash
sbatch scripts/pcad_hype_benchmark.sbatch
```

Para executar apenas o teste de layout no mesmo tipo de nó:

```bash
sbatch scripts/pcad_hype_layout.sbatch
```

O job coleta a topologia de CPU e usa a configuração padrão do ambiente. A
campanha VTune é separada, roda apenas no nó de cálculo e não entra nas
amostras temporizadas. Consulte [VTUNE_PCAD.md](VTUNE_PCAD.md): ele inclui o
preflight para localizar o módulo VTune, o job exclusivo e os nove perfis
selecionados para adaptativo, layouts e Zoom In.
