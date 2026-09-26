#!/usr/bin/env python3
"""Consolida os experimentos finais de confirmação executados no PCAD/Hype.

Uso:
    python plot_experimentos_finais.py
"""

from __future__ import annotations

import argparse
import csv
import html
import math
import re
import statistics
from collections import defaultdict
from pathlib import Path

from plot_resultados_pcad import bar_chart, line_chart, safe_ratio, write_csv


ROOT = Path(__file__).resolve().parent
SUMMARY_PATTERNS = {
    "Elapsed_s": r"^\s*Elapsed Time: ([0-9.]+)s$",
    "CPU_s": r"^\s*CPU Time: ([0-9.]+)s$",
    "CPI": r"^\s*CPI Rate: ([0-9.]+)$",
    "Physical_Cores": r"\s*Effective Physical Core Utilization: ([0-9.]+)% \(([0-9.]+) out of 20\)",
    "Memory_Bound_pct": r"^\s*Memory Bound: ([0-9.]+)%",
    "Cache_Bound_pct": r"^\s*Cache Bound: ([0-9.]+)%",
    "DRAM_Bound_pct": r"^\s*DRAM Bandwidth Bound: ([0-9.]+)%",
    "NUMA_Remote_pct": r"^\s*NUMA: % of Remote Accesses: ([0-9.]+)%",
}


def median(values: list[float]) -> float:
    return statistics.median(values) if values else math.nan


def parse_summary(path: Path) -> dict[str, float]:
    text = path.read_text(encoding="utf-8", errors="replace")
    output: dict[str, float] = {}
    for key, pattern in SUMMARY_PATTERNS.items():
        match = re.search(pattern, text, re.MULTILINE)
        if match:
            output[key] = float(match.group(1))
            if key == "Physical_Cores":
                output["Physical_Cores_Used"] = float(match.group(2))
    return output


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as source:
        return list(csv.DictReader(source))


def esc(value: object) -> str:
    return html.escape(str(value))


def page(output: Path, figures: list[tuple[str, str]], tables: list[tuple[str, str]]) -> None:
    cards = "\n".join(
        f'<article><a href="figures/{esc(name)}"><img src="figures/{esc(name)}" alt="{esc(caption)}"></a><p>{esc(caption)}</p></article>'
        for name, caption in figures
    )
    links = "\n".join(f'<li><a href="tables/{esc(name)}">{esc(caption)}</a></li>' for name, caption in tables)
    (output / "index.html").write_text(f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><title>Experimentos finais — PCAD Hype</title>
<style>body{{font-family:Arial,sans-serif;margin:32px;max-width:1420px;color:#202124;background:#fafafa}}.note{{max-width:1100px;line-height:1.45;color:#555}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(420px,1fr));gap:22px}}article{{background:#fff;border:1px solid #ddd;border-radius:8px;padding:12px}}img{{width:100%;height:auto}}p{{line-height:1.35;margin:8px 3px 2px}}code{{background:#eee;padding:2px 4px}}</style>
</head><body><h1>Experimentos finais de confirmação</h1>
<p class="note">Esta página cruza cinco campanhas: HPC Performance para os layouts Gaussianos, duas alocações independentes para Flip/topologia, Hotspots para Zoom/schedules e a campanha de cinco repetições para tamanhos Gaussianos. <strong>Percentuais HPC são diagnósticos do trecho coletado, não tempos de benchmark.</strong> Tempos de Gaussianos são medianas de cinco repetições sem VTune; Flip/topologia tem duas réplicas independentes de uma execução-controlada cada.</p>
<p class="note">No Flip, a mudança de sinal em 20 threads é o dado-chave: com preparação paralela em blocos static, static supera dynamic,1; com preparação serial, o oposto ocorre. Em 10 threads, dynamic permanece mais rápido, logo primeiro toque/topologia explica parte importante, mas não toda, a assimetria observada.</p>
<div class="grid">{cards}</div><h2>Tabelas de apoio</h2><ul>{links}</ul></body></html>""", encoding="utf-8")


def hotspot_times(path: Path) -> dict[str, float]:
    phases = {"Copy": "zoom_copy_source_pixels", "Horizontal": "zoom_interpolate_horizontal", "Vertical": "zoom_interpolate_vertical"}
    result: dict[str, float] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        for phase, token in phases.items():
            if token in line:
                match = re.search(r"\s([0-9.]+)s\s+", line)
                if match and phase not in result:
                    result[phase] = float(match.group(1))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--layout", default="resultados_pcad_hype_hpc_layout_gaussian_824167")
    parser.add_argument("--flip", action="append", default=["resultados_pcad_hype_hpc_flip_topology_824168", "resultados_pcad_hype_hpc_flip_topology_824169"])
    parser.add_argument("--zoom", default="resultados_pcad_hype_vtune_zoom_schedules_823586")
    parser.add_argument("--sizes", default="resultados_pcad_hype_gaussian_separavel_tamanhos_824170")
    parser.add_argument("--out", default="visualizacoes_pcad_hype_experimentos_finais_824167_824168_824169_824170")
    args = parser.parse_args()
    layout_root, zoom_root, sizes_root = (ROOT / args.layout, ROOT / args.zoom, ROOT / args.sizes)
    flip_roots = [ROOT / item for item in args.flip]
    output = ROOT / args.out
    figures_dir, tables_dir = output / "figures", output / "tables"
    figures_dir.mkdir(parents=True, exist_ok=True)
    tables_dir.mkdir(parents=True, exist_ok=True)
    figures: list[tuple[str, str]] = []
    tables: list[tuple[str, str]] = []

    # VTune usa quantidades diferentes de iterações conforme o layout; compare
    # somente as métricas normalizadas, não o tempo wall da coleta.
    layout_rows: list[dict[str, object]] = []
    for directory in sorted(layout_root.glob("[0-9][0-9]_*")):
        config = dict(line.strip().split("=", 1) for line in (directory / "configuration.txt").read_text().splitlines() if "=" in line)
        row: dict[str, object] = {"Build": config["build"], "Layout": config["layout"], "Profile_Iterations": int(config["profile_iterations"])}
        row.update(parse_summary(directory / "summary.txt"))
        layout_rows.append(row)
    columns = ["Build", "Layout", "Profile_Iterations", "Elapsed_s", "CPI", "Physical_Cores", "Physical_Cores_Used", "Memory_Bound_pct", "Cache_Bound_pct", "DRAM_Bound_pct", "NUMA_Remote_pct"]
    write_csv(tables_dir / "gaussian_layout_hpc.csv", columns, layout_rows)
    tables.append(("gaussian_layout_hpc.csv", "Gaussian 11×11: métricas normalizadas HPC por layout e build"))
    order = [("off-avx2", "aos"), ("off-avx2", "soa-naive"), ("off-avx2", "soa-separable"), ("omp-avx2", "aos"), ("omp-avx2", "soa-naive"), ("omp-avx2", "soa-separable")]
    lookup = {(str(r["Build"]), str(r["Layout"])): r for r in layout_rows}
    labels = [f"{'AVX2' if build == 'omp-avx2' else 'sem AVX2'} {layout}" for build, layout in order]
    line_chart(figures_dir / "01_gaussian_hpc_memoria.svg", "Gaussian 11×11: pressão de memória/cache no VTune HPC", labels, [
        ("Memory Bound (% slots)", [float(lookup[key].get("Memory_Bound_pct", math.nan)) for key in order], "#d62728", None),
        ("Cache Bound (% clocks)", [float(lookup[key].get("Cache_Bound_pct", math.nan)) for key in order], "#ff7f0e", None),
        ("DRAM bound (% tempo)", [float(lookup[key].get("DRAM_Bound_pct", math.nan)) for key in order], "#1f77b4", None),
    ], "Percentual (%)", y_zero=True, x_label="Build e layout")
    figures.append(("01_gaussian_hpc_memoria.svg", "Gaussian: SoA ingênuo + AVX2 tem pressão de memória/cache maior; o separável fica limitado por DRAM após remover trabalho aritmético."))

    # Cinco repetições sem profiler: a mediana é a medida de tempo principal.
    size_rows = read_csv(sizes_root / "gaussian_sizes_summary.csv")
    normalized_sizes: list[dict[str, object]] = []
    by_key: dict[tuple[int, int, str, str], dict[str, float]] = {}
    for row in size_rows:
        key = (int(row["Taps"]), int(row["Threads"]), row["Build"], row["Component"])
        by_key[key] = {name: float(row[name]) for name in ("Median_ms", "Min_ms", "Max_ms", "Mean_ms", "StdDev_ms")}
        normalized_sizes.append({name: (int(row[name]) if name in ("Taps", "Threads", "Samples") else float(row[name]) if name.endswith("_ms") else row[name]) for name in row})
    write_csv(tables_dir / "gaussian_tamanhos_mediana.csv", list(normalized_sizes[0]), normalized_sizes)
    tables.append(("gaussian_tamanhos_mediana.csv", "Gaussian 3–11 taps: cinco amostras, mediana, mínimo–máximo e desvio"))
    taps = [3, 5, 7, 9, 11]
    for threads in (1, 20):
        series = []
        for build, direct_color, sep_color, label in (("off-avx2", "#555555", "#2ca02c", "sem AVX2"), ("omp-avx2", "#8a2be2", "#17becf", "AVX2")):
            series.append((f"AoS direto — {label}", [by_key[(tap, threads, build, "AoS_Direct")]["Median_ms"] for tap in taps], direct_color, None))
            series.append((f"SoA separável — {label}", [by_key[(tap, threads, build, "SoA_Separable_Kernel")]["Median_ms"] for tap in taps], sep_color, None))
        name = f"02_gaussian_tamanhos_{threads}t.svg"
        line_chart(figures_dir / name, f"Gaussian: custo direto versus separável — {threads} thread{'s' if threads > 1 else ''}", [str(tap) for tap in taps], series, "Tempo do kernel (ms)", y_zero=True, x_label="Taps por dimensão")
        figures.append((name, f"Gaussian 3×3 a 11×11, {threads} thread(s): mudança algorítmica e AVX2."))
    speed_rows: list[dict[str, object]] = []
    speed_series = []
    for threads, scalar_color, avx_color in ((1, "#1f77b4", "#9467bd"), (20, "#d62728", "#ff7f0e")):
        for build, color, label in (("off-avx2", scalar_color, "sem AVX2"), ("omp-avx2", avx_color, "AVX2")):
            ratios = [safe_ratio(by_key[(tap, threads, build, "AoS_Direct")]["Median_ms"], by_key[(tap, threads, build, "SoA_Separable_Kernel")]["Median_ms"]) for tap in taps]
            speed_series.append((f"{threads}t — {label}", ratios, color, None))
            speed_rows.extend({"Taps": tap, "Threads": threads, "Build": build, "AoS_Direct_div_Separable": ratio} for tap, ratio in zip(taps, ratios))
    write_csv(tables_dir / "gaussian_speedup_separavel.csv", ["Taps", "Threads", "Build", "AoS_Direct_div_Separable"], speed_rows)
    tables.append(("gaussian_speedup_separavel.csv", "Gaussian: speedup AoS direto / SoA separável por tamanho"))
    line_chart(figures_dir / "03_gaussian_speedup_separavel.svg", "Gaussian: speedup algorítmico do SoA separável", [str(tap) for tap in taps], speed_series, "Speedup (×)", reference=("empate", 1.0, "#555555"), x_label="Taps por dimensão")
    figures.append(("03_gaussian_speedup_separavel.svg", "Razão AoS direto / SoA separável: este é ganho algorítmico, não ganho de AVX2. O separável usa 2N, em vez de N², contribuições."))

    avx_rows: list[dict[str, object]] = []
    avx_series = []
    for threads, direct_color, separable_color in ((1, "#8a2be2", "#17becf"), (20, "#d62728", "#ff7f0e")):
        for component, color, label in (("AoS_Direct", direct_color, "AoS direto"), ("SoA_Separable_Kernel", separable_color, "SoA separável")):
            ratios = [safe_ratio(by_key[(tap, threads, "off-avx2", component)]["Median_ms"], by_key[(tap, threads, "omp-avx2", component)]["Median_ms"]) for tap in taps]
            avx_series.append((f"{threads}t — {label}", ratios, color, None))
            avx_rows.extend({"Taps": tap, "Threads": threads, "Kernel": label, "Off_AVX2_div_OMP_AVX2": ratio} for tap, ratio in zip(taps, ratios))
    write_csv(tables_dir / "gaussian_efeito_avx2.csv", ["Taps", "Threads", "Kernel", "Off_AVX2_div_OMP_AVX2"], avx_rows)
    tables.append(("gaussian_efeito_avx2.csv", "Gaussian: efeito isolado de AVX2 dentro do mesmo algoritmo"))
    line_chart(figures_dir / "03b_gaussian_efeito_avx2.svg", "Gaussian genérica: efeito isolado de AVX2", [str(tap) for tap in taps], avx_series, "Speedup (off-avx2 / omp-avx2)", reference=("empate", 1.0, "#555555"), x_label="Taps por dimensão")
    figures.append(("03b_gaussian_efeito_avx2.svg", "AVX2 isolado dentro do mesmo kernel. Valores próximos de 1× significam que AVX2 quase não alterou o tempo; não confundir com a razão AoS/separável."))

    # As duas alocações do Flip são réplicas independentes.
    flip_controls: dict[str, list[dict[str, object]]] = defaultdict(list)
    for root in flip_roots:
        for case in sorted(root.glob("[0-9][0-9]_*")):
            rows = read_csv(case / "threads.csv")
            first = rows[0]
            # Nomes como 00_t20_static_serial incluem o número de threads.
            # Preservá-lo evita misturar os controles de 10t e 20t e gerar NaN.
            key = case.name.split("_", 1)[1]
            works = [float(row["Work_ms"]) for row in rows]
            row_counts = [int(row["Rows"]) for row in rows]
            flip_controls[key].append({"Job": root.name.rsplit("_", 1)[-1], "Case": key, "Threads": len(rows), "Init": first["Init_Mode"], "Schedule": "dynamic,1" if "dynamic" in key else "static", "Control_ms": float(first["Control_ms"]), "Work_Mean_ms": statistics.fmean(works), "Work_CV_pct": statistics.pstdev(works) / statistics.fmean(works) * 100, "Rows_Min": min(row_counts), "Rows_Max": max(row_counts), "First_Half_Work_ms": statistics.fmean(works[:len(works)//2]), "Second_Half_Work_ms": statistics.fmean(works[len(works)//2:])})
    all_flip = [row for rows in flip_controls.values() for row in rows]
    write_csv(tables_dir / "flip_topologia_replicas.csv", list(all_flip[0]), all_flip)
    tables.append(("flip_topologia_replicas.csv", "Flip: controles por thread das duas alocações independentes"))
    def control(case: str) -> float:
        return median([float(row["Control_ms"]) for row in flip_controls[case]])

    def cv(case: str) -> float:
        return median([float(row["Work_CV_pct"]) for row in flip_controls[case]])

    touch_labels = ["20 threads / init serial", "20 threads / init paralelo-static"]
    touch_ratios = [
        safe_ratio(control("t20_static_serial"), control("t20_dynamic_1_serial")),
        safe_ratio(control("t20_static_parallel-static"), control("t20_dynamic_1_parallel-static")),
    ]
    bar_chart(figures_dir / "04_flip_primeiro_toque_20t.svg", "Flip, 20 threads: o primeiro toque inverte o resultado", touch_labels, [("static / dynamic,1", touch_ratios, "#1f77b4")], "Speedup static / dynamic,1", baseline=1.0)
    figures.append(("04_flip_primeiro_toque_20t.svg", "Razão de tempos: acima de 1× favorece dynamic,1; abaixo de 1× favorece static. Agora o gráfico evidencia a inversão causada pelo primeiro toque."))

    imbalance_labels = ["10 threads / init paralelo-static", "20 threads / init serial", "20 threads / init paralelo-static"]
    static_cv = [cv("t10_static_parallel-static"), cv("t20_static_serial"), cv("t20_static_parallel-static")]
    dynamic_cv = [cv("t10_dynamic_1_parallel-static"), cv("t20_dynamic_1_serial"), cv("t20_dynamic_1_parallel-static")]
    bar_chart(figures_dir / "05_flip_desequilibrio_temporal.svg", "Flip: dispersão do tempo de trabalho entre threads", imbalance_labels, [("static", static_cv, "#1f77b4"), ("dynamic,1", dynamic_cv, "#d62728")], "CV do tempo de trabalho por thread (%)", baseline=0.0)
    figures.append(("05_flip_desequilibrio_temporal.svg", "Coeficiente de variação do tempo de trabalho por thread, em porcentagem. Valores menores significam término mais uniforme; não representam ganho de velocidade."))

    hpc_flip: list[dict[str, object]] = []
    for root in flip_roots:
        for case in sorted(root.glob("[0-9][0-9]_*")):
            config = dict(line.strip().split("=", 1) for line in (case / "configuration.txt").read_text().splitlines() if "=" in line)
            row: dict[str, object] = {"Job": root.name.rsplit("_", 1)[-1], "Case": case.name, "Threads": int(config["threads"]), "Schedule": config["schedule"], "Init": config["init"]}
            row.update(parse_summary(case / "summary.txt"))
            hpc_flip.append(row)
    write_csv(tables_dir / "flip_hpc_metricas.csv", ["Job", "Case", "Threads", "Schedule", "Init", "Elapsed_s", "CPI", "Physical_Cores", "Physical_Cores_Used", "Memory_Bound_pct", "Cache_Bound_pct", "DRAM_Bound_pct", "NUMA_Remote_pct"], hpc_flip)
    tables.append(("flip_hpc_metricas.csv", "Flip: métricas HPC por caso e alocação"))

    # CPU time acumulado do Hotspots; todos os casos têm 50 iterações.
    zoom_rows: list[dict[str, object]] = []
    for prefix, suffix, schedule in (("00", "static", "static"), ("01", "dynamic1", "dynamic,1"), ("02", "dynamic16", "dynamic,16")):
        values = hotspot_times(zoom_root / f"{prefix}_zoom_{suffix}_hotspots.txt")
        summary = parse_summary(zoom_root / f"{prefix}_zoom_{suffix}_summary.txt")
        zoom_rows.append({"Schedule": schedule, **values, **summary})
    write_csv(tables_dir / "zoom_hotspots_schedules.csv", ["Schedule", "Copy", "Horizontal", "Vertical", "Elapsed_s", "CPU_s", "CPI", "Physical_Cores", "Physical_Cores_Used"], zoom_rows)
    tables.append(("zoom_hotspots_schedules.csv", "Zoom: CPU time acumulado por fase no Hotspots (50 iterações)"))
    line_chart(figures_dir / "06_zoom_hotspots_schedules.svg", "Zoom, 20 threads: Hotspots confirmam piora de todas as fases com dynamic", [str(row["Schedule"]) for row in zoom_rows], [(phase, [float(row.get(phase, math.nan)) for row in zoom_rows], color, None) for phase, color in (("Copy", "#1f77b4"), ("Horizontal", "#2ca02c"), ("Vertical", "#d62728"))], "CPU time acumulado (s)", y_zero=True, x_label="Schedule")
    figures.append(("06_zoom_hotspots_schedules.svg", "Zoom: 50 iterações no Hotspots; dynamic,1 aumenta CPU time nas três fases e o CPI (1,223 versus 1,110 com static)."))

    page(output, figures, tables)
    print(f"Visualizações geradas em: {output}")


if __name__ == "__main__":
    main()
