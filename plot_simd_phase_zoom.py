#!/usr/bin/env python3
"""Mapas SVG da campanha curta, sem dependências externas."""

import argparse
import csv
from pathlib import Path

from plot_simd_heatmap import presentation_heatmap


def read(path):
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--phases", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    zoom = read(args.summary)
    threads = sorted({int(row["Threads"]) for row in zoom})
    values = {(int(row["Threads"]), row["Build"]): row for row in zoom}
    image = {row["Image"] for row in zoom}
    if len(image) != 1:
        raise ValueError(f"Imagens misturadas no Zoom: {image}")
    sample_counts = {int(row["N"]) for row in zoom}
    ratios = (("off / auto", "off-avx2", "auto-avx2"),
              ("off / omp", "off-avx2", "omp-avx2"),
              ("auto / omp", "auto-avx2", "omp-avx2"))
    matrix = [[float(values[(threads_count, numerator)]["Median_ms"]) /
               float(values[(threads_count, denominator)]["Median_ms"])
               for threads_count in threads] for _, numerator, denominator in ratios]
    presentation_heatmap(
        args.out / "zoom_36mp_builds_por_threads.svg",
        f"Zoom In — três builds, {next(iter(image))}, static",
        f"Razão de medianas; {next(iter(sample_counts))} amostras por ponto; "
        ">1× favorece o denominador." if len(sample_counts) == 1 else
        "Razão de medianas; confira N por ponto no CSV. >1× favorece o denominador.",
        [str(count) for count in threads], [label for label, _, _ in ratios], matrix)
    spread = [[float(values[(threads_count, build)]["Max_ms"]) /
               float(values[(threads_count, build)]["Min_ms"])
               for threads_count in threads]
              for build in ("off-avx2", "auto-avx2", "omp-avx2")]
    presentation_heatmap(
        args.out / "zoom_36mp_dispersao.svg",
        f"Zoom In — dispersão das amostras, {next(iter(image))}, static",
        "Máximo / mínimo das amostras; 1× significa ausência de dispersão, não ganho de SIMD.",
        [str(count) for count in threads], ["off-avx2", "auto-avx2", "omp-avx2"], spread)

    phases = read(args.phases)
    data = {(row["Operation"], row["Phase"], int(row["Threads"]), row["Build"]): row
            for row in phases}
    phase_threads = sorted({int(row["Threads"]) for row in phases})
    phase_images = {row["Image"] for row in phases}
    if len(phase_images) != 1:
        raise ValueError(f"Imagens misturadas nas fases: {phase_images}")
    operations = (("Quantize", ("production_total", "grayscale", "production_after_gray",
                                 "minmax", "remap")),
                  ("Equalize_Histogram", ("production_total", "histogram_count",
                                           "cdf_normalize", "remap")))
    labels, phase_matrix = [], []
    for operation, names in operations:
        for phase in names:
            if (operation, phase, phase_threads[0], "off-avx2") not in data:
                continue
            labels.append(f"{operation} · {phase}")
            phase_matrix.append([
                float(data[(operation, phase, threads_count, numerator)]["Median_ms"]) /
                float(data[(operation, phase, threads_count, denominator)]["Median_ms"])
                for threads_count in phase_threads
                for _, numerator, denominator in ratios
            ])
    if phase_matrix:
        presentation_heatmap(
            args.out / "quantize_equalize_fases.svg",
            f"Quantize e Equalize — contribuição de cada fase, {next(iter(phase_images))}, static",
            "Razão das medianas; >1× favorece o denominador. Fases replicadas e validadas; "
            "CDF de 256 posições é muito curta para inferência estável.",
            [label for _ in phase_threads for label, _, _ in ratios], labels, phase_matrix,
            [(f"{count} thread{'s' if count != 1 else ''}", index * 3, index * 3 + 2)
             for index, count in enumerate(phase_threads)])
    print(f"Gráficos: {args.out}")


if __name__ == "__main__":
    main()
