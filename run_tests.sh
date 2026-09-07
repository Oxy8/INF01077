#!/bin/bash

# Garante que o benchmark está compilado e atualizado
make

# Você pode alterar este nome livremente!
ARQUIVO_SAIDA="teste.csv"

echo "Iniciando bateria de testes. Os dados serão salvos em: $ARQUIVO_SAIDA"

for i in {1..6}
do
    echo "----------------------------------------"
    echo "Executando benchmark com $i threads..."
    
    # Passamos o número de threads para o OpenMP e o nome do CSV para o Makefile
    OMP_NUM_THREADS=$i make run-benchmark-folder FOLDER="images" CSV="$ARQUIVO_SAIDA"
done

echo "----------------------------------------"
echo "Todos os testes concluídos com sucesso!"
echo "Abra '$ARQUIVO_SAIDA' no Excel/Calc ou carregue num script Python para plotar os gráficos!"