# Mapa confirmado da integração de tabelas

09/10/2026. Leitura do código identificado em `referencia.json`, na branch
`upgrade-01`. Esta etapa não alterou os componentes abaixo.

## Contrato e estrutura das páginas

- `core/model_document.py`: `PAGE_COLLECTIONS`/`PAGE_KEYS`, `_validate_page`,
  `normalize_model_document`, `adapt_model_page`, `replace_model_page`,
  `persistent_model_document`, `remove_model_page` e reconciliação dos campos.
  Versões atuais: 3 legada, 4 para páginas, 5 para organograma. Não há coleção
  `tables` nem versão de documento 6.
- `core/document_layers.py`: `GROUPS`, `layer_entries`, `upgrade_layers`.
  Os tipos enumerados hoje são image/text/signature/shape. A tabela precisa
  entrar na identidade e ordem dos objetos, não ser convertida em shape.
- `features/editor/model_adapter.py`: `prepare_scene_page` enumera as quatro
  coleções atuais para atribuir `layer_id`. A enumeração precisa acompanhar
  o novo tipo antes de carregá-lo na cena.
- `core/fornax_container.py`: normalização/persistência são usadas na abertura
  e gravação. `MAX_JSON_OBJECTS` é 100.000; células com estilos repetidos podem
  consumir rapidamente esse orçamento. A prova técnica deve medir o contrato
  antes de oficializar limites; não elevar os limites globais automaticamente.

## Canvas, edição e histórico

- `features/editor/editor_window.py`: `get_current_scene_state`,
  `apply_scene_state`, `get_all_model_placeholders`, `sync_placeholders_list`,
  `duplicate_selected`, `copy_selected_items`, `paste_copied_items`,
  `_capture_resize_snapshots`, nomes e camadas. Há filtros explícitos por
  `DesignerBox`, `ImageItem`, `SignatureItem` e `RectangleItem` nos caminhos
  de seleção/transformação; não existe um registro genérico que resolva todos.
- `features/editor/canvas_edit.py`: `CanvasEdit.begin`, `changed`, `checkpoint`,
  `finish`, `format`, `eventFilter`. A edição ativa desabilita atalhos globais;
  perder a seleção encerra a sessão. A célula precisa de um destino explícito
  sem modificar as regras de edição das caixas existentes.
- `features/editor/frontend.py` e `controls.py`: menu Formas, painel Texto,
  seções recolhíveis, controles de propriedades e sincronização da seleção.
  Reutilizar `Section`, `property_heading`, `configure_editor_combo` e ícones
  temáticos; a sincronização de UI não deve produzir snapshots.
- `features/editor/history_capture.py`: `history_inputs` usa fallback
  conservador para tipo desconhecido. Uma tabela nova ainda faria esse caminho
  retornar `None`. A captura completa precisa reconhecê-la primeiro; não
  presumir igualdade omitindo o novo conteúdo.
- `features/editor/document_session.py`: `_capture_document_history_state`.
  `editor_window.py` mantém `_document_with_active_page`, `save_snapshot`,
  `_restore_history_state`, `undo` e `redo`. Devem sincronizar a célula ativa
  antes das capturas e preservar texto, mesclagens e fronteiras.
- `features/editor/page_scenes.py`: identidade do conteúdo, dependências e
  estimativa de memória das cenas retidas. Texto de células e caches novos
  precisam entrar na cobertura, sem aumentar o orçamento de 64 MiB.
- `features/editor/visual_cache.py`: proxy de imagens e prévia compartilhada
  da Página 1. O snapshot já inclui o template completo; confirmar que as
  tabelas chegam ao template antes de assumir invalidação correta.

## Texto, campos e fontes

- `core/text_layout.py`: `resolve_rich_text` retorna `None` quando encontra
  um placeholder vazio fora de um bloco opcional, ocultando a caixa inteira.
  Essa política não atende às células. Criar a política da tabela sem alterar
  o resultado atual das caixas.
- `core/html_utils.py`: `TextOnlyDocument` e sanitização impedem recursos
  externos. Texto de célula deve usar a mesma proteção, inclusive ao colar.
- `core/font_utils.py`: `template_font_families` percorre caixas de texto.
  `core/model_info.py`: `build_model_snapshot` também descreve fontes em
  caixas. Precisam reconhecer conteúdo de células para avisos e metadados.
- `core/organogram.py`: `card_fields` e `row_is_valid` hoje consideram
  placeholders visíveis das caixas e imagens variáveis das formas. Um cartão
  com dados somente em uma célula não será válido até atualizar essa coleta.

## Organograma e desenho complementar

- `features/editor/organogram_editor.py`: `_board_artwork_roots`,
  `_board_geometry_state`, `_board_geometry`, `_build_board_cutouts`,
  `_load_board_items`. O desenho complementar e seus limites usam tipos
  enumerados. Incluir a tabela nos planos, bounds, rotação e recortes sem
  serializar HTML a cada movimento.
- `features/generator/organogram.py`: `OrganogramRenderer` copia e filtra
  explicitamente boxes/images/shapes nos planos à frente/atrás. Atualizar
  essa filtragem e a coleta de placeholders da prévia sem dados.
- O canvas usa uma imagem compartilhada do cartão para todos os slots.
  Esse comportamento deve continuar; mil cartões não são mil editores de
  células nem mil blocos independentes.

## Caminhos de geração e avisos

| Caminho | Fluxo atual | Atenção para tabelas |
|---|---|---|
| Item individual PNG/PDF, frente/verso | `RenderManager` → `DirectRenderWorker` → `NativeRenderer.render_to_qimage` | Tabela precisa entrar no dispatcher e na resolução por registro. Cada renderer é derivado para o worker. |
| Múltiplos itens por folha | `RenderManager` → `PageRenderWorker` → `SheetAssembler.render_sheet` | Renderizar cartão antes de montar a folha; escala, slots e verso seguem o plano existente. |
| PDF único sem proteção total | Modo híbrido → imagens temporárias → `HybridAssemblerWorker` | Conteúdo de tabela precisa estar no cartão gerado; não fazer um renderer separado na montagem. |
| PDF único com conteúdo protegido | `SecureGroupedPdfWorker` | Preservar caminho sem cache intermediário de imagens em disco, autorização e descarte. |
| Organograma PNG/PDF | `OrganogramWorker` → `OrganogramRenderer` → `NativeRenderer.paint_card` para cartões e planos | Tabelas na Página 1 e complementares precisam funcionar nos dois contextos. |
| Ladrilhos de páginas comuns | `TiledDocumentWorker` → `PageTilingRenderer` → `NativeRenderer.paint_card` | A tabela participa da pintura da região; não criar sua própria paginação. |
| Ladrilhos de organograma | `OrganogramRenderer.paint_tile`, `export_tile_png`, `export_pdf` | Respeitar escala, recorte, margens e marcas existentes. |
| Prévia de cartão/miniatura | `NativeRenderer.render_preview_image`, `PreviewRenderWorker` e caches | Manter placeholders literais sem dados e invalidar revisões do novo conteúdo. |

O PDF de itens/folhas comuns **já usa imagens raster do cartão/folha** no
`QPdfWriter`. Isso é diferente de salvar a tabela do modelo como imagem:
o objeto deve continuar editável, e o PDF deve manter o caminho atual. Não
prometer PDF totalmente vetorial nem reescrever sua exportação nesta tarefa.

Existe apresentação de mensagens via `RenderManager.log_updated` → painel
de logs do workspace. `PageRenderWorker.page_finished` também entrega uma
mensagem; os workers de quadro e ladrilhos têm `log_updated`. Entretanto:

- `DirectRenderWorker` possui `card_finished` e `error_occurred`, sem um canal
  dedicado a avisos de conteúdo excedente.
- O renderer não mantém uma coleção padronizada de ocorrências de overflow
  por tabela/célula/registro, pois o recurso ainda não existe.
- Erro fatal e aviso não devem ser confundidos. Na etapa de integração,
  agregar ocorrências durante a pintura e devolvê-las por resultados/sinais,
  chegando ao log sem acesso do worker aos widgets nem renderização adicional.
- Conferir os caminhos híbrido/protegido/ladrilhos para não duplicar o aviso
  de uma mesma célula quando a região é pintada em várias partes. A forma
  exata dessa deduplicação será definida com o renderer da tabela.

## Pontos de compatibilidade a validar depois

Biblioteca, importação/exportação e workspace dependem dos contratos comuns
em `core/model_library.py`, `core/fornax_import.py`, `core/fornax_export.py` e
`features/workspace/main_window.py`. A etapa 00 confirma esses consumidores,
mas não certifica suporte a uma versão nova que ainda não foi implementada.

Ajuda usa `assets/help/pt_BR/catalog.json` e artigos locais; traduções usam
`assets/translations/`. Manter os IDs e acrescentar termos de busca para
Elementos/Formas/Tabela na etapa final, sem inventar novos controles agora.
