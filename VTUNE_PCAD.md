# Campanha VTune no PCAD

Esta campanha explica os resultados do benchmark; suas coletas instrumentadas
não entram nos CSVs de tempo nem devem ser comparadas às cinco repetições.

## 1. Verificar VTune no nó hype

No frontend, a ausência de `vtune` é esperada. O job carrega automaticamente
`/home/intel/oneapi/vtune/2021.1.1/vtune-vars.sh`, a instalação documentada
para o hype. Envie o preflight, que executa em um nó hype e confirma o caminho:

```bash
cd ~/teste/INF01077
sbatch scripts/pcad_vtune_preflight.sbatch
```

Quando ele finalizar, leia `slurm-vtune-preflight-<job>.out`. Se o VTune não
foi localizado automaticamente, consulte os módulos disponíveis no mesmo nó
com uma alocação curta:

```bash
salloc -p hype -N 1 -n 1 -c 20 --exclusive -t 00:20:00
module avail 2>&1 | grep -i vtune
```

Saia da alocação com `exit`. Com o nome encontrado, use-o em `VTUNE_MODULE`.

## 2. Enviar a campanha

Sem módulo adicional:

```bash
sbatch scripts/pcad_hype_vtune.sbatch
```

Ou, se o preflight indicar que é necessário um módulo específico:

```bash
sbatch --export=ALL,VTUNE_MODULE=NOME_DO_MODULO scripts/pcad_hype_vtune.sbatch
```

O job pede um nó hype exclusivo com 20 CPUs e produz
`resultados_pcad_hype_vtune_<jobid>/`. Ele executa dez coletas (a primeira é
uma confirmação leve de Hotspots):

1. Adaptativo em `rain_paisage`: `dynamic,4`, Hotspots.
2. Adaptativo em `rain_paisage`: `dynamic,4`, HPC Performance.
3. Adaptativo em `rain_paisage`: `static`, HPC Performance.
4. Mesmo adaptativo: Memory Access.
5. Grayscale AoS/SoA, `off-avx2`, HPC Performance.
6. Grayscale AoS/SoA, `omp-avx2`, HPC Performance.
7. Gaussian 11x11 AoS/SoA/separável, `off-avx2`, Hotspots.
8. Mesmo Gaussian, `omp-avx2`, Hotspots.
9. Zoom In, `off-avx2`, HPC Performance.
10. Zoom In, `omp-avx2`, HPC Performance.

Antes da campanha completa, execute a verificação curta abaixo. Ela coleta
Hotspots e HPC Performance no adaptativo, sem a calibração de pico de DRAM:

```bash
sbatch --time=00:20:00 scripts/pcad_hype_vtune.sbatch --smoke
```

O VTune 2021.1.1 do PCAD abortou durante essa calibração quando
`dram-bandwidth-limits=true` estava ativado. Além disso, seu motor Pin não lê
algumas seções ELF modernas. Por isso, Hotspots é forçado ao modo de amostragem
por hardware e a campanha mede largura de banda observada e *Memory Bound*,
mas não tenta estimar automaticamente o pico de banda da máquina nem atribuir
tempo a regiões OpenMP pelo VTune.

As repetições internas de profiling existem apenas para obter amostras VTune
suficientes. Em Grayscale e Zoom In elas repetem o kernel com buffers já
alocados; nenhuma alocação, conversão de layout ou cópia de restauração é
misturada ao trecho analisado.

## 3. Ler resultados no terminal

```bash
vtune -report summary -r resultados_pcad_hype_vtune_<jobid>/01_adaptive_static_hpc
vtune -report summary -r resultados_pcad_hype_vtune_<jobid>/02_adaptive_dynamic4_hpc
vtune -report hotspots -r resultados_pcad_hype_vtune_<jobid>/07_gaussian_omp_avx2_hotspots
```

No resumo HPC, compare `Effective Physical Core Utilization`, `Memory Bound`,
`DRAM Bandwidth Bound` e o histograma de utilização de banda. No resultado
Memory Access, procure misses de cache e tráfego de DRAM. `Memory Bound` não significa
automaticamente DRAM saturada: pode ser latência ou misses de cache.
