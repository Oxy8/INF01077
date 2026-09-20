# Benchmark de escalonamento por transformação

Execute a campanha completa a partir da raiz do repositório:

```sh
./benchmark_transformacoes/run.sh
```

O script usa todas as imagens em `images/`, compila o executável dedicado e mede as 18 transformações com 20 e 40 threads. Para cada quantidade de threads, executa `static` e `dynamic` com chunks de 1 a 1024 (potências de 2), cinco vezes por condição. Cada execução cria uma nova pasta em `benchmark_transformacoes/runs/` com um CSV. O script não executa Python, portanto pode rodar em um nó de computação sem as bibliotecas de plotagem.

Depois que a coleta terminar, gere os dois gráficos em um ambiente com `pandas`, `matplotlib` e `seaborn`:

```sh
python3 benchmark_transformacoes/plot.py benchmark_transformacoes/runs/PASTA/benchmark_transformacoes.csv
```

Em cada imagem, transformação e quantidade de threads, o gráfico usa a mediana das cinco medições. A aceleração de cada escalonamento é a mediana de `static` dividida pela mediana desse escalonamento. Cada barra é a média geométrica dessas acelerações entre as imagens, dando o mesmo peso a cada imagem. Valores acima de `1×` indicam ganho em relação a `static`; valores abaixo indicam perda.

O CSV contém apenas `Repetition,Image,Num_Threads,OMP_Schedule,Transformation,Time_ms`. O plotador exige a campanha completa antes de gerar os PNGs.
