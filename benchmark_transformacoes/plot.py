"""Plota a aceleração por transformação a partir do CSV do benchmark dedicado.

Para cada imagem, transformação, quantidade de threads e escalonamento:
1. Calcula a mediana de cinco tempos medidos.
2. Divide a mediana estática pela mediana do escalonamento avaliado.
3. Calcula a média geométrica dessas razões entre as imagens.
"""

import argparse
import math
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns


COLUNAS = ["Repetition", "Image", "Num_Threads", "OMP_Schedule", "Transformation", "Time_ms"]
THREADS = {20, 40}
REPETICOES = set(range(1, 6))
CHUNKS = {2 ** expoente for expoente in range(11)}

NOMES_TRANSFORMACOES = {
    "Grayscale": "Escala de cinza",
    "Flip_Horizontal": "Espelhamento horizontal",
    "Adjust_Brightness": "Brilho",
    "Flip_Vertical": "Espelhamento vertical",
    "Quantize": "Quantização",
    "Adjust_Contrast": "Contraste",
    "Negative": "Negativo",
    "Equalize_Histogram": "Equalização do histograma",
    "Zoom_In": "Ampliação",
    "Zoom_Out": "Redução",
    "Rotate_CW": "Rotação horária",
    "Rotate_CCW": "Rotação anti-horária",
    "Gaussian_3x3": "Gaussiano 3×3",
    "Gaussian_5x5": "Gaussiano 5×5",
    "Gaussian_7x7": "Gaussiano 7×7",
    "Gaussian_9x9": "Gaussiano 9×9",
    "Gaussian_11x11": "Gaussiano 11×11",
    "Adaptive_Gaussian": "Gaussiano adaptativo",
}


def ordem_schedule(schedule):
    if schedule == "static":
        return (0, 0)
    correspondencia = re.fullmatch(r"dynamic_(\d+)", schedule)
    if not correspondencia:
        raise ValueError(f"Escalonamento inválido: {schedule}")
    return (1, int(correspondencia.group(1)))


def carregar_e_validar(csv_path):
    df = pd.read_csv(csv_path)
    if list(df.columns) != COLUNAS:
        raise ValueError(f"Colunas esperadas: {', '.join(COLUNAS)}")
    if df.empty or df[COLUNAS].isna().any().any():
        raise ValueError("O CSV está vazio ou contém campos ausentes.")

    for coluna in ("Repetition", "Num_Threads", "Time_ms"):
        df[coluna] = pd.to_numeric(df[coluna], errors="raise")
    if not np.isfinite(df["Time_ms"]).all() or (df["Time_ms"] <= 0).any():
        raise ValueError("Todos os tempos precisam ser positivos e finitos.")
    if set(df["Num_Threads"]) != THREADS or set(df["Repetition"]) != REPETICOES:
        raise ValueError("A campanha deve conter 20 e 40 threads e as cinco repetições.")

    schedules = sorted(df["OMP_Schedule"].unique(), key=ordem_schedule)
    schedules_esperados = {"static", *(f"dynamic_{chunk}" for chunk in CHUNKS)}
    if set(schedules) != schedules_esperados:
        raise ValueError("Faltam o escalonamento estático ou chunks dinâmicos entre 1 e 1024.")

    transformacoes = df["Transformation"].drop_duplicates().tolist()
    if len(transformacoes) != 18:
        raise ValueError(f"Esperadas 18 transformações; encontradas {len(transformacoes)}.")
    chaves = ["Repetition", "Image", "Num_Threads", "OMP_Schedule", "Transformation"]
    if df.duplicated(chaves).any():
        raise ValueError("O CSV contém medições duplicadas para a mesma condição.")

    imagens = df["Image"].unique()
    grupos = df.groupby(chaves[1:], sort=False)["Repetition"].nunique()
    total_esperado = len(imagens) * len(THREADS) * len(schedules) * len(transformacoes)
    if len(grupos) != total_esperado or (grupos != len(REPETICOES)).any():
        raise ValueError("O CSV está incompleto: faltam imagens, condições ou repetições.")
    return df, schedules, transformacoes, len(imagens)


def calcular_aceleracoes(df):
    por_imagem = (
        df.groupby(["Num_Threads", "Image", "Transformation", "OMP_Schedule"], sort=False)["Time_ms"]
        .median()
        .reset_index(name="Mediana_ms")
    )
    chaves = ["Num_Threads", "Image", "Transformation"]
    referencia = por_imagem[por_imagem["OMP_Schedule"] == "static"][chaves + ["Mediana_ms"]]
    referencia = referencia.rename(columns={"Mediana_ms": "Mediana_estatica_ms"})
    por_imagem = por_imagem.merge(referencia, on=chaves, validate="many_to_one")
    por_imagem["Aceleracao"] = por_imagem["Mediana_estatica_ms"] / por_imagem["Mediana_ms"]

    # A média geométrica dá o mesmo peso a cada imagem, independentemente do
    # tamanho do arquivo ou do tempo absoluto da transformação.
    resumo = (
        por_imagem.groupby(["Num_Threads", "OMP_Schedule", "Transformation"], sort=False)["Aceleracao"]
        .agg(lambda valores: math.exp(np.log(valores).mean()))
        .reset_index()
    )
    return resumo


def criar_grafico(resumo, schedules, transformacoes, quantidade_imagens, threads, destino, cores, limite_y):
    dados = resumo[resumo["Num_Threads"] == threads].pivot(
        index="OMP_Schedule", columns="Transformation", values="Aceleracao"
    ).reindex(index=schedules, columns=transformacoes)
    if dados.isna().any().any():
        raise ValueError(f"Faltam barras para {threads} threads.")

    fig, ax = plt.subplots(figsize=(25, 11))
    posicoes = np.arange(len(schedules))
    largura = 0.88 / len(transformacoes)
    for indice, transformacao in enumerate(transformacoes):
        deslocamento = (indice - (len(transformacoes) - 1) / 2) * largura
        ax.bar(
            posicoes + deslocamento,
            dados[transformacao].to_numpy(),
            width=largura,
            color=cores[transformacao],
            label=NOMES_TRANSFORMACOES.get(transformacao, transformacao.replace("_", " ")),
        )

    rotulos = ["Estático" if s == "static" else f"Din. {ordem_schedule(s)[1]}" for s in schedules]
    ax.set_xticks(posicoes, rotulos, rotation=35, ha="right")
    ax.set_xlim(-0.6, len(schedules) - 0.4)
    ax.set_ylim(0, limite_y)
    ax.axhline(1.0, color="black", linestyle="--", linewidth=1.4, label="Referência estática (1×)")
    ax.set_title(f"Aceleração por transformação e escalonamento — {threads} threads", fontsize=19, weight="bold")
    ax.set_xlabel("Escalonamento (tamanho do chunk)", fontsize=13)
    ax.set_ylabel("Aceleração média geométrica vs. estático (×)", fontsize=13)
    ax.grid(axis="y", linestyle="--", alpha=0.35)
    ax.set_axisbelow(True)

    handles, labels = ax.get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", bbox_to_anchor=(0.5, 0.105), ncol=5,
               frameon=False, fontsize=10)
    fig.text(
        0.5, 0.025,
        f"Cada imagem: mediana de 5 execuções; aceleração = mediana estática ÷ mediana do escalonamento, "
        f"com {threads} threads.\n"
        f"Cada barra: média geométrica das acelerações das {quantidade_imagens} imagens. "
        "Acima de 1× indica ganho; abaixo de 1× indica perda.",
        ha="center", va="bottom", fontsize=10,
    )
    fig.tight_layout(rect=(0.02, 0.22, 0.98, 0.98))
    fig.savefig(destino, dpi=300)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description="Gera gráficos de aceleração por transformação.")
    parser.add_argument("csv", type=Path, help="CSV gerado por benchmark_transformacoes/run.sh")
    args = parser.parse_args()

    try:
        df, schedules, transformacoes, quantidade_imagens = carregar_e_validar(args.csv)
        resumo = calcular_aceleracoes(df)
        paleta = sns.color_palette("husl", len(transformacoes))
        cores = dict(zip(transformacoes, paleta))
        limite_y = max(1.1, float(resumo["Aceleracao"].max()) * 1.08)
        for threads in sorted(THREADS):
            destino = args.csv.parent / f"speedup_{threads}_threads.png"
            criar_grafico(resumo, schedules, transformacoes, quantidade_imagens,
                          threads, destino, cores, limite_y)
            print(f"Gráfico salvo: {destino}")
    except (OSError, ValueError, pd.errors.ParserError) as erro:
        parser.exit(1, f"Erro: {erro}\n")


if __name__ == "__main__":
    main()
