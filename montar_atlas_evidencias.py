#!/usr/bin/env python3
"""Gera um atlas HTML offline a partir das figuras e CSVs já preservados.

Uso: python -B montar_atlas_evidencias.py
Não modifica dados brutos e não depende de rede, servidor ou bibliotecas externas.
"""

from __future__ import annotations

import csv
import html
import json
import math
import os
import re
import statistics
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

from plot_resultados_pcad import bar_chart


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "atlas_evidencias"
FIG = OUT / "figures"
TABLES = OUT / "tables"
GROUPS = {
    "visualizacoes_pcad_hype_final_benchmark_principal": ("Benchmark principal", "822851, 822852, 822853", "5 por configuração", "plot_resultados_pcad.py"),
    "visualizacoes_pcad_hype_final_simd_avx2_adaptativo": ("AVX2 e chunks", "822851, 822852", "5 por configuração", "plot_resultados_avx.py"),
    "visualizacoes_pcad_hype_final_layout_aos_soa": ("Layouts AoS/SoA", "822854", "5 por configuração", "plot_resultados_layout.py"),
    "visualizacoes_pcad_hype_final_experimentos_complementares": ("Confirmação", "823348, 823349", "10 para schedules; 1 coleta VTune por caso", "plot_experimentos_complementares.py"),
    "visualizacoes_pcad_hype_final_diagnosticos": ("Diagnósticos Zoom/Flip", "823585", "10 para Zoom; 12 rodadas pareadas para Flip", "plot_diagnosticos_finais.py"),
    "visualizacoes_pcad_hype_experimentos_finais_824167_824168_824169_824170": ("Experimentos finais", "823586, 824167–824170", "5 para tamanhos Gaussianos; 2 alocações Flip; 1 coleta VTune por caso", "plot_experimentos_finais.py"),
}
PNG = ["grayscale_avx_on_vs_avx_off.png", "static_dynamic_ops_regulares.png", "filtro_adaptativo_static_vs_dynamic_4.png", "filtro_adaptativo_dynamic256_vs_dynamic_4.png"]
TOPIC_LABELS = {"schedules": "Static versus dynamic", "simd": "SIMD e AVX2", "layout": "Layout e convolução", "memoria": "Memória e VTune", "escala": "Escalabilidade e SMT"}
OPS = {"zoom": "Zoom In", "flip": "Flip Horizontal", "grayscale": "Grayscale", "gaussian": "Gaussian 11×11", "adaptive": "Filtro adaptativo"}


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def med(values: list[float]) -> float:
    return statistics.median(values)


def rel(target: Path, page: Path) -> str:
    return Path(os.path.relpath(target, page.parent)).as_posix()


def svg_details(path: Path) -> tuple[str, str, int, int]:
    tree = ET.parse(path)
    root = tree.getroot()
    title = root.find("{http://www.w3.org/2000/svg}title")
    axis = ["".join(x.itertext()) for x in root.findall("{http://www.w3.org/2000/svg}text") if x.get("class") == "axis"]
    raw = path.read_text(encoding="utf-8")
    if re.search(r'(?<![\w])(?:nan|inf)(?![\w])', raw, re.I):
        raise ValueError(f"SVG contém NaN/Inf: {path}")
    width, height = int(root.attrib["width"]), int(root.attrib["height"])
    for item in root.findall(".//*[@x]"):
        x = item.attrib.get("x", "")
        if re.fullmatch(r"-?\d+(?:\.\d+)?", x) and (float(x) < -2 or float(x) > width + 20):
            raise ValueError(f"Elemento fora do SVG: {path}, x={x}")
    return ("".join(title.itertext()) if title is not None else path.stem,
            axis[-1] if axis else "escala indicada na figura", width, height)


def source_table(group: str, name: str) -> Path | None:
    p = ROOT / group / "tables"
    if "benchmark_principal" in group:
        if name.startswith("00_tempo_total_dataset"): return p / "tempo_total_dataset_schedules_20_threads.csv"
        if name.startswith(("00_tempo", "00_speedup", "00_eficiencia")): return p / "tempo_total_operacoes_regulares.csv"
        if name.startswith("01_"): return p / "simd_por_operacao.csv"
        if name.startswith("02_"): return ROOT / "resultados_pcad_hype_final_regular_avx2_5reps_822851" / "benchmark_summary.csv"
        if name.startswith("03b_"): return p / "schedules_regulares_detalhe_20_threads.csv"
        if name.startswith("03_"): return p / "schedules_regulares_20_threads.csv"
        if name.startswith(("04_", "05_")): return ROOT / "resultados_pcad_hype_final_regular_avx2_5reps_822851" / "benchmark_summary.csv"
        if name.startswith("06_tempo_total"): return p / "adaptive_total_por_chunk_20_threads.csv"
        if name.startswith("06_tempo_chunks"): return p / "adaptive_chunks_20_threads.csv"
        if name.startswith("06_chunks"): return p / "adaptive_chunks_20_threads.csv"
        if name.startswith("07_"): return p / "adaptive_static_vs_dynamic16_20_threads.csv"
        if name.startswith("08_"): return ROOT / "resultados_pcad_hype_final_adaptativo_chunks_avx2_5reps_822852" / "benchmark_summary.csv"
        if name.startswith(("09_", "10_")): return p / "smt_20_vs_40.csv"
    if "simd_avx2_adaptativo" in group:
        return p / ("adaptativo_total_por_build_chunk.csv" if name.startswith("04_") else "efeito_simd_por_build.csv" if name.startswith(("01_", "02_")) else ROOT / "resultados_pcad_hype_final_adaptativo_chunks_avx2_5reps_822852" / "benchmark_summary.csv")
    if "layout_aos_soa" in group:
        return p / ("kernels_por_layout.csv" if name.startswith("01_") else "fases_20_threads.csv" if name.startswith("03_") else "efeito_simd.csv" if name.startswith("04_") else ROOT / "resultados_pcad_hype_final_layout_aos_soa_avx2_5reps_822854" / "layout_summary.csv")
    if "experimentos_complementares" in group:
        return p / ("schedules_confirmacao.csv" if name.startswith("03_") else "hpc_metricas.csv")
    if "diagnosticos" in group:
        return p / ("zoom_escalabilidade.csv" if name.startswith(("01_", "02_", "03_", "04_")) else "zoom_schedule_pretouch.csv" if name.startswith(("05_", "06_")) else "flip_schedules_confirmacao.csv" if name.startswith("07_") else "flip_razoes_pareadas_por_rodada.csv" if name.startswith("08_") else "flip_por_thread.csv")
    if "experimentos_finais_" in group:
        return p / ("gaussian_layout_hpc.csv" if name.startswith("01_") else "gaussian_tamanhos_mediana.csv" if name.startswith("02_") else "gaussian_speedup_separavel.csv" if name.startswith("03_gaussian") else "gaussian_efeito_avx2.csv" if name.startswith("03b_") else "flip_topologia_replicas.csv" if name.startswith(("04_", "05_")) else "zoom_hotspots_schedules.csv")
    return None


def classify(group: str, name: str) -> tuple[str, str | None, str, str]:
    low = name.lower()
    if "adaptive" in low or "adaptativo" in low or "chunks" in low: topic, op = "schedules", "adaptive"
    elif "flip" in low: topic, op = "schedules", "flip"
    elif "zoom" in low: topic, op = "simd", "zoom"
    elif "gaussian" in low or "layout" in group: topic, op = "layout", "gaussian" if "gaussian" in low else "grayscale" if "grayscale" in low else None
    elif "grayscale" in low: topic, op = "simd", "grayscale"
    elif "hpc" in low or "memory" in low: topic, op = "memoria", None
    elif "smt" in low or "escalabilidade" in low or "eficiencia" in low: topic, op = "escala", None
    elif "schedule" in low: topic, op = "schedules", None
    else: topic, op = "simd", None
    if group.endswith("experimentos_complementares") and low.startswith("03_"): topic = "schedules"
    if group.endswith("experimentos_finais_824167_824168_824169_824170") and low.startswith("01_"): topic = "memoria"
    if low.startswith(("09_smt", "10_smt")): topic = "escala"
    if low.startswith(("00_tempo", "00_speedup", "00_eficiencia")): topic = "escala"
    if name == "static_dynamic_ops_regulares.png": topic = "schedules"
    status = "verificado"
    if group.endswith("benchmark_principal") and low.startswith(("01_", "02_")): status = "historico"
    if "layout_aos_soa" in group and "grayscale" in low: status = "historico"
    if group.endswith("simd_avx2_adaptativo") and "chunks" in low: status = "redundante"
    if name in ("04_flip_primeiro_toque_20t.svg", "05_flip_desequilibrio_temporal.svg") and "experimentos_finais" in group: status = "corrigido"
    if name == "03_schedules_regulares_20_threads.svg" and "benchmark_principal" in group: status = "corrigido"
    metric = "tempo mediano (ms)"
    if "speedup" in low or "ganho" in low or "efeito" in low or "simd" in low or "schedule" in low or "chunks" in low: metric = "razão de tempos; sentido definido no eixo e na tabela"
    if "hpc" in low or "memory" in low: metric = "percentual/contador do perfil; não é tempo de kernel"
    if "flip_linhas" in low: metric = "linhas atribuídas por thread"
    if "flip_tempo" in low: metric = "tempo de trabalho por thread"
    if "flip_primeiro_toque" in low: metric = "razão de medianas static/dynamic,1; >1 favorece dynamic"
    if "flip_desequilibrio" in low: metric = "coeficiente de variação do tempo por thread (%)"
    if "hotspots" in low: metric = "CPU time acumulado no VTune; não usar como tempo decorrido"
    caveat = "Mediana por configuração; confira mínimo–máximo na tabela antes de afirmar diferença."
    if status == "historico": caveat = "Campanha anterior à refatoração do Grayscale; não combinar silenciosamente com o job 824454."
    if status == "redundante": caveat = "Recorte da mesma campanha do painel principal; mantido para rastreabilidade, não é réplica independente."
    if "hpc" in low or "hotspots" in low: caveat = "VTune altera a execução; use o perfil para diagnóstico, não como amostra de benchmark."
    if "schedules_regulares_20_threads" in name and "03b" not in name: caveat = "Cada barra é média geométrica de quatro razões de medianas; pode ocultar dispersão entre imagem/build."
    if "gaussian_speedup_separavel" in name: caveat = "AoS direto / SoA separável combina mudança de algoritmo e layout; NÃO é ganho AVX2."
    if "gaussian_efeito_avx2" in name: caveat = "Compara builds dentro do mesmo algoritmo; não confundir com o ganho direto→separável."
    if "flip_primeiro_toque" in name: caveat = "Dois jobs são réplicas de alocação, não dez repetições por caso; efeito depende da inicialização."
    return topic, op, status, metric + "||" + caveat


def context_for(name: str, group: str) -> str:
    bits = []
    for image in ("4000x3000", "6000x6000", "rain_paisage", "control_smooth", "control_noise", "control_half_noise", "control_bands", "firework", "sky", "stars"):
        if image in name: bits.append(image)
    if "_1t" in name: bits.append("1 thread")
    if "_20t" in name or "20_threads" in name: bits.append("20 threads")
    if "36mp" in name: bits.append("36 MP")
    if "static" in name: bits.append("static")
    if "avx2" in name: bits.append("Haswell/AVX2")
    if group.endswith("benchmark_principal") and name.startswith("03_"): bits.extend(("12/36 MP", "builds off/omp"))
    if group.endswith("experimentos_finais_824167_824168_824169_824170"):
        if name.startswith("01_"): bits.extend(("Gaussian 11×11, layouts AoS/SoA", "omp-avx2/off-avx2", "20 threads, static"))
        if name.startswith(("02_", "03_")): bits.extend(("3–11 taps", "off-avx2/omp-avx2", "static"))
        if name.startswith(("04_", "05_")): bits.extend(("init serial/paralelo-static", "static/dynamic,1"))
        if name.startswith("06_"): bits.extend(("20 threads", "static/dynamic,1/dynamic,16"))
    if group.endswith("simd_avx2_adaptativo") and name.startswith("04_"): bits.extend(("8 imagens", "20 threads", "static/dynamic por chunk", "off/omp/avx2"))
    if group.endswith("layout_aos_soa") and name.startswith("04_"): bits.extend(("12/36 MP", "1–20 threads", "static", "off/omp/avx2"))
    if group.endswith("experimentos_complementares"):
        if name.startswith(("01_", "02_")): bits.extend(("Zoom/Grayscale", "1/20 threads", "off-avx2/omp-avx2", "static, VTune HPC"))
        else: bits.extend(("6 operações, 36 MP", "20 threads", "static/dynamic,1/dynamic,16", "off-avx2/omp-avx2"))
    if group.endswith("diagnosticos"):
        if name.startswith("01_"): bits.extend(("Zoom In, 36 MP", "1–20 threads", "static", "off-avx2/omp-avx2"))
        if name.startswith(("05_", "06_")): bits.extend(("Zoom In, 36 MP", "20 threads", "static/dynamic chunks", "pré-toque/fresh"))
        if name.startswith(("07_", "08_", "09_", "10_")): bits.extend(("Flip Horizontal, 36 MP", "20 threads", "static/dynamic chunks"))
    if not bits and "benchmark_principal" in group: bits.append("12 e 36 MP; até 20 threads")
    return ", ".join(bits) or "ver tabela de suporte para imagem/build/threads/schedule"


def exact_jobs(group: str, name: str) -> str:
    if group.endswith("benchmark_principal"):
        return "822851" if name.startswith(("00_", "01_", "02_", "03_", "04_", "05_")) else "822852" if name.startswith(("06_", "07_", "08_")) else "822853"
    if group.endswith("simd_avx2_adaptativo"):
        return "822851" if name.startswith(("01_", "02_")) else "822852"
    if group.endswith("layout_aos_soa"): return "822854"
    if group.endswith("experimentos_complementares"): return "823349" if name.startswith("03_") else "823348"
    if group.endswith("diagnosticos"): return "823585"
    if group.endswith("experimentos_finais_824167_824168_824169_824170"):
        return "824167" if name.startswith("01_") else "824170" if name.startswith(("02_", "03_")) else "824168, 824169" if name.startswith(("04_", "05_")) else "823586"
    return "não identificado"


def conclusion_for(group: str, name: str) -> str:
    if name.startswith("00_"):
        return "Resume tempos de campanhas distintas; os totais são somas de medianas por operação, não a mediana de uma execução conjunta."
    if "schedules_regulares" in name:
        return "Mostra a razão static/dynamic; valores >1 favorecem dynamic. A vista por configuração verifica se a média agregada se repete em cada imagem/build."
    if "tempo_chunks_adaptativo" in name or "chunks_" in name:
        return "Compara static com diferentes chunks dynamic para a imagem indicada; a ordem dos chunks importa mais que um único vencedor global."
    if "smt" in name: return "Compara 20 e 40 threads no mesmo conjunto de casos; a razão não pode ser extrapolada a outros kernels."
    if "escalabilidade" in name or "eficiencia" in name: return "Expõe a variação por threads; não identifica por si só o gargalo causal."
    if "simd" in name or "avx2" in name or "alvo_haswell" in name: return "Compara builds; o efeito é de pragma, vetorização automática e alvo de compilação conforme a legenda."
    if "kernels" in name: return "Tempo da fase Kernel, sem conversão AoS/SoA."
    if "total" in name and "layout" in group: return "Tempo total com fases de conversão e kernel; não confundir com o tempo isolado do kernel."
    if "fases" in name: return "Decompõe fases cronometradas separadamente; a soma deve ser lida no mesmo protocolo."
    if "gaussian_speedup_separavel" in name: return "Razão AoS direto / SoA separável mede sobretudo transformação algorítmica, não ganho AVX2 puro."
    if "gaussian_efeito_avx2" in name: return "Razão off/AVX dentro do mesmo algoritmo isola a comparação entre builds."
    if "gaussian_tamanhos" in name: return "Contrasta 3–11 taps; a vantagem do separável cresce com o tamanho, mas 3 taps não compensam o intermediário."
    if "flip_primeiro_toque" in name: return "O sinal static/dynamic se inverte entre inicialização serial e paralela-static nas duas alocações."
    if "flip_desequilibrio" in name: return "Dynamic reduz a dispersão do tempo de trabalho por thread; uniformidade não implica automaticamente menor tempo total."
    if "flip_linhas" in name: return "Static divide igualmente linhas; contagem igual não implica tempo igual."
    if "flip_tempo" in name: return "Mostra desequilíbrio temporal por thread sob static, apesar de igual número de linhas."
    if "flip_razoes" in name: return "Mostra cada rodada pareada, permitindo ver sinal e dispersão sem depender de média."
    if "flip_schedules" in name: return "Compara medianas e dispersão dos schedules para Flip no protocolo indicado."
    if "zoom_speedup" in name: return "O ganho adicional AVX2 do Zoom cai ao aumentar threads nessa campanha."
    if "zoom_schedules" in name or "zoom_hotspots" in name: return "Dynamic,1 aumenta o custo das fases; tempo sob VTune é diagnóstico, não benchmark, quando aplicável."
    if "zoom_fases" in name: return "Separa cópia, interpolação horizontal e vertical; o ganho SIMD não deve ser atribuído às três fases."
    if "hpc" in name or "memory" in name: return "Indica pressão de memória no trecho perfilado, sem atribuir diretamente um tempo de kernel ou número de cache misses."
    if "schedules_confirmacao" in name: return "Reavalia aparentes ganhos de dynamic com dez amostras intercaladas, sem misturar as campanhas."
    return "Mostra o contraste indicado no título; a tabela preserva os valores e a dispersão para uma leitura sustentada."


def inventory() -> list[dict[str, object]]:
    records = []
    for group, (campaign, jobs, samples, generator) in GROUPS.items():
        figures = sorted((ROOT / group / "figures").glob("*.svg"))
        for path in figures:
            title, axis, width, height = svg_details(path)
            table = source_table(group, path.name)
            if table is None or not table.exists(): raise FileNotFoundError(f"Tabela ausente para {path}: {table}")
            topic, op, status, combined = classify(group, path.name)
            metric, caveat = combined.split("||", 1)
            n = samples
            if group.endswith("experimentos_finais_824167_824168_824169_824170"):
                n = "5 por caso" if path.name.startswith(("02_", "03_")) else "2 jobs, 1 caso por job" if path.name.startswith(("04_", "05_")) else "1 coleta VTune por caso"
            if group.endswith("experimentos_complementares"):
                n = "10 por caso" if path.name.startswith("03_") else "1 coleta VTune por caso"
            if group.endswith("diagnosticos"):
                n = "12 rodadas pareadas" if path.name.startswith(("07_", "08_", "09_", "10_")) else "10 por caso"
            records.append({"id": f"f{len(records)+1:03d}", "path": path.relative_to(ROOT).as_posix(), "title": title,
                            "axis": axis, "width": width, "height": height, "topic": topic, "operation": op,
                            "status": status, "campaign": campaign, "jobs": exact_jobs(group, path.name), "samples": n,
                            "generator": generator, "table": table.relative_to(ROOT).as_posix(), "metric": metric,
                            "context": context_for(path.name, group), "caveat": caveat,
                            "question": TOPIC_LABELS[topic],
                            "conclusion": conclusion_for(group, path.name)})
    if len(records) != 99: raise ValueError(f"Inventário SVG inesperado: {len(records)} em vez de 99")
    for name in PNG:
        path = ROOT / name
        if not path.exists(): raise FileNotFoundError(path)
        topic, op, _, combined = classify("", name)
        records.append({"id": f"f{len(records)+1:03d}", "path": name, "title": name.replace("_", " ").removesuffix(".png"),
                        "axis": "captura raster; conferir eixos na imagem", "width": None, "height": None,
                        "topic": topic, "operation": op, "status": "nao_sustentado", "campaign": "captura manual",
                        "jobs": "origem não completamente reproduzível na captura", "samples": "não indicado na captura",
                        "generator": "captura manual", "table": None, "metric": "depende da captura", "context": "ver imagem",
                        "caveat": "Sem tabela e protocolo legíveis/associados no próprio PNG; use os painéis gerados dos CSVs para conclusões.",
                        "question": TOPIC_LABELS[topic], "conclusion": "Registro contextual, não evidência quantitativa autônoma."})
    return records


def perf_medians(scope: str, item: str, build: str, threads: int, group: str) -> tuple[dict[str, float], dict[str, float]]:
    directory = ROOT / "resultados_pcad_hype_regular_memory_1_20_824542" / scope / item / build / f"{threads}t" / group
    events: dict[str, list[float]] = defaultdict(list)
    coverage: dict[str, list[float]] = defaultdict(list)
    files = sorted(directory.glob("perf_*.csv"))
    if len(files) != 5: raise ValueError(f"Esperadas 5 amostras: {directory}")
    for file in files:
        for row in csv.reader(file.open(encoding="utf-8")):
            if len(row) >= 5 and row[2] in {"instructions", "LLC-load-misses", "L1-dcache-load-misses"}:
                events[row[2]].append(float(row[0]))
                coverage[row[2]].append(float(row[4]))
    return {k: med(v) for k, v in events.items()}, {k: med(v) for k, v in coverage.items()}


def build_memory_figures() -> list[dict[str, object]]:
    FIG.mkdir(parents=True, exist_ok=True); TABLES.mkdir(parents=True, exist_ok=True)
    raw = csv_rows(ROOT / "resultados_pcad_hype_regular_1_20_824454" / "regular_raw.csv")
    grouped: dict[tuple[str, int, str], list[float]] = defaultdict(list)
    for row in raw:
        if row["Schedule"] == "static" and row["Validation"] == "passed":
            grouped[row["Operation"], int(row["Threads"]), row["Simd_Build"]].append(float(row["Elapsed_ms"]))
    ops = sorted({key[0] for key in grouped})
    assert len(ops) == 17
    regular_rows = []
    for op in ops:
        for t in (1, 20):
            off, avx = (med(grouped[op, t, b]) for b in ("off-avx2", "omp-avx2"))
            if len(grouped[op, t, "off-avx2"]) != 10 or len(grouped[op, t, "omp-avx2"]) != 10: raise ValueError("N de tempos incorreto")
            basic_off, _ = perf_medians("regular", op, "off-avx2", t, "basic")
            basic_avx, _ = perf_medians("regular", op, "omp-avx2", t, "basic")
            cache_off, cov_off = perf_medians("regular", op, "off-avx2", t, "cache")
            cache_avx, cov_avx = perf_medians("regular", op, "omp-avx2", t, "cache")
            regular_rows.append({"Operation": op, "Threads": t, "Off_kernel_median_ms": off, "AVX_kernel_median_ms": avx,
                                 "Kernel_speedup_off_over_avx": off / avx, "Process_instructions_avx_over_off": basic_avx["instructions"] / basic_off["instructions"],
                                 "Process_LLC_load_misses_avx_over_off": cache_avx["LLC-load-misses"] / cache_off["LLC-load-misses"],
                                 "LLC_coverage_off_pct": cov_off["LLC-load-misses"], "LLC_coverage_avx_pct": cov_avx["LLC-load-misses"],
                                 "Time_job": 824454, "Counters_job": 824542, "Time_samples_per_build": 10, "Counter_samples_per_build": 5})
    regular_csv = TABLES / "regular_tempo_e_contadores.csv"
    write_csv(regular_csv, regular_rows)
    for t in (1, 20):
        series = [r for r in regular_rows if r["Threads"] == t]
        bar_chart(FIG / f"regular_kernel_versus_llc_{t}t.svg", f"17 operações, {t} thread(s): ganho do kernel e LLC do processo", ops,
                  [("tempo off/AVX do kernel", [r["Kernel_speedup_off_over_avx"] for r in series], "#1f77b4"),
                   ("LLC AVX/off do processo", [r["Process_LLC_load_misses_avx_over_off"] for r in series], "#d48419")],
                  "Razão (×); numerador indicado na legenda", baseline=1.0)
    layout_rows = []
    names = [("AoS_Naive", "aos"), ("SoA_Naive", "soa-naive"), ("SoA_Separable", "soa-separable")]
    for display, dirname in names:
        for t in (1, 20):
            off_basic, _ = perf_medians("gaussian11_kernel", dirname, "off-avx2", t, "basic")
            avx_basic, _ = perf_medians("gaussian11_kernel", dirname, "omp-avx2", t, "basic")
            off_cache, cov_off = perf_medians("gaussian11_kernel", dirname, "off-avx2", t, "cache")
            avx_cache, cov_avx = perf_medians("gaussian11_kernel", dirname, "omp-avx2", t, "cache")
            layout_rows.append({"Layout": display, "Threads": t, "Process_instructions_avx_over_off": avx_basic["instructions"] / off_basic["instructions"],
                                "Process_LLC_load_misses_avx_over_off": avx_cache["LLC-load-misses"] / off_cache["LLC-load-misses"],
                                "LLC_coverage_off_pct": cov_off["LLC-load-misses"], "LLC_coverage_avx_pct": cov_avx["LLC-load-misses"],
                                "Job": 824542, "Samples_per_build": 5, "Note": "Comparação dentro do mesmo layout; perf envolve processo inteiro; iterações diferem entre layouts"})
    layout_csv = TABLES / "gaussian_contadores_dentro_layout.csv"
    write_csv(layout_csv, layout_rows)
    labels = [f'{r["Layout"]} · {r["Threads"]}t' for r in layout_rows]
    for key, label, filename in [("Process_instructions_avx_over_off", "Instruções AVX/off do processo", "gaussian_instr_dentro_layout.svg"),
                                  ("Process_LLC_load_misses_avx_over_off", "LLC load misses AVX/off do processo", "gaussian_llc_dentro_layout.svg")]:
        bar_chart(FIG / filename, "Gaussian 11×11: comparação de builds dentro de cada layout", labels,
                  [(label, [r[key] for r in layout_rows], "#286b91")], "Contagem AVX/off do processo (×)", baseline=1.0)
    return [{"path": p.relative_to(ROOT).as_posix(), "title": svg_details(p)[0], "axis": svg_details(p)[1],
             "topic": "memoria" if "regular" in p.name else "layout", "operation": "gaussian" if "gaussian" in p.name else None,
             "status": "verificado", "campaign": "Cruzamento 824454 × 824542", "jobs": "824454, 824542" if "regular" in p.name else "824542",
             "samples": "10 tempos e 5 contagens por build" if "regular" in p.name else "5 contagens por build",
             "generator": "montar_atlas_evidencias.py", "table": (regular_csv if "regular" in p.name else layout_csv).relative_to(ROOT).as_posix(),
             "metric": "duas razões com numeradores diferentes" if "regular" in p.name else "contagem AVX/off do processo inteiro",
             "context": "6000×6000, static, 1/20 threads", "question": "Tempo de kernel versus contadores do processo",
             "conclusion": "O contraste deve ser interpretado por métrica; contagem maior não implica kernel mais lento.",
             "caveat": "Tempos de kernel e contadores vêm de jobs diferentes; perf envolve decodificação/hash e os eventos LLC têm multiplexação."}
            for p in sorted(FIG.glob("*.svg"))]


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)


def audit_ratios() -> dict[str, object]:
    regular = csv_rows(ROOT / "resultados_pcad_hype_regular_1_20_824454" / "regular_raw.csv")
    results = {}
    for op in ("Grayscale", "Zoom_In", "Gaussian_11x11"):
        for t in (1, 20):
            samples = {b: [float(r["Elapsed_ms"]) for r in regular if r["Operation"] == op and int(r["Threads"]) == t and r["Simd_Build"] == b and r["Validation"] == "passed"] for b in ("off-avx2", "omp-avx2")}
            assert all(len(v) == 10 for v in samples.values())
            results[f"{op}_{t}t_off_over_avx"] = med(samples["off-avx2"]) / med(samples["omp-avx2"])
    assert abs(results["Grayscale_1t_off_over_avx"] - 1.277) < .005
    assert abs(results["Zoom_In_1t_off_over_avx"] - 1.222) < .005
    assert abs(results["Zoom_In_20t_off_over_avx"] - 1.046) < .005
    layout = csv_rows(ROOT / "resultados_pcad_hype_regular_1_20_824454" / "layout_gaussian11_raw.csv")
    for name in ("AoS_Naive", "SoA_Naive", "SoA_Separable"):
        for t in (1, 20):
            d = {b: [float(r["Elapsed_ms"]) for r in layout if r["Layout"] == name and r["Phase"] == "Kernel" and int(r["Threads"]) == t and r["Simd_Build"] == b] for b in ("off-avx2", "omp-avx2")}
            assert all(len(v) == 10 for v in d.values())
            results[f"{name}_{t}t_off_over_avx"] = med(d["off-avx2"]) / med(d["omp-avx2"])
    assert abs(results["SoA_Naive_20t_off_over_avx"] - .503) < .005
    assert abs(results["SoA_Separable_1t_off_over_avx"] - 2.444) < .005
    old = csv_rows(ROOT / "resultados_pcad_hype_final_regular_avx2_5reps_822851" / "benchmark_raw.csv")
    grouped: dict[tuple[str, str, str, str, str], list[float]] = defaultdict(list)
    for r in old:
        if r["Operation"] in ("Flip_Horizontal", "Adjust_Brightness") and int(r["Threads"]) == 20:
            grouped[r["Operation"], r["Image"], r["Simd_Build"], r["Schedule"], r["Chunk"]].append(float(r["Elapsed_ms"]))
    published = csv_rows(ROOT / "visualizacoes_pcad_hype_final_benchmark_principal" / "tables" / "schedules_regulares_20_threads.csv")
    for op in ("Flip_Horizontal", "Adjust_Brightness"):
        for chunk in ("1", "16"):
            ratios = []
            for image in ("4000x3000.png", "6000x6000.png"):
                for build in ("off", "omp"):
                    static = grouped[op, image, build, "static", ""]
                    dynamic = grouped[op, image, build, "dynamic", chunk]
                    assert len(static) == len(dynamic) == 5
                    ratios.append(med(static) / med(dynamic))
            gm = math.exp(statistics.fmean(math.log(x) for x in ratios))
            shown = float(next(r for r in published if r["Operation"] == op)[f"dynamic,{chunk}"])
            assert abs(gm - shown) < 1e-10
            results[f"historical_{op}_dynamic{chunk}_geomean"] = gm
    return {"method": "medianas recalculadas dos CSVs brutos; schedules = média geométrica de 4 razões de medianas", "ratios": results}


def badge(status: str) -> str:
    return f'<span class="status {esc(status.replace("_", "-"))}">{esc(status.replace("_", " "))}</span>'


def page_shell(page: Path, title: str, body: str, subtitle: str = "") -> None:
    nav = [("Início", OUT / "index.html"), ("Catálogo", OUT / "catalogo.html")]
    nav += [(label, OUT / "temas" / f"{slug}.html") for slug, label in TOPIC_LABELS.items()]
    navigation = "".join(f'<a href="{esc(rel(target, page))}">{esc(label)}</a>' for label, target in nav)
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(f'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)} · Atlas OpenMP</title><link rel="stylesheet" href="{esc(rel(OUT / "assets" / "style.css", page))}"></head><body><header class="site-header"><div class="wrap"><a class="brand" href="{esc(rel(OUT / "index.html", page))}">Atlas de evidências · OpenMP</a><nav class="nav">{navigation}</nav></div></header><main class="wrap"><div class="breadcrumbs"><a href="{esc(rel(OUT / "index.html", page))}">Início</a> / {esc(title)}</div><div class="hero"><span class="eyebrow">Investigação reprodutível · PCAD hype</span><h1>{esc(title)}</h1><p class="lede">{esc(subtitle)}</p></div>{body}</main><footer class="wrap">Dados brutos preservados. Páginas locais sem dependências de rede. <a href="{esc(rel(ROOT / "RESULTADOS.md", page))}">Campanhas e protocolo</a>.</footer></body></html>''', encoding="utf-8")


def figure_card(record: dict[str, object], page: Path, note: str = "") -> str:
    path = ROOT / str(record["path"])
    table = ROOT / str(record["table"]) if record.get("table") else None
    table_link = f'<a href="{esc(rel(table, page))}">Tabela de suporte</a>' if table else "Tabela não identificada"
    generator = ROOT / str(record["generator"])
    generator_link = f'<a href="{esc(rel(generator, page))}">Gerador</a>' if generator.exists() else esc(record["generator"])
    return f'''<article class="figure-card" id="{esc(record['id'])}"><div>{badge(str(record['status']))}</div><h3>{esc(record['title'])}</h3><a href="{esc(rel(path,page))}"><img src="{esc(rel(path,page))}" alt="{esc(record['title'])}" loading="lazy"></a><dl><dt>Pergunta</dt><dd>{esc(record['question'])}</dd><dt>Métrica/eixo</dt><dd>{esc(record['metric'])}; {esc(record['axis'])}</dd><dt>Configuração</dt><dd>{esc(record['context'])}</dd><dt>Origem</dt><dd>Job(s) {esc(record['jobs'])}; {esc(record['samples'])}</dd><dt>Permite concluir</dt><dd>{esc(note or record['conclusion'])}</dd><dt>Ressalva</dt><dd>{esc(record['caveat'])}</dd></dl><p class="links"><a href="{esc(rel(path,page))}">Abrir figura original</a>{table_link}{generator_link}</p></article>'''


def code_excerpt(page: Path, source: Path, start: int, end: int, heading: str) -> str:
    lines = source.read_text(encoding="utf-8").splitlines()
    if not 1 <= start <= end <= len(lines): raise ValueError(f"Trecho inválido: {source}:{start}-{end}")
    snippet = "\n".join(f"{i:4d}  {line}" for i,line in enumerate(lines[start-1:end],start))
    return f'<section class="section"><h2>{esc(heading)}</h2><p>Fonte: <a href="{esc(rel(source,page))}">{esc(source.name)}:{start}–{end}</a>. O código mostra o trabalho distribuído; a confirmação de vetorização vem do relatório GCC, não do pragma sozinho.</p><pre><code>{esc(snippet)}</code></pre></section>'


def selected(records: list[dict[str, object]], group_suffix: str, name: str) -> dict[str, object]:
    found = [r for r in records if str(r["path"]).startswith(group_suffix) and str(r["path"]).endswith("/" + name)]
    if len(found) != 1: raise ValueError(f"Figura não encontrada/ambígua: {group_suffix}/{name}: {len(found)}")
    return found[0]


def evidence_section(title: str, statement: str, answer: str, suggestion: str, missing: str, figs: list[tuple[dict[str, object], str]], page: Path, docs: list[tuple[str, Path]] = []) -> str:
    doclinks = " ".join(f'<a href="{esc(rel(path,page))}">{esc(label)}</a>' for label, path in docs)
    return f'''<section class="investigation"><h2>{esc(title)}</h2><div class="triad"><div class="panel">{badge('confirmado')}<h3>O que responde</h3><p>{esc(answer)}</p></div><div class="panel">{badge('parcial')}<h3>O que sugere</h3><p>{esc(suggestion)}</p></div><div class="panel">{badge('aberto')}<h3>O que falta</h3><p>{esc(missing)}</p></div></div><p>{esc(statement)}</p><div class="evidence">{''.join(figure_card(r,page,n) for r,n in figs)}</div><p class="note">Documentos e código: {doclinks}</p></section>'''


def build_pages(records: list[dict[str, object]]) -> None:
    main = "visualizacoes_pcad_hype_final_benchmark_principal"
    diag = "visualizacoes_pcad_hype_final_diagnosticos"
    final = "visualizacoes_pcad_hype_experimentos_finais_824167_824168_824169_824170"
    comp = "visualizacoes_pcad_hype_final_experimentos_complementares"
    layout = "visualizacoes_pcad_hype_final_layout_aos_soa"
    avx = "visualizacoes_pcad_hype_final_simd_avx2_adaptativo"
    F = lambda g,n: selected(records,g,n)
    analyses = ROOT / "ANALISE_EVIDENCIAS.md"
    simd_doc = ROOT / "ANALISE_SIMD_824453_824454.md"
    mem_doc = ROOT / "ANALISE_MEMORIA_824542.md"
    loops_doc = ROOT / "RELATORIO_LOOPS_SIMD_17_OPERACOES.md"
    comp_doc = ROOT / "ANALISE_COMPLEMENTAR_FINAL.md"
    docs_common = [("Análise das 9 perguntas", analyses)]

    p = OUT / "investigacoes" / "zoom.html"
    body = evidence_section("Por que o ganho AVX2 cai de 1 para 20 threads?", "Imagem 6000×6000, static, compilação Haswell. O ganho atualizado do kernel é 1,222× (1t) e 1,046× (20t), dez repetições; a série diagnóstica independente também decai.", "O loop vertical, não o Zoom inteiro, foi vetorizado em 32 bytes. O ganho do kernel diminui com mais threads.", "As fases não vetorizadas e o custo de memória/runtime passam a pesar relativamente mais. Contadores do processo inteiro não localizam a causa.", "Contadores e banda DRAM por fase em 1/20 threads; controle de afinidade/NUMA no mesmo binário.", [(F(diag,"02_zoom_speedup_avx2.svg"),"Ganho por threads no diagnóstico de dez repetições."),(F(diag,"03_zoom_fases_sem_avx2.svg"),"Decomposição das fases sem AVX2."),(F(diag,"04_zoom_fases_com_avx2.svg"),"Decomposição das fases com AVX2."),(F("atlas_evidencias","regular_kernel_versus_llc_1t.svg"),"O kernel acelera, embora LLC misses do processo aumentem.")],p,docs_common+[("Tempos e GCC",simd_doc),("Memória",mem_doc)])
    body += evidence_section("Por que dynamic,1 degrada Zoom?", "A cópia fresh mede 10,41 ms em static e 54,12 ms em dynamic,1; após pré-toque, 8,80 ms em dynamic,1. Mesmo após pré-toque, o total é 17,34 ms static e 29,97 ms dynamic,1.", "A distribuição em linhas pequenas e a primeira escrita das páginas explicam boa parte da perda; não é desequilíbrio aritmético do Zoom.", "O perfil de 50 iterações registra mais CPU time nas três fases com dynamic,1, especialmente na vertical.", "Contadores por fase para decompor fila OpenMP, localidade e tráfego remoto.", [(F(diag,"05_zoom_schedules_pretouch.svg"),"Contraste fresh/pré-toque."),(F(diag,"06_zoom_fases_schedules.svg"),"Custos de cada fase por schedule."),(F(final,"06_zoom_hotspots_schedules.svg"),"CPU time acumulado sob VTune; não é wall time de benchmark.")],p,docs_common+[("Confirmação Hotspots",comp_doc)])
    body += code_excerpt(p,ROOT/"577262-FPI-Relatorio2"/"image_manipulation.cpp",697,723,"Código: interpolação horizontal e vertical")
    body += '<p class="note">GCC 824453: <code>image_manipulation.cpp:714</code> recebeu <code>loop vectorized using 32 byte vectors</code>; os laços de cópia e interpolação horizontal não têm confirmação equivalente. <a href="'+esc(rel(ROOT/'resultados_pcad_hype_compiler_evidence_824453'/'omp-avx2'/'image_manipulation.opt-info.txt',p))+'">Relatório GCC completo</a>.</p>'
    page_shell(p,"Zoom In",body,"Separar vetorização da fase vertical, escalabilidade e efeito da granularidade do schedule.")

    p = OUT / "investigacoes" / "flip.html"
    body = evidence_section("Dynamic melhora o Flip Horizontal de modo reprodutível?", "No job 823349, static/dynamic,1 = 1,084× em 20 threads; houve 10 repetições. No diagnóstico 823585, 12 rodadas pareadas confirmam tendência para a preparação original.", "O ganho ocorre naquele protocolo, mas não é uma propriedade invariável do algoritmo.", "Static atribui exatamente 300 linhas por thread em 20t, porém o tempo de trabalho varia. Dynamic redistribui linhas para equalizar duração.", "Rotacionar lugares OpenMP e medir frequência por núcleo; repetir mais inicializações no mesmo host.", [(F(comp,"03_schedules_confirmacao.svg"),"Confirmação de 10 amostras para várias operações."),(F(diag,"08_flip_razoes_pareadas.svg"),"Razões por rodada, sem esconder variação."),(F(diag,"09_flip_linhas_por_thread.svg"),"Linhas atribuídas por thread."),(F(diag,"10_flip_tempo_por_thread.svg"),"Tempo por thread, distinto da contagem de linhas.")],p,docs_common)
    body += evidence_section("Qual o papel do primeiro toque e da topologia?", "Nos jobs independentes 824168/824169, init serial: 6,78/6,22 ms (static/dynamic,1); init paralelo-static: 4,20/4,53 ms. O sinal inverte.", "A inicialização das páginas participa causalmente do contraste em 20 threads.", "Em 10 threads no mesmo nó NUMA, dynamic ainda ganha; NUMA remoto não é a única explicação.", "Medir afinidade e frequências por núcleo em réplicas adicionais.", [(F(final,"04_flip_primeiro_toque_20t.svg"),"Figura corrigida: agora mostra duas razões finitas, uma em cada lado de 1×."),(F(final,"05_flip_desequilibrio_temporal.svg"),"Figura corrigida: CV de tempo por thread; não mede velocidade do kernel.")],p,[("Análise complementar",comp_doc)])
    body += code_excerpt(p,ROOT/"577262-FPI-Relatorio2"/"image_manipulation.cpp",1024,1046,"Código: uma linha por iteração, tempo por thread")
    page_shell(p,"Flip Horizontal",body,"A carga por linha é regular; o tempo observado por thread não foi.")

    p = OUT / "investigacoes" / "grayscale.html"
    body = evidence_section("Grayscale ganha com AVX2 no código atual?", "No job 824454, 78,044/61,115 ms em 1t (1,277×) e 6,165/5,319 ms em 20t (1,159×), dez amostras. No antigo 822851 havia empate.", "Sim, na revisão atual; o GCC reporta loop de pixels vetorizado em 32 bytes e o assembly inclui rearranjo RGB (`vpshufb`, `vpermq`).", "A extração para buffer bruto tornou a vetorização viável; não houve A/B das duas revisões no mesmo job.", "Se a atribuição causal exata à refatoração for necessária, compilar ambas as revisões no mesmo nó e protocolo.", [(F(layout,"01_kernels_6000x6000_Grayscale_omp-avx2.svg"),"Layout histórico: útil para discussão AoS/SoA, não substitui o job 824454."),(F("atlas_evidencias","regular_kernel_versus_llc_1t.svg"),"Grayscale acelera sem queda de misses LLC no processo."),(F("atlas_evidencias","regular_kernel_versus_llc_20t.svg"),"Comparação equivalente em 20 threads.")],p,[("Tempos e relatório GCC",simd_doc),("Auditoria de loops",loops_doc),("Memória",mem_doc)])
    body += '<p class="note warning">A captura VTune antiga do Grayscale compara CPU time acumulado e tempo decorrido. Mais CPU time não significa necessariamente maior latência do kernel; ela não pertence à mesma revisão da campanha 824454. <a href="'+esc(rel(ROOT/'grayscale_avx_on_vs_avx_off.png',p))+'">Abrir captura histórica</a>.</p>'
    body += code_excerpt(p,ROOT/"577262-FPI-Relatorio2"/"image_manipulation.cpp",975,987,"Código: pixels RGB e laço vetorizável")
    body += '<p class="note">GCC 824453: o laço de <code>image_manipulation.cpp:979</code> foi vetorizado em 32 bytes (com caminho de 16 bytes). <a href="'+esc(rel(ROOT/'resultados_pcad_hype_compiler_evidence_824453'/'omp-avx2'/'image_manipulation.opt-info.txt',p))+'">Relatório GCC completo</a>.</p>'
    page_shell(p,"Grayscale",body,"O diagnóstico mudou após a refatoração do loop de pixels; as campanhas não devem ser fundidas.")

    p = OUT / "investigacoes" / "gaussian.html"
    body = evidence_section("Por que SoA ingênuo com AVX2 piora?", "No kernel isolado de 11×11 (824454), SoA ingênuo off/AVX = 0,508× em 1t e 0,503× em 20t: o tempo quase dobra. Conversão foi cronometrada à parte.", "O laço mantém 121 taps; o GCC registra vetorização de 8 bytes associada aos taps, não um eficiente laço externo de pixels. A regressão está no kernel.", "O processo AVX2 registra 1,54× instruções e 1,64–1,66× LLC load misses dentro do mesmo layout; isso é compatível com a escolha desfavorável, mas não separa as parcelas de tempo.", "Contadores ligados/desligados somente no kernel, com mesmo número de iterações por layout.", [(F(layout,"01_kernels_6000x6000_Gaussian_11x11_omp-avx2.svg"),"Comparação de kernels sem conversão no job anterior."),(F(final,"01_gaussian_hpc_memoria.svg"),"HPC normalizado: não comparar tempos absolutos das coletas."),(F("atlas_evidencias","gaussian_instr_dentro_layout.svg"),"Instruções AVX/off dentro de cada layout; processo inteiro."),(F("atlas_evidencias","gaussian_llc_dentro_layout.svg"),"LLC load misses AVX/off dentro de cada layout; processo inteiro.")],p,[("Tempos/GCC",simd_doc),("Memória",mem_doc)])
    body += evidence_section("O que ganha no SoA separável: algoritmo ou AVX2?", "O especializado reduz 121 contribuições por pixel para 22 e vetoriza duas passadas de 32 bytes. Em 824454, off/AVX do mesmo separável = 2,444× (1t) e 1,361× (20t).", "Os dois efeitos existem no especializado: redução algorítmica e SIMD dentro do mesmo kernel.", "No benchmark genérico 3–11 taps (824170), o ganho direto/separável chega a 2,92× em 11 taps/20t, mas o efeito isolado AVX2 em 11 taps fica perto de 1×. Não transferir ganhos do especializado para o genérico.", "Isolar conversão e banda de memória com contadores por fase para decomposição fina.", [(F(final,"02_gaussian_tamanhos_20t.svg"),"Tempos por tamanho e algoritmo, cinco amostras."),(F(final,"03_gaussian_speedup_separavel.svg"),"Razão AoS direto / SoA separável = ganho algorítmico combinado."),(F(final,"03b_gaussian_efeito_avx2.svg"),"Razão off/AVX no mesmo algoritmo = efeito de build separado.")],p,[("Análise complementar",comp_doc),("Relatório GCC",simd_doc)])
    body += code_excerpt(p,ROOT/"577262-FPI-Relatorio2"/"layout_benchmark.cpp",235,255,"Código: SoA ingênuo mantém a convolução 11×11")
    body += code_excerpt(p,ROOT/"577262-FPI-Relatorio2"/"layout_benchmark.cpp",271,307,"Código: duas passadas de 11 taps")
    body += '<p class="note">GCC 824453: no SoA ingênuo, a linha 242 foi vetorizada em 8 bytes, mas o laço externo por pixel não recebeu uma vetorização eficiente. No separável, as linhas 278 e 299 foram vetorizadas em 32 bytes. <a href="'+esc(rel(ROOT/'resultados_pcad_hype_compiler_evidence_824453'/'omp-avx2'/'layout_benchmark.opt-info.txt',p))+'">Relatório GCC completo</a>.</p>'
    page_shell(p,"Gaussian 11×11",body,"Distinguir layout, algoritmo separável, vetorização e conversão.")

    p = OUT / "investigacoes" / "adaptive.html"
    body = evidence_section("Quando dynamic ajuda uma carga irregular?", "A varredura do job 822852 inclui static e vários chunks dynamic em quatro imagens reais e quatro controles; são cinco repetições por configuração.", "O tamanho do chunk interage com a distribuição de detalhes da imagem. As curvas por imagem são mais informativas que apenas o total.", "A irregularidade por linha dá oportunidade para balanceamento, mas chunk pequeno custa despacho e afeta localidade.", "Para atribuir tempo por fase/linha, medir mapa de trabalho e tempo por thread com os mesmos chunks.", [(F(main,"06_tempo_chunks_adaptativo_rain_paisage.svg"),"Imagem real rain_paisage: static e a varredura dynamic."),(F(main,"06_tempo_chunks_adaptativo_control_smooth_6000x6000.svg"),"Controle homogêneo: checa custo do schedule."),(F(main,"06_tempo_total_chunks_adaptativo.svg"),"Soma de medianas das oito imagens, não uma execução única."),(F(main,"07_adaptativo_static_vs_dynamic16.svg"),"Contraste por imagem e build.")],p,docs_common)
    body += code_excerpt(p,ROOT/"577262-FPI-Relatorio2"/"image_manipulation.cpp",593,609,"Código: a janela depende do detalhe do pixel")
    page_shell(p,"Filtro adaptativo",body,"Static versus dynamic deve ser lido por imagem e tamanho de chunk; o total esconde regimes distintos.")

    topic_data = {
      "schedules": ("Carga regular não garante tempo por thread uniforme. A campanha principal, confirmação e controles de primeiro toque têm escopos distintos.",[(F(main,"03_schedules_regulares_20_threads.svg"),"Visão histórica agregada: média geométrica de quatro razões, não uma razão única."),(F(main,"03b_schedules_regulares_por_configuracao_20_threads.svg"),"Desagregação por imagem/build."),(F(comp,"03_schedules_confirmacao.svg"),"Confirmação intercalada com dez amostras."),(F(main,"06_tempo_chunks_adaptativo_rain_paisage.svg"),"Contraste com carga irregular."),(F(final,"04_flip_primeiro_toque_20t.svg"),"Controle causal de inicialização."),(F(diag,"05_zoom_schedules_pretouch.svg"),"Zoom: custo de chunk/localidade/primeiro toque.")],[("Zoom","zoom"),("Flip Horizontal","flip"),("Filtro adaptativo","adaptive")]),
      "simd": ("Off/AVX2 compara dois builds, inclusive vetorização automática; somente alguns laços receberam código vetorial útil. Resultados antigos do Grayscale são históricos.",[(F(diag,"02_zoom_speedup_avx2.svg"),"Zoom perde ganho adicional com mais threads."),(F("atlas_evidencias","regular_kernel_versus_llc_1t.svg"),"17 operações atuais: tempo do kernel versus contadores globais."),(F("atlas_evidencias","regular_kernel_versus_llc_20t.svg"),"Mesmo cruzamento em 20 threads."),(F(final,"03b_gaussian_efeito_avx2.svg"),"Efeito de build dentro do mesmo algoritmo."),(F(avx,"02_alvo_haswell_36mp_static.svg"),"Diferença de alvo de compilação da campanha histórica.")],[("Zoom","zoom"),("Grayscale","grayscale"),("Gaussian 11×11","gaussian")]),
      "layout": ("Conversão, kernel e transformação algorítmica são métricas separadas. Os ganhos de 2× da Gaussiana genérica não são, por si, ganhos AVX2.",[(F(layout,"01_kernels_6000x6000_Gaussian_11x11_omp-avx2.svg"),"Kernel 11×11 por layout."),(F(layout,"03_fases_20t_6000x6000_Gaussian_11x11.svg"),"Conversão e kernel cronometrados separadamente."),(F(final,"03_gaussian_speedup_separavel.svg"),"Efeito combinado direto/separável."),(F(final,"03b_gaussian_efeito_avx2.svg"),"Efeito de build no mesmo algoritmo."),(F("atlas_evidencias","gaussian_instr_dentro_layout.svg"),"Contadores dentro do mesmo layout.")],[("Gaussian 11×11","gaussian"),("Grayscale","grayscale")]),
      "memoria": ("VTune e perf explicam pressão de recursos, mas contadores do processo inteiro não provam comportamento de um laço específico.",[(F(comp,"01_hpc_memory_bound.svg"),"HPC: fração memory bound, amostragem VTune."),(F(comp,"02_hpc_dram_bandwidth.svg"),"HPC: banda/DRAM, escopo perfilado."),(F(final,"01_gaussian_hpc_memoria.svg"),"Layouts Gaussianos sob HPC."),(F("atlas_evidencias","regular_kernel_versus_llc_1t.svg"),"Controle: Flip sem SIMD também eleva LLC misses no build AVX2."),(F("atlas_evidencias","gaussian_llc_dentro_layout.svg"),"Razão LLC dentro do mesmo layout, sem atribuição exclusiva ao kernel.")],[("Zoom","zoom"),("Gaussian 11×11","gaussian"),("Flip Horizontal","flip")]),
      "escala": ("Curvas de 1–20 threads e sensibilidade 20/40 devem ser interpretadas separadamente; hiperthreading não é uma extensão linear de núcleos físicos.",[(F(main,"04_escalabilidade_static_6000x6000.svg"),"Tempo por operação e threads na campanha principal."),(F(main,"05_eficiencia_static_6000x6000.svg"),"Eficiência relativa ao caso de 1 thread."),(F(main,"09_smt_tempos_20_vs_40.svg"),"20 versus 40 threads, tempos absolutos."),(F(main,"10_smt_speedup_20_para_40.svg"),"Razão 20/40 por operação."),(F(diag,"01_zoom_escalabilidade_total.svg"),"Zoom por threads, dez amostras.")],[("Zoom","zoom"),("Grayscale","grayscale"),("Filtro adaptativo","adaptive")]),
    }
    for slug,(intro,figs,links) in topic_data.items():
        p = OUT / "temas" / f"{slug}.html"
        linkhtml = '<div class="toc">'+''.join(f'<a href="{esc(rel(OUT/"investigacoes"/f"{op}.html",p))}">{esc(label)}</a>' for label,op in links)+'</div>'
        body = f'<p class="note">{esc(intro)}</p><h2>Investigações específicas</h2>{linkhtml}<h2>Gráficos que acrescentam evidência</h2><div class="evidence">'+''.join(figure_card(r,p,n) for r,n in figs)+'</div>'
        if slug == "memoria":
            body += '<p class="note warning">Tempo decorrido e CPU time do VTune medem coisas diferentes: o segundo soma tempo de todas as threads. Na captura histórica do Grayscale aparecem 4,407/4,528 s de tempo decorrido e 41,746/46,843 s de CPU time; isso não substitui as medianas do kernel atual. O job 824542 mede contadores do processo inteiro, não só do laço.</p>'
        body += '<p class="note warning">Para verificar versões de código, dispersão e lacunas, consulte <a href="'+esc(rel(analyses,p))+'">a análise de evidências</a>, <a href="'+esc(rel(simd_doc,p))+'">tempos e compilador</a> e <a href="'+esc(rel(mem_doc,p))+'">contadores de memória</a>.</p>'
        page_shell(p,TOPIC_LABELS[slug],body,intro)

    p = OUT / "index.html"
    cards = ''.join(f'<article class="card"><h3>{esc(label)}</h3><p>{esc(desc)}</p><a href="{esc(rel(OUT/"temas"/f"{slug}.html",p))}">Abrir tema</a></article>' for slug,(label,desc) in {
        "schedules":("Static versus dynamic","Regularidade, granulação, primeiro toque e filtro adaptativo."),
        "simd":("SIMD e AVX2","Laços realmente vetorizados, ganhos atuais e efeitos históricos."),
        "layout":("Layout e convolução","AoS, SoA ingênuo e separável, conversão e tamanhos de máscara."),
        "memoria":("Memória e VTune","Pressão de cache, banda DRAM e limites do escopo dos contadores."),
        "escala":("Escalabilidade e SMT","Curvas 1–20 threads e comparação com 40 threads lógicas.")}.items())
    opcards=''.join(f'<a href="{esc(rel(OUT/"investigacoes"/f"{slug}.html",p))}">{esc(label)}</a>' for slug,label in OPS.items())
    body=f'''<p class="note">O percurso parte de perguntas, abre gráficos selecionados e mantém as 103 figuras originais no <a href="{esc(rel(OUT/'catalogo.html',p))}">catálogo pesquisável</a>. São 99 SVGs e 4 capturas PNG; o planejamento previa três capturas, mas o inventário real encontrou quatro. Quatro figuras novas cruzam os jobs 824454 e 824542 sem modificar dados brutos. <a href="{esc(rel(OUT/'REVISAO.md',p))}">Ver revisão e correções</a>.</p><section class="section"><h2>Perguntas de pesquisa</h2><div class="grid">{cards}</div></section><section class="section"><h2>Operações investigadas em profundidade</h2><div class="toc">{opcards}</div><p>As outras 12 operações regulares estão no panorama SIMD e na <a href="{esc(rel(loops_doc,p))}">auditoria dos 17 laços</a>.</p></section><section class="section"><h2>Como ler o estado das evidências</h2><div class="grid"><div class="panel">{badge('confirmado')} Resultado replicado ou diretamente medido sob protocolo compatível.</div><div class="panel">{badge('parcial')} A medição sustenta parte da explicação, mas não isola todas as causas.</div><div class="panel">{badge('hipotese')} Mecanismo plausível ainda sem teste causal específico.</div><div class="panel">{badge('aberto')} Questão para a qual falta medida decisiva.</div></div><p>O catálogo usa também estados de figura: verificado, corrigido, redundante, histórico e não sustentado. “Histórico” não significa errado; significa que a revisão/protocolo não deve ser mesclado ao atual sem aviso.</p></section><section class="section"><h2>Campanhas e documentos</h2><p><a href="{esc(rel(ROOT/'RESULTADOS.md',p))}">Mapa das campanhas</a> · <a href="{esc(rel(analyses,p))}">9 perguntas</a> · <a href="{esc(rel(comp_doc,p))}">Confirmações finais</a> · <a href="{esc(rel(simd_doc,p))}">Tempos e GCC</a> · <a href="{esc(rel(mem_doc,p))}">Perf/memória 824542</a></p><p>Jobs principais: 822851–822854; diagnósticos: 823348–823349 e 823585–823586; confirmações: 824167–824170; código gerado e tempos atuais: 824453–824454; memória: 824542.</p></section>'''
    page_shell(p,"Atlas de evidências dos experimentos OpenMP",body,"Uma leitura por pergunta, com figura, tabela, protocolo e limite da inferência no mesmo lugar.")


def catalog(records: list[dict[str, object]]) -> None:
    p = OUT / "catalogo.html"
    rows=[]
    for r in records:
        path=ROOT / str(r["path"])
        source = (ROOT / str(r["table"])) if r.get("table") else None
        link = f'<a href="{esc(rel(source,p))}">Tabela</a>' if source else "—"
        search=esc(" ".join(str(r[k]) for k in ("title","path","jobs","context","topic","status")).lower())
        rows.append(f'''<tr class="catalog-row" data-search="{search}" data-topic="{esc(r['topic'])}" data-status="{esc(r['status'])}"><td><a href="{esc(rel(path,p))}">{esc(r['title'])}</a><br><small>{esc(r['path'])}</small></td><td>{esc(TOPIC_LABELS[str(r['topic'])])}</td><td>{badge(str(r['status']))}</td><td>Job(s) {esc(r['jobs'])}<br>{esc(r['samples'])}</td><td>{link}<details><summary>Ficha</summary><p><b>Pergunta:</b> {esc(r['question'])}<br><b>Métrica/sentido:</b> {esc(r['metric'])}; {esc(r['axis'])}<br><b>Configuração:</b> {esc(r['context'])}<br><b>Conclusão permitida:</b> {esc(r['conclusion'])}<br><b>Ressalva:</b> {esc(r['caveat'])}<br><b>Gerador:</b> {esc(r['generator'])}</p></details></td></tr>''')
    body=f'''<p class="note">Inventário integral: 99 SVGs e 4 capturas PNG. As quatro figuras novas do atlas aparecem separadamente abaixo. Filtros funcionam por <code>file://</code>, sem servidor.</p><div class="catalog-controls"><input id="search" type="search" placeholder="Buscar operação, job, imagem ou figura" aria-label="Buscar figuras"><select id="topic-filter" aria-label="Filtrar tema"><option value="">Todos os temas</option>{''.join(f'<option value="{esc(k)}">{esc(v)}</option>' for k,v in TOPIC_LABELS.items())}</select><select id="status-filter" aria-label="Filtrar estado"><option value="">Todos os estados</option>{''.join(f'<option value="{s}">{esc(s.replace("_"," "))}</option>' for s in ('verificado','corrigido','redundante','historico','nao_sustentado'))}</select></div><p id="visible-count"></p><div class="table-wrap"><table><thead><tr><th>Figura original</th><th>Tema</th><th>Revisão</th><th>Protocolo</th><th>Suporte e ressalva</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div><h2>Gráficos novos de cruzamento</h2><div class="evidence">{''.join(figure_card(r,p) for r in records if str(r['path']).startswith('atlas_evidencias/figures/'))}</div><script src="{esc(rel(OUT/'assets'/'catalogo.js',p))}"></script>'''
    page_shell(p,"Catálogo de figuras",body,"Cada imagem preservada tem estado de revisão, contexto, origem, tabela e ressalva.")


def main() -> None:
    original = inventory()
    audit = audit_ratios()
    new = build_memory_figures()
    for i,r in enumerate(new,len(original)+1): r["id"] = f"f{i:03d}"
    records = original + new
    build_pages(records)
    catalog(records)
    (OUT / "manifesto_figuras.json").write_text(json.dumps({"original_svg":99,"original_png":4,"derived_svg":len(new),"figures":records},ensure_ascii=False,indent=2),encoding="utf-8")
    (OUT / "auditoria_recalculos.json").write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"Atlas: {OUT / 'index.html'} | {len(original)} originais + {len(new)} derivados")


if __name__ == "__main__": main()
