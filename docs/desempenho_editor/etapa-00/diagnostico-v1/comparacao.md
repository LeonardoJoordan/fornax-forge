> **Coleta descartada como referência oficial.** Instrumento anterior à correção do descarte/pintura do Qt. Dados mantidos somente para auditar o diagnóstico.

# Etapa 00 — referência do editor

**Status: medições em execução.**

Foram preparados cenários determinísticos, instrumentos de desempenho e oito novos testes de comportamento. O funcionamento do aplicativo não foi alterado nesta etapa; os ajustes locais anteriores foram preservados.

## Verificação antes e depois

- Antes dos instrumentos: **201 testes** nos 18 módulos de regressão, sem falhas.
- A rodada final de regressões será executada após as medições.
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

**29 de 43 cenários concluídos.** Os tempos são deste ambiente, sem otimização aplicada. Resultados diagnósticos de uma amostra não entram nesta tabela.

| Cenário | Amostras | Mediana (ms) | p95 (ms) | RSS final (MiB) |
|---|---:|---:|---:|---:|
| `select_all-20` | 20 | 116.97 | 131.94 | 135.0 |
| `layers-20` | 20 | 84.63 | 108.12 | 173.0 |
| `snapshot_unchanged-20` | 20 | 4.74 | 5.75 | 134.9 |
| `select_all-60` | 20 | 1355.97 | 1635.61 | 190.9 |
| `layers-60` | 20 | 247.18 | 276.01 | 314.7 |
| `snapshot_unchanged-60` | 20 | 11.17 | 13.44 | 190.7 |
| `select_all-200` | 20 | 54290.21 | 62659.80 | 329.4 |
| `layers-200` | 20 | 1040.33 | 1164.48 | 720.5 |
| `snapshot_unchanged-200` | 20 | 44.16 | 48.56 | 328.2 |
| `paste-20` | 20 | 428.52 | 439.60 | 157.5 |
| `paste-60` | 20 | 1160.99 | 1191.39 | 318.2 |
| `drag_one-40` | 20 | 1402.60 | 1733.71 | 138.1 |
| `drag_four-40` | 20 | 4892.00 | 6670.53 | 134.5 |
| `drag_one-100` | 20 | 5702.97 | 7043.98 | 140.3 |
| `drag_four-100` | 20 | 20461.65 | 24851.47 | 140.6 |
| `connector_opacity` | 20 | 79.39 | 106.76 | 177.0 |
| `block_outline` | 20 | 84.37 | 116.88 | 165.2 |
| `paint_small` | 20 | 59.44 | 85.75 | 149.4 |
| `switch_board` | 20 | 273.38 | 351.67 | 169.0 |
| `paint_near-40` | 20 | 13.00 | 33.42 | 131.0 |
| `paint_far-40` | 20 | 45.87 | 56.18 | 131.0 |
| `paint_near-400` | 20 | 28.74 | 33.07 | 131.1 |
| `paint_far-400` | 20 | 43.45 | 74.46 | 130.9 |
| `paint_near-2500` | 20 | 121.32 | 133.81 | 131.1 |
| `paint_far-2500` | 20 | 145.73 | 151.98 | 130.8 |
| `text_insert-60` | 20 | 24.29 | 31.56 | 143.6 |
| `text_insert-1200` | 20 | 30.14 | 35.24 | 144.2 |
| `text_resize-1200` | 20 | 13.71 | 20.21 | 143.8 |
| `switch_back` | 20 | 1149.12 | 1375.61 | 314.6 |

Amostras completas, dispersão e contagens: [antes.json](antes.json) e `raw/antes/`. Cada arquivo bruto tem seu próprio hash de entrada e log.

`page_cycles` representa **vinte idas e voltas no mesmo lote**, com pintura ao final; não é o tempo de uma troca nem simula cliques espaçados. `drag_four` mede quatro mudanças de posição sequenciais e seus callbacks, sem reproduzir todos os eventos de ponteiro.

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

Essas contagens indicam onde investigar; não demonstram ganho. O mapa das mutações, sinais, histórico e autorização está em [MAPEAMENTO_PROCESSOS.md](MAPEAMENTO_PROCESSOS.md). Os ajustes correspondem às etapas do [plano](../../PLANO_OTIMIZACAO_EDITOR.md).

## Limitações e continuidade

- Nenhuma falha de comportamento foi observada nos testes aprovados. Isso não equivale a provar ausência de bugs em todos os fluxos do editor.
- Não foi realizada validação manual com mouse/touchpad, temas e backend nativo do Linux ou Windows. Essas verificações permanecem previstas para as etapas que alterarem a interface e para a integração final.
- Os testes existentes de fidelidade entre editor, prévia e geração integram as regressões. Não houve nova comparação visual de pintura parcial porque esse caminho ainda não foi implementado.
- Cada etapa deve acrescentar os casos/contadores específicos necessários, medir seu estado imediatamente anterior e preservar esta referência. A próxima etapa é **01 — seleção e painéis**.

Logs: [testes-antes.txt](testes-antes.txt), [testes-depois.txt](testes-depois.txt). Identidade final do aplicativo: [verificacao-final.json](verificacao-final.json).
