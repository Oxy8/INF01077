#!/usr/bin/env python3
"""Merge a VTune campaign into one wide, traceable CSV using only stdlib."""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterator, List, Mapping, Optional, Sequence, Set, Tuple


COMMON_FIELDS = [
    "Record_Type",
    "Report_Type",
    "Campaign_ID",
    "Collection_ID",
    "Collection_Repetition",
    "Slurm_Job_ID",
    "Host",
    "VTune_Version",
    "CPU_Model",
    "Kernel",
    "Num_Threads",
    "OMP_Schedule_Raw",
    "OMP_Schedule",
    "Schedule_Kind",
    "Chunk_Size",
    "Transformation",
    "Image",
    "Workload_Iteration",
    "Workload_Iterations",
    "Frame_ID",
    "Time_ms",
    "Function",
    "Module",
    "Affinity_Label",
    "OMP_PLACES",
    "OMP_PROC_BIND",
    "GOMP_CPU_AFFINITY",
    "VTune_Knobs",
    "Git_Commit",
    "Git_Status",
    "Result_Dir",
    "Status",
    "Unsupported_Metrics",
    "Unsupported_Reports",
    "Failure",
]

REQUIRED_REPORTS = {
    "hotspots.csv": ("function", "hotspots", ("function",)),
    "hw-events.csv": ("function", "hw_events", ("function",)),
    "frames.csv": ("frame", "frames", ("frame",)),
}

OPTIONAL_REPORTS = {
    "tasks.csv": ("frame", "tasks", ("task",)),
    "task-functions.csv": ("function", "task_functions", ("task", "function")),
    "task-hw-events.csv": ("function", "task_hw_events", ("task", "function")),
}

REPORTS = {**REQUIRED_REPORTS, **OPTIONAL_REPORTS}

REQUIRED_TIMING_FIELDS = {
    "Collection_ID",
    "Collection_Repetition",
    "Image",
    "Num_Threads",
    "OMP_Schedule",
    "Transformation",
    "Workload_Iteration",
    "Workload_Iterations",
    "Frame_ID",
    "Time_ms",
}


class AggregationError(RuntimeError):
    pass


def sanitize_column(value: str) -> str:
    value = value.strip().replace("%", " Percent ")
    value = re.sub(r"[^0-9A-Za-z]+", "_", value).strip("_")
    return value or "Value"


def unique_columns(headers: Sequence[str], prefix: str) -> List[str]:
    counts: Counter[str] = Counter()
    result: List[str] = []
    for header in headers:
        base = f"{prefix}__{sanitize_column(header)}"
        counts[base] += 1
        result.append(base if counts[base] == 1 else f"{base}_{counts[base]}")
    return result


def read_manifest(run_dir: Path) -> List[Dict[str, str]]:
    path = run_dir / "manifest.csv"
    if not path.is_file():
        raise AggregationError(f"manifesto nao encontrado: {path}")
    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise AggregationError(f"manifesto vazio: {path}")
    identifiers = [row.get("Collection_ID", "") for row in rows]
    if "" in identifiers or len(identifiers) != len(set(identifiers)):
        raise AggregationError("Collection_ID vazio ou duplicado no manifesto")
    return rows


def read_key_values(path: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return values


def base_record(run_dir: Path, manifest: Mapping[str, str]) -> Dict[str, str]:
    collection_id = manifest["Collection_ID"]
    collection_dir = run_dir / "collections" / collection_id
    metadata = read_key_values(collection_dir / "metadata.env")
    record = {field: "" for field in COMMON_FIELDS}
    for field in (
        "Collection_ID",
        "Collection_Repetition",
        "Num_Threads",
        "OMP_Schedule_Raw",
        "OMP_Schedule",
        "Schedule_Kind",
        "Chunk_Size",
        "Transformation",
        "Workload_Iterations",
    ):
        record[field] = manifest.get(field, "")
    for field in (
        "Campaign_ID",
        "Slurm_Job_ID",
        "Host",
        "VTune_Version",
        "CPU_Model",
        "Kernel",
        "Affinity_Label",
        "OMP_PLACES",
        "OMP_PROC_BIND",
        "GOMP_CPU_AFFINITY",
        "VTune_Knobs",
        "Git_Commit",
        "Git_Status",
    ):
        record[field] = metadata.get(field, "")
    record["Result_Dir"] = f"collections/{collection_id}/result"
    record["Image"] = "ALL"
    complete = is_complete(collection_dir)
    record["Status"] = "complete" if complete else "incomplete"
    failure_file = collection_dir / "failure.txt"
    if failure_file.is_file():
        record["Status"] = "failed"
        record["Failure"] = failure_file.read_text(
            encoding="utf-8", errors="replace"
        ).strip()
    unsupported_reports = collection_dir / "reports" / "unsupported-reports.txt"
    if unsupported_reports.is_file():
        record["Unsupported_Reports"] = ";".join(
            line.strip()
            for line in unsupported_reports.read_text(
                encoding="utf-8", errors="replace"
            ).splitlines()
            if line.strip()
        )
    return record


def is_complete(collection_dir: Path) -> bool:
    marker = collection_dir / ".complete"
    if not marker.is_file():
        return False
    required = [
        collection_dir / "metadata.env",
        collection_dir / "timings.csv",
        collection_dir / "result",
        collection_dir / "reports" / "summary.csv",
    ]
    required.extend(collection_dir / "reports" / name for name in REQUIRED_REPORTS)
    return all(path.exists() and (path.is_dir() or path.stat().st_size > 0) for path in required)


def read_csv_rows(path: Path) -> List[List[str]]:
    with path.open(newline="", encoding="utf-8", errors="replace") as stream:
        return [[cell.strip() for cell in row] for row in csv.reader(stream)]


def summary_metrics(path: Path) -> Tuple[Dict[str, str], List[str]]:
    metrics: Dict[str, str] = {}
    unsupported: List[str] = []
    counts: Counter[str] = Counter()
    for row in read_csv_rows(path):
        if len(row) != 2 or not row[0] or not row[1]:
            continue
        if row[0].strip().lower() in {"metric name", "metric", "name"}:
            continue
        base = f"Summary__{sanitize_column(row[0])}"
        counts[base] += 1
        column = base if counts[base] == 1 else f"{base}_{counts[base]}"
        metrics[column] = row[1]
        normalized_value = row[1].strip().lower()
        if normalized_value.startswith("n/a") or normalized_value in {
            "not available",
            "not supported",
        }:
            unsupported.append(row[0].strip())
    if not metrics:
        raise AggregationError(f"resumo VTune sem metricas reconheciveis: {path}")
    return metrics, unsupported


def locate_report_header(
    rows: Sequence[Sequence[str]], required_tokens: Sequence[str], path: Path
) -> int:
    normalized_tokens = tuple(token.lower() for token in required_tokens)
    for index, row in enumerate(rows):
        cells = [sanitize_column(cell).lower() for cell in row]
        if len(cells) < 2:
            continue
        if all(any(token == cell or token in cell for cell in cells) for token in normalized_tokens):
            return index
    raise AggregationError(f"cabecalho VTune nao reconhecido: {path}")


def prepare_report_table(
    path: Path, required_tokens: Sequence[str]
) -> Tuple[List[str], List[List[str]]]:
    rows = read_csv_rows(path)
    header_index = locate_report_header(rows, required_tokens, path)
    headers = list(rows[header_index])
    data_index = header_index + 1

    # Some VTune releases split long hardware-event headings over two CSV rows.
    # Continuation rows have an empty grouping cell and must not become data rows.
    while data_index < len(rows) and rows[data_index] and not rows[data_index][0]:
        continuation = rows[data_index]
        for index, value in enumerate(continuation):
            if not value:
                continue
            while index >= len(headers):
                headers.append("")
            headers[index] = f"{headers[index]} {value}".strip()
        data_index += 1
    return headers, rows[data_index:]


def report_records(
    path: Path,
    record_type: str,
    report_type: str,
    required_tokens: Sequence[str],
    base: Mapping[str, str],
) -> Iterator[Dict[str, str]]:
    headers, data_rows = prepare_report_table(path, required_tokens)
    columns = unique_columns(headers, report_type)
    normalized_headers = [sanitize_column(header).lower() for header in headers]
    for values in data_rows:
        if not any(values) or values == headers:
            continue
        record = dict(base)
        record["Record_Type"] = record_type
        record["Report_Type"] = report_type
        for index, column in enumerate(columns):
            record[column] = values[index] if index < len(values) else ""
        for index, normalized in enumerate(normalized_headers):
            value = values[index] if index < len(values) else ""
            if normalized == "function" and not record["Function"]:
                record["Function"] = value
            elif normalized == "module" and not record["Module"]:
                record["Module"] = value
            elif normalized == "frame" and not record["Frame_ID"]:
                record["Frame_ID"] = value
        yield record


def timing_records(path: Path, base: Mapping[str, str]) -> Iterator[Dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        fields = set(reader.fieldnames or [])
        if not REQUIRED_TIMING_FIELDS.issubset(fields):
            missing = sorted(REQUIRED_TIMING_FIELDS - fields)
            raise AggregationError(f"colunas ausentes em {path}: {', '.join(missing)}")
        for timing in reader:
            record = dict(base)
            record["Record_Type"] = "timing"
            record["Report_Type"] = "benchmark"
            for field in REQUIRED_TIMING_FIELDS:
                record[field] = timing.get(field, "")
            yield record


def collection_records(
    run_dir: Path, manifest: Mapping[str, str], include_incomplete: bool
) -> Iterator[Dict[str, str]]:
    collection_dir = run_dir / "collections" / manifest["Collection_ID"]
    base = base_record(run_dir, manifest)
    if not is_complete(collection_dir):
        if include_incomplete:
            base["Record_Type"] = "collection"
            base["Report_Type"] = "manifest"
            yield base
        return

    summary, unsupported = summary_metrics(collection_dir / "reports" / "summary.csv")
    collection = dict(base)
    collection["Record_Type"] = "collection"
    collection["Report_Type"] = "summary"
    collection["Unsupported_Metrics"] = ";".join(unsupported)
    collection.update(summary)
    yield collection

    yield from timing_records(collection_dir / "timings.csv", base)
    for filename, (record_type, report_type, tokens) in REPORTS.items():
        report_path = collection_dir / "reports" / filename
        if not report_path.is_file() or report_path.stat().st_size == 0:
            continue
        yield from report_records(
            report_path,
            record_type,
            report_type,
            tokens,
            base,
        )


def all_records(
    run_dir: Path,
    manifest_rows: Sequence[Mapping[str, str]],
    include_incomplete: bool,
) -> Iterator[Dict[str, str]]:
    for manifest in manifest_rows:
        yield from collection_records(run_dir, manifest, include_incomplete)


def validate_timing_file(
    path: Path, manifest: Mapping[str, str]
) -> Tuple[Set[str], int]:
    counts: Dict[str, Set[int]] = defaultdict(set)
    rows = 0
    expected_iterations = int(manifest["Workload_Iterations"])
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        fields = set(reader.fieldnames or [])
        if not REQUIRED_TIMING_FIELDS.issubset(fields):
            raise AggregationError(f"CSV de tempos incompleto: {path}")
        for row in reader:
            rows += 1
            if row["Collection_ID"] != manifest["Collection_ID"]:
                raise AggregationError(f"Collection_ID divergente em {path}")
            if row["Transformation"] != manifest["Transformation"]:
                raise AggregationError(f"transformacao divergente em {path}")
            if row["Num_Threads"] != manifest["Num_Threads"]:
                raise AggregationError(f"threads divergentes em {path}")
            if row["OMP_Schedule"] != manifest["OMP_Schedule"]:
                raise AggregationError(f"schedule divergente em {path}")
            if row["Workload_Iterations"] != manifest["Workload_Iterations"]:
                raise AggregationError(f"numero de iteracoes divergente em {path}")
            try:
                iteration = int(row["Workload_Iteration"])
                elapsed = float(row["Time_ms"])
            except ValueError as error:
                raise AggregationError(f"tempo ou iteracao invalida em {path}") from error
            if elapsed <= 0:
                raise AggregationError(f"tempo nao positivo em {path}")
            counts[row["Image"]].add(iteration)
    expected = set(range(1, expected_iterations + 1))
    if not counts or any(iterations != expected for iterations in counts.values()):
        raise AggregationError(f"iteracoes ausentes ou duplicadas em {path}")
    if rows != len(counts) * expected_iterations:
        raise AggregationError(f"numero de linhas inesperado em {path}")
    return set(counts), rows


def validate_campaign(
    run_dir: Path,
    manifest_rows: Sequence[Mapping[str, str]],
    expected_collections: Optional[int],
    require_complete: bool,
) -> Tuple[int, int, int]:
    if expected_collections is not None and len(manifest_rows) != expected_collections:
        raise AggregationError(
            f"manifesto tem {len(manifest_rows)} colecoes; esperado: {expected_collections}"
        )

    complete_count = 0
    timing_count = 0
    expected_images: Optional[Set[str]] = None
    for manifest in manifest_rows:
        collection_dir = run_dir / "collections" / manifest["Collection_ID"]
        if not is_complete(collection_dir):
            if require_complete:
                raise AggregationError(f"colecao incompleta: {manifest['Collection_ID']}")
            continue
        complete_count += 1
        images, rows = validate_timing_file(collection_dir / "timings.csv", manifest)
        timing_count += rows
        if expected_images is None:
            expected_images = images
        elif images != expected_images:
            raise AggregationError(
                f"conjunto de imagens divergente: {manifest['Collection_ID']}"
            )
        summary_metrics(collection_dir / "reports" / "summary.csv")
        for filename, (_, _, tokens) in REQUIRED_REPORTS.items():
            report_path = collection_dir / "reports" / filename
            _, data_rows = prepare_report_table(report_path, tokens)
            if not any(any(cell for cell in row) for row in data_rows):
                raise AggregationError(f"relatorio VTune sem dados: {report_path}")

    return complete_count, len(expected_images or set()), timing_count


def write_master_table(
    run_dir: Path,
    manifest_rows: Sequence[Mapping[str, str]],
    include_incomplete: bool,
) -> Path:
    dynamic_fields: Set[str] = set()
    for record in all_records(run_dir, manifest_rows, include_incomplete):
        dynamic_fields.update(set(record) - set(COMMON_FIELDS))
    fieldnames = COMMON_FIELDS + sorted(dynamic_fields)

    output = run_dir / "benchmark_transformacoes_vtune.csv"
    temporary = output.with_suffix(".csv.tmp")
    with temporary.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for record in all_records(run_dir, manifest_rows, include_incomplete):
            writer.writerow(record)
    os.replace(temporary, output)
    return output


def parse_arguments(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--require-complete", action="store_true")
    parser.add_argument("--expected-collections", type=int)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_arguments(argv or sys.argv[1:])
    run_dir = arguments.run_dir.resolve()
    try:
        manifest = read_manifest(run_dir)
        complete, images, timings = validate_campaign(
            run_dir,
            manifest,
            arguments.expected_collections,
            arguments.require_complete,
        )
        output = write_master_table(run_dir, manifest, include_incomplete=True)
    except (AggregationError, OSError, csv.Error) as error:
        print(f"Erro: {error}", file=sys.stderr)
        return 1

    print(
        f"Tabela: {output}\n"
        f"Colecoes completas: {complete}/{len(manifest)} | "
        f"Imagens: {images} | Linhas de tempo: {timings}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
