"""Layout de texto compartilhado pelo renderer e pela edição no canvas."""
import re
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontMetrics, QTextCursor, QTextCharFormat, QTextBlockFormat, QColor, QBrush
from core.html_utils import TextOnlyDocument, normalize_text_decoration, sanitize_text_html
from core.object_style import outline_pen

ALIGNMENTS = {"left": Qt.AlignLeft, "center": Qt.AlignHCenter, "right": Qt.AlignRight, "justify": Qt.AlignJustify}
REFERENCE_GLYPHS = "AÇgjpqy|{}"
PLACEHOLDER_PATTERN = r"\{([\w]+)\}"


def line_reference_ink_bounds(doc, block, line):
    """Retorna topo/base estáveis usando as fontes realmente presentes na linha."""
    fonts = {}
    line_start = line.textStart()
    line_end = line_start + line.textLength()
    cursor = QTextCursor(doc)
    for offset in range(line_start, line_end):
        cursor.setPosition(block.position() + offset)
        font = cursor.charFormat().font().resolve(doc.defaultFont())
        fonts[font.toString()] = font

    if not fonts:
        default = doc.defaultFont()
        fonts[default.toString()] = default

    bounds = [QFontMetrics(font).tightBoundingRect(REFERENCE_GLYPHS) for font in fonts.values()]
    return min(rect.top() for rect in bounds), max(rect.bottom() for rect in bounds)


def variables_in_html(content):
    doc = TextOnlyDocument()
    doc.setHtml(sanitize_text_html(content))
    return re.findall(PLACEHOLDER_PATTERN, doc.toPlainText())


def _html_plain_text(content):
    """Extrai texto real de um fragmento HTML, incluindo entidades do Qt."""
    doc = TextOnlyDocument()
    doc.setHtml(sanitize_text_html(content))
    return doc.toPlainText()


def _insert_cell_html(cursor, html, base_format):
    """Insere uma célula preservando a tipografia definida no modelo.

    O QTextEdit da planilha inclui fonte, tamanho e cor padrão em seu HTML. Esses
    atributos pertencem à interface da planilha, não ao conteúdo do modelo. Da
    célula importamos somente as ênfases que o usuário pode editar na tabela.
    """
    source = TextOnlyDocument()
    source.setHtml(sanitize_text_html(html))

    block = source.begin()
    first_block = True
    while block.isValid():
        if not first_block:
            cursor.insertText("\n", base_format)
        first_block = False

        iterator = block.begin()
        while not iterator.atEnd():
            fragment = iterator.fragment()
            if fragment.isValid():
                source_format = fragment.charFormat()
                output_format = QTextCharFormat(base_format)
                output_format.setFontWeight(source_format.fontWeight())
                output_format.setFontItalic(source_format.fontItalic())
                output_format.setFontUnderline(source_format.fontUnderline())
                cursor.insertText(fragment.text(), output_format)
            iterator += 1
        block = block.next()


def resolve_rich_text(box, values):
    """Substitui marcações por posições no documento, mesmo entre spans de estilo."""
    doc = build_document(box, box.get("html", ""))
    cursor = QTextCursor(doc)

    def select(text, start, end):
        # QTextCursor usa offsets UTF-16; índices Python contam code points.
        cursor.setPosition(len(text[:start].encode("utf-16-le")) // 2)
        cursor.setPosition(len(text[:end].encode("utf-16-le")) // 2, QTextCursor.KeepAnchor)

    def empty(name):
        value = str(values.get(name, ""))
        plain_value = _html_plain_text(value) if re.search(r"<[^>]+>", value) else value
        return not plain_value.strip()

    plain = doc.toPlainText()
    for match in reversed(list(re.finditer(r"\|([^|]*\{[\w]+\}[^|]*)\|", plain))):
        if any(empty(name) for name in re.findall(PLACEHOLDER_PATTERN, match[1])):
            select(plain, match.start(), match.end())
            cursor.removeSelectedText()
        else:
            select(plain, match.end()-1, match.end())
            cursor.removeSelectedText()
            select(plain, match.start(), match.start()+1)
            cursor.removeSelectedText()
    plain = doc.toPlainText()
    matches = list(re.finditer(PLACEHOLDER_PATTERN, plain))
    if any(empty(match[1]) for match in matches):
        return None
    for match in reversed(matches):
        select(plain, match.start(), match.end())
        value = str(values[match[1]])
        placeholder_format = QTextCharFormat(cursor.charFormat())
        if re.search(r"<[^>]+>", value):
            _insert_cell_html(cursor, value, placeholder_format)
        else:
            cursor.insertText(value, placeholder_format)
    return doc.toHtml()

def build_document(box, content):
    doc = TextOnlyDocument()
    doc.setDocumentMargin(0)
    rich = box.get("rich_text_version") == 1
    cleaned = sanitize_text_html(content)
    if not rich:
        for name in ("color", "background-color", "font-size", "font-family"):
            cleaned = re.sub(name + r'\s*:[^;"]+;?', "", cleaned)
    cleaned = normalize_text_decoration(cleaned)
    cleaned = re.sub(r"(?i)</?a\b[^>]*>", "", cleaned)
    from core.ui_font import DOCUMENT_FONT_FAMILY
    font = QFont(box.get("font_family", DOCUMENT_FONT_FAMILY), int(box.get("font_size", 16)))
    doc.setDefaultFont(font)
    if rich:
        doc.setDefaultStyleSheet("body { color: " + box.get("font_color", "#000000") + "; }")
    doc.setHtml(cleaned)
    options = doc.defaultTextOption()
    options.setAlignment(ALIGNMENTS.get(box.get("align", "left"), Qt.AlignLeft))
    doc.setDefaultTextOption(options)
    cursor = QTextCursor(doc)
    cursor.select(QTextCursor.Document)
    if not rich:
        color = QTextCharFormat()
        color.setForeground(QBrush(QColor(box.get("font_color", "#000000"))))
        cursor.mergeCharFormat(color)
        block = QTextBlockFormat()
        block.setTextIndent(box.get("indent_px", 0.0))
        block.setLineHeight(box.get("line_height", 1.15) * 100, 1)
        cursor.mergeBlockFormat(block)
    outline = QTextCharFormat()
    outline.setTextOutline(outline_pen(box))
    cursor.mergeCharFormat(outline)
    frame = doc.rootFrame()
    fmt = frame.frameFormat()
    fmt.setMargin(0)
    frame.setFrameFormat(fmt)
    doc.setTextWidth(box.get("w", 300))
    return doc

def text_geometry(doc, box_data):
    h = box_data.get("h", 100)
    layout = doc.documentLayout()
    logical_h = layout.documentSize().height()
    
    real_top = 0
    real_bottom = logical_h
    
    first_block = doc.begin()
    if first_block.isValid():
        text_layout = first_block.layout()
        if text_layout.lineCount() > 0:
            first_line = text_layout.lineAt(0)
            text_str = first_block.text()[first_line.textStart() : first_line.textStart() + first_line.textLength()]
            if text_str.strip():
                ink_top, _ = line_reference_ink_bounds(doc, first_block, first_line)
                real_top = first_line.y() + first_line.ascent() + ink_top

    last_block = doc.begin()
    last_valid_block = last_block
    while last_block.isValid():
        if last_block.text().strip(): last_valid_block = last_block
        last_block = last_block.next()
        
    if last_valid_block.isValid():
        text_layout = last_valid_block.layout()
        if text_layout.lineCount() > 0:
            last_line = text_layout.lineAt(text_layout.lineCount() - 1)
            text_str = last_valid_block.text()[last_line.textStart() : last_line.textStart() + last_line.textLength()]
            if text_str.strip():
                _, ink_bottom = line_reference_ink_bounds(doc, last_valid_block, last_line)
                block_y = layout.blockBoundingRect(last_valid_block).y()
                real_bottom = block_y + last_line.y() + last_line.ascent() + ink_bottom
                
    content_h = real_bottom - real_top
    
    y_offset = 0
    if box_data.get("vertical_align") == "center":
        y_offset = (h - content_h) / 2 - real_top
    elif box_data.get("vertical_align") == "bottom":
        y_offset = h - content_h - real_top
    else: 
        y_offset = -real_top


    return y_offset, real_top, content_h
