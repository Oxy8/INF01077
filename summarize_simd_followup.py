#!/usr/bin/env python3
"""Medianas da rodada SIMD: mantém função de produção e variantes float separadas."""

import argparse
import csv
from collections import defaultdict
from pathlib import Path
from statistics import median


BUILDS = ("off-avx2", "auto-avx2", "omp-avx2")


def read_rows(original: Path, floating: Path):
    with original.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            if row["Validation"] != "passed":
                raise ValueError(f"Hash original divergente: {row['Operation']} {row['Simd_Build']}")
            yield {
                "image": row["Image"], "operation": row["Operation"],
                "variant": "production", "threads": int(row["Threads"]),
                "build": row["Simd_Build"], "time": float(row["Elapsed_ms"]),
                "exact": True, "differing": 0, "error": 0,
                "reference_hash": row["Result_Hash"], "source": original.name,
                "scope": "transformation_including_internal_allocation",
            }
    with floating.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            if row["Phase"] != "total":
                continue
            error = int(row["Max_Abs_Error"])
            exact = row["Exact"] == "yes"
            if error > 1 or (row["Variant"] != "float_tap_reduction" and not exact):
                raise ValueError(f"Saída float inválida: {row['Variant']} {row['Build']}; erro {error}")
            yield {
                "image": row["Image"], "operation": row["Operation"],
                "variant": row["Variant"], "threads": int(row["Threads"]),
                "build": row["Build"], "time": float(row["Elapsed_ms"]),
                "exact": exact, "differing": int(row["Differing_Bytes"]),
                "error": error, "reference_hash": row["Reference_Hash"],
                "source": floating.name,
                "scope": ("kernel_plus_aos_soa_conversions" if row["Variant"] == "float_row_soa"
                          else "preallocated_kernel"),
            }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", required=True, type=Path)
    parser.add_argument("--float", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    groups = defaultdict(list)
    reference_hashes = defaultdict(set)
    for row in read_rows(args.original, args.float):
        if row["build"] not in BUILDS:
            raise ValueError(f"Build inesperado: {row['build']}")
        key = (row["image"], row["operation"], row["variant"], row["threads"], row["build"])
        groups[key].append(row)
        reference_hashes[(row["image"], row["operation"], row["source"])].add(row["reference_hash"])
    if not groups:
        raise ValueError("Nenhuma amostra encontrada")
    if any(len(hashes) != 1 for hashes in reference_hashes.values()):
        raise ValueError("Hash de referência varia entre builds na mesma campanha")

    medians = {key: median(row["time"] for row in values) for key, values in groups.items()}
    result = []
    for (image, operation, variant, threads, build), values in sorted(groups.items()):
        prefix = (image, operation, variant, threads)
        get = lambda name: medians.get(prefix + (name,))
        off, auto, omp = (get(name) for name in BUILDS)
        if any(value is None for value in (off, auto, omp)):
            raise ValueError(f"Falta build para {prefix}")
        result.append({
            "Image": image, "Operation": operation, "Variant": variant,
            "Threads": threads, "Build": build, "Samples": len(values),
            "Median_ms": f"{medians[prefix + (build,)]:.6f}",
            "Min_ms": f"{min(row['time'] for row in values):.6f}",
            "Max_ms": f"{max(row['time'] for row in values):.6f}",
            "Off_over_Auto": f"{off / auto:.6f}",
            "Auto_over_Omp": f"{auto / omp:.6f}",
            "Off_over_Omp": f"{off / omp:.6f}",
            "All_Exact": "yes" if all(row["exact"] for row in values) else "no",
            "Max_Differing_Bytes": max(row["differing"] for row in values),
            "Max_Abs_Error": max(row["error"] for row in values),
            "Scope": values[0]["scope"], "Source_CSV": values[0]["source"],
        })
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=result[0])
        writer.writeheader()
        writer.writerows(result)
    print(f"Resumo: {args.out} ({len(result)} configurações)")


if __name__ == "__main__":
    main()
