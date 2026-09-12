#!/bin/bash

# Garante que o código está atualizado
make

ARQUIVO_SAIDA="benchmark_escalonamento.csv"

# Remove o arquivo anterior para a nova bateria estatística começar limpa
rm -f "$ARQUIVO_SAIDA"

NUM_REPETICOES=5

echo "Iniciando bateria de testes estatísticos com $NUM_REPETICOES rodadas..."

# Laço externo das repetições estatísticas
for RUN in $(seq 1 $NUM_REPETICOES)
do
    echo "========================================"
    echo "       RODADA $RUN DE $NUM_REPETICOES       "
    echo "========================================"

    for THREADS in {1..12}
    do
        if [ "$THREADS" -eq 1 ]; then
            echo "----------------------------------------"
            echo "Testando: 1 Thread | Pipeline Completo"
            
            ONLY_ADAPTIVE=0 OMP_NUM_THREADS=1 OMP_SCHEDULE="dynamic,1" \
            make run-benchmark-folder FOLDER="images" CSV="$ARQUIVO_SAIDA"
            
            continue 
        fi

        # Primeiro, rodamos a PIPELINE COMPLETA com o chunk padrão (16)
        echo "----------------------------------------"
        echo "Testando: $THREADS Threads | Pipeline Completa (Chunk 16)"
        ONLY_ADAPTIVE=0 OMP_NUM_THREADS=$THREADS OMP_SCHEDULE="dynamic,16" \
        make run-benchmark-folder FOLDER="images" CSV="$ARQUIVO_SAIDA"

        # Teste do Static Baseline
        echo "Testando: $THREADS Threads | APENAS Adaptativo | Schedule: static"
        ONLY_ADAPTIVE=1 OMP_NUM_THREADS=$THREADS OMP_SCHEDULE="static" \
        make run-benchmark-folder FOLDER="images" CSV="$ARQUIVO_SAIDA"

        # Testes das variações do dynamic
        for CHUNK in 1 2 4 8 32 64 128
        do
            echo "Testando: $THREADS Threads | APENAS Adaptativo | Schedule: dynamic, $CHUNK"
            
            ONLY_ADAPTIVE=1 OMP_NUM_THREADS=$THREADS OMP_SCHEDULE="dynamic,$CHUNK" \
            make run-benchmark-folder FOLDER="images" CSV="$ARQUIVO_SAIDA"
        done
    done
done

echo "========================================"
echo "Bateria finalizada com sucesso! O arquivo '$ARQUIVO_SAIDA' possui dados estatisticamente válidos."