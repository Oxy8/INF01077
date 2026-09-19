#!/usr/bin/env python3
"""Gera tabelas e gráficos SVG/HTML para a campanha OpenMP no PCAD.

Não depende de pandas, matplotlib ou seaborn. Por padrão, encontra os três
diretórios mais recentes de resultados PCAD e os classifica como regular,
adaptativo e SMT. Os gráficos usam a média das cinco amostras e, quando
aplicável, mostram o desvio-padrão registrado no CSV de resumo.

Uso:
    python plot_resultados_pcad.py
    python plot_resultados_pcad.py --out resultados_visualizados
    python plot_resultados_pcad.py --regular resultados_pcad_hype_822669 \
        --adaptive resultados_pcad_hype_822670 --smt resultados_pcad_hype_822671
"""

from __future__ import annotations

import argparse
import csv
import html
import math
import os
import re
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Callable, Iterable, Sequence


ROOT = Path(__file__).resolve().parent
PALETTE = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e", "#17becf", "#8c564b", "#e377c2"]
SCHEDULE_COLORS = {"static": "#1f77b4", "dynamic,1": "#d62728", "dynamic,16": "#2ca02c"}
SIMD_COLORS = {"off": "#555555", "omp": "#8a2be2"}
THREADS = [1, 2, 4, 8, 12, 16, 20]
SELECTED_OPS = ["Grayscale", "Negative", "Zoom_In", "Gaussian_3x3", "Gaussian_11x11"]


def number(value: str) -> float:
    return float(value) if value else 0.0


def read_summary(directory: Path) -> list[dict[str, object]]:
    path = directory / "benchmark_summary.csv"
    with path.open(newline="", encoding="utf-8") as source:
        rows: list[dict[str, object]] = []
        for raw in csv.DictReader(source):
            row: dict[str, object] = dict(raw)
            for field in ("Width", "Height", "Threads", "Samples"):
                row[field] = int(raw[field])
            for field in ("Median_ms", "Min_ms", "Max_ms", "Mean_ms", "StdDev_ms", "Speedup_vs_Static"):
                row[field] = number(raw[field])
            rows.append(row)
    return rows


def job_id(directory: Path) -> int:
    match = re.search(r"(\d+)$", directory.name)
    return int(match.group(1)) if match else -1


def classify(rows: list[dict[str, object]]) -> str | None:
    operations = {str(row["Operation"]) for row in rows}
    threads = {int(row["Threads"]) for row in rows}
    if 40 in threads:
        return "smt"
    if operations == {"Adaptive_Median"}:
        return "adaptive"
    if len(operations) >= 10:
        return "regular"
    return None


def resolve_inputs(args: argparse.Namespace) -> dict[str, Path]:
    explicit = {"regular": args.regular, "adaptive": args.adaptive, "smt": args.smt}
    resolved: dict[str, Path] = {}
    candidates: dict[str, list[Path]] = defaultdict(list)
    for directory in ROOT.glob("resultados_pcad_hype_*"):
        summary = directory / "benchmark_summary.csv"
        if not summary.exists():
            continue
        kind = classify(read_summary(directory))
        if kind:
            candidates[kind].append(directory)
    for kind, given in explicit.items():
        if given:
            directory = Path(given)
            if not directory.is_absolute():
                directory = ROOT / directory
            resolved[kind] = directory
        elif candidates[kind]:
            resolved[kind] = max(candidates[kind], key=job_id)
        else:
            raise SystemExit(f"Não encontrei resultados para a campanha '{kind}'.")
    return resolved


def esc(value: object) -> str:
    return html.escape(str(value))


def fmt_ms(value: float) -> str:
    if value >= 1000:
        return f"{value / 1000:.2f} s"
    return f"{value:.2f} ms"


def grouped(rows: Iterable[dict[str, object]], keys: Sequence[str]) -> dict[tuple[object, ...], list[dict[str, object]]]:
    result: dict[tuple[object, ...], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        result[tuple(row[key] for key in keys)].append(row)
    return result


def mean(rows: Iterable[dict[str, object]], field: str = "Mean_ms") -> float:
    values = [float(row[field]) for row in rows]
    return statistics.fmean(values) if values else math.nan


def geometric_mean(values: Iterable[float]) -> float:
    valid = [value for value in values if value > 0 and math.isfinite(value)]
    return math.exp(statistics.fmean(math.log(value) for value in valid)) if valid else math.nan


def svg_header(width: int, height: int, title: str) -> list[str]:
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{esc(title)}">',
        f"<title>{esc(title)}</title>",
        "<style>text{font-family:Arial,sans-serif;fill:#202124}.axis{font-size:13px}.small{font-size:12px}.title{font-size:20px;font-weight:700}.legend{font-size:12px}.grid{stroke:#d9d9d9;stroke-width:1}.frame{fill:none;stroke:#555;stroke-width:1}.note{font-size:11px;fill:#555}</style>",
    ]


def write_svg(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines + ["</svg>"]), encoding="utf-8")


def ticks(low: float, high: float, count: int = 5) -> list[float]:
    if not math.isfinite(low) or not math.isfinite(high):
        return [0.0, 1.0]
    if low == high:
        pad = abs(low) * 0.1 or 1.0
        low, high = low - pad, high + pad
    step = (high - low) / (count - 1)
    return [low + step * i for i in range(count)]


def line_chart(
    path: Path,
    title: str,
    x_values: Sequence[object],
    series: Sequence[tuple[str, Sequence[float], str, Sequence[float] | None]],
    y_label: str,
    *,
    y_zero: bool = False,
    reference: tuple[str, float, str] | None = None,
    numeric_x: bool = False,
    log_x: bool = False,
    x_label: str = "Threads",
) -> None:
    width, height = 1200, 700
    left, right, top, bottom = 105, 270, 72, 95
    plot_w, plot_h = width - left - right, height - top - bottom
    values = [value for _, data, _, errors in series for value in data]
    for _, data, _, errors in series:
        if errors:
            values.extend(v + e for v, e in zip(data, errors))
            values.extend(v - e for v, e in zip(data, errors))
    if reference:
        values.append(reference[1])
    low, high = min(values), max(values)
    if y_zero:
        low = min(0.0, low)
    pad = (high - low) * 0.09 or 1.0
    low -= 0 if y_zero else pad
    high += pad
    if log_x:
        numeric_values = [math.log2(float(value)) for value in x_values]
        x_low, x_high = min(numeric_values), max(numeric_values)
        sx = lambda i: left + plot_w * (numeric_values[i] - x_low) / (x_high - x_low)
    elif numeric_x:
        numeric_values = [float(value) for value in x_values]
        x_low, x_high = min(numeric_values), max(numeric_values)
        sx = lambda i: left + plot_w * (numeric_values[i] - x_low) / (x_high - x_low)
    else:
        x_count = max(1, len(x_values) - 1)
        sx = lambda i: left + plot_w * i / x_count
    sy = lambda y: top + plot_h * (high - y) / (high - low)
    lines = svg_header(width, height, title)
    lines.append(f'<text class="title" x="{left}" y="34">{esc(title)}</text>')
    for value in ticks(low, high):
        y = sy(value)
        lines.append(f'<line class="grid" x1="{left}" x2="{left + plot_w}" y1="{y:.1f}" y2="{y:.1f}"/>')
        lines.append(f'<text class="axis" text-anchor="end" x="{left - 10}" y="{y + 5:.1f}">{esc(fmt_ms(value) if "ms" in y_label else f"{value:.2f}")}</text>')
    lines.append(f'<rect class="frame" x="{left}" y="{top}" width="{plot_w}" height="{plot_h}"/>')
    for i, label in enumerate(x_values):
        x = sx(i)
        lines.append(f'<line class="frame" x1="{x:.1f}" x2="{x:.1f}" y1="{top + plot_h}" y2="{top + plot_h + 6}"/>')
        lines.append(f'<text class="axis" text-anchor="middle" x="{x:.1f}" y="{top + plot_h + 27}">{esc(label)}</text>')
    if reference:
        name, value, color = reference
        y = sy(value)
        lines.append(f'<line x1="{left}" x2="{left + plot_w}" y1="{y:.1f}" y2="{y:.1f}" stroke="{color}" stroke-width="2" stroke-dasharray="7,5"/>')
        lines.append(f'<text class="note" x="{left + plot_w + 10}" y="{y + 4:.1f}">{esc(name)}</text>')
    for index, (name, data, color, errors) in enumerate(series):
        points = " ".join(f"{sx(i):.1f},{sy(value):.1f}" for i, value in enumerate(data))
        lines.append(f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="2.5"/>')
        if errors:
            for i, (value, error) in enumerate(zip(data, errors)):
                x, y0, y1 = sx(i), sy(value - error), sy(value + error)
                lines.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{y0:.1f}" y2="{y1:.1f}" stroke="{color}" stroke-width="1.2"/>')
        for i, value in enumerate(data):
            lines.append(f'<circle cx="{sx(i):.1f}" cy="{sy(value):.1f}" r="4" fill="{color}"/>')
        y = top + 22 * index
        lines.append(f'<line x1="{left + plot_w + 18}" x2="{left + plot_w + 42}" y1="{y}" y2="{y}" stroke="{color}" stroke-width="3"/>')
        lines.append(f'<text class="legend" x="{left + plot_w + 50}" y="{y + 4}">{esc(name)}</text>')
    lines.append(f'<text class="axis" text-anchor="middle" x="{left + plot_w / 2}" y="{height - 25}">{esc(x_label)}</text>')
    lines.append(f'<text class="axis" text-anchor="middle" transform="translate(25 {top + plot_h / 2}) rotate(-90)">{esc(y_label)}</text>')
    write_svg(path, lines)


def bar_chart(path: Path, title: str, labels: Sequence[str], groups_: Sequence[tuple[str, Sequence[float], str]], y_label: str, *, baseline: float | None = None) -> None:
    width, height = 1200, max(540, 310 + 34 * len(labels))
    left, right, top, bottom = 255, 190, 70, 75
    plot_w, plot_h = width - left - right, height - top - bottom
    values = [value for _, data, _ in groups_ for value in data]
    if baseline is not None:
        values.append(baseline)
    is_speedup = "Speedup" in y_label
    low, high = (min(values), max(values)) if is_speedup else (min(0.0, min(values)), max(values))
    if low == high:
        low, high = low - (0.1 if is_speedup else 1), high + (0.1 if is_speedup else 1)
    pad = (high - low) * 0.1
    if is_speedup:
        low -= pad
    high += pad
    sx = lambda value: left + plot_w * (value - low) / (high - low)
    band = plot_h / max(1, len(labels))
    bar_h = band / (len(groups_) + 1.5)
    lines = svg_header(width, height, title)
    lines.append(f'<text class="title" x="{left}" y="34">{esc(title)}</text>')
    for value in ticks(low, high):
        x = sx(value)
        lines.append(f'<line class="grid" x1="{x:.1f}" x2="{x:.1f}" y1="{top}" y2="{top + plot_h}"/>')
        text = fmt_ms(value) if "ms" in y_label else f"{value:.2f}×"
        lines.append(f'<text class="axis" text-anchor="middle" x="{x:.1f}" y="{top + plot_h + 22}">{esc(text)}</text>')
    lines.append(f'<rect class="frame" x="{left}" y="{top}" width="{plot_w}" height="{plot_h}"/>')
    if baseline is not None:
        x = sx(baseline)
        lines.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{top}" y2="{top + plot_h}" stroke="#555" stroke-width="2" stroke-dasharray="6,4"/>')
    for row, label in enumerate(labels):
        base_y = top + band * row + band * 0.16
        lines.append(f'<text class="axis" text-anchor="end" x="{left - 12}" y="{base_y + band / 2:.1f}">{esc(label)}</text>')
        for idx, (_, data, color) in enumerate(groups_):
            value = data[row]
            y = base_y + idx * bar_h
            # Horizontal bars improve label readability. Width is on numeric x scale.
            x_value = sx(value)
            lines.append(f'<rect x="{sx(low):.1f}" y="{y:.1f}" width="{max(0, x_value-sx(low)):.1f}" height="{bar_h * .78:.1f}" fill="{color}"/>')
            lines.append(f'<text class="small" x="{min(left + plot_w - 48, x_value + 6):.1f}" y="{y + bar_h * .61:.1f}">{esc(fmt_ms(value) if "ms" in y_label else f"{value:.2f}×")}</text>')
    for idx, (name, _, color) in enumerate(groups_):
        x = left + idx * 180
        lines.append(f'<rect x="{x}" y="{height - 48}" width="15" height="15" fill="{color}"/>')
        lines.append(f'<text class="legend" x="{x + 22}" y="{height - 36}">{esc(name)}</text>')
    lines.append(f'<text class="axis" text-anchor="middle" x="{left + plot_w / 2}" y="{height - 12}">{esc(y_label)}</text>')
    write_svg(path, lines)


def heatmap(path: Path, title: str, x_labels: Sequence[str], y_labels: Sequence[str], values: list[list[float]], legend: str) -> None:
    width, height = 1200, max(560, 150 + 42 * len(y_labels))
    left, top, right, bottom = 250, 105, 120, 100
    plot_w, plot_h = width - left - right, height - top - bottom
    flat = [value for row in values for value in row if math.isfinite(value)]
    magnitude = max(abs(value - 1.0) for value in flat) if flat else 0.1
    magnitude = max(magnitude, 0.03)
    cell_w, cell_h = plot_w / len(x_labels), plot_h / len(y_labels)
    lines = svg_header(width, height, title)
    lines.append(f'<text class="title" x="{left}" y="34">{esc(title)}</text>')
    lines.append(f'<text class="note" x="{left}" y="58">{esc(legend)}</text>')
    for y_idx, label in enumerate(y_labels):
        y = top + y_idx * cell_h
        lines.append(f'<text class="axis" text-anchor="end" x="{left - 10}" y="{y + cell_h * .63:.1f}">{esc(label)}</text>')
        for x_idx, value in enumerate(values[y_idx]):
            ratio = max(-1, min(1, (value - 1.0) / magnitude))
            if ratio >= 0:
                red, green, blue = int(235 - 130 * ratio), int(245 - 45 * ratio), int(255 - 185 * ratio)
            else:
                red, green, blue = int(255 - 25 * -ratio), int(245 - 120 * -ratio), int(235 - 145 * -ratio)
            x = left + x_idx * cell_w
            lines.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{cell_w:.1f}" height="{cell_h:.1f}" fill="rgb({red},{green},{blue})" stroke="#fff"/>')
            lines.append(f'<text class="small" text-anchor="middle" x="{x + cell_w/2:.1f}" y="{y + cell_h*.62:.1f}">{value:.2f}×</text>')
    for x_idx, label in enumerate(x_labels):
        x = left + (x_idx + .5) * cell_w
        lines.append(f'<text class="axis" text-anchor="middle" x="{x:.1f}" y="{top - 12}">{esc(label)}</text>')
    lines.append(f'<rect class="frame" x="{left}" y="{top}" width="{plot_w}" height="{plot_h}"/>')
    write_svg(path, lines)


def exact(rows: Iterable[dict[str, object]], **criteria: object) -> list[dict[str, object]]:
    return [row for row in rows if all(row[key] == value for key, value in criteria.items())]


def lookup(rows: Iterable[dict[str, object]], **criteria: object) -> dict[str, object] | None:
    found = exact(rows, **criteria)
    return found[0] if found else None


def safe_ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else math.nan


def write_csv(path: Path, columns: Sequence[str], rows: Iterable[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as destination:
        writer = csv.DictWriter(destination, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def regular_figures(rows: list[dict[str, object]], figures: Path, tables: Path) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    images = sorted({str(row["Image"]) for row in rows})
    operations = sorted({str(row["Operation"]) for row in rows})

    # Reconstitui o tempo do conjunto das 17 operações, equivalente ao
    # "pipeline completo" do script legado, mas sem misturar schedules.
    totals: list[dict[str, object]] = []
    for key, group in grouped(rows, ["Image", "Threads", "Schedule", "Chunk", "Simd_Build"]).items():
        totals.append({"Image": key[0], "Threads": key[1], "Schedule": key[2], "Chunk": key[3], "Simd": key[4], "Total_operations_ms": sum(float(row["Mean_ms"]) for row in group), "Operations": len(group)})
    write_csv(tables / "tempo_total_operacoes_regulares.csv", ["Image", "Threads", "Schedule", "Chunk", "Simd", "Total_operations_ms", "Operations"], totals)
    static_totals = [row for row in totals if row["Schedule"] == "static"]
    total_series = []
    total_speedup_series = []
    total_efficiency_series = []
    for index, image_name in enumerate(images):
        for simd in ("off", "omp"):
            data = [next((row for row in static_totals if row["Image"] == image_name and row["Threads"] == thread and row["Simd"] == simd), None) for thread in THREADS]
            if any(row is None for row in data):
                continue
            values = [float(row["Total_operations_ms"]) for row in data if row]
            label = f"{image_name} ({simd})"
            color = PALETTE[(index * 2 + (1 if simd == "omp" else 0)) % len(PALETTE)]
            total_series.append((label, values, color, None))
            speedups = [safe_ratio(values[0], value) for value in values]
            total_speedup_series.append((label, speedups, color, None))
            total_efficiency_series.append((label, [speedup / thread * 100 for speedup, thread in zip(speedups, THREADS)], color, None))
    path = figures / "00_tempo_total_operacoes_static.svg"
    line_chart(path, "Tempo total das 17 operações regulares — static", THREADS, total_series, "Tempo médio (ms)", numeric_x=True)
    links.append((path.name, "Tempo total do conjunto de operações por threads"))
    path = figures / "00_speedup_total_operacoes_static.svg"
    line_chart(path, "Speedup do conjunto de operações regulares — static", THREADS, total_speedup_series + [("ideal", [float(thread) for thread in THREADS], "#555", None)], "Speedup (T1 / Tn)", numeric_x=True)
    links.append((path.name, "Speedup do conjunto de operações por threads"))
    path = figures / "00_eficiencia_total_operacoes_static.svg"
    line_chart(path, "Eficiência do conjunto de operações regulares — static", THREADS, total_efficiency_series, "Eficiência (%)", reference=("ideal: 100%", 100.0, "#555"), numeric_x=True)
    links.append((path.name, "Eficiência do conjunto de operações por threads"))

    dataset_totals: list[dict[str, object]] = []
    for simd in ("off", "omp"):
        for schedule, chunk in (("static", ""), ("dynamic", "1"), ("dynamic", "16")):
            selected = [row for row in totals if row["Threads"] == 20 and row["Simd"] == simd and row["Schedule"] == schedule and row["Chunk"] == chunk]
            dataset_totals.append({"Simd": simd, "Schedule": schedule if not chunk else f"{schedule},{chunk}", "Total_dataset_ms": sum(float(row["Total_operations_ms"]) for row in selected)})
    write_csv(tables / "tempo_total_dataset_schedules_20_threads.csv", ["Simd", "Schedule", "Total_dataset_ms"], dataset_totals)
    schedule_names = ["static", "dynamic,1", "dynamic,16"]
    path = figures / "00_tempo_total_dataset_por_schedule.svg"
    bar_chart(path, "Tempo total das operações regulares — 20 threads", ["SIMD off", "SIMD omp"], [(schedule, [float(next(row for row in dataset_totals if row["Simd"] == simd and row["Schedule"] == schedule)["Total_dataset_ms"]) for simd in ("off", "omp")], SCHEDULE_COLORS[schedule]) for schedule in schedule_names], "Tempo médio (ms)")
    links.append((path.name, "Tempo total do dataset por schedule, como no script legado"))

    # SIMD effect by operation across all comparable regular configurations.
    simd_pairs: list[dict[str, object]] = []
    for key, group in grouped(rows, ["Image", "Operation", "Threads", "Schedule", "Chunk"]).items():
        off = next((row for row in group if row["Simd_Build"] == "off"), None)
        omp = next((row for row in group if row["Simd_Build"] == "omp"), None)
        if off and omp and off["Simd_Eligible"] == "yes":
            simd_pairs.append({"Image": key[0], "Operation": key[1], "Threads": key[2], "Schedule": key[3], "Chunk": key[4], "Off_ms": off["Mean_ms"], "OMP_ms": omp["Mean_ms"], "Speedup_off_over_omp": safe_ratio(float(off["Mean_ms"]), float(omp["Mean_ms"]))})
    simd_by_op = []
    for op, group in grouped(simd_pairs, ["Operation"]).items():
        speedup = geometric_mean(float(row["Speedup_off_over_omp"]) for row in group)
        simd_by_op.append({"Operation": op[0], "Comparisons": len(group), "Geometric_mean_speedup": speedup})
    simd_by_op.sort(key=lambda row: float(row["Geometric_mean_speedup"]), reverse=True)
    write_csv(tables / "simd_por_operacao.csv", ["Operation", "Comparisons", "Geometric_mean_speedup"], simd_by_op)
    path = figures / "01_simd_ganho_por_operacao.svg"
    bar_chart(path, "SIMD explícito: ganho geométrico por operação", [str(r["Operation"]) for r in simd_by_op], [("off / omp", [float(r["Geometric_mean_speedup"]) for r in simd_by_op], "#8a2be2")], "Speedup (off / omp)", baseline=1.0)
    links.append((path.name, "Ganho SIMD agregado por operação regular"))

    # SIMD matrix at the larger image and static schedule gives a readable, controlled view.
    image = max(images, key=lambda name: next(int(r["Width"]) * int(r["Height"]) for r in rows if r["Image"] == name))
    eligible_ops = sorted({str(row["Operation"]) for row in rows if row["Image"] == image and row["Simd_Eligible"] == "yes"})
    matrix = []
    for op in eligible_ops:
        line = []
        for thread in THREADS:
            off = lookup(rows, Image=image, Operation=op, Threads=thread, Schedule="static", Chunk="", Simd_Build="off")
            omp = lookup(rows, Image=image, Operation=op, Threads=thread, Schedule="static", Chunk="", Simd_Build="omp")
            line.append(safe_ratio(float(off["Mean_ms"]), float(omp["Mean_ms"])) if off and omp else math.nan)
        matrix.append(line)
    path = figures / "02_simd_matriz_36mp_static.svg"
    heatmap(path, f"SIMD por threads — {image}, static", [str(t) for t in THREADS], eligible_ops, matrix, "Células acima de 1× favorecem SIMD explícito (tempo off / tempo omp).")
    links.append((path.name, "Mapa de calor do efeito SIMD por operação e threads"))

    # Dynamic schedule gain at 20 threads, aggregated over both images and SIMD variants.
    schedules = ["dynamic,1", "dynamic,16"]
    schedule_rows: list[dict[str, object]] = []
    for op in operations:
        values: dict[str, list[float]] = {schedule: [] for schedule in schedules}
        for image_name in images:
            for simd in ("off", "omp"):
                static = lookup(rows, Image=image_name, Operation=op, Threads=20, Schedule="static", Chunk="", Simd_Build=simd)
                if not static:
                    continue
                for schedule in schedules:
                    kind, chunk = schedule.split(",")
                    dynamic = lookup(rows, Image=image_name, Operation=op, Threads=20, Schedule=kind, Chunk=chunk, Simd_Build=simd)
                    if dynamic:
                        values[schedule].append(safe_ratio(float(static["Mean_ms"]), float(dynamic["Mean_ms"])))
        schedule_rows.append({"Operation": op, **{schedule: geometric_mean(values[schedule]) for schedule in schedules}})
    write_csv(tables / "schedules_regulares_20_threads.csv", ["Operation", *schedules], schedule_rows)
    path = figures / "03_schedules_regulares_20_threads.svg"
    bar_chart(path, "Schedules dinâmicos versus static — operações regulares, 20 threads", operations, [(schedule, [float(next(r for r in schedule_rows if r["Operation"] == op)[schedule]) for op in operations], SCHEDULE_COLORS[schedule]) for schedule in schedules], "Speedup (static / dynamic)", baseline=1.0)
    links.append((path.name, "Impacto de dynamic,1 e dynamic,16 nas operações regulares"))

    # Representative scalability and efficiency retain the important plots from the legacy script.
    for image_name in images:
        lines: list[tuple[str, Sequence[float], str, Sequence[float] | None]] = []
        efficiency: list[tuple[str, Sequence[float], str, Sequence[float] | None]] = []
        for op_index, op in enumerate(SELECTED_OPS):
            for simd in ("off", "omp"):
                data = [lookup(rows, Image=image_name, Operation=op, Threads=t, Schedule="static", Chunk="", Simd_Build=simd) for t in THREADS]
                if any(item is None for item in data):
                    continue
                label = f"{op} ({simd})"
                color = PALETTE[(op_index * 2 + (1 if simd == 'omp' else 0)) % len(PALETTE)]
                values = [float(item["Mean_ms"]) for item in data if item]
                errors = [float(item["StdDev_ms"]) for item in data if item]
                lines.append((label, values, color, errors))
                t1 = values[0]
                efficiency.append((label, [safe_ratio(t1, value) / thread * 100 for value, thread in zip(values, THREADS)], color, None))
        suffix = Path(image_name).stem
        path = figures / f"04_escalabilidade_static_{suffix}.svg"
        line_chart(path, f"Escalabilidade static — {image_name}", THREADS, lines, "Tempo médio (ms)", numeric_x=True)
        links.append((path.name, f"Tempo por threads para operações representativas em {image_name}"))
        path = figures / f"05_eficiencia_static_{suffix}.svg"
        line_chart(path, f"Eficiência paralela — {image_name}", THREADS, efficiency, "Eficiência (%)", reference=("ideal: 100%", 100.0, "#555"), numeric_x=True)
        links.append((path.name, f"Eficiência T1/(Tn·n) das operações representativas em {image_name}"))
    return links


def adaptive_figures(rows: list[dict[str, object]], figures: Path, tables: Path) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    images = sorted({str(row["Image"]) for row in rows})
    chunks = [1, 4, 16, 64, 256]
    chunk_configs = [("static", "", "static")] + [("dynamic", str(chunk), f"dynamic,{chunk}") for chunk in chunks]

    # Chunk sweep: normalize each image to its own static reference, revealing load imbalance independent of size.
    chunk_table: list[dict[str, object]] = []
    for image in images:
        for simd in ("off", "omp"):
            static = lookup(rows, Image=image, Threads=20, Schedule="static", Chunk="", Simd_Build=simd)
            if not static:
                continue
            for chunk in chunks:
                dynamic = lookup(rows, Image=image, Threads=20, Schedule="dynamic", Chunk=str(chunk), Simd_Build=simd)
                if dynamic:
                    chunk_table.append({"Image": image, "Simd": simd, "Chunk": chunk, "Static_ms": static["Mean_ms"], "Dynamic_ms": dynamic["Mean_ms"], "Speedup_static_over_dynamic": safe_ratio(float(static["Mean_ms"]), float(dynamic["Mean_ms"]))})
    write_csv(tables / "adaptive_chunks_20_threads.csv", ["Image", "Simd", "Chunk", "Static_ms", "Dynamic_ms", "Speedup_static_over_dynamic"], chunk_table)

    # Tempo absoluto por imagem: este é o gráfico principal da varredura.
    # Diferente das curvas normalizadas abaixo, mantém static e todos os cinco
    # chunks dinâmicos na escala original de cada imagem.
    for image in images:
        series = []
        labels = [label for _, _, label in chunk_configs]
        for simd in ("off", "omp"):
            data = [lookup(rows, Image=image, Threads=20, Schedule=schedule, Chunk=chunk, Simd_Build=simd) for schedule, chunk, _ in chunk_configs]
            if any(item is None for item in data):
                continue
            series.append((f"SIMD {simd}", [float(item["Mean_ms"]) for item in data if item], SIMD_COLORS[simd], [float(item["StdDev_ms"]) for item in data if item]))
        if series:
            path = figures / f"06_tempo_chunks_adaptativo_{Path(image).stem}.svg"
            line_chart(path, f"Filtro adaptativo: tempo por chunk — {image}, 20 threads", labels, series, "Tempo médio (ms)", x_label="Schedule OpenMP")
            links.append((path.name, f"Tempo static e dynamic por chunk — {image}"))

    # Soma por configuração, útil como uma visão global da campanha. Não é
    # confundida com a média de imagens: o título registra que é uma soma.
    total_rows: list[dict[str, object]] = []
    totals: dict[tuple[str, str], float] = {}
    for simd in ("off", "omp"):
        for schedule, chunk, label in chunk_configs:
            selected = [lookup(rows, Image=image, Threads=20, Schedule=schedule, Chunk=chunk, Simd_Build=simd) for image in images]
            if any(item is None for item in selected):
                continue
            total = sum(float(item["Mean_ms"]) for item in selected if item)
            totals[(simd, label)] = total
            total_rows.append({"Simd": simd, "Schedule": label, "Images": len(images), "Total_ms": total})
    write_csv(tables / "adaptive_total_por_chunk_20_threads.csv", ["Simd", "Schedule", "Images", "Total_ms"], total_rows)
    if len(totals) == len(chunk_configs) * 2:
        path = figures / "06_tempo_total_chunks_adaptativo.svg"
        bar_chart(path, "Filtro adaptativo: soma dos tempos por chunk — 8 imagens, 20 threads", ["SIMD off", "SIMD omp"], [(label, [totals[(simd, label)] for simd in ("off", "omp")], PALETTE[index % len(PALETTE)]) for index, (_, _, label) in enumerate(chunk_configs)], "Tempo médio (ms)")
        links.append((path.name, "Soma dos tempos static e dynamic por chunk nas 8 imagens"))

    # As curvas normalizadas respondem à pergunta complementar: quanto cada
    # chunk ganha ou perde contra static na própria imagem.
    for simd in ("off", "omp"):
        series = []
        for index, image in enumerate(images):
            subset = [row for row in chunk_table if row["Image"] == image and row["Simd"] == simd]
            mapping = {int(row["Chunk"]): float(row["Speedup_static_over_dynamic"]) for row in subset}
            if len(mapping) == len(chunks):
                series.append((image, [mapping[chunk] for chunk in chunks], PALETTE[index % len(PALETTE)], None))
        path = figures / f"06_chunks_adaptativo_{simd}.svg"
        line_chart(path, f"Filtro adaptativo: efeito do chunk — SIMD {simd}, 20 threads", chunks, series, "Speedup (static / dynamic)", reference=("empate", 1.0, "#555"), log_x=True, x_label="Tamanho do chunk (log₂)")
        links.append((path.name, f"Varredura de chunk do adaptativo com SIMD {simd}"))

    # Direct static/dynamic16 comparison on all images.
    compare_rows: list[dict[str, object]] = []
    for image in images:
        for simd in ("off", "omp"):
            static = lookup(rows, Image=image, Threads=20, Schedule="static", Chunk="", Simd_Build=simd)
            dynamic = lookup(rows, Image=image, Threads=20, Schedule="dynamic", Chunk="16", Simd_Build=simd)
            if static and dynamic:
                compare_rows.append({"Image": image, "Simd": simd, "Static_ms": static["Mean_ms"], "Dynamic16_ms": dynamic["Mean_ms"], "Speedup_static_over_dynamic16": safe_ratio(float(static["Mean_ms"]), float(dynamic["Mean_ms"]))})
    write_csv(tables / "adaptive_static_vs_dynamic16_20_threads.csv", ["Image", "Simd", "Static_ms", "Dynamic16_ms", "Speedup_static_over_dynamic16"], compare_rows)
    path = figures / "07_adaptativo_static_vs_dynamic16.svg"
    bar_chart(path, "Filtro adaptativo, 20 threads: dynamic,16 versus static", images, [(simd, [float(next(r for r in compare_rows if r["Image"] == image and r["Simd"] == simd)["Speedup_static_over_dynamic16"]) for image in images], SIMD_COLORS[simd]) for simd in ("off", "omp")], "Speedup (static / dynamic,16)", baseline=1.0)
    links.append((path.name, "Ganho do dynamic,16 por imagem adaptativa"))

    # Scalability: two representative images expose regular and irregular detail distributions.
    representatives = ["control_half_noise_6000x6000.png", "rain_paisage.jpg"]
    for image in [name for name in representatives if name in images]:
        series = []
        for simd in ("off", "omp"):
            for schedule, color in (("static", SIMD_COLORS[simd]), ("dynamic", "#d62728" if simd == "off" else "#ff7f0e")):
                data = []
                for thread in THREADS:
                    chunk = "" if schedule == "static" else "16"
                    row = lookup(rows, Image=image, Threads=thread, Schedule=schedule, Chunk=chunk, Simd_Build=simd)
                    if row:
                        data.append(row)
                if len(data) == len(THREADS):
                    series.append((f"{simd}, {schedule}{',16' if schedule == 'dynamic' else ''}", [float(row["Mean_ms"]) for row in data], color, [float(row["StdDev_ms"]) for row in data]))
        path = figures / f"08_escalabilidade_adaptativo_{Path(image).stem}.svg"
        line_chart(path, f"Escalabilidade do filtro adaptativo — {image}", THREADS, series, "Tempo médio (ms)", numeric_x=True)
        links.append((path.name, f"Escalabilidade static e dynamic,16 para {image}"))
    return links


def smt_figures(rows: list[dict[str, object]], figures: Path, tables: Path) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    workloads = sorted({(str(row["Image"]), str(row["Operation"])) for row in rows}, key=lambda item: item[1])
    workload_labels = {"Adaptive_Median": "Adaptativo (meio-a-meio)", "Gaussian_11x11": "Gaussian 11×11", "Grayscale": "Grayscale"}
    labels = [workload_labels.get(operation, operation) for _, operation in workloads]
    time_rows: list[dict[str, object]] = []
    speedups: dict[str, list[float]] = {"static": [], "dynamic,16": []}
    values_by_config: dict[str, list[float]] = {"20 threads, static": [], "40 threads, static": [], "20 threads, dynamic,16": [], "40 threads, dynamic,16": []}
    for image, operation in workloads:
        for schedule, chunk, label in (("static", "", "static"), ("dynamic", "16", "dynamic,16")):
            r20 = lookup(rows, Image=image, Operation=operation, Threads=20, Schedule=schedule, Chunk=chunk, Simd_Build="omp")
            r40 = lookup(rows, Image=image, Operation=operation, Threads=40, Schedule=schedule, Chunk=chunk, Simd_Build="omp")
            if r20 and r40:
                values_by_config[f"20 threads, {label}"].append(float(r20["Mean_ms"]))
                values_by_config[f"40 threads, {label}"].append(float(r40["Mean_ms"]))
                speedups[label].append(safe_ratio(float(r20["Mean_ms"]), float(r40["Mean_ms"])))
                time_rows.append({"Image": image, "Operation": operation, "Schedule": label, "T20_ms": r20["Mean_ms"], "T40_ms": r40["Mean_ms"], "Speedup_20_over_40": safe_ratio(float(r20["Mean_ms"]), float(r40["Mean_ms"]))})
    write_csv(tables / "smt_20_vs_40.csv", ["Image", "Operation", "Schedule", "T20_ms", "T40_ms", "Speedup_20_over_40"], time_rows)
    path = figures / "09_smt_tempos_20_vs_40.svg"
    bar_chart(path, "SMT: 20 versus 40 threads", labels, [(name, data, PALETTE[index]) for index, (name, data) in enumerate(values_by_config.items())], "Tempo médio (ms)")
    links.append((path.name, "Tempos absolutos na sensibilidade de hyperthreading"))
    path = figures / "10_smt_speedup_20_para_40.svg"
    bar_chart(path, "SMT: ganho de 20 para 40 threads", labels, [(name, data, SCHEDULE_COLORS[name]) for name, data in speedups.items()], "Speedup (T20 / T40)", baseline=1.0)
    links.append((path.name, "Ganho ou perda ao habilitar hyperthreading"))
    return links


def overview_table(rows_by_kind: dict[str, list[dict[str, object]]], inputs: dict[str, Path], path: Path) -> list[dict[str, object]]:
    report = []
    for kind, rows in rows_by_kind.items():
        samples = sorted({int(row["Samples"]) for row in rows})
        report.append({"Campaign": kind, "Source_directory": inputs[kind].name, "Summary_groups": len(rows), "Samples_per_group": ",".join(map(str, samples)), "Hostnames": ",".join(sorted({str(row["Hostname"]) for row in rows})), "Operations": len({str(row["Operation"]) for row in rows}), "Images": len({str(row["Image"]) for row in rows})})
    write_csv(path, ["Campaign", "Source_directory", "Summary_groups", "Samples_per_group", "Hostnames", "Operations", "Images"], report)
    return report


def write_index(output: Path, links: list[tuple[str, str]], overview: list[dict[str, object]]) -> None:
    rows = "".join("<tr>" + "".join(f"<td>{esc(report[column])}</td>" for column in ("Campaign", "Source_directory", "Summary_groups", "Samples_per_group", "Hostnames", "Operations", "Images")) + "</tr>" for report in overview)
    figures = "".join(f'<li><a href="figures/{esc(name)}">{esc(description)}</a></li>' for name, description in links)
    content = f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><title>Visualização dos experimentos OpenMP</title>
<style>body{{font-family:Arial,sans-serif;max-width:1100px;margin:32px auto;padding:0 18px;color:#202124}}h1{{margin-bottom:4px}}h2{{margin-top:32px}}table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #ddd;padding:8px;text-align:left}}th{{background:#f4f4f4}}li{{margin:9px 0}}a{{color:#0757a8}}</style></head>
<body><h1>Experimentos OpenMP no PCAD</h1><p>Gráficos calculados com a média e o desvio-padrão das cinco amostras de cada configuração.</p>
<h2>Campanhas usadas</h2><table><thead><tr><th>Campanha</th><th>Diretório</th><th>Grupos</th><th>Amostras</th><th>Nó</th><th>Operações</th><th>Imagens</th></tr></thead><tbody>{rows}</tbody></table>
<h2>Figuras</h2><ol>{figures}</ol>
<h2>Tabelas derivadas</h2><p>Consulte a pasta <code>tables/</code> para as tabelas usadas nas figuras.</p></body></html>"""
    (output / "index.html").write_text(content, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera visualizações SVG/HTML dos resultados PCAD.")
    parser.add_argument("--regular", help="Diretório da campanha regular")
    parser.add_argument("--adaptive", help="Diretório da campanha adaptativa")
    parser.add_argument("--smt", help="Diretório da campanha SMT")
    parser.add_argument("--out", default="resultados_visualizados", help="Diretório de saída")
    args = parser.parse_args()
    inputs = resolve_inputs(args)
    output = Path(args.out)
    if not output.is_absolute():
        output = ROOT / output
    figures, tables = output / "figures", output / "tables"
    figures.mkdir(parents=True, exist_ok=True)
    tables.mkdir(parents=True, exist_ok=True)
    rows_by_kind = {kind: read_summary(directory) for kind, directory in inputs.items()}
    overview = overview_table(rows_by_kind, inputs, tables / "campanhas_usadas.csv")
    links = []
    links += regular_figures(rows_by_kind["regular"], figures, tables)
    links += adaptive_figures(rows_by_kind["adaptive"], figures, tables)
    links += smt_figures(rows_by_kind["smt"], figures, tables)
    write_index(output, links, overview)
    print(f"Visualizações geradas em: {output}")
    print(f"Abra: {output / 'index.html'}")


if __name__ == "__main__":
    main()
