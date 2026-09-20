# Benchmark de escalonamento por transformação

Execute a campanha completa a partir da raiz do repositório:

```sh
./benchmark_transformacoes/run.sh
```

O script usa todas as imagens em `images/`, compila o executável dedicado e mede as 18 transformações com 20 e 40 threads. Para cada quantidade de threads, executa `static` e `dynamic` com chunks de 1 a 1024 (potências de 2), cinco vezes por condição. Cada execução cria uma nova pasta em `benchmark_transformacoes/runs/` com um CSV. O script não executa Python, portanto pode rodar em um nó de computação sem as bibliotecas de plotagem.

Para comparar afinidades OpenMP no Slurm, execute `sbatch job.sh` a partir de `benchmark_transformacoes/` (ou `sbatch benchmark_transformacoes/job.sh` a partir da raiz). Esse job executa três campanhas completas, em sequência: afinidade padrão, `OMP_PLACES=cores` com `OMP_PROC_BIND=close`, e `OMP_PLACES=cores` com `OMP_PROC_BIND=spread`. Cada campanha cria sua própria pasta datada e um `config.txt` com a afinidade, o nó e o ID do job. As três campanhas precisam caber no limite de tempo do job.

Os gráficos de `plot.py` comparam escalonamentos dentro de cada campanha. Para comparar afinidades, compare os tempos dos CSVs entre campanhas com a mesma imagem, transformação, quantidade de threads e escalonamento.

Depois que a coleta terminar, gere os dois gráficos em um ambiente com `pandas`, `matplotlib` e `seaborn`:

```sh
python3 benchmark_transformacoes/plot.py benchmark_transformacoes/runs/PASTA/benchmark_transformacoes.csv
```

Em cada imagem, transformação e quantidade de threads, o gráfico usa a mediana das cinco medições. A aceleração de cada escalonamento é a mediana de `static` dividida pela mediana desse escalonamento. Cada barra é a média geométrica dessas acelerações entre as imagens, dando o mesmo peso a cada imagem. Valores acima de `1×` indicam ganho em relação a `static`; valores abaixo indicam perda.

O CSV contém apenas `Repetition,Image,Num_Threads,OMP_Schedule,Transformation,Time_ms`. O plotador exige a campanha completa antes de gerar os PNGs.
