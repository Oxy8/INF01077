#!/usr/bin/env python3
"""Mapas da campanha controlada: separa efeito do build e efeito da reestruturação."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path
from statistics import median

from plot_simd_heatmap import presentation_heatmap


OPERATIONS = (
    ("Negative", "linear_bytes", "Negative · linha de bytes"),
    ("Adjust_Brightness", "linear_bytes", "Brightness · linha de bytes"),
    ("Adjust_Contrast", "linear_bytes", "Contrast · linha de bytes"),
    ("Equalize_Histogram", "linear_remap", "Histograma · remap linear"),
    ("Gaussian_11x11", "row_linear_aos", "Gauss 11×11 · linha AoS"),
    ("Quantize", "original_control", "Quantize · controle"),
    ("Grayscale", "original", "Grayscale · controle"),
    ("Zoom_In", "original", "Zoom In · controle"),
)
BASELINES = {
    "Negative": "original",
    "Adjust_Brightness": "original",
    "Adjust_Contrast": "original",
    "Equalize_Histogram": "original",
    "Gaussian_11x11": "pixel_outer",
}
BUILDS = ("off-avx2", "auto-avx2", "omp-avx2")


def medians(raw: Path) -> dict[tuple[str, str, str, str, int, str], float]:
    groups = defaultdict(list)
    with raw.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            if row["Schedule"] != "static" or row["Exact"] != "yes":
                raise ValueError(f"Configuração ou saída inválida: {row}")
            key = (row["Image"], row["Operation"], row["Variant"], row["Phase"],
                   int(row["Threads"]), row["Build"])
            groups[key].append(float(row["Elapsed_ms"]))
    if not groups:
        raise ValueError("CSV vazio")
    return {key: median(values) for key, values in groups.items()}


def make_maps(data: dict, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    with (output / "efeito_estrutura.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(("Image", "Operation", "Threads", "Build", "Original_ms",
                         "Linear_ms", "Original_over_linear"))
        for image in ("4000x3000.png", "6000x6000.png"):
            rows, matrix = [], []
            for operation, variant, label in OPERATIONS:
                if image == "6000x6000.png" and operation == "Zoom_In":
                    continue
                values = []
                for threads in (1, 20):
                    off, auto, omp = (data[(image, operation, variant, "total", threads, build)]
                                      for build in BUILDS)
                    values.extend((off / auto, off / omp, auto / omp))
                    if operation in BASELINES:
                        for build in BUILDS:
                            original = data[(image, operation, BASELINES[operation], "total", threads, build)]
                            linear = data[(image, operation, variant, "total", threads, build)]
                            writer.writerow((image, operation, threads, build, f"{original:.6f}",
                                             f"{linear:.6f}", f"{original / linear:.6f}"))
                rows.append(label)
                matrix.append(values)
            scale = "12mp" if image == "4000x3000.png" else "36mp"
            presentation_heatmap(
                output / f"simd_mesma_variante_{scale}.svg",
                f"Efeito do build SIMD no mesmo código — {image}, static",
                "Razão das medianas de 5 execuções; >1× favorece o denominador. 'Controle' não foi reescrito.",
                ["off / auto", "off / omp", "auto / omp"] * 2,
                rows, matrix, [("1 thread", 0, 2), ("20 threads", 3, 5)],
            )
    print(f"Mapas e tabela de mudança estrutural: {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    make_maps(medians(args.raw), args.out)
