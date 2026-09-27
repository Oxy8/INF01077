#!/usr/bin/env python3
"""Estilo comum dos mapas SIMD usados na apresentação curta."""

from __future__ import annotations

import math
from pathlib import Path
from xml.sax.saxutils import escape


def _blend(white: tuple[int, int, int], target: tuple[int, int, int], amount: float) -> str:
    rgb = (round(a * (1 - amount) + b * amount) for a, b in zip(white, target))
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def ratio_color(value: float) -> tuple[str, str]:
    """Azul/laranja, centrado em 1; o número mantém o mapa legível sem cor."""
    if not math.isfinite(value) or value <= 0:
        return "#eeeeee", "#25313f"
    distance = abs(math.log2(value))
    if distance < 0.015:
        return "#ffffff", "#25313f"
    strength = min(0.80, 0.12 + 0.38 * distance)
    target = (0, 114, 178) if value > 1 else (213, 94, 0)
    return _blend((255, 255, 255), target, strength), ("#ffffff" if strength >= 0.57 else "#203044")


def presentation_heatmap(path: Path, title: str, subtitle: str,
                         columns: list[str], rows: list[str], matrix: list[list[float]],
                         groups: list[tuple[str, int, int]] | None = None) -> None:
    """Células adjacentes e mesma escala visual para ambas as campanhas."""
    if len(rows) != len(matrix) or any(len(row) != len(columns) for row in matrix):
        raise ValueError("Dimensões incompatíveis no mapa SIMD")
    width, left, right, top, row_height = 1260, 305, 35, 136, 38
    height = top + len(rows) * row_height + 32
    cell_width = (width - left - right) / len(columns)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">',
        '<rect width="100%" height="100%" fill="#fff"/>',
        '<g font-family="Arial,Helvetica,sans-serif">',
        f'<text x="{left}" y="35" font-size="25" font-weight="700" fill="#172b40">{escape(title)}</text>',
        f'<text x="{left}" y="60" font-size="15" fill="#42566b">{escape(subtitle)}</text>',
    ]
    if groups:
        for name, first, last in groups:
            center = left + (first + (last - first + 1) / 2) * cell_width
            parts.append(f'<text x="{center:.1f}" y="91" text-anchor="middle" '
                         f'font-size="17" font-weight="700" fill="#172b40">{escape(name)}</text>')
    for index, column in enumerate(columns):
        x = left + (index + 0.5) * cell_width
        parts.append(f'<text x="{x:.1f}" y="123" text-anchor="middle" font-size="14" '
                     f'font-weight="700" fill="#25394f">{escape(column)}</text>')
    for index, (name, values) in enumerate(zip(rows, matrix)):
        y = top + index * row_height
        parts.append(f'<text x="{left - 10}" y="{y + 25:.1f}" text-anchor="end" '
                     f'font-size="14" fill="#25394f">{escape(name)}</text>')
        for col, value in enumerate(values):
            x = left + col * cell_width
            fill, ink = ratio_color(value)
            parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{cell_width:.1f}" '
                         f'height="{row_height}" fill="{fill}" stroke="#dce4ec" stroke-width="0.8"/>')
            printed = f"{value:.2f}×" if math.isfinite(value) else "—"
            parts.append(f'<text x="{x + cell_width / 2:.1f}" y="{y + 25:.1f}" '
                         f'text-anchor="middle" font-size="15" font-weight="700" '
                         f'fill="{ink}">{printed}</text>')
    parts.extend(['</g>', '</svg>'])
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")
