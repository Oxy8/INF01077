#!/usr/bin/env python3
"""Valida saídas e sumariza a campanha de linearização sem outras otimizações."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path
from statistics import median


def summarize(raw: Path, output: Path) -> None:
    samples = defaultdict(list)
    hashes = defaultdict(set)
    repeats = defaultdict(set)
    with raw.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            if row["Exact"] != "yes" or row["Hash"] != row["Reference_Hash"]:
                raise ValueError(f"Saída divergente: {row['Image']} {row['Operation']} {row['Variant']}")
            key = (row["Image"], row["Operation"], row["Variant"], row["Phase"],
                   int(row["Threads"]), row["Build"])
            samples[key].append(float(row["Elapsed_ms"]))
            repeats[key].add(int(row["Repeat"]))
            hashes[(row["Image"], row["Operation"])].add(row["Hash"])
    for key, values in hashes.items():
        if len(values) != 1:
            raise ValueError(f"Hashes diferem entre variantes/builds: {key}: {values}")
    for key in samples:
        if len(samples[key]) != len(repeats[key]):
            raise ValueError(f"Repetição duplicada: {key}")
        if set(repeats[key]) != set(range(1, len(samples[key]) + 1)):
            raise ValueError(f"Repetições incompletas: {key}")
    conditions = defaultdict(dict)
    for image, operation, variant, phase, threads, build in samples:
        conditions[(image, operation, variant, phase, threads)][build] = len(
            samples[(image, operation, variant, phase, threads, build)])
    for condition, builds in conditions.items():
        if set(builds) != {"off-avx2", "auto-avx2", "omp-avx2"} or len(set(builds.values())) != 1:
            raise ValueError(f"Build ausente ou amostras desiguais: {condition}: {builds}")

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(("Image", "Operation", "Variant", "Phase", "Threads", "Build",
                         "N", "Median_ms", "Min_ms", "Max_ms", "Hash"))
        for key in sorted(samples):
            image, operation, variant, phase, threads, build = key
            values = samples[key]
            writer.writerow((image, operation, variant, phase, threads, build, len(values),
                             f"{median(values):.6f}", f"{min(values):.6f}",
                             f"{max(values):.6f}", next(iter(hashes[(image, operation)]))))
    print(f"Validadas {len(samples)} configurações e {len(hashes)} saídas; resumo: {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    summarize(args.raw, args.out)
