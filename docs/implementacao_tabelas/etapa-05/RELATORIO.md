# Tabelas — etapa 05: inserção, painel e operações

09/10/2026. **Etapa concluída.** O recurso está disponível em
**Elementos → Tabela**, com quantidade inicial de linhas e colunas.
O painel Tabela fica abaixo de Texto e segue os títulos, divisores,
espaçamento, controles e cores do editor. Os modelos da biblioteca e os
331 assets existentes da referência permaneceram inalterados; foi
adicionado apenas um SVG próprio para o novo item do menu.

## Funcionalidades entregues

- O botão Formas passou a mostrar Elementos. Quadrado, círculo e linha
  continuam disponíveis, com os IDs internos anteriores. Descrição,
  tooltip e nome de acessibilidade incluem a tabela.
- A inserção valida os limites por tabela/documento antes de publicar o
  novo objeto. Cancelar o diálogo não modifica o modelo.
- Texto controla fonte, tamanho em pontos (inclusive fracionário),
  negrito, itálico, sublinhado, cor/opacidade, alinhamento horizontal e
  vertical e entrelinha. Durante edição, a formatação atua no cursor ou
  texto selecionado; fora dela, atua nas células selecionadas. As opções
  de justificado/recuo próprias das caixas não são apresentadas como
  funções da tabela.
- Tabela reúne adicionar linhas/colunas antes/depois, remover, mesclar,
  separar, dimensões totais, medidas das linhas/colunas selecionadas,
  espaçamento interno, quebra automática, preenchimento e contornos.
  Medidas são exibidas em milímetros. Cor, espessura, opacidade e
  visibilidade podem atuar nos contornos internos, externos ou em todos.
- Valores diferentes na seleção aparecem como **Vários**, campo vazio,
  alinhamento sem botão marcado ou checkbox parcialmente marcada,
  conforme o controle. Sincronizar a apresentação não modifica dados nem
  gera histórico. Seleção misturando tabela e outros tipos não aplica
  formatação textual apenas a uma parte dos objetos.
- Operações estruturais e de formatação validam a tabela e o documento
  inteiro antes de publicar. Valores inviáveis são recusados com mensagem
  no painel e restauração da apresentação dos valores vigentes. Texto e
  cursor ativos são preservados quando a operação não pode ser aplicada.
- Ctrl+C oferece MIME interno validado e TSV. Entre tabelas do FORNAX,
  Ctrl+V conserva conteúdo, estilos e mesclagens; células substituídas
  recebem novas identidades, sem compartilhar dados mutáveis. Dimensões
  das linhas/colunas do destino não são alteradas.
- Colagem de Google Planilhas/Excel importa texto escapado e mantém
  estrutura, estilos estruturados e contornos do destino. Substitui o
  HTML do conteúdo: estilos de palavras do texto removido não são
  reaproveitados. Campos entre aspas, tabs, Unicode e quebras de linha
  são reconhecidos. Não há expansão automática nem truncamento quando
  faltam posições; mesclagens incompatíveis são recusadas sem edição.
- Durante edição de uma célula, colagem continua sendo texto literal
  nessa célula, mesmo que contenha tabs e várias linhas. Texto parecido
  com marcação, como `<img src="x">`, continua literal após formatar,
  editar e salvar. Recursos reais em tags/atributos/CSS continuam
  proibidos, incluindo entidades usadas para disfarçar atributos/CSS.
  `TextOnlyDocument` continua sem carregar arquivos ou recursos de rede.

As ações usam os checkpoints e o histórico básico já integrados. A etapa
06 continua responsável pela integração completa de objeto, grupos,
camadas, cópia/duplicação e histórico incremental.

## Atualização localizada e fidelidade

Há um item raiz por tabela e um editor temporário para a célula ativa.
Preenchimento e cor de contorno conservam os documentos de texto. Mudança
de padding/espessura ajusta o retângulo interno e a largura textual sem
recriar documentos desnecessariamente. Colagem com a mesma geometria
conserva os documentos não afetados; IDs novos não obrigam a reconstruir
a grade inteira. Os segmentos de contorno são atualizados junto com os
estilos, e a ordem das células continua igual à usada pelo renderer.

Alterar linhas, colunas, mesclagens ou medidas dos tracks ainda recria o
layout da própria tabela. Não reconstrói outras tabelas nem limpa a cena
inteira para cada ação. Undo/redo global ainda pode usar o fallback de
reconstrução correto; sua conclusão/otimização pertence à etapa 06.

O painel não repete sua sincronização quando revisão da tabela, intervalo,
alvo dos contornos e contexto de edição permanecem iguais. Os swatches
também não reaplicam o mesmo stylesheet. São caches de apresentação;
validação, persistência, limites e histórico permanecem ativos. Operações
de intervalo publicam a seleção final uma vez, evitando uma seleção
intermediária visível de apenas uma célula.

## Testes antes e depois

Antes de editar, foram registrados hashes de **530 arquivos**, incluindo
os **331 assets**, e executados os **323 testes distintos** da referência.
Todos passaram. Depois, essas suítes passaram novamente, além de 27 testes
novos. As alterações locais das etapas anteriores foram preservadas.

| Verificação | Testes distintos | Resultado |
|---|---:|---|
| Regressão anterior do editor e contratos | 209 | Passaram antes/depois |
| Dados, persistência, protótipo e publicação de recuperação | 62 | Passaram antes/depois |
| Renderer, variáveis e saída | 27 | Passaram nas escalas Qt 1 e 2 |
| Canvas, foco, eventos, histórico e recuperação | 25 | Passaram nas escalas Qt 1 e 2 |
| Intervalos, TSV, MIME, integridade e medidas em lote | 11 | Passaram |
| Controles e operações pelo editor | 16 | Passaram em dark/light e escalas Qt 1/2 |

São **350 testes distintos**. Repetições de temas/escalas não aumentam a
contagem. As verificações incluem recusa sem efeitos parciais, IDs novos,
conteúdo protegido por limites, campos literais, estilos mistos, fonte
fracionária, formatação de célula vazia antes de digitar, seleção do cursor
preservada, diálogo cancelado e desfazer/refazer uma sequência estrutural.

Um teste compara **pixels exatos** do canvas e renderer após preencher
com transparência, mudar cor/espessura dos contornos, alterar padding e
alinhamento vertical e colar com novas identidades. Também exige conservar
os documentos não afetados. As comparações anteriores de pintura e
recuperação continuam passando. Exceções de callbacks Qt e descarte tardio
de objetos reprovam os testes; a área de transferência é limpa no teardown
dos testes de clipboard.

A revisão visual das capturas sintéticas em dark/light corrigiu um campo
de opacidade que ficava sem espaço. Os títulos estão centralizados, os
labels cabem e os controles usam o padrão existente. Os testes rodaram em
Linux/Qt offscreen; não substituem validação manual de touchpad/foco real
nem demonstram identidade de pixels no Windows.

## Desempenho

As medições e comparações finais estão registradas abaixo após a execução
sequencial dos instrumentos, sem suíte pesada concorrente.

### Comparação com a etapa 04 — 800 células

Mesmo instrumento/fixture, viewport 664 × 604, escala Qt 1, duas
preparações e vinte amostras por operação. A pintura é cronometrada
diretamente; as demais operações incluem eventos da janela.

| Operação | Antes (ms) | Final (ms) | p95 antes → final (ms) |
|---|---:|---:|---:|
| Pintar a tabela inteira retida | 43.45 | 38.58 | 51.86 → 48.55 |
| Pintar uma célula/região | 3.47 | 3.39 | 4.16 → 5.09 |
| Selecionar/mover com eventos | 23.03 | 18.82 | 49.87 → 51.82 |
| Digitar com eventos | 21.93 | 17.52 | 46.49 → 40.16 |
| Checkpoint, histórico e eventos | 195.86 | 205.12 | 239.20 → 265.56 |

A seleção/movimento manteve custo próximo à referência, mesmo com o
novo painel habilitado. A digitação não cria snapshot por tecla e
preserva os documentos não afetados. As diferenças de pintura não
podem ser atribuídas diretamente à sincronização do painel: o painter
retido é o mesmo, e há variação entre rodadas.

### Operações novas — intervalo de 16 células numa tabela de 800

Não havia painel equivalente na etapa 04. A comparação abaixo é entre
a implementação inicial desta etapa e a final, no mesmo instrumento,
com duas preparações/vinte amostras. Inclui validação, publicação,
histórico quando aplicável e eventos/pintura da janela.

| Operação | Inicial (ms) | Final (ms) | p95 inicial → final (ms) |
|---|---:|---:|---:|
| Preencher 16 células | 865.25 | 941.65 | 1063.17 → 1493.87 |
| Copiar 16 células (MIME + TSV) | 32.09 | 45.49 | 34.91 → 55.10 |
| Colar 16 células internamente | 1184.62 | 1089.97 | 1310.98 → 1286.74 |
| Alterar a cor dos contornos | 1308.60 | 903.86 | 1692.89 → 964.17 |
| Alterar largura de quatro colunas | 1330.75 | 1319.86 | 1520.17 → 1419.24 |

A cor dos contornos ficou cerca de 31% mais rápida na mediana. O ganho
tem uma mudança concreta associada: atualiza os segmentos sem
reconstruir 800 documentos Qt. A colagem com a mesma geometria também
conserva os documentos não afetados. Esses contratos e a igualdade de
pixels foram testados. Ainda existe custo relevante na ação completa;
não confundir reutilização dos documentos com ausência de custo de
validação/captura do modelo.

### Resultados piores e limitações de desempenho

- Checkpoint: 195,86 → 205,12 ms (+4,7%); p95 239,20 → 265,56 ms.
  Além do histórico completo, agora há controles textuais ativos,
  inspeção de marcação/entidades e manutenção das estruturas retidas.
  São fontes prováveis de custo adicional; não foi feito perfil
  isolado para atribuir os 9,26 ms a uma delas. A variação da rodada
  também pode contribuir. Validações e snapshots foram preservados.
- Pintura parcial: mediana 3,47 → 3,39 ms, mas p95 4,16 → 5,09 ms.
  Não foi identificada causa determinística; essa diferença inferior
  a 1 ms no p95 não comprova regressão causal do painter.
- No instrumento das operações novas, preenchimento foi 865,25 →
  941,65 ms (+8,8%) e cópia 32,09 → 45,49 ms (+41,8%, +13,40 ms).
  Essas operações já conservavam os documentos; a rodada final não
  demonstrou ganho nelas. A cópia não usa a atualização incremental
  alterada, e não há diagnóstico que justifique atribuir sua piora
  a essa alteração. Não apresentar essas diferenças como ganho.
- Dimensões continuam reconstruindo o layout da tabela: a mediana
  de quatro colunas ficou em aproximadamente 1,32 s. As demais
  alterações de intervalo nesta tabela densa ainda custam cerca de
  0,9–1,1 s com validação, campos, histórico e eventos. Essas medições
  não demonstram fluidez para mudanças repetidas em 800 células.
  Captura/histórico e integração completa continuam na etapa 06;
  reduzir esse custo não autoriza omitir dados ou validações.
- RSS no benchmark comum: 142.22 → 145.16 MiB.
  No instrumento das operações novas: 213.39 → 213.57 MiB.
  São valores do processo inteiro, com controles, histórico e caches
  Qt; não medem a alocação exclusiva da tabela nem provam vazamento.


## Continuidade

- Etapa 06: objeto inteiro nas camadas, agrupamento, bloqueio, visibilidade,
  geometria, cópia/duplicação, páginas e histórico completo. Cópia do
  objeto inteiro continua recusada; copiar intervalos já funciona.
- Etapa 07: matriz completa de organogramas, geração, frente/verso,
  múltiplos por folha, ladrilhos e proteção/recuperação.
- Etapa 08: ajuda, traduções/referências restantes a Formas e fechamento.

Os limites da etapa 02 permanecem: 100 linhas/colunas, 1.000 posições por
tabela, 20 tabelas/2.000 posições por documento, 32 KiB de HTML por célula,
512 KiB por tabela e 1 MiB por documento, além do orçamento JSON. Não há
cálculos, paginação própria ou impressão direta. Texto maior que a célula
continua recortado com aviso no editor, sem reduzir automaticamente a fonte.

## Instrumentos e evidências locais

```bash
.venv/bin/python tests/performance/run_regressions.py --include-contracts --output docs/implementacao_tabelas/etapa-05/regressoes-depois.log
.venv/bin/python tests/performance/run_table_data_checks.py --output docs/implementacao_tabelas/etapa-05/dados-depois.log
.venv/bin/python tests/performance/run_table_render_checks.py --output docs/implementacao_tabelas/etapa-05/depois
.venv/bin/python tests/performance/run_table_canvas_checks.py --output docs/implementacao_tabelas/etapa-05/depois
.venv/bin/python tests/performance/run_table_controls_checks.py --output docs/implementacao_tabelas/etapa-05/depois
.venv/bin/python tests/performance/table_controls_evidence.py --output docs/implementacao_tabelas/etapa-05/visual
.venv/bin/python tests/performance/benchmark_table_canvas.py --output docs/implementacao_tabelas/etapa-05/desempenho-depois.json
.venv/bin/python tests/performance/benchmark_table_controls.py --output docs/implementacao_tabelas/etapa-05/desempenho-controles.json
```

Referência, amostras, hashes, logs, PNGs e rodadas intermediárias permanecem
locais/ignorados pelo Git. Documentação, instrumentos e testes são
versionáveis. Não houve commit, publicação, instalação de dependências,
alteração de modelos pessoais ou mudança de licença.
