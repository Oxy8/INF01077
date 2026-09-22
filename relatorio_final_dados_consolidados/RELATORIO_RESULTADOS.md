# Resultados consolidados

## Validação

| Campanha | Medições | Passaram | Falharam | Grupos | Amostras/grupo | Nó |
|---|---:|---:|---:|---:|---|---|
| regular | 14280 | 14280 | 0 | 2856 | 5 | hype5 |
| adaptive | 2880 | 2880 | 0 | 576 | 5 | hype2 |
| smt | 120 | 120 | 0 | 24 | 5 | hype1 |
| layout | 4480 | 4480 | 0 | 896 | 5 | hype1 |

Todos os gráficos e razões abaixo usam a **mediana** das cinco amostras. Consulte mínimo e máximo nos CSVs de resumo antes de interpretar diferenças pequenas. As 12 configurações mais dispersas de cada campanha estão em `maior_variabilidade.csv`.

## Achados numéricos

| Área | Achado | Referência → teste | Valor |
|---|---|---|---:|
| Regulares | SIMD no alvo padrão | off → omp | 1.009 |
| Regulares | SIMD com AVX2 | off-avx2 → omp-avx2 | 1.010 |
| Regulares | alvo Haswell mantendo omp simd | omp → omp-avx2 | 1.019 |
| Regulares | schedule em 20 threads: static sobre dynamic,1 | static → dynamic,1 | 0.884 |
| Regulares | schedule em 20 threads: static sobre dynamic,16 | static → dynamic,16 | 0.989 |
| Adaptativo | melhor chunk em 20 threads | off → dynamic,4 | 11503.663 |
| Adaptativo | speedup do melhor chunk sobre static | off: static → off: dynamic,4 | 1.222 |
| Adaptativo | melhor chunk em 20 threads | off-avx2 → dynamic,1 | 11961.241 |
| Adaptativo | speedup do melhor chunk sobre static | off-avx2: static → off-avx2: dynamic,1 | 1.214 |
| Adaptativo | melhor chunk em 20 threads | omp → dynamic,4 | 11766.759 |
| Adaptativo | speedup do melhor chunk sobre static | omp: static → omp: dynamic,4 | 1.220 |
| Adaptativo | melhor chunk em 20 threads | omp-avx2 → dynamic,1 | 12145.907 |
| Adaptativo | speedup do melhor chunk sobre static | omp-avx2: static → omp-avx2: dynamic,1 | 1.214 |
| SMT | 20→40 threads: Adaptive_Median, static | omp → 40 threads | 1.395 |
| SMT | 20→40 threads: Adaptive_Median, dynamic,16 | omp → 40 threads | 1.041 |
| SMT | 20→40 threads: Gaussian_11x11, static | omp → 40 threads | 1.014 |
| SMT | 20→40 threads: Gaussian_11x11, dynamic,16 | omp → 40 threads | 0.981 |
| SMT | 20→40 threads: Grayscale, static | omp → 40 threads | 0.668 |
| SMT | 20→40 threads: Grayscale, dynamic,16 | omp → 40 threads | 0.925 |
| SMT | 20→40 threads: Adaptive_Median, static | omp-avx2 → 40 threads | 1.394 |
| SMT | 20→40 threads: Adaptive_Median, dynamic,16 | omp-avx2 → 40 threads | 1.018 |
| SMT | 20→40 threads: Gaussian_11x11, static | omp-avx2 → 40 threads | 1.022 |
| SMT | 20→40 threads: Gaussian_11x11, dynamic,16 | omp-avx2 → 40 threads | 0.988 |
| SMT | 20→40 threads: Grayscale, static | omp-avx2 → 40 threads | 1.037 |
| SMT | 20→40 threads: Grayscale, dynamic,16 | omp-avx2 → 40 threads | 1.022 |
| Layout | Gaussian 11×11 separável sobre AoS ingênuo, 6000² T20 | off: AoS_Naive → off: SoA_Separable | 11.758 |
| Layout | Gaussian 11×11 separável sobre AoS ingênuo, 6000² T20 | off-avx2: AoS_Naive → off-avx2: SoA_Separable | 11.859 |
| Layout | Gaussian 11×11 separável sobre AoS ingênuo, 6000² T20 | omp: AoS_Naive → omp: SoA_Separable | 14.863 |
| Layout | Gaussian 11×11 separável sobre AoS ingênuo, 6000² T20 | omp-avx2: AoS_Naive → omp-avx2: SoA_Separable | 16.005 |

Valores maiores que 1 em speedups favorecem o teste; valores menores que 1 favorecem a referência.
