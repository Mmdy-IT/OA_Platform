from __future__ import annotations

import html as html_module
import re
from html.parser import HTMLParser
from typing import Iterable

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import HRFlowable, Paragraph, Spacer, Table, TableStyle

from .richtext import BLANK, PLACEHOLDER_RE

_BLOCK_TAGS = {
    "p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote", "pre",
}
_CONTAINER_TAGS = {"table", "ul", "ol", "thead", "tbody", "tfoot", "tr", "td", "th", "colgroup"}
_VOID_TAGS = {"br", "hr", "col"}
_SKIP_DROP = {"script", "style"}

_ALIGN = {
    "left": TA_LEFT,
    "center": TA_CENTER,
    "right": TA_RIGHT,
    "justify": TA_JUSTIFY,
}


class _Node:
    __slots__ = ("tag", "attrs", "children")

    def __init__(self, tag: str, attrs: dict[str, str] | None = None) -> None:
        self.tag = tag
        self.attrs = attrs or {}
        self.children: list["_Node | str"] = []

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<_Node {self.tag}>"


class _TreeBuilder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node("root")
        self.stack: list[_Node] = [self.root]
        self.drop_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if self.drop_depth:
            if tag not in _VOID_TAGS:
                self.drop_depth += 1
            return
        if tag in _SKIP_DROP:
            self.drop_depth = 1
            return
        node = _Node(tag, {name.lower(): (value or "") for name, value in attrs})
        self.stack[-1].children.append(node)
        if tag not in _VOID_TAGS:
            self.stack.append(node)

    def handle_startendtag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if self.drop_depth:
            return
        self.stack[-1].children.append(
            _Node(tag, {name.lower(): (value or "") for name, value in attrs})
        )

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self.drop_depth:
            self.drop_depth = max(0, self.drop_depth - 1)
            return
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                return

    def handle_data(self, data: str) -> None:
        if self.drop_depth:
            return
        self.stack[-1].children.append(data)


def _parse_html(content: str) -> _Node:
    builder = _TreeBuilder()
    builder.feed(content or "")
    builder.close()
    return builder.root


def _parse_style(raw: str | None) -> dict[str, str]:
    result: dict[str, str] = {}
    for chunk in (raw or "").split(";"):
        if ":" not in chunk:
            continue
        name, _, value = chunk.partition(":")
        name = name.strip().lower()
        value = value.strip()
        if name and value:
            result[name] = value
    return result


def _length(value: str | None, base_size: float) -> float | None:
    if not value:
        return None
    match = re.fullmatch(r"(-?\d+(?:\.\d+)?)\s*(px|pt|mm|cm|em|rem|%)?", value.strip().lower())
    if not match:
        return None
    number = float(match.group(1))
    unit = match.group(2) or "pt"
    if unit == "px":
        number *= 0.75
    elif unit == "mm":
        number *= 2.8346
    elif unit == "cm":
        number *= 28.346
    elif unit in {"em", "rem"}:
        number *= base_size
    elif unit == "%":
        number = number / 100 * base_size
    return max(0.0, min(number, 600.0))


def _color(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip().lower()
    if re.fullmatch(r"#[0-9a-f]{3}(?:[0-9a-f]{3})?", value):
        return value
    match = re.fullmatch(r"rgba?\(([^)]+)\)", value)
    if match:
        parts = [part.strip() for part in match.group(1).split(",")[:3]]
        try:
            return "#%02x%02x%02x" % tuple(int(float(part)) for part in parts)
        except (TypeError, ValueError):
            return None
    named = {
        "black": "#000000",
        "red": "#ff0000",
        "blue": "#0000ff",
        "green": "#008000",
        "gray": "#808080",
        "grey": "#808080",
        "white": "#ffffff",
    }
    return named.get(value)


def _family_key(value: str | None) -> str:
    if not value:
        return ""
    first = value.split(",")[0].strip().strip('"').strip("'")
    return first.lower()


def _node_text(node: _Node | str) -> str:
    if isinstance(node, str):
        return node
    return "".join(_node_text(child) for child in node.children)


def _is_block(node: "_Node | str") -> bool:
    return isinstance(node, _Node) and (node.tag in _BLOCK_TAGS or node.tag in _CONTAINER_TAGS)


class _Renderer:
    def __init__(
        self,
        values: dict[str, str],
        body_font: str,
        bold_font: str,
        font_family_map: dict[str, str],
        base_size: float,
        base_leading: float,
        base_color: str,
        content_width: float,
    ) -> None:
        self.values = values
        self.body_font = body_font
        self.bold_font = bold_font
        self.font_family_map = {key.lower(): value for key, value in (font_family_map or {}).items()}
        self.base_size = base_size
        self.base_leading = base_leading
        self.base_color = colors.HexColor(base_color)
        self.content_width = content_width
        self._style_seq = 0
        self._cell_depth = 0

    # ------------------------------------------------------------------ blocks
    def build(self, root: _Node) -> list:
        flowables: list = []
        first = True
        for node in root.children:
            if isinstance(node, str):
                if node.strip():
                    flowables.append(self.paragraph_from_inline([node], indent_default=not first))
                    first = False
                continue
            if self._should_skip_title(node, first):
                first = False
                continue
            if node.tag in _SKIP_DROP:
                continue
            first = False
            flowables.extend(self.render_node(node, 0))
        return flowables

    def _should_skip_title(self, node: _Node, first: bool) -> bool:
        if not first or node.tag not in {"p", "h1", "h2", "h3", "h4", "div"}:
            return False
        text = _node_text(node).strip()
        if not text or "{{" in text or len(text) > 30:
            return False
        if any(punct in text for punct in "：:，,。；;"):
            return False
        return "合同" in text or "协议" in text

    def render_node(self, node: _Node, level: int) -> list:
        tag = node.tag
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            return [self.heading(node)]
        if tag == "p":
            return [self.paragraph(node)]
        if tag == "div":
            if any(_is_block(child) for child in node.children):
                flowables: list = []
                for child in node.children:
                    if isinstance(child, str):
                        if child.strip():
                            flowables.append(self.paragraph_from_inline([child]))
                    else:
                        flowables.extend(self.render_node(child, level))
                return flowables
            return [self.paragraph(node)]
        if tag in {"ul", "ol"}:
            return self.render_list(node, level)
        if tag == "table":
            return self.render_table(node)
        if tag == "hr":
            return [
                HRFlowable(
                    width="100%",
                    thickness=0.7,
                    color=colors.HexColor("#d8dfe8"),
                    spaceBefore=2 * mm,
                    spaceAfter=2 * mm,
                )
            ]
        if tag == "br":
            return [Spacer(1, self.base_size * 1.2)]
        if tag == "blockquote":
            return [self.paragraph(node, kind="quote")]
        if tag == "pre":
            return [self.paragraph(node, kind="pre")]
        if tag == "li":
            return [self.paragraph(node)]
        if _is_block(node):
            return [self.paragraph_from_inline([node])]
        markup = self.inline_children(node.children)
        return [Paragraph(markup, self.paragraph_style(None, "body"))] if markup.strip() else []

    # ------------------------------------------------------------------ text
    def render_text(self, text: str) -> str:
        parts: list[str] = []
        position = 0
        for match in PLACEHOLDER_RE.finditer(text):
            parts.append(html_module.escape(text[position : match.start()]))
            value = (self.values.get(match.group(1)) or "").strip()
            parts.append(html_module.escape(value) if value else BLANK)
            position = match.end()
        parts.append(html_module.escape(text[position:]))
        return "".join(parts).replace("\n", "<br/>")

    def inline_children(self, children: Iterable["_Node | str"]) -> str:
        return "".join(self.inline(child) for child in children)

    def inline(self, node: "_Node | str") -> str:
        if isinstance(node, str):
            return self.render_text(node)
        tag = node.tag
        if tag == "br":
            return "<br/>"
        if tag in _SKIP_DROP:
            return ""
        inner = self.inline_children(node.children)
        if tag in {"strong", "b"}:
            return f"<b>{inner}</b>"
        if tag in {"em", "i"}:
            return f"<i>{inner}</i>"
        if tag in {"u", "ins"}:
            return f"<u>{inner}</u>"
        if tag in {"s", "strike", "del"}:
            return f"<strike>{inner}</strike>"
        if tag == "sup":
            return f"<super>{inner}</super>"
        if tag == "sub":
            return f"<sub>{inner}</sub>"
        if tag in {"span", "font", "mark", "a"}:
            style = _parse_style(node.attrs.get("style"))
            face = self.font_family_map.get(_family_key(style.get("font-family") or node.attrs.get("face")))
            size = _length(style.get("font-size"), self.base_size)
            color = _color(style.get("color") or node.attrs.get("color"))
            weight = (style.get("font-weight") or "").strip().lower()
            decoration = (style.get("text-decoration") or "").lower()
            if weight in {"bold", "bolder", "600", "700", "800", "900"}:
                inner = f"<b>{inner}</b>"
            if style.get("font-style") == "italic":
                inner = f"<i>{inner}</i>"
            if "underline" in decoration or tag == "u":
                inner = f"<u>{inner}</u>"
            if "line-through" in decoration:
                inner = f"<strike>{inner}</strike>"
            attrs: list[str] = []
            if face:
                attrs.append(f'face="{html_module.escape(face, quote=True)}"')
            if size:
                attrs.append(f'size="{size:g}"')
            if color:
                attrs.append(f'color="{color}"')
            if attrs:
                inner = f"<font {' '.join(attrs)}>{inner}</font>"
            return inner
        return inner

    # ------------------------------------------------------------------ paragraphs
    def paragraph(self, node: _Node, kind: str = "body") -> Paragraph | Spacer:
        markup = self.inline_children(node.children)
        if not markup.strip() or re.fullmatch(r"(?:<br/>\s*)+", markup):
            return Spacer(1, max(8.0, self.base_size * 1.35))
        return Paragraph(markup, self.paragraph_style(node, kind))

    def paragraph_from_inline(self, children: Iterable["_Node | str"], indent_default: bool = True) -> Paragraph:
        markup = self.inline_children(children)
        return Paragraph(markup, self.paragraph_style(None, "body", indent_default=indent_default))

    def heading(self, node: _Node) -> Paragraph:
        markup = self.inline_children(node.children)
        return Paragraph(markup, self.paragraph_style(node, node.tag))

    def paragraph_style(
        self,
        node: _Node | None,
        kind: str,
        indent_default: bool = True,
    ) -> ParagraphStyle:
        style = _parse_style(node.attrs.get("style")) if node is not None else {}
        self._style_seq += 1

        size = _length(style.get("font-size"), self.base_size)
        leading = self.base_leading
        font = self.body_font
        align = TA_JUSTIFY
        first_indent = 2 * self.base_size if indent_default else 0.0
        left_indent = 0.0
        space_before = 0.0
        space_after = 2.2 * mm
        text_color = self.base_color

        if kind in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            heading_sizes = {"h1": 16.0, "h2": 13.5, "h3": 12.0, "h4": 11.0, "h5": 10.5, "h6": 10.5}
            size = size or heading_sizes[kind]
            font = self.bold_font
            align = TA_LEFT
            first_indent = 0.0
            space_before = 4 * mm if kind in {"h1", "h2"} else 3 * mm
            space_after = 2 * mm
        elif kind == "quote":
            size = size or self.base_size
            left_indent = 12
            first_indent = 0.0
            text_color = colors.HexColor("#5b6778")
            space_after = 2 * mm
        elif kind == "pre":
            size = size or self.base_size
            first_indent = 0.0
            align = TA_LEFT
        else:
            size = size or self.base_size
            if self._cell_depth:
                first_indent = 0.0
                align = TA_LEFT
                space_after = 0.8 * mm

        if style.get("line-height"):
            computed = self._line_height(style["line-height"], size)
            if computed:
                leading = computed
        elif kind in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            leading = size * 1.55
        elif self._cell_depth:
            leading = size * 1.55

        if style.get("text-indent"):
            first_indent = _length(style["text-indent"], size) or 0.0
        if style.get("margin-left"):
            left_indent = _length(style["margin-left"], size) or 0.0
        if style.get("text-align", "").lower() in _ALIGN:
            align = _ALIGN[style["text-align"].lower()]
        if _color(style.get("color")):
            text_color = colors.HexColor(_color(style["color"]))

        return ParagraphStyle(
            f"rt-{self._style_seq}",
            fontName=font,
            fontSize=size,
            leading=leading,
            alignment=align,
            textColor=text_color,
            firstLineIndent=first_indent,
            leftIndent=left_indent,
            spaceBefore=space_before,
            spaceAfter=space_after,
            wordWrap="CJK",
        )

    def _line_height(self, value: str, size: float) -> float | None:
        value = value.strip().lower()
        if re.fullmatch(r"\d+(?:\.\d+)?", value):
            return max(size, float(value) * size)
        if value.endswith("%"):
            try:
                return max(size, float(value[:-1]) / 100 * size)
            except ValueError:
                return None
        computed = _length(value, size)
        return max(size, computed) if computed else None

    # ------------------------------------------------------------------ lists
    def render_list(self, node: _Node, level: int) -> list:
        ordered = node.tag == "ol"
        try:
            start = int(node.attrs.get("start") or 1)
        except ValueError:
            start = 1
        flowables: list = []
        index = start
        for item in node.children:
            if not isinstance(item, _Node):
                continue
            if item.tag != "li":
                flowables.extend(self.render_node(item, level + 1))
                continue
            paragraphs = [child for child in item.children if isinstance(child, _Node) and child.tag == "p"]
            inline_children = item.children if paragraphs else [item]
            for position, paragraph_node in enumerate(inline_children if paragraphs else [item]):
                children = paragraph_node.children if isinstance(paragraph_node, _Node) else [paragraph_node]
                markup = self.inline_children(children)
                if not markup.strip():
                    continue
                style = self.paragraph_style(paragraph_node if isinstance(paragraph_node, _Node) else None, "body")
                style.leftIndent = style.leftIndent + 12 + level * 16
                style.firstLineIndent = 0
                style.spaceAfter = 1.2 * mm
                bullet = None
                if position == 0:
                    bullet = f"{index}. " if ordered else "•"
                flowables.append(Paragraph(markup, style, bulletText=bullet))
            for child in item.children:
                if isinstance(child, _Node) and child.tag in {"ul", "ol"}:
                    flowables.extend(self.render_list(child, level + 1))
            index += 1
        flowables.append(Spacer(1, 1.2 * mm))
        return flowables

    # ------------------------------------------------------------------ tables
    def render_table(self, node: _Node) -> list:
        rows: list[list] = []
        spans: list[tuple] = []
        occupied: set[tuple[int, int]] = set()
        col_widths: list[float] | None = None
        header_rows = 0

        row_nodes: list[_Node] = []
        for section in node.children:
            if not isinstance(section, _Node):
                continue
            if section.tag == "colgroup":
                widths = self._col_widths(section)
                if widths:
                    col_widths = widths
                continue
            if section.tag in {"thead", "tbody", "tfoot"}:
                if section.tag == "thead":
                    header_rows += sum(1 for child in section.children if isinstance(child, _Node) and child.tag == "tr")
                row_nodes.extend(
                    child for child in section.children if isinstance(child, _Node) and child.tag == "tr"
                )
            elif section.tag == "tr":
                row_nodes.append(section)

        for row_index, row_node in enumerate(row_nodes):
            cells: list = []
            column = 0
            cell_nodes = [child for child in row_node.children if isinstance(child, _Node) and child.tag in {"td", "th"}]
            for cell_node in cell_nodes:
                while (row_index, column) in occupied:
                    cells.append("")
                    column += 1
                try:
                    colspan = max(1, int(cell_node.attrs.get("colspan") or 1))
                    rowspan = max(1, int(cell_node.attrs.get("rowspan") or 1))
                except ValueError:
                    colspan, rowspan = 1, 1
                colspan = min(colspan, 12)
                rowspan = min(rowspan, 30)
                for dc in range(colspan):
                    for dr in range(rowspan):
                        occupied.add((row_index + dr, column + dc))
                if colspan > 1 or rowspan > 1:
                    spans.append(
                        ("SPAN", (column, row_index), (column + colspan - 1, row_index + rowspan - 1))
                    )
                cells.append(self._cell_flowables(cell_node))
                for _ in range(colspan - 1):
                    cells.append("")
                column += colspan
            # Fill trailing occupied slots so rows stay rectangular.
            while (row_index, column) in occupied:
                cells.append("")
                column += 1
            rows.append(cells)

        if not rows:
            return []
        max_columns = max(len(row) for row in rows)
        for row in rows:
            while len(row) < max_columns:
                row.append("")
        if col_widths and len(col_widths) == max_columns:
            widths = [max(12.0, ratio) for ratio in col_widths]
            total = sum(widths)
            widths = [width / total * self.content_width for width in widths]
        else:
            widths = [self.content_width / max_columns] * max_columns

        table = Table(rows, colWidths=widths, repeatRows=header_rows)
        commands = [
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#b9c3d1")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
        if header_rows:
            commands.append(("BACKGROUND", (0, 0), (-1, header_rows - 1), colors.HexColor("#f1f4f9")))
        commands.extend(spans)
        table.setStyle(TableStyle(commands))
        return [Spacer(1, 1.5 * mm), table, Spacer(1, 1.5 * mm)]

    def _col_widths(self, node: _Node) -> list[float] | None:
        values: list[float] = []
        for child in node.children:
            if not isinstance(child, _Node) or child.tag != "col":
                continue
            width = _parse_style(child.attrs.get("style")).get("width") or child.attrs.get("width")
            if not width:
                values.append(0.0)
                continue
            match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(%|px|pt)?", width.strip().lower())
            values.append(float(match.group(1)) if match else 0.0)
        if not values or not any(values):
            return None
        return values

    def _cell_flowables(self, node: _Node) -> list:
        self._cell_depth += 1
        try:
            flowables: list = []
            for child in node.children:
                if isinstance(child, str):
                    if child.strip():
                        flowables.append(self.paragraph_from_inline([child], indent_default=False))
                    continue
                if child.tag in _BLOCK_TAGS or child.tag in _CONTAINER_TAGS:
                    flowables.extend(self.render_node(child, 0))
                else:
                    markup = self.inline(child)
                    if markup.strip():
                        flowables.append(
                            Paragraph(markup, self.paragraph_style(child, "body", indent_default=False))
                        )
            if not flowables:
                return [
                    Paragraph(
                        "\u00a0",
                        self.paragraph_style(None, "body", indent_default=False),
                    )
                ]
            return flowables
        finally:
            self._cell_depth -= 1


def build_html_flowables(
    content: str,
    values: dict[str, str] | None = None,
    *,
    body_font: str,
    bold_font: str,
    font_family_map: dict[str, str] | None = None,
    base_size: float = 10.5,
    base_leading: float = 19.0,
    base_color: str = "#202b3b",
    content_width: float = 170 * mm,
) -> list:
    root = _parse_html(content)
    renderer = _Renderer(
        values or {},
        body_font,
        bold_font,
        font_family_map or {},
        base_size,
        base_leading,
        base_color,
        content_width,
    )
    return renderer.build(root)
