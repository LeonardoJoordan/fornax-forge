# Processos do editor — referência da etapa 00

Este mapa descreve o código existente em 08/10/2026. Não representa uma alteração
implementada. Serve como matriz de cobertura para as etapas de otimização,
especialmente histórico, recuperação e reutilização de cenas.

## Modificações persistentes e suas entradas

| Família | Entradas no código | Estado e dependências a preservar |
|---|---|---|
| Criar, excluir, duplicar e colar objetos | `EditorWindow.add_new_box`, `delete_selected_items`, `duplicate_selected`, `paste_copied_items`; desenho de formas e inclusão de imagens/assinaturas | Coleções, identidades, nomes, ordem, seleção, assets e relacionamentos. Colagem comum reconstrói a cena por `apply_scene_state`. |
| Texto no canvas | `CanvasTextEdit.begin/changed/checkpoint/finish/format` | HTML, estilos, placeholders, foco e cursor. `contentsChanged` sincroniza o conteúdo imediatamente; checkpoint/finalização capturam histórico. |
| Texto na barra lateral | `EditorTextoPanel`, `_on_content_updated`, atualização de fonte, alinhamento, recuo e altura de linha | `TextBoxState`, documento Qt e geometria interna. Valores podem ser aplicados antes de `editingFinished`. |
| Geometria e aparência | Alças, `itemChange`, `apply_position_x/y`, sinais do painel de propriedades, controles de formas em `frontend.py` | Posição, dimensões, rotação, proporção, opacidade, preenchimento, contorno e cantos. Incluir área antiga e nova ao otimizar pintura. |
| Recursos de imagem | Carregar fundo, incluir/substituir imagem ou assinatura, imagem variável, restaurar tamanho, links | Referência e conteúdo do asset, recorte/ajuste, dimensões e campos variáveis. Um arquivo externo pode mudar sem uma edição do documento. |
| Máscaras | `create_mask`, `begin_mask_edit`, `finish_mask_edit`, `remove_mask`; alças da forma e da imagem | Parentagem, coordenadas locais, identidade da forma, ordem dos filhos, clipping e confirmação/cancelamento de gestos. |
| Agrupamento | `group_selected_items`, `ungroup_selected_items`, redimensionamento coletivo | Identidade do grupo, geometria relativa, seleção completa e regra de camadas já aprovada. Não alterar a regra de ordem dos grupos. |
| Camadas | `rename_layer`, `_on_layer_reordered`, `move_layer_group_from_badge`, controles de visibilidade/bloqueio criados em `refresh_layer_list` | Nomes, z, grupos, máscaras, flags e camada Organograma; callbacks devem continuar ligados aos objetos corretos. |
| Guias | `add_guide`, `GuideLine.itemChange/mouseReleaseEvent`, limpar, mostrar e bloquear guias | Posições, direção, visibilidade e bloqueio. Respeitar a propagação já existente para organograma e o magnetismo. |
| Dimensões do documento | `_on_doc_w_changed`, `_on_doc_h_changed`, `_on_physical_size_changed` | Canvas, tamanho físico, fundos vinculados e proporção dos cartões no quadro. A captura sincroniza dependências entre páginas. |
| Páginas e estrutura do modelo | `switch_model_page`, `add_model_page`, `clear_model_page`, `remove_model_page`, `add_model_organogram` | Páginas, exclusividade verso/organograma, seleção por página e encerramento das interações. Troca isolada não deve criar edição falsa. |
| Conjuntos e posições no quadro | `add_board_group`, `edit_board_group`, duplicação/colagem de blocos, `BoardGroupItem.itemChange`, `_move_board_items`, árvore da estrutura | Nome único, capacidade, linhas/colunas, ordem, posição central, dimensões e espaçamentos. Mudança de posição aciona conexões. |
| Hierarquia e portas | `set_board_parents`, modo de conexão, `change_board_ports`, arrastar/soltar na árvore | Relações, lados permitidos, ciclos inválidos, seleção de origem/destino e estado transitório do modo conectar. |
| Contornos do quadro | `change_board_border`, cantos, posição e escopo | Aparências independentes dos cards e conjuntos, clipping dos cards e raio/padding do conjunto. Afeta limites e terminais dos conectores. |
| Conectores | `change_board_connector_style`, conexão/desconexão | Cor, espessura, opacidade, raio, seleção coletiva e caminhos. Mudança só de opacidade ainda percorre atualizações de geometria/estado. |
| Arte acima/abaixo do quadro | `change_board_artwork_position`, `_sync_board_artwork_layers` | Ordem de texto/imagem/forma relativa à camada Organograma. Textos à frente recortam conectores; textos atrás não. |
| Metadados e proteção | Salvar, renomear modelo, escolha de proteção, alteração de senha, reescrita de caminhos de assets | Nome/destino, provider, autorização e vínculo entre documento, histórico e arquivos. Estado salvo manualmente é diferente de recuperação. |

Seleção, zoom, pan, réguas, abertura de painéis e navegação da galeria são estados
da interface. Nem todo sinal `scene.changed` representa uma edição persistente:
pintura, realces e seleção também podem provocá-lo. Um futuro contador de edições
não deve simplesmente tratar cada emissão como mudança de conteúdo.

## Sinais e ciclo de vida da cena

| Origem | Destinos existentes | Consequência para otimização |
|---|---|---|
| `scene.selectionChanged` | `EditorWindow.on_selection_changed`, `CanvasTextEdit.selection_changed`, controles habilitados em `frontend.install_frontend` | Seleção individual pode atualizar painéis repetidamente. Concluir edição textual ao retirar sua seleção continua obrigatório. |
| `scene.changed` | `EditorWindow.update_position_ui` | A notificação é agregada/enfileirada pelo Qt; incluir seu processamento na medição, sem confundi-la com captura do histórico. |
| Seleção da lista de camadas | `_on_layer_selection_changed`, atualização dos controles | Sincronização bidirecional com a cena precisa evitar realimentação e preservar multisseleção. |
| Seleção/clique da árvore de estrutura | `select_from_tree`, `click_tree_item`; drag/drop da `StructureTree` | Há seleção do quadro e mudança de hierarquia. Não reutilizar nós que mantenham referências a blocos removidos. |
| Documento Qt do texto | `DesignerBox.recalculate_text_position`; `CanvasTextEdit.changed` e `sync_panel` enquanto editando | Cache de métricas deve invalidar para conteúdo/estilo/dimensões/fontes; encerrar edição desconecta os callbacks temporários. |
| `BoardGroupItem.itemChange` | Atualização de dados e `_update_board_connections` | Vários `moveBy` causam várias atualizações; `_move_board_items` já adia essas chamadas durante seu lote. |
| Controles laterais | `valueChanged`, `toggled`, `activated`, `editingFinished` | Diferenciar aplicação imediata do valor e conclusão da ação no histórico. Undo captura edição numérica ainda com foco. |
| Histórico | `canUndoChanged`, `canRedoChanged` → botões | Restauração bloqueia sinais da cena, adia pintura e depois sincroniza os painéis. Não reconectar callbacks duplicados. |
| Fonte e tema | `fontDatabaseChanged` → limpeza do cache; tema → callbacks de widgets | Reavaliar chaves visuais e liberar callbacks ao destruir widgets. A arte mantém suas cores próprias. |

Atualmente `apply_scene_state` remove e recria itens da cena. Trocar páginas
chama esse caminho. Captura, carregamento e restauração usam flags como
`_switching_page`, `_restoring_history`, `_loading_board` e `_board_defer_connections`.
Uma cena reutilizada precisa incluir essas condições, foco, handlers, seleção,
document rect e referências fortes aos wrappers PySide6.

## Histórico e recuperação

`save_snapshot` chama `_capture_document_history_state`, que serializa a página,
compara sua referência, atualiza o documento completo e copia o resultado.
Mesmo quando não há novo estado para `HistoryManager.push`, parte desse trabalho
já ocorreu. Undo/redo finalizam interações e capturam edições pendentes antes da
restauração. Estados completos, limites de passos/memória e invalidação do redo
continuam sendo a referência funcional.

O timer de recuperação chama `_write_fornax_recovery` a cada minuto. A função
ignora gestos incompletos, captura o documento e compara com o último salvamento
manual. Por isso uma edição ainda não salva pode ser escrita novamente em todos
os disparos. Não há trabalhador de arquivo separado nesse caminho.

## Autorização e liberação de conteúdo

1. `FornaxSessionManager.select/unlock/open_without_signatures` determina a forma
   de acesso. `EditorWindow.load_from_fornax` recebe o provider dessa sessão e
   `_detached_asset_provider` mantém uma cópia dos bytes autorizados no editor,
   que precisa ser liberada junto com seu conteúdo ao encerrar a janela.
2. `document`, `asset` e `write_recovery` passam por `_accessible_session`; a
   recuperação conserva a proteção do documento original. Dados públicos e
   protegidos não devem compartilhar caches externos à sessão.
3. `leave_active`, `expire_due`, `suspend`, alteração externa, `forget` e `close`
   mudam ou invalidam acesso/estado conforme a sessão. A expiração por tempo
   trata a tolerância de sessões inativas; não encerra automaticamente o editor
   ativo. Não reutilizar conteúdo autorizado em outro documento por um cache antigo.
4. `borrow_job`, `issue_token` e `token_is_current` são pontos existentes a avaliar
   se a etapa 08 introduzir trabalho assíncrono. Não basta validar só ao iniciar:
   uma tarefa atrasada não pode publicar sobre uma revisão/autorização nova.
5. Ao fechar o editor, `closeEvent` confirma edições, para o timer, remove a
   recuperação conforme a decisão, limpa caches e libera a janela principal.
   Conteúdo protegido também passa por `_discard_protected_editor_content`, que
   limpa cena, histórico, clipboard, provider e documento e destrói a janela.

Não introduzir acesso a widgets, cena ou `QPixmap` no futuro trabalhador de
arquivo. A matriz acima é referência inicial; cada etapa deve revisar seus
consumidores e acrescentar testes específicos antes da alteração.

## Localização das implementações

- `features/editor/editor_window.py`: ciclo do editor, cena, camadas, colagem,
  propriedades, máscaras, captura/restauração, fechamento e recuperação.
- `features/editor/document_session.py`: seleção por página, captura do documento,
  sincronização de dimensões e troca/adição/remoção de páginas.
- `features/editor/canvas_edit.py`, `canvas_items.py`, `properties.py`, `frontend.py`:
  edição e desenho dos objetos, painéis, eventos, fonte/tema e sinais.
- `features/editor/organogram_editor.py`: árvore, blocos, conectores, geometria,
  contornos, recortes e camadas do quadro.
- `features/editor/visual_cache.py`: caches visuais limitados já existentes;
  identificação por conteúdo e liberação ao encerrar a janela.
- `core/history_manager.py`, `model_document.py`, `document_layers.py`,
  `organogram.py`, `text_layout.py`: estado e cálculos compartilhados.
- `core/fornax_session.py`, `fornax_container.py`: autorização, acesso a assets,
  proteção, recuperação e publicação de arquivos.
