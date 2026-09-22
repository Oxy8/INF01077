# Diagnósticos finais: Zoom, schedules e compilador

Estes jobs são complementares à campanha principal. Eles não substituem os
tempos já medidos; isolam causas específicas com afinidade controlada
(`OMP_PLACES=cores`, `OMP_PROC_BIND=close`) e usam mediana, mínimo e máximo.

## 1. Zoom, Flip e evidência do compilador

```bash
sbatch scripts/pcad_hype_diagnostics.sbatch
```

O job de duas horas produz `resultados_pcad_hype_diagnostico_zoom_flip_compilador_<jobid>/`.
O único uso de Python é o resumo final de CSVs; o script procura `python3` e
usa somente a biblioteca padrão, sem dependências adicionais.

| Arquivo | Conteúdo |
| --- | --- |
| `zoom_phases_raw.csv` / `zoom_phases_summary.csv` | Tempo das fases de cópia, interpolação horizontal e vertical do Zoom |
| `flip_raw.csv` / `flip_summary.csv` | Flip Horizontal com `static`, `static,1`, `static,16`, `dynamic,1` e `dynamic,16`, em ordem aleatória |
| `flip_threads_raw.csv` | Linhas executadas e tempo de trabalho de cada thread no Flip |
| `compiler/*vectorization*all.log` | Laços aceitos e recusados pelo vetorizador do GCC, separados por build e arquivo-fonte |
| `compiler/*layout_benchmark.asm` | Assembly comentado de AoS direto, SoA ingênuo e SoA separável |

O Zoom é medido em `static` com 1, 2, 4, 8, 12, 16 e 20 threads, nas builds
escalar Haswell e `omp simd`/AVX2. Em 20 threads, ele compara os cinco
schedules acima e também `dynamic,64`, com páginas recém-descartadas e com
pré-toque paralelo `static` fora da janela de tempo.

Para repetir a confirmação do Flip em outra alocação independente, envie o
mesmo job novamente. Isso é preferível a aumentar repetições dentro do mesmo
nó quando a pergunta é reprodutibilidade entre alocações.

## 2. VTune Hotspots do Zoom

```bash
sbatch scripts/pcad_hype_vtune_zoom_schedules.sbatch
```

O job de uma hora produz `resultados_pcad_hype_vtune_zoom_schedules_<jobid>/`
com três coletas por amostragem de hardware: `static`, `dynamic,1` e
`dynamic,16`. Cada caso contém controle normal validado por hash,
`*_summary.txt` e `*_hotspots.txt`.

O VTune é evidência complementar: compare tempo em `libgomp`, funções das
três fases do Zoom e utilização efetiva dos núcleos. A conclusão causal sobre
o schedule deve vir principalmente de `zoom_phases_summary.csv`, incluindo os
contrastes `static,1` versus `dynamic,1` e `fresh` versus `pretouch-static`.
