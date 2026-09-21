"""Compare OpenMP affinity policies from a complete Slurm benchmark job.

For each image, transformation, schedule and affinity, take the median of five
times. Divide the median with default affinity by the median with the selected
affinity, then take the geometric mean of those ratios across images.
"""

import argparse
import csv
import math
import re
import statistics
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


SCRIPT_DIR = Path(__file__).resolve().parent
AFFINITIES = ("default", "close", "spread")
AFFINITY_LABELS = ("Padrão", "Close", "Spread")
TRANSFORMATIONS = {
    "Adaptive_Gaussian": ("adaptive_gaussian.csv", "Denoising gaussiano adaptativo"),
    "Negative": ("negative.csv", "Negativo"),
}
COLUMNS = ["Repetition", "Image", "Num_Threads", "OMP_Schedule", "Transformation", "Time_ms"]
COLORS = {"static": "#2878a6", "dynamic": "#df8731"}
REPETITIONS = set(range(1, 6))


def geometric_mean(values):
    return math.exp(statistics.fmean(math.log(value) for value in values))


def read_config(path):
    config = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
        elif ":" in line:
            key, value = line.split(":", 1)
        else:
            raise ValueError(f"Linha inválida em {path}: {line}")
        key = key.strip()
        if key in config:
            raise ValueError(f"Chave duplicada em {path}: {key}")
        config[key] = value.strip()
    return config


def find_campaigns(runs_dir, job_id):
    if not runs_dir.is_dir():
        raise ValueError(f"Pasta de execuções não encontrada: {runs_dir}")

    campaigns_by_job = defaultdict(dict)
    for folder in sorted(runs_dir.iterdir()):
        config_path = folder / "config.txt"
        if not folder.is_dir() or not config_path.is_file():
            continue
        config = read_config(config_path)
        found_job = config.get("SLURM_JOB_ID")
        affinity = config.get("Affinity")
        if not found_job or affinity not in AFFINITIES:
            raise ValueError(f"Job ID ou afinidade inválida em {config_path}")
        if affinity in campaigns_by_job[found_job]:
            raise ValueError(f"Campanhas duplicadas para {found_job}/{affinity}")
        campaigns_by_job[found_job][affinity] = (folder, config)

    if not campaigns_by_job:
        raise ValueError(f"Nenhuma campanha encontrada em {runs_dir}")
    if job_id is None:
        if len(campaigns_by_job) != 1:
            ids = ", ".join(sorted(campaigns_by_job))
            raise ValueError(f"Há vários jobs ({ids}); escolha um com --job-id")
        job_id = next(iter(campaigns_by_job))
    if job_id not in campaigns_by_job:
        raise ValueError(f"Job {job_id} não encontrado em {runs_dir}")

    campaigns = campaigns_by_job[job_id]
    if set(campaigns) != set(AFFINITIES):
        missing = ", ".join(sorted(set(AFFINITIES) - set(campaigns)))
        raise ValueError(f"Job {job_id} incompleto; faltam afinidades: {missing}")

    reference_config = campaigns["default"][1]
    schedule_match = re.fullmatch(r"static,dynamic,([1-9][0-9]*)", reference_config.get("Schedules", ""))
    if not schedule_match:
        raise ValueError("config.txt deve registrar static e um dynamic,N")
    dynamic_chunk = int(schedule_match.group(1))
    schedules = ("static", f"dynamic_{dynamic_chunk}")

    same_fields = ("Host", "Images", "Threads", "Repetitions", "OMP_DYNAMIC",
                   "SLURM_CPUS_PER_TASK", "SLURM_CPU_BIND", "Cpus_allowed_list",
                   "Mems_allowed_list", "Schedules")
    for affinity in AFFINITIES:
        folder, config = campaigns[affinity]
        if any(config.get(field) != reference_config.get(field) for field in same_fields):
            raise ValueError(f"Configuração incompatível em {folder}")
        if config.get("Threads") != "40" or config.get("Repetitions") != "5" or config.get("OMP_DYNAMIC") != "FALSE":
            raise ValueError(f"Configuração de threads/repetições inválida em {folder}")
        expected_places = "unset" if affinity == "default" else "cores"
        expected_bind = "unset" if affinity == "default" else affinity
        if config.get("OMP_PLACES") != expected_places or config.get("OMP_PROC_BIND") != expected_bind:
            raise ValueError(f"Afinidade declarada não corresponde às variáveis OpenMP em {folder}")
    return job_id, campaigns, schedules


def read_csv(path, expected_transformation, schedules):
    groups = defaultdict(dict)
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != COLUMNS:
            raise ValueError(f"Colunas inválidas em {path}")
        for line_number, row in enumerate(reader, start=2):
            try:
                repetition = int(row["Repetition"])
                image = row["Image"]
                threads = int(row["Num_Threads"])
                schedule = row["OMP_Schedule"]
                transformation = row["Transformation"]
                time_ms = float(row["Time_ms"])
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError(f"Valor inválido em {path}:{line_number}") from error
            if (repetition not in REPETITIONS or not image or threads != 40 or
                    schedule not in schedules or transformation != expected_transformation or
                    not math.isfinite(time_ms) or time_ms <= 0):
                raise ValueError(f"Medição inválida em {path}:{line_number}")
            key = (image, schedule)
            if repetition in groups[key]:
                raise ValueError(f"Medição duplicada em {path}:{line_number}")
            groups[key][repetition] = time_ms

    images = {image for image, _ in groups}
    if not images or set(groups) != {(image, schedule) for image in images for schedule in schedules}:
        raise ValueError(f"Faltam imagens ou escalonamentos em {path}")
    if any(set(repetitions) != REPETITIONS for repetitions in groups.values()):
        raise ValueError(f"Faltam repetições em {path}")
    medians = {key: statistics.median(repetitions.values()) for key, repetitions in groups.items()}
    return images, medians


def calculate_summary(campaigns, schedules):
    medians = {}
    image_set = None
    for affinity in AFFINITIES:
        folder, _ = campaigns[affinity]
        for transformation, (filename, _) in TRANSFORMATIONS.items():
            images, measured = read_csv(folder / filename, transformation, schedules)
            if image_set is None:
                image_set = images
            elif images != image_set:
                raise ValueError(f"Conjunto de imagens diferente em {folder / filename}")
            medians[(affinity, transformation)] = measured

    summary = {}
    for transformation in TRANSFORMATIONS:
        for schedule in schedules:
            for affinity in AFFINITIES:
                reference = medians[("default", transformation)]
                candidate = medians[(affinity, transformation)]
                ratios = [reference[(image, schedule)] / candidate[(image, schedule)]
                          for image in sorted(image_set)]
                total_ms = sum(candidate[(image, schedule)] for image in image_set)
                summary[(transformation, schedule, affinity)] = (geometric_mean(ratios), total_ms)
    return summary, len(image_set)


def plot_transformation(transformation, title, schedules, summary, image_count, job_id, host, output):
    fig, (ax_speedup, ax_time) = plt.subplots(1, 2, figsize=(15, 6))
    positions = list(range(len(AFFINITIES)))
    all_speedups = []
    max_total_ms = max(summary[(transformation, schedule, affinity)][1]
                       for schedule in schedules for affinity in AFFINITIES)
    time_scale = 1000 if max_total_ms >= 1000 else 1
    time_unit = "s" if time_scale == 1000 else "ms"

    for index, schedule in enumerate(schedules):
        offset = -0.16 if index == 0 else 0.16
        x_values = [position + offset for position in positions]
        speedups = [summary[(transformation, schedule, affinity)][0] for affinity in AFFINITIES]
        times = [summary[(transformation, schedule, affinity)][1] / time_scale for affinity in AFFINITIES]
        all_speedups.extend(speedups)
        label = "Estático" if schedule == "static" else f"Dinâmico (chunk {schedule.split('_')[1]})"
        color = COLORS["static" if schedule == "static" else "dynamic"]

        ax_speedup.plot(x_values, speedups, color=color, marker="o", markersize=9,
                        linestyle="none", label=label)
        for x, value in zip(x_values, speedups):
            ax_speedup.annotate(f"{value:.3f}×", (x, value), xytext=(0, 9),
                                textcoords="offset points", ha="center", fontsize=9)

        bars = ax_time.bar(x_values, times, width=0.27, color=color, label=label)
        for bar, value in zip(bars, times):
            ax_time.annotate(f"{value:.2f}",
                             (bar.get_x() + bar.get_width() / 2, bar.get_height()),
                             xytext=(0, 4), textcoords="offset points", ha="center", fontsize=9)

    ax_speedup.axhline(1, color="black", linestyle="--", linewidth=1, alpha=0.7)
    ax_speedup.set_xticks(positions, AFFINITY_LABELS)
    ax_speedup.set_xlim(-0.5, len(positions) - 0.5)
    ax_speedup.set_ylim(min(0.9, min(all_speedups) - 0.04),
                        max(1.1, max(all_speedups) + 0.04))
    ax_speedup.set_title("Aceleração relativa ao padrão")
    ax_speedup.set_ylabel("Média geométrica da aceleração (×)")
    ax_speedup.grid(axis="y", alpha=0.25)
    ax_speedup.legend(loc="best")

    ax_time.set_xticks(positions, AFFINITY_LABELS)
    ax_time.set_title("Tempo do conjunto de imagens")
    ax_time.set_ylabel(f"Soma das medianas por imagem ({time_unit})")
    ax_time.set_ylim(0, max_total_ms / time_scale * 1.17)
    ax_time.grid(axis="y", alpha=0.25)
    ax_time.set_axisbelow(True)

    fig.suptitle(f"{title} — 40 threads — job {job_id} ({host})", fontsize=16)
    fig.text(0.5, 0.035,
             f"Cada imagem: mediana de 5 repetições. Aceleração = mediana padrão ÷ mediana da afinidade, "
             f"com o mesmo escalonamento.\nEsquerda: média geométrica das {image_count} imagens "
             "(acima de 1× é mais rápido). Direita: soma das medianas; menor é melhor.",
             ha="center", va="bottom", fontsize=9)
    fig.tight_layout(rect=(0.02, 0.13, 0.98, 0.93))
    fig.savefig(output, dpi=250)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description="Compara as políticas de afinidade de um job Slurm.")
    parser.add_argument("runs_dir", nargs="?", type=Path, default=SCRIPT_DIR / "runs",
                        help="Pasta com as campanhas (padrão: benchmark_affinity/runs)")
    parser.add_argument("--job-id", help="ID do job Slurm, obrigatório se houver vários jobs")
    parser.add_argument("--output-dir", type=Path, help="Pasta de saída dos PNGs")
    args = parser.parse_args()

    try:
        job_id, campaigns, schedules = find_campaigns(args.runs_dir, args.job_id)
        summary, image_count = calculate_summary(campaigns, schedules)
        output_dir = args.output_dir or SCRIPT_DIR / "plots" / f"job_{job_id}"
        output_dir.mkdir(parents=True, exist_ok=True)
        host = campaigns["default"][1]["Host"]
        for transformation, (_, title) in TRANSFORMATIONS.items():
            output = output_dir / f"affinity_{transformation.lower()}.png"
            plot_transformation(transformation, title, schedules, summary,
                                image_count, job_id, host, output)
            print(f"Gráfico salvo: {output}")
        for transformation in TRANSFORMATIONS:
            for schedule in schedules:
                values = ", ".join(
                    f"{affinity}={summary[(transformation, schedule, affinity)][0]:.3f}×"
                    for affinity in AFFINITIES
                )
                print(f"{transformation} / {schedule}: {values}")
    except (OSError, ValueError, csv.Error) as error:
        parser.exit(1, f"Erro: {error}\n")


if __name__ == "__main__":
    main()
