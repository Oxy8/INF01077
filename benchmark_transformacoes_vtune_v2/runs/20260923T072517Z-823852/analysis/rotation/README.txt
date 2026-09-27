Rotation VTune analysis
=======================

This directory compares Rotate_CW and Rotate_CCW with every dynamic chunk size found in the analysis CSVs.

Threads: 20, 40
Dynamic chunks: 1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024

Panels
------

1. VTune speedup relative to static.
2. CYCLE_ACTIVITY.STALLS_L1D_PENDING relative to static.
3. CYCLE_ACTIVITY.STALLS_L2_PENDING relative to static.
4. RESOURCE_STALLS.SB relative to static.

The cycle_percentages_all_schedules files use static and every dynamic chunk. Their first panel shows function-filtered CPU_CLK_UNHALTED.THREAD in billions per complete image-set pass. The other panels show 100 × event / CPU_CLK_UNHALTED.THREAD for the same schedule.
L1, L2 and SB conditions can overlap, so their percentages must not be added.

The heatmaps use log2 internally so reciprocal factors receive equal color intensity, but labels and colorbars display multiplicative factors. Beige is 1.00×.
Large RESOURCE_STALLS.SB ratios can result from a very small sampled static denominator, so interpret their magnitude together with the absolute event CSV and the sampling caveat.

Run plot.py from this directory to regenerate both PNG files. By default it reads ../vtune_diagnostic_metrics.csv and ../zoom/eventos_hardware_transformacoes.csv.
