#!/usr/bin/env python3
"""Gera diagnosticos que relacionam speedup e metricas VTune por frame.

O CSV consolidado e lido em blocos. Somente linhas de tempo e frames ITT das
transformacoes sao mantidas em memoria; metricas globais da coleta nao entram
nos graficos porque incluem leitura e restauracao de imagens.
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Iterable, Sequence

os.environ.setdefault(
    "MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "inf01077-matplotlib")
)

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize
import numpy as np
import pandas as pd
import seaborn as sns


THREADS_ESPERADAS = {20, 40}
CHUNKS_ESPERADOS = {2**expoente for expoente in range(11)}

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
    "Gaussian_3x3": "Gaussiano 3x3",
    "Gaussian_5x5": "Gaussiano 5x5",
    "Gaussian_7x7": "Gaussiano 7x7",
    "Gaussian_9x9": "Gaussiano 9x9",
    "Gaussian_11x11": "Gaussiano 11x11",
    "Adaptive_Gaussian": "Gaussiano adaptativo",
}

COLUNAS_ORIGINAIS = [
    "Repetition",
    "Image",
    "Num_Threads",
    "OMP_Schedule",
    "Transformation",
    "Time_ms",
]

COLUNAS_VTUNE = [
    "Record_Type",
    "Report_Type",
    "Scope",
    "Collection_ID",
    "Num_Threads",
    "OMP_Schedule",
    "Transformation",
    "Image",
    "Frame_ID",
    "Time_ms",
    "frames__CPU_Time",
    "frames__CPU_Time_Effective_Time",
    "frames__CPU_Time_Effective_Time_Poor",
    "frames__CPU_Time_Effective_Time_Ok",
    "frames__CPU_Time_Effective_Time_Ideal",
    "frames__CPU_Time_Spin_Time",
    "frames__CPU_Time_Overhead_Time",
    "frames__Memory_Bound_Percent",
    "frames__Memory_Bound_L1_Bound_Percent",
    "frames__Memory_Bound_Store_Bound_Percent",
    "frames__CPI_Rate",
    "frames__Instructions_Retired",
    "frames__Average_CPU_Frequency",
]

CHAVES_FRAME = [
    "Collection_ID",
    "Num_Threads",
    "OMP_Schedule",
    "Transformation",
    "Frame_ID",
]

CHAVES_IMAGEM = ["Num_Threads", "OMP_Schedule", "Transformation", "Image"]
CHAVES_CONDICAO = ["Num_Threads", "OMP_Schedule", "Transformation"]

COLUNAS_SOMA = [
    "CPU_Time",
    "CPU_Time_Effective_Time",
    "CPU_Time_Effective_Time_Poor",
    "CPU_Time_Effective_Time_Ok",
    "CPU_Time_Effective_Time_Ideal",
    "CPU_Time_Spin_Time",
    "CPU_Time_Overhead_Time",
    "Instructions_Retired",
]

COLUNAS_PONDERADAS_CPU = [
    "Memory_Bound_Percent",
    "Memory_Bound_L1_Bound_Percent",
    "Memory_Bound_Store_Bound_Percent",
    "Average_CPU_Frequency",
]

ROTACOES = ["Rotate_CW", "Rotate_CCW"]
CASOS_SIMPLES = [
    "Grayscale",
    "Flip_Horizontal",
    "Flip_Vertical",
    "Adjust_Brightness",
    "Adjust_Contrast",
    "Negative",
]
CASOS_CONTRASTANTES = ["Zoom_In", "Gaussian_11x11", "Adaptive_Gaussian"]


class PlotError(RuntimeError):
    pass


def ordem_schedule(schedule: str) -> tuple[int, int]:
    if schedule == "static":
        return (0, 0)
    correspondencia = re.fullmatch(r"dynamic_(\d+)", schedule)
    if not correspondencia:
        raise PlotError(f"escalonamento invalido: {schedule}")
    return (1, int(correspondencia.group(1)))


def rotulo_schedule(schedule: str) -> str:
    return "Estático" if schedule == "static" else schedule.replace("dynamic_", "Din. ")


def media_geometrica(valores: Iterable[float]) -> float:
    array = np.asarray(list(valores), dtype=float)
    array = array[np.isfinite(array) & (array > 0)]
    return float(np.exp(np.log(array).mean())) if array.size else math.nan


def validar_cabecalho(path: Path, colunas: Sequence[str]) -> None:
    try:
        with path.open(newline="", encoding="utf-8") as arquivo:
            cabecalho = next(csv.reader(arquivo))
    except StopIteration as erro:
        raise PlotError(f"CSV vazio: {path}") from erro
    ausentes = sorted(set(colunas) - set(cabecalho))
    if ausentes:
        raise PlotError(f"colunas ausentes em {path}: {', '.join(ausentes)}")


def carregar_frames_vtune(path: Path, tamanho_bloco: int) -> tuple[pd.DataFrame, float]:
    validar_cabecalho(path, COLUNAS_VTUNE)
    tempos: list[pd.DataFrame] = []
    frames: list[pd.DataFrame] = []

    for bloco in pd.read_csv(
        path,
        usecols=COLUNAS_VTUNE,
        dtype=str,
        chunksize=tamanho_bloco,
        keep_default_na=False,
    ):
        linhas_tempo = bloco[bloco["Record_Type"].eq("timing")]
        if not linhas_tempo.empty:
            tempos.append(
                linhas_tempo[
                    CHAVES_FRAME + ["Image", "Time_ms"]
                ].copy()
            )

        linhas_frame = bloco[
            bloco["Record_Type"].eq("frame")
            & bloco["Report_Type"].eq("frames")
            & bloco["Scope"].eq("transformation_frame")
        ]
        if not linhas_frame.empty:
            colunas_frame = CHAVES_FRAME + [
                coluna for coluna in COLUNAS_VTUNE if coluna.startswith("frames__")
            ]
            frames.append(linhas_frame[colunas_frame].copy())

    if not tempos or not frames:
        raise PlotError("o CSV nao contem tempos e frames ITT de transformacao")

    tempos_df = pd.concat(tempos, ignore_index=True)
    frames_df = pd.concat(frames, ignore_index=True)
    if tempos_df.duplicated(CHAVES_FRAME).any():
        raise PlotError("ha Frame_ID duplicado nas linhas de tempo")
    if frames_df.duplicated(CHAVES_FRAME).any():
        raise PlotError("ha Frame_ID duplicado no relatorio de frames")

    tempos_df["Num_Threads"] = pd.to_numeric(
        tempos_df["Num_Threads"], errors="raise", downcast="integer"
    )
    tempos_df["Time_ms"] = pd.to_numeric(tempos_df["Time_ms"], errors="raise")
    if (~np.isfinite(tempos_df["Time_ms"]) | (tempos_df["Time_ms"] <= 0)).any():
        raise PlotError("o CSV contem tempos invalidos")

    frames_df["Num_Threads"] = pd.to_numeric(
        frames_df["Num_Threads"], errors="raise", downcast="integer"
    )
    frames_df = frames_df.rename(
        columns={coluna: coluna.removeprefix("frames__") for coluna in frames_df}
    )
    metricas_frame = [
        coluna for coluna in frames_df if coluna not in CHAVES_FRAME
    ]
    for coluna in metricas_frame:
        frames_df[coluna] = pd.to_numeric(frames_df[coluna], errors="coerce")

    combinado = tempos_df.merge(
        frames_df,
        on=CHAVES_FRAME,
        how="left",
        validate="one_to_one",
    )
    cobertura = float(combinado["CPU_Time"].notna().mean())
    if cobertura < 0.90:
        raise PlotError(
            f"somente {cobertura:.1%} dos tempos possuem metricas de frame VTune"
        )
    return combinado, cobertura


def soma_com_minimo(grupo: pd.core.groupby.DataFrameGroupBy, coluna: str) -> pd.Series:
    return grupo[coluna].sum(min_count=1)


def agregar_por_imagem(frames: pd.DataFrame) -> pd.DataFrame:
    grupo = frames.groupby(CHAVES_IMAGEM, sort=False, observed=True)
    agregado = grupo["Time_ms"].agg(
        Mediana_ms="median", Media_ms="mean", Tempo_total_ms="sum", Chamadas="size"
    )
    agregado["Frames_amostrados"] = grupo["CPU_Time"].count()

    for coluna in COLUNAS_SOMA:
        agregado[coluna] = soma_com_minimo(grupo, coluna)

    for coluna in COLUNAS_PONDERADAS_CPU:
        numerador = (frames[coluna] * frames["CPU_Time"]).groupby(
            [frames[chave] for chave in CHAVES_IMAGEM], sort=False, observed=True
        ).sum(min_count=1)
        denominador = frames["CPU_Time"].where(frames[coluna].notna()).groupby(
            [frames[chave] for chave in CHAVES_IMAGEM], sort=False, observed=True
        ).sum(min_count=1)
        agregado[coluna] = numerador / denominador

    # CPI e ponderado por instrucoes, pois CPI = ciclos / instrucoes.
    numerador_cpi = (frames["CPI_Rate"] * frames["Instructions_Retired"]).groupby(
        [frames[chave] for chave in CHAVES_IMAGEM], sort=False, observed=True
    ).sum(min_count=1)
    denominador_cpi = frames["Instructions_Retired"].where(
        frames["CPI_Rate"].notna()
    ).groupby(
        [frames[chave] for chave in CHAVES_IMAGEM], sort=False, observed=True
    ).sum(min_count=1)
    agregado["CPI_Rate"] = numerador_cpi / denominador_cpi

    agregado = agregado.reset_index()
    agregado["CPU_Time_por_chamada"] = agregado["CPU_Time"] / agregado["Chamadas"]
    agregado["Instrucoes_por_chamada"] = (
        agregado["Instructions_Retired"] / agregado["Chamadas"]
    )
    agregado["Nucleos_ativos"] = (
        agregado["CPU_Time"] * 1000.0 / agregado["Tempo_total_ms"]
    )
    agregado["Baixa_utilizacao_Percent"] = (
        100.0
        * agregado["CPU_Time_Effective_Time_Poor"]
        / agregado["CPU_Time_Effective_Time"]
    )
    agregado["Cobertura_Percent"] = (
        100.0 * agregado["Frames_amostrados"] / agregado["Chamadas"]
    )
    return agregado


def razao_segura(numerador: pd.Series, denominador: pd.Series) -> pd.Series:
    resultado = numerador / denominador
    return resultado.where(np.isfinite(resultado) & (resultado > 0))


def resumir_condicoes(por_imagem: pd.DataFrame) -> pd.DataFrame:
    chaves_referencia = ["Num_Threads", "Transformation", "Image"]
    metricas_referencia = [
        "Mediana_ms",
        "Media_ms",
        "CPU_Time_por_chamada",
        "Instrucoes_por_chamada",
        "Nucleos_ativos",
        "CPI_Rate",
        "Average_CPU_Frequency",
        "Baixa_utilizacao_Percent",
        "Memory_Bound_Percent",
        "Memory_Bound_L1_Bound_Percent",
        "Memory_Bound_Store_Bound_Percent",
    ]
    referencia = por_imagem[por_imagem["OMP_Schedule"].eq("static")][
        chaves_referencia + metricas_referencia
    ].copy()
    if referencia.duplicated(chaves_referencia).any():
        raise PlotError("referencia estatica duplicada")
    referencia = referencia.rename(
        columns={metrica: f"Estatico__{metrica}" for metrica in metricas_referencia}
    )
    dados = por_imagem.merge(
        referencia, on=chaves_referencia, how="left", validate="many_to_one"
    )
    if dados["Estatico__Media_ms"].isna().any():
        raise PlotError("faltam referencias estaticas para algumas imagens")

    dados["VTune_Speedup_Mediana"] = razao_segura(
        dados["Estatico__Mediana_ms"], dados["Mediana_ms"]
    )
    dados["VTune_Speedup_Perfil"] = razao_segura(
        dados["Estatico__Media_ms"], dados["Media_ms"]
    )
    dados["Fator_Trabalho_CPU"] = razao_segura(
        dados["Estatico__CPU_Time_por_chamada"], dados["CPU_Time_por_chamada"]
    )
    dados["Fator_Paralelismo"] = razao_segura(
        dados["Nucleos_ativos"], dados["Estatico__Nucleos_ativos"]
    )
    dados["Fator_Instrucoes"] = razao_segura(
        dados["Estatico__Instrucoes_por_chamada"], dados["Instrucoes_por_chamada"]
    )
    dados["Fator_CPI"] = razao_segura(
        dados["Estatico__CPI_Rate"], dados["CPI_Rate"]
    )
    dados["Fator_Frequencia"] = razao_segura(
        dados["Average_CPU_Frequency"], dados["Estatico__Average_CPU_Frequency"]
    )
    dados["Melhora_Baixa_Utilizacao_pp"] = (
        dados["Estatico__Baixa_utilizacao_Percent"]
        - dados["Baixa_utilizacao_Percent"]
    )
    dados["Melhora_Memory_Bound_pp"] = (
        dados["Estatico__Memory_Bound_Percent"] - dados["Memory_Bound_Percent"]
    )
    dados["Melhora_L1_Bound_pp"] = (
        dados["Estatico__Memory_Bound_L1_Bound_Percent"]
        - dados["Memory_Bound_L1_Bound_Percent"]
    )
    dados["Melhora_Store_Bound_pp"] = (
        dados["Estatico__Memory_Bound_Store_Bound_Percent"]
        - dados["Memory_Bound_Store_Bound_Percent"]
    )

    validos = dados[
        ["VTune_Speedup_Perfil", "Fator_Trabalho_CPU", "Fator_Paralelismo"]
    ].dropna()
    erro = np.abs(
        np.log(
            validos["VTune_Speedup_Perfil"]
            / (validos["Fator_Trabalho_CPU"] * validos["Fator_Paralelismo"])
        )
    )
    if not erro.empty and float(erro.max()) > 1e-9:
        raise PlotError("a decomposicao trabalho CPU x paralelismo nao fechou")

    razoes = [
        "VTune_Speedup_Mediana",
        "VTune_Speedup_Perfil",
        "Fator_Trabalho_CPU",
        "Fator_Paralelismo",
        "Fator_Instrucoes",
        "Fator_CPI",
        "Fator_Frequencia",
    ]
    medias = [
        "Nucleos_ativos",
        "Baixa_utilizacao_Percent",
        "Memory_Bound_Percent",
        "Memory_Bound_L1_Bound_Percent",
        "Memory_Bound_Store_Bound_Percent",
        "Cobertura_Percent",
        "Melhora_Baixa_Utilizacao_pp",
        "Melhora_Memory_Bound_pp",
        "Melhora_L1_Bound_pp",
        "Melhora_Store_Bound_pp",
    ]
    grupo = dados.groupby(CHAVES_CONDICAO, sort=False, observed=True)
    resumo = grupo.size().rename("Imagens").reset_index()
    for coluna in razoes:
        valores = grupo[coluna].agg(media_geometrica).rename(coluna).reset_index()
        resumo = resumo.merge(valores, on=CHAVES_CONDICAO, validate="one_to_one")
    for coluna in medias:
        valores = grupo[coluna].mean().rename(coluna).reset_index()
        resumo = resumo.merge(valores, on=CHAVES_CONDICAO, validate="one_to_one")
    resumo["Erro_Decomposicao"] = np.abs(
        resumo["VTune_Speedup_Perfil"]
        - resumo["Fator_Trabalho_CPU"] * resumo["Fator_Paralelismo"]
    )
    return resumo


def carregar_speedup_original(path: Path) -> tuple[pd.DataFrame, list[str]]:
    validar_cabecalho(path, COLUNAS_ORIGINAIS)
    dados = pd.read_csv(path)
    if list(dados.columns) != COLUNAS_ORIGINAIS:
        raise PlotError("o CSV original possui colunas inesperadas")
    transformacoes = dados["Transformation"].drop_duplicates().tolist()
    dados["Time_ms"] = pd.to_numeric(dados["Time_ms"], errors="raise")
    dados["Num_Threads"] = pd.to_numeric(dados["Num_Threads"], errors="raise")
    if (~np.isfinite(dados["Time_ms"]) | (dados["Time_ms"] <= 0)).any():
        raise PlotError("o benchmark original contem tempos invalidos")

    por_imagem = (
        dados.groupby(
            ["Num_Threads", "Image", "Transformation", "OMP_Schedule"],
            sort=False,
            observed=True,
        )["Time_ms"]
        .median()
        .reset_index(name="Mediana_ms")
    )
    referencia = por_imagem[por_imagem["OMP_Schedule"].eq("static")][
        ["Num_Threads", "Image", "Transformation", "Mediana_ms"]
    ].rename(columns={"Mediana_ms": "Mediana_estatica_ms"})
    por_imagem = por_imagem.merge(
        referencia,
        on=["Num_Threads", "Image", "Transformation"],
        validate="many_to_one",
    )
    por_imagem["Speedup_Original"] = (
        por_imagem["Mediana_estatica_ms"] / por_imagem["Mediana_ms"]
    )
    original = (
        por_imagem.groupby(CHAVES_CONDICAO, sort=False, observed=True)[
            "Speedup_Original"
        ]
        .agg(media_geometrica)
        .reset_index()
    )
    return original, transformacoes


def validar_campanha(
    resumo: pd.DataFrame, transformacoes: Sequence[str]
) -> tuple[list[str], list[int]]:
    threads = sorted(int(valor) for valor in resumo["Num_Threads"].unique())
    schedules = sorted(resumo["OMP_Schedule"].unique(), key=ordem_schedule)
    esperados = {"static", *(f"dynamic_{chunk}" for chunk in CHUNKS_ESPERADOS)}
    if set(threads) != THREADS_ESPERADAS:
        raise PlotError(f"threads encontradas: {threads}; esperado: [20, 40]")
    if set(schedules) != esperados:
        raise PlotError("faltam schedules entre static e dynamic_1..dynamic_1024")
    if len(transformacoes) != 18 or set(transformacoes) != set(
        resumo["Transformation"].unique()
    ):
        raise PlotError("a campanha deve conter as mesmas 18 transformacoes")
    esperado = len(threads) * len(schedules) * len(transformacoes)
    if len(resumo) != esperado:
        raise PlotError(f"esperadas {esperado} condicoes; encontradas {len(resumo)}")
    return schedules, threads


def preparar_pivo(
    dados: pd.DataFrame,
    coluna: str,
    schedules: Sequence[str],
    transformacoes: Sequence[str],
) -> pd.DataFrame:
    return (
        dados.pivot(index="Transformation", columns="OMP_Schedule", values=coluna)
        .reindex(index=transformacoes, columns=schedules)
        .rename(index=NOMES_TRANSFORMACOES)
    )


def heatmap_fator(
    ax: plt.Axes,
    valores: pd.DataFrame,
    titulo: str,
    mostrar_y: bool,
) -> None:
    log2 = np.log2(valores.astype(float)).clip(-2.0, 2.0)
    sns.heatmap(
        log2,
        ax=ax,
        cmap="RdBu_r",
        center=0,
        vmin=-2,
        vmax=2,
        xticklabels=[rotulo_schedule(s).replace("Din. ", "") for s in valores.columns],
        yticklabels=mostrar_y,
        cbar_kws={"label": "log2(fator)", "ticks": [-2, -1, 0, 1, 2]},
    )
    barra = ax.collections[0].colorbar
    barra.set_ticklabels(["0,25x", "0,5x", "1x", "2x", "4x"])
    ax.set_title(titulo, fontsize=12, weight="bold")
    ax.set_xlabel("Chunk dinâmico")
    ax.set_ylabel("")
    ax.tick_params(axis="x", rotation=45, labelsize=8)
    ax.tick_params(axis="y", rotation=0, labelsize=8)


def heatmap_delta(
    ax: plt.Axes,
    valores: pd.DataFrame,
    titulo: str,
    mostrar_y: bool,
) -> None:
    limite = float(np.nanpercentile(np.abs(valores.to_numpy(dtype=float)), 95))
    limite = max(limite, 1.0)
    sns.heatmap(
        valores,
        ax=ax,
        cmap="RdBu_r",
        center=0,
        vmin=-limite,
        vmax=limite,
        xticklabels=[rotulo_schedule(s).replace("Din. ", "") for s in valores.columns],
        yticklabels=mostrar_y,
        cbar_kws={"label": "pontos percentuais"},
    )
    ax.set_title(titulo, fontsize=12, weight="bold")
    ax.set_xlabel("Chunk dinâmico")
    ax.set_ylabel("")
    ax.tick_params(axis="x", rotation=45, labelsize=8)
    ax.tick_params(axis="y", rotation=0, labelsize=8)


def plotar_diagnostico(
    resumo: pd.DataFrame,
    schedules: Sequence[str],
    transformacoes: Sequence[str],
    threads: int,
    destino: Path,
) -> None:
    dados = resumo[resumo["Num_Threads"].eq(threads)]
    dinamicos = [schedule for schedule in schedules if schedule != "static"]
    paineis = [
        ("Speedup_Original", "Speedup original", "fator"),
        ("VTune_Speedup_Perfil", "Speedup durante o VTune", "fator"),
        ("Fator_Trabalho_CPU", "Fator de trabalho CPU", "fator"),
        ("Fator_Paralelismo", "Fator de paralelismo", "fator"),
        ("Fator_Instrucoes", "Fator de instruções", "fator"),
        ("Fator_CPI", "Fator de CPI", "fator"),
        (
            "Melhora_Baixa_Utilizacao_pp",
            "Redução do tempo em baixa utilização",
            "delta",
        ),
        ("Melhora_Memory_Bound_pp", "Redução de Memory Bound", "delta"),
    ]

    fig, eixos = plt.subplots(2, 4, figsize=(31, 20), constrained_layout=False)
    for indice, (coluna, titulo, tipo) in enumerate(paineis):
        eixo = eixos.flat[indice]
        valores = preparar_pivo(dados, coluna, dinamicos, transformacoes)
        mostrar_y = indice in {0, 4}
        if tipo == "fator":
            heatmap_fator(eixo, valores, titulo, mostrar_y)
        else:
            heatmap_delta(eixo, valores, titulo, mostrar_y)

    fig.suptitle(
        f"Diagnóstico VTune por transformação e schedule — {threads} threads",
        fontsize=20,
        weight="bold",
        y=0.995,
    )
    fig.text(
        0.5,
        0.012,
        "Valores por imagem e normalizados pelo static; fatores usam média geométrica entre imagens. "
        "Speedup VTune = fator de trabalho CPU x fator de paralelismo.\n"
        "Valores positivos nas duas últimas matrizes indicam menos tempo em baixa utilização ou menos Memory Bound. "
        "Métricas usam apenas frames ITT das transformações.",
        ha="center",
        va="bottom",
        fontsize=10,
    )
    fig.tight_layout(rect=(0.015, 0.045, 0.995, 0.975), h_pad=3.0, w_pad=2.0)
    fig.savefig(destino, dpi=220)
    plt.close(fig)


def plotar_reproducao(resumo: pd.DataFrame, destino: Path) -> None:
    fig, eixos = plt.subplots(1, 2, figsize=(16, 7), sharex=True, sharey=True)
    dinamicos = resumo[~resumo["OMP_Schedule"].eq("static")].copy()
    dinamicos["Chunk"] = dinamicos["OMP_Schedule"].str.removeprefix("dynamic_").astype(int)
    todos = np.concatenate(
        [dinamicos["Speedup_Original"], dinamicos["VTune_Speedup_Mediana"]]
    )
    minimo = max(0.1, float(np.nanmin(todos)) * 0.85)
    maximo = float(np.nanmax(todos)) * 1.15
    norma = Normalize(vmin=0, vmax=10)
    mapa = plt.get_cmap("viridis")

    for eixo, threads in zip(eixos, sorted(THREADS_ESPERADAS)):
        dados = dinamicos[dinamicos["Num_Threads"].eq(threads)].copy()
        cores = mapa(norma(np.log2(dados["Chunk"])))
        eixo.scatter(
            dados["Speedup_Original"],
            dados["VTune_Speedup_Mediana"],
            c=cores,
            s=34,
            alpha=0.78,
            edgecolors="none",
        )
        rotacoes = dados[dados["Transformation"].isin(ROTACOES)]
        eixo.scatter(
            rotacoes["Speedup_Original"],
            rotacoes["VTune_Speedup_Mediana"],
            facecolors="none",
            edgecolors="black",
            linewidths=1.1,
            s=78,
            label="Rotações",
        )
        eixo.plot([minimo, maximo], [minimo, maximo], "--", color="0.25", linewidth=1)
        eixo.axvline(1, color="0.7", linewidth=0.8)
        eixo.axhline(1, color="0.7", linewidth=0.8)
        eixo.set_xscale("log", base=2)
        eixo.set_yscale("log", base=2)
        eixo.set_xlim(minimo, maximo)
        eixo.set_ylim(minimo, maximo)
        eixo.grid(True, which="both", linestyle="--", alpha=0.25)
        eixo.set_title(f"{threads} threads", fontsize=14, weight="bold")
        eixo.set_xlabel("Speedup no benchmark original")
        eixo.set_ylabel("Speedup mediano durante o VTune")
        eixo.legend(loc="lower right")

        dados["Divergencia"] = np.abs(
            np.log(dados["VTune_Speedup_Mediana"] / dados["Speedup_Original"])
        )
        for indice, linha in enumerate(
            dados.nlargest(4, "Divergencia").itertuples()
        ):
            abreviado = NOMES_TRANSFORMACOES.get(
                linha.Transformation, linha.Transformation
            ).replace("Espelhamento ", "Esp. ")
            deslocamento_x = -5 if linha.Speedup_Original > 1.25 else 5
            deslocamento_y = (-24, -8, 8, 24)[indice]
            eixo.annotate(
                f"{abreviado}\n{rotulo_schedule(linha.OMP_Schedule)}",
                (linha.Speedup_Original, linha.VTune_Speedup_Mediana),
                xytext=(deslocamento_x, deslocamento_y),
                textcoords="offset points",
                fontsize=7,
                ha="right" if deslocamento_x < 0 else "left",
                va="top" if deslocamento_y < 0 else "bottom",
                arrowprops={"arrowstyle": "-", "color": "0.45", "linewidth": 0.5},
            )

        correlacao = dados["Speedup_Original"].corr(
            dados["VTune_Speedup_Mediana"], method="spearman"
        )
        proximos = np.mean(
            np.abs(
                np.log(dados["VTune_Speedup_Mediana"] / dados["Speedup_Original"])
            )
            <= np.log(1.35)
        )
        eixo.text(
            0.03,
            0.97,
            f"Spearman = {correlacao:.2f}\nDentro de 35% = {proximos:.0%}",
            transform=eixo.transAxes,
            va="top",
            fontsize=9,
            bbox={"facecolor": "white", "alpha": 0.8, "edgecolor": "0.8"},
        )

    escala = plt.cm.ScalarMappable(norm=norma, cmap=mapa)
    escala.set_array([])
    fig.subplots_adjust(left=0.07, right=0.88, bottom=0.11, top=0.88, wspace=0.16)
    eixo_barra = fig.add_axes([0.90, 0.16, 0.018, 0.66])
    barra = fig.colorbar(escala, cax=eixo_barra)
    barra.set_ticks(range(11))
    barra.set_ticklabels([str(2**expoente) for expoente in range(11)])
    barra.set_label("Chunk dinâmico")
    fig.suptitle(
        "O perfil VTune reproduz o comportamento do benchmark original?",
        fontsize=18,
        weight="bold",
    )
    fig.text(
        0.5,
        0.015,
        "Pontos na diagonal mantiveram o mesmo speedup. Distância da diagonal indica que a instrumentação "
        "ou a variação entre execuções alterou o comportamento; esses casos exigem cautela causal.",
        ha="center",
        fontsize=10,
    )
    fig.savefig(destino, dpi=240)
    plt.close(fig)


def configurar_eixo_schedule(ax: plt.Axes, schedules: Sequence[str]) -> None:
    ax.set_xticks(range(len(schedules)), [rotulo_schedule(s) for s in schedules])
    ax.tick_params(axis="x", rotation=45, labelsize=8)
    ax.grid(axis="y", linestyle="--", alpha=0.3)


def plotar_speedup_barras(
    resumo: pd.DataFrame,
    schedules: Sequence[str],
    transformacoes: Sequence[str],
    quantidade_imagens: int,
    threads: int,
    destino: Path,
    cores: dict[str, tuple[float, ...]],
    limite_y: float,
) -> None:
    """Reproduz o gráfico de barras do benchmark sem VTune."""
    dados = (
        resumo[resumo["Num_Threads"].eq(threads)]
        .pivot(
            index="OMP_Schedule",
            columns="Transformation",
            values="VTune_Speedup_Mediana",
        )
        .reindex(index=schedules, columns=transformacoes)
    )
    if dados.isna().any().any():
        raise PlotError(f"faltam barras de speedup VTune para {threads} threads")

    fig, eixo = plt.subplots(figsize=(25, 11))
    posicoes = np.arange(len(schedules))
    largura = 0.88 / len(transformacoes)
    for indice, transformacao in enumerate(transformacoes):
        deslocamento = (indice - (len(transformacoes) - 1) / 2) * largura
        eixo.bar(
            posicoes + deslocamento,
            dados[transformacao].to_numpy(),
            width=largura,
            color=cores[transformacao],
            label=NOMES_TRANSFORMACOES.get(
                transformacao, transformacao.replace("_", " ")
            ),
        )

    eixo.set_xticks(
        posicoes,
        [rotulo_schedule(schedule) for schedule in schedules],
        rotation=35,
        ha="right",
    )
    eixo.set_xlim(-0.6, len(schedules) - 0.4)
    eixo.set_ylim(0, limite_y)
    eixo.axhline(
        1.0,
        color="black",
        linestyle="--",
        linewidth=1.4,
        label="Referência estática (1×)",
    )
    eixo.set_title(
        f"Aceleração por transformação e escalonamento sob VTune — {threads} threads",
        fontsize=19,
        weight="bold",
    )
    eixo.set_xlabel("Escalonamento (tamanho do chunk)", fontsize=13)
    eixo.set_ylabel("Aceleração média geométrica vs. estático (×)", fontsize=13)
    eixo.grid(axis="y", linestyle="--", alpha=0.35)
    eixo.set_axisbelow(True)

    handles, labels = eixo.get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        loc="lower center",
        bbox_to_anchor=(0.5, 0.105),
        ncol=5,
        frameon=False,
        fontsize=10,
    )
    fig.text(
        0.5,
        0.025,
        "Cada imagem: mediana das repetições internas da coleta VTune; aceleração = "
        f"mediana estática ÷ mediana do escalonamento, com {threads} threads.\n"
        f"Cada barra: média geométrica das acelerações das {quantidade_imagens} imagens. "
        "Acima de 1× indica ganho; abaixo de 1× indica perda.",
        ha="center",
        va="bottom",
        fontsize=10,
    )
    fig.tight_layout(rect=(0.02, 0.22, 0.98, 0.98))
    fig.savefig(destino, dpi=300)
    plt.close(fig)


def plotar_rotacoes(
    resumo: pd.DataFrame, schedules: Sequence[str], threads: int, destino: Path
) -> None:
    dados_threads = resumo[resumo["Num_Threads"].eq(threads)]
    fig, eixos = plt.subplots(4, 2, figsize=(18, 17), sharex="col")

    for coluna, transformacao in enumerate(ROTACOES):
        dados = (
            dados_threads[dados_threads["Transformation"].eq(transformacao)]
            .set_index("OMP_Schedule")
            .reindex(schedules)
        )
        x = np.arange(len(schedules))

        eixo = eixos[0, coluna]
        eixo.plot(x, dados["Speedup_Original"], "o-", label="Benchmark original")
        eixo.plot(x, dados["VTune_Speedup_Mediana"], "s-", label="VTune (mediana)")
        eixo.axhline(1, color="black", linestyle="--", linewidth=1)
        eixo.set_ylabel("Speedup vs. static")
        eixo.set_title(NOMES_TRANSFORMACOES[transformacao], fontsize=14, weight="bold")
        eixo.legend(fontsize=9)
        eixo.grid(axis="y", linestyle="--", alpha=0.3)

        eixo = eixos[1, coluna]
        eixo.plot(x, dados["VTune_Speedup_Perfil"], "o-", label="Speedup VTune")
        eixo.plot(x, dados["Fator_Trabalho_CPU"], "s-", label="Trabalho CPU")
        eixo.plot(x, dados["Fator_Paralelismo"], "^-", label="Paralelismo")
        eixo.axhline(1, color="black", linestyle="--", linewidth=1)
        eixo.set_yscale("log", base=2)
        eixo.set_ylabel("Fator (escala log2)")
        eixo.legend(fontsize=8, ncol=3)
        eixo.grid(axis="y", which="both", linestyle="--", alpha=0.3)

        eixo = eixos[2, coluna]
        linha_nucleos = eixo.plot(
            x, dados["Nucleos_ativos"], "o-", color="#2166ac", label="Núcleos ativos"
        )
        eixo.axhline(threads, color="#2166ac", linestyle=":", linewidth=1)
        eixo.set_ylim(0, threads * 1.12)
        eixo.set_ylabel("Núcleos lógicos ativos")
        outro = eixo.twinx()
        linha_pobre = outro.plot(
            x,
            dados["Baixa_utilizacao_Percent"],
            "s--",
            color="#b2182b",
            label="Baixa utilização",
        )
        outro.set_ylim(0, 105)
        outro.set_ylabel("Tempo em baixa utilização (%)", color="#b2182b")
        eixo.legend(
            linha_nucleos + linha_pobre,
            ["Núcleos ativos", "Baixa utilização"],
            fontsize=8,
        )
        eixo.grid(axis="y", linestyle="--", alpha=0.25)

        eixo = eixos[3, coluna]
        eixo.plot(x, dados["Fator_Instrucoes"], "o-", label="Fator de instruções")
        eixo.plot(x, dados["Fator_CPI"], "s-", label="Fator de CPI")
        eixo.plot(x, dados["Fator_Frequencia"], "^-", label="Fator de frequência")
        eixo.axhline(1, color="black", linestyle="--", linewidth=1)
        eixo.set_yscale("log", base=2)
        eixo.set_ylabel("Fator vs. static")
        outro = eixo.twinx()
        linha_memoria = outro.plot(
            x,
            dados["Memory_Bound_Percent"],
            "D--",
            color="#1b7837",
            label="Memory Bound",
        )
        outro.set_ylabel("Memory Bound (%)", color="#1b7837")
        linhas, rotulos = eixo.get_legend_handles_labels()
        eixo.legend(linhas + linha_memoria, rotulos + ["Memory Bound"], fontsize=8, ncol=2)
        configurar_eixo_schedule(eixo, schedules)

    fig.suptitle(
        f"Estudo das rotações com VTune — {threads} threads",
        fontsize=19,
        weight="bold",
    )
    fig.text(
        0.5,
        0.012,
        "Trabalho CPU x paralelismo decompõe o speedup medido durante o VTune. "
        "Chunks grandes reduzem o número de threads que recebem linhas; isso pode reduzir contenção, "
        "mas também aumenta o tempo em baixa utilização.",
        ha="center",
        fontsize=10,
    )
    fig.tight_layout(rect=(0.02, 0.035, 0.98, 0.965), h_pad=2.4, w_pad=2.0)
    fig.savefig(destino, dpi=240)
    plt.close(fig)


def plotar_casos_simples(
    resumo: pd.DataFrame, schedules: Sequence[str], threads: int, destino: Path
) -> None:
    fig, eixos = plt.subplots(2, 3, figsize=(22, 11), sharex=True, sharey=True)
    dados_threads = resumo[resumo["Num_Threads"].eq(threads)]
    x = np.arange(len(schedules))
    for eixo, transformacao in zip(eixos.flat, CASOS_SIMPLES):
        dados = (
            dados_threads[dados_threads["Transformation"].eq(transformacao)]
            .set_index("OMP_Schedule")
            .reindex(schedules)
        )
        eixo.plot(x, dados["Speedup_Original"], "o-", label="Speedup original")
        eixo.plot(x, dados["VTune_Speedup_Perfil"], "s-", label="Speedup VTune")
        eixo.plot(x, dados["Fator_Trabalho_CPU"], "^-", label="Trabalho CPU")
        eixo.plot(x, dados["Fator_Paralelismo"], "D-", label="Paralelismo")
        eixo.axhline(1, color="black", linestyle="--", linewidth=1)
        eixo.set_title(NOMES_TRANSFORMACOES[transformacao], weight="bold")
        eixo.set_ylabel("Fator vs. static")
        configurar_eixo_schedule(eixo, schedules)
    handles, labels = eixos[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=4, frameon=False)
    fig.suptitle(
        f"Transformações com custo quase uniforme por pixel — {threads} threads",
        fontsize=18,
        weight="bold",
    )
    fig.text(
        0.5,
        0.045,
        "Fator acima de 1 indica melhora. O ganho pode vir de menos trabalho CPU, maior paralelismo efetivo, ou ambos.",
        ha="center",
        fontsize=10,
    )
    fig.tight_layout(rect=(0.02, 0.10, 0.98, 0.94), h_pad=2.2)
    fig.savefig(destino, dpi=240)
    plt.close(fig)


def plotar_casos_contrastantes(
    resumo: pd.DataFrame, schedules: Sequence[str], threads: int, destino: Path
) -> None:
    fig, eixos = plt.subplots(3, 3, figsize=(22, 15), sharex="col")
    dados_threads = resumo[resumo["Num_Threads"].eq(threads)]
    x = np.arange(len(schedules))

    for coluna, transformacao in enumerate(CASOS_CONTRASTANTES):
        dados = (
            dados_threads[dados_threads["Transformation"].eq(transformacao)]
            .set_index("OMP_Schedule")
            .reindex(schedules)
        )

        eixo = eixos[0, coluna]
        eixo.plot(x, dados["Speedup_Original"], "o-", label="Speedup original")
        eixo.plot(x, dados["VTune_Speedup_Perfil"], "s-", label="Speedup VTune")
        eixo.axhline(1, color="black", linestyle="--", linewidth=1)
        eixo.set_title(NOMES_TRANSFORMACOES[transformacao], weight="bold", fontsize=13)
        eixo.set_ylabel("Speedup vs. static")
        eixo.grid(axis="y", linestyle="--", alpha=0.3)

        eixo = eixos[1, coluna]
        eixo.plot(x, dados["Fator_Trabalho_CPU"], "o-", label="Trabalho CPU")
        eixo.plot(x, dados["Fator_Paralelismo"], "s-", label="Paralelismo")
        eixo.plot(x, dados["VTune_Speedup_Perfil"], "^-", label="Produto / speedup")
        eixo.axhline(1, color="black", linestyle="--", linewidth=1)
        eixo.set_yscale("log", base=2)
        eixo.set_ylabel("Fator (log2)")
        eixo.grid(axis="y", which="both", linestyle="--", alpha=0.3)

        eixo = eixos[2, coluna]
        eixo.plot(x, dados["Fator_Instrucoes"], "o-", label="Instruções")
        eixo.plot(x, dados["Fator_CPI"], "s-", label="CPI")
        eixo.plot(x, dados["Fator_Frequencia"], "^-", label="Frequência")
        eixo.axhline(1, color="black", linestyle="--", linewidth=1)
        eixo.set_yscale("log", base=2)
        eixo.set_ylabel("Fator vs. static")
        outro = eixo.twinx()
        linha_memoria = outro.plot(
            x,
            dados["Memory_Bound_Percent"],
            "D--",
            color="#1b7837",
            label="Memory Bound",
        )
        outro.set_ylabel("Memory Bound (%)", color="#1b7837")
        configurar_eixo_schedule(eixo, schedules)

        if coluna == 0:
            eixos[0, coluna].legend(fontsize=8)
            eixos[1, coluna].legend(fontsize=8)
            linhas, rotulos = eixo.get_legend_handles_labels()
            eixo.legend(
                linhas + linha_memoria,
                rotulos + ["Memory Bound"],
                fontsize=8,
            )

    fig.suptitle(
        f"Três mecanismos contrastantes de escalonamento — {threads} threads",
        fontsize=19,
        weight="bold",
    )
    fig.text(
        0.5,
        0.012,
        "Ampliação: chunks pequenos elevam CPI e Memory Bound. Gaussiano 11x11: chunks grandes reduzem trabalho CPU, "
        "mas perdem mais paralelismo. Adaptativo: chunks pequenos melhoram o balanceamento de carga.",
        ha="center",
        fontsize=10,
    )
    fig.tight_layout(rect=(0.02, 0.04, 0.98, 0.965), h_pad=2.2, w_pad=2.5)
    fig.savefig(destino, dpi=240)
    plt.close(fig)


def salvar_relatorio_texto(
    resumo: pd.DataFrame, cobertura: float, destino: Path
) -> None:
    linhas = [
        "Resumo da análise VTune",
        "=========================",
        "",
        f"Cobertura global dos frames: {cobertura:.2%}",
        f"Condições analisadas: {len(resumo)}",
        "",
        "Aceleração VTune = fator de trabalho CPU x fator de paralelismo.",
        "Fator de trabalho CPU > 1: menos CPU-time para o mesmo conjunto de chamadas.",
        "Fator de paralelismo > 1: mais núcleos ativos em média.",
        "",
        "Reprodução do benchmark original:",
    ]
    dinamicos = resumo[~resumo["OMP_Schedule"].eq("static")]
    for threads in sorted(THREADS_ESPERADAS):
        dados = dinamicos[dinamicos["Num_Threads"].eq(threads)]
        correlacao = dados["Speedup_Original"].corr(
            dados["VTune_Speedup_Mediana"], method="spearman"
        )
        proximos = np.mean(
            np.abs(
                np.log(dados["VTune_Speedup_Mediana"] / dados["Speedup_Original"])
            )
            <= np.log(1.35)
        )
        linhas.append(
            f"- {threads} threads: Spearman={correlacao:.3f}; dentro de 35%={proximos:.1%}."
        )

    linhas.extend(["", "Mecanismos gerais observados nos frames:"])
    for threads in sorted(THREADS_ESPERADAS):
        dados = dinamicos[dinamicos["Num_Threads"].eq(threads)].dropna(
            subset=[
                "VTune_Speedup_Perfil",
                "Fator_Trabalho_CPU",
                "Fator_Paralelismo",
                "Melhora_Baixa_Utilizacao_pp",
            ]
        )
        log_speedup = np.log(dados["VTune_Speedup_Perfil"])
        correlacao_trabalho = log_speedup.corr(
            np.log(dados["Fator_Trabalho_CPU"])
        )
        correlacao_paralelismo = log_speedup.corr(
            np.log(dados["Fator_Paralelismo"])
        )
        correlacao_baixa_utilizacao = log_speedup.corr(
            dados["Melhora_Baixa_Utilizacao_pp"]
        )
        linhas.append(
            f"- {threads} threads: correlação do log(speedup) com trabalho CPU="
            f"{correlacao_trabalho:.3f}, com paralelismo={correlacao_paralelismo:.3f}; "
            f"correlação com a redução de baixa utilização={correlacao_baixa_utilizacao:.3f}."
        )

    def condicao(threads: int, schedule: str, transformacao: str) -> pd.Series:
        dados = resumo[
            resumo["Num_Threads"].eq(threads)
            & resumo["OMP_Schedule"].eq(schedule)
            & resumo["Transformation"].eq(transformacao)
        ]
        if len(dados) != 1:
            raise PlotError(
                f"condição ausente no relatório: {threads}, {schedule}, {transformacao}"
            )
        return dados.iloc[0]

    rotacao = condicao(40, "dynamic_512", "Rotate_CW")
    ampliacao = condicao(40, "dynamic_1", "Zoom_In")
    gaussiano = condicao(40, "dynamic_512", "Gaussian_11x11")
    adaptativo = condicao(40, "dynamic_1", "Adaptive_Gaussian")
    linhas.extend(
        [
            "",
            "Casos úteis para interpretação (40 threads):",
            (
                "- Rotação horária, dynamic 512: o benchmark original marcou "
                f"{rotacao['Speedup_Original']:.2f}x, mas a mediana sob VTune marcou "
                f"{rotacao['VTune_Speedup_Mediana']:.2f}x. Nos frames houve "
                f"{rotacao['Fator_Trabalho_CPU']:.2f}x menos trabalho CPU, contrabalançado "
                f"por um fator de paralelismo de {rotacao['Fator_Paralelismo']:.2f}x. "
                "O perfil revela esse conflito, mas não reproduz nem confirma a magnitude do ganho original."
            ),
            (
                "- Ampliação, dynamic 1: speedup original="
                f"{ampliacao['Speedup_Original']:.2f}x e VTune="
                f"{ampliacao['VTune_Speedup_Mediana']:.2f}x. O fator de trabalho CPU="
                f"{ampliacao['Fator_Trabalho_CPU']:.2f}x e o fator de CPI="
                f"{ampliacao['Fator_CPI']:.2f}x mostram que a perda vem principalmente de "
                "mais ciclos por instrução, e não de falta de threads ativas."
            ),
            (
                "- Gaussiano 11x11, dynamic 512: trabalho CPU="
                f"{gaussiano['Fator_Trabalho_CPU']:.2f}x e paralelismo="
                f"{gaussiano['Fator_Paralelismo']:.2f}x. O chunk reduz custo por chamada, "
                "mas deixa trabalho insuficiente para manter os 40 threads ocupados."
            ),
            (
                "- Gaussiano adaptativo, dynamic 1: speedup VTune="
                f"{adaptativo['VTune_Speedup_Mediana']:.2f}x, trabalho CPU="
                f"{adaptativo['Fator_Trabalho_CPU']:.2f}x e paralelismo="
                f"{adaptativo['Fator_Paralelismo']:.2f}x. O ganho aparece principalmente "
                "como melhor balanceamento entre threads."
            ),
        ]
    )
    linhas.extend(
        [
            "",
            "Limites de interpretação:",
            "- Métricas usam frames ITT e excluem restauração e leitura de imagens.",
            "- Contadores por frame são estimativas de amostragem; use tendências repetidas.",
            "- Quando o speedup VTune diverge do original, os contadores não confirmam sozinhos a causa do resultado original.",
            "- Memory Bound menor pode decorrer de menos threads ativos; não implica melhora isoladamente.",
        ]
    )
    destino.write_text("\n".join(linhas) + "\n", encoding="utf-8")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("vtune_csv", type=Path, help="benchmark_transformacoes_vtune.csv")
    parser.add_argument(
        "benchmark_csv",
        type=Path,
        help="benchmark_transformacoes.csv usado nos graficos de speedup originais",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="diretorio de saida (padrao: <pasta do CSV VTune>/analysis)",
    )
    parser.add_argument("--chunk-size", type=int, default=100_000)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    argumentos = parse_args(argv)
    vtune_csv = argumentos.vtune_csv.resolve()
    benchmark_csv = argumentos.benchmark_csv.resolve()
    destino = (
        argumentos.output_dir.resolve()
        if argumentos.output_dir
        else vtune_csv.parent / "analysis"
    )
    if argumentos.chunk_size <= 0:
        print("Erro: --chunk-size deve ser positivo", file=sys.stderr)
        return 1

    try:
        print(f"Lendo CSV VTune em blocos: {vtune_csv}")
        frames, cobertura = carregar_frames_vtune(vtune_csv, argumentos.chunk_size)
        print(
            f"Tempos: {len(frames):,} | cobertura de frames: {cobertura:.2%}"
        )
        por_imagem = agregar_por_imagem(frames)
        resumo = resumir_condicoes(por_imagem)
        original, transformacoes = carregar_speedup_original(benchmark_csv)
        resumo = resumo.merge(
            original, on=CHAVES_CONDICAO, how="left", validate="one_to_one"
        )
        if resumo["Speedup_Original"].isna().any():
            raise PlotError("o benchmark original nao cobre todas as condicoes VTune")
        schedules, threads = validar_campanha(resumo, transformacoes)

        destino.mkdir(parents=True, exist_ok=True)
        resumo = resumo.sort_values(
            ["Num_Threads", "Transformation", "OMP_Schedule"],
            key=lambda coluna: (
                coluna.map({nome: indice for indice, nome in enumerate(transformacoes)})
                if coluna.name == "Transformation"
                else coluna.map({nome: indice for indice, nome in enumerate(schedules)})
                if coluna.name == "OMP_Schedule"
                else coluna
            ),
        )
        resumo.to_csv(destino / "vtune_diagnostic_metrics.csv", index=False)
        por_imagem.to_csv(destino / "vtune_metrics_by_image.csv", index=False)
        salvar_relatorio_texto(resumo, cobertura, destino / "README.txt")

        plotar_reproducao(resumo, destino / "comparacao_speedup_original_vtune.png")
        cores_transformacoes = dict(
            zip(transformacoes, sns.color_palette("husl", len(transformacoes)))
        )
        limite_speedup = max(
            1.1, float(resumo["VTune_Speedup_Mediana"].max()) * 1.08
        )
        quantidade_imagens = por_imagem["Image"].nunique()
        for quantidade_threads in threads:
            plotar_speedup_barras(
                resumo,
                schedules,
                transformacoes,
                quantidade_imagens,
                quantidade_threads,
                destino / f"speedup_{quantidade_threads}_threads.png",
                cores_transformacoes,
                limite_speedup,
            )
            plotar_diagnostico(
                resumo,
                schedules,
                transformacoes,
                quantidade_threads,
                destino / f"diagnostico_vtune_{quantidade_threads}_threads.png",
            )
            plotar_rotacoes(
                resumo,
                schedules,
                quantidade_threads,
                destino / f"rotacoes_vtune_{quantidade_threads}_threads.png",
            )
            plotar_casos_simples(
                resumo,
                schedules,
                quantidade_threads,
                destino / f"transformacoes_simples_vtune_{quantidade_threads}_threads.png",
            )
            plotar_casos_contrastantes(
                resumo,
                schedules,
                quantidade_threads,
                destino / f"casos_contrastantes_vtune_{quantidade_threads}_threads.png",
            )
    except (OSError, ValueError, KeyError, pd.errors.ParserError, PlotError) as erro:
        print(f"Erro: {erro}", file=sys.stderr)
        return 1

    print(f"Analise salva em: {destino}")
    for arquivo in sorted(destino.iterdir()):
        print(f"- {arquivo.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
