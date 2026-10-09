# Etapa 00 — referência do editor

**Status: concluída.**

Foram preparados cenários determinísticos, instrumentos de desempenho e oito novos testes de comportamento. O funcionamento do aplicativo não foi alterado nesta etapa; os ajustes locais anteriores foram preservados.

## Verificação antes e depois

- Antes dos instrumentos: **201 testes** nos 18 módulos de regressão, sem falhas.
- Depois: **209 testes**, incluindo os oito novos contratos, sem falhas.
- Código, fontes e modelos distribuídos mantiveram os mesmos hashes SHA-256.
- `depois.json` registra que não se aplica medir ganho nesta etapa. A referência é `antes.json`; a etapa 01 terá suas próprias rodadas antes/depois.

Os contratos adicionais verificam seleção de objetos ocultos/bloqueados, preservação de conteúdo e máscaras ao atualizar camadas/alternar páginas, colagem com undo/redo, snapshots sem alteração, movimentação coletiva com histórico, entradas determinísticas e resumo estatístico.

## Ambiente e método

- Linux, Intel(R) Core(TM) i5-8350U CPU @ 1.70GHz; Python 3.13.13, PySide6/Qt 6.11.0.
- Qt offscreen, tema escuro, Inter, janela solicitada de 1.280 × 800, um cenário por vez.
- Operações aquecidas: duas preparações e vinte amostras; abertura/recuperação: cinco sessões novas. Profiler executado separadamente, fora das amostras de tempo.
- Memória é RSS corrente depois da operação/verificação, não pico. O arquivo bruto também registra objetos e bytes dos caches visuais.
- Dados e preferências temporários; modelos pessoais não foram usados.

Protocolo e comandos: [tests/performance/README.md](../../../tests/performance/README.md). Hashes e versões: [ambiente.json](ambiente.json).

## Tempos da referência

**43 de 43 cenários concluídos.** Os tempos são deste ambiente, sem otimização aplicada. Resultados diagnósticos de uma amostra não entram nesta tabela.

| Cenário | Amostras | Mediana (ms) | p95 (ms) | RSS final (MiB) |
|---|---:|---:|---:|---:|
| `select_all-20` | 20 | 117.00 | 125.46 | 135.2 |
| `layers-20` | 20 | 80.31 | 85.16 | 135.8 |
| `snapshot_unchanged-20` | 20 | 4.73 | 6.50 | 134.9 |
| `select_all-60` | 20 | 1380.40 | 1482.23 | 191.0 |
| `layers-60` | 20 | 223.88 | 243.05 | 191.8 |
| `snapshot_unchanged-60` | 20 | 11.19 | 13.66 | 190.8 |
| `select_all-200` | 20 | 52819.69 | 57106.59 | 329.4 |
| `layers-200` | 20 | 771.29 | 860.79 | 330.4 |
| `snapshot_unchanged-200` | 20 | 36.59 | 49.08 | 328.4 |
| `paste-20` | 20 | 351.49 | 410.85 | 154.3 |
| `paste-60` | 20 | 974.71 | 1156.39 | 304.8 |
| `drag_one-40` | 20 | 1155.45 | 1561.17 | 138.1 |
| `drag_four-40` | 20 | 3832.87 | 5443.12 | 138.2 |
| `drag_one-100` | 20 | 4441.01 | 5519.75 | 136.8 |
| `drag_four-100` | 20 | 16445.26 | 20365.85 | 136.6 |
| `connector_opacity` | 20 | 61.87 | 73.56 | 177.1 |
| `block_outline` | 20 | 65.76 | 80.16 | 165.3 |
| `paint_small` | 20 | 39.88 | 45.20 | 149.6 |
| `switch_board` | 20 | 230.98 | 269.16 | 165.0 |
| `paint_near-40` | 20 | 10.03 | 11.23 | 131.1 |
| `paint_far-40` | 20 | 18.11 | 19.82 | 131.0 |
| `paint_near-400` | 20 | 22.54 | 26.48 | 131.0 |
| `paint_far-400` | 20 | 32.84 | 36.37 | 130.8 |
| `paint_near-2500` | 20 | 91.45 | 110.30 | 131.1 |
| `paint_far-2500` | 20 | 108.66 | 127.82 | 130.9 |
| `text_insert-60` | 20 | 22.34 | 30.04 | 143.7 |
| `text_insert-1200` | 20 | 26.12 | 36.03 | 143.7 |
| `text_resize-1200` | 20 | 10.18 | 16.27 | 143.7 |
| `switch_back` | 20 | 977.79 | 1075.36 | 304.6 |
| `page_cycles` | 20 | 37136.34 | 38198.50 | 308.5 |
| `gallery-model-cold` | 5 | 1030.36 | 1071.61 | 159.4 |
| `gallery-model-warm` | 20 | 970.87 | 1068.32 | 153.5 |
| `gallery-organogram-cold` | 5 | 704.91 | 847.12 | 142.0 |
| `gallery-organogram-warm` | 20 | 702.64 | 935.05 | 148.9 |
| `load-personnel` | 5 | 354.68 | 415.14 | 228.6 |
| `load-internship-certificate` | 5 | 493.99 | 521.10 | 294.8 |
| `load-identification-prism` | 5 | 297.29 | 332.46 | 217.9 |
| `load-formal-invitation` | 5 | 410.86 | 423.11 | 208.3 |
| `autosave-public-small` | 5 | 40.15 | 40.35 | 170.4 |
| `autosave-signatures-small` | 5 | 47.75 | 50.33 | 171.3 |
| `autosave-full-small` | 5 | 36.35 | 40.96 | 171.3 |
| `autosave-full-large` | 5 | 290.99 | 305.29 | 204.6 |
| `autosave-repeated` | 20 | 133.00 | 150.54 | 151.8 |

Amostras completas, dispersão e contagens: [antes.json](antes.json) e `raw/antes/`. Cada arquivo bruto tem seu próprio hash de entrada e log.

`page_cycles` representa **vinte idas e voltas no mesmo lote**, com pintura e descarte em cada troca; não é o tempo de uma troca nem simula cliques espaçados. `drag_four` mede quatro mudanças de posição sequenciais e seus callbacks, sem reproduzir todos os eventos de ponteiro.

## Trabalho repetido observado

| Cenário | Método | Chamadas por operação instrumentada |
|---|---|---:|
| `select_all-20` | `EditorWindow.on_selection_changed` | 19 |
| `select_all-20` | `EditorWindow._groupable_items` | 189 |
| `select_all-60` | `EditorWindow.on_selection_changed` | 59 |
| `select_all-60` | `EditorWindow._groupable_items` | 1632 |
| `select_all-200` | `EditorWindow.on_selection_changed` | 199 |
| `select_all-200` | `EditorWindow._groupable_items` | 17998 |
| `paste-60` | `EditorWindow.on_selection_changed` | 3 |
| `paste-60` | `EditorWindow.refresh_layer_list` | 3 |
| `paste-60` | `EditorWindow.apply_scene_state` | 1 |
| `paste-60` | `DocumentSessionMixin._capture_document_history_state` | 1 |
| `paste-60` | `EditorWindow._groupable_items` | 2 |
| `drag_four-40` | `OrganogramEditorMixin._update_board_connections` | 4 |
| `connector_opacity` | `DocumentSessionMixin._capture_document_history_state` | 1 |
| `connector_opacity` | `OrganogramEditorMixin._update_board_extent` | 2 |
| `connector_opacity` | `OrganogramEditorMixin._update_board_connections` | 1 |
| `switch_back` | `EditorWindow.refresh_layer_list` | 3 |
| `switch_back` | `EditorWindow.apply_scene_state` | 1 |
| `switch_back` | `DocumentSessionMixin._capture_document_history_state` | 2 |
| `switch_back` | `EditorWindow._groupable_items` | 6 |
| `autosave-repeated` | `FornaxSessionManager.write_recovery` | 3 |
| `autosave-repeated` | `DocumentSessionMixin._capture_document_history_state` | 3 |

Essas contagens indicam onde investigar; não demonstram ganho. O mapa das mutações, sinais, histórico e autorização está em [MAPEAMENTO_PROCESSOS.md](MAPEAMENTO_PROCESSOS.md). Os ajustes correspondem às etapas do [plano](../../PLANO_OTIMIZACAO_EDITOR.md).

## Validação do instrumento

A coleta inicial foi arquivada em `diagnostico-v1/` e descartada como referência oficial. Ela acumulava trocas antes de processar o descarte de widgets. No protocolo 2, `DeferredDelete` é processado explicitamente e cada troca do teste de ciclos aguarda sua pintura. O consumo de cerca de 2,6 GiB observado na versão inicial foi um efeito do driver; a validação corrigida ficou próxima de 304 MiB. Isso não foi registrado como bug do aplicativo. Todos os resultados oficiais deste relatório foram recolhidos com o protocolo 2.

## Limitações e continuidade

- Nenhuma falha de comportamento foi observada nos testes aprovados. Isso não equivale a provar ausência de bugs em todos os fluxos do editor.
- Não foi realizada validação manual com mouse/touchpad, temas e backend nativo do Linux ou Windows. Essas verificações permanecem previstas para as etapas que alterarem a interface e para a integração final.
- Os testes existentes de fidelidade entre editor, prévia e geração integram as regressões. Não houve nova comparação visual de pintura parcial porque esse caminho ainda não foi implementado.
- Cada etapa deve acrescentar os casos/contadores específicos necessários, medir seu estado imediatamente anterior e preservar esta referência. A próxima etapa é **01 — seleção e painéis**.

Logs: [testes-antes.txt](testes-antes.txt), [testes-depois.txt](testes-depois.txt). Identidade final do aplicativo: [verificacao-final.json](verificacao-final.json).
