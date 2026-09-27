#!/usr/bin/env python3
"""Valida e resume a campanha mínima de redução SIMD nos 11 taps internos."""

import csv
import statistics
import sys
from collections import defaultdict
from pathlib import Path


def main():
    if len(sys.argv) != 4:
        raise SystemExit("Uso: python3 summarize_inner_simd_convolution.py RAW.csv SUMMARY.csv REPETICOES")
    source, destination = map(Path, sys.argv[1:3])
    repetitions = int(sys.argv[3])
    groups = defaultdict(dict)
    with source.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            if row["Phase"] != "kernel":
                continue  # 'total' duplica exatamente o kernel nesta variante.
            if row["Variant"] != "float_tap_reduction" or row["Schedule"] != "static":
                raise ValueError(f"Linha inesperada: {row}")
            if row["Build"] not in ("auto-avx2", "omp-avx2"):
                raise ValueError(f"Build inesperado: {row['Build']}")
            if int(row["Max_Abs_Error"]) > 1:
                raise ValueError(f"Divergência maior que um nível de cor: {row}")
            key = (row["Threads"], row["Build"])
            repeat = int(row["Repeat"])
            if repeat in groups[key]:
                raise ValueError(f"Repetição duplicada: {key}, {repeat}")
            groups[key][repeat] = row

    if not groups:
        raise ValueError("Nenhuma medição encontrada")
    threads_seen = {threads for threads, _ in groups}
    expected_repeats = set(range(1, repetitions + 1))
    summaries = {}
    for threads in sorted(threads_seen, key=int):
        for build in ("auto-avx2", "omp-avx2"):
            samples = groups.get((threads, build), {})
            if set(samples) != expected_repeats:
                raise ValueError(f"Amostras incompletas: {threads} threads, {build}: {sorted(samples)}")
            rows = list(samples.values())
            identity = {(r["Image"], r["Width"], r["Height"], r["Compiler"], r["Flags"]) for r in rows}
            if len(identity) != 1:
                raise ValueError(f"Configuração mudou entre amostras: {threads}, {build}")
            hashes = {r["Hash"] for r in rows}
            reference_hashes = {r["Reference_Hash"] for r in rows}
            if len(hashes) != 1 or len(reference_hashes) != 1:
                raise ValueError(f"Saída não determinística: {threads}, {build}")
            elapsed = [float(r["Elapsed_ms"]) for r in rows]
            summaries[(threads, build)] = {
                "median": statistics.median(elapsed),
                "min": min(elapsed),
                "max": max(elapsed),
                "different": statistics.median(int(r["Differing_Bytes"]) for r in rows),
                "max_error": max(int(r["Max_Abs_Error"]) for r in rows),
                "exact": all(r["Exact"].lower() in ("true", "1", "yes") for r in rows),
                "hashes": ";".join(sorted(hashes)),
                "reference_hash": next(iter(reference_hashes)),
                "image": rows[0]["Image"],
            }

    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(("Image", "Threads", "Repetitions", "Auto_Median_ms", "Auto_Min_ms",
                         "Auto_Max_ms", "OMP_Median_ms", "OMP_Min_ms", "OMP_Max_ms",
                         "Auto_over_OMP", "Auto_Differing_Bytes_Median", "OMP_Differing_Bytes_Median",
                         "Auto_Max_Abs_Error", "OMP_Max_Abs_Error", "Auto_Exact", "OMP_Exact",
                         "Auto_Hashes", "OMP_Hashes"))
        for threads in sorted(threads_seen, key=int):
            auto = summaries[(threads, "auto-avx2")]
            omp = summaries[(threads, "omp-avx2")]
            if auto["image"] != omp["image"] or auto["reference_hash"] != omp["reference_hash"]:
                raise ValueError(f"Referências diferentes entre builds: {threads}")
            writer.writerow((auto["image"], threads, repetitions,
                             f"{auto['median']:.6f}", f"{auto['min']:.6f}", f"{auto['max']:.6f}",
                             f"{omp['median']:.6f}", f"{omp['min']:.6f}", f"{omp['max']:.6f}",
                             f"{auto['median'] / omp['median']:.6f}", auto["different"],
                             omp["different"], auto["max_error"], omp["max_error"],
                             auto["exact"], omp["exact"], auto["hashes"], omp["hashes"]))
    print(f"Resumo validado: {destination}")


if __name__ == "__main__":
    main()
