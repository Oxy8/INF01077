#!/usr/bin/env python3
"""Resume o experimento AoS versus SoA sem misturar fases distintas."""

import argparse
import csv
import statistics
from collections import defaultdict
from pathlib import Path


GROUP_COLUMNS = [
    "Image", "Operation", "Width", "Height", "Layout", "Phase", "Threads", "Schedule", "Chunk",
    "Simd_Build", "OMP_Places", "OMP_Proc_Bind", "Hostname", "Compiler", "Build_Flags",
]


def main():
    parser = argparse.ArgumentParser(description="Resume medições do experimento AoS versus SoA.")
    parser.add_argument("--raw", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    groups = defaultdict(list)
    failures = []
    with args.raw.open(newline="", encoding="utf-8") as source:
        for row in csv.DictReader(source):
            if row["Validation"] != "passed":
                failures.append(row)
                continue
            groups[tuple(row[column] for column in GROUP_COLUMNS)].append(float(row["Elapsed_ms"]))

    if failures:
        raise SystemExit(f"Há {len(failures)} medições cuja reconstrução SoA não coincidiu com AoS.")
    if not groups:
        raise SystemExit("Nenhuma medição válida encontrada no CSV bruto.")

    rows = []
    for key, samples in groups.items():
        fields = dict(zip(GROUP_COLUMNS, key))
        rows.append({
            **fields,
            "Samples": len(samples),
            "Median_ms": f"{statistics.median(samples):.6f}",
            "Min_ms": f"{min(samples):.6f}",
            "Max_ms": f"{max(samples):.6f}",
            "Mean_ms": f"{statistics.fmean(samples):.6f}",
            "StdDev_ms": f"{statistics.stdev(samples):.6f}" if len(samples) > 1 else "0.000000",
        })

    args.out.parent.mkdir(parents=True, exist_ok=True)
    fields = GROUP_COLUMNS + ["Samples", "Median_ms", "Min_ms", "Max_ms", "Mean_ms", "StdDev_ms"]
    with args.out.open("w", newline="", encoding="utf-8") as destination:
        writer = csv.DictWriter(destination, fieldnames=fields)
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda row: tuple(row[column] for column in GROUP_COLUMNS)))


if __name__ == "__main__":
    main()
