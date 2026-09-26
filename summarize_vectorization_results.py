#!/usr/bin/env python3
"""Resume o CSV bruto sem somar fases nem confundir algoritmo com SIMD."""
import argparse
import csv
import statistics
from collections import defaultdict
from pathlib import Path

FIELDS = ("Image", "Operation", "Variant", "Phase", "Width", "Height", "Threads", "Schedule", "Build")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    groups = defaultdict(list)
    with args.raw.open(newline="", encoding="utf-8") as source:
        for row in csv.DictReader(source):
            if row["Exact"] != "yes" and row["Variant"] != "production_float":
                raise SystemExit(f"Saída divergente: {row['Image']} {row['Operation']} {row['Variant']}")
            key = tuple(row[field] for field in FIELDS)
            groups[key].append(row)

    medians = {key: statistics.median(float(row["Elapsed_ms"]) for row in rows)
               for key, rows in groups.items()}
    result_rows = []
    for key, rows in sorted(groups.items()):
        fields = dict(zip(FIELDS, key))
        times = [float(row["Elapsed_ms"]) for row in rows]
        median = medians[key]
        common = tuple(fields[field] for field in FIELDS[:4] + FIELDS[4:8])
        def other_build(build):
            return medians.get(common + (build,))

        reference_variant = "aos_direct" if fields["Operation"].startswith("Gaussian_") else "original"
        reference_key = (fields["Image"], fields["Operation"], reference_variant, "total",
                         fields["Width"], fields["Height"], fields["Threads"], fields["Schedule"], fields["Build"])
        reference = medians.get(reference_key) if fields["Phase"] == "total" else None
        result_rows.append({
            **fields,
            "Samples": len(times),
            "Median_ms": f"{median:.6f}",
            "Min_ms": f"{min(times):.6f}",
            "Max_ms": f"{max(times):.6f}",
            "Scalar_to_Auto": f"{other_build('off-avx2') / median:.6f}"
                if fields["Build"] == "auto-avx2" and other_build("off-avx2") else "",
            "Auto_to_Omp": f"{other_build('auto-avx2') / median:.6f}"
                if fields["Build"] == "omp-avx2" and other_build("auto-avx2") else "",
            "Original_to_Variant": f"{reference / median:.6f}"
                if reference and fields["Variant"] != reference_variant else "",
            "All_Exact": "yes" if all(row["Exact"] == "yes" for row in rows) else "no",
            "Max_Abs_Error": max(int(row["Max_Abs_Error"]) for row in rows),
        })

    args.out.parent.mkdir(parents=True, exist_ok=True)
    if not result_rows:
        raise SystemExit("CSV sem amostras")
    with args.out.open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(target, fieldnames=result_rows[0].keys())
        writer.writeheader()
        writer.writerows(result_rows)
    print(f"Resumo: {args.out} ({len(result_rows)} combinações)")


if __name__ == "__main__":
    main()
