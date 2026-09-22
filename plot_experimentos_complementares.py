#!/usr/bin/env python3
"""Visualiza as duas campanhas complementares executadas no PCAD.

Usa a mediana e os intervalos min--max do CSV de confirmação de schedules e
extrai métricas do resumo textual do VTune HPC Performance. Não depende de
bibliotecas externas para também poder ser executado no cluster.
"""

from __future__ import annotations

import argparse
import csv
import html
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent
COLORS = {"dynamic,1": "#d62728", "dynamic,16": "#2ca02c", "Memory Bound": "#9467bd", "DRAM média": "#1f77b4"}


def esc(value: object) -> str:
    return html.escape(str(value))


def write_csv(path: Path, columns: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def find_number(text: str, expression: str) -> float:
    match = re.search(expression, text)
    return float(match.group(1)) if match else float("nan")


def read_hpc(directory: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for case in sorted(path for path in directory.iterdir() if path.is_dir()):
        configuration = dict(
            line.split("=", 1) for line in (case / "configuration.txt").read_text(encoding="utf-8").splitlines() if "=" in line
        )
        text = (case / "summary.txt").read_text(encoding="utf-8")
        rows.append({
            "Case": case.name,
            "Operation": configuration["operation"],
            "SIMD": configuration["simd"],
            "Threads": int(configuration["threads"]),
            "Profile_iterations": int(configuration["profile_iterations"]),
            "CPI": find_number(text, r"CPI Rate:\s*([0-9.]+)"),
            "Memory_Bound_pct": find_number(text, r"Memory Bound:\s*([0-9.]+)%"),
            "Cache_Bound_pct": find_number(text, r"Cache Bound:\s*([0-9.]+)%"),
            "DRAM_High_BW_pct": find_number(text, r"DRAM Bandwidth Bound:\s*([0-9.]+)%"),
            "DRAM_Average_GBs": find_number(text, r"DRAM, GB/sec\s+\d+\s+[0-9.]+\s+([0-9.]+)"),
            "Physical_Cores_Effective": find_number(text, r"Effective Physical Core Utilization: [0-9.]+% \(([0-9.]+) out of 20\)"),
        })
    return rows


def read_schedules(directory: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with (directory / "benchmark_summary.csv").open(newline="", encoding="utf-8") as source:
        for raw in csv.DictReader(source):
            rows.append({**raw, **{field: float(raw[field]) for field in ("Median_ms", "Min_ms", "Max_ms", "Speedup_vs_Static")}})
    return rows


def horizontal_bars(path: Path, title: str, labels: list[str], series: list[tuple[str, list[float], str]], axis: str, *, baseline: float | None = None, unit: str = "×") -> None:
    width = 1200
    height = max(480, 170 + len(labels) * 62)
    left, right, top, bottom = 280, 145, 70, 82
    plot_width, plot_height = width - left - right, height - top - bottom
    values = [value for _, data, _ in series for value in data]
    if baseline is not None:
        values.append(baseline)
    low = min(0.0, min(values)) if baseline is None else min(min(values), baseline)
    high = max(values)
    pad = (high - low) * 0.10 or 1.0
    low = low - pad if baseline is not None else 0.0
    high += pad
    x = lambda value: left + plot_width * (value - low) / (high - low)
    value_text = lambda value: f"{value:.1f}{unit}" if unit != "×" else f"{value:.3f}×"
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{esc(title)}">',
        f"<title>{esc(title)}</title>",
        "<style>text{font-family:Arial,sans-serif;fill:#202124}.axis{font-size:13px}.small{font-size:12px}.title{font-size:20px;font-weight:700}.grid{stroke:#d9d9d9}.frame{fill:none;stroke:#555}.legend{font-size:12px}</style>",
        f'<text class="title" x="{left}" y="34">{esc(title)}</text>',
    ]
    for tick in [low + (high - low) * index / 4 for index in range(5)]:
        lines.append(f'<line class="grid" x1="{x(tick):.1f}" x2="{x(tick):.1f}" y1="{top}" y2="{top + plot_height}"/>')
        lines.append(f'<text class="axis" text-anchor="middle" x="{x(tick):.1f}" y="{top + plot_height + 23}">{esc(value_text(tick))}</text>')
    lines.append(f'<rect class="frame" x="{left}" y="{top}" width="{plot_width}" height="{plot_height}"/>')
    if baseline is not None:
        lines.append(f'<line x1="{x(baseline):.1f}" x2="{x(baseline):.1f}" y1="{top}" y2="{top + plot_height}" stroke="#555" stroke-width="2" stroke-dasharray="6,4"/>')
    band = plot_height / len(labels)
    bar_height = band / (len(series) + 1.7)
    for row, label in enumerate(labels):
        y0 = top + row * band + band * 0.13
        lines.append(f'<text class="axis" text-anchor="end" x="{left - 12}" y="{y0 + band / 2:.1f}">{esc(label)}</text>')
        for series_index, (_, values_, color) in enumerate(series):
            value = values_[row]
            y = y0 + series_index * bar_height
            start = x(low)
            end = x(value)
            lines.append(f'<rect x="{start:.1f}" y="{y:.1f}" width="{max(0.0, end - start):.1f}" height="{bar_height * .75:.1f}" fill="{color}"/>')
            lines.append(f'<text class="small" x="{min(left + plot_width - 42, end + 6):.1f}" y="{y + bar_height * .58:.1f}">{esc(value_text(value))}</text>')
    for index, (name, _, color) in enumerate(series):
        legend_x = left + index * 190
        lines.append(f'<rect x="{legend_x}" y="{height - 53}" width="15" height="15" fill="{color}"/>')
        lines.append(f'<text class="legend" x="{legend_x + 22}" y="{height - 41}">{esc(name)}</text>')
    lines.append(f'<text class="axis" text-anchor="middle" x="{left + plot_width / 2}" y="{height - 14}">{esc(axis)}</text>')
    lines.append("</svg>")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera gráficos das campanhas complementares do PCAD.")
    parser.add_argument("--hpc", default="resultados_pcad_hype_final_hpc_simd_zoom_grayscale_823348")
    parser.add_argument("--schedules", default="resultados_pcad_hype_final_schedules_confirmacao_10reps_823349")
    parser.add_argument("--out", default="visualizacoes_pcad_hype_final_experimentos_complementares")
    args = parser.parse_args()
    hpc_dir = ROOT / args.hpc
    schedules_dir = ROOT / args.schedules
    output = ROOT / args.out
    figures, tables = output / "figures", output / "tables"
    figures.mkdir(parents=True, exist_ok=True)
    tables.mkdir(parents=True, exist_ok=True)

    hpc = read_hpc(hpc_dir)
    write_csv(tables / "hpc_metricas.csv", list(hpc[0]), hpc)
    hpc_labels = [f"{row['Operation']} — {'SIMD' if row['SIMD'] == 'omp-avx2' else 'sem SIMD'}, T{row['Threads']}" for row in hpc]
    horizontal_bars(figures / "01_hpc_memory_bound.svg", "VTune HPC: fração Memory Bound", hpc_labels, [("Memory Bound", [float(row["Memory_Bound_pct"]) for row in hpc], COLORS["Memory Bound"])], "Memory Bound (% dos slots)", unit="%")
    horizontal_bars(figures / "02_hpc_dram_bandwidth.svg", "VTune HPC: banda DRAM média", hpc_labels, [("DRAM média", [float(row["DRAM_Average_GBs"]) for row in hpc], COLORS["DRAM média"])], "Banda DRAM média (GB/s)", unit=" GB/s")

    schedules = read_schedules(schedules_dir)
    operations = sorted({str(row["Operation"]) for row in schedules})
    detail: list[dict[str, object]] = []
    ratios: dict[str, list[float]] = {"dynamic,1": [], "dynamic,16": []}
    for operation in operations:
        static = next(row for row in schedules if row["Operation"] == operation and row["Schedule"] == "static")
        for schedule, chunk in (("dynamic,1", "1"), ("dynamic,16", "16")):
            dynamic = next(row for row in schedules if row["Operation"] == operation and row["Schedule"] == "dynamic" and row["Chunk"] == chunk)
            ratio = float(static["Median_ms"]) / float(dynamic["Median_ms"])
            ratios[schedule].append(ratio)
            detail.append({
                "Operation": operation, "Schedule": schedule,
                "Static_median_ms": static["Median_ms"], "Static_min_ms": static["Min_ms"], "Static_max_ms": static["Max_ms"],
                "Dynamic_median_ms": dynamic["Median_ms"], "Dynamic_min_ms": dynamic["Min_ms"], "Dynamic_max_ms": dynamic["Max_ms"],
                "Static_over_dynamic_median": ratio,
                "Ranges_overlap": not (float(static["Max_ms"]) < float(dynamic["Min_ms"]) or float(dynamic["Max_ms"]) < float(static["Min_ms"])),
            })
    write_csv(tables / "schedules_confirmacao.csv", list(detail[0]), detail)
    horizontal_bars(figures / "03_schedules_confirmacao.svg", "Confirmação: dynamic versus static, 20 threads", operations, [(schedule, ratios[schedule], COLORS[schedule]) for schedule in ("dynamic,1", "dynamic,16")], "Razão das medianas: static / dynamic", baseline=1.0)

    links = "".join(f'<li><a href="figures/{name}">{description}</a></li>' for name, description in [
        ("01_hpc_memory_bound.svg", "Memory Bound nos oito perfis HPC"),
        ("02_hpc_dram_bandwidth.svg", "Banda DRAM média nos oito perfis HPC"),
        ("03_schedules_confirmacao.svg", "Confirmação de schedules com dez amostras"),
    ])
    (output / "index.html").write_text(f"""<!doctype html><html lang=\"pt-BR\"><head><meta charset=\"utf-8\"><title>Experimentos complementares</title><style>body{{font-family:Arial,sans-serif;max-width:1000px;margin:32px auto;padding:0 18px;color:#202124}}table{{border-collapse:collapse}}td,th{{border:1px solid #ddd;padding:8px}}li{{margin:10px 0}}</style></head><body><h1>Experimentos complementares no PCAD</h1><p>Schedules: razões calculadas sobre medianas de 10 amostras; as tabelas preservam mínimo--máximo. HPC: métricas extraídas do resumo do VTune; a duração total não é comparável entre casos porque o número de repetições internas foi ajustado por caso.</p><h2>Figuras</h2><ol>{links}</ol><h2>Tabelas</h2><ul><li><code>tables/hpc_metricas.csv</code></li><li><code>tables/schedules_confirmacao.csv</code></li></ul></body></html>""", encoding="utf-8")
    print(f"Visualizações geradas em: {output}")


if __name__ == "__main__":
    main()
