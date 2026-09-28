#!/usr/bin/env python3
"""Confronta Memory Bound do VTune com a eficiência da campanha principal.

Uso: python3 plot_hpc_regular_memory.py --result resultados_pcad_hype_hpc_regular_memory_JOBID
Não altera os dados brutos nem usa tempos medidos sob VTune como benchmark.
"""

from __future__ import annotations

import argparse
import csv
import html
import math
from pathlib import Path

from plot_resultados_pcad import ROOT, bar_chart, esc, read_summary, svg_header, write_csv, write_svg


MAIN_REGULAR = ROOT / "resultados_pcad_hype_final_regular_avx2_5reps_822851"
IMAGE = "6000x6000.png"


def scatter_memory_efficiency(path: Path, rows: list[dict[str, float | str]]) -> None:
    """Confronta métricas sem sugerir que uma cause a outra."""
    width, height = 1250, 710
    left, top, plot_w, plot_h = 92, 83, 710, 530
    sx = lambda value: left + plot_w * value / 100
    sy = lambda value: top + plot_h * (1 - value / 100)
    title = "Memory Bound × eficiência — 20 threads, static"
    lines = svg_header(width, height, title)
    lines.append(f'<rect width="{width}" height="{height}" fill="white"/>')
    lines.append(f'<text class="title" x="{left}" y="37">{esc(title)}</text>')
    lines.append(f'<text class="note" x="{left}" y="58">{esc("Memory Bound sob VTune; eficiência dos controles sem VTune. Associação não implica causalidade.")}</text>')
    for tick in range(0, 101, 20):
        x, y = sx(tick), sy(tick)
        lines.append(f'<line class="grid" x1="{x:.1f}" x2="{x:.1f}" y1="{top}" y2="{top + plot_h}"/>')
        lines.append(f'<line class="grid" x1="{left}" x2="{left + plot_w}" y1="{y:.1f}" y2="{y:.1f}"/>')
        lines.append(f'<text class="axis" text-anchor="middle" x="{x:.1f}" y="{top + plot_h + 25}">{tick}%</text>')
        lines.append(f'<text class="axis" text-anchor="end" x="{left - 9}" y="{y + 5:.1f}">{tick}%</text>')
    lines.append(f'<rect class="frame" x="{left}" y="{top}" width="{plot_w}" height="{plot_h}"/>')
    lines.append(f'<text class="axis" text-anchor="middle" x="{left + plot_w / 2}" y="{height - 35}">Memory Bound, 20 threads (%)</text>')
    lines.append(f'<text class="axis" text-anchor="middle" transform="translate(25 {top + plot_h / 2}) rotate(-90)">Eficiência, 20 threads (%)</text>')
    for index, row in enumerate(rows, 1):
        x, y = sx(float(row["Memory_Bound_20t_pct"])), sy(float(row["Efficiency_control_20t_pct"]))
        color = "#e76f00" if row["Operation"] == "Zoom_In" else "#275dad" if str(row["Operation"]).startswith("Gaussian_") else "#555555"
        lines.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="9" fill="{color}"/>')
        lines.append(f'<text x="{x:.1f}" y="{y + 3.8:.1f}" text-anchor="middle" style="font-size:10px;fill:white;font-weight:bold">{index}</text>')
        legend_y = top + 12 + (index - 1) * 29
        lines.append(f'<circle cx="{left + plot_w + 30}" cy="{legend_y}" r="8" fill="{color}"/>')
        lines.append(f'<text class="legend" x="{left + plot_w + 46}" y="{legend_y + 4}">{index}. {esc(str(row["Operation"]))}</text>')
    write_svg(path, lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result", required=True, type=Path, help="Diretório de saída do job HPC regular")
    parser.add_argument("--out", type=Path, help="Diretório das visualizações (padrão: visualizacoes_<job>)")
    args = parser.parse_args()
    result = args.result if args.result.is_absolute() else ROOT / args.result
    output = args.out or ROOT / f"visualizacoes_{result.name}"
    if not output.is_absolute():
        output = ROOT / output
    figures = output / "figures"
    tables = output / "tables"
    figures.mkdir(parents=True, exist_ok=True)
    tables.mkdir(parents=True, exist_ok=True)

    path = result / "memory_bound_17.csv"
    with path.open(newline="", encoding="utf-8") as source:
        measured = list(csv.DictReader(source))
    valid: dict[tuple[str, int], dict[str, float]] = {}
    for row in measured:
        if row["State"] != "ok":
            continue
        operation = row["Operation"]
        threads = int(row["Threads"])
        memory_bound = float(row["Memory_Bound_pct"])
        median = float(row["Control_median_ms"])
        if threads not in (1, 20) or not math.isfinite(memory_bound) or not math.isfinite(median) or not 0 <= memory_bound <= 100 or median <= 0:
            raise ValueError(f"Métrica inválida para {operation}/{threads} threads")
        key = operation, threads
        if key in valid:
            raise ValueError(f"Configuração duplicada: {key}")
        valid[key] = {"memory_bound": memory_bound, "median_ms": median}

    original = read_summary(MAIN_REGULAR)
    original_times = {
        (str(row["Operation"]), int(row["Threads"])): float(row["Median_ms"])
        for row in original
        if row["Image"] == IMAGE and row["Simd_Build"] == "off"
        and row["Schedule"] == "static" and row["Chunk"] == ""
        and row["Threads"] in (1, 20)
    }
    operations = sorted({operation for operation, _ in valid})
    joined = []
    for operation in operations:
        if any((operation, threads) not in valid or (operation, threads) not in original_times for threads in (1, 20)):
            continue
        mb1 = valid[(operation, 1)]["memory_bound"]
        mb20 = valid[(operation, 20)]["memory_bound"]
        new_t1 = valid[(operation, 1)]["median_ms"]
        new_t20 = valid[(operation, 20)]["median_ms"]
        old_t1 = original_times[(operation, 1)]
        old_t20 = original_times[(operation, 20)]
        joined.append({
            "Operation": operation,
            "Memory_Bound_1t_pct": mb1,
            "Memory_Bound_20t_pct": mb20,
            "Efficiency_original_20t_pct": 100 * old_t1 / old_t20 / 20,
            "Efficiency_control_20t_pct": 100 * new_t1 / new_t20 / 20,
            "Original_T1_ms": old_t1,
            "Original_T20_ms": old_t20,
            "Control_T1_ms": new_t1,
            "Control_T20_ms": new_t20,
            "Original_over_control_T1": old_t1 / new_t1,
            "Original_over_control_T20": old_t20 / new_t20,
        })
    if not joined:
        raise ValueError("Nenhuma operação possui coletas válidas em 1 e 20 threads")
    joined.sort(key=lambda row: row["Memory_Bound_20t_pct"], reverse=True)
    write_csv(tables / "memoria_eficiencia_17.csv", list(joined[0]), joined)
    labels = [str(row["Operation"]) for row in joined]
    bar_chart(
        figures / "01_memory_bound_1_20_threads.svg",
        f"Memory Bound por operação — {IMAGE}, static",
        labels,
        [("1 thread", [float(row["Memory_Bound_1t_pct"]) for row in joined], "#1f77b4"),
         ("20 threads", [float(row["Memory_Bound_20t_pct"]) for row in joined], "#ff7f0e")],
        "Memory Bound (%)",
    )
    bar_chart(
        figures / "02_controle_vs_campanha_principal.svg",
        f"Controle de tempo versus campanha principal — {IMAGE}, static",
        labels,
        [("1 thread", [float(row["Original_over_control_T1"]) for row in joined], "#1f77b4"),
         ("20 threads", [float(row["Original_over_control_T20"]) for row in joined], "#ff7f0e")],
        "Razão das medianas (principal / controle)", baseline=1.0,
    )
    scatter_memory_efficiency(figures / "03_memory_bound_vs_eficiencia_20t.svg", joined)
    missing = 17 - len(joined)
    content = f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>VTune HPC: operações regulares</title>
<style>body{{font-family:Arial,sans-serif;max-width:1000px;margin:32px auto;padding:0 20px;color:#202124}}a{{color:#0757a8}}li{{margin:10px 0}}</style></head>
<body><h1>VTune HPC: operações regulares</h1><p>Fonte: {html.escape(result.name)}. {len(joined)} operações têm medições válidas em 1 e 20 threads; {missing} incompletas. Imagem {IMAGE}, build sem SIMD, schedule static.</p>
<ol><li><a href="figures/01_memory_bound_1_20_threads.svg">Memory Bound de cada operação, 1 e 20 threads</a></li>
<li><a href="figures/02_controle_vs_campanha_principal.svg">Reprodutibilidade dos tempos sem VTune</a></li>
<li><a href="figures/03_memory_bound_vs_eficiencia_20t.svg">Memory Bound versus eficiência, 20 threads</a></li></ol>
<p><a href="tables/memoria_eficiencia_17.csv">Tabela cruzada: Memory Bound, eficiência e tempos</a>.</p>
<p>Memory Bound é a fração estimada de slots do pipeline afetada por espera na hierarquia de memória; não é porcentagem do tempo nem prova isolada de saturação da DRAM. As coletas VTune contêm apenas as chamadas da operação, enquanto os controles de tempo foram executados sem o profiler. Diferenças de nó, versão e amostragem ainda precisam ser consideradas.</p></body></html>"""
    (output / "index.html").write_text(content, encoding="utf-8")
    print(f"Visualizações: {output / 'index.html'} ({len(joined)}/17 operações completas)")


if __name__ == "__main__":
    main()
