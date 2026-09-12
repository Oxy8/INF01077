import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import os

# ==============================================================================
# 0. DEFINIÇÃO DAS PASTAS DE SAÍDA
# ==============================================================================
PASTA_RESULTADOS = 'resultados'
PASTA_INDIVIDUAIS = os.path.join(PASTA_RESULTADOS, 'individuais')

os.makedirs(PASTA_RESULTADOS, exist_ok=True)

# ==============================================================================
# 1. CIRURGIA NO ARQUIVO DE TEXTO (Limpeza do CSV)
# ==============================================================================
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

print("Arquivo CSV consertado com sucesso! Iniciando processamento...")

# ==============================================================================
# 2. PREPARAÇÃO DOS DADOS (PANDAS)
# ==============================================================================
df = pd.read_csv(arquivo_limpo)

df_pipeline_completa = df[df['Grayscale'] > 0].copy()

NUM_THREADS_MAX = df['Num_Threads'].max()
df_max_threads = df[df['Num_Threads'] == NUM_THREADS_MAX].copy()

# Ordena os schedules de forma lógica
ordem_schedules = ['static'] + [f'dynamic_{c}' for c in [1, 2, 4, 8, 16, 32, 64, 128]]
ordem_presente = [s for s in ordem_schedules if s in df_max_threads['OMP_Schedule'].unique()]

# ==============================================================================
# 3. GERAÇÃO DE TABELAS COM NÚMEROS REAIS (Excel/CSV)
# ==============================================================================
print("Calculando estatísticas e exportando tabelas...")

# Tabela 1: Média e Desvio Padrão separados por Imagem e Schedule
tabela_detalhada = df_max_threads.groupby(['Image', 'OMP_Schedule'])['Adaptive_Median'].agg(['mean', 'std']).reset_index()
tabela_detalhada.rename(columns={'mean': 'Media_Tempo_ms', 'std': 'Desvio_Padrao_ms'}, inplace=True)

# Tabela 2: Soma total do Dataset por Schedule
# Calcula quanto tempo levaria para rodar a pasta TODA usando a média de cada imagem
tabela_total_dataset = tabela_detalhada.groupby('OMP_Schedule')['Media_Tempo_ms'].sum().reset_index()
tabela_total_dataset.rename(columns={'Media_Tempo_ms': 'Tempo_Total_Dataset_ms'}, inplace=True)

# Salvando os arquivos
tabela_detalhada.to_csv(os.path.join(PASTA_RESULTADOS, 'tabela_01_detalhada_imagem_schedule.csv'), index=False, float_format='%.2f')
tabela_total_dataset.to_csv(os.path.join(PASTA_RESULTADOS, 'tabela_02_total_dataset_schedule.csv'), index=False, float_format='%.2f')

# ==============================================================================
# 4. GRÁFICOS GERAIS (Pasta Raiz)
# ==============================================================================
print("Gerando gráficos gerais comparativos...")

# 4.1 Tempo Total (Speedup Global)
plt.figure(figsize=(12, 7))
sns.lineplot(data=df_pipeline_completa, x='Num_Threads', y='Total_Time_ms', hue='Image', marker='s', errorbar='sd', linewidth=2)
plt.title('Tempo Total do Pipeline Completo por Número de Threads', fontsize=14, fontweight='bold')
plt.xlabel('Número de Threads Ativas', fontsize=12)
plt.ylabel('Tempo de Execução Total (ms)', fontsize=12)
plt.xticks(range(1, NUM_THREADS_MAX + 1))
plt.grid(True, linestyle='--', alpha=0.7)
plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
plt.tight_layout()
plt.savefig(os.path.join(PASTA_RESULTADOS, 'geral_01_tempo_total_por_thread.png'), dpi=300)
plt.close()

# 4.2 Tempo Total do DATASET INTEIRO por Schedule (O Campeão Geral)
plt.figure(figsize=(12, 7))
sns.barplot(data=tabela_total_dataset, x='OMP_Schedule', y='Tempo_Total_Dataset_ms', order=ordem_presente, color='#1f77b4', edgecolor='black')
plt.title(f'Tempo Total do Banco de Imagens por Escalonamento\n({NUM_THREADS_MAX} Threads)', fontsize=14, fontweight='bold')
plt.xlabel('Estratégia de Escalonamento (Schedule)', fontsize=12)
plt.ylabel('Soma do Tempo Médio de Todas as Imagens (ms)', fontsize=12)
plt.grid(True, axis='y', linestyle='--', alpha=0.7)

# Adiciona os números (rótulos) no topo de cada barra para facilitar a leitura no PDF
for index, row in tabela_total_dataset.set_index('OMP_Schedule').reindex(ordem_presente).reset_index().iterrows():
    if pd.notna(row['Tempo_Total_Dataset_ms']):
        plt.text(index, row['Tempo_Total_Dataset_ms'] + (row['Tempo_Total_Dataset_ms'] * 0.01), 
                 f"{row['Tempo_Total_Dataset_ms']:.0f}ms", color='black', ha="center", fontweight='bold')

plt.tight_layout()
plt.savefig(os.path.join(PASTA_RESULTADOS, 'geral_02_total_dataset_por_schedule.png'), dpi=300)
plt.close()

# ==============================================================================
# 5. GRÁFICOS INDIVIDUAIS (Isolados por imagem)
# ==============================================================================
print("Gerando gráficos individuais detalhados...")
imagens_unicas = df['Image'].unique()

for img in imagens_unicas:
    pasta_img = os.path.join(PASTA_INDIVIDUAIS, img)
    os.makedirs(pasta_img, exist_ok=True)
    
    df_img_max = df_max_threads[df_max_threads['Image'] == img]
    df_img_dinamico = df_img_max[df_img_max['OMP_Schedule'].str.startswith('dynamic')].copy()
    
    df_img_dinamico['Chunk_Size'] = df_img_dinamico['OMP_Schedule'].apply(lambda x: int(x.split('_')[1]))
    
    df_img_estatico = df_img_max[df_img_max['OMP_Schedule'] == 'static']
    df_img_completo = df_pipeline_completa[df_pipeline_completa['Image'] == img]
    
    # ---------------------------------------------------------
    # PLOT A: Impacto do Chunk (Curva + Baseline)
    # ---------------------------------------------------------
    plt.figure(figsize=(10, 6))
    sns.lineplot(data=df_img_dinamico, x='Chunk_Size', y='Adaptive_Median', color='#1f77b4', marker='o', linewidth=3, markersize=10, label='Dynamic (Média ± SD)', errorbar='sd')
    
    if not df_img_estatico.empty:
        static_mean = df_img_estatico['Adaptive_Median'].mean()
        plt.axhline(y=static_mean, color='#d62728', linestyle='--', linewidth=3, label=f'Static Baseline (Média: {static_mean:.1f} ms)')
    
    plt.title(f'[{img}] Impacto do Chunk Size no Filtro Adaptativo\n(CPU sob Estresse: {NUM_THREADS_MAX} Threads)', fontsize=13, fontweight='bold')
    plt.xlabel('Tamanho do Chunk (Escala Log)', fontsize=12)
    plt.ylabel('Tempo (ms)', fontsize=12)
    plt.xscale('log') 
    plt.xticks([1, 2, 4, 8, 16, 32, 64, 128], ['1', '2', '4', '8', '16', '32', '64', '128'])
    plt.grid(True, linestyle='--', alpha=0.7)
    plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(pasta_img, '01_analise_chunk.png'), dpi=300)
    plt.close()

    # ---------------------------------------------------------
    # PLOT B: Tempo Total de Todas as Operações por Thread
    # ---------------------------------------------------------
    if not df_img_completo.empty:
        plt.figure(figsize=(10, 6))
        sns.lineplot(data=df_img_completo, x='Num_Threads', y='Total_Time_ms', color='#2ca02c', marker='s', linewidth=3, markersize=10, errorbar='sd')
        plt.title(f'[{img}] Escalabilidade do Tempo Total\n(Pipeline Completo)', fontsize=13, fontweight='bold')
        plt.xlabel('Número de Threads Ativas', fontsize=12)
        plt.ylabel('Tempo Total de Execução (ms)', fontsize=12)
        plt.xticks(range(1, NUM_THREADS_MAX + 1))
        plt.grid(True, linestyle='--', alpha=0.7)
        plt.tight_layout()
        plt.savefig(os.path.join(pasta_img, '02_tempo_total_vs_threads.png'), dpi=300)
        plt.close()

    # ---------------------------------------------------------
    # PLOT C: Tempo por Schedule (Barplot com Pontos Reais)
    # ---------------------------------------------------------
    plt.figure(figsize=(10, 6))
    sns.barplot(data=df_img_max, x='OMP_Schedule', y='Adaptive_Median', order=ordem_presente, color='#9467bd', errorbar='sd', capsize=0.1)
    sns.stripplot(data=df_img_max, x='OMP_Schedule', y='Adaptive_Median', order=ordem_presente, color='black', alpha=0.5, jitter=True)
    plt.title(f'[{img}] Comparação de Schedules para o Filtro Adaptativo\n({NUM_THREADS_MAX} Threads)', fontsize=13, fontweight='bold')
    plt.xlabel('Estratégia de Escalonamento (Schedule)', fontsize=12)
    plt.ylabel('Tempo (ms)', fontsize=12)
    plt.grid(True, axis='y', linestyle='--', alpha=0.7)
    plt.tight_layout()
    plt.savefig(os.path.join(pasta_img, '03_comparativo_schedules.png'), dpi=300)
    plt.close()

print("========================================")
print(f"Bateria finalizada! Confira a pasta '{PASTA_RESULTADOS}' para acessar as tabelas CSV e os gráficos.")