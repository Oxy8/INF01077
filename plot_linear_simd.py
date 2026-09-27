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
COMPARED_SOURCES = ("577262-FPI-Relatorio2/image_manipulation.cpp",
                    "577262-FPI-Relatorio2/vectorization_benchmark.cpp")


def source_hashes(raw: Path) -> dict[str, str]:
    manifest = raw.parent / "source_sha256.txt"
    if not manifest.exists():
        raise ValueError(f"Manifesto de fontes ausente: {manifest}")
    hashes = {}
    for line in manifest.read_text(encoding="utf-8").splitlines():
        parts = line.split(maxsplit=1)
        if len(parts) == 2:
            hashes[parts[1].lstrip("* ")] = parts[0].lower()
    if any(source not in hashes for source in COMPARED_SOURCES):
        raise ValueError(f"Manifesto incompleto: {manifest}")
    return {source: hashes[source] for source in COMPARED_SOURCES}


def zoom_output_hashes(raw: Path) -> dict[str, str]:
    hashes = defaultdict(set)
    with raw.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            if row["Operation"] == "Zoom_In" and row["Variant"] == "original" and row["Phase"] == "total":
                hashes[row["Image"]].add(row["Hash"])
    if any(len(values) != 1 for values in hashes.values()):
        raise ValueError(f"Hashes de Zoom variam dentro de {raw}")
    return {image: next(iter(values)) for image, values in hashes.items()}


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


def make_maps(data: dict, output: Path, supplemental_zoom: bool = False,
              exclude_quantize: bool = False) -> None:
    output.mkdir(parents=True, exist_ok=True)
    with (output / "efeito_estrutura.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(("Image", "Operation", "Threads", "Build", "Original_ms",
                         "Linear_ms", "Original_over_linear"))
        for image in ("4000x3000.png", "6000x6000.png"):
            rows, matrix = [], []
            for operation, variant, label in OPERATIONS:
                if exclude_quantize and operation == "Quantize":
                    continue
                if operation == "Zoom_In" and (image, operation, variant, "total", 1, "off-avx2") not in data:
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
                rows.append(label + (" · campanha complementar" if supplemental_zoom and operation == "Zoom_In" else ""))
                matrix.append(values)
            scale = "12mp" if image == "4000x3000.png" else "36mp"
            presentation_heatmap(
                output / f"simd_mesma_variante_{scale}.svg",
                f"Efeito do build SIMD no mesmo código — {image}, static",
                ("Razão das medianas; >1× favorece o denominador. Zoom: campanha complementar, "
                 "10 amostras; demais: job 825200, 5 amostras."
                 if supplemental_zoom else
                 "Razão das medianas de 5 execuções; >1× favorece o denominador. 'Controle' não foi reescrito."),
                ["off / auto", "off / omp", "auto / omp"] * 2,
                rows, matrix, [("1 thread", 0, 2), ("20 threads", 3, 5)],
            )
    print(f"Mapas e tabela de mudança estrutural: {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--zoom-raw", type=Path,
                        help="CSV suplementar só de Zoom In; mantém os dados originais intactos")
    parser.add_argument("--exclude-quantize", action="store_true",
                        help="Omitir o controle Quantize, cujo total inclui Grayscale")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    data = medians(args.raw)
    if args.zoom_raw:
        if source_hashes(args.raw) != source_hashes(args.zoom_raw):
            raise ValueError("Fontes do kernel Zoom/benchmark diferem entre campanhas")
        original_hashes = zoom_output_hashes(args.raw)
        new_hashes = zoom_output_hashes(args.zoom_raw)
        for image in original_hashes.keys() & new_hashes.keys():
            if original_hashes[image] != new_hashes[image]:
                raise ValueError(f"A saída de Zoom em {image} difere entre campanhas")
        extra = medians(args.zoom_raw)
        if any(key[1] != "Zoom_In" or key[2:4] != ("original", "total") for key in extra):
            raise ValueError("--zoom-raw deve conter somente o controle original de Zoom In")
        data.update(extra)
    make_maps(data, args.out, args.zoom_raw is not None, args.exclude_quantize)
