#!/usr/bin/env python3
"""Resume a campanha de generalização da convolução gaussiana separável."""
from __future__ import annotations

import argparse
import csv
import statistics
from collections import defaultdict
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    groups: dict[tuple[str, ...], list[float]] = defaultdict(list)
    with args.raw.open(newline="", encoding="utf-8") as source:
        for row in csv.DictReader(source):
            if row["Validation"] != "passed":
                raise SystemExit(f"Validação falhou em {row}")
            key = (row["Image"], row["Taps"], row["Threads"], row["Build"], row["Component"])
            groups[key].append(float(row["Elapsed_ms"]))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as destination:
        fields = ["Image", "Taps", "Threads", "Build", "Component", "Samples", "Median_ms", "Min_ms", "Max_ms", "Mean_ms", "StdDev_ms"]
        writer = csv.DictWriter(destination, fieldnames=fields)
        writer.writeheader()
        for key, values in sorted(groups.items(), key=lambda item: item[0]):
            writer.writerow(dict(zip(fields[:5], key), Samples=len(values), Median_ms=f"{statistics.median(values):.6f}", Min_ms=f"{min(values):.6f}", Max_ms=f"{max(values):.6f}", Mean_ms=f"{statistics.fmean(values):.6f}", StdDev_ms=f"{statistics.stdev(values):.6f}" if len(values) > 1 else "0.000000"))


if __name__ == "__main__":
    main()
