# Medições do editor

## Prova técnica de tabelas — etapa 01

`table_layout_prototype.py` é um experimento isolado, sem schema persistente
ou integração no menu do aplicativo. `run_table_prototype.py` compara o
candidato QTextTable com medidas próprias, gera imagens/PDF de prova e mede
construção/pintura de uma grade de 800 células. As evidências ficam locais.

```bash
QT_QPA_PLATFORM=offscreen QT_SCALE_FACTOR=1 .venv/bin/python tests/performance/run_table_prototype.py --output docs/implementacao_tabelas/etapa-01
QT_QPA_PLATFORM=offscreen QT_SCALE_FACTOR=1 PYTHONPATH=tests .venv/bin/python -m unittest test_table_layout_prototype -v
```

O runner usa Poppler e `pypdf` para conferência independente do PDF, sem
instalá-los. O teste funcional do protótipo não depende dessas ferramentas.
Decisões, medições, limites e comandos estão no
[relatório da etapa 01](../../docs/implementacao_tabelas/etapa-01/RELATORIO.md).

## O que é versionado

Os testes, instrumentos, fixtures e relatórios em Markdown fazem parte do
repositório. Logs, capturas, resultados brutos, patches e cópias de referência
das rodadas em `docs/desempenho_editor/` e `docs/implementacao_tabelas/` ficam
apenas no computador, ignorados pelo Git. A exceção é
`docs/desempenho_editor/etapa-00/antes.json`, usada para selecionar os cenários
de `run_final_benchmarks.py`.

Links para essas evidências nos relatórios descrevem arquivos locais; eles
não estarão disponíveis numa cópia nova do GitHub. Comparações históricas,
auditorias e reconstruções de versões anteriores exigem essas evidências
locais. Os testes e benchmarks do código atual continuam versionados.

Execute a partir da raiz, com o Python do ambiente do projeto:

```bash
.venv/bin/python tests/performance/run_regressions.py --output docs/desempenho_editor/etapa-00/testes-antes.txt
.venv/bin/python tests/performance/benchmark_editor.py --output docs/desempenho_editor/etapa-00
.venv/bin/python tests/performance/run_regressions.py --include-contracts --output docs/desempenho_editor/etapa-00/testes-depois.txt
```

Para uma etapa posterior, use sua pasta e execute o benchmark antes da mudança
com `--label antes` e depois com `--label depois`. Guarde uma cópia do
`ambiente.json` de cada rodada: o arquivo identifica a execução mais recente.
Mantenha as mesmas versões e o mesmo conjunto de cenários nas duas medições.

`--case select_all-60` executa um cenário; repita `--case` para escolher vários na mesma rodada. `--samples 1` serve exclusivamente
para verificar o instrumento; resultados assim são marcados como diagnóstico.
Os cenários maiores são deliberadamente lentos no código de referência.
Cada cenário tem limite de 2.400 segundos, sem limite de aprovação por tempo.
Um timeout é registrado como falha de medição, nunca como resultado aprovado.
O worker interrompe o cenário se o RSS observado após uma operação superar
2 GiB, preservando as amostras já coletadas. Esse limite protege o ambiente,
não define um requisito de memória do aplicativo.

## Protocolo

- Um processo por cenário, executados em sequência, com diretórios temporários
  para dados, configurações e cache. Os módulos de regressão também são isolados.
- Qt `offscreen`, tema escuro, fonte Inter instalada pelo aplicativo e janela
  solicitada de 1.280 × 800. O tamanho efetivo do viewport e a fonte são registrados.
- Operações aquecidas: duas preparações e vinte amostras. Abertura de modelos,
  primeira galeria e recuperação: cinco sessões novas, com caches do editor vazios.
  São sessões frias do aplicativo, **não** garantia de cache do sistema operacional vazio.
- Dados sintéticos determinísticos e modelos públicos distribuídos no projeto.
  Não são lidos modelos pessoais. Hashes identificam documento, assets, fontes,
  código e instrumentos, incluindo alterações locais ainda sem commit.
- Colagem e edição começam com uma restauração da entrada fora do cronômetro;
  não se acumulam itens. Os movimentos também partem da mesma cena e usam uma
  sequência fixa de deslocamentos de 5, 10, 15… mm para não medir apenas um acerto
  do cache de roteamento sobre a mesma geometria. Essa sequência é igual nas duas versões.
- A operação inclui o processamento da pintura esperada e três turnos de eventos
  sem nova pintura. Camadas e snapshots sem alteração não exigem repintar o canvas;
  galerias aguardam sua própria pintura. Recuperação termina com arquivo publicado.
  O conteúdo recuperado é verificado fora do cronômetro.
  `DeferredDelete` é processado explicitamente: um driver que só chama
  `processEvents()` não reproduz todo o descarte do loop normal do Qt.
- Não há pausas fixas no intervalo medido. Exceções nos callbacks Qt são capturadas
  além dos erros normais dos testes.
- Uma rodada adicional com `cProfile` conta chamadas; seu tempo não entra na mediana.
  `qualname` distingue métodos de pintura que compartilham o nome `paint`.
  As contagens são de funções Python; não medem separadamente chamadas nativas
  de desenho do Qt. A etapa de pintura deve acrescentar a contagem por cartão.
- Memória: RSS corrente no Linux, após cada operação; não é pico nem memória apenas
  Python. Também são registrados bytes dos caches visuais e objetos da cena.
  Retenção de objetos usa referências Python válidas e a cena de origem, não `id()`
  reciclado nem somente os identificadores serializados.
- `page_cycles` mede vinte idas e voltas como **uma** operação e registra a memória
  ao final de cada lote. Não comparar esse tempo com uma troca isolada.
  Cada troca aguarda sua pintura e descarte dos widgets antes da próxima,
  sem pausas artificiais. Assim não acumula quarenta trocas sem retornar ao Qt.
- `drag_four` reproduz quatro mudanças de posição sequenciais e seus callbacks;
  não simula toda a sequência de eventos de mouse/touchpad. A regressão funcional
  verifica separadamente `_move_board_items`, que já adia atualizações coletivas.
- Mediana, p95 interpolado, desvio padrão populacional e todas as amostras são
  guardados. Não juntar tempos de máquinas ou backends distintos.

## Limites

Estes instrumentos localizam custos e preservam uma referência para comparações.
Não substituem testes de ponteiro real, capturas de fidelidade visual nem validação
no backend nativo do Linux ou Windows. Novas etapas devem acrescentar casos e
contagens específicos antes de implementar seus ajustes, conforme o plano.

## Rodada Pareto

`benchmark_pareto.py` mede troca de páginas, rotas, 1.000 cartões distribuídos
em 100 conjuntos e quatro cenários de recuperação. Usa duas preparações e
cinco amostras por padrão; `--samples` permite uma rodada maior. Confere
movimento efetivo, histórico e pintura, sem modificar os modelos pessoais.

```bash
.venv/bin/python tests/performance/benchmark_pareto.py --output /tmp/fornax-pareto --label depois --samples 5
.venv/bin/python tests/performance/run_pareto_checks.py --output /tmp/fornax-pareto-checks
```

O runner de testes isola processos e preferências. `--baseline` omite os
novos contratos; `--module` seleciona módulos específicos. As evidências
da comparação preservada estão em `docs/desempenho_editor/etapa-12/`.

## Consolidação — etapa 11

```bash
.venv/bin/python docs/desempenho_editor/etapa-11/reconstruir_referencia.py --output /tmp/fornax-referencia-inicial
.venv/bin/python tests/performance/run_final_benchmarks.py --reference /tmp/fornax-referencia-inicial --output /tmp/fornax-final-referencia-texto
.venv/bin/python tests/performance/run_final_benchmarks.py --output /tmp/fornax-final-bench
.venv/bin/python tests/performance/benchmark_recovery.py --label depois --output /tmp/fornax-final-recuperacao
.venv/bin/python tests/performance/run_page_regressions.py --label depois --output /tmp/fornax-final-checks
PYTHONPATH=tests FORNAX_GALLERY_CACHE_CHECKS=1 QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest test_starter_gallery_cache -q
QT_QPA_PLATFORM=offscreen .venv/bin/python tests/performance/check_final_journeys.py --output /tmp/fornax-final-fluxos.json
QT_QPA_PLATFORM=offscreen .venv/bin/python tests/performance/check_final_journeys.py --reference /tmp/fornax-referencia-inicial --output /tmp/fornax-inicial-fluxos.json
```

Use diretórios de preferências/dados temporários em cada comando; não execute
suítes pesadas junto dos benchmarks. A reconstrução exige uma pasta nova e
confere os 101 hashes iniciais. Ela reverte patches somente na cópia temporária.
O `--reference` de `run_final_benchmarks.py` recalibra os dois casos de digitação,
com os pacotes completos anteriores; a rodada final sem essa opção repete os
43 cenários iniciais. Os demais resultados iniciais ficam preservados na etapa 00.
O driver de digitação abre a sessão depois da leitura do documento; o autosave
aguarda a publicação, não somente o retorno da solicitação.

`docs/desempenho_editor/etapa-11/consolidar.py` audita os resultados preservados
da etapa, compara entradas, fontes, viewport e identidades, e gera as tabelas.
Não executa testes nem substitui a validação manual nativa descrita no relatório.


## Seleção — etapa 01

Os oito cenários desta etapa podem ser repetidos sem executar a bateria inteira:

```bash
.venv/bin/python tests/performance/benchmark_editor.py --output /tmp/fornax-selecao --label depois --case select_all-20 --case select_all-60 --case select_all-200 --case select_group-mixed-60 --case select_layers-mixed-60 --case select_area-mixed-60 --case select_tree-connected-40 --case select_area-connected-40
.venv/bin/python tests/performance/run_selection_checks.py --theme dark
.venv/bin/python tests/performance/run_selection_checks.py --theme light
```

`run_selection_checks.py --evidence <arquivo.json>` guarda estados e hashes de
pixels. `compare_selection_evidence.py <antes.json> <depois.json>` exige igualdade
exata. `--behavior-only` executa os contratos existentes antes da otimização,
sem exigir a API de lote introduzida nesta etapa.

Para repetir uma referência isolada, ambos os instrumentos aceitam
`--reference-editor <pasta>`, contendo os três módulos anteriores
`editor_window.py`, `frontend.py` e `organogram_editor.py`. A importação fica
restrita ao processo do teste. O benchmark registra os hashes desses módulos
como parte do produto medido; não altera os arquivos do projeto. Os outros
arquivos precisam coincidir com a referência. O patch e a verificação de
reconstituição estão em `docs/desempenho_editor/etapa-01/`.

A seleção pela árvore cobre vinte blocos, incluindo descendentes, com uma
operação no modelo de seleção. O intervalo de linhas de nível superior não
representa uma seleção de todos os nós de uma árvore hierárquica.

## Camadas — etapa 02

```bash
.venv/bin/python tests/performance/run_layer_checks.py --theme dark
.venv/bin/python tests/performance/run_layer_checks.py --theme light
.venv/bin/python tests/performance/benchmark_editor.py --output /tmp/fornax-camadas --label depois --case layers-20 --case layers-60 --case layers-200 --case layer_rename --case layer_text --case layer_hide --case layer_lock --case layer_add --case layer_delete --case layer_group --case layer_ungroup --case layer_reorder --case layer_cycles
```

`run_layer_checks.py` aceita `--evidence`, `--behavior-only` e
`--reference-editor` com os mesmos critérios do instrumento de seleção.
Os identificadores do pequeno organograma visual são fixos, para não comparar
UUIDs aleatórios como se fossem uma diferença do produto.

Os dez comandos locais usam uma página mista de 60 objetos; reordenação começa
com uma camada fora do topo. `layer_cycles` mede dez atualizações da lista como
uma operação. A edição começa com o editor de texto aberto, fora do cronômetro,
e termina pela conclusão real da edição. Visibilidade e bloqueio acionam os
botões da linha. As contagens de `ElidedLayerLabel.__init__` indicam novas linhas,
e `LayerGroupBadge.__init__` indica novos badges; não são um total de todas as
alocações nativas do Qt. A retenção verifica a validade das linhas e widgets
originais, além da associação atual entre eles.


## Conectores, propriedades e recortes — etapa 03

```bash
.venv/bin/python tests/performance/run_board_checks.py --theme dark
.venv/bin/python tests/performance/run_board_checks.py --theme light
.venv/bin/python tests/performance/benchmark_editor.py --output /tmp/fornax-quadro --label depois --case board_drag_1-20 --case board_drag_4-20 --case board_drag_10-20 --case board_drag_1-40 --case board_drag_4-40 --case board_drag_10-40 --case board_color --case board_opacity --case board_width --case board_radius --case board_ports --case board_border_color --case board_border_opacity --case board_border_width --case board_border_radius --case board_text_move --case board_text_edit --case board_cutouts
.venv/bin/python tests/performance/compare_board_evidence.py docs/desempenho_editor/etapa-03/estados-antes.json docs/desempenho_editor/etapa-03/estados-depois.json
.venv/bin/python tests/performance/compare_board_evidence.py docs/desempenho_editor/etapa-03/estados-antes-claro.json docs/desempenho_editor/etapa-03/estados-depois-claro.json
```

Os seis arrastes de `board_input.py` usam o caminho nativo de eventos da view:
selecionar, ajustar zoom, estabilizar eventos, pressionar, mover e soltar. A
pressão vem **depois** da estabilização, para não provocar uma soltura perdida
artificial. Cada amostra mede um evento de movimento e a soltura, com pintura e
conclusão dos eventos; não um gesto de vários movimentos. O teste exige que
1/4/10 blocos se movam pelo mesmo deslocamento não nulo. Os deslocamentos variam
por repetição e são iguais antes/depois; a restauração da cena fica fora do tempo.

Propriedades, textos e recortes usam 40 blocos conectados. O caso de portas pode
não precisar pintar ao apenas habilitar um lado; ele aguarda os eventos, sem
exigir uma pintura artificial. Os casos de texto criam uma caixa normalizada
sobre os conectores; `board_text_edit` começa já em edição. `board_cutouts`
exercita seleção e pintura com cache aquecido. Os testes também verificam cache
vazio, invalidação após mudança, remoção, destruição nativa e troca de cena.

`run_board_checks.py --evidence <arquivo.json>` guarda 23 estados: documentos,
SHA-256 dos pixels, coordenadas brutas dos caminhos e limites. `--behavior-only`
executa os seis contratos que já passam na referência; os outros sete verificam
a redução de trabalho e a invalidação da nova implementação. O comparador exige
pixels e documentos exatos, topologia exata e diferenças geométricas de no máximo
1e-10 unidades da cena, para ruído de ponto flutuante; imprime o maior delta.
Não aplica tolerância às imagens. Os 13 testes rodam nos temas claro e escuro.

O manifesto depois registra a versão inicial do comparador auxiliar, acrescentado
após a referência. A versão usada na comparação final foi ajustada após o
benchmark e está identificada em `verificacao-comparacao.json`. Driver, fixtures,
benchmark e todos os instrumentos preexistentes mantiveram os hashes antes/depois.
`visual_cache_bytes` mede caches raster existentes, não os novos caminhos vetoriais;
RSS inclui todos os recursos do processo. A referência anterior está identificada
pelo patch exclusivo de cinco arquivos e sua verificação. `--reference-editor`
isola somente módulos do editor e não substitui os arquivos de `core` ou
`canvas_items`: sozinho não reconstitui esta referência. Inverta o patch numa
cópia isolada ao repetir a referência completa, preservando a árvore em uso.

A rodada de 100 blocos foi interrompida por duração antes da referência oficial;
não consta entre os cenários aprovados. As evidências oficiais de desempenho são
dos quadros de 20 e 40 blocos. Backend nativo e ponteiro físico continuam como
validação complementar.


## Texto — etapa 04

```bash
.venv/bin/python tests/performance/run_text_checks.py --theme dark
.venv/bin/python tests/performance/run_text_checks.py --theme light
.venv/bin/python tests/performance/probe_text_metrics.py --output /tmp/fornax-metricas-texto.json
.venv/bin/python tests/performance/benchmark_editor.py --output /tmp/fornax-texto --label depois --case typography_type-60 --case typography_type-1200 --case typography_paste-60 --case typography_paste-1200 --case typography_resize --case typography_resize_four --case typography_format --case typography_reapply --case load_text-60 --case load_text-200 --case load-personnel --case load-internship-certificate --case load-identification-prism --case load-formal-invitation
.venv/bin/python tests/performance/compare_text_evidence.py docs/desempenho_editor/etapa-04/estados-antes.json docs/desempenho_editor/etapa-04/estados-depois.json
.venv/bin/python tests/performance/compare_text_evidence.py docs/desempenho_editor/etapa-04/estados-antes-claro.json docs/desempenho_editor/etapa-04/estados-depois-claro.json
```

São oito operações aquecidas (duas preparações, vinte amostras) e seis
carregamentos frios (cinco sessões novas). Os sufixos `60` e `1200` nos casos
`typography` escolhem a entrada curta de um parágrafo ou longa de trinta
parágrafos; não são uma contagem exata de caracteres. As entradas incluem fontes,
tamanhos e ênfases mistas, acentos, emoji e símbolo fora do BMP.

Digitar usa sete teclas reais do Qt (` equipe`); colar aciona Ctrl+V sobre o
clipboard isolado do Qt offscreen, com um ou vinte trechos de texto Unicode.
Seleção/estado inicial são capturados antes de abrir a edição: a leitura do
documento público encerra a interação. A verificação exige sessão ativa e HTML
sincronizado **antes** dessa leitura final. Assim não mede apenas um QTextCursor
alterando o documento visual fora da sessão do editor. O redimensionamento
coletivo usa a sessão real de quatro textos e exige a largura final multiplicada
por 1,2. A cena é restaurada fora do cronômetro; pintura e eventos finais entram
no tempo. O carregamento começa com editor vazio em uma sessão nova, sem prometer
cache vazio do sistema operacional.

`probe_text_metrics.py` conta consultas ao cursor e construções de QFontMetrics
em rodada separada; não modifica o trecho temporizado. Os dois probes e o teste
específico preservam os hashes em `instrumentos-adicionais-antes.json` e no
relatório de verificação. Os instrumentos usados no tempo mantêm os mesmos hashes
antes/depois. O comparador e o probe foram acrescentados durante a referência,
após o manifesto inicial; essa diferença de catálogo não altera o benchmark.

`run_text_checks.py --behavior-only` executa os sete contratos anteriores à
implementação; o modo completo acrescenta seis verificações da redução de
trabalho, métricas locais, lotes aninhados/exceções e sinais não bloqueados.
`--evidence <arquivo.json>` registra vinte estados por tema, incluindo os quatro
modelos aprovados. PDF exige Poppler (`pdftoppm`) para renderizar os pixels; sem
Poppler esse contrato é explicitamente pulado. Os PDFs e suas imagens ficam numa
pasta com o mesmo nome do JSON, sem a extensão. O comparador exige igualdade exata
do estado, da geometria e dos pixels **em cada canal**, sem tolerância. Os casos
sintéticos também exigem igualdade entre texto do editor, prévia e PNG na mesma
escala; PDF é comparado a sua referência PDF, pois usa outro dispositivo.

O cache de métricas existe somente dentro de uma chamada a `text_geometry`; não
retém texto, documentos, snapshots ou posições entre chamadas. `visual_cache_bytes`
continua medindo os caches raster existentes e não esse pequeno cache temporário.
A referência integral pode ser reconstituída invertendo o patch exclusivo de três
arquivos em uma cópia isolada; `--reference-editor` sozinho não substitui
`canvas_items`, `canvas_edit` ou `core/text_layout.py` e não reproduz esta etapa.

## Colagem e duplicação — etapa 05

```bash
.venv/bin/python tests/performance/run_copy_checks.py --theme dark
.venv/bin/python tests/performance/run_copy_checks.py --theme light
.venv/bin/python tests/performance/compare_copy_evidence.py docs/desempenho_editor/etapa-05/evidencia-antes-dark.json docs/desempenho_editor/etapa-05/evidencia-depois-dark.json
.venv/bin/python docs/desempenho_editor/etapa-05/verificar_controles.py --output /tmp/controles-copias.json
.venv/bin/python tests/performance/benchmark_editor.py --output /tmp/fornax-copias --label depois --case copy_paste-1-20 --case copy_paste-10-20 --case copy_paste-50-20 --case copy_paste-1-60 --case copy_paste-10-60 --case copy_paste-50-60 --case copy_paste-1-200 --case copy_paste-10-200 --case copy_paste-50-200 --case copy_cross --case copy_duplicate_plain --case copy_duplicate_mask --case copy_duplicate_group --case copy_duplicate_board
```

São 14 operações aquecidas, cada uma com duas preparações, vinte amostras e
uma rodada separada de profiler. Restauração da cena e preparação do clipboard
ficam fora do cronômetro; pintura e estabilização de eventos entram no tempo.
Os destinos têm 20 textos ou 60/200 objetos mistos. O clipboard de 1/10/50 textos
é preparado a partir de dados completos obtidos pelo comando real de copiar,
com identidades e posições distintas; assim é possível medir 50 cópias num
destino com apenas 20 objetos. Não se mede a importação de clipboard externo.

`copy_cases.py` fixa somente a fonte de UUIDs durante as ações e a ordem dos
quatro conjuntos no clipboard de teste, que a enumeração da seleção do Qt não
garante. As identidades novas continuam distintas. Todos os cenários exigem a
quantidade esperada de cópias e exatamente uma ação de histórico. O JSON inclui
hash do clipboard, documento final, widgets/objetos retidos e contagens de
construção; `QImageReader.read` ausente no perfil significa zero chamadas.

`run_copy_checks.py --behavior-only` executa nove contratos e registra 21 estados
por tema. O modo completo acrescenta seis verificações de trabalho e segurança:
preservação de objetos/widgets, seleção final única, pixels autorizados nas
duplicações, referências fortes durante máscaras e descarte do papel da cena.
Guias são ordenadas somente na evidência porque não possuem ordem semântica;
a comparação de undo/redo também normaliza z pela ordem das camadas, como a
restauração anterior já fazia. Os estados entre versões preservam os valores z
reais e exigem pixels idênticos, sem tolerância.

O papel foi corrigido após a primeira validação posterior revelar falha nativa;
o teste específico foi acrescentado nessa investigação. Sua execução na cópia
anterior está registrada como falha esperada. Os instrumentos temporizados não
mudaram. As fontes anteriores podem ser recuperadas pelo patch exclusivo de
`editor_window.py`, `organogram_editor.py` e `controls.py`; os manifestos permitem
conferir a recuperação exata por SHA-256.

## Captura de histórico — etapa 07

```bash
.venv/bin/python tests/performance/run_history_checks.py --theme dark --evidence /tmp/fornax-historico-dark.json
.venv/bin/python tests/performance/run_history_checks.py --theme light --evidence /tmp/fornax-historico-light.json
.venv/bin/python tests/performance/benchmark_history.py --output /tmp/fornax-historico --label depois
.venv/bin/python docs/desempenho_editor/etapa-07/verificar_comparacao.py
```

São doze cenários, vinte amostras por cenário e duas preparações, em processos
sequenciais com dados/configurações temporários e Qt offscreen em escala 1.
A preparação reconstrói a mesma cena e aquece o snapshot antes de cada amostra;
seu tempo não entra na medição. O intervalo contém a operação e o processamento
de eventos/pintura. A verificação posterior compara documento, estados completos
do histórico, índice, orçamento em bytes, disponibilidade de undo/redo, botões e
pixels efetivamente pintados. A rodada de perfil é separada dos tempos.

Cobre chamadas sem alteração em páginas simples/frente e verso, conjuntos
conectados e um conjunto com 2.500 cartões; chamada após undo; movimento que
retorna à origem; mudança de posição; edição numérica sem `editingFinished`; e
estilo do contorno do organograma. Os contratos complementam com texto, formas,
imagens, assinaturas, guias, máscaras, páginas inativas, estrutura do documento,
novas edições após undo, fechamento e reescrita de referências de assets.

`--case snapshot-60 --samples 2` é uma sondagem do instrumento, não o resultado
final. `--behavior-only` repete os quinze contratos de comportamento na referência.
Os dois contratos `--work-only` falhavam antes, pois ainda havia capturas completas
sem alteração; passam na versão otimizada. Repetições por tema não aumentam o
número de testes distintos. A auditoria exige vinte amostras e estados/pixels
idênticos, verifica os instrumentos e fontes, e reverte o patch em pasta temporária
para recuperar os hashes anteriores. A referência deve ser recriada em uma cópia
isolada do projeto, preservando as alterações da pasta de trabalho.

## Referência antes de implementar tabelas

O plano está em `docs/PLANO_IMPLEMENTACAO_TABELAS.md`. A etapa 00 registra
os processos existentes; não implementa nem mede uma tabela do editor.

```bash
.venv/bin/python tests/performance/table_fixtures.py --check
.venv/bin/python tests/performance/run_table_baseline.py --output /tmp/fornax-tabelas-referencia --label antes
```

`table_fixtures.py` gera e confere quatro especificações sintéticas em
`tests/fixtures/tables/`. Elas não usam o schema do aplicativo nem podem ser
importadas como modelos. Contêm medidas, conteúdo, mesclagens planejadas,
registros fictícios e expectativas de aceitação para o protótipo futuro.

`run_table_baseline.py` executa quinze cenários existentes, em sequência:
sete da rodada Pareto; cinco de digitação, colagem, duplicação e troca de
páginas; três de histórico. Reutiliza os drivers atuais, incluindo suas
verificações de estado/pixels e rodadas de perfil separadas. Ações curtas
usam vinte amostras aquecidas; os sete casos caros usam cinco amostras.

Os drivers isolam processos, preferências e dados sintéticos. O runner força
escala 1 e registra seus comandos, retornos e hashes dos instrumentos. Não
executar suítes pesadas durante as medições. Repetir com `--label depois` em
outra pasta para comparar as operações antigas após implementar tabelas;
preservar os arquivos originais da referência antes de qualquer repetição.

As evidências da primeira execução, o mapa confirmado e a cópia dos fontes
anteriores estão em `docs/implementacao_tabelas/etapa-00/`. Não confundir o
arquivo de fontes com uma cópia completa do ambiente: assets e dependências
ficam identificados separadamente e os modelos pessoais não são copiados.

## Tabelas — dados e persistência (etapa 02)

```bash
.venv/bin/python tests/performance/run_table_data_checks.py --output /tmp/fornax-tabelas-dados.log
.venv/bin/python tests/performance/benchmark_table_data.py --output /tmp/fornax-tabelas-dados.json
```

O runner usa processos, dados e preferências temporários. Confere contrato e
operações puras, versões, campos/camadas, pacotes públicos/protegidos,
snapshots de recuperação e abertura atômica no editor, além do
protótipo e dos contratos de publicação já existentes. Exceções Qt também
reprovam a rodada. A regressão geral continua no `run_regressions.py`.

`table_document_fixtures.py` adapta as quatro especificações sintéticas da
etapa 00 para documentos v6 somente em memória/pastas temporárias. Não
modifica a biblioteca do aplicativo. `benchmark_table_data.py` mede dados
síncronos com duas preparações e vinte amostras por caso; memória Python é
medida em rodada separada. Não mede pintura nem digitação no canvas.

`--reference-source /caminho/model_document-anterior.txt` executa apenas a
normalização v4 contra uma cópia local histórica do módulo. Essa comparação
é uma reconstrução isolada da referência, não uma medição de tabelas antigas.
O teste do leitor anterior usa a mesma evidência local e registra um skip
quando ela não existir em outro checkout. Relatório e contrato estão em
`docs/implementacao_tabelas/etapa-02/`; resultados brutos permanecem ignorados.

## Tabelas — layout, variáveis e saída (etapa 03)

```bash
.venv/bin/python tests/performance/run_table_render_checks.py --output /tmp/fornax-tabelas-render
.venv/bin/python tests/performance/run_table_render_evidence.py --output /tmp/fornax-tabelas-evidencias
```

O primeiro runner executa os mesmos 27 testes de renderização nas escalas Qt
1 e 2, isolando preferências/dados. Exercita células e mesclagens, formatação
de placeholders, campos ausentes, cache estático, camadas, fontes, documentos
públicos/protegidos e workers reais. A integração da cena é verificada
separadamente pelos testes da etapa 04.

O segundo instrumento gera PNG e PDF vetorial sintéticos. O Poppler rasteriza
o PDF em 300 dpi; comparam-se caixas de tinta por célula, cores, tamanho físico
e texto extraído. O PDF de prova usa a mesma escala física do organograma.
`QPageSize` quantiza a página em pontos inteiros; não redistribuir o desenho
para compensar essa pequena diferença. O PDF por item/folha do aplicativo
continua com seu pipeline raster existente.

Em seguida, o instrumento compara sequencialmente o protótipo da etapa 01 e
o layout de produção com 800 células, duas preparações e vinte amostras.
Construção + primeira pintura e pintura de um layout retido são medidas
separadamente. O protótipo é uma referência técnica isolada, não uma versão
anterior de tabelas utilizáveis no aplicativo. Memória RSS inclui o processo
Qt e seus caches; não representa alocação exclusiva da tabela. Executar a
medição sem outras suítes pesadas concorrentes.

Relatório: `docs/implementacao_tabelas/etapa-03/RELATORIO.md`. Logs, PDF, PNG,
JSON e fontes históricos ficam locais/ignorados; apenas documentação e
instrumentos devem ser versionados. O módulo de teste usa `pypdf` já presente
no ambiente de desenvolvimento e o Poppler disponível na máquina.

## Tabelas — canvas e edição (etapa 04)

```bash
.venv/bin/python tests/performance/run_table_canvas_checks.py --output /tmp/fornax-tabelas-canvas
.venv/bin/python tests/performance/benchmark_table_canvas.py --output /tmp/fornax-tabelas-canvas-desempenho.json
```

O runner executa os mesmos 25 testes nas escalas Qt 1 e 2, com dados e
preferências temporários. Usa eventos nativos para clique/arraste, foco,
teclado e composição Unicode; verifica células mescladas, atalhos por
contexto, pintura parcial, limites, histórico local/global, páginas e
recuperação da célula ativa em pacotes públicos e totalmente protegidos.
Exceções de callbacks Qt e descarte de objetos reprovam os testes.

O benchmark usa uma tabela sintética de 800 células, sem ler modelos
pessoais. São duas preparações e vinte amostras por operação. Mede pintura
completa/parcial diretamente no item retido; seleção/movimento, digitação
e checkpoint incluem processamento de eventos da janela real. Não medir
enquanto outras suítes pesadas estiverem rodando. A restauração da célula
e a abertura da sessão ficam fora do tempo do checkpoint. RSS abrange todo
o processo, incluindo janela, histórico e caches Qt.

Confere a identidade do layout/documentos não afetados e que digitar não
cria snapshots por tecla. O checkpoint inclui validação e captura completa
de histórico; não representa o custo de cada caractere. Registra amostras,
mediana, p95, hashes dos fontes/instrumento e da especificação da fixture.
O recurso não existia antes desta etapa: a comparação do relatório é entre
a implementação inicial da etapa 04 e seu recorte de pintura, não entre
tabelas de duas versões públicas do programa.

Inserção pelo menu e painel de propriedades pertencem à etapa 05; cópia de
intervalos/objetos, duplicação e integração completa de camadas/histórico
seguem as etapas 05/06. Relatório: `docs/implementacao_tabelas/etapa-04/RELATORIO.md`.

## Tabelas — controles e intervalos (etapa 05)

```bash
.venv/bin/python tests/performance/run_table_controls_checks.py --output /tmp/fornax-tabelas-controles
.venv/bin/python tests/performance/table_controls_evidence.py --output /tmp/fornax-tabelas-visual
.venv/bin/python tests/performance/benchmark_table_controls.py --output /tmp/fornax-tabelas-controles-desempenho.json
```

O runner executa 11 testes de intervalos/dados e 16 testes de interface,
estes repetidos nos temas dark/light e nas escalas Qt 1/2. Os processos usam
preferências temporárias. Exercita inserção pública/cancelamento, limites,
tipografia e fundo por seleção, estilos mistos, medidas, contornos,
operações estruturais com undo/redo e clipboard por contexto. Inclui
colagem inválida sem efeitos parciais, texto multilinha durante edição e
texto literal semelhante a HTML, mantendo a recusa de recursos externos.
Callbacks Qt e descarte tardio de wrappers também reprovam.

O segundo script captura um boletim sintético e o painel Tabela nos dois
temas, sem ler modelos pessoais. PNGs ficam locais/ignorados. Capturas
offscreen não substituem testes de foco/touchpad no desktop real.

Para comparar com a etapa 04, o mesmo `benchmark_table_canvas.py` mede as
mesmas 800 células e operações, sem suíte pesada concorrente. Conferir
viewport/hashes/fixture e distinguir custo de pintura, eventos e histórico.
Relatório: `docs/implementacao_tabelas/etapa-05/RELATORIO.md`.


## Tabelas — objetos, camadas e histórico (etapa 06)

```bash
.venv/bin/python tests/performance/run_table_integration_checks.py --output /tmp/fornax-tabelas-integracao
.venv/bin/python tests/performance/benchmark_table_integration.py --output /tmp/fornax-tabelas-historico.json
```

O runner executa 20 testes distintos de integração, nos temas claro/escuro
e escalas Qt 1/2, com dados/preferências temporários. Verifica identidade e
independência de cópias, cópia entre páginas, grupos mistos e seleção parcial
pelas camadas, ordenação, controles de visibilidade/bloqueio/nome, geometria
e recusas sem efeitos parciais. Exercita texto ativo, formatação, mesclagem,
inserção de coluna, duplicação, troca de página, gravação/reabertura pública,
undo/redo, estado canônico e pixels do canvas contra o renderer.

O benchmark mede uma tabela sintética de 800 células: checkpoint sem
alterações e ciclo completo undo/redo de um preenchimento. Duas preparações
e vinte amostras, com eventos Qt, mediana/p95, RSS do processo e hashes dos
fontes. Execute sem testes/benchmarks pesados concorrentes. A restauração
ainda usa o fallback completo; o resultado não demonstra restauração
incremental ou desempenho de organogramas/exportações da etapa 07.

Para comparar o editor/painel já existente, repetir também
`benchmark_table_canvas.py` e `benchmark_table_controls.py`, separadamente.
Relatório: `docs/implementacao_tabelas/etapa-06/RELATORIO.md`.

Diagnóstico auxiliar de memória (não altera o editor):

```bash
.venv/bin/python tests/performance/check_table_history_memory.py --output /tmp/fornax-tabelas-memoria.json
```

Registra referências fracas a raízes/layouts antigos e RSS em um lote de
undo/redo sem descarte explícito e com `DeferredDelete`/coleta Python entre
operações. Serve para distinguir retenção transitória do lote offscreen de
objetos ainda vivos; RSS alto sozinho não demonstra vazamento permanente.

## Tabelas — integração de produto (etapa 07)

```bash
.venv/bin/python tests/performance/run_table_product_checks.py --output /tmp/fornax-tabelas-produto
.venv/bin/python tests/performance/benchmark_table_product.py --output /tmp/fornax-tabelas-produto.json
```

O runner executa 19 testes distintos em escalas Qt 1/2, com biblioteca,
preferências e modelos sintéticos temporários. Cobre limites/caches do
organograma, Página 1 replicada em 1.000 cartões/20 conjuntos, prévia vazia,
PNG/PDF, lote, frente/verso, múltiplos por folha e remontagem exata de
ladrilhos. Exercita importar/exportar, duplicar/renomear/reabrir, miniatura
de revisão atual, recuperação de texto ativo e corridas de fechamento,
salvamento, publicação, alteração externa e expiração de autorização.
Verifica snapshot independente de geração e transporte/importação protegida.

O benchmark mede o cálculo leve de geometria com/sem tabela complementar
de 800 células e construção/pintura de prévia real de 1.000 cartões com
tabela de uma célula. Duas preparações, vinte amostras curtas/cinco caras,
mediana/p95, RSS e hashes. Confere também se os limites calculados estão
corretos; uma referência rápida que ignora a tabela não prova otimização.
Execute sem suites/benchmarks pesados concorrentes. Não é medição de 1.000
blocos individuais, impressão nativa ou exportação de 1.000 imagens em disco.
Relatório: `docs/implementacao_tabelas/etapa-07/RELATORIO.md`.

## Tabelas — ajuda, idiomas e fechamento (etapa 08)

```bash
.venv/bin/python tests/performance/run_table_help_checks.py --output /tmp/fornax-tabelas-ajuda
QT_SCALE_FACTOR=1 .venv/bin/python tests/performance/table_final_evidence.py --output /tmp/fornax-tabelas-visual-1
QT_SCALE_FACTOR=2 .venv/bin/python tests/performance/table_final_evidence.py --output /tmp/fornax-tabelas-visual-2
```

O runner verifica 21 testes distintos de ajuda e idiomas, repetidos nas
escalas Qt 1/2, com preferências e dados temporários. Inclui os 416 tópicos
públicos, links, seções, busca pelos nomes antigos/novos, os 14 artigos de
tabelas, literais traduzíveis e mensagens operacionais fixas, preservação
dos campos de formatação e uso dos arquivos QM pelos controles reais.
Inglês e espanhol traduzem a interface; a ajuda mantém o conteúdo em
português, seguindo o fallback atual.

O segundo script gera 20 capturas por escala: três idiomas, dois temas,
zooms 0,5/1,5, painel Tabela completo e ajuda. Usa a fonte Inter distribuída
e uma célula em DejaVu Sans. Os campos longos demonstram também os
indicadores de overflow; o zoom alto recorta naturalmente o viewport.
Não lê modelos pessoais. As capturas offscreen não comprovam o foco,
touchpad ou renderização nativa de outros sistemas.

Para reproduzir a regressão final completa, executar também os runners de
regressão (`--include-contracts`), dados, canvas, renderer, controles,
integração e produto documentados acima. Somar módulos distintos, sem
contar repetições de tema/escala como testes novos.

Traduções usam o contexto vazio de `core.i18n.tr`. Manter chamadas com
literais nas ações evita perder textos na extração pelo `pyside6-lupdate`.
Validar os `.ts` e compilar para `.qm` com `pyside6-lrelease` após editar.
Mensagens diagnósticas dinâmicas da validação podem permanecer em português;
o núcleo de dados continua independente do Qt.

Relatório: `docs/implementacao_tabelas/etapa-08/RELATORIO_FINAL.md`.

## Tabelas — seleção, arraste e alças

```bash
.venv/bin/python tests/performance/run_table_interaction_checks.py --output /tmp/fornax-tabelas-interacao
```

Executa 36 testes distintos nos temas claro/escuro e escalas Qt 1/2,
com dados/preferências isolados. Exercita clique no interior transparente,
arraste pelo corpo, entrada na seleção de células, alças de canto/lateral
com rotação e histórico, recusa de medidas sem mover a âncora, texto ativo,
seleção múltipla/bloqueio, criação no contexto de objeto, medidas da barra
superior, magnetismo de grupos e cancelamento de ponteiro. Verifica também
o recolhimento imediato e bloqueio de seções indisponíveis, inclusive
durante animação ou tentativa programática de expansão.

Inclui a barra flutuante de tabela, seus menus reais, preservação de foco e
texto ativo, cancelamento e troca de alvo, quadro/organograma, canvas estreito,
zoom/rolagem/rotação, seleção suave sem alterar o documento e encontros de
contornos grossos/translúcidos, conservando as fronteiras ocultas das mesclagens.

O encaixe, recolhimento e aparência da barra incluem treze testes de arraste pelas quatro posições,
orientação horizontal/vertical, três destinos destacados, seleção/texto/foco
preservados e cancelamento por Esc, botão solto, desativação, perda de captura
e troca de página. Verificam também fundo com 75% de opacidade, botões opacos nos
dois temas, a mesma espessura/cantos arredondados nos seletores de alinhamento,
fundo dos seletores com 75% de opacidade e transparência dos destinos (fundo cinza
de aproximadamente 35% normalmente e 50% sob o mouse), recolhimento pela
extremidade direita/inferior, expansão, arraste da barra recolhida e digitação
preservada. Compara os destinos antes/depois de recolher a barra, inclusive com
zoom, rotação e deslocamento da tabela. Verifica destaques limitados à largura/altura
da tabela, sem sobreposição em torno de uma tabela visível, mantendo o tamanho
normal das ferramentas após soltar, tanto abertas quanto recolhidas.
O lado permanece durante a sessão, sem entrar no histórico do documento.
Para capturas das quatro posições, abertas/recolhidas, e dos destinos nos dois temas:

```bash
.venv/bin/python tests/performance/table_controls_evidence.py --docking --output /tmp/fornax-tabelas-encaixe-visual
```

Os atalhos mínimos de retângulos/círculos, agrupamento e conexão de blocos
reutilizam a estrutura de encaixe da tabela. A verificação específica fica em:

```bash
PYTHONPATH=tests QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest test_object_floating -v
```

São quinze testes: contextos permitidos/excluídos, cor/contorno/opacidade com
undo/redo, cancelamento e troca de alvo, máscaras sem apagar imagens, agrupamento,
conexão de blocos e encaixe/recolhimento sem histórico. Inclui recusa de ação
antiga sobre outra seleção ou imagem removida da cena, seleção de imagem no
canvas/em Camadas, cancelamento com Esc e atalho de imagem variável com histórico.
O fluxo de máscara também recebe cliques pela `QWindow`, antes do encaminhamento
ao widget, para cobrir a entrega de eventos que os cliques diretos de `QTest`
em widgets não exercitam. Esse teste continua usando o backend offscreen.
Inclui os botões flutuantes de Cancelar/Concluir no enquadramento: confirmação
com undo/redo, cancelamento de máscaras novas/existentes e posição junto à forma,
com zoom e a preferência de barra recolhida preservada.
Preferências/dados pessoais
ficam isolados pelos fixtures; os widgets não são adicionados à cena/exportação.

A regressão complementar usa os runners de canvas, controles, integração,
renderer, ajuda e `run_regressions.py --include-contracts`. O teste de
captura de integração exige continuar evitando checkpoints completos sem
mudanças e recusar atributos persistentes desconhecidos; as novas alças
e os dados de ponteiro são apresentação, não conteúdo salvo.
