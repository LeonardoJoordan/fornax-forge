"""Tutorial interativo de primeiros passos do FORNAX Forge."""

from __future__ import annotations

from html import escape
from pathlib import Path
import re

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, QTimer, QUrl
from PySide6.QtGui import QColor, QTextDocument
from PySide6.QtWidgets import QApplication, QInputDialog, QLineEdit, QMessageBox

from core.i18n import tr
from core.themes import theme_color
from features.spreadsheet.headers import table_column_key
from .coach_marks import CoachMark, Spotlight


MODEL_TEXT = (
    "Este cartão foi feito de forma muito rápida e eficiente para "
    "{nome}| com a ajuda de {programa}|!"
)
NAMES = (
    "Ana Silva", "Bruno Costa", "Carla Souza", "Daniel Lima", "Elisa Rocha",
    "Felipe Alves", "Gabriela Nunes", "Henrique Melo", "Isabela Martins",
    "João Ribeiro",
)
PROGRAM = "FORNAX Forge"
TOTAL_STEPS = 37


class FirstStepsTutorial(QObject):
    """Conduz um trabalho real, validando cada ação antes de avançar."""

    def __init__(self, workspace):
        super().__init__(workspace)
        self.workspace = workspace
        self.editor = None
        self.coach = None
        self.step = 1
        self._phase = 0
        self.text_box = None
        self._initial_box_size = None
        self._connections = []
        self._seen_rows = set()
        self._model_saved = False
        self._last_output_dir = None
        self._menu_spotlight = None
        self._clipboard_backup = QApplication.clipboard().text()
        self._poll = QTimer(self)
        self._poll.setInterval(120)
        self._poll.timeout.connect(self._poll_current_step)

    def start(self):
        QApplication.instance().installEventFilter(self)
        self._show_step()

    def _replace_coach(self, host):
        if self.coach is not None:
            self.coach.close()
        self.coach = CoachMark(host)
        self.coach.card.nextRequested.connect(self.next)
        self.coach.card.backRequested.connect(self.back)
        self.coach.card.skipRequested.connect(self.finish)

    def _ensure_coach(self, host):
        if self.coach is None or self.coach.host is not host:
            self._replace_coach(host)

    def _disconnect_stage(self):
        self._poll.stop()
        if self._menu_spotlight is not None:
            self._menu_spotlight.stop()
            self._menu_spotlight.deleteLater()
            self._menu_spotlight = None
        while self._connections:
            signal, callback = self._connections.pop()
            try:
                signal.disconnect(callback)
            except (RuntimeError, TypeError):
                pass

    def _connect(self, signal, callback):
        signal.connect(callback)
        self._connections.append((signal, callback))

    def _show(self, host, *, target=None, provider=None, title, body,
              action="", wait=False, next_text=None, back=True,
              important=False, preserve=False, link_text="", link_url="",
              highlight=True):
        self._ensure_coach(host)
        self.coach.show_step(
            target=target,
            target_rect_provider=provider,
            title=title,
            body=body,
            action_text=action,
            current=self.step,
            total=TOTAL_STEPS,
            can_go_back=back,
            next_text=next_text or tr("Continuar"),
            wait_for_action=wait,
            important=important,
            preserve_card_position=preserve,
            link_text=link_text,
            link_url=link_url,
            highlight_target=highlight,
        )

    def _advance(self, expected=None):
        if expected is not None and self.step != expected:
            return
        self._disconnect_stage()
        self.step += 1
        self._phase = 0
        self._show_step()

    def next(self):
        phase_steps = {16: 5, 20: 1, 22: 1, 24: 2, 27: 2, 33: 2}
        if self.step in phase_steps and self._phase < phase_steps[self.step]:
            self._disconnect_stage()
            self._phase += 1
            self._show_step()
            return
        if self.step >= TOTAL_STEPS:
            self.finish()
        else:
            self._advance(self.step)

    def back(self):
        self._disconnect_stage()
        self.step = max(1, self.step - 1)
        self._phase = 0
        self._show_step()

    def _menu_action_rect(self, menu, action):
        def provider():
            rect = menu.actionGeometry(action)
            point = self.workspace.mapFromGlobal(menu.mapToGlobal(rect.topLeft()))
            return QRect(point, rect.size()).adjusted(-4, -3, 4, 3)
        return provider

    def _highlight_menu_action(self, menu, action):
        pulse = Spotlight(menu)
        pulse.setGeometry(menu.rect())
        pulse.set_target_rect(menu.actionGeometry(action).adjusted(2, 1, -2, -1))
        pulse.start()
        self._menu_spotlight = pulse

    def _menubar_action_rect(self, menu):
        def provider():
            bar = self.workspace.menuBar()
            rect = bar.actionGeometry(menu.menuAction())
            point = bar.mapTo(self.workspace, rect.topLeft())
            return QRect(point, rect.size()).adjusted(-4, -3, 4, 3)
        return provider

    def _graphics_rect(self, item):
        def provider():
            if self.editor is None or item is None or item.scene() is None:
                return QRect()
            polygon = self.editor.view.mapFromScene(item.sceneBoundingRect())
            rect = polygon.boundingRect()
            point = self.editor.view.viewport().mapTo(self.editor, rect.topLeft())
            return QRect(point, rect.size()).adjusted(-7, -7, 7, 7)
        return provider

    @staticmethod
    def _widget_rect(widget, host):
        def provider():
            point = widget.mapTo(host, QPoint(0, 0))
            return QRect(point, widget.size()).adjusted(-7, -7, 7, 7)
        return provider

    def _document_rect(self):
        def provider():
            rect = self.editor.view.mapFromScene(self.editor._document_rect).boundingRect()
            point = self.editor.view.viewport().mapTo(self.editor, rect.topLeft())
            return QRect(point, rect.size())
        return provider

    def _place_card_above(self, widget):
        """Mantém o cartão fora de um bloco de controles compacto."""
        if self.coach is None:
            return
        card = self.coach.card
        target_top = widget.mapTo(self.editor, QPoint(0, 0)).y()
        margin = 18
        y = max(margin, target_top - card.height() - 30)
        x = max(margin, min(card.x(), self.editor.width() - card.width() - margin))
        card.move(x, y)
        card._manually_positioned = True

    def _place_card_right_of_document(self):
        """Libera o documento para o redimensionamento orientado."""
        if self.coach is None or self.editor is None:
            return
        card = self.coach.card
        document = self._document_rect()()
        margin = 18
        x = min(self.editor.width() - card.width() - margin, document.right() + 30)
        x = max(margin, x)
        y = document.center().y() - card.height() // 2
        y = max(margin, min(y, self.editor.height() - card.height() - margin))
        card.move(x, y)
        card._manually_positioned = True

    @staticmethod
    def _important_article(parts):
        """Monta explicações longas com parágrafos, tópicos e exemplos."""
        text = theme_color("text")
        muted = theme_color("muted")
        surface = theme_color("surface")
        accent = theme_color("accent")
        html = [f'<div style="color:{text};">']
        for kind, value in parts:
            safe = escape(value).replace("\n", "<br>")
            if kind == "paragraph":
                html.append(f'<p align="justify" style="margin:0 0 12px 0;">{safe}</p>')
            elif kind == "bullet":
                html.append(f'<p align="justify" style="margin:0 0 7px 16px;">• {safe}</p>')
            elif kind == "label":
                html.append(f'<p style="margin:10px 0 5px 0; color:{accent};"><b>{safe}</b></p>')
            elif kind == "quote":
                html.append(
                    f'<table width="100%" cellspacing="0" cellpadding="12" bgcolor="{surface}" '
                    f'style="border-left:4px solid {accent}; margin:5px 0 12px 0;">'
                    f'<tr><td style="color:{text};">{safe}</td></tr></table>'
                )
            elif kind == "rich_quote":
                html.append(
                    f'<table width="100%" cellspacing="0" cellpadding="12" bgcolor="{surface}" '
                    f'style="border-left:4px solid {accent}; margin:5px 0 12px 0;">'
                    f'<tr><td style="color:{text};">{value}</td></tr></table>'
                )
            elif kind == "note":
                html.append(f'<p align="justify" style="color:{muted}; margin:8px 0 0 0;"><i>{safe}</i></p>')
        html.append("</div>")
        return "".join(html)

    @staticmethod
    def _marked_example(value, *marked_parts):
        """Destaca a sintaxe ensinada como uma marca de marca-texto."""
        rendered = escape(value).replace("\n", "<br>")
        marker = QColor(theme_color("warning"))
        base = QColor(theme_color("surface"))
        # QTextDocument não trata alpha em CSS de modo uniforme entre os
        # sistemas. A mistura prévia reproduz 50% de opacidade com resultado
        # idêntico e portátil.
        marker.setRed((marker.red() + base.red()) // 2)
        marker.setGreen((marker.green() + base.green()) // 2)
        marker.setBlue((marker.blue() + base.blue()) // 2)
        foreground = "#111111" if marker.lightness() >= 135 else "#ffffff"
        style = (
            f"background-color:{marker.name()}; color:{foreground}; "
            "font-weight:700; padding:1px 3px;"
        )
        for part in sorted(marked_parts, key=len, reverse=True):
            safe = escape(part).replace("\n", "<br>")
            rendered = rendered.replace(safe, f'<span style="{style}">{safe}</span>')
        return rendered

    @classmethod
    def _marked_optional_example(cls, value):
        start = value.find("|")
        end = value.find("|", start + 1)
        marked = value[start:end + 1] if start >= 0 and end > start else ""
        return cls._marked_example(value, marked) if marked else escape(value)

    def _table_column(self, name):
        table = self.workspace.table_panel.table
        for column in range(table.columnCount()):
            if table_column_key(table.horizontalHeaderItem(column)) == name:
                return column
        return -1

    def _table_range_rect(self, columns=("nome", "programa"), rows=10):
        def provider():
            table = self.workspace.table_panel.table
            logical = [self._table_column(name) for name in columns]
            logical = [column for column in logical if column >= 0]
            if not logical or not table.isVisible():
                return QRect()
            rect = QRect()
            for row in range(min(rows, table.rowCount())):
                for column in logical:
                    cell = table.visualRect(table.model().index(row, column))
                    rect = cell if rect.isNull() else rect.united(cell)
            point = table.viewport().mapTo(self.workspace, rect.topLeft())
            return QRect(point, rect.size()).adjusted(-3, -3, 3, 3)
        return provider

    def _set_clipboard_text(self, text):
        QApplication.clipboard().setText(text)

    def _plain_box_text(self):
        if self.text_box is None:
            return ""
        document = QTextDocument()
        document.setHtml(self.text_box.state.html_content)
        return document.toPlainText()

    def _tutorial_values_ok(self, names=True, programs=True):
        table = self.workspace.table_panel.table
        name_col = self._table_column("nome")
        program_col = self._table_column("programa")
        if table.rowCount() < 10 or name_col < 0 or program_col < 0:
            return False
        for row in range(10):
            if names:
                item = table.item(row, name_col)
                if item is None or item.text().strip() != NAMES[row]:
                    return False
            if programs:
                item = table.item(row, program_col)
                if item is None or item.text().strip() != PROGRAM:
                    return False
        return True

    def _tutorial_data_empty(self):
        table = self.workspace.table_panel.table
        for name in ("nome", "programa"):
            column = self._table_column(name)
            if column < 0:
                continue
            for row in range(table.rowCount()):
                item = table.item(row, column)
                if item is not None and item.text().strip():
                    return False
        return True

    def _prepare_workspace_table(self):
        panel = self.workspace.table_panel
        if not panel.isVisible() and self.workspace._workspace_data_toggle.isVisible():
            self.workspace._workspace_data_toggle.click()

    def _show_step(self):
        self._disconnect_stage()
        if self.step <= 3 or self.step >= 20:
            self._show_workspace_step()
        else:
            self._show_editor_step()

    def _show_workspace_step(self):
        w = self.workspace
        if self.step == 1:
            self._show(w, title=tr("Primeiros passos"), back=False,
                       next_text=tr("Começar"), body=tr(
                "Você criará um modelo, preencherá dez itens e gerará o primeiro trabalho. "
                "O tutorial acompanhará suas ações diretamente nos controles do programa."))
        elif self.step == 2:
            menu = w._model_menu
            self._show(w, provider=self._menubar_action_rect(menu), wait=True,
                       action=tr("Clique em Arquivo"),
                       title=tr("Abra o menu Arquivo"), body=tr(
                "Os modelos definem o visual e os campos personalizados. Clique em Arquivo."))
            self._connect(menu.aboutToShow, lambda: QTimer.singleShot(0, lambda: self._advance(2)))
        elif self.step == 3:
            menu, action = w._model_menu, w._new_model_action
            menu.setActiveAction(action)
            self._show(w, provider=self._menu_action_rect(menu, action), wait=True,
                       highlight=False,
                       action=tr("Clique em Novo modelo"),
                       title=tr("Crie um modelo"), body=tr(
                "Clique em Novo modelo para abrir um documento vazio no editor."))
            self._highlight_menu_action(menu, action)
            self._connect(action.triggered, self._new_editor_opened)
        elif self.step == 20:
            self._prepare_workspace_table()
            if self._phase == 0:
                self._show(w, target=w.preview_panel.cbo_models,
                           title=tr("Modelo salvo"), body=tr(
                    "O novo modelo está selecionado na biblioteca."))
            else:
                self._show(w, provider=self._table_range_rect(("nome", "programa"), 1),
                           title=tr("Campos criados"), body=tr(
                    "Os placeholders criaram automaticamente as colunas nome e programa, prontas para receber os dados."))
        elif self.step == 21:
            self._prepare_workspace_table()
            self._set_clipboard_text("\n".join(NAMES))
            self._show(w, provider=self._table_range_rect(("nome",), 1), wait=True,
                       action=tr("Clique na primeira célula e pressione Ctrl+V"),
                       title=tr("Cole dez nomes"), body=tr(
                "Dez nomes foram copiados. Clique na primeira célula de nome e pressione Ctrl+V."))
            self._poll.start()
        elif self.step == 22:
            if self._phase == 0:
                self._show(w, provider=self._table_range_rect(("nome",), 10),
                           title=tr("Dez linhas de uma vez"), body=tr(
                    "Uma única colagem preencheu dez linhas. O FORNAX preserva a estrutura copiada de uma planilha."))
            else:
                self._show(w, target=w.preview_panel, title=tr("Trecho opcional em ação"), body=tr(
                    "O preview já mostra os nomes porque programa está dentro de um trecho opcional. "
                    "Esse trecho permanece oculto até a segunda coluna ser preenchida."),
                           preserve=True)
        elif self.step == 23:
            self._set_clipboard_text("\n".join([PROGRAM] * 10))
            self._show(w, provider=self._table_range_rect(("programa",), 1), wait=True,
                       action=tr("Clique na primeira célula e pressione Ctrl+V"),
                       title=tr("Complete a segunda coluna"), body=tr(
                "FORNAX Forge foi copiado dez vezes. Clique na primeira célula de programa e pressione Ctrl+V."))
            self._poll.start()
        elif self.step == 24:
            if self._phase == 0:
                self._show(w, provider=self._table_range_rect(("nome", "programa"), 10),
                           title=tr("Duas colunas preenchidas"), body=tr(
                    "As dez linhas agora possuem nome e programa."))
            elif self._phase == 1:
                self._seen_rows = set()
                self._show(w, target=w.preview_panel, wait=True,
                           action=tr("Clique em linhas diferentes da tabela"),
                           title=tr("Confira o preview"), body=tr(
                    "Selecione linhas diferentes e observe o preview mudar em tempo real."),
                           preserve=True)
                self._connect(w.table_panel.table.itemSelectionChanged, self._workspace_row_changed)
            else:
                self._show(w, target=w.preview_panel, title=tr("Preview atualizado"), body=tr(
                    "O preview mostra o conteúdo da linha selecionada antes da geração."),
                           preserve=True)
        elif self.step == 25:
            table = w.table_panel.table
            self._show(w, target=w.table_panel.btn_delete_rows, wait=True,
                       action=tr("Clique em uma célula, pressione Ctrl+A e clique em Excluir"),
                       title=tr("Exclua as linhas"), body=tr(
                "Ctrl+A seleciona todas as linhas. O botão Excluir remove as linhas selecionadas e também pode ser usado com uma ou várias linhas."))
            self._connect(w.table_panel.btn_delete_rows.clicked,
                          lambda: QTimer.singleShot(0, self._after_delete))
            table.setFocus()
        elif self.step == 26:
            combined = "\n".join(f"{name}\t{PROGRAM}" for name in NAMES)
            self._set_clipboard_text(combined)
            self._show(w, provider=self._table_range_rect(("nome",), 1), wait=True,
                       action=tr("Clique na primeira célula e pressione Ctrl+V"),
                       title=tr("Cole duas colunas"), body=tr(
                "Os nomes e o programa foram copiados juntos. Clique na primeira célula de nome e pressione Ctrl+V."))
            self._poll.start()
        elif self.step == 27:
            if self._phase == 0:
                self._show(w, provider=self._table_range_rect(("nome", "programa"), 10),
                           title=tr("Use seus dados existentes"), body=tr(
                    "Você pode copiar várias linhas e colunas do Excel, Google Sheets ou LibreOffice, evitando redigitação."))
            elif self._phase == 1:
                self._seen_rows = set()
                self._show(w, target=w.preview_panel, wait=True,
                           action=tr("Clique em dois itens diferentes"),
                           title=tr("Navegue pelos itens"), body=tr(
                    "Selecione dois itens diferentes para conferir a atualização do preview."),
                           preserve=True)
                self._connect(w.table_panel.table.itemSelectionChanged, self._workspace_row_changed)
            else:
                self._show(w, target=w.preview_panel, title=tr("Dados conferidos"), body=tr(
                    "O preview acompanhou os itens escolhidos. Agora o trabalho está pronto para ser gerado."),
                           preserve=True)
        elif self.step == 28:
            self._show(w, target=w.btn_sel_out, wait=True,
                       action=tr("Clique nos três pontos"),
                       title=tr("Escolha o destino"), body=tr(
                "Clique nos três pontos e escolha a pasta onde os trabalhos serão armazenados."))
            self._connect(w.btn_sel_out.clicked,
                          lambda: QTimer.singleShot(0, self._output_folder_selected))
        elif self.step == 29:
            self._show(w, target=w.txt_output_path,
                       title=tr("Pasta principal"), body=tr(
                "Cada geração será guardada dentro desta pasta em uma pasta exclusiva."))
        elif self.step == 30:
            menu = w._view_menu
            self._show(w, provider=self._menubar_action_rect(menu), wait=True,
                       action=tr("Clique em Exibir"),
                       title=tr("Abra o menu Exibir"), body=tr(
                "Antes de gerar, vamos abrir o log. Clique em Exibir."))
            self._connect(menu.aboutToShow, lambda: QTimer.singleShot(0, lambda: self._advance(30)))
        elif self.step == 31:
            menu, action = w._view_menu, w._workspace_log_toggle
            menu.setActiveAction(action)
            already_visible = action.isChecked()
            self._show(w, provider=self._menu_action_rect(menu, action),
                       highlight=False,
                       action=tr("Clique em Log de processamento") if not already_visible else "",
                       wait=not already_visible, title=tr("Mostre o log"), body=(
                tr("O log já está visível. Continue para conhecê-lo.") if already_visible
                else tr("Clique em Log de processamento para exibi-lo.")))
            self._highlight_menu_action(menu, action)
            if not already_visible:
                self._connect(action.toggled, self._log_toggled)
        elif self.step == 32:
            self._show(w, target=w.log_panel, title=tr("Log de processamento"), body=tr(
                "O log mostra andamento, avisos e resultados. Ele ajuda a acompanhar trabalhos maiores e identificar dados que precisam de atenção."))
        elif self.step == 33:
            formats = (
                (tr("PNG"), tr(
                    "PNG é indicado para compartilhamento digital e gera uma imagem separada para cada item.")),
                (tr("PDF por item"), tr(
                    "PDF por item preserva as dimensões de impressão e os links clicáveis do documento, como localizações e formulários, criando um PDF separado para cada item.")),
                (tr("PDF agrupado"), tr(
                    "PDF agrupado reúne todos os itens e páginas em um único arquivo, facilitando a impressão completa em um só comando. Escolha qualquer formato para continuar.")),
            )
            title, body = formats[self._phase]
            self._show(w, target=w.cbo_export_format, title=title, body=body,
                       preserve=self._phase > 0)
        elif self.step == 34:
            self._show(w, target=w.btn_generate_cards, wait=True,
                       action=tr("Clique em Gerar material"),
                       title=tr("Gere o material"), body=tr(
                "Clique em Gerar material. As dez linhas produzirão dez cartões personalizados."))
            self._connect(w.btn_generate_cards.clicked,
                          lambda: QTimer.singleShot(0, self._generation_started))
        elif self.step == 35:
            self._show(w, target=w.log_panel, wait=True, back=False,
                       title=tr("Acompanhe a velocidade"), body=tr(
                "Acompanhe o tempo real no log. Um trabalho que exigiria editar dez cartões individualmente é concluído automaticamente em poucos segundos."))
        elif self.step == 36:
            duration = getattr(w, "_last_generation_duration", 0.0)
            if duration < 60:
                time_text = tr("{tempo:.1f} segundos").format(tempo=duration)
            else:
                time_text = tr("{minutos} min {segundos}s").format(
                    minutos=int(duration // 60), segundos=int(duration % 60))
            self._show(w, target=w.log_panel, title=tr("Geração concluída"), body=tr(
                "Os dez itens foram gerados em {tempo}. O log é opcional: mantenha-o visível para acompanhar detalhes ou oculte-o para ampliar a área de trabalho.").format(tempo=time_text))
        elif self.step == 37:
            folder = self._last_output_dir or getattr(w, "_last_forge_output_dir", None)
            folder_path = Path(folder) if folder else None
            name = folder_path.name if folder_path else tr("a nova pasta da Forja")
            destination = str(folder_path.parent) if folder_path else str(Path(w.txt_output_path.text().strip()))
            self._show(w, target=w.log_panel, title=tr("Trabalho organizado"),
                       next_text=tr("Concluir"), body=tr(
                "Trabalho concluído: dez cartões foram reunidos na pasta {pasta}. "
                "Cada geração cria uma nova Forja numerada para não misturar arquivos de trabalhos diferentes."
                ).format(pasta=name),
                       link_text=tr("Abrir pasta: {destino}").format(destino=destination),
                       link_url=QUrl.fromLocalFile(destination).toString())

    def _show_editor_step(self):
        e = self.editor
        if e is None:
            return
        if self.step == 4:
            self._show(e, provider=self._document_rect(), title=tr("Área do documento"), body=tr(
                "Tudo que permanecer dentro da página fará parte do material gerado. A área externa pode ser usada para organizar objetos."))
        elif self.step == 5:
            self._show(e, target=e.btn_add, wait=True, action=tr("Clique em Texto"),
                       title=tr("Adicione texto"), body=tr(
                "Clique em Texto para adicionar o primeiro conteúdo personalizado."))
            self._connect(e.btn_add.clicked, lambda: QTimer.singleShot(0, self._text_added))
        elif self.step == 6:
            self._show(e, provider=self._graphics_rect(self.text_box), title=tr("Texto adicionado"), body=tr(
                "A caixa está selecionada. Os marcadores ao redor dela permitem mudar seu tamanho."))
        elif self.step == 7:
            self._initial_box_size = (self.text_box.rect().width(), self.text_box.rect().height())
            self._show(e, provider=self._graphics_rect(self.text_box), wait=True,
                       action=tr("Clique em um nó da borda ou do canto e arraste"),
                       title=tr("Redimensione a caixa"), body=tr(
                "Use um dos marcadores nas bordas ou nos cantos para deixar a caixa mais larga. O texto se adapta ao novo espaço."))
            self._poll.start()
        elif self.step == 8:
            self._show(e, provider=self._graphics_rect(self.text_box), title=tr("Novo tamanho"), body=tr(
                "A caixa agora possui mais espaço. Textos e outros objetos podem ser redimensionados dessa forma."))
        elif self.step == 9:
            e._text_section.header.setChecked(True)
            self._show(e, target=e._text_section.header,
                       title=tr("Menu Texto"), body=tr(
                "Este é o menu Texto da barra lateral direita. Nele você ajusta fonte, tamanho, cor, estilo, alinhamento, entrelinha e recuo."))
        elif self.step == 10:
            button = e.editor_texto_panel.alignment_buttons[1]
            self._show(e, target=button,
                       wait=True, action=tr("Clique em Centralizar"),
                       title=tr("Centralize horizontalmente"), body=tr(
                "Clique em Centralizar para alinhar as linhas no centro da caixa."))
            self._place_card_above(e.editor_texto_panel.alignment_widget)
            self._connect(button.clicked, lambda: QTimer.singleShot(0, self._horizontal_aligned))
        elif self.step == 11:
            self._show(e, provider=self._graphics_rect(self.text_box), title=tr("Alinhamento horizontal"), body=tr(
                "O conteúdo agora está centralizado entre as laterais da caixa."))
        elif self.step == 12:
            button = e.editor_texto_panel.alignment_buttons[5]
            self._show(e, target=button,
                       wait=True, action=tr("Clique em Meio"),
                       title=tr("Centralize verticalmente"), body=tr(
                "Clique em Meio para posicionar o texto no centro vertical da caixa."))
            self._place_card_above(e.editor_texto_panel.alignment_widget)
            self._connect(button.clicked, lambda: QTimer.singleShot(0, self._vertical_aligned))
        elif self.step == 13:
            self._show(e, provider=self._graphics_rect(self.text_box), title=tr("Centralizado nos dois sentidos"), body=tr(
                "Os alinhamentos horizontal e vertical são independentes e agora estão centralizados."))
        elif self.step == 14:
            spin = e.editor_texto_panel.spin_size
            self._show(e, target=spin, wait=True,
                       action=tr("Defina o tamanho da fonte como 45"),
                       title=tr("Aumente a legibilidade"), body=tr(
                "Altere o tamanho para 45 para criar um cartão fácil de ler."))
            self._connect(spin.valueChanged, self._font_size_changed)
        elif self.step == 15:
            if self._phase == 0:
                self._set_clipboard_text(MODEL_TEXT)
                self._show(e, provider=self._graphics_rect(self.text_box), wait=True,
                           action=tr("Dê dois cliques, pressione Ctrl+A e depois Ctrl+V"),
                           title=tr("Cole o conteúdo do exercício"), body=tr(
                    "O texto foi copiado. Dê dois cliques na caixa, pressione Ctrl+A e depois Ctrl+V."))
                self._poll.start()
            else:
                self._initial_box_size = (
                    self.text_box.rect().width(), self.text_box.rect().height())
                self._show(e, provider=self._graphics_rect(self.text_box),
                           action=tr("Saia da edição e reajuste a caixa"),
                           title=tr("Reajuste a caixa"), body=tr(
                    "Clique fora da caixa para encerrar a edição do texto. Depois, selecione a caixa novamente com um clique simples e arraste seus marcadores até que o conteúdo fique bem distribuído. Quando estiver satisfeito, clique em Continuar."))
                self._place_card_right_of_document()
        elif self.step == 16:
            pages = (
                (tr("O segredo da personalização"), self._important_article((
                    ("paragraph", tr("O segredo da automação eficiente do FORNAX Forge está em dois recursos: placeholders e trechos opcionais.")),
                    ("paragraph", tr("Com eles, você cria o visual uma única vez e usa a tabela para produzir dezenas, centenas ou milhares de itens diferentes. O modelo permanece intacto; somente os dados personalizados mudam.")),
                    ("label", tr("Ao final desta explicação, você saberá:")),
                    ("bullet", tr("como transformar partes do texto em colunas da tabela;")),
                    ("bullet", tr("como mostrar uma caixa somente quando os dados necessários existirem;")),
                    ("bullet", tr("como tornar apenas uma parte da frase opcional.")),
                ))),
                (tr("Como funcionam os placeholders"), self._important_article((
                    ("paragraph", tr("Placeholders são nomes escritos entre chaves, como {nome} e {programa}. Cada placeholder diferente cria automaticamente uma coluna correspondente na tabela de dados.")),
                    ("paragraph", tr("Cada linha da tabela representa um item final. Ao gerar o material, o FORNAX lê aquela linha e substitui cada placeholder pelo conteúdo da célula correspondente.")),
                    ("label", tr("Texto escrito no modelo")),
                    ("rich_quote", self._marked_example(
                        tr("Este cartão foi criado para {nome} com a ajuda de {programa}!"),
                        "{nome}", "{programa}",
                    )),
                    ("label", tr("Exemplo de uma linha da tabela")),
                    ("quote", tr("nome: João\nprograma: LINUX")),
                    ("label", tr("Resultado final no cartão gerado")),
                    ("quote", tr("Este cartão foi criado para João com a ajuda de LINUX!")),
                    ("note", tr("Você pode trocar os dados de cada linha sem abrir nem modificar o modelo.")),
                ))),
                (tr("Caixas condicionais"), self._important_article((
                    ("paragraph", tr("Quando uma caixa de texto possui placeholders obrigatórios, ela só é exibida se todos eles estiverem preenchidos naquela linha. Se faltar um valor, a caixa inteira desaparece do resultado.")),
                    ("paragraph", tr("Isso é útil para informações que existem somente para algumas pessoas. Imagine um convite com duas caixas independentes:")),
                    ("label", tr("Texto escrito no modelo")),
                    ("rich_quote", self._marked_example(
                        tr("Caixa 1: {nome}\nCaixa 2: {funcao} da Cidade de Ponta Grossa - Paraná, Brasil"),
                        "{nome}", "{funcao}",
                    )),
                    ("label", tr("Primeiro exemplo na tabela")),
                    ("quote", tr("nome: Maria Helena da Silva\nfuncao: Prefeita")),
                    ("label", tr("Segundo exemplo na tabela")),
                    ("quote", tr("nome: Eliezer Belisário\nfuncao: [célula vazia]")),
                ))),
                (tr("Resultados das caixas condicionais"), self._important_article((
                    ("paragraph", tr("A mesma estrutura do modelo produz resultados diferentes conforme os dados daquela linha da tabela.")),
                    ("label", tr("Resultado com a função preenchida")),
                    ("quote", tr("Maria Helena da Silva\nPrefeita da Cidade de Ponta Grossa - Paraná, Brasil\n\n[texto do convite]")),
                    ("label", tr("Resultado com a função vazia")),
                    ("quote", tr("Eliezer Belisário\n\n[texto do convite]")),
                    ("note", tr("Como {funcao} ficou vazio para Eliezer, toda a segunda caixa foi ocultada; a caixa com o nome permaneceu visível.")),
                ))),
                (tr("Trechos opcionais"), self._important_article((
                    ("paragraph", tr("Trechos opcionais são delimitados por barras verticais: | trecho |. Um placeholder vazio dentro desse trecho não oculta a caixa inteira; somente o conteúdo entre as barras desaparece.")),
                    ("label", tr("Texto escrito no modelo")),
                    ("rich_quote", self._marked_optional_example(tr(
                        "{nome}| - {funcao} da Cidade de Ponta Grossa - Paraná, Brasil|, é com grande satisfação que lhe convidamos para a solenidade [...]"
                    ))),
                    ("label", tr("Com função preenchida")),
                    ("quote", tr("Maria Helena da Silva - Prefeita da Cidade de Ponta Grossa - Paraná, Brasil, é com grande satisfação que lhe convidamos para a solenidade [...]")),
                    ("label", tr("Com função vazia")),
                    ("quote", tr("Eliezer Belisário, é com grande satisfação que lhe convidamos para a solenidade [...]")),
                ))),
                (tr("Dois recursos, muitas possibilidades"), self._important_article((
                    ("paragraph", tr("Use uma caixa condicional quando toda a informação deve existir ou desaparecer em conjunto. Use um trecho opcional quando apenas uma parte da frase deve desaparecer.")),
                    ("bullet", tr("Placeholder obrigatório vazio: oculta toda a caixa de texto.")),
                    ("bullet", tr("Placeholder vazio dentro de | barras |: oculta somente o trecho opcional.")),
                    ("paragraph", tr("Com essa combinação, o mesmo modelo atende pessoas, cargos e situações diferentes. É uma mala direta visual, simplificada e flexível: você organiza os dados na tabela e deixa o FORNAX montar cada resultado.")),
                    ("label", tr("Sua criatividade é o limite.")),
                ))),
            )
            title, body = pages[self._phase]
            self._show(e, title=title, body=body, important=True,
                       preserve=self._phase > 0)
        elif self.step == 17:
            self._show(e, target=e.btn_save, wait=True,
                       action=tr("Clique em Salvar modelo e depois em Encerrar edição"),
                       title=tr("Salve e encerre a edição"), body=tr(
                "O modelo será adicionado à biblioteca. Quando a confirmação aparecer, clique em Encerrar edição para voltar à tela principal e continuar o tutorial."))
        elif self.step == 18:
            # O QInputDialog modal contém a orientação e mantém o foco correto.
            if self.coach is not None:
                self.coach.card.hide()
                self.coach.spotlight.hide()
        elif self.step == 19:
            if self.coach is not None:
                self.coach.card.hide()
                self.coach.spotlight.hide()

    def _new_editor_opened(self):
        self._disconnect_stage()
        self.editor = getattr(self.workspace, "editor_window", None)
        if self.editor is None:
            return
        self.editor.modelSaved.connect(self._model_was_saved)
        self.step = 4
        QTimer.singleShot(0, self._show_step)

    def _text_added(self):
        from features.editor.canvas_items import DesignerBox
        selected = [item for item in self.editor.scene.selectedItems() if isinstance(item, DesignerBox)]
        if not selected:
            return
        self.text_box = selected[0]
        self._advance(5)

    def _horizontal_aligned(self):
        if self.text_box is not None and self.text_box.state.align == "center":
            self._advance(10)

    def _vertical_aligned(self):
        if self.text_box is not None and self.text_box.state.vertical_align == "center":
            self._advance(12)

    def _font_size_changed(self, value):
        if self.step != 14 or abs(float(value) - 45.0) > 0.01:
            return
        self._advance(14)

    def _model_was_saved(self, *_args):
        self._model_saved = True

    def _workspace_row_changed(self):
        row = self.workspace.table_panel.table.currentRow()
        if row >= 0:
            self._seen_rows.add(row)
        required = 2
        if len(self._seen_rows) >= required:
            expected = self.step
            self._disconnect_stage()
            def show_result():
                if self.step != expected:
                    return
                self._phase = 2
                self._show_step()
            QTimer.singleShot(180, show_result)

    def _after_delete(self):
        if self.step == 25 and self._tutorial_data_empty():
            self._advance(25)

    def _output_folder_selected(self):
        if self.step == 28 and Path(self.workspace.txt_output_path.text().strip()).is_dir():
            self._advance(28)

    def _log_toggled(self, checked):
        if checked:
            QTimer.singleShot(0, lambda: self._advance(31))

    def _generation_started(self):
        if self.step != 34:
            return
        manager = getattr(self.workspace, "manager", None)
        if manager is None or self.workspace.btn_generate_cards.isEnabled():
            return
        self._disconnect_stage()
        self.step = 35
        self._show_step()
        self._connect(manager.finished_process, self._generation_finished)

    def _generation_finished(self):
        if getattr(self.workspace, "_generation_failed", False):
            self._disconnect_stage()
            self.step = 34
            self._show_step()
            return
        self._last_output_dir = getattr(self.workspace, "_last_forge_output_dir", None)
        self._advance(35)

    def _poll_current_step(self):
        if self.step == 7 and self.text_box is not None:
            size = (self.text_box.rect().width(), self.text_box.rect().height())
            if self._initial_box_size and (
                abs(size[0] - self._initial_box_size[0]) > 1
                or abs(size[1] - self._initial_box_size[1]) > 1
            ):
                self._advance(7)
        elif self.step == 15 and self._phase == 0:
            text = re.sub(r"\s+", " ", self._plain_box_text()).strip()
            expected = re.sub(r"\s+", " ", MODEL_TEXT).strip()
            if text == expected:
                self.editor.sync_placeholders_list()
                self._disconnect_stage()
                self._phase = 1
                self._show_step()
        elif self.step == 21 and self._tutorial_values_ok(programs=False):
            self._advance(21)
        elif self.step == 23 and self._tutorial_values_ok():
            self._advance(23)
        elif self.step == 26 and self._tutorial_values_ok():
            self._advance(26)

    def _name_dialog_finished(self, result):
        if result == 0 and self.step == 18:
            self.step = 17
            QTimer.singleShot(0, self._show_step)

    def _save_message_finished(self, _result):
        QTimer.singleShot(200, self._after_save_message)

    def _after_save_message(self):
        if self.step != 19:
            return
        if self.workspace.isVisible():
            self.step = 20
            self._show_step()
        elif self.editor is not None and self.editor.isVisible():
            self.step = 17
            self._show_step()

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Show:
            if isinstance(watched, QInputDialog) and self.step == 17:
                self._disconnect_stage()
                self.step = 18
                self._show_editor_step()
                watched.setLabelText(tr(
                    "Digite um nome para reconhecer este modelo. Você pode usar “Meu primeiro modelo”."
                ))
                line_edit = watched.findChild(QLineEdit)
                if line_edit is not None:
                    line_edit.setPlaceholderText(tr("Meu primeiro modelo"))
                self._connect(watched.finished, self._name_dialog_finished)
            elif (isinstance(watched, QMessageBox) and self.step in (17, 18, 19)
                  and self._model_saved and watched.windowTitle() == tr("Sucesso")):
                self._disconnect_stage()
                self.step = 19
                self._show_editor_step()
                self._connect(watched.finished, self._save_message_finished)
            elif watched is self.workspace and self.step == 19:
                QTimer.singleShot(150, self._after_save_message)
        return False

    def finish(self):
        self._disconnect_stage()
        try:
            QApplication.instance().removeEventFilter(self)
        except RuntimeError:
            pass
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self._clipboard_backup)
        if self.coach is not None:
            self.coach.close()
            self.coach = None
        if getattr(self.workspace, "_active_tutorial", None) is self:
            self.workspace._active_tutorial = None
        self.deleteLater()


def start_first_steps_tutorial(workspace):
    current = getattr(workspace, "_active_tutorial", None)
    if current is not None:
        current.finish()
    tutorial = FirstStepsTutorial(workspace)
    workspace._active_tutorial = tutorial
    tutorial.start()
    return tutorial
