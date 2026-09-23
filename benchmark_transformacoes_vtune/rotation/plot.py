#!/usr/bin/env python3
"""Plot Rotate_CW and Rotate_CCW VTune ratios for every dynamic chunk size."""

from __future__ import annotations

import argparse
import math
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Sequence

os.environ.setdefault(
    "MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "inf01077-matplotlib")
)

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns


ROTATIONS = ["Rotate_CW", "Rotate_CCW"]
KEYS = ["Num_Threads", "OMP_Schedule", "Transformation"]
PANELS = [
    ("VTune_Speedup_Mediana", "Performance speedup", True),
    (
        "Fator_L1_Pending_Cycles",
        "CYCLE_ACTIVITY.STALLS_L1D_PENDING",
        False,
    ),
    (
        "Fator_L2_Pending_Cycles",
        "CYCLE_ACTIVITY.STALLS_L2_PENDING",
        False,
    ),
    ("Fator_Store_Buffer_Stalls", "RESOURCE_STALLS.SB", False),
]


class RotationPlotError(RuntimeError):
    pass


def dynamic_chunk(schedule: str) -> int:
    match = re.fullmatch(r"dynamic_(\d+)", str(schedule))
    if not match:
        raise RotationPlotError(f"invalid dynamic schedule: {schedule}")
    return int(match.group(1))


def find_dynamic_schedules(data: pd.DataFrame) -> list[str]:
    schedules = [
        str(schedule)
        for schedule in data["OMP_Schedule"].dropna().unique()
        if str(schedule).startswith("dynamic_")
    ]
    if not schedules:
        raise RotationPlotError("no dynamic schedules were found")
    schedules = sorted(set(schedules), key=dynamic_chunk)
    chunks = [dynamic_chunk(schedule) for schedule in schedules]
    if len(chunks) != len(set(chunks)):
        raise RotationPlotError("duplicate dynamic chunk sizes")
    return schedules


def require_columns(data: pd.DataFrame, columns: Sequence[str], source: Path) -> None:
    missing = sorted(set(columns) - set(data.columns))
    if missing:
        raise RotationPlotError(
            f"missing columns in {source}: {', '.join(missing)}"
        )


def factor_label(exponent: int) -> str:
    if exponent == 0:
        return "1.00×"
    value = 2.0**exponent
    if 0.01 <= value < 100:
        return f"{value:.2f}×"
    return f"{value:.3g}×"


def configure_factor_colorbar(axis: plt.Axes, limit: int) -> None:
    if limit <= 4:
        exponents = list(range(-limit, limit + 1))
    else:
        middle = int(round(limit / 2))
        exponents = [-limit, -middle, 0, middle, limit]
    colorbar = axis.collections[0].colorbar
    colorbar.set_ticks(exponents)
    colorbar.set_ticklabels([factor_label(exponent) for exponent in exponents])


def plot_thread(
    data: pd.DataFrame,
    schedules: Sequence[str],
    threads: int,
    output: Path,
) -> None:
    thread_data = data[data["Num_Threads"].eq(threads)]
    expected = len(ROTATIONS) * len(schedules)
    if len(thread_data) != expected:
        raise RotationPlotError(
            f"expected {expected} rotation conditions for {threads} threads; "
            f"found {len(thread_data)}"
        )

    fig, axes = plt.subplots(4, 1, figsize=(23, 15))
    chunk_labels = [str(dynamic_chunk(schedule)) for schedule in schedules]

    for axis, (metric, title, is_speedup) in zip(axes, PANELS):
        factors = (
            thread_data.pivot(
                index="Transformation", columns="OMP_Schedule", values=metric
            )
            .reindex(index=ROTATIONS, columns=schedules)
            .astype(float)
        )
        if factors.isna().all().all():
            raise RotationPlotError(
                f"metric {metric} has no values for {threads} threads"
            )

        positive = factors.where(factors > 0)
        log_values = np.log2(positive)
        finite = np.abs(log_values.to_numpy()[np.isfinite(log_values.to_numpy())])
        limit = max(1, math.ceil(float(finite.max()))) if finite.size else 1
        # A sampled zero is a valid 0x observation, unlike an unavailable ratio.
        log_values = log_values.mask(factors.eq(0), -float(limit))
        annotations = factors.map(
            lambda value: "" if pd.isna(value) else f"{value:.2f}×"
        )

        sns.heatmap(
            log_values,
            ax=axis,
            cmap="RdYlGn" if is_speedup else "RdYlGn_r",
            center=0,
            vmin=-limit,
            vmax=limit,
            annot=annotations,
            fmt="",
            linewidths=0.6,
            linecolor="white",
            mask=factors.isna(),
            xticklabels=chunk_labels,
            yticklabels=ROTATIONS,
            cbar_kws={
                "label": (
                    "Speedup / static (×)"
                    if is_speedup
                    else "Event count / static (×)"
                ),
                "shrink": 0.90,
            },
        )
        configure_factor_colorbar(axis, limit)
        axis.set_title(title, fontsize=14, weight="bold")
        axis.set_xlabel("Dynamic chunk size")
        axis.set_ylabel("Transformation")
        axis.tick_params(axis="x", rotation=0)
        axis.tick_params(axis="y", rotation=0)

    fig.suptitle(
        f"Rotation scheduling across all dynamic chunk sizes — {threads} threads",
        fontsize=19,
        weight="bold",
    )
    fig.text(
        0.5,
        0.012,
        "Every value is a multiplicative ratio to static with the same thread count; 1.00× is the neutral color. "
        "For speedup, below 1× is slower. For events, above 1× means more pending/stall cycles.\n"
        "Blank event cells have no usable sampled ratio because the static reference was zero or unavailable.",
        ha="center",
        fontsize=10,
    )
    fig.tight_layout(rect=(0.02, 0.055, 0.99, 0.96), h_pad=2.0)
    fig.savefig(output, dpi=240)
    plt.close(fig)


def write_readme(output_dir: Path, schedules: Sequence[str], threads: Sequence[int]) -> None:
    chunks = ", ".join(str(dynamic_chunk(schedule)) for schedule in schedules)
    lines = [
        "Rotation VTune analysis",
        "=======================",
        "",
        "This directory compares Rotate_CW and Rotate_CCW with every dynamic chunk size found in the analysis CSVs.",
        "",
        f"Threads: {', '.join(str(value) for value in threads)}",
        f"Dynamic chunks: {chunks}",
        "",
        "Panels",
        "------",
        "",
        "1. VTune speedup relative to static.",
        "2. CYCLE_ACTIVITY.STALLS_L1D_PENDING relative to static.",
        "3. CYCLE_ACTIVITY.STALLS_L2_PENDING relative to static.",
        "4. RESOURCE_STALLS.SB relative to static.",
        "",
        "The heatmaps use log2 internally so reciprocal factors receive equal color intensity, but labels and colorbars display multiplicative factors. Beige is 1.00×.",
        "Large RESOURCE_STALLS.SB ratios can result from a very small sampled static denominator, so interpret their magnitude together with the absolute event CSV and the sampling caveat.",
        "",
        "Run plot.py from this directory to regenerate both PNG files. By default it reads ../vtune_diagnostic_metrics.csv and ../zoom/eventos_hardware_transformacoes.csv.",
    ]
    (output_dir / "README.txt").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    script_dir = Path(__file__).resolve().parent
    analysis_dir = script_dir.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--metrics",
        type=Path,
        default=analysis_dir / "vtune_diagnostic_metrics.csv",
        help="compact VTune condition metrics CSV",
    )
    parser.add_argument(
        "--events",
        type=Path,
        default=analysis_dir / "zoom" / "eventos_hardware_transformacoes.csv",
        help="filtered per-transformation hardware-event CSV",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=script_dir,
        help="directory for PNG and README outputs",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        metrics_path = args.metrics.resolve()
        events_path = args.events.resolve()
        output_dir = args.output_dir.resolve()
        metrics = pd.read_csv(metrics_path)
        events = pd.read_csv(events_path)
        require_columns(
            metrics,
            KEYS + ["VTune_Speedup_Mediana"],
            metrics_path,
        )
        require_columns(
            events,
            KEYS
            + [
                "Fator_L1_Pending_Cycles",
                "Fator_L2_Pending_Cycles",
                "Fator_Store_Buffer_Stalls",
            ],
            events_path,
        )

        metrics = metrics[metrics["Transformation"].isin(ROTATIONS)][
            KEYS + ["VTune_Speedup_Mediana"]
        ]
        events = events[events["Transformation"].isin(ROTATIONS)][
            KEYS
            + [
                "Fator_L1_Pending_Cycles",
                "Fator_L2_Pending_Cycles",
                "Fator_Store_Buffer_Stalls",
            ]
        ]
        schedules = find_dynamic_schedules(metrics)
        metrics = metrics[metrics["OMP_Schedule"].isin(schedules)]
        events = events[events["OMP_Schedule"].isin(schedules)]
        data = metrics.merge(events, on=KEYS, how="left", validate="one_to_one")
        if data.duplicated(KEYS).any():
            raise RotationPlotError("duplicate rotation conditions")

        threads = sorted(int(value) for value in data["Num_Threads"].unique())
        if not threads:
            raise RotationPlotError("no rotation thread configurations were found")
        output_dir.mkdir(parents=True, exist_ok=True)
        for thread_count in threads:
            plot_thread(
                data,
                schedules,
                thread_count,
                output_dir
                / f"rotation_dynamic_all_chunks_{thread_count}_threads.png",
            )
        write_readme(output_dir, schedules, threads)
    except (OSError, ValueError, KeyError, pd.errors.ParserError, RotationPlotError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    print(f"Rotation analysis saved to: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
