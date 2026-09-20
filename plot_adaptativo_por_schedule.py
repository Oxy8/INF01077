import os

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns


PASTA_RESULTADOS = 'resultados_adaptativo_por_schedule'
os.makedirs(PASTA_RESULTADOS, exist_ok=True)

# Mesma limpeza inicial usada por plot_resultados.py.
print("Realizando limpeza nos dados brutos do CSV...")

arquivo_original = 'benchmark_escalonamento.csv'
arquivo_limpo = 'benchmark_limpo.csv'

linhas_corrigidas = []
with open(arquivo_original, 'r') as file:
    linhas = file.readlines()

header = linhas[0].strip()
linhas_corrigidas.append(header + '\n')
qtd_colunas_corretas = len(header.split(','))

for linha in linhas[1:]:
    linha = linha.strip()
    if not linha: continue

    colunas = linha.split(',')

    if len(colunas) == qtd_colunas_corretas + 1:
        colunas[2] = f"{colunas[2]}_{colunas[3]}"
        del colunas[3]
        linhas_corrigidas.append(','.join(colunas) + '\n')
    elif len(colunas) == qtd_colunas_corretas and not colunas[2].replace('.', '', 1).isdigit():
        linhas_corrigidas.append(linha + '\n')

with open(arquivo_limpo, 'w') as file:
    file.writelines(linhas_corrigidas)

print("Arquivo CSV consertado com sucesso! Gerando gráfico...")

df = pd.read_csv(arquivo_limpo)
num_threads_max = df['Num_Threads'].max()
df_max_threads = df[df['Num_Threads'] == num_threads_max].copy()

ordem_schedules = ['static'] + [f'dynamic_{c}' for c in [1, 2, 4, 8, 16, 32, 64, 128]]
ordem_presente = [s for s in ordem_schedules if s in df_max_threads['OMP_Schedule'].unique()]

plt.figure(figsize=(14, 7))
sns.barplot(
    data=df_max_threads,
    x='OMP_Schedule',
    y='Adaptive_Median',
    hue='Image',
    order=ordem_presente,
    palette='husl',
    errorbar='sd',
    capsize=0.1,
)
plt.title(
    f'Tempo do Filtro Adaptativo por Escalonamento (Fixo em {num_threads_max} Threads)',
    fontsize=14,
    fontweight='bold',
)
plt.xlabel('Estratégia de Escalonamento (Schedule)', fontsize=12)
plt.ylabel('Tempo de Execução (ms)', fontsize=12)
plt.grid(True, axis='y', linestyle='--', alpha=0.7)
plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
plt.tight_layout()

caminho_grafico = os.path.join(PASTA_RESULTADOS, 'geral_adaptativo_por_schedule.png')
plt.savefig(caminho_grafico, dpi=300)
plt.close()
print(f"Gráfico salvo em '{caminho_grafico}'.")
