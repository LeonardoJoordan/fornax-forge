# Plano de implementação de tabelas — FORNAX Forge

Data: 09/10/2026.

**Status: etapa 00 autorizada e concluída em 09/10/2026, com referência, cenários, testes e medições registrados. Etapas 01–08 pendentes. Nenhuma alteração no código de produção ou na interface nesta etapa.**

## 1. Instruções para a instância responsável

Implementar um elemento de tabela editável no canvas, integrado ao editor, ao formato do modelo, à prévia e à geração. A tabela deve permitir compor boletins, escalas, fichas e quadros de informações, sem cálculos ou fórmulas.

Este documento registra o pedido, recomendações de comportamento, pontos de integração encontrados no código e critérios de conclusão. O usuário autorizou a execução da primeira etapa (00), concluída conforme o relatório abaixo. As etapas seguintes serão executadas conforme as instruções de continuidade do usuário, sem solicitar confirmação para cada decisão técnica rotineira dentro da etapa autorizada.

- Ler as instruções locais aplicáveis e conferir o estado real dos arquivos antes de editar. Os nomes de funções abaixo são referências; números de linha não são contratos.
- Preservar as alterações locais existentes. Na análise, a branch `upgrade-01` continha mudanças e arquivos não versionados das otimizações anteriores. Não restaurar arquivos inteiros para o `HEAD`, limpar a árvore ou usar o commit como única identidade da referência.
- Ler o [relatório da rodada Pareto](desempenho_editor/etapa-12/RELATORIO.md) e os critérios do [plano de otimização](PLANO_OTIMIZACAO_EDITOR.md). A implementação parte do código atual, incluindo essas otimizações.
- Aplicar mudanças por etapa e registrar evidências. Não fazer uma reescrita geral do editor, da planilha de dados ou do histórico.
- Não modificar modelos pessoais, substituir modelos prontos, publicar releases, instalar dependências ou alterar a licença como parte desta tarefa.
- Este plano não exige delegação a subagentes.

## 2. Escopo e distinção entre pedido e recomendações

### 2.1. Funcionalidades solicitadas

- Trocar o rótulo visível **Formas** por **Elementos**, mantendo quadrado, círculo e linha e acrescentando **Tabela**.
- Inserir uma tabela com quantidade de linhas e colunas escolhida pelo usuário.
- Selecionar células e digitar textos diretamente no canvas.
- Selecionar várias células para alterar propriedades, como a cor de fundo.
- Controlar a quebra automática de linha e permitir quebras manuais.
- Inserir linhas e colunas e mesclar células entre linhas e/ou colunas.
- Alinhar conteúdo à esquerda, ao centro ou à direita; no topo, no meio ou embaixo da célula.
- Disponibilizar uma seção **Tabela** na barra lateral direita, abaixo de **Texto**, preservando o padrão visual do programa.
- Manter a fidelidade entre editor, prévia e arquivo gerado.

### 2.2. Complementos recomendados para uma primeira versão utilizável

As regras das seções seguintes são propostas deste plano, não decisões já aprovadas individualmente pelo usuário. São padrões de partida para a implementação; registrar alterações justificadas por evidências. Consultar o usuário somente se for necessário mudar substancialmente o comportamento ou reduzir uma função solicitada.

- Placeholders em cada célula, com a formatação do modelo preservada.
- Remover linhas/colunas, desfazer mesclagem e ajustar larguras/alturas.
- Contornos externos e internos, espaçamento interno e preenchimento por célula.
- Seleção da tabela inteira para posição, dimensões, rotação, opacidade, camadas, bloqueio, visibilidade, agrupamento e duplicação.
- Copiar/colar texto de uma célula e copiar/colar intervalos simples de texto, distinguindo essas ações da cópia do objeto inteiro.
- Histórico, recuperação automática, documentos protegidos, frente/verso e uso na Página 1 de um organograma.
- Tabela como desenho complementar na aba de organograma, respeitando a camada do organograma.

### 2.3. Fora da primeira versão

- Fórmulas, cálculos, classificação, filtros ou formatação condicional.
- Importação nativa de arquivos Excel, integração com Google Sheets ou reprodução completa da formatação de uma planilha externa.
- Linhas repetidas automaticamente para uma quantidade variável de registros, paginação automática da tabela ou repetição de cabeçalho entre páginas.
- Imagens, assinaturas, tabelas aninhadas, links por célula ou máscaras dentro das células.
- Arredondamento individual de células, bordas diagonais e efeitos gráficos novos.

A estrutura da tabela é definida no modelo. Um registro da planilha de dados pode preencher várias células através de placeholders. Não confundir essa estrutura com a planilha de entrada do FORNAX nem modificar suas regras de assinaturas, cópias e destino de blocos.

## 3. Contrato de comportamento proposto

### 3.1. Inserção e seleção

1. **Elementos → Tabela** abre um diálogo compacto de linhas e colunas. Padrão inicial sugerido: 3 × 3, com distribuição uniforme e largura que caiba na página. Cancelar não altera o documento nem o histórico.
2. A tabela aparece como uma única camada, com nome único seguindo as regras atuais, como `Tabela 1`.
3. Clicar em uma célula seleciona a célula e identifica sua tabela. Digitar inicia a edição; duplo clique permite posicionar o cursor no texto existente.
4. Arrastar sobre células seleciona um intervalo retangular. Shift amplia a seleção. Não exigir seleção descontínua na primeira versão.
5. Uma moldura/alça externa ou a seleção pela lista de camadas permite mover/redimensionar o objeto inteiro. Não disputar o mesmo gesto com a seleção interna.
6. Com várias camadas selecionadas, as ações coletivas existentes operam sobre a tabela inteira. A seção Tabela só edita células quando há uma tabela ativa inequívoca.
7. Esc sai da edição preservando o texto, depois sai da seleção interna. Perder a janela ativa ou soltar o touchpad encerra a captura do ponteiro; não perde texto nem deixa arraste preso.

Definir uma pequena máquina de estados: objeto selecionado, células selecionadas e texto em edição. A transição entre esses estados deve ser explícita e testada.

### 3.2. Teclado, foco e histórico

- Durante a edição, Enter insere quebra manual; Tab/Shift+Tab navegam entre células visíveis, considerando mesclagens. No fim da tabela, não criar linha automaticamente.
- Delete/Backspace no texto editam texto; sobre células selecionadas limpam o conteúdo; sobre a camada inteira seguem a exclusão de objetos atual. Não deixar um atalho global apagar a tabela durante digitação.
- Ctrl+A, copiar, colar, desfazer e refazer respeitam o contexto. Preservar o comportamento fora da tabela.
- Selecionar uma cor ou fonte no painel mantém o intervalo-alvo e a edição, mesmo que o foco do teclado passe ao controle.
- Digitação usa a edição de texto do Qt e checkpoints coerentes com `CanvasEdit`. Alterar várias células ou mesclar um intervalo produz uma ação estrutural única no histórico, sem uma entrada por célula.
- Antes de salvar, recuperar, trocar de página ou fechar, sincronizar a edição ativa para o documento. Um texto ainda com cursor ativo não pode ficar fora da recuperação.
- Desfazer edição após uma mesclagem e refazer tudo deve restaurar texto, estilos, dimensões e estrutura. Não manter duas pilhas independentes que disputem os mesmos atalhos.

### 3.3. Dimensões, texto e alinhamento

- Armazenar dimensões nas unidades lógicas atuais do documento e apresentar milímetros na interface. Não criar conversão independente baseada no DPI do monitor.
- Padrão proposto: largura das colunas e altura das linhas fixas, quebra automática ligada, texto alinhado à esquerda e ao topo, com espaçamento interno positivo.
- Alterar uma coluna/linha redistribui ou expande a tabela conforme a operação explícita; recomendação: arrastar uma divisória muda os dois vizinhos mantendo o tamanho total, e editar a medida de uma linha/coluna no painel muda o total. Respeitar dimensões mínimas.
- Redimensionar a moldura inteira distribui proporcionalmente as larguras/alturas. Na primeira versão, manter os pontos da fonte, espaçamento interno e espessura dos contornos; não reduzir a fonte silenciosamente para fazer caber. O comportamento deve ser descrito na ajuda.
- Quebra automática e quebra manual são independentes. Desligar a automática não remove as quebras que o usuário inseriu.
- O texto é limitado ao retângulo interno da célula, descontando contorno e espaçamento. Não invade a célula vizinha.
- Se o conteúdo não couber, mostrar indicação no editor e registrar aviso na geração com a tabela/célula e o registro afetado. O aviso não faz parte do desenho exportado. Usar os mecanismos existentes de resultado/avisos e evitar uma segunda renderização completa apenas para detectar excesso.
- Ajuste automático de altura é uma extensão possível, não requisito para encerrar esta versão. Não introduzir crescimento automático diferente entre preview e saída.

### 3.4. Mesclagem, inserção e remoção

- Mesclar somente um retângulo de células contíguas. Uma seleção que corte uma mesclagem existente deve ser expandida coerentemente ou recusada com mensagem; nunca gerar sobreposições parciais.
- A célula superior esquerda é a âncora da mesclagem. Ela mantém a identidade, o preenchimento e os padrões de texto; textos das demais células são concatenados em ordem de leitura, em parágrafos, preservando ênfases. Nenhum texto é descartado silenciosamente.
- Desfazer mesclagem pela ferramenta divide a área e mantém o texto reunido na célula superior esquerda; as outras ficam vazias. Explicar a diferença para **Desfazer**, que restaura exatamente o estado anterior à operação.
- Inserir uma linha/coluna estritamente dentro de uma área mesclada expande seu alcance. Inserir antes/depois desloca as coordenadas sem quebrar a mesclagem. Validar o resultado inteiro antes de aplicar.
- Remover uma linha/coluna que cruza uma mesclagem reduz seu alcance. Se sua âncora sair, preservar texto e identidade numa célula sobrevivente da área. Se toda a área for removida, excluir seu conteúdo como parte da operação, recuperável por Desfazer.
- Impedir tabela com zero linhas/colunas. Excluir a tabela inteira usa a ação de exclusão do objeto.
- Guardar e testar o estado completo antes/depois; não deduzir o conteúdo anterior a partir do aspecto visual.

### 3.5. Texto variável e geração em lote

- Permitir texto fixo e placeholders na mesma célula, por exemplo `Nota: {nota_portugues}`. Campos exclusivos de células devem aparecer na planilha de dados, inclusive no verso.
- Prévia sem dados mostra os placeholders literais, como nos modelos atuais.
- Com dados, substituir um valor ausente por texto vazio naquela posição, preservando o texto fixo, as demais células e a estrutura da tabela. Não usar a regra atual de ocultar uma caixa inteira para decidir a visibilidade da tabela.
- Preservar negrito, itálico e sublinhado do placeholder e as regras atuais de ênfase vinda da planilha. Tratar Unicode e placeholders divididos entre trechos de formatação.
- Se forem utilizados blocos opcionais `|...{campo}...|`, aplicar sua regra dentro da própria célula, sem remover células, linhas ou a tabela inteira.
- Não modificar globalmente `resolve_rich_text` para atender às tabelas se isso mudar a semântica das caixas existentes. Preferir política explícita ou função específica que reutilize a parte comum.
- Na Página 1 de um organograma, campos das células também contam em `card_fields`/`row_is_valid`: um cartão preenchido somente por uma célula deve ser reconhecido como válido.
- Tabelas decorativas na aba de organograma seguem o contexto de dados já existente para textos dessa aba. Não escolher arbitrariamente o primeiro registro nem agregar a planilha. Registrar essa limitação na ajuda.

### 3.6. Preenchimentos e contornos

- Cor/transparência de preenchimento por célula ou intervalo; cor, espessura e visibilidade dos contornos. Reutilizar controles e temas, sem copiar o painel de formas inteiro.
- Oferecer os alvos externos/internos/todos/nenhum para a seleção. Garantir que o usuário saiba se está formatando a célula ou a tabela inteira.
- Usar uma representação canônica para cada segmento de fronteira da grade; uma divisa entre duas células é desenhada uma única vez. Alterar um intervalo não pode produzir duas linhas sobrepostas ou uma regra dependente da ordem de pintura.
- Mesclagens ocultam as divisórias internas. Definir sua preservação para a posterior divisão e para undo/redo; não perder estilos silenciosamente.
- Contornos de tabela não precisam herdar todas as opções geométricas das formas. Não aplicar raio de canto ou posição dentro/centro/fora de forma ambígua às linhas internas.
- Temas mudam controles, seleção e indicadores. As cores escolhidas para o documento não mudam ao alternar tema.

## 4. Arquitetura recomendada

### 4.1. Um objeto persistente próprio

Adicionar uma coleção `tables` às páginas e ao desenho complementar do organograma, e um tipo `table` na ordenação de camadas. Uma tabela não deve ser salva como imagem, como dezenas de caixas de texto ou como uma forma com atributos ocultos.

Separar responsabilidades em módulos pequenos. Nomes sugeridos, ainda inexistentes:

| Módulo proposto | Responsabilidade |
|---|---|
| `core/table_model.py` | Contrato, validação, células/mesclagens e operações estruturais em dados puros. |
| `core/table_layout.py` | Medidas de células, conteúdo, alinhamento, clipping e detecção de excesso. |
| `core/table_paint.py` | Desenho compartilhado por canvas, prévia e exportação. Pode ser unido ao módulo de layout se permanecer pequeno. |
| `features/editor/table_item.py` | Um item raiz da cena por tabela; moldura e hit testing. |
| `features/editor/table_edit.py` | Sessão de edição, seleção interna, teclado e adaptação ao histórico. |
| `features/editor/table_panel.py` | Controles específicos, construídos com os componentes visuais existentes. |

O estado persistente deve conter identidade/nome, geometria, visibilidade/bloqueio/opacidade/grupo, larguras das colunas, alturas das linhas, estilos padrão, células e fronteiras. Cada célula lógica guarda identidade, linha/coluna da âncora, alcance da mesclagem, conteúdo e sobrescritas de estilo. Posições cobertas por uma mesclagem apontam para uma única âncora; não guardam cópias divergentes do texto.

A largura/altura total deve ser derivada das listas de medidas ou validada contra elas. Não manter duas geometrias independentes. Seleção, cursor, hover, caches e documentos Qt temporários não pertencem ao JSON.

### 4.2. Reaproveitar Qt sem herdar sua interface de planilha

O Qt já oferece [QTextTable](https://doc.qt.io/qt-6/qtexttable.html), [QTextTableCellFormat](https://doc.qt.io/qt-6/qtexttablecellformat.html) e edição de texto rico. Avaliar essas peças no protótipo da etapa 01. Verificar a API da versão efetivamente instalada, pois a documentação online pode apontar para outra versão.

Recomendação inicial: modelo estruturado próprio, layout/desenho compartilhados e reaproveitamento do motor de texto seguro por célula. Um editor de texto temporário atende à célula ativa; não criar centenas de widgets de entrada permanentemente na cena.

Se `QTextTable` cumprir as medidas fixas, mesclagens, contornos e clipping com fidelidade, pode ser usado internamente. A prova técnica deve preceder essa escolha. Não misturar dois motores que calculem quebras e alturas de maneira diferente.

Não embutir a planilha de dados inteira com `QGraphicsProxyWidget` como solução final. Além das diferenças de papel entre a planilha e o objeto gráfico, a própria [documentação do Qt](https://doc.qt.io/qt-6/qgraphicsproxywidget.html) limita essa abordagem para cenários de alto desempenho.

Não introduzir navegador, HTML remoto ou nova dependência para este recurso. Preservar a proteção de `TextOnlyDocument` e a sanitização do texto.

### 4.3. Desenho e caches

- O renderer recebe estado independente da UI. Nenhum worker acessa widgets, itens da cena ou documentos de texto criados em outra thread. Criar documentos Qt na thread que os utiliza e liberar suas referências com segurança.
- O motor comum retorna medidas e operações de pintura; overlays de seleção são exclusivos do editor. Não exportar captura de tela do widget.
- Cachear somente com chave completa do conteúdo e das propriedades que afetam o resultado; distinguir texto do modelo de valores resolvidos de um registro. Não deixar dados do aluno anterior aparecerem no próximo.
- Limitar a memória dos caches, respeitar o ciclo da sessão e invalidar em conteúdo, geometria, fonte ou autorização alterados. Incluir memória da tabela na estimativa das cenas retidas.
- Editar uma célula não reconstrói a cena inteira. Mover a tabela não recalcula todo o texto. Uma alteração de coluna pode recalcular as células/mesclagens afetadas, sem redesenhar documentos não relacionados.
- Um organograma continua usando a prévia compartilhada da Página 1. Não criar editores de célula para cada cartão repetido.

## 5. Persistência, compatibilidade e segurança dos dados

Na análise, o documento usa versões 3 (legada), 4 (páginas) e 5 (organograma). Há atribuições explícitas dessas versões em mais de um lugar. Não basta incrementar uma constante.

Proposta: versão de documento **6** para modelos que introduzem tabelas, caso o número ainda esteja livre ao implementar. A versão 6 admite páginas normais ou organograma, mantendo a exclusão atual entre verso e organograma. A versão do contêiner `.fornax` é outro contrato; não alterá-la automaticamente junto com a versão do documento.

- Ler 3/4/5 normalmente e interpretar ausência de `tables` como coleção vazia. Não alterar/gravar o arquivo de origem durante a abertura.
- Modelos sem tabelas podem continuar sendo persistidos no formato anterior adequado. Modelos com tabelas precisam declarar a nova versão para que programas antigos os recusem em vez de descartarem elementos silenciosamente.
- Um documento que já está na versão nova pode permanecer nela mesmo após a última tabela ser removida. Não introduzir downgrade automático sem necessidade.
- Atualizar normalização, validação, adaptação de página, criação/remoção de organograma, remoção de página e persistência. Remover o organograma não pode voltar à versão 4 se a Página 1 ainda possui tabela.
- Não confundir `template_v4.json`, nome legado já usado no projeto, com a versão interna. Evitar renomear arquivos/diretórios existentes como efeito lateral.
- Validar índices e quantidades inteiras (rejeitando booleanos), valores finitos e positivos, dimensões, identidades únicas, cobertura da grade, mesclagens sem sobreposição, estilos e conteúdo antes de alocar estruturas Qt.
- Definir limites explícitos de linhas, colunas, células por tabela/documento e bytes de texto. Medir primeiro os cenários da seção 8; publicar os limites escolhidos e testá-los em criar, inserir, colar, importar e abrir. Não aumentar limites globais de JSON, raster, contêiner ou histórico para fazer um exemplo passar.
- A complexidade do JSON das células deve caber nos limites atuais; compartilhar padrões de estilo ajuda a evitar repetição. Falha de validação não pode deixar alteração parcial na cena ou no arquivo.
- Preservar criptografia, autorização, cancelamento, checks de origem, backup e publicação atômica. Texto de tabelas de um modelo totalmente protegido não pode ir para thumbnail/cache persistente/log sem autorização.
- Exercitar modos público, assinaturas protegidas e totalmente protegido. No código atual, o modo público usa a constante `PUBLIC_MODE` cujo valor é `none`; não inventar o literal `public` nas chamadas internas.

## 6. Mapa de integração no código atual

Conferido por leitura nesta análise. As listas são pontos de atenção, não autorização para editar todos os arquivos indiscriminadamente.

| Área | Arquivos/símbolos existentes | Integração necessária |
|---|---|---|
| Contrato do documento | `core/model_document.py`: `PAGE_COLLECTIONS`, `PAGE_KEYS`, `_validate_page`, `normalize_model_document`, `adapt_model_page`, `replace_model_page`, `persistent_model_document`, reconciliação de campos | Tabelas como conteúdo de página; versão nova; campos dinâmicos e preservação de versões anteriores. |
| Camadas | `core/document_layers.py`: `GROUPS`, `layer_entries`, `upgrade_layers` | Reconhecer `table`, preservar ordenação e uma identidade por objeto. |
| Adaptação da cena | `features/editor/model_adapter.py`: `prepare_scene_page` | Identidades e valores padrão; não converter tabelas em caixas/formas. |
| Estado e interação geral | `features/editor/editor_window.py`: `get_current_scene_state`, `apply_scene_state`, `duplicate_selected`, `copy_selected_items`, `paste_copied_items`, `get_all_model_placeholders`, `sync_placeholders_list`, `refresh_layer_list` | Serialização/restauração, seleção, geometria, cópia, campos e camadas. Auditar os filtros explícitos por tipo em todos esses caminhos. |
| Edição de texto | `features/editor/canvas_edit.py`, `features/editor/properties.py` | Sessão ativa, atalhos, foco, seleção e encaminhamento do painel Texto para células. Evitar mudanças no comportamento das caixas existentes. |
| Interface | `features/editor/frontend.py`, `features/editor/controls.py` | Menu Elementos e seção Tabela; reutilizar `Section`, `property_heading`, `configure_editor_combo`, controles e ícones com tema. |
| Desenho/gestos | `features/editor/canvas_items.py`, `features/editor/draw_shapes.py`, `features/editor/rulers.py` | Integrar item próprio a seleção/movimento/redimensionamento/guias, sem fingir que tabela é `RectangleItem`. |
| Histórico | `features/editor/history_capture.py`, `core/history_manager.py`, `features/editor/document_session.py` | Cobrir o conteúdo e propriedades da tabela nos estados; checkpoints do editor de célula; identidade ao restaurar. |
| Cenas e recursos visuais | `features/editor/page_scenes.py`, `features/editor/visual_cache.py`, `features/editor/starter_cache.py` | Invalidação, orçamento de memória, descarte e prévia do cartão/miniaturas. |
| Texto e fontes | `core/text_layout.py`, `core/html_utils.py`, `core/font_utils.py`, `core/model_info.py` | Formatação e placeholders por célula; fontes faltantes e informações do modelo também precisam considerar células. |
| Renderer do cartão | `features/generator/renderer.py`: `_paint_card`, cache estático, `render_preview_image`, `paint_card` | Dispatch de `table`, pintura comum e dados por registro. Auditar o atalho legado e o prefixo estático. |
| Organograma | `core/organogram.py`, `features/editor/organogram_editor.py`, `features/generator/organogram.py` | Campos válidos do cartão; desenho complementar; planos de camadas; bounds; proxies; recorte dos conectores. |
| Exportação | `features/generator/workers.py`, `features/generator/imposition.py`, `features/generator/tiled_document.py` | Confirmar que todos os caminhos chegam ao novo desenho, inclusive PDF, imagem, frente/verso e ladrilhos. |
| Contêiner e recuperação | `core/fornax_container.py`, `core/fornax_session.py`, `features/editor/recovery_worker.py` | Novo conteúdo atravessa o mesmo contrato e snapshot seguro, sem bypass de proteção. |
| Biblioteca/workspace | `core/model_library.py`, `core/fornax_import.py`, `core/fornax_export.py`, `features/workspace/main_window.py` | Importar, duplicar, renomear, listar e pré-visualizar modelo com a versão nova; não fazê-lo desaparecer da biblioteca. |
| Ajuda e idiomas | `assets/help/pt_BR/catalog.json`, artigos, `core/help_catalog.py`, `assets/translations/` | Novos tópicos e busca; atualizar o rótulo Formas no que for visível, preservando IDs estáveis e seguindo o fluxo de traduções existente. |

### Pontos que podem produzir falhas silenciosas

- `history_inputs` hoje retorna `None` para tipo desconhecido, usando a captura completa. Isso é uma proteção; nunca substituir por uma igualdade presumida. A serialização completa também precisa reconhecer a tabela antes de qualquer UI de edição ser habilitada.
- A captura atual lê revisões de texto das `DesignerBox`; tabelas precisam de cobertura equivalente para conteúdo, estilos, fronteiras e mesclagens. Selecionar células não é alteração persistente.
- `_paint_card` tem um caminho legado e um prefixo estático. Tabela com placeholders não pode entrar no cache de imagem estática resolvida com outro registro, nem desaparecer ao pintar uma camada individual.
- `OrganogramRenderer` copia e filtra explicitamente `boxes`, `images`, `shapes` etc. Incluir `tables` em cada plano sem pintar duas vezes ou vazá-las entre frente/trás.
- O cálculo de bounds do organograma deve considerar tabelas, inclusive rotação e contorno, sem serializar todo o HTML a cada movimento.
- Para tabelas à frente do organograma, proposta: recortar conectores no retângulo da tabela, como ocorre com caixas de texto; atrás, não recortar. Implementar a mesma regra no canvas e na geração. Alterar apenas texto, com geometria fixa, não deve recalcular rotas.
- Campos e fontes são coletados por caminhos que hoje percorrem somente `boxes`. Um modelo contendo apenas uma tabela deve funcionar sem precisar de uma caixa de texto auxiliar.

## 7. Etapas de execução

Não marcar uma etapa concluída apenas porque o elemento aparece na tela. Cada etapa deve registrar arquivos alterados, comandos de verificação, resultados e limitações em `docs/implementacao_tabelas/etapa-XX/RELATORIO.md`. Criar esses diretórios durante a implementação, não como evidência fictícia neste planejamento.

| Etapa | Entrega | Dependências | Critério para avançar |
|---|---|---|---|
| 00 | Referência atual, cenários e mapa confirmado | Nenhuma | Estado inicial e regressões relevantes registrados sem mudar produção. |
| 01 | Protótipo de layout, texto, mesclagem e pintura | 00 | Demonstrar medidas e saída iguais; registrar escolha entre QTextTable e layout próprio. |
| 02 | Contrato e operações em dados puros, versão e persistência | 01 | Abrir/salvar/reabrir com equivalência; versões antigas e dados inválidos tratados. |
| 03 | Renderer compartilhado e placeholders | 02 | Prévia e geração sem UI funcionam; isolamento entre registros e fontes verificado. |
| 04 | Item no canvas, seleção e edição básica | 03 | Digitação/foco/gestos corretos; salvamento e histórico básico integrados desde a primeira edição. |
| 05 | Painel Tabela e operações completas | 04 | Formatação coletiva, mesclagem, estrutura e overflow passam nos testes. |
| 06 | Integração completa com camadas, histórico e páginas | 05 | Jornadas de duplicar, agrupar, mover, undo/redo, trocar página e reabrir preservam tudo. |
| 07 | Organograma, geração completa, proteção e recuperação | 06 | Mesmo documento funciona nos caminhos de saída e sessão sem regressões. |
| 08 | Ajuda, desempenho, regressão e revisão visual | 07 | Evidências finais, testes e limitações documentados; recurso completo e revisável. |

### Etapa 00 — Referência e preparação

- Registrar branch, commit, status e hashes dos arquivos relevantes. Preservar uma referência reproduzível das alterações não commitadas, sem copiar dados pessoais.
- Executar as regressões existentes pertinentes e guardar os resultados; falhas anteriores ficam identificadas, não atribuídas automaticamente à tabela.
- Preparar fixtures sintéticas de boletim, escala, tabela com células mescladas e documento frente/verso. Não alterar modelos prontos do usuário.
- Medir operações existentes sem tabelas que serão sensíveis: texto, troca de página, duplicação, histórico e recuperação. Reutilizar os instrumentos atuais quando aplicável.
- Confirmar o caminho de todos os tipos de saída disponíveis e como avisos de geração são apresentados.

**Registro da execução:** [relatório da etapa 00](implementacao_tabelas/etapa-00/RELATORIO.md). As três baterias existentes passaram (209, 126 e 96 execuções, com sobreposição), e quinze cenários de desempenho foram registrados. Quatro fixtures sintéticas e um mapa confirmado ficaram preparados para o protótipo. Fontes e assets originais foram conferidos e preservados; a tabela ainda não foi implementada no produto.

### Etapa 01 — Prova técnica pequena

- Criar um protótipo isolado de 4 × 4 com título mesclado, texto rico, célula multilinha, preenchimentos, contornos e placeholder. Sem alterar a biblioteca nem expor menu incompleto ao usuário.
- Exercitar largura/altura fixas, alinhamento vertical, clipping, seleção em zoom e rotação. Comparar renderizações em escalas diferentes e saída PDF.
- Verificar se o motor Qt candidato cresce células implicitamente, altera margens ou perde estilos no ciclo de salvar/carregar. Se impedir o contrato, usar layout próprio com texto Qt por célula.
- Escolher e documentar representação das fronteiras, medidas e política de overflow. Medir o custo inicial de 40 × 20 células antes de definir limites.
- Avançar quando os requisitos couberem na abordagem. Se for necessário retirar uma função solicitada, relatar a limitação ao usuário antes de reduzir o escopo.

### Etapa 02 — Dados, compatibilidade e operações atômicas

- Implementar estrutura persistente, validação e helpers de inserir/remover/mesclar/dividir, com entradas/saídas independentes e sem Qt na parte de dados.
- Incluir tabela nas coleções, camadas, adaptação e versionamento. Auditar atribuições literais de versão e criação/remoção de organograma.
- Definir limites consistentes com o contêiner; testar exatamente no limite e acima dele. Uma operação inválida deve deixar o documento anterior intacto.
- Cobrir leitura 3/4/5, versão nova, arquivo desconhecido, ida e volta pública/protegida e rejeição do novo formato pelo leitor antigo, em processo/check-out isolado quando necessário.
- Não aplicar teste de compatibilidade salvando uma cópia com a aplicação antiga sobre o arquivo original.

### Etapa 03 — Layout e saída antes de completar a UI

- Implementar desenho compartilhado de fundos, fronteiras e conteúdo, com `save/restore` do painter e transformações consistentes.
- Tratar campos vazios, texto literal na prévia, Unicode, estilos mistos e blocos opcionais sem alterar a semântica das caixas existentes.
- Incluir fontes de células na coleta de fontes e nos avisos de ausência. Testar tabela como único elemento textual do documento.
- Integrar o renderer e sua classificação estática/dinâmica. Gerar registros alternados com valores, vazios e estilos diferentes, sem vazamento entre saídas.
- Comparar PNG/prévia/PDF em dimensões equivalentes; não aceitar apenas um teste em que as duas saídas chamam a mesma função sem verificar medidas e conteúdo esperado.

### Etapa 04 — Canvas e sessão de edição

- Implementar item raiz, coordenadas locais, hit testing de células mescladas, moldura e seleção interna.
- Reutilizar edição textual e encaminhar atalhos por contexto; preservar acentos, caracteres compostos e entrada por método de composição.
- Ligar serialização, checkpoint, recuperação e histórico básico antes de habilitar a edição no menu público.
- Testar foco no painel, clique fora, salvar com cursor ativo, Esc, Delete, Tab, seleção por arraste e interrupção do gesto.
- Garantir que apenas a região afetada seja invalidada. Não usar `scene.clear()` ou reconstrução global para cada tecla.

### Etapa 05 — Painel e operações completas

- Renomear visualmente Formas → Elementos; manter os IDs internos estáveis quando não houver necessidade de alterá-los. Atualizar tooltip, acessibilidade e descrições relacionadas.
- Criar seção Tabela abaixo de Texto com títulos centralizados em caixa alta, divisores e espaçamentos atuais. Reutilizar ícones com cor de tema; não usar caracteres improvisados como ícones.
- Encaminhar tipografia e alinhamento textual pelo painel Texto; agrupar estrutura, espaçamento, preenchimento e contornos em Tabela. Não duplicar dois controles que disputem a mesma propriedade.
- Para valores mistos na seleção, exibir estado misto em vez de aplicar arbitrariamente o estilo da primeira célula. Uma sincronização visual dos controles não gera edição nem histórico.
- Conectar inserção/remoção, mesclagem/divisão, medidas e formatação múltipla às operações testadas da etapa 02.
- Cópia de intervalos: usar formato interno validado para preservar estrutura/estilo e texto tabular para interoperabilidade. Colagem externa inicial importa conteúdo, não HTML irrestrito. Se o intervalo não couber ou interceptar mesclagens incompatíveis, recusar antes de alterar; não truncar silenciosamente nem expandir sem ação explícita.
- Verificar que copiar/colar um texto multilinha durante edição de uma célula não seja confundido com colar várias linhas na grade.

### Etapa 06 — Histórico, camadas e cenas completas

- Incluir tabela nos caminhos de nome, grupo, bloqueio, visibilidade, exclusão, geometria, seleção múltipla e ordenação. Manter as regras de grupo aprovadas no projeto.
- Duplicar/colar cria novas identidades de tabela/células, sem referências compartilhadas mutáveis. As células de uma cópia não alteram a original.
- Completar captura e restauração do histórico. Se o caminho incremental não puder provar equivalência, usar o fallback correto; não ignorar células para obter velocidade.
- Incluir conteúdo e custo de memória nas cenas retidas; limpar editor temporário ao trocar de página ou encerrar sessão. Caches não são autoridade de persistência.
- Testar uma sequência combinada: digitar → formatar → mesclar → inserir coluna → duplicar → trocar página → salvar → desfazer/refazer. Conferir estado canônico e desenho.

### Etapa 07 — Integração de produto

- Validar tabela na Página 1 replicada nos cartões e como desenho complementar no organograma, inclusive ordem de camadas, limites, conectores e prévia sem dados.
- Validar todos os formatos já suportados, múltiplos por folha, frente/verso e ladrilhos. A tabela não introduz impressão direta nem paginação própria.
- Verificar miniaturas, biblioteca, importar/exportar modelo, duplicar/renomear e reabrir. A nova versão não pode resultar em aviso falso de modelo protegido.
- Testar recuperação em texto ativo, fechamento, cancelamento, arquivo alterado externamente e expiração de autorização. Preservar o snapshot autorizado independente e publicação atômica existentes.
- Usar dados sintéticos para todos os cenários protegidos e excluir conteúdo/chaves de logs e evidências.

### Etapa 08 — Fechamento e documentação

- Adicionar ajuda para inserir, selecionar/editar, medidas, mesclagem, contornos, alinhamento, texto variável, overflow e atalhos. Incluir exemplo de boletim, limites e distinção para a planilha de dados.
- Atualizar referências visíveis ao botão Formas para Elementos mantendo buscas por ambos os termos. Seguir o fluxo de traduções já usado pelo projeto.
- Executar regressões relevantes após a última mudança; repetir medições apenas se o código medido mudou ou houver resultado inconclusivo.
- Fazer revisão visual em temas claro/escuro, zoom baixo/alto, fontes e escala de tela. Exercitar Linux e Windows quando disponíveis; testes offscreen não substituem validação nativa de foco/touchpad.
- Entregar relatório com funcionalidades, decisões finais, testes, desempenho, regressões/pioras e limitações. Identificar claramente o que não foi testado.

## 8. Matriz mínima de verificação

### 8.1. Testes funcionais novos

Nomes sugeridos: `test_table_model.py`, `test_table_rendering.py`, `test_table_editor.py`, `test_table_integration.py`. Não confundir com `tests/test_table_copy.py`, que testa a planilha de dados existente.

| Cenário | Verificação exigida |
|---|---|
| Documento só com tabela | Salvar/reabrir, fontes, campos da planilha e prévia corretos. |
| Tabela 1 × 1 | Inserir/remover até os limites; não permitir dimensão zero. |
| Mesclagens | Horizontais, verticais e retangulares; seleção parcial; inserir/remover cruzando a âncora; texto preservado. |
| Propriedades múltiplas | Cor, contorno, espaçamento, alinhamento e valores mistos; uma ação no histórico. |
| Texto | Acentos, emoji/caracteres fora do BMP, estilos mistos, quebra manual/automática e alinhamento vertical. |
| Placeholders | Negrito no modelo; valor formatado; zero; vazio; marcação dividida entre spans; dois campos na mesma célula; bloco opcional. |
| Overflow | Texto longo nunca invade outra célula; aviso correto; nenhuma alteração silenciosa de fonte ou layout. |
| Foco/atalhos | Painel de cor/fonte durante edição; copiar, colar, Ctrl+A, Delete, Esc, Tab e undo/redo por contexto. |
| Transformações | Zoom, rotação, redimensionamento, seleção por área e guias; hit testing acompanha a geometria. |
| Estado | Cópia independente, nome único, ordem de camadas, agrupamento, bloqueio e visibilidade preservados após reopen/undo. |
| Compatibilidade | Fixtures legadas inalteradas visualmente, versão nova recusada pelo leitor antigo, JSON/mesclagens inválidos rejeitados antes da UI. |
| Organograma | 1.000 cartões distribuídos em grupos, campo apenas em célula, tabela à frente/atrás e bounds/recortes iguais no editor e saída. |
| Saída | Imagem/PDF, lote, múltiplos por folha, frente/verso, ladrilhos; indicadores de seleção não exportados. |
| Proteção | Público, assinaturas e proteção total; recuperação com texto ativo e autorização expirada; nenhuma perda do original. |

### 8.2. Desempenho e ausência de regressões

- Cenários de tabela: boletim 10 × 6; tabela densa 40 × 20; várias tabelas pequenas; mistura de tabela, imagens, caixas e formas; frente/verso; organograma com cartão contendo tabela pequena.
- Medir inserir, digitar, alterar seleção, formatar intervalo, mesclar/dividir, mudar coluna, mover, duplicar, undo/redo, trocar página, prévia, lote e recuperação. Separar operações locais de exportação.
- Comparar operações antigas sem tabelas antes/depois. Para o recurso novo não existe desempenho anterior equivalente: registrar a referência do protótipo e o resultado final, sem inventar porcentagem de melhoria contra um recurso inexistente.
- Não atribuir custo de 1.000 cartões a 1.000 blocos ou 1.000 editores ativos. Registrar grupos, conexões, cartões e tamanho das tabelas separadamente. O cenário de 100 grupos conectados já tem limitação conhecida; consultar a etapa 12.
- Usar a mesma máquina, fonte, escala, entradas e backend; processos/preferências isolados. Duas execuções de aquecimento e pelo menos vinte amostras para ações curtas; cinco para ações caras, aumentando quando inconclusivo.
- Guardar amostras, mediana, p95, memória e hashes de entrada/código. Cronometrar até o estado/pintura esperados; não só até a função agendar a atualização.
- Testes determinísticos devem verificar estados, pintura e ausência de reconstrução global desnecessária. Não usar um prazo absoluto de milissegundos dependente do hardware como único critério.
- Comparações de pixels exigem escalas, clipping, dados e fontes equivalentes e overlays desativados. PDF rasterizado por outro motor pode diferir no antialiasing; conferir geometria, quebras e conteúdo e justificar tolerâncias, sem ocultar deslocamentos.
- Exceções em callbacks Qt também reprovam. Verificar stderr/`sys.excepthook`, lifetimes e `DeferredDelete`, não apenas o retorno de `unittest`.

### 8.3. Instrumentos existentes

Executar a partir da raiz. Estes comandos são referências verificadas por leitura do runner; **não foram executados para o recurso de tabela neste planejamento**.

```bash
.venv/bin/python tests/performance/run_regressions.py --include-contracts --output docs/implementacao_tabelas/etapa-00/regressoes-antes.log
.venv/bin/python tests/performance/run_pareto_checks.py --output docs/implementacao_tabelas/etapa-00/pareto-antes
.venv/bin/python tests/performance/benchmark_pareto.py --label antes --samples 5 --output docs/implementacao_tabelas/etapa-00/pareto-medicoes
```

Na etapa final, repetir os mesmos cenários em diretórios `etapa-08`, com rótulos `depois`. Conferir `--help` antes, caso os instrumentos tenham mudado.

Os runners atuais não incluem automaticamente os testes novos nem todos os módulos locais. Criar um runner de tabelas ou completar o escopo explicitamente. Incluir, conforme as áreas alteradas, os testes de texto/fidelidade/placeholders, histórico, cenas, cópia incremental, camadas, organograma, atribuição de blocos, prévia, exportação em ladrilhos, recuperação, segurança e ajuda. Não somar suítes sobrepostas como testes distintos.

## 9. Critérios de conclusão e entrega à próxima instância

- [x] Etapa 00: referência e instrumentos registrados — [relatório](implementacao_tabelas/etapa-00/RELATORIO.md).
- [ ] Etapa 01: abordagem de layout comprovada e decisões registradas.
- [ ] Etapa 02: contrato, versão, limites e operações estruturais verificados.
- [ ] Etapa 03: renderer e placeholders com fidelidade demonstrada.
- [ ] Etapa 04: canvas e edição com foco/atalhos/histórico básico corretos.
- [ ] Etapa 05: controles e funções solicitadas completos.
- [ ] Etapa 06: integração com camadas, cópia, histórico e páginas completa.
- [ ] Etapa 07: organograma, exportações e proteção/recuperação verificados.
- [ ] Etapa 08: regressão, desempenho, ajuda e revisão visual registrados.

Uma etapa só pode ser marcada concluída com evidência correspondente. Não relaxar validações, rasterizar a tabela como substituto da função editável ou omitir o histórico para apresentar um protótipo como funcionalidade terminada.

Ao encerrar cada etapa, deixar o documento atualizado com o estado real, link para o relatório, decisões tomadas e próximo passo. Ao terminar a implementação, resumir o que o usuário consegue fazer, como foi testado, limites conhecidos e qualquer piora confirmada. Não prometer igualdade visual entre sistemas ou fluidez em cenários que não foram medidos.

Texto sugerido para iniciar a próxima instância, quando o usuário autorizar a execução:

> Implemente o recurso de tabelas seguindo `docs/PLANO_IMPLEMENTACAO_TABELAS.md`. Comece conferindo as instruções locais, as alterações existentes e a etapa 00. Preserve as otimizações e os modelos atuais. Execute as etapas em ordem, valide cada uma e registre evidências. Não publique nem faça alterações fora do escopo. Use as recomendações do plano como padrões de partida e explique qualquer mudança material necessária.
