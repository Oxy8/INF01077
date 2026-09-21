# Benchmark de afinidade

Execute `sbatch job.sh` dentro de `benchmark_affinity/`, ou `sbatch benchmark_affinity/job.sh` na raiz do repositório. O job reserva 40 CPUs e executa três campanhas sequenciais: afinidade padrão, `OMP_PLACES=cores` com `OMP_PROC_BIND=close`, e `OMP_PLACES=cores` com `OMP_PROC_BIND=spread`.

Cada campanha usa todas as imagens em `images/`, 40 threads, cinco repetições e dois escalonamentos: `static` e `dynamic,16`. Para escolher outro chunk dinâmico, execute, por exemplo, `sbatch --export=ALL,AFFINITY_DYNAMIC_CHUNK=32 job.sh`. O escalonamento é mantido igual nas três campanhas.

Cada campanha cria uma pasta em `runs/` com `config.txt`, `adaptive_gaussian.csv` e `negative.csv`. As duas transformações são executadas separadamente, cada uma em seu próprio processo e CSV. Cada CSV contém `Repetition,Image,Num_Threads,OMP_Schedule,Transformation,Time_ms`. Com as 13 imagens atuais, cada CSV completo tem 130 medições mais o cabeçalho. O job apenas coleta os dados; não executa Python.

Para comparar afinidades, use a mediana das cinco medições para a mesma imagem, transformação e escalonamento em cada campanha. Compare os tempos absolutos entre campanhas; o chunk e a contagem de threads devem permanecer iguais. `close` e `spread` distribuem threads nos lugares disponíveis ao processo, então verifique a topologia do nó antes de interpretar uma política como execução em um ou dois sockets.

Depois de copiar as três pastas do job para `runs/`, gere os gráficos no computador local com `matplotlib` instalado:

```sh
python3 benchmark_affinity/plot.py
```

Se houver vários jobs em `runs/`, escolha um com `--job-id ID`. O script valida as três campanhas e cria `plots/job_ID/affinity_adaptive_gaussian.png` e `affinity_negative.png`. Cada figura compara `default`, `close` e `spread` separadamente para `static` e `dynamic,N`: o painel esquerdo mostra a média geométrica das acelerações por imagem em relação a `default` no mesmo escalonamento; o direito soma as medianas de tempo das imagens. Uma aceleração acima de `1×` indica que a afinidade foi mais rápida que `default`.
