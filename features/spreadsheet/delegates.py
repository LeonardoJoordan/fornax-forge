import re
from PySide6.QtWidgets import (QStyledItemDelegate, QStyle, QStyleOptionViewItem,
                               QApplication, QTextEdit, QToolTip, QAbstractItemDelegate)
from PySide6.QtGui import (QTextDocument, QPalette, QTextCursor, QFont, QPen, QColor,
                           QTextOption, QPainter)
from PySide6.QtCore import Qt, QEvent, QRectF, QRect, QPointF
from core.themes import theme_color
from core.html_utils import TextOnlyDocument, sanitize_text_html


RICH_TEXT_STYLESHEET = "b, strong { font-weight: 800; }"


def rich_text_document(html, font, color, *, no_wrap=False):
    """Monta o documento usado tanto na célula quanto nos testes visuais."""
    doc = TextOnlyDocument()
    doc.setDefaultFont(font)
    doc.setDefaultStyleSheet(
        f"body {{ color: {color}; }} {RICH_TEXT_STYLESHEET}"
    )
    doc.setHtml(sanitize_text_html(html))
    _promote_bold_fragments(doc)
    doc.setDocumentMargin(0 if no_wrap else 2)
    if no_wrap:
        option = doc.defaultTextOption()
        option.setWrapMode(QTextOption.WrapMode.NoWrap)
        doc.setDefaultTextOption(option)
    return doc


def _promote_bold_fragments(document):
    ranges = []
    block = document.begin()
    while block.isValid():
        iterator = block.begin()
        while not iterator.atEnd():
            fragment = iterator.fragment()
            if fragment.isValid() and fragment.charFormat().fontWeight() >= QFont.Weight.Bold:
                ranges.append((fragment.position(), fragment.length()))
            iterator += 1
        block = block.next()
    for position, length in ranges:
        cursor = QTextCursor(document)
        cursor.setPosition(position)
        cursor.setPosition(position + length, QTextCursor.MoveMode.KeepAnchor)
        fmt = cursor.charFormat()
        fmt.setFontWeight(QFont.Weight.ExtraBold)
        cursor.mergeCharFormat(fmt)

class RichTextEditor(QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptRichText(True)
        self.document().setDefaultStyleSheet(RICH_TEXT_STYLESHEET)
        self.setFrameShape(QTextEdit.Shape.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
    def keyPressEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            key = event.key()
            if key == Qt.Key.Key_B:
                self._toggle_weight()
                return
            elif key == Qt.Key.Key_I:
                self._toggle_italic()
                return
            elif key == Qt.Key.Key_U:
                self._toggle_underline()
                return
        super().keyPressEvent(event)

    def _toggle_weight(self):
        fmt = self.currentCharFormat()
        new_weight = QFont.Weight.Normal if fmt.fontWeight() > QFont.Weight.Normal else QFont.Weight.ExtraBold
        fmt.setFontWeight(new_weight)
        self.mergeCurrentCharFormat(fmt)

    def _toggle_italic(self):
        fmt = self.currentCharFormat()
        fmt.setFontItalic(not fmt.fontItalic())
        self.mergeCurrentCharFormat(fmt)

    def _toggle_underline(self):
        fmt = self.currentCharFormat()
        fmt.setFontUnderline(not fmt.fontUnderline())
        self.mergeCurrentCharFormat(fmt)

class HTMLDelegate(QStyledItemDelegate):
    @staticmethod
    def _is_checked(value):
        numeric = value.value if hasattr(value, 'value') else int(value)
        return numeric == Qt.CheckState.Checked.value

    @staticmethod
    def _check_rect(option):
        size = 14
        return QRect(
            option.rect.center().x() - size // 2,
            option.rect.center().y() - size // 2,
            size,
            size,
        )

    def eventFilter(self, editor, event):
        if isinstance(editor, RichTextEditor) and event.type() == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    # A tecla chega ao QTextEdit e vira uma quebra de linha.
                    return False
                self.commitData.emit(editor)
                self.closeEditor.emit(editor, QAbstractItemDelegate.EndEditHint.NoHint)
                return True
        return super().eventFilter(editor, event)

    def helpEvent(self, event, view, option, index):
        if index.data(Qt.ItemDataRole.CheckStateRole) is not None:
            tooltip = str(index.data(Qt.ItemDataRole.ToolTipRole) or '')
            if tooltip:
                QToolTip.showText(event.globalPos(), tooltip, view, option.rect)
                return True
            return False
        text = str(index.data(Qt.ItemDataRole.DisplayRole) or '')
        available = max(0, option.rect.width() - 20)
        clipped = '\n' in text or option.fontMetrics.horizontalAdvance(text) > available
        if clipped and text:
            QToolTip.showText(event.globalPos(), text, view, option.rect)
            return True
        QToolTip.hideText()
        return False

    def paint(self, painter, option, index):
        options = option
        self.initStyleOption(options, index)
        style = options.widget.style() if options.widget else QApplication.style()

        check_state = index.data(Qt.ItemDataRole.CheckStateRole)
        if check_state is not None:
            self._paint_centered_check(painter, options, index, check_state, style)
            return

        rich_text = index.data(Qt.ItemDataRole.UserRole)

        # No modo compacto cada célula continua em uma única linha, mas agora
        # preserva negrito, itálico e sublinhado do conteúdo rico.
        if not options.widget or not options.widget.wordWrap():
            if rich_text:
                self._paint_compact_rich_text(painter, options, index, rich_text, style)
                self._paint_current(painter, options, index)
                return
            text = str(index.data(Qt.ItemDataRole.DisplayRole) or '')
            options.text = re.sub(r'\s*[\r\n]+\s*', ' ', text)
            options.features &= ~QStyleOptionViewItem.ViewItemFeature.WrapText
            options.displayAlignment = (
                options.displayAlignment & Qt.AlignmentFlag.AlignHorizontal_Mask
            ) | Qt.AlignmentFlag.AlignVCenter
            style.drawControl(QStyle.ControlElement.CE_ItemViewItem, options, painter, options.widget)
            self._paint_current(painter, options, index)
            return
        
        if not rich_text:
            super().paint(painter, options, index)
            self._paint_current(painter, options, index)
            return

        painter.save()
        style.drawPrimitive(QStyle.PrimitiveElement.PE_PanelItemViewItem, options, painter, options.widget)

        selected = bool(options.state & QStyle.StateFlag.State_Selected)
        role = QPalette.ColorRole.HighlightedText if selected else QPalette.ColorRole.Text
        text_color = options.palette.color(QPalette.ColorGroup.Normal, role).name()
        doc = rich_text_document(rich_text, options.font, text_color)
        doc.setTextWidth(options.rect.width())

        content_height = doc.size().height()
        y_offset = max(0, (options.rect.height() - content_height) / 2)
        
        painter.translate(options.rect.left(), options.rect.top() + y_offset)
        painter.setClipRect(0, 0, options.rect.width(), options.rect.height())
        doc.drawContents(painter)
        painter.restore()
        self._paint_current(painter, options, index)

    def _paint_centered_check(self, painter, options, index, check_state, style):
        style.drawPrimitive(
            QStyle.PrimitiveElement.PE_PanelItemViewItem,
            options,
            painter,
            options.widget,
        )
        rect = self._check_rect(options)
        checked = self._is_checked(check_state)
        enabled = bool(index.flags() & Qt.ItemFlag.ItemIsEnabled)
        border = theme_color('accent') if checked else theme_color('border_strong')
        fill = theme_color('accent') if checked else theme_color('field')
        if not enabled:
            border = fill = theme_color('disabled')

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(QColor(border), 1))
        painter.setBrush(QColor(fill))
        painter.drawRoundedRect(QRectF(rect), 3, 3)
        if checked:
            painter.setPen(QPen(
                QColor(theme_color('on_accent')),
                2,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
                Qt.PenJoinStyle.RoundJoin,
            ))
            painter.drawPolyline([
                QPointF(rect.left() + 3, rect.top() + 7),
                QPointF(rect.left() + 6, rect.top() + 10),
                QPointF(rect.left() + 11, rect.top() + 4),
            ])
        painter.restore()
        self._paint_current(painter, options, index)

    def editorEvent(self, event, model, option, index):
        check_state = index.data(Qt.ItemDataRole.CheckStateRole)
        if check_state is None:
            return super().editorEvent(event, model, option, index)
        if not (index.flags() & Qt.ItemFlag.ItemIsEnabled
                and index.flags() & Qt.ItemFlag.ItemIsUserCheckable):
            return False

        activate = False
        if event.type() == QEvent.Type.MouseButtonRelease:
            activate = (
                event.button() == Qt.MouseButton.LeftButton
                and self._check_rect(option).adjusted(-4, -4, 4, 4).contains(
                    event.position().toPoint()
                )
            )
        elif event.type() == QEvent.Type.KeyPress:
            activate = event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Select)
        if not activate:
            return False

        state = (
            Qt.CheckState.Unchecked
            if self._is_checked(check_state)
            else Qt.CheckState.Checked
        )
        return model.setData(index, state, Qt.ItemDataRole.CheckStateRole)

    def _paint_compact_rich_text(self, painter, options, index, rich_text, style):
        style.drawPrimitive(
            QStyle.PrimitiveElement.PE_PanelItemViewItem,
            options,
            painter,
            options.widget,
        )
        selected = bool(options.state & QStyle.StateFlag.State_Selected)
        role = QPalette.ColorRole.HighlightedText if selected else QPalette.ColorRole.Text
        text_color = options.palette.color(QPalette.ColorGroup.Normal, role)
        doc = rich_text_document(rich_text, options.font, text_color.name(), no_wrap=True)

        content = options.rect.adjusted(8, 0, -8, 0)
        available = max(0, content.width())
        clipped = doc.idealWidth() > available
        ellipsis = '…'
        ellipsis_width = options.fontMetrics.horizontalAdvance(ellipsis) if clipped else 0
        draw_width = max(0, available - ellipsis_width)
        doc.setTextWidth(max(doc.idealWidth(), 1))
        content_height = doc.size().height()
        y_offset = max(0, (content.height() - content_height) / 2)

        painter.save()
        painter.translate(content.left(), content.top() + y_offset)
        painter.setClipRect(QRectF(0, 0, draw_width, content.height()))
        doc.drawContents(painter)
        painter.restore()

        if clipped:
            painter.save()
            painter.setPen(text_color)
            ellipsis_rect = QRectF(
                content.right() - ellipsis_width + 1,
                content.top(),
                ellipsis_width,
                content.height(),
            )
            painter.drawText(ellipsis_rect, Qt.AlignmentFlag.AlignVCenter, ellipsis)
            painter.restore()

    def _paint_current(self, painter, option, index):
        if option.widget and option.widget.currentIndex() == index:
            painter.save()
            painter.setPen(QPen(QColor(theme_color('accent')), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(option.rect.adjusted(1, 1, -1, -1))
            painter.restore()

    def createEditor(self, parent, option, index):
        if index.data(Qt.ItemDataRole.CheckStateRole) is not None:
            return None
        editor = RichTextEditor(parent)
        # Se for a coluna 0 (Cópias), força o alinhamento central no editor
        if index.column() == 0:
            editor.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return editor
    
    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(option.rect)

    def setEditorData(self, editor, index):
        html = index.data(Qt.ItemDataRole.UserRole)
        text = index.data(Qt.ItemDataRole.DisplayRole)
        if html:
            editor.setHtml(html)
        else:
            editor.setText(text)
        editor.moveCursor(QTextCursor.MoveOperation.End)

    def setModelData(self, editor, model, index):
        raw_html = editor.toHtml()
        html_content_only = re.sub(r'<(head|style|script)[^>]*>.*?</\1>', '', raw_html, flags=re.IGNORECASE | re.DOTALL)
        plain = editor.toPlainText()
        
        # Como o editor do Qt gera um HTML muito poluído internamente ao editar,
        # limpamos as tags estruturais pesadas e salvamos o fragmento direto
        clean_html = re.sub(r'</?(html|body|meta|p)[^>]*>', '', html_content_only, flags=re.IGNORECASE).strip()
        
        model.setData(index, clean_html, Qt.ItemDataRole.UserRole)
        model.setData(index, plain, Qt.ItemDataRole.DisplayRole)
