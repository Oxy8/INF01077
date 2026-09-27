# Campanha mínima: SIMD nos taps da convolução 11×11

O teste isola **uma mudança**: `#pragma omp simd reduction(+:sum_r,sum_g,sum_b)`
imediatamente antes do laço interno `l` de `float_tap_reduction` em
`577262-FPI-Relatorio2/vectorization_benchmark.cpp`. Ambos os builds
executam a **mesma função**, os mesmos 121 coeficientes float da Gaussiana de
produção e o mesmo alvo Haswell. `auto-avx2` compila esse laço sem o pragma;
`omp-avx2` compila com ele. Não há mudança de layout nem separação do filtro.
O compilador ainda pode vetorizar automaticamente o baseline; por isso os
relatórios GCC são parte da campanha. Os outros pragmas existentes no arquivo
não pertencem ao kernel medido.

São somente **12 amostras**: imagem `4000x3000.png`, `OMP_SCHEDULE=static`,
1 e 20 threads, três medições para cada build/configuração, precedidas de
um aquecimento. Mede-se só o **kernel**, com saída pré-alocada; leitura PNG,
alocação, referência e validação não entram no cronômetro. Não se compara
essa duração diretamente ao tempo total da função de produção.

O CSV registra `Differing_Bytes` e `Max_Abs_Error` contra a convolução float
original (que é conferida contra a implementação de produção no aquecimento).
Uma redução pode alterar a ordem das somas de ponto flutuante: resultado
não-exato **não** é tratado como semanticamente idêntico. Diferença máxima
maior que um nível de cor interrompe a campanha; diferenças menores ficam
quantificadas, sem serem escondidas. `auto/omp > 1` significa que o pragma
melhorou o tempo nessa variante, não necessariamente que a imagem seja
bit a bit igual.

## Executar no PCAD

Após enviar e atualizar o repositório no frontend, a partir da raiz:

```bash
job=$(sbatch --parsable scripts/pcad_hype_inner_simd_convolution.sbatch)
echo "$job"
squeue -j "$job"
```

O job não depende de outros. Os arquivos ficam em
`resultados_pcad_hype_conv_inner_simd_ID/`: `inner_simd_raw.csv`,
`inner_simd_summary.csv`, relatórios completos GCC de cada build,
`*-inner-loop-focus.txt` com as mensagens do laço investigado,
versão do compilador, flags, protocolo e hashes das fontes. Para conferir
a execução sem esperar o nó, no Linux e com um diretório novo:

```bash
bash run_inner_simd_convolution.sh --quick --output teste_conv_inner_simd
```

Os arquivos `*-inner-loop-focus.txt` mostram se o GCC vetorizou o laço `l`
em cada build. A razão de tempos e as diferenças de bytes determinam se
isso foi útil e numericamente aceitável.
