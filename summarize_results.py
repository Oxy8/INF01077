#!/usr/bin/env python3
"""Resume o CSV normalizado produzido por image_benchmark.

O script usa apenas a biblioteca padrão para também funcionar nos nós do PCAD
sem depender de pandas. Cada grupo preserva operação, imagem, escala, schedule
e variante SIMD; portanto não agrega workloads heterogêneos por acidente.
"""

import argparse
import csv
import statistics
from collections import defaultdict
from pathlib import Path


GROUP_COLUMNS = [
    "Image", "Width", "Height", "Operation", "Threads", "Schedule", "Chunk",
    "Simd_Build", "Simd_Eligible", "OMP_Places", "OMP_Proc_Bind", "Hostname",
    "Compiler", "Build_Flags",
]


def parse_arguments():
    parser = argparse.ArgumentParser(description="Gera mediana, mínimo e máximo dos benchmarks OpenMP.")
    parser.add_argument("--raw", required=True, type=Path, help="CSV bruto normalizado")
    parser.add_argument("--out", required=True, type=Path, help="CSV resumido")
    return parser.parse_args()


def main():
    args = parse_arguments()
    groups = defaultdict(list)
    failures = []

    with args.raw.open(newline="", encoding="utf-8") as source:
        for row in csv.DictReader(source):
            if row["Validation"] != "passed":
                failures.append((row["Image"], row["Operation"], row["Validation"]))
                continue
            key = tuple(row[column] for column in GROUP_COLUMNS)
            groups[key].append(float(row["Elapsed_ms"]))

    if failures:
        formatted = ", ".join(f"{image}/{operation} ({status})" for image, operation, status in failures[:10])
        raise SystemExit(f"Há hashes não validados no CSV: {formatted}")
    if not groups:
        raise SystemExit("Nenhuma medição válida encontrada no CSV bruto.")

    rows = []
    baselines = {}
    for key, samples in groups.items():
        fields = dict(zip(GROUP_COLUMNS, key))
        median = statistics.median(samples)
        row = {
            **fields,
            "Samples": len(samples),
            "Median_ms": f"{median:.6f}",
            "Min_ms": f"{min(samples):.6f}",
            "Max_ms": f"{max(samples):.6f}",
            "Mean_ms": f"{statistics.fmean(samples):.6f}",
            "StdDev_ms": f"{statistics.stdev(samples):.6f}" if len(samples) > 1 else "0.000000",
        }
        rows.append(row)
        if fields["Schedule"] == "static":
            baseline_key = tuple(fields[column] for column in [
                "Image", "Width", "Height", "Operation", "Threads", "Simd_Build", "OMP_Places",
                "OMP_Proc_Bind", "Hostname", "Compiler", "Build_Flags",
            ])
            baselines[baseline_key] = median

    for row in rows:
        baseline_key = tuple(row[column] for column in [
            "Image", "Width", "Height", "Operation", "Threads", "Simd_Build", "OMP_Places",
            "OMP_Proc_Bind", "Hostname", "Compiler", "Build_Flags",
        ])
        baseline = baselines.get(baseline_key)
        row["Speedup_vs_Static"] = f"{baseline / float(row['Median_ms']):.6f}" if baseline else ""

    args.out.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = GROUP_COLUMNS + [
        "Samples", "Median_ms", "Min_ms", "Max_ms", "Mean_ms", "StdDev_ms", "Speedup_vs_Static",
    ]
    with args.out.open("w", newline="", encoding="utf-8") as destination:
        writer = csv.DictWriter(destination, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda row: tuple(row[column] for column in GROUP_COLUMNS)))


if __name__ == "__main__":
    main()
