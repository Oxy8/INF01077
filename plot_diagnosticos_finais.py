#!/usr/bin/env python3
"""Visualiza a campanha diagnóstica Zoom / Flip / compilador no PCAD.

Os gráficos deste arquivo não se misturam aos da campanha principal: ela mede
as fases internas do Zoom, controla a primeira escrita (fresh x pre-touch) e
repete os schedules do Flip em rodadas pareadas e embaralhadas.

Uso:
    python plot_diagnosticos_finais.py
    python plot_diagnosticos_finais.py --input resultados_pcad_hype_diagnostico_zoom_flip_compilador_823585
"""

from __future__ import annotations

import argparse
import csv
import html
import math
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Iterable

from plot_resultados_pcad import PALETTE, bar_chart, heatmap, line_chart, safe_ratio


ROOT = Path(__file__).resolve().parent
THREADS = [1, 2, 4, 8, 12, 16, 20]
SCHEDULES = [("static", ""), ("static", "1"), ("static", "16"),
             ("dynamic", "1"), ("dynamic", "16"), ("dynamic", "64")]
SCHEDULE_COLORS = {
    "static": "#1f77b4", "static,1": "#4c78a8", "static,16": "#72b7b2",
    "dynamic,1": "#d62728", "dynamic,16": "#f58518", "dynamic,64": "#e45756",
}


def read_csv(path: Path, integer: Iterable[str] = (), numeric: Iterable[str] = ()) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with path.open(newline="", encoding="utf-8") as source:
        for raw in csv.DictReader(source):
            row: dict[str, object] = dict(raw)
            for field in integer:
                row[field] = int(raw[field])
            for field in numeric:
                row[field] = float(raw[field]) if raw[field] else 0.0
            rows.append(row)
    return rows


def write_csv(path: Path, fields: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as destination:
        writer = csv.DictWriter(destination, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def schedule_name(schedule: object, chunk: object) -> str:
    return str(schedule) if not chunk else f"{schedule},{chunk}"


def schedule_label(key: str) -> str:
    return "static (padrão)" if key == "static" else key


def median(values: list[float]) -> float:
    return statistics.median(values) if values else math.nan


def esc(value: object) -> str:
    return html.escape(str(value))


def fig_link(name: str, caption: str) -> str:
    return f'<article><a href="figures/{esc(name)}"><img src="figures/{esc(name)}" alt="{esc(caption)}"></a><p>{esc(caption)}</p></article>'


def build_page(output: Path, figures: list[tuple[str, str]], tables: list[tuple[str, str]], source: Path) -> None:
    cards = "\n".join(fig_link(name, caption) for name, caption in figures)
    table_links = "\n".join(f'<li><a href="tables/{esc(name)}">{esc(caption)}</a></li>' for name, caption in tables)
    page = f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><title>Diagnósticos finais — PCAD Hype</title>
<style>
body{{font-family:Arial,sans-serif;margin:32px;max-width:1400px;color:#202124;background:#fafafa}}
h1{{margin-bottom:6px}} .note{{color:#555;max-width:1000px;line-height:1.45}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(420px,1fr));gap:22px}}
article{{background:white;border:1px solid #ddd;padding:12px;border-radius:8px}} img{{width:100%;height:auto}} p{{margin:8px 3px 2px;line-height:1.35}}
a{{color:#135aa0}} code{{background:#eee;padding:2px 4px}}
</style></head><body>
<h1>Diagnósticos finais: Zoom, Flip e distribuição de trabalho</h1>
<p class="note">Fonte: <code>{esc(source.name)}</code>. Os gráficos de tempo resumido usam <strong>medianas</strong>; o gráfico de razões pareadas preserva cada rodada individual. As barras verticais em gráficos de linhas representam o intervalo mínimo–máximo das 10 repetições do Zoom. O Flip foi executado em 12 rodadas pareadas e com ordem embaralhada; por isso, os gráficos de razão comparam cada schedule à execução <em>static</em> da mesma rodada.</p>
<p class="note">No pré-toque, a saída é escrita antes da região medida: ele isola o efeito de primeira alocação/páginas de memória do custo dos kernels. Nas razões do Flip, valor acima de 1× significa que o schedule comparado foi mais rápido que <em>static</em>.</p>
<div class="grid">{cards}</div>
<h2>Tabelas de apoio</h2><ul>{table_links}</ul>
<p class="note">Os artefatos de assembly da coleta estão em <code>{esc(source.name)}/compiler/</code>. Os relatórios de vetorização vazios são uma limitação daquele job e não evidência de ausência de vetorização.</p>
</body></html>"""
    (output / "index.html").write_text(page, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="resultados_pcad_hype_diagnostico_zoom_flip_compilador_823585")
    parser.add_argument("--out", default="visualizacoes_pcad_hype_final_diagnosticos")
    args = parser.parse_args()
    source = Path(args.input)
    if not source.is_absolute():
        source = ROOT / source
    output = Path(args.out)
    if not output.is_absolute():
        output = ROOT / output
    figures_dir, tables_dir = output / "figures", output / "tables"
    figures_dir.mkdir(parents=True, exist_ok=True)
    tables_dir.mkdir(parents=True, exist_ok=True)

    zoom = read_csv(source / "zoom_phases_summary.csv", integer=("Threads", "Samples"), numeric=tuple(
        f"{phase}_ms_{stat}" for phase in ("Copy", "Horizontal", "Vertical", "Total")
        for stat in ("Median", "Min", "Max", "Mean", "StdDev")))
    flip = read_csv(source / "flip_summary.csv", integer=("Threads", "Samples"), numeric=("Elapsed_ms_Median", "Elapsed_ms_Min", "Elapsed_ms_Max", "Elapsed_ms_Mean", "Elapsed_ms_StdDev"))
    flip_raw = read_csv(source / "flip_raw.csv", integer=("Threads", "Round", "Order"), numeric=("Elapsed_ms",))
    flip_threads = read_csv(source / "flip_threads_raw.csv", integer=("Threads", "Round", "Order", "Thread", "Rows"), numeric=("Work_ms",))

    figures: list[tuple[str, str]] = []
    tables: list[tuple[str, str]] = []

    # 1–4: Zoom com static, escalabilidade e fases.
    scaling = [row for row in zoom if row["Experiment"] == "zoom-scaling-static" and row["Touch_Mode"] == "fresh"]
    lookup = {(str(row["Build"]), int(row["Threads"])): row for row in scaling}
    scaling_table: list[dict[str, object]] = []
    for threads in THREADS:
        scalar, avx = lookup[("off-avx2", threads)], lookup[("omp-avx2", threads)]
        scaling_table.append({
            "Threads": threads,
            "Off_AVX2_Total_Median_ms": scalar["Total_ms_Median"], "Off_AVX2_Total_Min_ms": scalar["Total_ms_Min"], "Off_AVX2_Total_Max_ms": scalar["Total_ms_Max"],
            "OMP_AVX2_Total_Median_ms": avx["Total_ms_Median"], "OMP_AVX2_Total_Min_ms": avx["Total_ms_Min"], "OMP_AVX2_Total_Max_ms": avx["Total_ms_Max"],
            "Speedup_Off_div_OMP_AVX2": safe_ratio(float(scalar["Total_ms_Median"]), float(avx["Total_ms_Median"])),
        })
    write_csv(tables_dir / "zoom_escalabilidade.csv", list(scaling_table[0]), scaling_table)
    tables.append(("zoom_escalabilidade.csv", "Zoom: medianas, intervalo mínimo–máximo e speedup AVX2"))

    def series_for_build(build: str, phase: str, color: str) -> tuple[str, list[float], str, list[float]]:
        values = [float(lookup[(build, thread)][f"{phase}_ms_Median"]) for thread in THREADS]
        errors = [(float(lookup[(build, thread)][f"{phase}_ms_Max"]) - float(lookup[(build, thread)][f"{phase}_ms_Min"])) / 2 for thread in THREADS]
        return ("Sem SIMD / AVX2" if build == "off-avx2" else "SIMD explícito + AVX2", values, color, errors)

    line_chart(figures_dir / "01_zoom_escalabilidade_total.svg", "Zoom In: escalabilidade com static (dados fresh)", [str(x) for x in THREADS], [series_for_build("off-avx2", "Total", "#555555"), series_for_build("omp-avx2", "Total", "#8a2be2")], "Tempo total (ms)", y_zero=True)
    figures.append(("01_zoom_escalabilidade_total.svg", "Zoom: tempo total por threads; barras mostram mínimo–máximo."))

    avx_speedup = [safe_ratio(float(lookup[("off-avx2", t)]["Total_ms_Median"]), float(lookup[("omp-avx2", t)]["Total_ms_Median"])) for t in THREADS]
    line_chart(figures_dir / "02_zoom_speedup_avx2.svg", "Zoom In: speedup de SIMD + AVX2", [str(x) for x in THREADS], [("off-avx2 / omp-avx2", avx_speedup, "#8a2be2", None)], "Speedup (×)", reference=("sem ganho", 1.0, "#555555"))
    figures.append(("02_zoom_speedup_avx2.svg", "Zoom: speedup escalar de AVX2. A queda ao aumentar threads fica explícita."))

    for build, filename, title in (("off-avx2", "03_zoom_fases_sem_avx2.svg", "Zoom In sem SIMD/AVX2: fases internas"), ("omp-avx2", "04_zoom_fases_com_avx2.svg", "Zoom In com SIMD explícito + AVX2: fases internas")):
        phase_series = []
        for phase, color in (("Copy", "#1f77b4"), ("Horizontal", "#2ca02c"), ("Vertical", "#d62728")):
            values = [float(lookup[(build, t)][f"{phase}_ms_Median"]) for t in THREADS]
            errors = [(float(lookup[(build, t)][f"{phase}_ms_Max"]) - float(lookup[(build, t)][f"{phase}_ms_Min"])) / 2 for t in THREADS]
            phase_series.append((phase, values, color, errors))
        line_chart(figures_dir / filename, title, [str(x) for x in THREADS], phase_series, "Tempo da fase (ms)", y_zero=True)
        figures.append((filename, "Zoom: cópia, interpolação horizontal e interpolação vertical separadas."))

    # 5–6: schedules e primeira escrita da saída do Zoom.
    touch_rows = [row for row in zoom if row["Experiment"] == "zoom-schedule-touch"]
    touch_lookup = {(schedule_name(row["Schedule"], row["Chunk"]), str(row["Touch_Mode"])): row for row in touch_rows}
    schedule_keys = [schedule_name(schedule, chunk) for schedule, chunk in SCHEDULES]
    touch_table: list[dict[str, object]] = []
    for key in schedule_keys:
        for touch in ("fresh", "pretouch-static"):
            row = touch_lookup[(key, touch)]
            touch_table.append({"Schedule": key, "Touch_Mode": touch, "Total_Median_ms": row["Total_ms_Median"], "Total_Min_ms": row["Total_ms_Min"], "Total_Max_ms": row["Total_ms_Max"], "Copy_Median_ms": row["Copy_ms_Median"], "Horizontal_Median_ms": row["Horizontal_ms_Median"], "Vertical_Median_ms": row["Vertical_ms_Median"]})
    write_csv(tables_dir / "zoom_schedule_pretouch.csv", list(touch_table[0]), touch_table)
    tables.append(("zoom_schedule_pretouch.csv", "Zoom: schedules, pré-toque, fases e intervalo mínimo–máximo"))

    bar_chart(figures_dir / "05_zoom_schedules_pretouch.svg", "Zoom In com 20 threads: schedule e primeira escrita", [schedule_label(key) for key in schedule_keys], [("Saída fresh", [float(touch_lookup[(key, "fresh")]["Total_ms_Median"]) for key in schedule_keys], "#d62728"), ("Saída pré-tocada por static", [float(touch_lookup[(key, "pretouch-static")]["Total_ms_Median"]) for key in schedule_keys], "#1f77b4")], "Tempo total (ms)")
    figures.append(("05_zoom_schedules_pretouch.svg", "Zoom, 20 threads: separar primeira escrita/páginas do custo do schedule."))

    focus_keys = ["static", "static,1", "dynamic,1", "dynamic,16", "dynamic,64"]
    bar_chart(figures_dir / "06_zoom_fases_schedules.svg", "Zoom pré-tocado, 20 threads: onde cada schedule gasta tempo", [schedule_label(key) for key in focus_keys], [("Cópia", [float(touch_lookup[(key, "pretouch-static")]["Copy_ms_Median"]) for key in focus_keys], "#1f77b4"), ("Horizontal", [float(touch_lookup[(key, "pretouch-static")]["Horizontal_ms_Median"]) for key in focus_keys], "#2ca02c"), ("Vertical", [float(touch_lookup[(key, "pretouch-static")]["Vertical_ms_Median"]) for key in focus_keys], "#d62728")], "Tempo da fase (ms)")
    figures.append(("06_zoom_fases_schedules.svg", "Zoom pré-tocado: cópia e as duas fases de interpolação, por schedule."))

    # 7–10: confirmação pareada do Flip e divisão do trabalho.
    flip_order = ["static", "static,1", "static,16", "dynamic,1", "dynamic,16"]
    flip_lookup = {schedule_name(row["Schedule"], row["Chunk"]): row for row in flip}
    flip_table = [{"Schedule": key, "Samples": flip_lookup[key]["Samples"], "Median_ms": flip_lookup[key]["Elapsed_ms_Median"], "Min_ms": flip_lookup[key]["Elapsed_ms_Min"], "Max_ms": flip_lookup[key]["Elapsed_ms_Max"], "Mean_ms": flip_lookup[key]["Elapsed_ms_Mean"], "StdDev_ms": flip_lookup[key]["Elapsed_ms_StdDev"], "Speedup_vs_static_medians": safe_ratio(float(flip_lookup["static"]["Elapsed_ms_Median"]), float(flip_lookup[key]["Elapsed_ms_Median"]))} for key in flip_order]
    write_csv(tables_dir / "flip_schedules_confirmacao.csv", list(flip_table[0]), flip_table)
    tables.append(("flip_schedules_confirmacao.csv", "Flip: 12 amostras por schedule, mediana, dispersão e razão contra static"))
    bar_chart(figures_dir / "07_flip_schedules_medianas.svg", "Flip Horizontal, 20 threads: confirmação dos schedules", [schedule_label(key) for key in flip_order], [("Mediana de 12 rodadas", [float(flip_lookup[key]["Elapsed_ms_Median"]) for key in flip_order], "#1f77b4")], "Tempo total (ms)")
    figures.append(("07_flip_schedules_medianas.svg", "Flip: medianas da campanha de confirmação; a tabela preserva mínimo, máximo e desvio."))

    raw_by_round_schedule: dict[tuple[int, str], float] = {}
    for row in flip_raw:
        raw_by_round_schedule[(int(row["Round"]), schedule_name(row["Schedule"], row["Chunk"]))] = float(row["Elapsed_ms"])
    rounds = sorted({int(row["Round"]) for row in flip_raw})
    paired_rows: list[dict[str, object]] = []
    paired_series = []
    for idx, key in enumerate(flip_order[1:]):
        ratios = []
        for round_id in rounds:
            ratio = safe_ratio(raw_by_round_schedule[(round_id, "static")], raw_by_round_schedule[(round_id, key)])
            ratios.append(ratio)
            paired_rows.append({"Round": round_id, "Schedule": key, "Static_ms": raw_by_round_schedule[(round_id, "static")], "Schedule_ms": raw_by_round_schedule[(round_id, key)], "Static_div_Schedule": ratio})
        paired_series.append((key, ratios, PALETTE[idx + 1], None))
    write_csv(tables_dir / "flip_razoes_pareadas_por_rodada.csv", ["Round", "Schedule", "Static_ms", "Schedule_ms", "Static_div_Schedule"], paired_rows)
    tables.append(("flip_razoes_pareadas_por_rodada.csv", "Flip: razões static/schedule para cada rodada pareada"))
    line_chart(figures_dir / "08_flip_razoes_pareadas.svg", "Flip Horizontal: razão pareada static / schedule", [str(round_id + 1) for round_id in rounds], paired_series, "Speedup static / schedule (×)", reference=("empate", 1.0, "#555555"), x_label="Rodada embaralhada")
    figures.append(("08_flip_razoes_pareadas.svg", "Flip: cada ponto usa a mesma rodada; acima de 1× favorece o schedule indicado."))

    per_schedule_thread: dict[tuple[str, int], list[dict[str, object]]] = defaultdict(list)
    for row in flip_threads:
        per_schedule_thread[(schedule_name(row["Schedule"], row["Chunk"]), int(row["Thread"]))].append(row)
    thread_table: list[dict[str, object]] = []
    row_ratios: list[list[float]] = []
    work_ratios: list[list[float]] = []
    for key in flip_order:
        mean_work_by_thread = [statistics.fmean(float(row["Work_ms"]) for row in per_schedule_thread[(key, thread)]) for thread in range(20)]
        overall_work = statistics.fmean(mean_work_by_thread)
        row_ratios.append([statistics.fmean(float(row["Rows"]) for row in per_schedule_thread[(key, thread)]) / 300.0 for thread in range(20)])
        work_ratios.append([safe_ratio(value, overall_work) for value in mean_work_by_thread])
        for thread in range(20):
            rows_values = [float(row["Rows"]) for row in per_schedule_thread[(key, thread)]]
            work_values = [float(row["Work_ms"]) for row in per_schedule_thread[(key, thread)]]
            thread_table.append({"Schedule": key, "Thread": thread, "Mean_Rows": statistics.fmean(rows_values), "Rows_div_300": statistics.fmean(rows_values) / 300.0, "Mean_Work_ms": statistics.fmean(work_values), "Work_div_Schedule_Mean": safe_ratio(statistics.fmean(work_values), overall_work)})
    write_csv(tables_dir / "flip_por_thread.csv", list(thread_table[0]), thread_table)
    tables.append(("flip_por_thread.csv", "Flip: linhas e tempo médio por thread, normalizados por schedule"))
    heatmap(figures_dir / "09_flip_linhas_por_thread.svg", "Flip Horizontal: distribuição de linhas por thread", [str(x) for x in range(20)], [schedule_label(key) for key in flip_order], row_ratios, "Cada célula = linhas médias / 300; 1× é a divisão perfeitamente uniforme.")
    figures.append(("09_flip_linhas_por_thread.svg", "Flip: distribuição de linhas; revela o balanceamento real das iterações."))
    heatmap(figures_dir / "10_flip_tempo_por_thread.svg", "Flip Horizontal: tempo de trabalho relativo por thread", [str(x) for x in range(20)], [schedule_label(key) for key in flip_order], work_ratios, "Cada célula = tempo médio da thread / média do schedule; 1× significa trabalho temporal uniforme.")
    figures.append(("10_flip_tempo_por_thread.svg", "Flip: desequilíbrio temporal por thread, separado da simples contagem de linhas."))

    build_page(output, figures, tables, source)
    print(f"Visualizações geradas em: {output}")


if __name__ == "__main__":
    main()
