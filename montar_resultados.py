#!/usr/bin/env python3
"""Consolida validação e achados das quatro campanhas OpenMP."""

from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parent
BUILDS = ("off", "off-avx2", "omp", "omp-avx2")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as source:
        return list(csv.DictReader(source))


def lookup(rows: Iterable[dict[str, str]], **criteria: object) -> dict[str, str] | None:
    return next((row for row in rows if all(row[key] == str(value) for key, value in criteria.items())), None)


def median(row: dict[str, str]) -> float:
    return float(row["Median_ms"])


def geometric_mean(values: Iterable[float]) -> float:
    valid = [value for value in values if value > 0 and math.isfinite(value)]
    return math.exp(sum(math.log(value) for value in valid) / len(valid)) if valid else math.nan


def write_csv(path: Path, columns: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as destination:
        writer = csv.DictWriter(destination, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def campaign_validation(name: str, directory: Path, raw_name: str, summary_name: str) -> dict[str, object]:
    raw = read_csv(directory / raw_name)
    summary = read_csv(directory / summary_name)
    return {
        "Campaign": name,
        "Directory": directory.name,
        "Raw_measurements": len(raw),
        "Summary_groups": len(summary),
        "Passed_measurements": sum(row.get("Validation") == "passed" for row in raw),
        "Failed_measurements": sum(row.get("Validation") == "failed" for row in raw),
        "Samples_per_group": ",".join(sorted({row["Samples"] for row in summary})),
        "Hostnames": ",".join(sorted({row["Hostname"] for row in raw})),
    }


def regular_findings(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    result = []
    keys = {(r["Image"], r["Operation"], r["Threads"], r["Schedule"], r["Chunk"]) for r in rows}
    for scalar, simd, label in (("off", "omp", "SIMD no alvo padrão"), ("off-avx2", "omp-avx2", "SIMD com AVX2"), ("omp", "omp-avx2", "alvo Haswell mantendo omp simd")):
        values = []
        for image, operation, threads, schedule, chunk in keys:
            base = lookup(rows, Image=image, Operation=operation, Threads=threads, Schedule=schedule, Chunk=chunk, Simd_Build=scalar)
            tested = lookup(rows, Image=image, Operation=operation, Threads=threads, Schedule=schedule, Chunk=chunk, Simd_Build=simd)
            if base and tested and base["Simd_Eligible"] == "yes":
                values.append(median(base) / median(tested))
        result.append({"Area": "Regulares", "Finding": label, "Reference": scalar, "Tested": simd, "Metric": "média geométrica de speedups das medianas", "Value": geometric_mean(values), "Comparisons": len(values)})
    for schedule, chunk, label in (("dynamic", "1", "dynamic,1"), ("dynamic", "16", "dynamic,16")):
        values = []
        for image in sorted({row["Image"] for row in rows}):
            for operation in sorted({row["Operation"] for row in rows}):
                for build in BUILDS:
                    static = lookup(rows, Image=image, Operation=operation, Threads=20, Schedule="static", Chunk="", Simd_Build=build)
                    dynamic = lookup(rows, Image=image, Operation=operation, Threads=20, Schedule=schedule, Chunk=chunk, Simd_Build=build)
                    if static and dynamic:
                        values.append(median(static) / median(dynamic))
        result.append({"Area": "Regulares", "Finding": f"schedule em 20 threads: static sobre {label}", "Reference": "static", "Tested": label, "Metric": "média geométrica de speedups das medianas", "Value": geometric_mean(values), "Comparisons": len(values)})
    return result


def adaptive_findings(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    result = []
    images = sorted({row["Image"] for row in rows})
    configurations = [("static", "", "static"), ("dynamic", "1", "dynamic,1"), ("dynamic", "4", "dynamic,4"), ("dynamic", "16", "dynamic,16"), ("dynamic", "64", "dynamic,64"), ("dynamic", "256", "dynamic,256")]
    for build in BUILDS:
        totals = []
        for schedule, chunk, label in configurations:
            selected = [lookup(rows, Image=image, Threads=20, Schedule=schedule, Chunk=chunk, Simd_Build=build) for image in images]
            if not any(row is None for row in selected):
                totals.append((label, sum(median(row) for row in selected if row)))
        if totals:
            best_label, best_time = min(totals, key=lambda item: item[1])
            static_time = next(time for label, time in totals if label == "static")
            result.append({"Area": "Adaptativo", "Finding": "melhor chunk em 20 threads", "Reference": build, "Tested": best_label, "Metric": "soma das medianas nas 8 imagens (ms)", "Value": best_time, "Comparisons": len(images)})
            result.append({"Area": "Adaptativo", "Finding": "speedup do melhor chunk sobre static", "Reference": f"{build}: static", "Tested": f"{build}: {best_label}", "Metric": "static / melhor soma mediana", "Value": static_time / best_time, "Comparisons": len(images)})
    return result


def smt_findings(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    result = []
    for build in ("omp", "omp-avx2"):
        for operation in sorted({row["Operation"] for row in rows}):
            for schedule, chunk, label in (("static", "", "static"), ("dynamic", "16", "dynamic,16")):
                at_20 = next((row for row in rows if row["Operation"] == operation and row["Simd_Build"] == build and row["Schedule"] == schedule and row["Chunk"] == chunk and row["Threads"] == "20"), None)
                at_40 = next((row for row in rows if row["Operation"] == operation and row["Simd_Build"] == build and row["Schedule"] == schedule and row["Chunk"] == chunk and row["Threads"] == "40"), None)
                if at_20 and at_40:
                    result.append({"Area": "SMT", "Finding": f"20→40 threads: {operation}, {label}", "Reference": build, "Tested": "40 threads", "Metric": "mediana T20 / mediana T40", "Value": median(at_20) / median(at_40), "Comparisons": 1})
    return result


def layout_findings(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    result = []
    for build in BUILDS:
        aos = lookup(rows, Image="6000x6000.png", Operation="Gaussian_11x11", Threads=20, Layout="AoS_Naive", Phase="Kernel", Simd_Build=build)
        separable = lookup(rows, Image="6000x6000.png", Operation="Gaussian_11x11", Threads=20, Layout="SoA_Separable", Phase="Kernel", Simd_Build=build)
        if aos and separable:
            result.append({"Area": "Layout", "Finding": "Gaussian 11×11 separável sobre AoS ingênuo, 6000² T20", "Reference": f"{build}: AoS_Naive", "Tested": f"{build}: SoA_Separable", "Metric": "mediana AoS / mediana separável", "Value": median(aos) / median(separable), "Comparisons": 1})
    return result


def variability_rows(campaign: str, rows: list[dict[str, str]], limit: int = 12) -> list[dict[str, object]]:
    selected = []
    for row in rows:
        center = median(row)
        if center <= 0:
            continue
        selected.append({
            "Campaign": campaign,
            "Image": row["Image"],
            "Operation": row["Operation"],
            "Build": row["Simd_Build"],
            "Threads": row["Threads"],
            "Schedule": row["Schedule"] + ("," + row["Chunk"] if row["Chunk"] else ""),
            "Median_ms": row["Median_ms"],
            "Min_ms": row["Min_ms"],
            "Max_ms": row["Max_ms"],
            "Range_over_median": (float(row["Max_ms"]) - float(row["Min_ms"])) / center,
        })
    return sorted(selected, key=lambda row: float(row["Range_over_median"]), reverse=True)[:limit]


def main() -> None:
    parser = argparse.ArgumentParser(description="Consolida quatro diretórios de resultados PCAD.")
    parser.add_argument("--regular", required=True)
    parser.add_argument("--adaptive", required=True)
    parser.add_argument("--smt", required=True)
    parser.add_argument("--layout", required=True)
    parser.add_argument("--out", default="resultados_consolidados")
    args = parser.parse_args()
    directories = {key: Path(getattr(args, key)) for key in ("regular", "adaptive", "smt", "layout")}
    directories = {key: path if path.is_absolute() else ROOT / path for key, path in directories.items()}
    output = Path(args.out)
    output = output if output.is_absolute() else ROOT / output
    output.mkdir(parents=True, exist_ok=True)
    regular = read_csv(directories["regular"] / "benchmark_summary.csv")
    adaptive = read_csv(directories["adaptive"] / "benchmark_summary.csv")
    smt = read_csv(directories["smt"] / "benchmark_summary.csv")
    layout = read_csv(directories["layout"] / "layout_summary.csv")
    validation = [
        campaign_validation("regular", directories["regular"], "benchmark_raw.csv", "benchmark_summary.csv"),
        campaign_validation("adaptive", directories["adaptive"], "benchmark_raw.csv", "benchmark_summary.csv"),
        campaign_validation("smt", directories["smt"], "benchmark_raw.csv", "benchmark_summary.csv"),
        campaign_validation("layout", directories["layout"], "layout_raw.csv", "layout_summary.csv"),
    ]
    findings = regular_findings(regular) + adaptive_findings(adaptive) + smt_findings(smt) + layout_findings(layout)
    variability = variability_rows("regular", regular) + variability_rows("adaptive", adaptive) + variability_rows("smt", smt) + variability_rows("layout", layout)
    write_csv(output / "validacao_campanhas.csv", list(validation[0]), validation)
    write_csv(output / "achados_chave.csv", ["Area", "Finding", "Reference", "Tested", "Metric", "Value", "Comparisons"], findings)
    write_csv(output / "maior_variabilidade.csv", ["Campaign", "Image", "Operation", "Build", "Threads", "Schedule", "Median_ms", "Min_ms", "Max_ms", "Range_over_median"], variability)
    lines = ["# Resultados consolidados", "", "## Validação", "", "| Campanha | Medições | Passaram | Falharam | Grupos | Amostras/grupo | Nó |", "|---|---:|---:|---:|---:|---|---|"]
    lines.extend(f"| {row['Campaign']} | {row['Raw_measurements']} | {row['Passed_measurements']} | {row['Failed_measurements']} | {row['Summary_groups']} | {row['Samples_per_group']} | {row['Hostnames']} |" for row in validation)
    lines += ["", "Todos os gráficos e razões abaixo usam a **mediana** das cinco amostras. Consulte mínimo e máximo nos CSVs de resumo antes de interpretar diferenças pequenas. As 12 configurações mais dispersas de cada campanha estão em `maior_variabilidade.csv`.", "", "## Achados numéricos", "", "| Área | Achado | Referência → teste | Valor |", "|---|---|---|---:|"]
    lines.extend(f"| {row['Area']} | {row['Finding']} | {row['Reference']} → {row['Tested']} | {float(row['Value']):.3f} |" for row in findings)
    lines += ["", "Valores maiores que 1 em speedups favorecem o teste; valores menores que 1 favorecem a referência.", ""]
    (output / "RELATORIO_RESULTADOS.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Consolidação gerada em: {output}")


if __name__ == "__main__":
    main()
