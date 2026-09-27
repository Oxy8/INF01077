#!/usr/bin/env python3
"""Export per-thread VTune placement and work data for an entire campaign.

The script runs resumable VTune ``hotspots`` reports for every collection in a
campaign manifest and combines them into one long-form CSV.  The views cover
logical CPUs, physical cores, packages, package/core totals, and functions by
thread.  By default only rows inside the transformation ITT frame are retained.

Usage on the cluster, after loading the VTune environment::

    python3 extract_thread_placement.py runs/<campaign-id>

The raw VTune ``result/`` directories must still exist.  Intermediate reports
are cached under ``<run>/thread_placement_reports`` so an interrupted export can
be resumed without regenerating reports that already succeeded.
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Mapping, Sequence, Tuple


BASE_FIELDS = [
    "Record_Type",
    "Report_Type",
    "Group_By",
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
    "Workload_Iterations",
    "Affinity_Label",
    "OMP_PLACES",
    "OMP_PROC_BIND",
    "GOMP_CPU_AFFINITY",
    "Frame_Domain",
    "Inside_Transformation",
    "Thread",
    "Thread_ID",
    "Logical_Core",
    "Logical_CPU_ID",
    "Physical_Core",
    "Physical_Core_ID",
    "Package",
    "Package_ID",
    "Function",
    "Function_Full",
    "Module",
    "Source_File",
    "Start_Address",
    "Result_Dir",
    "Source_Report",
    "Status",
    "Error",
]

REPORT_DIMENSIONS = {
    "Frame Domain",
    "Thread",
    "Logical Core",
    "Physical Core",
    "Package",
    "Function",
    "Function (Full)",
    "Module",
    "Source File",
    "Start Address",
}


@dataclass(frozen=True)
class ReportSpec:
    name: str
    report_type: str
    group_by: str
    required_columns: Tuple[str, ...]


PLACEMENT_REPORTS = (
    ReportSpec(
        "thread_cpu",
        "hotspots",
        "frame-domain,thread,cpuid",
        ("Frame Domain", "Thread", "Logical Core"),
    ),
    ReportSpec(
        "thread_core",
        "hotspots",
        "frame-domain,thread,core",
        ("Frame Domain", "Thread", "Physical Core"),
    ),
    ReportSpec(
        "thread_package",
        "hotspots",
        "frame-domain,thread,package",
        ("Frame Domain", "Thread", "Package"),
    ),
    ReportSpec(
        "package_core",
        "hotspots",
        "frame-domain,package,core",
        ("Frame Domain", "Package", "Physical Core"),
    ),
)

THREAD_FUNCTION_REPORT = ReportSpec(
    "thread_function",
    "hotspots",
    "frame-domain,thread,function",
    ("Frame Domain", "Thread", "Function"),
)


class ExportError(RuntimeError):
    pass


def parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "run_dir",
        type=Path,
        help="campaign directory containing manifest.csv and collections/",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="output CSV (default: <run>/vtune_thread_placement.csv)",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        help="report cache (default: <run>/thread_placement_reports)",
    )
    parser.add_argument(
        "--vtune",
        help="VTune CLI executable (default: command found in PATH)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="regenerate cached VTune reports",
    )
    parser.add_argument(
        "--skip-thread-functions",
        action="store_true",
        help="omit the larger thread/function report",
    )
    parser.add_argument(
        "--include-outside-frames",
        action="store_true",
        help="also retain loading, reset, cleanup, and other outside-frame rows",
    )
    parser.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="return success after writing error rows for missing or failed collections",
    )
    return parser.parse_args(argv)


def read_manifest(run_dir: Path) -> List[Dict[str, str]]:
    path = run_dir / "manifest.csv"
    if not path.is_file():
        raise ExportError(f"manifest not found: {path}")
    with path.open(newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise ExportError(f"empty manifest: {path}")
    identifiers = [row.get("Collection_ID", "").strip() for row in rows]
    if "" in identifiers or len(identifiers) != len(set(identifiers)):
        raise ExportError("manifest contains an empty or duplicate Collection_ID")
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


def sanitize_column(value: str) -> str:
    value = value.strip().replace("%", " Percent ")
    return re.sub(r"[^0-9A-Za-z]+", "_", value).strip("_") or "Value"


def numeric_suffix(value: str) -> str:
    match = re.search(r"(-?\d+)$", value.strip())
    return match.group(1) if match else ""


def thread_id(value: str) -> str:
    match = re.search(r"TID:\s*(\d+)", value)
    return match.group(1) if match else ""


def report_header(path: Path) -> List[str]:
    with path.open(newline="", encoding="utf-8-sig", errors="replace") as stream:
        reader = csv.reader(stream)
        try:
            return [column.strip() for column in next(reader)]
        except StopIteration as error:
            raise ExportError(f"empty VTune report: {path}") from error


def validate_report(path: Path, spec: ReportSpec) -> List[str]:
    if not path.is_file() or path.stat().st_size == 0:
        raise ExportError(f"missing or empty VTune report: {path}")
    header = report_header(path)
    missing = sorted(set(spec.required_columns) - set(header))
    if missing:
        raise ExportError(
            f"report {path} lacks required columns: {', '.join(missing)}"
        )
    with path.open(newline="", encoding="utf-8-sig", errors="replace") as stream:
        reader = csv.DictReader(stream)
        if not any(any((value or "").strip() for value in row.values()) for row in reader):
            raise ExportError(f"VTune report has no data rows: {path}")
    return header


def generate_report(
    vtune: str,
    result_dir: Path,
    output: Path,
    spec: ReportSpec,
    force: bool,
) -> List[str]:
    if not force:
        try:
            return validate_report(output, spec)
        except ExportError:
            pass

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.stem}.tmp.csv")
    log_path = output.with_suffix(".log")
    temporary.unlink(missing_ok=True)
    command = [
        vtune,
        "-report",
        spec.report_type,
        "-r",
        str(result_dir),
        "-group-by",
        spec.group_by,
        "-format",
        "csv",
        "-csv-delimiter",
        "comma",
        "-report-output",
        str(temporary),
    ]
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.run(
            command,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
    if process.returncode != 0:
        temporary.unlink(missing_ok=True)
        raise ExportError(
            f"VTune report failed ({spec.name}, exit {process.returncode}); "
            f"see {log_path}"
        )
    try:
        header = validate_report(temporary, spec)
    except ExportError:
        temporary.unlink(missing_ok=True)
        raise
    os.replace(temporary, output)
    return header


def build_metric_columns(headers: Iterable[str]) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    occupied: Dict[str, str] = {}
    for header in headers:
        if header in REPORT_DIMENSIONS or header in mapping:
            continue
        base = f"VTune__{sanitize_column(header)}"
        column = base
        suffix = 2
        while column in occupied and occupied[column] != header:
            column = f"{base}_{suffix}"
            suffix += 1
        mapping[header] = column
        occupied[column] = header
    return mapping


def report_rows(path: Path) -> Iterator[Dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig", errors="replace") as stream:
        yield from csv.DictReader(stream)


def relative_or_absolute(path: Path, base: Path) -> str:
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)


def common_record(
    run_dir: Path,
    manifest: Mapping[str, str],
    metadata: Mapping[str, str],
) -> Dict[str, str]:
    collection_id = manifest["Collection_ID"]
    result_dir = run_dir / "collections" / collection_id / "result"
    record = {field: "" for field in BASE_FIELDS}
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
    ):
        record[field] = metadata.get(field, "")
    record["Result_Dir"] = relative_or_absolute(result_dir, run_dir)
    return record


def populated_record(
    base: Mapping[str, str],
    spec: ReportSpec,
    source_report: Path,
    row: Mapping[str, str],
    metric_columns: Mapping[str, str],
    inside: bool,
) -> Dict[str, str]:
    record = dict(base)
    record.update(
        {
            "Record_Type": spec.name,
            "Report_Type": spec.report_type,
            "Group_By": spec.group_by,
            "Frame_Domain": row.get("Frame Domain", ""),
            "Inside_Transformation": "1" if inside else "0",
            "Thread": row.get("Thread", ""),
            "Thread_ID": thread_id(row.get("Thread", "")),
            "Logical_Core": row.get("Logical Core", ""),
            "Logical_CPU_ID": numeric_suffix(row.get("Logical Core", "")),
            "Physical_Core": row.get("Physical Core", ""),
            "Physical_Core_ID": numeric_suffix(row.get("Physical Core", "")),
            "Package": row.get("Package", ""),
            "Package_ID": numeric_suffix(row.get("Package", "")),
            "Function": row.get("Function", ""),
            "Function_Full": row.get("Function (Full)", ""),
            "Module": row.get("Module", ""),
            "Source_File": row.get("Source File", ""),
            "Start_Address": row.get("Start Address", ""),
            "Source_Report": str(source_report),
            "Status": "complete",
        }
    )
    for source, destination in metric_columns.items():
        record[destination] = row.get(source, "")
    return record


def error_record(
    base: Mapping[str, str],
    message: str,
) -> Dict[str, str]:
    record = dict(base)
    record.update(
        {
            "Record_Type": "error",
            "Status": "failed",
            "Error": message,
        }
    )
    return record


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_arguments(argv)
    run_dir = arguments.run_dir.expanduser().resolve()
    output = (
        arguments.output.expanduser().resolve()
        if arguments.output
        else run_dir / "vtune_thread_placement.csv"
    )
    cache_dir = (
        arguments.cache_dir.expanduser().resolve()
        if arguments.cache_dir
        else run_dir / "thread_placement_reports"
    )
    vtune = arguments.vtune or shutil.which("vtune")
    if not vtune:
        print(
            "Error: vtune was not found. Source vtune-vars.sh before running this script.",
            file=sys.stderr,
        )
        return 2

    try:
        manifest_rows = read_manifest(run_dir)
    except (ExportError, OSError, csv.Error) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2

    specs: Tuple[ReportSpec, ...] = PLACEMENT_REPORTS
    if not arguments.skip_thread_functions:
        specs += (THREAD_FUNCTION_REPORT,)

    cache_dir.mkdir(parents=True, exist_ok=True)
    campaign_metadata = read_key_values(run_dir / "campaign.env")
    metadata_by_collection: Dict[str, Dict[str, str]] = {}
    reports_by_collection: Dict[str, Dict[str, Path]] = {}
    headers: List[str] = []
    failures: Dict[str, str] = {}

    total = len(manifest_rows)
    for index, manifest in enumerate(manifest_rows, start=1):
        collection_id = manifest["Collection_ID"]
        collection_dir = run_dir / "collections" / collection_id
        result_dir = collection_dir / "result"
        metadata = dict(campaign_metadata)
        metadata.update(read_key_values(collection_dir / "metadata.env"))
        metadata_by_collection[collection_id] = metadata
        print(f"[{index}/{total}] {collection_id}", flush=True)
        if not result_dir.is_dir():
            failures[collection_id] = f"raw VTune result directory not found: {result_dir}"
            continue

        collection_reports: Dict[str, Path] = {}
        try:
            for spec in specs:
                report_path = cache_dir / collection_id / f"{spec.name}.csv"
                header = generate_report(
                    vtune, result_dir, report_path, spec, arguments.force
                )
                headers.extend(header)
                collection_reports[spec.name] = report_path
        except (ExportError, OSError) as error:
            failures[collection_id] = str(error)
            continue
        reports_by_collection[collection_id] = collection_reports

    metric_columns = build_metric_columns(headers)
    fieldnames = BASE_FIELDS + sorted(set(metric_columns.values()))
    temporary = output.with_name(f".{output.name}.tmp")
    output.parent.mkdir(parents=True, exist_ok=True)
    row_count = 0
    successful_collections = 0

    try:
        with temporary.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for manifest in manifest_rows:
                collection_id = manifest["Collection_ID"]
                metadata = metadata_by_collection.get(collection_id, {})
                base = common_record(run_dir, manifest, metadata)
                if collection_id in failures:
                    writer.writerow(error_record(base, failures[collection_id]))
                    row_count += 1
                    continue

                expected_frame = f"inf01077.transform.{manifest['Transformation']}"
                collection_rows = 0
                for spec in specs:
                    report_path = reports_by_collection[collection_id][spec.name]
                    relative_report = Path(relative_or_absolute(report_path, run_dir))
                    for row in report_rows(report_path):
                        frame_domain = (row.get("Frame Domain") or "").strip()
                        inside = frame_domain == expected_frame
                        if not arguments.include_outside_frames and not inside:
                            continue
                        writer.writerow(
                            populated_record(
                                base,
                                spec,
                                relative_report,
                                row,
                                metric_columns,
                                inside,
                            )
                        )
                        row_count += 1
                        collection_rows += 1
                if collection_rows == 0:
                    message = f"no rows found for transformation frame {expected_frame}"
                    failures[collection_id] = message
                    writer.writerow(error_record(base, message))
                    row_count += 1
                else:
                    successful_collections += 1
        os.replace(temporary, output)
    except (OSError, csv.Error, KeyError) as error:
        temporary.unlink(missing_ok=True)
        print(f"Error while writing output: {error}", file=sys.stderr)
        return 2

    print(f"Output: {output}")
    print(f"Rows: {row_count}")
    print(f"Complete collections: {successful_collections}/{total}")
    if failures:
        print(f"Failed collections: {len(failures)}", file=sys.stderr)
        for collection_id, message in sorted(failures.items()):
            print(f"- {collection_id}: {message}", file=sys.stderr)
        if not arguments.allow_incomplete:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
