#!/usr/bin/env python3
"""Resume as coletas cruas do diagnóstico Zoom/Flip por mediana e intervalo."""

from __future__ import annotations

import argparse
import csv
import statistics
from collections import defaultdict
from pathlib import Path


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as source:
        return list(csv.DictReader(source))


def summarize(input_path: Path, output_path: Path, value_fields: list[str], group_fields: list[str]) -> None:
    groups: dict[tuple[str, ...], list[dict[str, str]]] = defaultdict(list)
    for row in read_csv(input_path):
        groups[tuple(row[field] for field in group_fields)].append(row)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    columns = group_fields + ["Samples"] + [f"{field}_{stat}" for field in value_fields for stat in ("Median", "Min", "Max", "Mean", "StdDev")]
    with output_path.open("w", newline="", encoding="utf-8") as destination:
        writer = csv.DictWriter(destination, fieldnames=columns)
        writer.writeheader()
        for key, rows in sorted(groups.items()):
            result = dict(zip(group_fields, key))
            result["Samples"] = len(rows)
            for field in value_fields:
                values = [float(row[field]) for row in rows]
                result[f"{field}_Median"] = f"{statistics.median(values):.6f}"
                result[f"{field}_Min"] = f"{min(values):.6f}"
                result[f"{field}_Max"] = f"{max(values):.6f}"
                result[f"{field}_Mean"] = f"{statistics.fmean(values):.6f}"
                result[f"{field}_StdDev"] = f"{statistics.stdev(values):.6f}" if len(values) > 1 else "0.000000"
            writer.writerow(result)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--zoom-raw", type=Path, required=True)
    parser.add_argument("--zoom-summary", type=Path, required=True)
    parser.add_argument("--flip-raw", type=Path, required=True)
    parser.add_argument("--flip-summary", type=Path, required=True)
    args = parser.parse_args()
    summarize(
        args.zoom_raw,
        args.zoom_summary,
        ["Copy_ms", "Horizontal_ms", "Vertical_ms", "Total_ms"],
        ["Experiment", "Build", "Image", "Width", "Height", "Threads", "Schedule", "Chunk", "Touch_Mode"],
    )
    summarize(
        args.flip_raw,
        args.flip_summary,
        ["Elapsed_ms"],
        ["Experiment", "Build", "Image", "Width", "Height", "Threads", "Schedule", "Chunk"],
    )


if __name__ == "__main__":
    main()
