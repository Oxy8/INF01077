#!/bin/bash

# Garante que o código está atualizado
make

ARQUIVO_SAIDA="benchmark_escalonamento.csv"
echo "Iniciando bateria de testes super otimizada..."

for THREADS in {1..10}
do
    if [ "$THREADS" -eq 1 ]; then
        echo "----------------------------------------"
        echo "Testando: 1 Thread | Pipeline Completo"
        
        ONLY_ADAPTIVE=0 OMP_NUM_THREADS=1 OMP_SCHEDULE="dynamic,1" \
        make run-benchmark-folder FOLDER="images" CSV="$ARQUIVO_SAIDA"
        
        continue 
    fi

    # Primeiro, rodamos a PIPELINE COMPLETA com o chunk padrão (16) para ter os dados dos outros filtros
    echo "----------------------------------------"
    echo "Testando: $THREADS Threads | Pipeline Completa (Chunk 16)"
    ONLY_ADAPTIVE=0 OMP_NUM_THREADS=$THREADS OMP_SCHEDULE="dynamic,16" \
    make run-benchmark-folder FOLDER="images" CSV="$ARQUIVO_SAIDA"

    # Agora, rodamos APENAS o filtro Dinâmico variando os outros chunks (ignorando o 16 que já foi)
    for CHUNK in 1 32 64 128 256 512
    do
        echo "Testando: $THREADS Threads | APENAS Adaptativo | Schedule: dynamic, $CHUNK"
        
        # A MÁGICA: ONLY_ADAPTIVE=1 faz o C++ pular os 17 primeiros filtros!
        ONLY_ADAPTIVE=1 OMP_NUM_THREADS=$THREADS OMP_SCHEDULE="dynamic,$CHUNK" \
        make run-benchmark-folder FOLDER="images" CSV="$ARQUIVO_SAIDA"
    done
done

echo "----------------------------------------"
echo "Bateria finalizada! O arquivo '$ARQUIVO_SAIDA' está pronto."