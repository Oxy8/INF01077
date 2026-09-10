import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import os

# ==============================================================================
# 0. CRIAÇÃO DAS PASTAS DE SAÍDA
# ==============================================================================
PASTA_RESULTADOS = 'resultados'
PASTA_INDIVIDUAIS = os.path.join(PASTA_RESULTADOS, 'graficos_individuais')

os.makedirs(PASTA_RESULTADOS, exist_ok=True)
os.makedirs(PASTA_INDIVIDUAIS, exist_ok=True)

# ==============================================================================
# 1. CIRURGIA NO ARQUIVO DE TEXTO
# ==============================================================================
print("Realizando limpeza nos dados brutos do CSV...")

linhas_corrigidas = []
with open('benchmark_escalonamento.csv', 'r') as file: # Lembre de conferir o nome do seu arquivo aqui!
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

with open('benchmark_limpo.csv', 'w') as file:
    file.writelines(linhas_corrigidas)

print("Arquivo CSV consertado com sucesso! Iniciando plotagem...")

# ==============================================================================
# 2. ANÁLISE COM PANDAS E PREPARAÇÃO DOS DADOS
# ==============================================================================
df = pd.read_csv('benchmark_limpo.csv')

NUM_THREADS_MAX = df['Num_Threads'].max()
df_max_threads = df[df['Num_Threads'] == NUM_THREADS_MAX].copy()

df_dinamico = df_max_threads[df_max_threads['OMP_Schedule'].str.startswith('dynamic')].copy()
df_dinamico['Chunk_Size'] = df_dinamico['OMP_Schedule'].apply(
    lambda x: int(x.split('_')[1]) if '_' in x else int(x.split(',')[1]) if ',' in x else 0
)
df_estatico = df_max_threads[df_max_threads['OMP_Schedule'] == 'static'].copy()

# ==============================================================================
# GRÁFICO 1: GERAL (Todas as imagens juntas)
# ==============================================================================
plt.figure(figsize=(12, 7))
ax = sns.lineplot(data=df_dinamico, x='Chunk_Size', y='Adaptive_Median', hue='Image', marker='o', linewidth=2.5)

handles, labels = ax.get_legend_handles_labels()
color_dict = {label: handle.get_color() for handle, label in zip(handles, labels)}

for _, row in df_estatico.iterrows():
    if row['Image'] in color_dict: 
        ax.axhline(y=row['Adaptive_Median'], color=color_dict[row['Image']], linestyle='--', alpha=0.6, linewidth=2.5)

plt.title(f'Impacto Geral do Chunk Size (Estresse: {NUM_THREADS_MAX} Threads)', fontsize=14, fontweight='bold')
plt.xlabel('Tamanho do Chunk (Linhas)', fontsize=12)
plt.ylabel('Tempo de Execução (ms)', fontsize=12)
plt.xscale('log') 
plt.xticks([1, 16, 32, 64, 128, 256, 512], ['1', '16', '32', '64', '128', '256', '512'])
plt.grid(True, linestyle='--', alpha=0.7)
plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
plt.tight_layout()
plt.savefig(os.path.join(PASTA_RESULTADOS, 'grafico_geral_chunks.png'), dpi=300)
plt.close() # Fecha a figura para não sobrepor na memória

# ==============================================================================
# GRÁFICO 2: INDIVIDUAIS (Uma imagem por gráfico com a sua respectiva baseline)
# ==============================================================================
print("Gerando gráficos individuais...")
imagens_unicas = df_dinamico['Image'].unique()

for img in imagens_unicas:
    plt.figure(figsize=(10, 6))
    
    # Filtra os dados apenas para a imagem atual
    df_img_dinamico = df_dinamico[df_dinamico['Image'] == img]
    df_img_estatico = df_estatico[df_estatico['Image'] == img]
    
    # Plota a curva do Dynamic
    sns.lineplot(data=df_img_dinamico, x='Chunk_Size', y='Adaptive_Median', 
                 color='#1f77b4', marker='o', linewidth=3, markersize=10, label='Dynamic')
    
    # Plota a linha reta do Static (se existir)
    if not df_img_estatico.empty:
        static_time = df_img_estatico['Adaptive_Median'].values[0]
        plt.axhline(y=static_time, color='#d62728', linestyle='--', linewidth=3, label=f'Static Baseline ({static_time:.1f} ms)')
    
    plt.title(f'Análise de Chunk Size: {img}\n({NUM_THREADS_MAX} Threads)', fontsize=14, fontweight='bold')
    plt.xlabel('Tamanho do Chunk (Escala Log)', fontsize=12)
    plt.ylabel('Tempo de Execução (ms)', fontsize=12)
    plt.xscale('log') 
    plt.xticks([1, 16, 32, 64, 128, 256, 512], ['1', '16', '32', '64', '128', '256', '512'])
    plt.grid(True, linestyle='--', alpha=0.7)
    plt.legend()
    plt.tight_layout()
    
    # Salva na subpasta
    caminho_arquivo = os.path.join(PASTA_INDIVIDUAIS, f'analise_chunk_{img}.png')
    plt.savefig(caminho_arquivo, dpi=300)
    plt.close()

print(f"-> {len(imagens_unicas)} gráficos individuais salvos em '{PASTA_INDIVIDUAIS}/'")