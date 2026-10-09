# Etapa 02 — Atualização incremental das camadas

**Concluída em 08/10/2026.** A etapa 03 não foi iniciada.

## Mudança aplicada

A lista mantém as linhas e controles dos objetos que continuam na cena. Uma atualização sem mudanças não cria widgets; renomear altera o nome existente; inserir, excluir e reordenar preservam as outras linhas. Agrupar, desagrupar e alterar uma máscara refazem apenas as linhas cuja estrutura de controles mudou.

A identidade é a do objeto vivo, não apenas seu `layer_id`: uma cena reconstruída pode ter os mesmos identificadores e objetos diferentes. As linhas guardam o wrapper Python para verificar sua validade antes de converter referências do Qt. Isso evita acessar um `QGraphicsItem` destruído durante troca de página ou histórico. Os botões ignoram objetos inválidos ou fora da cena atual; os badges verificam também o grupo atual. Os estados visuais são invalidados após acionar os controles.

Seleção, item atual e rolagem são preservados durante a atualização. Os movimentos usam os sinais nativos do modelo para manter os widgets associados às linhas; a sincronização interna não dispara reordenações recursivas. A regra existente de arraste dos grupos permanece igual. A troca de tema atualiza nomes, ícones e badges nas linhas existentes. A abertura de outra cena e uma reconciliação impossível usam reconstrução completa segura.

Somente `features/editor/editor_window.py` e `features/editor/frontend.py` mudaram nesta etapa. O patch exclusivo e a reconstituição dos dois arquivos anteriores por SHA-256 estão em `alteracoes-etapa-02.patch` e `verificacao-patch.json`. Os demais hashes do produto coincidem; as alterações anteriores foram preservadas.

## Método

- Mesmo ThinkPad, Python 3.13.13, PySide6/Qt 6.11.0, Inter, Qt `offscreen`, tema escuro e janela solicitada de 1280 × 800. O ambiente e os hashes estão em `ambiente-antes.json` e `ambiente-depois.json`.
- **13 cenários**, com duas preparações e **20 amostras medidas** cada. Processos de benchmark em sequência, sem outros testes simultâneos. O tempo inclui pintura quando a operação a exige e a estabilização dos eventos. O profiler é uma execução adicional fora das amostras.
- As três atualizações usam páginas de 20, 60 e 200 objetos. Os dez comandos locais usam uma página mista de 60 objetos, com textos, formas, imagens, máscaras e grupos. A cena é restaurada fora do cronômetro; a edição começa já aberta. Ocultar/bloquear usam os botões reais. Reordenar move uma linha que não está no topo. O último cenário mede **dez atualizações por amostra**, não uma atualização isolada.
- A referência final foi coletada antes de alterar o produto. Uma rodada inicial de reordenação foi descartada porque o teste escolhia uma linha já no topo; o diagnóstico está em `diagnostico-alvo-reordenamento/`. Todos os 13 cenários finais foram repetidos com o alvo corrigido.
- `benchmark_editor.py` e `editor_scenarios.py`, e todos os instrumentos que já existiam, têm hashes iguais antes/depois. O executor adicional `run_layer_checks.py` foi criado para isolar temas e repetir a referência visual com os três módulos anteriores importados de uma pasta temporária. Não troca arquivos do projeto em uso.
- Entradas, assets, fontes, viewports e **documentos finais das 20 amostras de todos os 13 cenários coincidem**. Seleção, quantidade de objetos, retenção de objetos da cena, ordem serializada e índice do histórico também coincidem. As amostras brutas, p95, desvio padrão, RSS e contagens estão em `antes.json`, `depois.json` e `raw/`.

## Tempos

Valores em milissegundos; p95 interpolado.

| Operação | Mediana antes | Mediana depois | P95 antes → depois |
|---|---:|---:|---:|
| Atualizar lista — 20 objetos | 95,46 | 1,04 | 139,57 → 1,09 |
| Atualizar lista — 60 objetos | 268,91 | 2,83 | 330,78 → 2,95 |
| Atualizar lista — 200 objetos | 1.055,18 | 9,86 | 1.216,83 → 10,53 |
| Renomear camada | 324,66 | 23,99 | 377,68 → 25,32 |
| Concluir edição de texto | 83,38 | 26,31 | 98,97 → 28,62 |
| Ocultar camada | 46,75 | 35,76 | 91,79 → 42,70 |
| Bloquear camada | 70,29 | 71,90 | 132,55 → 149,80 |
| Adicionar caixa de texto | 333,24 | 119,09 | 422,72 → 151,65 |
| Excluir caixa de texto | 276,66 | 84,24 | 406,34 → 101,68 |
| Agrupar dois objetos | 233,74 | 69,29 | 322,16 → 77,30 |
| Desagrupar | 175,72 | 84,73 | 180,22 → 97,31 |
| Reordenar camada | 196,92 | 55,64 | 335,41 → 67,91 |
| Dez atualizações consecutivas | 1.872,01 | 41,65 | 2.283,33 → 61,83 |

A atualização de 200 objetos caiu de **1.055,18 ms para 9,86 ms**, redução de **99,07%**. Renomear caiu de **324,66 ms para 23,99 ms**, redução de **92,61%**. Adicionar, excluir, agrupar, desagrupar e reordenar também melhoraram nesta rodada.

**Bloquear não apresentou ganho:** 70,29 → 71,90 ms, com o mesmo trabalho contado. Ocultar e concluir a edição já não recriavam linhas antes; seus tempos incluem pintura e processamento do editor. Os valores menores observados nessas operações não são evidência de que esta etapa tenha reduzido a criação de widgets nelas. Não se atribui à etapa uma otimização do desenho do canvas, dos conectores ou do histórico.

## Trabalho e memória

Uma execução adicional com profiler. A retenção é observada após a operação, comparando linhas e widgets válidos com os originais.

| Operação | Novos nomes de linha antes → depois | Widgets originais mantidos / linhas finais, depois |
|---|---:|---:|
| Atualizar lista — 20 objetos | 21 → 0 | 21 / 21 |
| Atualizar lista — 60 objetos | 61 → 0 | 61 / 61 |
| Atualizar lista — 200 objetos | 201 → 0 | 201 / 201 |
| Renomear camada | 61 → 0 | 61 / 61 |
| Adicionar caixa de texto | 62 → 1 | 61 / 62 |
| Excluir caixa de texto | 60 → 0 | 60 / 60 |
| Agrupar dois objetos | 61 → 2 | 59 / 61 |
| Desagrupar | 61 → 9 | 52 / 61 |
| Reordenar camada | 61 → 0 | 61 / 61 |
| Dez atualizações consecutivas | 610 → 0 | 61 / 61 |

Cada linha possui um `ElidedLayerLabel`; essa contagem indica linhas montadas, não um total de todas as alocações nativas do Qt. Os badges também são contados nos resultados brutos. No agrupamento mudam os controles de duas linhas; no desagrupamento do grupo do cenário, de nove. Essas linhas mantêm os objetos gráficos, mas recebem os controles adequados à nova estrutura.

Em dez atualizações da página mista eram montados **610 nomes de linha**; agora são **zero**, com os 61 widgets mantidos. Não houve reconstrução da cena nos comandos medidos que já preservavam seus objetos.

Na página de 200 objetos o RSS foi de **330,8–330,9 MiB antes** e **312,0–312,0 MiB depois**, estável nas 20 amostras. No cenário de ciclos ficou em **247,8–256,2 MiB antes** e **242,9–250,5 MiB depois**. O último cenário também restaura a cena entre amostras fora do intervalo medido, portanto esse RSS inclui carregamento, histórico e caches. Essas faixas não demonstram, sozinhas, ausência de vazamentos em sessões longas nem uma redução permanente de memória. Não se mede apenas memória Python.

## Comportamento e fidelidade

- **Antes:** 209 regressões + 18 testes de seleção + 8 contratos de camadas = **235 testes distintos**.
- **Depois:** 209 regressões + 18 testes de seleção + 19 testes de camadas = **246 testes distintos**, todos aprovados. Os 19 testes de camadas também passaram no tema claro; repetições entre temas não aumentam o total.
- As regressões cobrem organogramas, contornos, conectores, prévia, camadas e máscaras, undo/redo, carregamento, cache, recuperação, ponteiro, texto, assinaturas, modelos e exportação em ladrilhos. Exceções nos callbacks Qt também reprovam.
- Os contratos adicionais verificam retenção real de linhas/widgets, seleção e rolagem, controles após renomear/editar/ocultar/bloquear, movimentação, colagem, troca de cena, objetos removidos e destruídos pelo Qt, recuperação após movimento recusado pelo modelo e troca de tema.
- **Nove cenários visuais por tema**: atualização, renomear/editar, ocultar/bloquear, inserir/excluir, agrupar, desagrupar, reordenar, camada Organograma e undo/redo. Há igualdade exata dos documentos, ordem, nomes, badges, flags e hashes dos pixels das linhas. Registros em `estados-*.json` e `fidelidade*.txt`. Os UUIDs do pequeno organograma de teste são fixos; caminhos temporários são normalizados. Não há tolerância visual.

Os testes usam dados sintéticos e preferências temporárias; não alteram modelos pessoais. As comparações de pixels são das linhas da lista, não capturas completas do programa ou um teste de impressão física. O backend `offscreen` não substitui validar o arraste de camadas com mouse/touchpad e a troca de temas no aplicativo aberto, em Linux ou Windows.

## Repetição

```bash
.venv/bin/python tests/performance/run_regressions.py --include-contracts --output /tmp/fornax-regressoes.txt
.venv/bin/python tests/performance/run_selection_checks.py --theme dark
.venv/bin/python tests/performance/run_layer_checks.py --theme dark
.venv/bin/python tests/performance/run_layer_checks.py --theme light
.venv/bin/python tests/performance/compare_selection_evidence.py docs/desempenho_editor/etapa-02/estados-antes.json docs/desempenho_editor/etapa-02/estados-depois.json
.venv/bin/python tests/performance/compare_selection_evidence.py docs/desempenho_editor/etapa-02/estados-antes-claro.json docs/desempenho_editor/etapa-02/estados-depois-claro.json
```

O comando com os 13 cenários está em `tests/performance/README.md`; use outra pasta de saída para preservar esta referência. O plano segue para a etapa 03 apenas com autorização.
