"""Texto tabulado e tabela HTML para colar a seleção em outras planilhas."""
import csv
from html import escape
from io import StringIO

from PySide6.QtCore import QMimeData
from PySide6.QtGui import QFont

from core.html_utils import TextOnlyDocument, sanitize_text_html


def cell_html(plain, rich=None):
    """Exporta somente o texto e as ênfases, sem recursos ou estilos da interface."""
    fallback = escape(plain, quote=False).replace('\n', '<br>')
    if not rich:
        return fallback
    document = TextOnlyDocument()
    document.setHtml(sanitize_text_html(rich))
    if document.toPlainText() != plain:
        return fallback  # Uma formatação antiga nunca substitui o valor da célula.
    blocks = []
    block = document.begin()
    while block.isValid():
        fragments = []
        iterator = block.begin()
        while not iterator.atEnd():
            fragment = iterator.fragment()
            if fragment.isValid():
                fmt = fragment.charFormat()
                tags = []
                if fmt.fontWeight() >= QFont.Weight.Bold:
                    tags.append('b')
                if fmt.fontItalic():
                    tags.append('i')
                if fmt.fontUnderline():
                    tags.append('u')
                fragments.append(''.join(f'<{tag}>' for tag in tags)
                                 + escape(fragment.text(), quote=False).replace('\u2028', '<br>')
                                 + ''.join(f'</{tag}>' for tag in reversed(tags)))
            iterator += 1
        blocks.append(''.join(fragments))
        block = block.next()
    return '<br>'.join(blocks)


def selection_mime_data(rows):
    """Cada célula é (texto, HTML opcional); aspas protegem tabs e quebras internas."""
    text = StringIO(newline='')
    writer = csv.writer(text, delimiter='\t', lineterminator='\n')
    html_rows = []
    for row in rows:
        writer.writerow([plain for plain, _rich in row])
        cells = ['<td style="white-space:pre-wrap">' + cell_html(plain, rich) + '</td>'
                 for plain, rich in row]
        html_rows.append('<tr>' + ''.join(cells) + '</tr>')
    mime = QMimeData()
    mime.setText(text.getvalue().removesuffix('\n'))
    mime.setHtml('<html><head><meta charset="utf-8"></head><body><table><tbody>'
                 + ''.join(html_rows) + '</tbody></table></body></html>')
    return mime
