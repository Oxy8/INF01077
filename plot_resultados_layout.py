#!/usr/bin/env python3
"""Visualiza AoS, SoA ingênuo e SoA separável sem supor uma variante SIMD fixa."""

from __future__ import annotations

import argparse
import csv
import html
import math
from pathlib import Path
from typing import Iterable, Sequence

from plot_resultados_pcad import PALETTE, bar_chart, heatmap, line_chart, safe_ratio


ROOT = Path(__file__).resolve().parent
THREADS = [1, 2, 4, 8, 12, 16, 20]
VARIANT_COLORS = {"off": "#555555", "off-avx2": "#d62728", "omp": "#8a2be2", "omp-avx2": "#1f77b4"}
LAYOUT_COLORS = {"AoS": "#555555", "AoS_Naive": "#555555", "SoA": "#1f77b4", "SoA_Naive": "#1f77b4", "SoA_Separable": "#2ca02c"}


def median(row: dict[str, object]) -> float:
    return float(row["Median_ms"])


def read_summary(directory: Path) -> list[dict[str, object]]:
    with (directory / "layout_summary.csv").open(newline="", encoding="utf-8") as source:
        rows: list[dict[str, object]] = []
        for raw in csv.DictReader(source):
            row: dict[str, object] = dict(raw)
            for field in ("Width", "Height", "Threads", "Samples"):
                row[field] = int(raw[field])
            for field in ("Median_ms", "Min_ms", "Max_ms", "Mean_ms", "StdDev_ms"):
                row[field] = float(raw[field])
            rows.append(row)
    return rows


def lookup(rows: Iterable[dict[str, object]], **criteria: object) -> dict[str, object] | None:
    return next((row for row in rows if all(row.get(key) == value for key, value in criteria.items())), None)


def ordered(present: Iterable[str], preferred: Sequence[str]) -> list[str]:
    values = set(present)
    return [item for item in preferred if item in values] + sorted(values - set(preferred))


def layout_label(layout: str) -> str:
    return {"AoS": "AoS direto", "AoS_Naive": "AoS direto", "SoA": "SoA ingênuo", "SoA_Naive": "SoA ingênuo", "SoA_Separable": "SoA separável"}.get(layout, layout)


def color(variant: str, offset: int = 0) -> str:
    return VARIANT_COLORS.get(variant, PALETTE[offset % len(PALETTE)])


def write_csv(path: Path, columns: Sequence[str], rows: Iterable[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as destination:
        writer = csv.DictWriter(destination, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def kernel_figures(rows: list[dict[str, object]], figures: Path, tables: Path) -> list[tuple[str, str]]:
    links, extracted = [], []
    images = sorted({str(row["Image"]) for row in rows})
    operations = sorted({str(row["Operation"]) for row in rows})
    builds = ordered((str(row["Simd_Build"]) for row in rows), ("off", "off-avx2", "omp", "omp-avx2"))
    layouts = ordered((str(row["Layout"]) for row in rows), ("AoS", "AoS_Naive", "SoA", "SoA_Naive", "SoA_Separable"))
    for image in images:
        for operation in operations:
            for build_index, build in enumerate(builds):
                series = []
                for layout in layouts:
                    values = [lookup(rows, Image=image, Operation=operation, Threads=t, Layout=layout, Phase="Kernel", Simd_Build=build) for t in THREADS]
                    if any(value is None for value in values):
                        continue
                    series.append((layout_label(layout), [median(value) for value in values if value], LAYOUT_COLORS.get(layout, color(build, build_index)), None))
                    for thread, value in zip(THREADS, values):
                        extracted.append({"Image": image, "Operation": operation, "Threads": thread, "Build": build, "Layout": layout, "Kernel_median_ms": value["Median_ms"], "Kernel_min_ms": value["Min_ms"], "Kernel_max_ms": value["Max_ms"]})
                if series:
                    path = figures / f"01_kernels_{Path(image).stem}_{operation}_{build}.svg"
                    line_chart(path, f"Kernels — {operation}, {image}, {build}", THREADS, series, "Tempo mediano (ms)", numeric_x=True)
                    links.append((path.name, f"Kernels por threads — {operation}, {image}, {build}"))
    write_csv(tables / "kernels_por_layout.csv", ["Image", "Operation", "Threads", "Build", "Layout", "Kernel_median_ms", "Kernel_min_ms", "Kernel_max_ms"], extracted)
    return links


def total_figures(rows: list[dict[str, object]], figures: Path) -> list[tuple[str, str]]:
    links = []
    images = sorted({str(row["Image"]) for row in rows})
    operations = sorted({str(row["Operation"]) for row in rows})
    builds = ordered((str(row["Simd_Build"]) for row in rows), ("off", "off-avx2", "omp", "omp-avx2"))
    layouts = ordered((str(row["Layout"]) for row in rows if str(row["Layout"]).startswith("SoA")), ("SoA", "SoA_Naive", "SoA_Separable"))
    for image in images:
        for operation in operations:
            for index, build in enumerate(builds):
                series = []
                for layout in layouts:
                    values = [lookup(rows, Image=image, Operation=operation, Threads=t, Layout=layout, Phase="End_to_End", Simd_Build=build) for t in THREADS]
                    if not any(value is None for value in values):
                        series.append((f"{layout_label(layout)} total", [median(value) for value in values if value], LAYOUT_COLORS.get(layout, color(build, index)), None))
                if series:
                    path = figures / f"02_total_{Path(image).stem}_{operation}_{build}.svg"
                    line_chart(path, f"Custo total com conversões — {operation}, {image}, {build}", THREADS, series, "Tempo mediano (ms)", numeric_x=True)
                    links.append((path.name, f"Custo total SoA — {operation}, {image}, {build}"))
    return links


def phase_figures(rows: list[dict[str, object]], figures: Path, tables: Path) -> list[tuple[str, str]]:
    links, extracted = [], []
    images = sorted({str(row["Image"]) for row in rows})
    operations = sorted({str(row["Operation"]) for row in rows})
    builds = ordered((str(row["Simd_Build"]) for row in rows), ("off", "off-avx2", "omp", "omp-avx2"))
    for image in images:
        for operation in operations:
            components = sorted({(str(row["Layout"]), str(row["Phase"])) for row in rows if row["Image"] == image and row["Operation"] == operation and row["Threads"] == 20}, key=lambda item: (item[0], item[1]))
            labels = [f"{layout_label(layout)}: {phase}" for layout, phase in components]
            groups = []
            for index, build in enumerate(builds):
                values = [lookup(rows, Image=image, Operation=operation, Threads=20, Layout=layout, Phase=phase, Simd_Build=build) for layout, phase in components]
                if any(value is None for value in values):
                    continue
                groups.append((build, [median(value) for value in values if value], color(build, index)))
                extracted.extend({"Image": image, "Operation": operation, "Build": build, "Component": label, "Median_ms": value["Median_ms"], "Min_ms": value["Min_ms"], "Max_ms": value["Max_ms"]} for label, value in zip(labels, values))
            if groups:
                path = figures / f"03_fases_20t_{Path(image).stem}_{operation}.svg"
                bar_chart(path, f"Componentes em 20 threads — {operation}, {image}", labels, groups, "Tempo mediano (ms)")
                links.append((path.name, f"Conversões e passadas em 20 threads — {operation}, {image}"))
    write_csv(tables / "fases_20_threads.csv", ["Image", "Operation", "Build", "Component", "Median_ms", "Min_ms", "Max_ms"], extracted)
    return links


def simd_heatmaps(rows: list[dict[str, object]], figures: Path, tables: Path) -> list[tuple[str, str]]:
    links, extracted = [], []
    builds = {str(row["Simd_Build"]) for row in rows}
    layouts = ordered((str(row["Layout"]) for row in rows), ("AoS", "AoS_Naive", "SoA", "SoA_Naive", "SoA_Separable"))
    for scalar, simd, suffix in (("off", "omp", "generico"), ("off-avx2", "omp-avx2", "avx2")):
        if not {scalar, simd}.issubset(builds):
            continue
        matrix, labels = [], []
        for image in sorted({str(row["Image"]) for row in rows}):
            for operation in sorted({str(row["Operation"]) for row in rows}):
                for layout in layouts:
                    values = []
                    for thread in THREADS:
                        base = lookup(rows, Image=image, Operation=operation, Threads=thread, Layout=layout, Phase="Kernel", Simd_Build=scalar)
                        tested = lookup(rows, Image=image, Operation=operation, Threads=thread, Layout=layout, Phase="Kernel", Simd_Build=simd)
                        ratio = safe_ratio(median(base), median(tested)) if base and tested else math.nan
                        values.append(ratio)
                        if base and tested:
                            extracted.append({"Image": image, "Operation": operation, "Layout": layout, "Threads": thread, "Scalar_build": scalar, "SIMD_build": simd, "Scalar_median_ms": base["Median_ms"], "Scalar_min_ms": base["Min_ms"], "Scalar_max_ms": base["Max_ms"], "SIMD_median_ms": tested["Median_ms"], "SIMD_min_ms": tested["Min_ms"], "SIMD_max_ms": tested["Max_ms"], "Speedup_scalar_over_simd": ratio})
                    if all(math.isfinite(value) for value in values):
                        labels.append(f"{image} · {operation} · {layout_label(layout)}")
                        matrix.append(values)
        if matrix:
            path = figures / f"04_simd_{suffix}.svg"
            title = "SIMD explícito com AVX2 (Haswell)" if suffix == "avx2" else "SIMD explícito no alvo padrão"
            heatmap(path, title, [str(t) for t in THREADS], labels, matrix, f"Tempo {scalar} / tempo {simd}. Acima de 1× favorece SIMD.")
            links.append((path.name, title))
    write_csv(tables / "efeito_simd.csv", ["Image", "Operation", "Layout", "Threads", "Scalar_build", "SIMD_build", "Scalar_median_ms", "Scalar_min_ms", "Scalar_max_ms", "SIMD_median_ms", "SIMD_min_ms", "SIMD_max_ms", "Speedup_scalar_over_simd"], extracted)
    return links


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera gráficos do experimento AoS/SoA/separável.")
    parser.add_argument("--input", default="resultados_pcad_hype_layout_822823")
    parser.add_argument("--out", default="resultados_visualizados_layout")
    args = parser.parse_args()
    source, output = Path(args.input), Path(args.out)
    source = source if source.is_absolute() else ROOT / source
    output = output if output.is_absolute() else ROOT / output
    rows = read_summary(source)
    if not rows:
        raise SystemExit("Nenhuma linha encontrada em layout_summary.csv.")
    figures, tables = output / "figures", output / "tables"
    figures.mkdir(parents=True, exist_ok=True)
    tables.mkdir(parents=True, exist_ok=True)
    links = kernel_figures(rows, figures, tables) + total_figures(rows, figures) + phase_figures(rows, figures, tables) + simd_heatmaps(rows, figures, tables)
    samples = ", ".join(map(str, sorted({int(row["Samples"]) for row in rows})))
    builds = ", ".join(ordered((str(row["Simd_Build"]) for row in rows), ("off", "off-avx2", "omp", "omp-avx2")))
    items = "".join(f'<li><a href="figures/{html.escape(name)}">{html.escape(label)}</a></li>' for name, label in links)
    (output / "index.html").write_text(f'<!doctype html><html lang="pt-BR"><meta charset="utf-8"><title>Layout e SIMD</title><body style="font-family:Arial;max-width:1000px;margin:32px auto"><h1>Layout de pixels e SIMD</h1><p>{html.escape(source.name)}; {samples} amostras; builds: {html.escape(builds)}.</p><p>Os gráficos usam a mediana; as tabelas preservam mínimo e máximo. Para Gaussian 11×11, SoA separável mede o kernel com 22 contribuições por componente; conversões aparecem em fases distintas.</p><h2>Figuras</h2><ol>{items}</ol><p>Valores derivados: <code>tables/</code>.</p></body></html>', encoding="utf-8")
    print(f"Visualizações geradas em: {output}")


if __name__ == "__main__":
    main()
