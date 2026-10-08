"""Busca de tópicos e leitura de artigos Markdown com widgets nativos do Qt."""

from PySide6.QtCore import Qt, QSignalBlocker
from PySide6.QtGui import QAction, QKeySequence, QTextBlockFormat, QTextCursor
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QSplitter, QTextBrowser, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)
from shiboken6 import isValid

from core.dialog_buttons import style_dialog_button_box
from core.help_catalog import help_catalog
from core.i18n import current_locale, tr
from core.themes import themed_style


STYLE = """
QDialog#helpDialog { background: @panel@; color: @text@; }
QWidget#helpTopics, QWidget#helpArticle { background: transparent; color: @text@; }
QLabel { background: transparent; color: @text@; }
QLabel#helpHeading { font-size: 20px; font-weight: 700; }
QLabel#helpArticleTitle { font-size: 18px; font-weight: 600; }
QLabel#helpHint, QLabel#helpCategory, QLabel#helpCount { color: @muted@; }
QLineEdit#helpSearch, QComboBox#helpFilter {
    background: @field@; color: @text@; border: 1px solid @border@;
    border-radius: 5px; padding: 7px 8px;
}
QLineEdit#helpSearch:focus, QComboBox#helpFilter:focus { border-color: @accent@; }
QComboBox#helpFilter QAbstractItemView {
    background: @field@; color: @text@; selection-background-color: @selection@;
    selection-color: @text@; border: 1px solid @border@;
}
QTreeWidget#helpResults, QTextBrowser#helpContent {
    background: @field@; color: @text@; border: 1px solid @border@;
    border-radius: 5px; padding: 6px; selection-background-color: @selection@;
    selection-color: @text@;
}
QTreeWidget#helpResults::item { padding: 6px 4px; }
QTreeWidget#helpResults::item:selected { background: @selection@; color: @text@; }
QTreeWidget#helpResults::item:hover { background: @hover@; }
QSplitter::handle { background: @border@; }
"""


class HelpDialog(QDialog):
    def __init__(self, parent=None, *, catalog=None):
        super().__init__(parent)
        self.catalog = catalog if catalog is not None else help_catalog(current_locale())
        self._last_query = ""
        self._match_count = len(self.catalog.topics)
        self.setObjectName("helpDialog")
        self.setWindowTitle(tr("Central de ajuda — FORNAX Forge"))
        self.resize(1000, 680)
        self.setMinimumSize(650, 440)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)
        heading = QLabel(tr("Central de ajuda"))
        heading.setObjectName("helpHeading")
        layout.addWidget(heading)
        hint = QLabel(tr("Pesquise uma ferramenta ou escolha um tópico do editor."))
        hint.setObjectName("helpHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        search_row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setObjectName("helpSearch")
        self.search.setPlaceholderText(tr("Buscar na ajuda… Ex.: máscara, guias, transparência"))
        self.search.setAccessibleName(tr("Buscar na ajuda"))
        self.search.setClearButtonEnabled(True)
        search_row.addWidget(self.search, 1)
        self.category_filter = QComboBox()
        self.category_filter.setObjectName("helpFilter")
        self.category_filter.setAccessibleName(tr("Categoria da ajuda"))
        self.category_filter.addItem(tr("Todas as categorias"), None)
        used_categories = {topic.category for topic in self.catalog.topics}
        for category, title in self.catalog.categories.items():
            if category in used_categories:
                self.category_filter.addItem(title, category)
        self.category_filter.setMaximumWidth(340)
        search_row.addWidget(self.category_filter)
        layout.addLayout(search_row)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(1)
        left = QWidget()
        left.setObjectName("helpTopics")
        left.setMinimumWidth(230)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 10, 0)
        left_layout.setSpacing(8)
        self.count = QLabel()
        self.count.setObjectName("helpCount")
        left_layout.addWidget(self.count)
        self.results = QTreeWidget()
        self.results.setObjectName("helpResults")
        self.results.setHeaderHidden(True)
        self.results.setExpandsOnDoubleClick(False)
        self.results.setUniformRowHeights(True)
        self.results.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.results.header().setStretchLastSection(True)
        self.results.setAccessibleName(tr("Tópicos da ajuda"))
        left_layout.addWidget(self.results, 1)
        splitter.addWidget(left)

        right = QWidget()
        right.setObjectName("helpArticle")
        right.setMinimumWidth(260)
        article_layout = QVBoxLayout(right)
        article_layout.setContentsMargins(10, 0, 0, 0)
        article_layout.setSpacing(8)
        self.article_title = QLabel()
        self.article_title.setObjectName("helpArticleTitle")
        self.article_title.setWordWrap(True)
        self.article_title.setTextFormat(Qt.TextFormat.PlainText)
        self.article_title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        article_layout.addWidget(self.article_title)
        self.article_category = QLabel()
        self.article_category.setObjectName("helpCategory")
        self.article_category.setWordWrap(True)
        self.article_category.setTextFormat(Qt.TextFormat.PlainText)
        article_layout.addWidget(self.article_category)
        self.content = QTextBrowser()
        self.content.setObjectName("helpContent")
        self.content.setAccessibleName(tr("Conteúdo da ajuda"))
        self.content.setOpenLinks(False)
        self.content.setOpenExternalLinks(False)
        self.content.document().setDocumentMargin(12)
        self.content.anchorClicked.connect(self._follow_link)
        article_layout.addWidget(self.content, 1)
        splitter.addWidget(right)
        splitter.setSizes([360, 600])
        layout.addWidget(splitter, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText(tr("Fechar"))
        # Enter no campo de busca leva à lista, sem acionar Fechar.
        for button in buttons.buttons():
            button.setAutoDefault(False)
            button.setDefault(False)
        buttons.rejected.connect(self.close)
        style_dialog_button_box(buttons)
        layout.addWidget(buttons)
        themed_style(self, STYLE)
        self.search.textChanged.connect(self._filter_topics)
        self.category_filter.currentIndexChanged.connect(self._filter_topics)
        self.results.currentItemChanged.connect(self._select_topic)
        self.results.itemClicked.connect(self._toggle_category)
        self.search.returnPressed.connect(lambda: self.results.setFocus())
        self._filter_topics()

    def _filter_topics(self, *_):
        selected = self.results.currentItem()
        previous_id = selected.data(0, Qt.ItemDataRole.UserRole) if selected else None
        query = self.search.text()
        if query != self._last_query:
            previous_id = None
        self._last_query = query
        found = self.catalog.search(query, self.category_filter.currentData())
        self._match_count = len(found)
        self.count.setText(tr("{quantidade} tópicos").format(quantidade=len(found)))
        chosen = None
        searching = bool(self.search.text().strip()) or self.category_filter.currentData() is not None
        with QSignalBlocker(self.results):
            self.results.clear()
            groups = {}
            first = None
            for topic in found:
                if topic.category not in groups:
                    group = QTreeWidgetItem([self.catalog.categories[topic.category]])
                    group.setFlags(Qt.ItemFlag.ItemIsEnabled)
                    group.setToolTip(0, group.text(0))
                    font = group.font(0)
                    font.setBold(True)
                    group.setFont(0, font)
                    self.results.addTopLevelItem(group)
                    groups[topic.category] = group
                item = QTreeWidgetItem(groups[topic.category], [topic.title])
                item.setData(0, Qt.ItemDataRole.UserRole, topic.id)
                item.setToolTip(0, topic.title)
                first = first or item
                if topic.id == previous_id:
                    chosen = item
            if searching:
                self.results.expandAll()
                chosen = chosen or first
            if chosen:
                chosen.parent().setExpanded(True)
                self.results.setCurrentItem(chosen)
        if chosen:
            self.results.scrollToItem(chosen)
        self._select_topic(chosen)

    def _toggle_category(self, item, _column):
        if item.parent() is None:
            item.setExpanded(not item.isExpanded())

    def _select_topic(self, item, previous=None):
        # Categorias organizam a lista; navegar por elas mantém o artigo aberto.
        if item is not None and item.parent() is None:
            return
        identifier = item.data(0, Qt.ItemDataRole.UserRole) if item else None
        topic = self.catalog.by_id.get(identifier)
        if topic is None:
            self.article_title.setText(tr("Escolha um tópico") if self._match_count
                                       else tr("Nenhum tópico encontrado"))
            self.article_category.clear()
            self.content.setPlainText(tr("Selecione um item da lista para consultar a ajuda.")
                                      if self._match_count
                                      else tr("Tente outro termo ou selecione todas as categorias."))
        else:
            self.article_title.setText(topic.title)
            self.article_category.setText(self.catalog.categories[topic.category])
            if topic.markdown:
                self._set_article_markdown(topic.markdown)
            else:
                self.content.setPlainText(tr("Descrição ainda não disponível."))
        self.content.verticalScrollBar().setValue(0)

    def _set_article_markdown(self, markdown):
        self.content.setMarkdown(markdown)
        # O importador Markdown do Qt deixa os títulos sem margem. Aplicar
        # espaçamento aos blocos preserva listas, links e formatação do artigo.
        document = self.content.document()
        block = document.begin()
        while block.isValid():
            formatting = block.blockFormat()
            heading = bool(formatting.headingLevel())
            formatting.setTopMargin(22 if heading and block.previous().isValid() else 0)
            formatting.setBottomMargin(10 if heading or not block.textList() else 5)
            formatting.setLineHeight(120 if heading else 125,
                                     QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
            QTextCursor(block).setBlockFormat(formatting)
            block = block.next()

    def _follow_link(self, url):
        if url.scheme() == "help":
            self.open_topic(url.path())

    def open_topic(self, identifier):
        """Ponto de entrada para links internos e futura ajuda contextual."""
        if identifier not in self.catalog.by_id:
            return
        with QSignalBlocker(self.search), QSignalBlocker(self.category_filter):
            self.search.clear()
            self.category_filter.setCurrentIndex(0)
        self._filter_topics()
        for row in range(self.results.topLevelItemCount()):
            group = self.results.topLevelItem(row)
            for child in range(group.childCount()):
                item = group.child(child)
                if item.data(0, Qt.ItemDataRole.UserRole) == identifier:
                    group.setExpanded(True)
                    self.results.setCurrentItem(item)
                    self.results.scrollToItem(item)
                    return


def show_help(parent):
    """Reutiliza uma janela não modal, preservando busca e posição de leitura."""
    dialog = getattr(parent, "_help_dialog", None)
    if dialog is None or not isValid(dialog):
        try:
            dialog = HelpDialog(parent)
        except (OSError, ValueError, KeyError, TypeError) as error:
            QMessageBox.warning(parent, tr("Central de ajuda"),
                                tr("Não foi possível carregar os tópicos da ajuda.") + "\n" + str(error))
            return None
        parent._help_dialog = dialog
    dialog.show()
    dialog.raise_()
    dialog.activateWindow()
    dialog.search.setFocus()
    return dialog


def add_help_action(menu, parent):
    action = QAction(tr("Central de ajuda…"), parent)
    action.setShortcut(QKeySequence("F1"))
    action.triggered.connect(lambda: show_help(parent))
    menu.addAction(action)
    parent._help_action = action
    return action
