Resumo da análise VTune
=========================

Cobertura global dos frames: 99.17%
Condições analisadas: 432

Aceleração VTune = fator de trabalho CPU x fator de paralelismo.
Fator de trabalho CPU > 1: menos CPU-time para o mesmo conjunto de chamadas.
Fator de paralelismo > 1: mais núcleos ativos em média.

Reprodução do benchmark original:
- 20 threads: Spearman=0.917; dentro de 35%=98.0%.
- 40 threads: Spearman=0.866; dentro de 35%=79.3%.

Mecanismos gerais observados nos frames:
- 20 threads: correlação do log(speedup) com trabalho CPU=0.534, com paralelismo=0.901; correlação com a redução de baixa utilização=0.871.
- 40 threads: correlação do log(speedup) com trabalho CPU=0.360, com paralelismo=0.856; correlação com a redução de baixa utilização=0.841.

Casos úteis para interpretação (40 threads):
- Rotação horária, dynamic 512: o benchmark original marcou 2.07x, mas a mediana sob VTune marcou 0.87x. Nos frames houve 2.24x menos trabalho CPU, contrabalançado por um fator de paralelismo de 0.42x. O perfil revela esse conflito, mas não reproduz nem confirma a magnitude do ganho original.
- Ampliação, dynamic 1: speedup original=0.16x e VTune=0.17x. O fator de trabalho CPU=0.17x e o fator de CPI=0.17x mostram que a perda vem principalmente de mais ciclos por instrução, e não de falta de threads ativas.
- Gaussiano 11x11, dynamic 512: trabalho CPU=1.07x e paralelismo=0.32x. O chunk reduz custo por chamada, mas deixa trabalho insuficiente para manter os 40 threads ocupados.
- Gaussiano adaptativo, dynamic 1: speedup VTune=1.21x, trabalho CPU=1.01x e paralelismo=1.20x. O ganho aparece principalmente como melhor balanceamento entre threads.

Limites de interpretação:
- Métricas usam frames ITT e excluem restauração e leitura de imagens.
- Contadores por frame são estimativas de amostragem; use tendências repetidas.
- Quando o speedup VTune diverge do original, os contadores não confirmam sozinhos a causa do resultado original.
- Memory Bound menor pode decorrer de menos threads ativos; não implica melhora isoladamente.
