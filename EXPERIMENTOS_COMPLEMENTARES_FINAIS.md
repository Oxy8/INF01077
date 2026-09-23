# Campanha complementar final

Estes jobs fecham as lacunas identificadas em
[`ANALISE_EVIDENCIAS.md`](ANALISE_EVIDENCIAS.md). Eles são independentes e
podem ser submetidos em paralelo; cada um pede um nó `hype` exclusivo.

```bash
job_compiler=$(sbatch --parsable scripts/pcad_hype_compiler_evidence.sbatch)
job_layout=$(sbatch --parsable scripts/pcad_hype_hpc_layout_gaussian.sbatch)
job_flip_1=$(sbatch --parsable scripts/pcad_hype_hpc_flip_topology.sbatch)
job_flip_2=$(sbatch --parsable scripts/pcad_hype_hpc_flip_topology.sbatch)
job_sizes=$(sbatch --parsable scripts/pcad_hype_gaussian_separable_sizes.sbatch)
echo "$job_compiler $job_layout $job_flip_1 $job_flip_2 $job_sizes"
```

## 1. Evidência do compilador

`pcad_hype_compiler_evidence.sbatch` não mede desempenho. Arquiva os relatórios
`-fopt-info-vec-all` e o assembly de `image_benchmark` e `layout_benchmark`
nas versões sem SIMD e com AVX2. Use-o para confirmar quais laços do Zoom,
AoS e SoA o GCC aceitou/recusou vetorizar.

## 2. VTune HPC: Gaussian por layout

`pcad_hype_hpc_layout_gaussian.sbatch` coleta seis casos: AoS direto, SoA
ingênuo e SoA separável, cada um sem SIMD e com AVX2, sempre em 20 threads e
`static`. A variante selecionada é repetida por cerca de três a quatro
segundos; as outras executam apenas uma vez para validação. O resultado inclui
`summary.txt` e, quando suportado pelo VTune local, `hw_events.csv`.

Compare `Memory Bound`, `Cache Bound`, banda DRAM, L3/DRAM local/remota e
stalls de store. Compare AoS × SoA ingênuo para isolar layout/código gerado;
SoA ingênuo × separável para isolar a mudança de algoritmo.

## 3. VTune HPC: Flip, sockets e first-touch

`pcad_hype_hpc_flip_topology.sbatch` compara `static` e `dynamic,1` com 10 e
20 threads, usando inicialização serial e first-touch paralelo por blocos
contíguos. Um controle adicional inicializa com `parallel-runtime` sob
`dynamic,1`. O executável repete pares de flips — dois flips restauram a
imagem — para que a cópia de restauração não domine o perfil. Cada caso grava
`threads.csv`, o resumo HPC e eventos brutos se disponíveis.

Se a vantagem de dynamic desaparecer após first-touch paralelo, a hipótese de
colocação das páginas/topologia ganha sustentação causal. Se persistir, os
contadores e a divisão por thread ajudam a separar banda, cache e frequência.
Envie-o duas vezes, como no bloco acima: isso produz duas alocações Slurm
independentes, necessárias para distinguir um efeito do nó de uma característica
reprodutível do programa.

## 4. Generalização para tamanhos gaussianos

`pcad_hype_gaussian_separable_sizes.sbatch` mede kernels diretos AoS e
separáveis SoA para 3×3, 5×5, 7×7, 9×9 e 11×11, em 1 e 20 threads e builds
sem SIMD/AVX2. Há cinco repetições por caso, com hash exato entre referência
direta e separável. O kernel é binomial inteiro; a convolução direta e as
duas passadas usam os mesmos pesos, portanto a validação não depende de
diferenças de arredondamento float.
