#!/usr/bin/env python3
"""Dois mapas SIMD finais, com a origem e o escopo de cada linha auditáveis."""

from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path
from statistics import median

from plot_simd_heatmap import presentation_heatmap


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "visualizacoes_simd_finais"
IMAGE = "6000x6000.png"
BUILDS = ("off-avx2", "auto-avx2", "omp-avx2")
THREADS = (1, 20)

SOURCES = {
    "825196": ROOT / "resultados_pcad_hype_simd_followup_825196" / "original_raw.csv",
    "825200": ROOT / "resultados_pcad_hype_linear_simd_825200" / "linear_simd_raw.csv",
    "825290-fases": ROOT / "resultados_pcad_hype_simd_phase_zoom_825290" / "phase_raw.csv",
    "825290-zoom-producao": ROOT / "resultados_pcad_hype_simd_phase_zoom_825290" / "zoom_production_raw.csv",
    "825290-zoom-controle": ROOT / "resultados_pcad_hype_simd_phase_zoom_825290" / "zoom_control_raw.csv",
}
EXPECTED_N = {
    "825196": 5,
    "825200": 5,
    "825290-fases": 10,
    "825290-zoom-producao": 20,
    "825290-zoom-controle": 10,
}

# (rótulo, fonte, operação no CSV, variante, fase)
ORIGINAL = (
    ("Negative", "825196", "Negative", None, None),
    ("Adjust Brightness", "825196", "Adjust_Brightness", None, None),
    ("Adjust Contrast", "825196", "Adjust_Contrast", None, None),
    ("Convolução 11×11", "825196", "Gaussian_11x11", None, None),
    ("Equalize Histogram", "825196", "Equalize_Histogram", None, None),
    ("Quantize sem Grayscale*", "825290-fases", "Quantize", None, "production_after_gray"),
    ("Zoom In*", "825290-zoom-producao", "Zoom_In", None, None),
    ("Grayscale*", "825290-fases", "Quantize", None, "grayscale"),
)
REWRITTEN = (
    ("Negative · bytes lineares", "825200", "Negative", "linear_bytes", "total"),
    ("Brightness · bytes lineares", "825200", "Adjust_Brightness", "linear_bytes", "total"),
    ("Contrast · bytes lineares", "825200", "Adjust_Contrast", "linear_bytes", "total"),
    ("Convolução 11×11", "825200", "Gaussian_11x11", "row_linear_aos", "total"),
    ("Equalize Histogram · original*", "825290-fases", "Equalize_Histogram", None, "production_total"),
    ("Equalize Histogram · remap linear", "825200", "Equalize_Histogram", "linear_remap", "total"),
    ("Quantize sem Grayscale*", "825290-fases", "Quantize", None, "production_after_gray"),
    ("Zoom In · saída pré-alocada*", "825290-zoom-controle", "Zoom_In", "original", "total"),
    ("Grayscale*", "825290-fases", "Quantize", None, "grayscale"),
)


@lru_cache(maxsize=None)
def read_rows(source: str) -> list[dict[str, str]]:
    with SOURCES[source].open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def source_hash(source: str, name: str) -> str:
    manifest = SOURCES[source].parent / "source_sha256.txt"
    for line in manifest.read_text(encoding="utf-8").splitlines():
        digest, _, filename = line.partition("  ")
        if filename == name:
            return digest
    raise ValueError(f"Fonte ausente do manifesto: {manifest}: {name}")


def validate_sources() -> None:
    core = "577262-FPI-Relatorio2/image_manipulation.cpp"
    if len({source_hash(source, core) for source in SOURCES}) != 1:
        raise ValueError("Versões diferentes de image_manipulation.cpp nos jobs")
    experiment = "577262-FPI-Relatorio2/vectorization_benchmark.cpp"
    if source_hash("825200", experiment) != source_hash("825290-zoom-controle", experiment):
        raise ValueError("Controle Zoom e variantes linearizadas usam fontes diferentes")


def measured(source: str, operation: str, variant: str | None,
             phase: str | None, threads: int) -> tuple[dict[str, float], int, str]:
    records = []
    for row in read_rows(source):
        if row["Image"] != IMAGE or row["Operation"] != operation or int(row["Threads"]) != threads:
            continue
        if variant is not None and row["Variant"] != variant:
            continue
        if phase is not None and row["Phase"] != phase:
            continue
        if "Schedule" in row and row["Schedule"] != "static":
            raise ValueError(f"Schedule inesperado em {source}")
        if row.get("Validation", "passed") != "passed" or row.get("Exact", "yes") != "yes":
            raise ValueError(f"Saída inválida em {source}: {operation}, {threads} threads")
        if "Reference_Hash" in row and row["Hash"] != row["Reference_Hash"]:
            raise ValueError(f"Hash divergente em {source}: {operation}, {threads} threads")
        records.append(row)

    build_field = "Simd_Build" if source in ("825196", "825290-zoom-producao") else "Build"
    hash_field = "Result_Hash" if source in ("825196", "825290-zoom-producao") else (
        "Output_Hash" if source == "825290-fases" else "Hash")
    by_build = {build: [row for row in records if row[build_field] == build] for build in BUILDS}
    counts = {len(group) for group in by_build.values()}
    hashes = {row[hash_field] for row in records}
    if counts != {EXPECTED_N[source]} or len(hashes) != 1:
        raise ValueError(f"Dados incompletos ou saídas diferentes: {source}, {operation}, {threads}")
    for build, group in by_build.items():
        if len({row["Repeat"] for row in group}) != len(group):
            raise ValueError(f"Repetições duplicadas: {source}, {operation}, {threads}, {build}")
    values = {build: median(float(row["Elapsed_ms"]) for row in group)
              for build, group in by_build.items()}
    return values, counts.pop(), hashes.pop()


def render_map(name: str, specs: tuple, original: bool, writer: csv.writer) -> None:
    labels, matrix = [], []
    for label, source, operation, variant, phase in specs:
        labels.append(label)
        numbers = []
        for threads in THREADS:
            values, count, image_hash = measured(source, operation, variant, phase, threads)
            off, auto, omp = (values[build] for build in BUILDS)
            ratios = (off / auto, off / omp, auto / omp)
            numbers.extend((ratios[1],) if original else ratios)
            writer.writerow((name, label, source, SOURCES[source].relative_to(ROOT),
                             operation, variant or "production", phase or "total", IMAGE,
                             threads, count, f"{off:.6f}", f"{auto:.6f}", f"{omp:.6f}",
                             *(f"{ratio:.6f}" for ratio in ratios), image_hash))
        matrix.append(numbers)

    if original:
        columns = ["off / omp", "off / omp"]
        groups = [("1 thread", 0, 0), ("20 threads", 1, 1)]
        title = "SIMD na abordagem original — 6000×6000, static"
        subtitle = "Razão das medianas; >1× favorece omp. * Job 825290; demais: 825196. Quantize sem Grayscale."
    else:
        columns = ["off / auto", "off / omp", "auto / omp"] * 2
        groups = [("1 thread", 0, 2), ("20 threads", 3, 5)]
        title = "SIMD após reorganizar os laços — 6000×6000, static"
        subtitle = "Razão das medianas; >1× favorece o denominador. * Job 825290; demais: 825200."
    presentation_heatmap(OUTPUT / name, title, subtitle, columns, labels, matrix, groups)


def main() -> None:
    validate_sources()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with (OUTPUT / "dados_mapas.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(("Map", "Label", "Job", "Source_CSV", "Operation", "Variant", "Phase",
                         "Image", "Threads", "N", "Off_ms", "Auto_ms", "Omp_ms",
                         "Off_over_Auto", "Off_over_Omp", "Auto_over_Omp", "Hash"))
        render_map("01_abordagem_original.svg", ORIGINAL, True, writer)
        render_map("02_abordagem_linearizada.svg", REWRITTEN, False, writer)
    print(f"Dois mapas finais e proveniência: {OUTPUT}")


if __name__ == "__main__":
    main()
