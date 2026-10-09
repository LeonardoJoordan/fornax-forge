# Etapa 03 — Conectores, propriedades e recortes

**Concluída em 08/10/2026.** A etapa 04 não foi iniciada.

## Mudança aplicada

O movimento nativo da seleção passa por um lote síncrono: os callbacks de cada bloco registram a necessidade de atualização, e as rotas são recalculadas uma vez após todos chegarem às suas posições finais naquele evento. Não há timer adiado entre o movimento e a atualização. Lotes aninhados restauram os estados anteriores mesmo diante de uma exceção; teclado, soltura perdida e Esc preservam seu comportamento existente. Esc encerra a movimentação; desfazer recupera a posição anterior.

O editor lê uma representação leve da geometria, sem serializar o HTML dos textos para descobrir caminhos e dimensões. Mantém um único resultado atual para rotas e limites. Todos os blocos continuam participando como obstáculos, inclusive os que não têm conexão com os itens movidos. Portas, contornos, espessuras e raios entram nas dependências geométricas. Cor e transparência reutilizam caminhos válidos. Limites e painel compartilham o resultado, e a captura do histórico evita uma segunda atualização desnecessária do painel.

Os recortes dos textos são compartilhados pelos conectores. Cada conector reutiliza sua forma de seleção e seu recorte de pintura enquanto caminho, espessura e revisão dos textos permanecem válidos. Mover, girar, redimensionar, ocultar, alterar transparência, mudar camada, remover texto ou carregar outra cena invalidam esses resultados. A destruição nativa do Qt também invalida o cache por um callback do objeto filho, com referência fraca à janela, sem acessar o item destruído. A edição do conteúdo continua atualizando a área de trabalho quando necessário.

Cinco arquivos do produto mudaram: `core/board_connectors.py`, `core/organogram.py`, `features/editor/canvas_items.py`, `features/editor/editor_window.py` e `features/editor/organogram_editor.py`. As funções compartilhadas aceitam resultados já calculados como argumentos opcionais; prévia e geração continuam usando o comportamento padrão. O patch exclusivo e a reconstituição exata dos arquivos anteriores por SHA-256 estão em `alteracoes-etapa-03.patch` e `verificacao-patch.json`. Os demais hashes do produto coincidem; as etapas anteriores e alterações do usuário foram preservadas.

## Método

- Mesmo ThinkPad i5-8350U, Python 3.13.13, PySide6/Qt 6.11.0, Inter, Qt `offscreen`, tema escuro e janela solicitada de 1280 × 800. Viewport efetivo e fonte coincidem por cenário.
- **18 cenários**, com duas preparações e **20 amostras medidas** cada. Processos de benchmark em sequência; profiler em uma execução adicional, fora dos tempos.
- Seis arrastes nativos: 1/4/10 blocos em quadros conectados de 20 e 40. Cada amostra inclui um evento de movimento e a soltura, com pintura e estabilização dos eventos. Mede a latência dessa atualização, não um gesto inteiro composto de vários movimentos.
- A cena é restaurada fora do cronômetro. Os deslocamentos variam deterministicamente por amostra, evitando medir repetidamente uma geometria já memorizada. O driver confirma quantos itens realmente se moveram e exige deslocamentos iguais em toda a seleção.
- A pressão ocorre após estabilizar seleção/zoom/eventos: a simulação anterior pressionava antes dessa espera, e o detector de soltura perdida encerrava corretamente o gesto artificial. Rodadas exploratórias com esse driver foram descartadas; não entram em `antes.json` ou `depois.json`.
- Os outros doze cenários usam 40 blocos. Textos sintéticos sobre os conectores exercitam edição e recorte. O caso de portas aguarda estabilização, sem exigir uma pintura que pode ser desnecessária ao mudar apenas a permissão de um lado.
- Todos os instrumentos que já existiam na referência, incluindo driver, entradas e testes comportamentais, têm hashes iguais antes/depois. O comparador auxiliar foi acrescentado depois da referência e ajustado após o benchmark para explicitar precisão numérica dos pontos/limites; não participa do trecho temporizado. Seu hash final e o capturado no manifesto estão em `verificacao-comparacao.json`, sem reescrever os manifestos históricos.
- **Todos os 18 cenários e suas 20 amostras** preservam entrada, viewport, fonte, hash do documento final, seleção, número de objetos, retenção dos itens gráficos e índice do histórico. Amostras, dispersão, memória e perfis ficam em `antes.json`, `depois.json` e `raw/`.

## Tempos

Valores em milissegundos; p95 interpolado.

| Operação | Mediana antes | Mediana depois | P95 antes → depois |
|---|---:|---:|---:|
| Arrastar 1 bloco — quadro de 20 | 245,99 | 235,80 | 305,99 → 295,07 |
| Arrastar 4 blocos — quadro de 20 | 603,82 | 174,26 | 1.099,54 → 324,83 |
| Arrastar 10 blocos — quadro de 20 | 1.617,37 | 175,39 | 2.520,28 → 255,12 |
| Arrastar 1 bloco — quadro de 40 | 1.075,02 | 1.046,80 | 1.414,67 → 1.308,49 |
| Arrastar 4 blocos — quadro de 40 | 3.553,45 | 953,41 | 5.771,96 → 1.471,17 |
| Arrastar 10 blocos — quadro de 40 | 10.745,55 | 1.421,78 | 15.392,64 → 1.606,41 |
| Cor do conector | 68,80 | 43,00 | 109,85 → 45,82 |
| Transparência do conector | 65,00 | 42,33 | 76,16 → 46,13 |
| Espessura do conector | 66,32 | 45,78 | 75,21 → 51,35 |
| Raio do conector | 67,42 | 46,29 | 76,58 → 61,96 |
| Portas permitidas | 70,66 | 51,85 | 77,20 → 69,24 |
| Cor do contorno | 74,00 | 54,57 | 86,41 → 60,83 |
| Transparência do contorno | 75,92 | 54,74 | 87,83 → 59,95 |
| Espessura do contorno | 78,30 | 55,29 | 85,64 → 72,17 |
| Raio do contorno | 77,33 | 55,68 | 85,96 → 60,72 |
| Mover texto sobre conexões | 27,75 | 24,69 | 32,76 → 31,23 |
| Concluir edição de texto | 63,81 | 49,15 | 67,95 → 53,31 |
| Selecionar/pintar com recortes aquecidos | 32,32 | 23,77 | 46,28 → 26,75 |

Mover dez blocos no quadro de 40 caiu de **10.745,55 ms para 1.421,78 ms**, redução de **86,77%**. No quadro de 20, caiu de **1.617,37 ms para 175,39 ms**, redução de **89,16%**. Quatro blocos também tiveram redução consistente. O movimento de um único bloco ficou próximo da referência; a pequena diferença nessa rodada não comprova ganho relevante nesse caso.

Os ajustes de propriedades tiveram medianas menores nesta rodada. A contagem confirma a eliminação de recálculos de geometria nas mudanças de aparência. A pintura continua necessária. **1,42 s por atualização ainda é perceptível:** o roteamento do quadro inteiro permanece caro; esta etapa elimina os cálculos intermediários sem alterar o algoritmo de roteamento ou suas regras.

## Trabalho e memória

Uma rodada adicional com profiler, fora das medianas. “Rotas efetivamente calculadas” conta `_routes`; `board_routes` também pode consultar o cache do núcleo.

| Operação | Rotas efetivamente calculadas | Capturas completas da cena | Atualizações do painel |
|---|---:|---:|---:|
| Arrastar dez — quadro de 40 | 10 → 1 | 5 → 1 | 2 → 1 |
| Cor do conector | 0 → 0 | 5 → 1 | 2 → 1 |
| Transparência do conector | 0 → 0 | 5 → 1 | 2 → 1 |
| Espessura do conector | 0 → 0 | 5 → 1 | 2 → 1 |
| Raio do conector | 0 → 0 | 5 → 1 | 2 → 1 |

No arraste de dez blocos/40, as chamadas a `board_routes` passaram de **24 para 1**, a `connector_paths` de **14 para 1**, e a `board_bounds` de **4 para 1**. O cálculo efetivo passou de dez geometrias intermediárias para uma geometria final. Os caminhos individuais passaram de 546 para 39, preservando todos os 39 conectores. O número de callbacks `_update_board_connections` não cai: agora dez deles só sinalizam trabalho pendente, e um consolida o resultado.

Mover o texto sobre as conexões antes reconstruía os recortes em 39 chamadas; agora reconstrói o recorte compartilhado **uma vez**. Seleção e pintura aquecidas consultavam os recortes 117 vezes e calculavam 39 clips; depois consultam 78 vezes, com **zero reconstruções de recorte e zero clips novos** nessa rodada. Um teste separado exige uma construção com cache vazio e outra após mudar a geometria do texto, além de verificar que modificar uma cópia retornada não corrompe o resultado compartilhado.

No arraste de dez/40, o RSS ficou em **134,96–135,16 MiB antes** e **134,42–138,58 MiB depois**; na seleção/pintura com recortes, **133,24–136,95 MiB antes** e **133,20–136,91 MiB depois**. RSS é memória corrente do processo, não pico nem memória apenas Python. Essas faixas não demonstram redução permanente nem ausência de vazamento em sessões longas. Os caches geométricos conservam um estado atual por janela e uma forma/clip atual por conector, sem histórico de posições ou referências aos itens nesses resultados. `visual_cache_bytes` mede os caches raster existentes; não contabiliza estes novos caminhos vetoriais.

## Comportamento e fidelidade

- **Antes:** 209 regressões + 18 testes de seleção + 19 de camadas + 6 contratos comportamentais do quadro = **252 testes distintos**, aprovados.
- **Depois:** 209 regressões + 18 de seleção + 19 de camadas + 13 do quadro = **259 testes distintos**, aprovados. Os 13 testes do quadro passaram também no tema claro; repetição entre temas não aumenta o total.
- Os contratos cobrem arraste nativo de 1/4/10, propriedades, portas e obstáculos sem conexão, contornos, textos rotacionados/redimensionados/ocultos/transparentes/atrás do quadro, edição, seleção dos conectores, soltura perdida, Esc, undo/redo, lotes aninhados com exceção, remoção/destruição de textos e troca de cena. As regressões existentes incluem prévia, exportação, camadas, máscaras, histórico e ladrilhos. Exceções dos callbacks Qt também são capturadas.
- **23 estados visuais em cada tema**, com documentos e hashes dos pixels **exatamente iguais** antes/depois. A imagem compara a cena inteira renderizada em 800 × 500, dentro dos limites atuais do quadro. Não há tolerância raster.
- Conexões, quantidade e tipos dos elementos dos caminhos também coincidem. Coordenadas e limites brutos apresentam ruído mínimo de ponto flutuante: máximo **2,8421709430404007e-14** unidades da cena no tema escuro e **1,1368683772161603e-13** no claro. O comparador admite somente **1e-10 unidades da cena** nesses números (aproximadamente 8,47e-12 mm), preservando os registros brutos. Não se declara igualdade binária das coordenadas nem se arredondam as imagens para esconder diferenças.

Os dados são sintéticos, com preferências temporárias; os modelos pessoais não foram alterados. Os testes automatizados não substituem conferir mouse/touchpad no aplicativo aberto, backend nativo do Linux, Windows ou impressão física. Não foi feita uma nova comparação raster completa de PNG/PDF de produção nesta etapa; os consumidores padrão das funções compartilhadas permaneceram iguais e suas regressões passaram.

## Limites e repetição

A rodada oficial usa 20/40 blocos. Um ensaio exploratório com 100 blocos e dez movidos foi interrompido por duração excessiva antes da referência oficial; não é contabilizado como aprovado nem permite alegar ganho em 100 blocos. O cenário de 100 permanece previsto para a revisão de desempenho do conjunto. A etapa não introduz pintura parcial da view, outro algoritmo de roteamento, mudança de formato nem alteração das regras de agrupamento ou magnetismo.

```bash
.venv/bin/python tests/performance/run_regressions.py --include-contracts --output /tmp/fornax-regressoes.txt
.venv/bin/python tests/performance/run_board_checks.py --theme dark
.venv/bin/python tests/performance/run_board_checks.py --theme light
.venv/bin/python tests/performance/compare_board_evidence.py docs/desempenho_editor/etapa-03/estados-antes.json docs/desempenho_editor/etapa-03/estados-depois.json
.venv/bin/python tests/performance/compare_board_evidence.py docs/desempenho_editor/etapa-03/estados-antes-claro.json docs/desempenho_editor/etapa-03/estados-depois-claro.json
```

Os comandos com os 18 cenários estão em `tests/performance/README.md`. Use outra pasta de saída para preservar esta referência. O patch desta etapa inclui também alterações em `canvas_items` e no núcleo: para reconstituir integralmente a referência, reverta o patch em uma cópia isolada. `--reference-editor` substitui apenas módulos do editor e, sozinho, não reconstitui os cinco arquivos desta etapa.
