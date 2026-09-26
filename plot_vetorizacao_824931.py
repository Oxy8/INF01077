#!/usr/bin/env python3
"""Gráficos reproduzíveis da campanha de vetorização 824931 (somente stdlib)."""

from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path
from statistics import median
from xml.sax.saxutils import escape


ROOT = Path(__file__).resolve().parent
DEFAULT_RAW = ROOT / "resultados_pcad_hype_vectorization_824931" / "vectorization_raw.csv"
DEFAULT_OUTPUT = ROOT / "visualizacoes_pcad_hype_vetorizacao_824931" / "figures"
BUILDS = ("off-avx2", "auto-avx2", "omp-avx2")
REGULAR = (
    ("Negative", "linear_bytes", "Negative · linear"),
    ("Adjust_Brightness", "linear_bytes", "Brightness · linear"),
    ("Adjust_Contrast", "linear_bytes", "Contrast · linear"),
    ("Quantize", "quantize_lut", "Quantize · tabela"),
    ("Equalize_Histogram", "private_histogram", "Histograma · privado"),
    ("Flip_Horizontal", "out_of_place", "Flip horizontal · saída nova"),
    ("Rotate_CW", "blocked_32", "Rotação horária · blocos"),
    ("Rotate_CCW", "blocked_32", "Rotação anti-horária · blocos"),
    ("Grayscale", "original", "Grayscale · original"),
    ("Zoom_In", "original", "Zoom in · original"),
    *((f"Gaussian_{tap}x{tap}", "aos_separable", f"Gauss {tap}×{tap} · AoS separável")
      for tap in (3, 5, 7, 9, 11)),
)
GAUSSIAN = tuple(
    (f"Gaussian_{tap}x{tap}", variant, f"{tap}×{tap} · {label}")
    for tap in (3, 5, 7, 9, 11)
    for variant, label in (
        ("aos_direct", "AoS direto"),
        ("soa_direct", "SoA direto"),
        ("aos_separable", "AoS separável"),
        ("soa_separable", "SoA separável"),
    )
)


def read_medians(path: Path) -> dict[tuple[str, str, str, int, str], tuple[float, int]]:
    groups: dict[tuple[str, str, str, int, str], list[float]] = defaultdict(list)
    with path.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            if row["Schedule"] != "static":
                raise ValueError(f"Schedule inesperado no CSV: {row['Schedule']}")
            if row["Build"] not in BUILDS:
                raise ValueError(f"Build inesperado no CSV: {row['Build']}")
            if row["Exact"] != "yes" and row["Variant"] != "production_float":
                raise ValueError(f"Saída divergente: {row['Image']} {row['Operation']} {row['Variant']}")
            if row["Phase"] != "total" or row["Variant"] == "production_float":
                continue
            key = (row["Image"], row["Operation"], row["Variant"], int(row["Threads"]), row["Build"])
            groups[key].append(float(row["Elapsed_ms"]))
    return {key: (median(values), len(values)) for key, values in groups.items()}


def label(x: float, y: float, value: str, *, anchor: str = "start", size: int = 14,
          color: str = "#223449", weight: int = 400) -> str:
    return (f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" '
            f'font-size="{size}" fill="{color}" font-weight="{weight}">{escape(value)}</text>')


def build_figure(medians: dict, image: str, threads: int, operations: tuple,
                 title: str, left_range: tuple[float, float], right_range: tuple[float, float],
                 out: Path, *, log_left: bool = False) -> None:
    rows = []
    for operation, variant, display in operations:
        builds = {}
        for build in BUILDS:
            key = (image, operation, variant, threads, build)
            if key not in medians:
                raise ValueError(f"Falta configuração: {key}")
            builds[build] = medians[key]
        if len({entry[1] for entry in builds.values()}) != 1:
            raise ValueError(f"Número de amostras desigual: {image} {operation} {variant}")
        rows.append((display,
                     builds["off-avx2"][0] / builds["auto-avx2"][0],
                     builds["auto-avx2"][0] / builds["omp-avx2"][0],
                     builds["auto-avx2"][1]))

    width, row_height = 1600, 37 if len(rows) <= 15 else 34
    top, bottom = 180, 120
    height = top + len(rows) * row_height + bottom
    panels = ((335, 820, left_range,
               "Vetorização automática: off / auto" + (" (log)" if log_left else ""), 1),
              (1035, 1510, right_range, "Pragma explícito: auto / omp", 2))

    def coordinate(value: float, x0: float, x1: float, limits: tuple[float, float], field: int) -> float:
        lo, hi = limits
        if field == 1 and log_left:
            return x0 + (math.log(value) - math.log(lo)) / (math.log(hi) - math.log(lo)) * (x1 - x0)
        return x0 + (value - lo) / (hi - lo) * (x1 - x0)
    elements = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<g font-family="Arial,Helvetica,sans-serif">',
        label(32, 42, title, size=25, weight=700),
        label(32, 70, "Razão das medianas de tempo; acima de 1×, o build do denominador é mais rápido.", size=15),
        label(32, 94, "Mesmo código, GCC 12.2, -march=haswell, static. O gráfico não atribui ganho à reescrita do algoritmo.",
              size=14, color="#536579"),
    ]
    for index in range(len(rows)):
        if index % 2 == 0:
            y0 = top + index * row_height
            elements.append(f'<rect x="24" y="{y0:.1f}" width="1545" height="{row_height}" '
                            'fill="#f6f8fb"/>')
    for x0, x1, limits, heading, field in panels:
        lo, hi = limits
        elements.append(label((x0 + x1) / 2, 133, heading, anchor="middle", size=17, weight=700))
        ticks = (lo, 1.0, 2.0, 4.0, hi) if field == 1 and log_left else (lo, 1.0, hi)
        for tick in ticks:
            x = coordinate(tick, x0, x1, limits, field)
            elements.append(f'<line x1="{x:.1f}" y1="{top-16}" x2="{x:.1f}" '
                            f'y2="{top+len(rows)*row_height}" stroke="{("#54657a" if tick == 1 else "#e1e7ed")}" '
                            f'stroke-width="{(1.8 if tick == 1 else 1)}" '
                            f'{("stroke-dasharray=\"5 5\"" if tick == 1 else "")}/>')
            elements.append(label(x, top - 24, f"{tick:g}×", anchor="middle", size=13, color="#536579"))

    for index, (display, automatic, explicit, _n) in enumerate(rows):
        y = top + index * row_height + row_height / 2
        elements.append(label(305, y + 5, display, anchor="end", size=14))
        for x0, x1, (lo, hi), _, field in panels:
            ratio = automatic if field == 1 else explicit
            if not lo <= ratio <= hi:
                raise ValueError(f"Razão {ratio:.4f} fora da escala {lo}–{hi}: {display}")
            ref = coordinate(1.0, x0, x1, (lo, hi), field)
            x = coordinate(ratio, x0, x1, (lo, hi), field)
            color = ("#087d85" if field == 1 else "#c56a14") if ratio >= 1 else "#b34b50"
            elements.append(f'<line x1="{ref:.1f}" y1="{y:.1f}" x2="{x:.1f}" y2="{y:.1f}" '
                            f'stroke="{color}" stroke-width="4"/>')
            elements.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5.5" fill="{color}"/>')
            anchor = "end" if x > x1 - 48 else "start"
            tx = x - 9 if anchor == "end" else x + 9
            elements.append(label(tx, y + 5, f"{ratio:.2f}×", anchor=anchor, size=13, color=color, weight=700))

    note = ("n=5 para Gaussianas de 36 MP; n=10 para as demais operações."
            if image == "6000x6000.png" else "n=10 em todas as operações de 12 MP.")
    elements.append(label(32, height - 75, note, size=14, color="#536579"))
    elements.append(label(32, height - 52, "Grayscale e Zoom são controles do código original; os demais nomes identificam variantes isoladas.",
                          size=14, color="#536579"))
    elements.append(label(32, height - 29, "Fonte: vectorization_raw.csv do job 824931; medianas recalculadas pelo gerador.",
                          size=14, color="#536579"))
    elements.append("</g></svg>")
    out.write_text("\n".join(elements) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=DEFAULT_RAW)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    medians = read_medians(args.raw)
    args.output.mkdir(parents=True, exist_ok=True)
    for image, scale in (("4000x3000.png", "12mp"), ("6000x6000.png", "36mp")):
        items = REGULAR if scale == "12mp" else tuple(row for row in REGULAR if row[0] != "Zoom_In")
        for threads in (1, 20):
            path = args.output / f"ganho_builds_{scale}_{threads}t.svg"
            build_figure(medians, image, threads, items,
                         f"Efeito dos builds SIMD — {scale.upper()}, {threads} thread{'s' if threads != 1 else ''}",
                         (0.5, 7.0), (0.7, 1.3), path, log_left=True)
            print(path)
    for threads in (1, 20):
        path = args.output / f"gaussianas_variantes_36mp_{threads}t.svg"
        build_figure(medians, "6000x6000.png", threads, GAUSSIAN,
                     f"Gaussianas por layout e algoritmo — 36 MP, {threads} thread{'s' if threads != 1 else ''}",
                     (0.7, 1.8), (0.85, 1.3), path)
        print(path)


if __name__ == "__main__":
    main()
