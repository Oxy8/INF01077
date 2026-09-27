# Nova campanha: organização dos laços para SIMD, sem outras otimizações

Esta campanha substitui o uso do job 824931 como prova de que “a reescrita para SIMD” melhorou operações. Ela **não usa** lookup no Quantize, histograma privado, SoA, pesos inteiros ou convolução separável. O código anterior não é removido; o modo `--clean-linearization` do [benchmark](577262-FPI-Relatorio2/vectorization_benchmark.cpp) seleciona só as variantes controladas.

| Operação | Referência | Candidata medida | Mudança |
| --- | --- | --- | --- |
| Negative, Brightness, Contrast | função de produção | `linear_bytes` | Percorrer os bytes RGB contíguos da linha; mesma aritmética. |
| Equalize_Histogram | função de produção | `linear_remap` | **Mesma** contagem/redução/normalização; apenas o remapeamento percorre bytes contíguos. Registrar `count_and_normalize`, `remap` e `total`. |
| Gaussian_11x11 | `pixel_outer` | `row_linear_aos` | Mesmos 121 coeficientes `float`, mesma ordem de acumulação e mesmo AoS; para cada tap, percorrer uma linha inteira de saída. Ambos recebem saída pré-alocada. A candidata precisa de acumuladores temporários por linha; seu custo integra o tempo e não deve ser chamado de “ganho SIMD puro”. |
| Quantize, Grayscale, Zoom_In | função de produção atual | nenhuma | **Controles**: mede `off/auto/omp` sem alegar reescrita. Quantize já tem pixels independentes; uma LUT seria outra otimização. |

O novo [script de execução](run_linear_simd_tests.sh) mede 12 e 36 MP (`Zoom_In` só 12 MP), 1 e 20 threads, `OMP_SCHEDULE=static`, cinco medições e um aquecimento por configuração. Os builds `off-avx2`, `auto-avx2` e `omp-avx2` compartilham `-march=haswell`. A ordem dos builds alterna entre repetições. Ele valida a imagem pequena e faz um **pré-voo nas imagens reais** antes das medições; esse pré-voo fica em CSV separado e não entra nas estatísticas. Cada execução registra hash e comparação exata. O [sumarizador](summarize_linear_simd.py) exige hashes iguais entre candidatos e builds, amostras completas e números iguais de repetições. Os relatórios de vetorização completos e um recorte dos laços do GCC são salvos por build.

Os [gráficos](plot_linear_simd.py) separam duas perguntas:

- `simd_mesma_variante_12mp.svg` e `simd_mesma_variante_36mp.svg`: `off/auto`, `off/omp`, `auto/omp` **dentro da mesma variante**. Isso é evidência para efeito das opções de vetorização naquele código.
- `efeito_estrutura.csv`: `original/candidata` **dentro do mesmo build**, para as cinco operações reestruturadas. Essa razão inclui efeitos de endereçamento, buffer temporário e organização do laço; não atribuí-la exclusivamente às instruções SIMD.

O gráfico principal mostra apenas tempo `total`. Para o histograma, consultar `linear_simd_summary.csv` e a fase `remap` separadamente; o total inclui a contagem não vetorizada. Para a Gaussiana, `kernel` e `total` coincidem porque ambas as saídas foram pré-alocadas; a alocação interna da função de produção fica fora dessa comparação. O relatório GCC identifica laços transformados, enquanto tempos medidos indicam se isso ajudou. Nenhum número da campanha nova existe até executar o job.

## Validação curta e submissão

Na raiz do repositório, em um ambiente com GCC/OpenMP:

```bash
bash run_linear_simd_tests.sh --quick --output resultados_linear_simd_checagem
```

Depois de enviar as mudanças ao repositório e atualizar o checkout no frontend do PCAD:

```bash
job=$(sbatch --parsable scripts/pcad_hype_linear_simd.sbatch)
echo "$job"
squeue -j "$job"
```

O job é independente dos anteriores e grava `resultados_pcad_hype_linear_simd_ID/` na raiz do repositório. Não há configuração de afinidade/NUMA adicional. A reserva é exclusiva, com uma tarefa, 20 CPUs e limite de um dia; terminará antes se a campanha acabar. Para conferir após a conclusão:

```bash
sacct -j "$job" --format=JobID,State,ExitCode,Elapsed
ls "resultados_pcad_hype_linear_simd_${job}"
```
