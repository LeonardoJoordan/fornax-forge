# Comparação acumulada — 43 cenários

Valores em ms. Variação positiva significa mais lento; negativa, mais rápido.

| Cenário | Mediana antes | Mediana final | Variação | P95 antes | P95 final | RSS máximo observado antes → final (MiB) |
|---|---:|---:|---:|---:|---:|---:|
| select_all-20 | 117.00 | 27.80 | -76.2% | 125.46 | 33.48 | 135.18 → 136.09 |
| layers-20 | 80.31 | 1.31 | -98.4% | 85.16 | 1.73 | 135.76 → 135.21 |
| snapshot_unchanged-20 | 4.73 | 1.11 | -76.4% | 6.50 | 1.27 | 134.93 → 135.30 |
| select_all-60 | 1380.40 | 42.83 | -96.9% | 1482.23 | 51.30 | 191.00 → 188.37 |
| layers-60 | 223.88 | 3.74 | -98.3% | 243.05 | 4.69 | 191.84 → 187.57 |
| snapshot_unchanged-60 | 11.19 | 2.79 | -75.1% | 13.66 | 4.03 | 190.84 → 187.86 |
| select_all-200 | 52819.69 | 113.02 | -99.8% | 57106.59 | 133.74 | 329.44 → 314.36 |
| layers-200 | 771.29 | 13.80 | -98.2% | 860.79 | 16.67 | 330.37 → 313.38 |
| snapshot_unchanged-200 | 36.59 | 9.90 | -73.0% | 49.08 | 10.48 | 328.43 → 314.21 |
| paste-20 | 351.49 | 58.90 | -83.2% | 410.85 | 68.34 | 154.28 → 149.45 |
| paste-60 | 974.71 | 109.81 | -88.7% | 1156.39 | 123.12 | 305.71 → 251.73 |
| drag_one-40 | 1155.45 | 1067.04 | -7.7% | 1561.17 | 1440.87 | 138.11 → 145.41 |
| drag_four-40 | 3832.87 | 3766.88 | -1.7% | 5443.12 | 5144.22 | 138.25 → 143.52 |
| drag_one-100 | 4441.01 | 5243.32 | +18.1% | 5519.75 | 8130.55 | 140.46 → 147.30 |
| drag_four-100 | 16445.26 | 15052.87 | -8.5% | 20365.85 | 20328.17 | 140.29 → 147.54 |
| connector_opacity | 61.87 | 20.33 | -67.1% | 73.56 | 22.24 | 177.11 → 182.52 |
| block_outline | 65.76 | 19.05 | -71.0% | 80.16 | 25.20 | 183.15 → 182.72 |
| paint_small | 39.88 | 2.08 | -94.8% | 45.20 | 2.81 | 149.64 → 158.20 |
| switch_board | 230.98 | 152.90 | -33.8% | 269.16 | 173.31 | 182.91 → 182.66 |
| paint_near-40 | 10.03 | 7.60 | -24.2% | 11.23 | 8.99 | 131.12 → 135.52 |
| paint_far-40 | 18.11 | 13.75 | -24.1% | 19.82 | 16.09 | 130.97 → 135.44 |
| paint_near-400 | 22.54 | 7.43 | -67.1% | 26.48 | 8.30 | 130.98 → 135.47 |
| paint_far-400 | 32.84 | 38.60 | +17.6% | 36.37 | 48.24 | 130.83 → 135.28 |
| paint_near-2500 | 91.45 | 7.42 | -91.9% | 110.30 | 9.12 | 131.14 → 135.55 |
| paint_far-2500 | 108.66 | 114.47 | +5.3% | 127.82 | 142.03 | 130.92 → 135.37 |
| text_insert-60 | 39.11 | 22.10 | -43.5% | 51.38 | 36.28 | 145.16 → 145.04 |
| text_insert-1200 | 57.33 | 42.47 | -25.9% | 70.84 | 51.76 | 145.28 → 145.57 |
| text_resize-1200 | 10.18 | 6.20 | -39.1% | 16.27 | 8.58 | 143.66 → 144.97 |
| switch_back | 977.79 | 677.38 | -30.7% | 1075.36 | 801.25 | 305.53 → 303.18 |
| page_cycles | 37136.34 | 10901.86 | -70.6% | 38198.50 | 15159.42 | 308.53 → 262.29 |
| gallery-model-cold | 1030.36 | 1062.55 | +3.1% | 1071.61 | 1111.95 | 163.28 → 169.65 |
| gallery-model-warm | 970.87 | 370.69 | -61.8% | 1068.32 | 379.11 | 159.70 → 169.59 |
| gallery-organogram-cold | 704.91 | 510.69 | -27.6% | 847.12 | 676.39 | 154.75 → 157.62 |
| gallery-organogram-warm | 702.64 | 72.53 | -89.7% | 935.05 | 75.75 | 148.89 → 152.41 |
| load-personnel | 354.68 | 276.13 | -22.1% | 415.14 | 278.05 | 246.69 → 241.32 |
| load-internship-certificate | 493.99 | 357.46 | -27.6% | 521.10 | 362.92 | 294.82 → 306.18 |
| load-identification-prism | 297.29 | 271.99 | -8.5% | 332.46 | 291.70 | 236.52 → 228.65 |
| load-formal-invitation | 410.86 | 274.29 | -33.2% | 423.11 | 277.62 | 237.21 → 234.61 |
| autosave-public-small | 40.15 | 52.39 | +30.5% | 40.35 | 54.83 | 170.37 → 168.96 |
| autosave-signatures-small | 47.75 | 58.09 | +21.7% | 50.33 | 63.65 | 171.34 → 162.54 |
| autosave-full-small | 36.35 | 55.27 | +52.1% | 40.96 | 72.46 | 171.30 → 162.54 |
| autosave-full-large | 290.99 | 369.12 | +26.8% | 305.29 | 400.41 | 204.60 → 190.07 |
| autosave-repeated | 133.00 | 27.08 | -79.6% | 150.54 | 32.78 | 151.79 → 153.15 |

RSS é memória corrente após cada operação, não pico. Diferenças de processos isolados
também incluem alocador, bibliotecas e caches. Não se mede somente memória Python.
Os dois casos `text_insert` usam a referência inicial recalibrada; os outros usam
a referência preservada da etapa 00. `page_cycles` executa vinte idas e voltas
por amostra. `drag_*` usa deslocamentos sequenciais, não um gesto coletivo nativo.
As cinco recuperações são comparadas até a conclusão, não só até liberar a UI.
