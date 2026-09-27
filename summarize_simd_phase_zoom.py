#!/usr/bin/env python3
"""Valida hashes/repetições e resume a campanha curta SIMD por medianas."""

import argparse
import csv
from collections import defaultdict
from pathlib import Path
from statistics import median


BUILDS = {"off-avx2", "auto-avx2", "omp-avx2"}


def rows(path):
    with path.open(newline="", encoding="utf-8") as stream:
        yield from csv.DictReader(stream)


def validate_samples(groups):
    for key, entries in groups.items():
        repeats = [int(row["Repeat"]) for row in entries]
        if sorted(repeats) != list(range(1, len(entries) + 1)):
            raise ValueError(f"Repetições ausentes ou duplicadas: {key}: {repeats}")
    conditions = defaultdict(dict)
    for key, entries in groups.items():
        conditions[key[:-1]][key[-1]] = len(entries)
    for condition, builds in conditions.items():
        if set(builds) != BUILDS or len(set(builds.values())) != 1:
            raise ValueError(f"Builds ou número de amostras diferentes: {condition}: {builds}")


def summarize_production(path, output):
    groups = defaultdict(list)
    hashes = set()
    for row in rows(path):
        if row["Operation"] != "Zoom_In" or row["Schedule"] != "static" or row["Validation"] != "passed":
            raise ValueError(f"Zoom de produção inválido: {row}")
        groups[(row["Image"], int(row["Threads"]), row["Simd_Build"])].append(row)
        hashes.add(row["Result_Hash"])
    if not groups or len(hashes) != 1:
        raise ValueError("Zoom sem amostras ou com hashes diferentes")
    validate_samples(groups)
    medians = {key: median(float(row["Elapsed_ms"]) for row in entries)
               for key, entries in groups.items()}
    with output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(("Image", "Threads", "Build", "N", "Median_ms", "Min_ms", "Max_ms",
                         "Off_over_Auto", "Auto_over_Omp", "Off_over_Omp", "Hash"))
        for (image, threads, build), entries in sorted(groups.items()):
            off, auto, omp = (medians[(image, threads, variant)]
                              for variant in ("off-avx2", "auto-avx2", "omp-avx2"))
            times = [float(row["Elapsed_ms"]) for row in entries]
            writer.writerow((image, threads, build, len(times), f"{median(times):.6f}",
                             f"{min(times):.6f}", f"{max(times):.6f}", f"{off / auto:.6f}",
                             f"{auto / omp:.6f}", f"{off / omp:.6f}", next(iter(hashes))))
    return len(groups)


def summarize_phases(path, output):
    groups = defaultdict(list)
    hashes = defaultdict(set)
    scopes = {}
    for row in rows(path):
        if row["Exact"] != "yes":
            raise ValueError(f"Fase divergente: {row}")
        key = (row["Image"], row["Operation"], row["Phase"], int(row["Threads"]), row["Build"])
        groups[key].append(row)
        hashes[(row["Image"], row["Operation"])].add(row["Output_Hash"])
        scopes[key] = row["Scope"]
    if not groups or any(len(values) != 1 for values in hashes.values()):
        raise ValueError(f"Fases sem amostras ou hashes diferentes: {hashes}")
    validate_samples(groups)
    with output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(("Image", "Operation", "Phase", "Threads", "Build", "N", "Median_ms",
                         "Min_ms", "Max_ms", "Scope", "Hash"))
        for key, entries in sorted(groups.items()):
            times = [float(row["Elapsed_ms"]) for row in entries]
            image, operation, phase, threads, build = key
            writer.writerow((image, operation, phase, threads, build, len(times),
                             f"{median(times):.6f}", f"{min(times):.6f}",
                             f"{max(times):.6f}", scopes[key], next(iter(hashes[(image, operation)]))))
    return len(groups)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--production", type=Path, required=True)
    parser.add_argument("--phases", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    zoom = summarize_production(args.production, args.out / "zoom_production_summary.csv")
    phases = summarize_phases(args.phases, args.out / "phase_summary.csv")
    print(f"Validados: {zoom} grupos Zoom e {phases} grupos de fases")


if __name__ == "__main__":
    main()
