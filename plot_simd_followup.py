#!/usr/bin/env python3
"""Mapas da campanha SIMD complementar, sem dependências externas."""

import argparse
import csv
import html
from pathlib import Path

from plot_simd_heatmap import presentation_heatmap


OPERATIONS = (
    "Adjust_Brightness", "Adjust_Contrast", "Equalize_Histogram",
    "Gaussian_11x11", "Grayscale", "Negative", "Quantize", "Zoom_In",
)
VARIANTS = (
    ("float_pixel_outer", "Pixel externo (referência)"),
    ("float_tap_products", "Produtos dos taps"),
    ("float_row_aos", "Linha RGB contígua"),
    ("float_row_soa", "Linha SoA + conversões"),
)
BUILDS = ("off-avx2", "auto-avx2", "omp-avx2")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    with args.summary.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise ValueError("Resumo vazio")
    images = {row["Image"] for row in rows}
    if len(images) != 1:
        raise ValueError(f"Esperada uma imagem por campanha: {images}")
    image = next(iter(images))
    threads = sorted({int(row["Threads"]) for row in rows})
    data = {(row["Operation"], row["Variant"], int(row["Threads"]), row["Build"]): row
            for row in rows}
    if len(data) != len(rows):
        raise ValueError("Configurações duplicadas no resumo")
    figures = args.out / "figures"
    figures.mkdir(parents=True, exist_ok=True)
    links = []

    for name, numerator, denominator in (
        ("original_off_omp", "off-avx2", "omp-avx2"),
        ("original_off_auto", "off-avx2", "auto-avx2"),
        ("original_auto_omp", "auto-avx2", "omp-avx2"),
    ):
        matrix = []
        for operation in OPERATIONS:
            values = []
            for count in threads:
                base = data[(operation, "production", count, numerator)]
                tested = data[(operation, "production", count, denominator)]
                if base["Samples"] != tested["Samples"]:
                    raise ValueError(f"Amostras desiguais: {operation} {count}")
                values.append(float(base["Median_ms"]) / float(tested["Median_ms"]))
            matrix.append(values)
        path = figures / f"{name}.svg"
        presentation_heatmap(
            path, f"Operações originais — {numerator} / {denominator}, {image}, static",
            "Razão das medianas; acima de 1× favorece o denominador. Azul: melhora; laranja: piora.",
            [str(count) for count in threads], list(OPERATIONS), matrix)
        links.append((path.name, f"Operações originais: {numerator} / {denominator}"))

    for build in BUILDS:
        matrix = []
        for variant, _ in VARIANTS:
            values = []
            for count in threads:
                baseline = data[("Gaussian_11x11", "float_pixel_outer", count, build)]
                tested = data[("Gaussian_11x11", variant, count, build)]
                values.append(float(baseline["Median_ms"]) / float(tested["Median_ms"]))
            matrix.append(values)
        path = figures / f"gaussian_float_{build}.svg"
        presentation_heatmap(
            path, f"Gaussiana float 11×11 — {build}, {image}, static",
            "Pixel externo / variante; SoA inclui conversões. Todas as saídas devem ser idênticas.",
            [str(count) for count in threads], [name for _, name in VARIANTS], matrix)
        links.append((path.name, f"Convolução float: {build}"))

    items = "".join(f'<li><a href="figures/{html.escape(file)}">{html.escape(title)}</a></li>'
                    for file, title in links)
    (args.out / "index.html").write_text(
        '<!doctype html><html lang="pt-BR"><meta charset="utf-8">'
        '<title>SIMD complementar</title><body style="font-family:Arial;max-width:1000px;margin:32px auto">'
        '<h1>SIMD complementar</h1>'
        '<p>Medianas dentro do mesmo build e mesma variante. A função de produção '
        'inclui sua alocação interna; as variantes float usam saída pré-alocada. '
        'Por isso, compare as variantes float à referência float_pixel_outer, não '
        'diretamente aos milissegundos da função de produção.</p>'
        '<p>A redução SIMD nos taps ficou fora da campanha porque alterou bytes '
        'na validação; a variante de produtos mantém a soma na ordem original. '
        'Consulte All_Exact no resumo CSV.</p>'
        f'<ol>{items}</ol><p><a href="../simd_followup_summary.csv">Resumo CSV</a></p></body></html>',
        encoding="utf-8")
    print(f"Gráficos: {args.out}")


if __name__ == "__main__":
    main()
