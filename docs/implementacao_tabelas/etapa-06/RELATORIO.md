# Tabelas — etapa 06: objetos, camadas, grupos e histórico

09/10/2026. Integração da tabela gráfica aos caminhos de objetos inteiros do
editor. Dados sintéticos; modelos pessoais e assets existentes preservados.

## O que mudou

- Tabelas participam de seleção múltipla, agrupamento/desagrupamento,
  rotação, transparência, medidas e transformação da seleção. São incluídas
  no cálculo da próxima camada de objetos novos. Nome, visibilidade,
  bloqueio, exclusão e ordenação usam a lista de camadas existente.
- A seleção pelo canvas continua expandindo o grupo; a seleção parcial
  pela lista de camadas continua permitida. Não houve mudança na regra
  aprovada de movimento/ordem dos grupos.
- Botão Duplicar e `Ctrl+D` na grade duplicam a tabela inteira, inclusive
  quando existe uma seleção de células. Durante digitação, o editor de
  texto conserva seu contexto e seus atalhos. Duplicação preserva os
  clipboards internos anteriores.
- Cópia/colagem de objetos inclui tabelas e seleções mistas, mantendo a
  sequência de camadas. Cada cópia recebe novos IDs de tabela/células,
  camada, nome e grupo; conteúdo e estilos são cópias independentes.
  Colagem entre páginas conserva o documento v6 e a origem.
- Copiar um intervalo continua produzindo MIME interno validado e TSV.
  Para copiar a tabela inteira, selecione sua camada/moldura ou use `Esc`
  para sair da edição e da seleção interna, mantendo o objeto selecionado.
  `Delete` em células limpa conteúdo; fora da seleção interna exclui o objeto.
- A página candidata é validada com as páginas inativas antes de inserir
  objetos ou reordenar a cena. Excesso de células/conteúdo é recusado sem
  alteração parcial. Uma duplicação recusada conserva o texto em edição,
  o editor temporário, a seleção e o histórico.
- Redimensionamento conserva a distribuição proporcional das linhas e
  colunas, sem escalar fonte, padding ou contornos. Geometria inválida é
  recusada antes de publicar; o grupo inteiro permanece intacto. A edição
  temporária é encerrada ao iniciar um gesto de redimensionamento de objetos.
  O quadro de transformação acompanha as mudanças de geometria da tabela.
- Renomeação valida o nome antes de alterar a tabela. Uma tentativa inválida
  não deixa uma camada impossível de salvar. Grupos agora aceitam os IDs
  numéricos usados pelo editor; `keep_proportion` é opcional e persistido.
- Corrigida uma falha preexistente na captura de redimensionamento de textos
  recém-criados: `TextState` pode ainda não ter `rich_text_version`. O padrão
  legado é usado quando esse atributo não existe.

## Histórico e cenas

A captura rápida lê todos os dados persistentes da tabela, além de nome,
grupo, camada, proporção, posição, rotação, opacidade, visibilidade e bloqueio
nativos. Não usa somente uma revisão ou hash do layout para afirmar que o
conteúdo não mudou. Mutações diretas no dicionário também são detectadas.
Uma célula ativa ou propriedade/tipo não coberto exige a captura completa.
Mudanças globais e de páginas inativas continuam invalidando a comparação.

**A restauração permanece completa.** Não foi introduzido um caminho
incremental que pudesse omitir células ou assumir equivalência apenas pela
geometria. Undo/redo restaura conteúdo, estilos, mesclagens, medidas, IDs,
grupos, ordem e páginas. O cache Qt permanece uma representação de desenho.
O custo desse fallback é registrado nas medições; esta etapa não promete
undo/redo instantâneo para tabelas densas.

A retenção de cenas já contabilizava HTML e estimativa de memória por
`QTextDocument`. Isso foi mantido e verificado: a edição temporária termina
antes da troca de página, o descarte tardio do Qt não deixa um editor na cena
retida, e o orçamento pode forçar reconstrução. Alterações na página inativa
invalidam a cena antiga; o conteúdo salvo continua sendo a autoridade.

## Verificação funcional

| Conjunto | Testes distintos | Resultado |
|---|---:|---|
| Regressões anteriores e contratos do editor | 209 | Passaram antes/depois |
| Dados, persistência, protótipo e recuperação | 62 | Passaram antes/depois |
| Renderer de tabelas | 27 | Passaram antes/depois, escalas 1/2 |
| Canvas, texto e foco | 25 | Passaram antes/depois, escalas 1/2 |
| Intervalos | 11 | Passaram antes/depois |
| Controles Texto/Tabela | 16 | Passaram antes/depois, temas claro/escuro, escalas 1/2 |
| Integração de objetos, grupos e páginas | 20 | Passaram nos dois temas e escalas 1/2 |

**370 testes distintos.** Repetições de tema/escala não aumentam a contagem.
Os testes novos reproduziram os bloqueios de cópia/duplicação e a exclusão da
tabela dos caminhos de agrupamento/transformação na referência anterior.
O instrumento inicial tinha uma fixture de 800 células com medidas
insuficientes; a fixture foi corrigida, sem relaxar limites de produção.
Essa rodada inicial não é usada como contagem comparável à suíte final.

A sequência combinada cobre digitar → formatar → mesclar → inserir coluna →
duplicar → trocar página → gravar/reabrir `.fornax` público → desfazer/refazer.
Compara o documento canônico antes/depois e, na página das tabelas, os pixels
do canvas com o renderer. Há verificações específicas de IDs independentes,
recusas atômicas, grupo misto, seleção parcial pelas camadas, texto ativo,
atalho de duplicação e invalidação das cenas retidas.

As suítes monitoram exceções em callbacks Qt e descarte de objetos nativos.
Os testes são Linux/offscreen com PySide6 6.11 e Python 3.13. Não substituem
validação nativa de foco/touchpad ou execução no Windows.

## Desempenho

As medições antes/depois usam o mesmo instrumento e fixture de cada caso,
sem suítes pesadas concorrentes, escala Qt 1, duas preparações e vinte
amostras. Os instrumentos registram mediana/p95, hashes dos fontes,
metadados e RSS do processo. Eventos e checkpoint/histórico estão incluídos
quando indicados. Nenhum teste foi removido para melhorar números.

### Canvas — 800 células

| Operação | Mediana antes → depois (ms) | Variação | p95 antes → depois (ms) |
|---|---:|---:|---:|
| Pintar 800 células | 35.98 → 44.91 | +24.8% | 39.87 → 53.39 |
| Pintar uma região de célula | 3.00 → 4.21 | +40.6% | 4.19 → 5.08 |
| Selecionar/mover com eventos | 18.95 → 21.78 | +14.9% | 49.33 → 61.44 |
| Digitar um caractere com eventos | 17.69 → 18.25 | +3.2% | 38.60 → 44.72 |
| Publicar célula + histórico/eventos | 156.13 → 182.77 | +17.1% | 205.42 → 213.82 |

### Painel — intervalo de 16 células em 800

| Operação | Mediana antes → depois (ms) | Variação | p95 antes → depois (ms) |
|---|---:|---:|---:|
| Preencher 16 células + histórico | 875.94 → 878.75 | +0.3% | 972.41 → 927.20 |
| Copiar 16 células MIME/TSV | 33.95 → 31.21 | -8.1% | 45.05 → 34.24 |
| Colar 16 células + histórico | 855.08 → 913.57 | +6.8% | 917.13 → 1035.01 |
| Cor do contorno + histórico | 894.71 → 866.97 | -3.1% | 971.78 → 935.90 |
| Medida de 4 colunas + histórico | 1278.59 → 1321.57 | +3.4% | 1410.40 → 1466.93 |

### Histórico — 800 células

| Operação | Mediana antes → depois (ms) | Variação | p95 antes → depois (ms) |
|---|---:|---:|---:|
| Checkpoint sem alterações + eventos | 49.17 → 8.87 | -82.0% | 53.54 → 11.78 |
| Ciclo undo/redo completo de preenchimento | 1618.78 → 1559.65 | -3.7% | 1831.69 → 1631.91 |

### Pioras, repetição e interpretação

- O ganho mais claro é o checkpoint sem alteração: **49,17 → 8,87 ms**, cerca de **82% menor**. A captura rápida evita normalizar/copiar novamente o documento quando a comparação completa dos dados da tabela comprova que nada mudou.
- A primeira medida de pintura ficou 24,8%/40,6% pior. Como o caminho de pintura e as fontes do layout não mudaram, foi feita uma repetição isolada, sem editar produção: pintura completa **37,62 ms**, região **3,00 ms**, seleção/movimento **18,84 ms** e digitação **17,79 ms**. A variação da máquina influencia os resultados; não há causa de código demonstrada para a piora da pintura. As duas rodadas permanecem registradas, sem substituir a primeira pela mais favorável.
- Publicar uma célula com histórico aumentou **156,13 → 182,77 ms**; na repetição, **171,17 ms**. A nova captura compara também todo o dicionário persistente da tabela antes/depois de um checkpoint, acrescentando trabalho. Essa é uma causa provável, não uma decomposição comprovada por perfilador. Não foi removida essa leitura para produzir um ganho artificial.
- Colagem interna aumentou **6,8%** e medidas de colunas **3,4%** na mediana; preenchimento ficou praticamente igual (+0,3%). A comparação adicional e os eventos de atualização do quadro de seleção podem contribuir, mas não foram isolados por operação.
- Copiar intervalos (-8,1%), contornos (-3,1%) e ciclo undo/redo (-3,7%) tiveram medianas menores. Esses caminhos não receberam uma reescrita destinada a acelerar essas operações; os ganhos pequenos não devem ser interpretados como garantia.
- A restauração densa ainda custa cerca de **1,56 s por ciclo undo + redo**. Operações de painel com histórico ficam aproximadamente entre **0,87 e 1,32 s** nesta fixture de 800 células. Portanto, a integração está correta, mas não é instantânea nesse tamanho.
- RSS do benchmark de canvas: **145,21 → 147,15 MiB**; painel: **213,73 → 215,91 MiB**. São leituras do processo, não o custo exclusivo de uma tabela. O benchmark de ciclos de histórico registrou cerca de **1.162 MiB** tanto antes quanto depois; o diagnóstico auxiliar de descarte Qt é apresentado abaixo.


### Memória e descarte tardio do Qt

O instrumento de tempo usa chamadas síncronas de undo/redo com
`processEvents()`, sem entregar explicitamente `DeferredDelete` entre elas.
No diagnóstico auxiliar, dez ciclos acumularam **20 raízes/layouts antigos**:
RSS passou de **141.10 para 584.35 MiB**. Após entregar `DeferredDelete` e coletar
Python, as **20 raízes e os 20 layouts foram liberados** (zero vivos).

O RSS ficou em **576.43 MiB**, em vez de voltar imediatamente ao inicial.
Mais dez ciclos com descarte entre operações terminaram em **563.12 MiB**,
novamente sem raízes/layouts antigos vivos. Isso evidencia retenção transitória
no lote offscreen. O RSS remanescente pode incluir memória conservada pelos
alocadores; o diagnóstico não identifica sua composição exata nem prova o
comportamento de todas as sessões nativas. Não se interpreta os 1.162 MiB do
benchmark como custo permanente de uma única tabela, nem como memória
normal de uso já comprovada. Nenhuma coleta forçada foi adicionada ao editor.

## Escopo e continuidade

Os limites continuam: 100 linhas/colunas, 1.000 posições por tabela, 20 tabelas
ou 2.000 posições por documento, 32 KiB HTML por célula, 512 KiB por tabela
e 1 MiB por documento. Mesclagens não reduzem o número de posições para
contornar o orçamento. Não foram instaladas dependências ou alteradas licenças.
Nenhum modelo pessoal ou asset foi substituído.

A etapa 07 continua pendente: integração de produto no organograma,
exportações, miniaturas/biblioteca e matriz completa de proteção/recuperação.
A etapa 08 inclui ajuda, revisão visual final e fechamento. A gravação pública
exercitada aqui não representa essa matriz completa.

## Reprodução e evidências

```bash
.venv/bin/python tests/performance/run_regressions.py --include-contracts --output /tmp/fornax-etapa06-regressoes.log
.venv/bin/python tests/performance/run_table_data_checks.py --output /tmp/fornax-etapa06-dados.log
.venv/bin/python tests/performance/run_table_render_checks.py --output /tmp/fornax-etapa06-renderer
.venv/bin/python tests/performance/run_table_canvas_checks.py --output /tmp/fornax-etapa06-canvas
.venv/bin/python tests/performance/run_table_controls_checks.py --output /tmp/fornax-etapa06-controles
.venv/bin/python tests/performance/run_table_integration_checks.py --output /tmp/fornax-etapa06-integracao
.venv/bin/python tests/performance/benchmark_table_canvas.py --output /tmp/fornax-etapa06-canvas.json
.venv/bin/python tests/performance/benchmark_table_controls.py --output /tmp/fornax-etapa06-controles.json
.venv/bin/python tests/performance/benchmark_table_integration.py --output /tmp/fornax-etapa06-historico.json
.venv/bin/python tests/performance/check_table_history_memory.py --output /tmp/fornax-etapa06-memoria.json
```

Executar os benchmarks separadamente das suítes. Logs, JSONs de medição e
auditoria ficam locais/ignorados, como definido no `.gitignore`. Este relatório,
o contrato, o plano e os instrumentos são arquivos revisáveis do projeto.
