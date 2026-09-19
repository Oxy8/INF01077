#!/usr/bin/env python3
"""Gráficos complementares para a campanha com alvo Haswell/AVX2."""

from __future__ import annotations

import argparse
import csv
import html
import math
from pathlib import Path

from plot_resultados_pcad import PALETTE, ROOT, THREADS, bar_chart, heatmap, line_chart, lookup, read_summary, safe_ratio


BUILD_ORDER = ("off", "off-avx2", "omp", "omp-avx2")
BUILD_COLORS = {"off": "#555555", "off-avx2": "#d62728", "omp": "#8a2be2", "omp-avx2": "#1f77b4"}


def builds(rows: list[dict[str, object]]) -> list[str]:
    present = {str(row["Simd_Build"]) for row in rows}
    return [build for build in BUILD_ORDER if build in present] + sorted(present - set(BUILD_ORDER))


def color(build: str, index: int) -> str:
    return BUILD_COLORS.get(build, PALETTE[index % len(PALETTE)])


def write_csv(path: Path, columns: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as destination:
        writer = csv.DictWriter(destination, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def regular(rows: list[dict[str, object]], figures: Path, tables: Path) -> list[tuple[str, str]]:
    links = []
    image = max({str(row["Image"]) for row in rows}, key=lambda name: next(int(row["Width"]) * int(row["Height"]) for row in rows if row["Image"] == name))
    operations = sorted({str(row["Operation"]) for row in rows if row["Image"] == image and row["Simd_Eligible"] == "yes"})
    extracted: list[dict[str, object]] = []
    for scalar, simd, suffix in (("off", "omp", "generico"), ("off-avx2", "omp-avx2", "avx2")):
        if scalar not in builds(rows) or simd not in builds(rows):
            continue
        values, labels = [], []
        for operation in operations:
            line = []
            for thread in THREADS:
                base = lookup(rows, Image=image, Operation=operation, Threads=thread, Schedule="static", Chunk="", Simd_Build=scalar)
                tested = lookup(rows, Image=image, Operation=operation, Threads=thread, Schedule="static", Chunk="", Simd_Build=simd)
                ratio = safe_ratio(float(base["Mean_ms"]), float(tested["Mean_ms"])) if base and tested else math.nan
                line.append(ratio)
                if base and tested:
                    extracted.append({"Image": image, "Operation": operation, "Threads": thread, "Scalar_build": scalar, "SIMD_build": simd, "Scalar_ms": base["Mean_ms"], "SIMD_ms": tested["Mean_ms"], "Speedup_scalar_over_simd": ratio})
            if all(math.isfinite(value) for value in line):
                labels.append(operation)
                values.append(line)
        if values:
            title = "SIMD explícito com AVX2/FMA" if suffix == "avx2" else "SIMD explícito no alvo padrão"
            path = figures / f"01_simd_{suffix}_36mp_static.svg"
            heatmap(path, f"{title} — {image}, static", [str(thread) for thread in THREADS], labels, values, f"Tempo {scalar} / tempo {simd}. Acima de 1× favorece SIMD.")
            links.append((path.name, title))
    write_csv(tables / "efeito_simd_por_build.csv", ["Image", "Operation", "Threads", "Scalar_build", "SIMD_build", "Scalar_ms", "SIMD_ms", "Speedup_scalar_over_simd"], extracted)

    # Isola a troca do alvo: ambos os lados mantêm os pragmas omp simd.
    if {"omp", "omp-avx2"}.issubset(builds(rows)):
        matrix, labels = [], []
        for operation in operations:
            line = []
            for thread in THREADS:
                generic = lookup(rows, Image=image, Operation=operation, Threads=thread, Schedule="static", Chunk="", Simd_Build="omp")
                avx2 = lookup(rows, Image=image, Operation=operation, Threads=thread, Schedule="static", Chunk="", Simd_Build="omp-avx2")
                line.append(safe_ratio(float(generic["Mean_ms"]), float(avx2["Mean_ms"])) if generic and avx2 else math.nan)
            if all(math.isfinite(value) for value in line):
                labels.append(operation)
                matrix.append(line)
        if matrix:
            path = figures / "02_alvo_haswell_36mp_static.svg"
            heatmap(path, f"Efeito de compilar para Haswell — {image}, static", [str(thread) for thread in THREADS], labels, matrix, "Tempo omp / tempo omp-avx2. Acima de 1× favorece Haswell/AVX2.")
            links.append((path.name, "Efeito do alvo Haswell, mantendo omp simd"))
    return links


def adaptive(rows: list[dict[str, object]], figures: Path, tables: Path) -> list[tuple[str, str]]:
    links = []
    images = sorted({str(row["Image"]) for row in rows})
    labels = ["static", "dynamic,1", "dynamic,4", "dynamic,16", "dynamic,64", "dynamic,256"]
    configurations = [("static", "")] + [("dynamic", label.split(",")[1]) for label in labels[1:]]
    for image in images:
        series = []
        for index, build in enumerate(builds(rows)):
            data = [lookup(rows, Image=image, Threads=20, Schedule=schedule, Chunk=chunk, Simd_Build=build) for schedule, chunk in configurations]
            if not any(row is None for row in data):
                series.append((build, [float(row["Mean_ms"]) for row in data if row], color(build, index), [float(row["StdDev_ms"]) for row in data if row]))
        if series:
            path = figures / f"03_chunks_{Path(image).stem}.svg"
            line_chart(path, f"Adaptativo: static e chunks — {image}, 20 threads", labels, series, "Tempo médio (ms)", x_label="Schedule OpenMP")
            links.append((path.name, f"Chunks por build — {image}"))
    totals: list[dict[str, object]] = []
    for build in builds(rows):
        for label, (schedule, chunk) in zip(labels, configurations):
            selected = [lookup(rows, Image=image, Threads=20, Schedule=schedule, Chunk=chunk, Simd_Build=build) for image in images]
            if not any(row is None for row in selected):
                totals.append({"Build": build, "Schedule": label, "Total_ms": sum(float(row["Mean_ms"]) for row in selected if row)})
    write_csv(tables / "adaptativo_total_por_build_chunk.csv", ["Build", "Schedule", "Total_ms"], totals)
    if len(totals) == len(builds(rows)) * len(labels):
        path = figures / "04_chunks_total.svg"
        bar_chart(path, "Adaptativo: soma dos tempos nas imagens, 20 threads", labels, [(build, [float(next(row for row in totals if row["Build"] == build and row["Schedule"] == label)["Total_ms"]) for label in labels], color(build, index)) for index, build in enumerate(builds(rows))], "Tempo médio (ms)")
        links.append((path.name, "Soma por chunk e build"))
    return links


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera gráficos específicos da campanha AVX2.")
    parser.add_argument("--regular", required=True, help="Diretório da campanha regular.")
    parser.add_argument("--adaptive", required=True, help="Diretório da campanha adaptativa.")
    parser.add_argument("--out", default="resultados_visualizados_avx")
    args = parser.parse_args()
    regular_dir, adaptive_dir, output = Path(args.regular), Path(args.adaptive), Path(args.out)
    regular_dir = regular_dir if regular_dir.is_absolute() else ROOT / regular_dir
    adaptive_dir = adaptive_dir if adaptive_dir.is_absolute() else ROOT / adaptive_dir
    output = output if output.is_absolute() else ROOT / output
    figures, tables = output / "figures", output / "tables"
    figures.mkdir(parents=True, exist_ok=True)
    tables.mkdir(parents=True, exist_ok=True)
    links = regular(read_summary(regular_dir), figures, tables) + adaptive(read_summary(adaptive_dir), figures, tables)
    items = "".join(f'<li><a href="figures/{html.escape(name)}">{html.escape(label)}</a></li>' for name, label in links)
    (output / "index.html").write_text(f'<!doctype html><html lang="pt-BR"><meta charset="utf-8"><title>AVX2 e OpenMP SIMD</title><body style="font-family:Arial;max-width:1000px;margin:32px auto"><h1>AVX2 e OpenMP SIMD</h1><p>Comparações controladas entre builds escalar, escalar Haswell, omp simd genérico e omp simd Haswell/AVX2.</p><ol>{items}</ol><p>Tabelas derivadas: <code>tables/</code>.</p></body></html>', encoding="utf-8")
    print(f"Visualizações geradas em: {output}")


if __name__ == "__main__":
    main()
