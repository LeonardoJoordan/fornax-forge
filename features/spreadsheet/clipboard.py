import re
import csv
import html as _html_mod
from io import StringIO
from html.parser import HTMLParser
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class CellValue:
    plain: str
    rich_html: str

    def html_for_document(self) -> str:
        # The model distinguishes text from HTML by actual tags. Entity-only
        # fragments also need decoding, without interpreting literal user tags.
        if '&' in self.rich_html and '<' not in self.rich_html:
            return '<span>' + self.rich_html + '</span>'
        return self.rich_html

# ---------------------------------------------------------------------------
# Helpers Gerais de CSS e Limpeza de Texto
# ---------------------------------------------------------------------------
def _parse_style(style_str: str) -> dict:
    """Transforma uma string de CSS inline em um dicionário de propriedades."""
    result = {}
    if not style_str:
        return result
    for part in style_str.split(";"):
        if ":" not in part:
            continue
        prop, _, val = part.partition(":")
        result[prop.strip().lower()] = val.strip().lower()
    return result

def _clean_spaces(s: str) -> str:
    s = s.replace("\xa0", " ")
    s = re.sub(r"[ \t]+", " ", s)
    return s.strip()

def _clean_spaces_keep_edges(s: str) -> str:
    s = s.replace("\xa0", " ")
    s = re.sub(r"[ \t]+", " ", s)
    return s

_STYLE_TAGS = ("b", "i", "u")

def _empty_style_state(value: Optional[bool] = None) -> dict:
    return {tag: value for tag in _STYLE_TAGS}

def _style_state_has_values(state: dict) -> bool:
    return any(value is not None for value in state.values())

def _merge_style_states(*states: dict) -> dict:
    merged = _empty_style_state()
    for state in states:
        for tag in _STYLE_TAGS:
            value = state.get(tag)
            if value is not None:
                merged[tag] = value
    return merged

def _style_state_to_tags(state: dict) -> List[str]:
    return [tag for tag in _STYLE_TAGS if state.get(tag) is True]

def _style_state_from_style(style_str: str) -> dict:
    style = _parse_style(style_str)
    state = _empty_style_state()

    if "font-weight" in style:
        fw = style.get("font-weight", "")
        if fw in ("bold", "bolder"):
            state["b"] = True
        elif fw in ("normal", "lighter"):
            state["b"] = False
        else:
            match = re.search(r"\d+", fw)
            if match:
                state["b"] = int(match.group(0)) >= 600

    if "font-style" in style:
        fs = style.get("font-style", "")
        if fs in ("italic", "oblique"):
            state["i"] = True
        elif fs == "normal":
            state["i"] = False

    decoration = " ".join([
        style.get("text-decoration", ""),
        style.get("text-decoration-line", ""),
    ]).strip()
    underline_style = style.get("text-underline-style", "")
    if decoration or underline_style:
        if "underline" in decoration or (underline_style and underline_style != "none"):
            state["u"] = True
        elif "none" in decoration or underline_style == "none" or decoration:
            state["u"] = False

    return state

def _remove_empty_style_tags(rich: str) -> str:
    previous = None
    while previous != rich:
        previous = rich
        rich = re.sub(r"<([biu])></\1>", "", rich)
    return rich


def _plain_from_rich(rich: str) -> str:
    # Remove markup before decoding entities: literal "<b>" is cell content.
    text = re.sub(r"<br\s*/?>", "\n", rich, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return _clean_spaces(_html_mod.unescape(text))


class _UnsupportedHTMLTable(ValueError):
    """Use the text representation when HTML geometry cannot be read safely."""


class _TableHTMLParser(HTMLParser):
    """Shared grid geometry for the existing HTML formatting readers."""
    MAX_EXPANDED_CELLS = 100_000

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._spans = []
        self._row_spans = []
        self._cell_span = (1, 1)
        self._row_open = False

    def close(self):
        super().close()
        if self.in_td or self._row_open or self.current_row:
            raise _UnsupportedHTMLTable('Tabela HTML incompleta')

    def _begin_row(self):
        if self.in_td or self._row_open:
            raise _UnsupportedHTMLTable('Tabela HTML aninhada ou incompleta')
        self.current_row = []
        self._row_spans = []
        self._row_open = True

    def _begin_cell(self, attrs):
        if self.in_td:
            raise _UnsupportedHTMLTable('Célula HTML incompleta')
        attrs = dict(attrs)
        spans = []
        for name in ('colspan', 'rowspan'):
            value = (attrs.get(name) or '1').strip()
            if value.isascii() and value.isdigit():
                if len(value) > 6 or int(value) > self.MAX_EXPANDED_CELLS:
                    raise _UnsupportedHTMLTable('Mesclagem HTML excessiva')
                spans.append(max(1, int(value)))
            else:
                spans.append(1)
        self._cell_span = tuple(spans)

    def _append_cell(self, cell):
        self.current_row.append(cell)
        self._row_spans.append(self._cell_span)

    def _append_row(self):
        if self.in_td:
            raise _UnsupportedHTMLTable('Célula HTML incompleta')
        if self._row_open:
            self.grid.append(self.current_row)
            self._spans.append(self._row_spans)
        self.current_row = []
        self._row_spans = []
        self._row_open = False

    def expanded_grid(self):
        if all(span == (1, 1) for row in self._spans for span in row):
            width = max((len(row) for row in self.grid), default=1)
            if width * len(self.grid) > self.MAX_EXPANDED_CELLS:
                width = 1  # the destination fills gaps only up to its visible columns
            return [row if row else [CellValue('', '') for _ in range(max(1, width))] for row in self.grid]
        # A merged cell's text belongs only to its upper-left position. Reserve
        # the covered positions so subsequent values stay in their columns.
        rows = [{} for _ in self.grid]
        width = 0
        blank = CellValue('', '')
        for r, values in enumerate(self.grid):
            column = 0
            for cell, (colspan, rowspan) in zip(values, self._spans[r]):
                while column in rows[r]:
                    column += 1
                end = column + colspan
                width = max(width, end)
                if width * len(rows) > self.MAX_EXPANDED_CELLS:
                    raise _UnsupportedHTMLTable('Mesclagem HTML excessiva')
                for rr in range(r, min(r + rowspan, len(rows))):
                    for cc in range(column, end):
                        if cc in rows[rr]:
                            raise _UnsupportedHTMLTable('Mesclagens HTML sobrepostas')
                        rows[rr][cc] = blank
                rows[r][column] = cell
                column = end
        return [[row.get(c, blank) for c in range(width)] for row in rows]

# ---------------------------------------------------------------------------
# Trabalhadores Especializados
# ---------------------------------------------------------------------------

class GoogleSheets:
    @staticmethod
    def processar(html: str) -> List[List[CellValue]]:
        def attrs_to_dict(attrs) -> dict:
            attrs_dict = {}
            style_fragments = []

            for key, value in attrs:
                if not key:
                    continue

                key_l = key.lower()
                if key_l == "style":
                    style_fragments.append(value or "")
                    continue

                if value is None and style_fragments:
                    # Alguns HTMLs de clipboard chegam com aspas internas em style
                    # e o HTMLParser quebra o CSS em "atributos" soltos.
                    style_fragments.append(key)
                    continue

                attrs_dict[key_l] = value or ""

            if style_fragments:
                attrs_dict["style"] = " ".join(style_fragments)

            return attrs_dict

        def tags_from_style(style_str: str) -> List[str]:
            style = _parse_style(style_str)
            tags = []

            fw = style.get("font-weight", "")
            if fw in ("bold", "bolder"):
                tags.append("b")
            else:
                match = re.search(r"\d+", fw)
                if match and int(match.group(0)) >= 600:
                    tags.append("b")

            if style.get("font-style", "") in ("italic", "oblique"):
                tags.append("i")

            decoration = " ".join([
                style.get("text-decoration", ""),
                style.get("text-decoration-line", ""),
            ])
            if "underline" in decoration:
                tags.append("u")

            return tags

        def unique_ordered_tags(tags: List[str]) -> List[str]:
            ordered = []
            for tag in ("b", "i", "u"):
                if tag in tags:
                    ordered.append(tag)
            return ordered

        def plain_from_rich(rich: str) -> str:
            return _plain_from_rich(rich)

        class SheetsParser(_TableHTMLParser):
            def __init__(self):
                super().__init__()
                self.grid: List[List[CellValue]] = []
                self.current_row: List[CellValue] = []
                self.in_td = False
                self.in_style = False
                self.seen_table_cell = False
                self.cell_chunks: List[str] = []
                self.base_tags: List[str] = []
                self.frames: List[tuple[str, List[str]]] = []
                self.fragment_chunks: List[str] = []
                self.fragment_frames: List[tuple[str, List[str]]] = []

            def _open_tags(self, tags: List[str], target: List[str]):
                for tag in tags:
                    target.append(f"<{tag}>")

            def _close_tags(self, tags: List[str], target: List[str]):
                for tag in reversed(tags):
                    target.append(f"</{tag}>")

            def _push_frame(self, tag: str, tags: List[str]):
                self._open_tags(tags, self.cell_chunks)
                self.frames.append((tag, tags))

            def _pop_frame(self, tag: str):
                if not self.frames:
                    return

                idx = len(self.frames) - 1
                while idx >= 0 and self.frames[idx][0] != tag:
                    idx -= 1

                if idx < 0:
                    idx = len(self.frames) - 1

                closing = self.frames[idx:]
                del self.frames[idx:]
                for _, tags in reversed(closing):
                    self._close_tags(tags, self.cell_chunks)

            def _push_fragment_frame(self, tag: str, tags: List[str]):
                self._open_tags(tags, self.fragment_chunks)
                self.fragment_frames.append((tag, tags))

            def _pop_fragment_frame(self, tag: str):
                if not self.fragment_frames:
                    return

                idx = len(self.fragment_frames) - 1
                while idx >= 0 and self.fragment_frames[idx][0] != tag:
                    idx -= 1

                if idx < 0:
                    idx = len(self.fragment_frames) - 1

                closing = self.fragment_frames[idx:]
                del self.fragment_frames[idx:]
                for _, tags in reversed(closing):
                    self._close_tags(tags, self.fragment_chunks)

            def _tags_for_tag(self, tag: str, attrs) -> List[str]:
                semantic = []
                if tag in ("b", "strong"):
                    semantic.append("b")
                elif tag in ("i", "em"):
                    semantic.append("i")
                elif tag == "u":
                    semantic.append("u")

                attrs_dict = attrs_to_dict(attrs)
                return unique_ordered_tags(semantic + tags_from_style(attrs_dict.get("style", "")))

            def _finalize_cell(self):
                while self.frames:
                    _, tags = self.frames.pop()
                    self._close_tags(tags, self.cell_chunks)

                self._close_tags(self.base_tags, self.cell_chunks)

                rich = "".join(self.cell_chunks)
                rich = _remove_empty_style_tags(re.sub(r"\s*<br>\s*", "<br>", rich)).strip()
                plain = plain_from_rich(rich)
                self._append_cell(CellValue(plain=plain, rich_html=rich))

                self.in_td = False
                self.cell_chunks = []
                self.base_tags = []
                self.frames = []

            def handle_starttag(self, tag, attrs):
                tag = tag.lower()

                if tag == "style":
                    self.in_style = True
                    return

                if tag == "tr":
                    self._begin_row()
                    return

                if tag in ("td", "th"):
                    self._begin_cell(attrs)
                    self.in_td = True
                    self.seen_table_cell = True
                    self.cell_chunks = []
                    self.frames = []
                    self.base_tags = tags_from_style(attrs_to_dict(attrs).get("style", ""))
                    self._open_tags(self.base_tags, self.cell_chunks)
                    return

                if self.in_td:
                    if tag == "br":
                        self.cell_chunks.append("<br>")
                        return

                    self._push_frame(tag, self._tags_for_tag(tag, attrs))
                    return

                if not self.seen_table_cell:
                    if tag == "br":
                        self.fragment_chunks.append("<br>")
                        return
                    self._push_fragment_frame(tag, self._tags_for_tag(tag, attrs))

            def handle_endtag(self, tag):
                tag = tag.lower()

                if tag == "style":
                    self.in_style = False
                    return

                if tag == "tr":
                    self._append_row()
                    return

                if tag in ("td", "th") and self.in_td:
                    self._finalize_cell()
                    return

                if self.in_td:
                    self._pop_frame(tag)
                    return

                if not self.seen_table_cell:
                    self._pop_fragment_frame(tag)

            def handle_data(self, data):
                if self.in_style or not data:
                    return

                if self.in_td:
                    self.cell_chunks.append(_html_mod.escape(_clean_spaces_keep_edges(data), quote=False))
                elif not self.seen_table_cell:
                    self.fragment_chunks.append(_html_mod.escape(_clean_spaces_keep_edges(data), quote=False))

        parser = SheetsParser()
        parser.feed(html or "")
        parser.close()
        
        if not parser.grid and parser.fragment_chunks:
            while parser.fragment_frames:
                _, tags = parser.fragment_frames.pop()
                parser._close_tags(tags, parser.fragment_chunks)

            rich = "".join(parser.fragment_chunks)
            rich = _remove_empty_style_tags(re.sub(r"\s*<br>\s*", "<br>", rich)).strip()
            plain = plain_from_rich(rich)
            if plain:
                return [[CellValue(plain=plain, rich_html=rich)]]
                
        return parser.expanded_grid()


class Excel:
    @staticmethod
    def processar(html: str) -> List[List[CellValue]]:
        def attrs_to_dict(attrs) -> dict:
            attrs_dict = {}
            style_fragments = []

            for key, value in attrs:
                if not key:
                    continue

                key_l = key.lower()
                if key_l == "style":
                    style_fragments.append(value or "")
                    continue

                if value is None and style_fragments:
                    style_fragments.append(key)
                    continue

                attrs_dict[key_l] = value or ""

            if style_fragments:
                attrs_dict["style"] = " ".join(style_fragments)

            return attrs_dict

        def plain_from_rich(rich: str) -> str:
            return _plain_from_rich(rich)

        class ExcelParser(_TableHTMLParser):
            def __init__(self):
                super().__init__()
                self.grid: List[List[CellValue]] = []
                self.current_row: List[CellValue] = []
                self.in_td = False
                self.in_style = False
                self.seen_table_cell = False
                self.cell_chunks: List[str] = []
                self.style_text = []
                self.classes_map: dict[str, dict] = {}
                self.current_state = _empty_style_state(False)
                self.frames: List[tuple[str, dict]] = []
                self.fragment_chunks: List[str] = []
                self.fragment_state = _empty_style_state(False)
                self.fragment_frames: List[tuple[str, dict]] = []

            def _merge_class_state(self, class_name: str, state: dict):
                if not _style_state_has_values(state):
                    return

                current = self.classes_map.get(class_name, _empty_style_state())
                self.classes_map[class_name] = _merge_style_states(current, state)

            def _parse_css_block(self, css_text: str):
                css_text = re.sub(r"/\*.*?\*/", "", css_text, flags=re.DOTALL)
                for m in re.finditer(r"([^{}]+)\{([^}]*)\}", css_text):
                    selectors = m.group(1)
                    state = _style_state_from_style(m.group(2))
                    if not _style_state_has_values(state):
                        continue

                    for selector in selectors.split(","):
                        for cls in re.findall(r"\.([\w-]+)", selector):
                            self._merge_class_state(cls, state)

            def _open_tags(self, tags: List[str], target: List[str]):
                for tag in tags:
                    target.append(f"<{tag}>")

            def _close_tags(self, tags: List[str], target: List[str]):
                for tag in reversed(tags):
                    target.append(f"</{tag}>")

            def _transition_state(self, current_state: dict, new_state: dict, target: List[str]) -> dict:
                old_tags = _style_state_to_tags(current_state)
                new_tags = _style_state_to_tags(new_state)

                common_len = 0
                for old_tag, new_tag in zip(old_tags, new_tags):
                    if old_tag != new_tag:
                        break
                    common_len += 1

                self._close_tags(old_tags[common_len:], target)
                self._open_tags(new_tags[common_len:], target)
                return new_state.copy()

            def _class_state(self, class_attr: str) -> dict:
                state = _empty_style_state()
                for cls in (class_attr or "").split():
                    state = _merge_style_states(state, self.classes_map.get(cls, _empty_style_state()))
                return state

            def _state_for_tag(self, tag: str, attrs) -> dict:
                semantic = _empty_style_state()
                if tag in ("b", "strong"):
                    semantic["b"] = True
                elif tag in ("i", "em"):
                    semantic["i"] = True
                elif tag == "u":
                    semantic["u"] = True

                attrs_dict = attrs_to_dict(attrs)
                class_state = self._class_state(attrs_dict.get("class", ""))
                style_state = _style_state_from_style(attrs_dict.get("style", ""))
                return _merge_style_states(semantic, class_state, style_state)

            def _push_frame(self, tag: str, state: dict):
                previous_state = self.current_state.copy()
                next_state = _merge_style_states(previous_state, state)
                self.current_state = self._transition_state(
                    self.current_state,
                    next_state,
                    self.cell_chunks
                )
                self.frames.append((tag, previous_state))

            def _pop_frame(self, tag: str):
                if not self.frames:
                    return

                idx = len(self.frames) - 1
                while idx >= 0 and self.frames[idx][0] != tag:
                    idx -= 1

                if idx < 0:
                    idx = len(self.frames) - 1

                previous_state = self.frames[idx][1]
                del self.frames[idx:]
                self.current_state = self._transition_state(
                    self.current_state,
                    previous_state,
                    self.cell_chunks
                )

            def _push_fragment_frame(self, tag: str, state: dict):
                previous_state = self.fragment_state.copy()
                next_state = _merge_style_states(previous_state, state)
                self.fragment_state = self._transition_state(
                    self.fragment_state,
                    next_state,
                    self.fragment_chunks
                )
                self.fragment_frames.append((tag, previous_state))

            def _pop_fragment_frame(self, tag: str):
                if not self.fragment_frames:
                    return

                idx = len(self.fragment_frames) - 1
                while idx >= 0 and self.fragment_frames[idx][0] != tag:
                    idx -= 1

                if idx < 0:
                    idx = len(self.fragment_frames) - 1

                previous_state = self.fragment_frames[idx][1]
                del self.fragment_frames[idx:]
                self.fragment_state = self._transition_state(
                    self.fragment_state,
                    previous_state,
                    self.fragment_chunks
                )

            def _finalize_cell(self):
                self.current_state = self._transition_state(
                    self.current_state,
                    _empty_style_state(False),
                    self.cell_chunks
                )

                rich = "".join(self.cell_chunks)
                rich = _remove_empty_style_tags(re.sub(r"\s*<br>\s*", "<br>", rich)).strip()
                plain = plain_from_rich(rich)
                self._append_cell(CellValue(plain=plain, rich_html=rich))

                self.in_td = False
                self.cell_chunks = []
                self.frames = []
                self.current_state = _empty_style_state(False)

            def handle_starttag(self, tag, attrs):
                tag = tag.lower()

                if tag == "style":
                    self.in_style = True
                    self.style_text = []
                    return

                if tag == "tr":
                    self._begin_row()
                    return

                if tag in ("td", "th"):
                    self._begin_cell(attrs)
                    self.in_td = True
                    self.seen_table_cell = True
                    self.cell_chunks = []
                    self.frames = []
                    self.current_state = _empty_style_state(False)
                    base_state = _merge_style_states(
                        self.current_state,
                        self._state_for_tag(tag, attrs)
                    )
                    self.current_state = self._transition_state(
                        self.current_state,
                        base_state,
                        self.cell_chunks
                    )
                    return

                if self.in_td:
                    if tag == "br":
                        self.cell_chunks.append("<br>")
                        return

                    self._push_frame(tag, self._state_for_tag(tag, attrs))
                    return

                if not self.seen_table_cell:
                    if tag == "br":
                        self.fragment_chunks.append("<br>")
                        return
                    self._push_fragment_frame(tag, self._state_for_tag(tag, attrs))

            def handle_endtag(self, tag):
                tag = tag.lower()

                if tag == "style":
                    self.in_style = False
                    self._parse_css_block("".join(self.style_text))
                    return

                if tag == "tr":
                    self._append_row()
                    return

                if tag in ("td", "th") and self.in_td:
                    self._finalize_cell()
                    return

                if self.in_td:
                    self._pop_frame(tag)
                    return

                if not self.seen_table_cell:
                    self._pop_fragment_frame(tag)

            def handle_data(self, data):
                if self.in_style:
                    self.style_text.append(data)
                elif self.in_td and data:
                    self.cell_chunks.append(_html_mod.escape(_clean_spaces_keep_edges(data), quote=False))
                elif not self.seen_table_cell and data:
                    self.fragment_chunks.append(_html_mod.escape(_clean_spaces_keep_edges(data), quote=False))

        parser = ExcelParser()
        parser.feed(html or "")
        parser.close()

        if not parser.grid and parser.fragment_chunks:
            parser.fragment_state = parser._transition_state(
                parser.fragment_state,
                _empty_style_state(False),
                parser.fragment_chunks
            )
            parser.fragment_frames = []

            rich = "".join(parser.fragment_chunks)
            rich = _remove_empty_style_tags(re.sub(r"\s*<br>\s*", "<br>", rich)).strip()
            plain = plain_from_rich(rich)
            if plain:
                return [[CellValue(plain=plain, rich_html=rich)]]

        return parser.expanded_grid()


class LibreOffice:
    @staticmethod
    def processar(html: str) -> List[List[CellValue]]:
        def attrs_to_dict(attrs) -> dict:
            attrs_dict = {}
            style_fragments = []

            for key, value in attrs:
                if not key:
                    continue

                key_l = key.lower()
                if key_l == "style":
                    style_fragments.append(value or "")
                    continue

                if value is None and style_fragments:
                    style_fragments.append(key)
                    continue

                attrs_dict[key_l] = value or ""

            if style_fragments:
                attrs_dict["style"] = " ".join(style_fragments)

            return attrs_dict

        def plain_from_rich(rich: str) -> str:
            return _plain_from_rich(rich)

        class LibreParser(_TableHTMLParser):
            def __init__(self):
                super().__init__()
                self.grid: List[List[CellValue]] = []
                self.current_row: List[CellValue] = []
                self.in_td = False
                self.in_style = False
                self.seen_table_cell = False
                self.cell_chunks: List[str] = []
                self.style_text = []
                self.classes_map: dict[str, dict] = {}
                self.current_state = _empty_style_state(False)
                self.frames: List[tuple[str, dict]] = []
                self.fragment_chunks: List[str] = []
                self.fragment_state = _empty_style_state(False)
                self.fragment_frames: List[tuple[str, dict]] = []

            def _merge_class_state(self, class_name: str, state: dict):
                if not _style_state_has_values(state):
                    return

                current = self.classes_map.get(class_name, _empty_style_state())
                self.classes_map[class_name] = _merge_style_states(current, state)

            def _parse_css_block(self, css_text: str):
                css_text = re.sub(r"/\*.*?\*/", "", css_text, flags=re.DOTALL)
                for m in re.finditer(r"([^{}@]+)\{([^}]*)\}", css_text):
                    selectors = m.group(1)
                    state = _style_state_from_style(m.group(2))
                    if not _style_state_has_values(state):
                        continue

                    for selector in selectors.split(","):
                        for cls in re.findall(r"\.([\w-]+)", selector):
                            self._merge_class_state(cls, state)

            def _open_tags(self, tags: List[str], target: List[str]):
                for tag in tags:
                    target.append(f"<{tag}>")

            def _close_tags(self, tags: List[str], target: List[str]):
                for tag in reversed(tags):
                    target.append(f"</{tag}>")

            def _transition_state(self, current_state: dict, new_state: dict, target: List[str]) -> dict:
                old_tags = _style_state_to_tags(current_state)
                new_tags = _style_state_to_tags(new_state)

                common_len = 0
                for old_tag, new_tag in zip(old_tags, new_tags):
                    if old_tag != new_tag:
                        break
                    common_len += 1

                self._close_tags(old_tags[common_len:], target)
                self._open_tags(new_tags[common_len:], target)
                return new_state.copy()

            def _class_state(self, class_attr: str) -> dict:
                state = _empty_style_state()
                for cls in (class_attr or "").split():
                    state = _merge_style_states(state, self.classes_map.get(cls, _empty_style_state()))
                return state

            def _state_for_tag(self, tag: str, attrs) -> dict:
                semantic = _empty_style_state()
                if tag in ("b", "strong"):
                    semantic["b"] = True
                elif tag in ("i", "em"):
                    semantic["i"] = True
                elif tag == "u":
                    semantic["u"] = True

                attrs_dict = attrs_to_dict(attrs)
                class_state = self._class_state(attrs_dict.get("class", ""))
                style_state = _style_state_from_style(attrs_dict.get("style", ""))
                return _merge_style_states(semantic, class_state, style_state)

            def _push_frame(self, tag: str, state: dict):
                previous_state = self.current_state.copy()
                next_state = _merge_style_states(previous_state, state)
                self.current_state = self._transition_state(
                    self.current_state,
                    next_state,
                    self.cell_chunks
                )
                self.frames.append((tag, previous_state))

            def _pop_frame(self, tag: str):
                if not self.frames:
                    return

                idx = len(self.frames) - 1
                while idx >= 0 and self.frames[idx][0] != tag:
                    idx -= 1

                if idx < 0:
                    idx = len(self.frames) - 1

                previous_state = self.frames[idx][1]
                del self.frames[idx:]
                self.current_state = self._transition_state(
                    self.current_state,
                    previous_state,
                    self.cell_chunks
                )

            def _push_fragment_frame(self, tag: str, state: dict):
                previous_state = self.fragment_state.copy()
                next_state = _merge_style_states(previous_state, state)
                self.fragment_state = self._transition_state(
                    self.fragment_state,
                    next_state,
                    self.fragment_chunks
                )
                self.fragment_frames.append((tag, previous_state))

            def _pop_fragment_frame(self, tag: str):
                if not self.fragment_frames:
                    return

                idx = len(self.fragment_frames) - 1
                while idx >= 0 and self.fragment_frames[idx][0] != tag:
                    idx -= 1

                if idx < 0:
                    idx = len(self.fragment_frames) - 1

                previous_state = self.fragment_frames[idx][1]
                del self.fragment_frames[idx:]
                self.fragment_state = self._transition_state(
                    self.fragment_state,
                    previous_state,
                    self.fragment_chunks
                )

            def _finalize_cell(self):
                self.current_state = self._transition_state(
                    self.current_state,
                    _empty_style_state(False),
                    self.cell_chunks
                )

                rich = "".join(self.cell_chunks)
                rich = _remove_empty_style_tags(re.sub(r"\s*<br>\s*", "<br>", rich)).strip()
                plain = plain_from_rich(rich)
                self._append_cell(CellValue(plain=plain, rich_html=rich))

                self.in_td = False
                self.cell_chunks = []
                self.frames = []
                self.current_state = _empty_style_state(False)

            def handle_starttag(self, tag, attrs):
                tag = tag.lower()

                if tag == "style":
                    self.in_style = True
                    self.style_text = []
                    return

                if tag == "tr":
                    self._begin_row()
                    return

                if tag in ("td", "th"):
                    self._begin_cell(attrs)
                    self.in_td = True
                    self.seen_table_cell = True
                    self.cell_chunks = []
                    self.frames = []
                    self.current_state = _empty_style_state(False)
                    base_state = _merge_style_states(
                        self.current_state,
                        self._state_for_tag(tag, attrs)
                    )
                    self.current_state = self._transition_state(
                        self.current_state,
                        base_state,
                        self.cell_chunks
                    )
                    return

                if self.in_td:
                    if tag == "br":
                        self.cell_chunks.append("<br>")
                        return

                    self._push_frame(tag, self._state_for_tag(tag, attrs))
                    return

                if not self.seen_table_cell:
                    if tag == "br":
                        self.fragment_chunks.append("<br>")
                        return

                    self._push_fragment_frame(tag, self._state_for_tag(tag, attrs))

            def handle_endtag(self, tag):
                tag = tag.lower()

                if tag == "style":
                    self.in_style = False
                    self._parse_css_block("".join(self.style_text))
                    return

                if tag == "tr":
                    self._append_row()
                    return

                if tag in ("td", "th") and self.in_td:
                    self._finalize_cell()
                    return

                if self.in_td:
                    self._pop_frame(tag)
                    return

                if not self.seen_table_cell:
                    self._pop_fragment_frame(tag)

            def handle_data(self, data):
                if self.in_style:
                    self.style_text.append(data)
                elif self.in_td and data:
                    self.cell_chunks.append(_html_mod.escape(_clean_spaces_keep_edges(data), quote=False))
                elif not self.seen_table_cell and data:
                    self.fragment_chunks.append(_html_mod.escape(_clean_spaces_keep_edges(data), quote=False))

        parser = LibreParser()
        parser.feed(html or "")
        parser.close()

        if not parser.grid and parser.fragment_chunks:
            parser.fragment_state = parser._transition_state(
                parser.fragment_state,
                _empty_style_state(False),
                parser.fragment_chunks
            )
            parser.fragment_frames = []

            rich = "".join(parser.fragment_chunks)
            rich = _remove_empty_style_tags(re.sub(r"\s*<br>\s*", "<br>", rich)).strip()
            plain = plain_from_rich(rich)
            if plain:
                return [[CellValue(plain=plain, rich_html=rich)]]

        return parser.expanded_grid()


class FallbackTSV:
    @staticmethod
    def processar(text: str) -> List[List[CellValue]]:
        if not text:
            return []
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        try:
            rows = [row or [''] for row in csv.reader(StringIO(text, newline=''), delimiter='\t', strict=True)]
        except csv.Error:
            # Arbitrary text may contain unmatched quotes. Preserve it literally
            # instead of swallowing subsequent records or failing Ctrl+V.
            lines = text.split('\n')
            if lines[-1] == '':
                lines.pop()  # one final record terminator, not internal blank rows
            rows = [line.split('\t') for line in lines]
        width = max(map(len, rows), default=0)
        if width * len(rows) > _TableHTMLParser.MAX_EXPANDED_CELLS:
            width = 0  # avoid multiplying a sparse text selection into a huge grid
        return [[CellValue(value, _html_mod.escape(value, quote=False).replace('\n', '<br>'))
                 for value in row + [''] * max(0, width - len(row))] for row in rows]


class _HTMLOrigin(HTMLParser):
    """Read provenance from markup, never from the user's cell text/comments."""
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.generators = []
        self.excel = False
        self.sheets_origin = False
        self.sheets_attributes = False
        self.feed(html)
        self.close()

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == 'meta':
            name = (attributes.get('name') or '').strip().lower()
            content = (attributes.get('content') or '').strip().lower()
            if name == 'generator' and content:
                self.generators.append(content)
            elif name == 'progid' and content.startswith('excel.sheet'):
                self.excel = True
        if any(key.startswith('xmlns:') and (value or '').lower() == 'urn:schemas-microsoft-com:office:excel'
               for key, value in attrs):
            self.excel = True
        if tag == 'google-sheets-html-origin':
            self.sheets_origin = True
        if tag in ('table', 'tr', 'td', 'th', 'span'):
            self.sheets_attributes |= any(key.startswith('data-sheets-') for key, _ in attrs)

    def processor(self):
        if any(re.search(r'\b(?:libreoffice|openoffice)\b', name) for name in self.generators):
            return LibreOffice
        if self.excel or any('microsoft excel' in name for name in self.generators):
            return Excel
        if (self.sheets_origin or any('google sheets' in name for name in self.generators)
                or (self.sheets_attributes and not self.generators)):
            return GoogleSheets
        # Other generators can also emit compatibility attributes. Use the
        # shared HTML/CSS capabilities rather than guessing a brand from them.
        return Excel


# ---------------------------------------------------------------------------
# O PORTEIRO (Função de Triagem Centralizada)
# ---------------------------------------------------------------------------
def router(html: str, texto: str) -> List[List[CellValue]]:
    """Função de triagem que atua como porteiro, identificando a assinatura

    dos dados e direcionando ao trabalhador especializado correspondente.
    """
    if not html or not html.strip():
        return FallbackTSV.processar(texto)

    try:
        grid = _HTMLOrigin(html).processor().processar(html)
        if grid:
            return grid
    except (ValueError, AssertionError):
        # HTMLParser can reject malformed declarations; no input error should
        # discard a valid text representation supplied by the source.
        pass
    # An empty/incomplete HTML representation must not discard available text.
    return FallbackTSV.processar(texto)


def parse_clipboard_mime_data(mime) -> List[List[CellValue]]:
    """Prefer the Calc native selection, which preserves partial formatting."""
    from .calc_clipboard import is_calc_format, parse_calc_package, MAX_PACKAGE_BYTES
    for name in mime.formats():
        if is_calc_format(name):
            raw = mime.data(name)
            if raw.size() <= MAX_PACKAGE_BYTES:
                grid = parse_calc_package(bytes(raw))
                if grid is not None:
                    return grid
    return router(mime.html() if mime.hasHtml() else '', mime.text() if mime.hasText() else '')


# ---------------------------------------------------------------------------
# Pontos de Entrada Legados (Mantidos para compatibilidade com o table_panel.py)
# ---------------------------------------------------------------------------
def parse_clipboard_html_table(html: str) -> List[List[CellValue]]:
    return router(html, "")

def parse_tsv(text: str) -> List[List[CellValue]]:
    return FallbackTSV.processar(text)

def parse_clipboard_html_fragment(html: str) -> List[List[CellValue]]:
    # Garante o roteamento mesmo para fragmentos de texto estilizados avulsos
    return router(html, "")
