#!/bin/bash

# Garante que o código está atualizado
make

ARQUIVO_SAIDA="benchmark_escalonamento.csv"
echo "Iniciando bateria de testes avançada..."

# Dica do Bash: {1..10} gera a lista de 1 a 10 automaticamente
for THREADS in {1..10}
do
    # Se for apenas 1 thread, roda uma única vez e pula o laço dos chunks
    if [ "$THREADS" -eq 1 ]; then
        echo "----------------------------------------"
        echo "Testando: 1 Thread | Schedule: Sequencial"
        
        # Injeta um valor padrão só para o CSV não ficar vazio nessa coluna
        OMP_NUM_THREADS=1 OMP_SCHEDULE="dynamic,1" \
        make run-benchmark-folder FOLDER="images" CSV="$ARQUIVO_SAIDA"
        
        # Pula direto para THREADS=2, ignorando o for do CHUNK abaixo
        continue 
    fi

    # Testa os cenários de chunk size para o dynamic (apenas para 2+ threads)
    for CHUNK in 1 16 32 64 128 256 512
    do
        echo "----------------------------------------"
        echo "Testando: $THREADS Threads | Schedule: dynamic, $CHUNK"
        
        # Injeta as DUAS variáveis de ambiente para o OpenMP
        OMP_NUM_THREADS=$THREADS OMP_SCHEDULE="dynamic,$CHUNK" \
        make run-benchmark-folder FOLDER="images" CSV="$ARQUIVO_SAIDA"
    done
done

echo "----------------------------------------"
echo "Bateria finalizada! Abra o '$ARQUIVO_SAIDA' para ver o impacto."