# Tabelas — contrato de dados da etapa 02

09/10/2026. Implementado em `core/table_model.py` e `core/model_document.py`.
Este contrato prepara o recurso; desenho, edição e controles continuam nas
etapas seguintes do [plano](../../PLANO_IMPLEMENTACAO_TABELAS.md).

## Documento e identidade

- Tabelas ficam em `pages[n].tables` ou `organogram.tables`. Ausência da
  coleção nos formatos anteriores equivale a uma lista vazia.
- Um documento com tabelas declara `schema_version: 6`. Versões 3/4/5 com
  tabelas são recusadas antes da conversão; versões desconhecidas também são
  recusadas. Um documento v6 conserva essa versão ao remover sua última tabela.
- Permanecem a exclusão entre verso e organograma e o nome legado
  `template_v4.json`. A versão do contêiner `.fornax` e sua proteção não mudam.
- `object_id` identifica a tabela na camada `table`; integra `layer_order`.
  Cada âncora tem `id` próprio, único entre todas as tabelas do documento.
  Duplicação gera identidades novas para a tabela e suas células.
- Nome e identidade têm de 1 a 128 caracteres, sem espaços nas extremidades,
  caracteres de controle ou Unicode inválido. A unicidade do nome visível
  entre as camadas deverá usar o mecanismo do editor na etapa 06.

## Geometria e estado

Campos obrigatórios da tabela:
`object_id`, `custom_name`, `rows`, `columns`, `column_widths`, `row_heights`,
`style`, `border`, `cells`, `edges`.

Campos opcionais permitidos:
`x`, `y`, `rotation`, `z_value`, `opacity`, `visible`, `locked`, `group_id`,
`layer_id`, `board_behind`, `keep_proportion`.

As medidas usam as unidades lógicas do projeto: **300 unidades por polegada**.
`table_size()` deriva largura e altura das somas das colunas e linhas.
Não salvar `w`, `h`, `width` ou `height` como segunda geometria.
Posição segue o contrato existente; a rotação acontece em torno do centro.
`board_behind` mantém a posição relativa à camada do organograma.

Seleção, cursor, documentos Qt, caches e estado de hover não pertencem ao
contrato e são recusados como campos desconhecidos. Índices começam em zero,
são inteiros reais e não aceitam booleanos. Números devem ser finitos.

## Células e estilo

Uma âncora contém exatamente `id`, `row`, `column`, `row_span`, `column_span`,
`html` e `style`. Células simples têm alcance 1 × 1. Posições cobertas por uma
mesclagem pertencem à mesma âncora e não guardam cópias do conteúdo.
A grade deve estar completamente coberta, sem buracos ou sobreposições.

O `style` da tabela é completo; o da célula contém somente sobrescritas.
`effective_cell_style()` resolve os valores. Padrões atuais:

| Campo | Padrão | Significado |
|---|---|---|
| `font_family` | `Inter 18pt` | Nome da família embarcada, não o tamanho da fonte. |
| `font_size` | 10 | Pontos físicos; aplicar a convenção de 300 dpi comprovada na etapa 01. |
| `font_color` | `#17242d` | Cor do texto. |
| `fill_color` | `#ffffff` | Cor do preenchimento. |
| `fill_opacity` | 1 | Opacidade de 0 a 1. |
| `align` | `left` | `left`, `center` ou `right`. |
| `vertical_align` | `top` | `top`, `center` ou `bottom`. |
| `wrap` | `true` | Quebra automática; não remove quebras manuais. |
| `padding` | 6 | Espaçamento interno, em unidades do documento. |
| `line_height` | 1,15 | Multiplicador de altura da linha. |

Cores estruturadas usam `#RRGGBB`; transparência usa os campos próprios.
Isso evita a ambiguidade entre ARGB do Qt e RGBA do CSS. A família aceita
até 256 caracteres; fonte de 1 a 200 pt; padding de 0 a 500 unidades;
altura de linha de 0,5 a 5. O contorno admite até 100 unidades de espessura.
Contorno e padding não podem consumir toda a área interna da célula.

HTML é texto rico: sem recursos externos/gráficos, tabelas aninhadas ou
scripts. `table_fields()` identifica campos `{nome}` através de spans e
entidades, sem unir nomes separados por parágrafos. Os campos entram na
reconciliação do documento e da página; sua substituição e a inclusão em
`card_fields` do organograma pertencem à etapa 03.

## Fronteiras canônicas

`border` contém os padrões completos `color`, `width`, `opacity` e `visible`.
Inicialmente: `#203746`, 2 unidades, opacidade 1 e visível.

`edges` é uma lista de sobrescritas, com registros contendo exatamente
`orientation`, `row`, `column` e `style`. Sua chave é única:

- `h`: segmento horizontal na divisa de linha `0..rows`, sobre a coluna
  `0..columns-1`.
- `v`: segmento vertical na linha `0..rows-1`, na divisa de coluna
  `0..columns`.

Uma fronteira compartilhada é pintada uma vez. `visible_edge_keys()` filtra
as divisórias internas de mesclagens; o pintor ainda deve aplicar
`visible`/opacidade do estilo. Mesclar não apaga os estilos ocultos;
dividir volta a expô-los. Os helpers armazenam somente diferenças dos
padrões, ordenadas por chave.

## Operações e atomicidade

Todos os helpers de alteração validam a entrada, alteram uma cópia
independente e validam o resultado. Erro gera `TableValidationError` e
preserva a entrada. Não há objetos Qt nessa camada.

| API | Comportamento |
|---|---|
| `new_table` | Cria grade uniforme, inicialmente 3 × 3. |
| `set_cell_html` | Altera a âncora correspondente à posição, inclusive quando mesclada. |
| `format_cells` | Aplica sobrescritas a um intervalo retangular inteiro. |
| `format_edges` | Aplica contornos a `all`, `outer`, `inner` ou `none`. |
| `merge_cells` | Mantém identidade e padrões da âncora superior esquerda; reúne textos em ordem de leitura, preservando estilos. |
| `split_cell` | Mantém o texto reunido na âncora; cria células vazias nas outras posições. |
| `insert_rows` / `insert_columns` | Inserção estritamente dentro de mesclagem expande seu alcance; antes desloca a âncora. |
| `remove_rows` / `remove_columns` | Reduz mesclagens; preserva texto/identidade numa parte sobrevivente; remoção completa exclui o conteúdo. |
| `resize_table` | Distribui medidas proporcionalmente; conserva fonte, padding e contornos. |
| `set_track_size` | Muda uma linha/coluna e, portanto, o tamanho total. |
| `duplicate_table` | Copia dados e recria identidades; não reutiliza `layer_id`. |
| `add_model_table` | Anexa a uma página/quadro, integra a camada e promove o documento para v6. |

Intervalos são inclusivos, na ordem `top, left, bottom, right`. Seleções que
cortam mesclagens são recusadas. Inserir copia a medida da linha/coluna
vizinha se nenhuma medida for informada. Novas células ficam vazias.
Em inserções internas, a divisa original delimita as duas extremidades
do intervalo novo. Na remoção, divisas que colapsam priorizam o contorno
externo; depois, a fronteira anterior ao intervalo removido.

**Dividir não é Desfazer.** Para recuperar textos e estilos individuais
anteriores à mesclagem, o editor deverá restaurar o snapshot anterior.
Essas operações ainda não estão conectadas ao histórico da interface.

## Limites iniciais

| Recurso | Limite |
|---|---|
| Linhas / colunas por tabela | 100 / 100 |
| Posições lógicas por tabela | 1.000, mesmo mescladas |
| Tabelas por documento | 20 |
| Posições lógicas no documento | 2.000 |
| HTML UTF-8 por célula | 32 KiB |
| HTML UTF-8 por tabela | 512 KiB |
| HTML UTF-8 das tabelas do documento | 1 MiB |
| Medida mínima por linha/coluna | 1 unidade, também limitada pelo espaço interno necessário |
| Dimensão total e coordenadas | 262.144 unidades, teto geométrico já usado no projeto |

Esses limites são uma política conservadora inicial, apoiada na prova de
800 células da etapa 01; não significam fluidez garantida para todos os
conteúdos. Podem ser reavaliados na etapa 08 com medições completas.
Contam as tabelas persistidas no modelo, sem multiplicar pelo número de
cartões que reutilizam a Página 1 em um organograma.

O documento v6 também conserva os tetos existentes do contêiner:
8 MiB de JSON, 100.000 elementos e profundidade 64. A contagem é da entrada
inteira, incluindo metadados, estilos e conteúdo escapado; não basta contar
células. Índices, cobertura, orçamento e segurança do HTML são conferidos
antes de copiar um documento v6 ou entregá-lo aos consumidores.

## Integração pendente e barreiras temporárias

**Atualização após a etapa 05 (09/10/2026):** inserção em Elementos → Tabela
e controles laterais já estão disponíveis. `set_track_sizes` aplica medidas
em lote. `core.table_clipboard` valida o MIME
`application/x-fornax-table-range+json` (versão 1, até 4 MiB), preserva
estilos/mesclagens em intervalos internos e oferece TSV para planilhas.
Colagem interna recria IDs das células substituídas, conserva a identidade
da tabela e as medidas do destino; externa importa apenas texto escapado.
Intervalos excessivos ou mesclagens incompatíveis são recusados antes da
publicação, sem ampliar ou truncar a grade. `core.table_html` verifica
recursos em tags/atributos/CSS, incluindo entidades nesses contextos; texto
literal escapado não é confundido com recursos. `TextOnlyDocument` continua
impedindo carregamento de arquivos/rede. Cópia/duplicação do objeto inteiro
permanece bloqueada até a etapa 06. Ver
[relatório da etapa 05](../etapa-05/RELATORIO.md).

**Atualização após a etapa 04 (09/10/2026):** o editor carrega tabelas v6
com um item raiz e uma sessão temporária para a célula ativa. Serialização,
histórico básico, páginas e recuperação foram verificados; a recusa
temporária de abertura foi retirada. Inserção e painel pertencem à etapa
05; cópia/duplicação e integração completa de camadas permanecem nas etapas
05/06. A cópia/duplicação de objetos contendo tabelas é recusada por enquanto,
para impedir operações parciais que descartem conteúdo. Continuidade no
[relatório da etapa 04](../etapa-04/RELATORIO.md).

**Atualização após a etapa 03 (09/10/2026):** prévia, renderer e geração já
desenham tabelas. As barreiras de renderização foram retiradas; as barreiras
do editor permanecem até a integração da cena/histórico. O estado original
da etapa 02 está descrito abaixo; a continuidade está no
[relatório da etapa 03](../etapa-03/RELATORIO.md).

Na conclusão da etapa 02, editor e renderizadores recusavam documentos
com tabelas, apresentando um aviso no workspace. Essa proteção impedia
prévias incompletas ou um salvamento que descartasse conteúdo enquanto a
integração estava em andamento.

- Etapa 03: implementar pintura/variáveis/fontes e então remover as barreiras
  de `NativeRenderer` e `OrganogramRenderer` e ajustar o aviso de prévia.
- Etapas 04–06: implementar cena, serialização, foco, histórico e páginas
  antes de retirar `require_table_free_editor` e os avisos de edição.
- Etapa 07: conferir todos os caminhos de geração e recuperação ativa.
  Nesta etapa 02, o contêiner e as sessões já preservam snapshots v6 públicos
  e protegidos; isso não equivale a testar edição ativa de uma célula.


## Integração com objetos e histórico — etapa 06

- `group_id` aceita a identidade textual já prevista ou um inteiro real de
  0 a 1.000.000, como os grupos nativos de texto/imagem/forma. Booleanos
  não são identidades numéricas. Isso conserva o mesmo tipo entre os
  membros de um grupo misto após salvar/reabrir e desfazer/refazer.
- `keep_proportion` é um booleano opcional, com padrão `true` no editor,
  persistido ao capturar a tabela. Documentos v6 anteriores continuam válidos.
- A tabela inteira participa das camadas, grupos e transformações existentes.
  A cópia de objetos reutiliza a ordem global; renova identidade da tabela e
  de todas as âncoras, camada, nome e grupo da cópia. Nenhum dicionário de
  estilo/conteúdo é compartilhado. A página candidata e os limites do
  documento completo são conferidos antes de inserir objetos Qt.
- Copiar células e copiar objetos são contextos distintos. `Esc` encerra
  primeiro a edição e depois a seleção interna; a seleção do objeto
  continua disponível para copiar/colar/excluir a tabela inteira. Duplicar
  pelo botão ou `Ctrl+D` na grade sempre duplica o objeto inteiro. Durante
  digitação, o contexto de edição nativo continua tendo prioridade.
- A captura rápida compara todos os dados persistentes da tabela e a
  geometria/flags nativos, sem usar somente a revisão do layout. Célula
  ativa, tipo/propriedade não cobertos ou mudanças globais exigem captura
  completa. Restauração segue o fallback completo existente, com todas as
  células. Caches Qt e seleção não são fonte de persistência.

Ver [relatório da etapa 06](../etapa-06/RELATORIO.md).
