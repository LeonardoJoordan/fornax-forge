"""Texto variável de células: ausência esvazia o campo, sem ocultar a grade."""
import re

from PySide6.QtGui import QTextCharFormat, QTextCursor

from core.text_layout import PLACEHOLDER_PATTERN, _html_plain_text, _insert_cell_html


def resolve_cell_document(document, values=None):
    """Resolve no documento temporário da célula, usando offsets UTF-16 do Qt.

    A ênfase da planilha soma-se à do placeholder; fonte/tamanho/cor padrão
    da planilha não substituem os do modelo. Nenhum documento é compartilhado.
    """
    plain = document.toPlainText()
    if values is None:
        values = {name: '{'+name+'}' for name in re.findall(PLACEHOLDER_PATTERN, plain)}
    cursor = QTextCursor(document)

    def select(text, start, end):
        cursor.setPosition(len(text[:start].encode('utf-16-le')) // 2)
        cursor.setPosition(len(text[:end].encode('utf-16-le')) // 2,
                           QTextCursor.MoveMode.KeepAnchor)

    def value(name):
        content = values.get(name)
        return '' if content is None else str(content)

    def empty(name):
        content = value(name)
        return not (_html_plain_text(content) if re.search(r'<[^>]+>', content) else content).strip()

    for match in reversed(list(re.finditer(r'\|([^|]*\{[\w]+\}[^|]*)\|', plain))):
        if any(empty(name) for name in re.findall(PLACEHOLDER_PATTERN, match[1])):
            select(plain, match.start(), match.end())
            cursor.removeSelectedText()
        else:
            select(plain, match.end()-1, match.end())
            cursor.removeSelectedText()
            select(plain, match.start(), match.start()+1)
            cursor.removeSelectedText()
    plain = document.toPlainText()
    for match in reversed(list(re.finditer(PLACEHOLDER_PATTERN, plain))):
        select(plain, match.start(), match.end())
        content = value(match[1])
        base = QTextCharFormat(cursor.charFormat())
        if re.search(r'<[^>]+>', content):
            _insert_cell_html(cursor, content, base)
        else:
            cursor.insertText(content, base)
    return document
