from __future__ import annotations

import html as html_module
import re
from dataclasses import dataclass, field
from io import BytesIO

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph
from pypdf import PdfReader

from .richtext import guess_template_name, html_to_text


@dataclass
class ImportResult:
    name: str
    content: str
    kind: str
    warnings: list[str] = field(default_factory=list)


_HEADING_RE = re.compile(r"^(?:heading|标题)\s*([1-6])$", re.IGNORECASE)
_LIST_STYLES = ("list bullet", "list number", "list paragraph", "项目符号", "编号列表", "列表")
_ALIGN_MAP = {
    WD_ALIGN_PARAGRAPH.CENTER: "center",
    WD_ALIGN_PARAGRAPH.RIGHT: "right",
    WD_ALIGN_PARAGRAPH.JUSTIFY: "justify",
    WD_ALIGN_PARAGRAPH.LEFT: "left",
}
_PAGE_NUMBER_RE = re.compile(r"^[\-—–_\s]*\d+[\-—–_\s]*$")
_PAGE_LABEL_RE = re.compile(r"^第\s*\d+\s*页(?:\s*[/共]\s*\d+\s*页)?$")
_SECTION_RE = re.compile(r"^第[一二三四五六七八九十百千零〇0-9]+[条章节]")


def _heading_level(paragraph: Paragraph) -> int:
    try:
        name = (paragraph.style.name or "").strip()
    except Exception:
        return 0
    match = _HEADING_RE.match(name)
    if match:
        return int(match.group(1))
    return 0


def _is_list_paragraph(paragraph: Paragraph) -> bool:
    try:
        name = (paragraph.style.name or "").lower()
    except Exception:
        name = ""
    if any(token in name for token in _LIST_STYLES):
        return True
    try:
        properties = paragraph._p.pPr
        return bool(properties is not None and properties.numPr is not None)
    except Exception:
        return False


def _east_asian_font(run) -> str | None:
    try:
        rpr = run._element.rPr
        if rpr is None or rpr.rFonts is None:
            return None
        return rpr.rFonts.get(qn("w:eastAsia")) or None
    except Exception:
        return None


def _run_html(run) -> str:
    text = run.text or ""
    if not text:
        return ""
    inner = html_module.escape(text).replace("\n", "<br/>")
    styles: list[str] = []
    try:
        if run.font.size:
            styles.append(f"font-size: {run.font.size.pt:g}pt")
        family = run.font.name or _east_asian_font(run)
        if family:
            styles.append(f"font-family: {family}")
        if run.font.color is not None and run.font.color.rgb is not None:
            styles.append(f"color: #{run.font.color.rgb}")
    except Exception:
        pass
    try:
        if run.bold:
            inner = f"<strong>{inner}</strong>"
        if run.italic:
            inner = f"<em>{inner}</em>"
        if run.underline:
            inner = f"<u>{inner}</u>"
        if run.font.strike:
            inner = f"<s>{inner}</s>"
    except Exception:
        pass
    if styles:
        inner = f'<span style="{"; ".join(styles)}">{inner}</span>'
    return inner


def _paragraph_style_attrs(paragraph: Paragraph) -> str:
    styles: list[str] = []
    try:
        alignment = _ALIGN_MAP.get(paragraph.alignment)
        if alignment:
            styles.append(f"text-align: {alignment}")
        fmt = paragraph.paragraph_format
        if fmt.first_line_indent is not None:
            styles.append(f"text-indent: {fmt.first_line_indent.pt:.1f}pt")
        if fmt.left_indent is not None:
            styles.append(f"margin-left: {fmt.left_indent.pt:.1f}pt")
        spacing = fmt.line_spacing
        if isinstance(spacing, float):
            styles.append(f"line-height: {spacing:g}")
        elif spacing is not None and hasattr(spacing, "pt"):
            styles.append(f"line-height: {spacing.pt:.1f}pt")
    except Exception:
        pass
    return f' style="{"; ".join(styles)}"' if styles else ""


def _paragraph_html(paragraph: Paragraph, warnings: set[str]) -> str:
    try:
        if paragraph._element.xpath(".//w:drawing") or paragraph._element.xpath(".//w:pict"):
            warnings.add("Word 中的图片、图形暂未导入，请在编辑器中重新插入。")
    except Exception:
        pass
    inner = "".join(_run_html(run) for run in paragraph.runs).strip()
    if not inner:
        return "<p></p>"
    attrs = _paragraph_style_attrs(paragraph)
    level = _heading_level(paragraph)
    if level:
        tag = f"h{min(level, 4)}"
        return f"<{tag}{attrs}>{inner}</{tag}>"
    return f"<p{attrs}>{inner}</p>"


def _table_html(table: Table, warnings: set[str]) -> str:
    rows: list[str] = []
    for row in table.rows:
        cells: list[str] = []
        seen_cells: set[int] = set()
        for cell in row.cells:
            if id(cell._tc) in seen_cells:
                continue
            seen_cells.add(id(cell._tc))
            parts = [_paragraph_html(paragraph, warnings) for paragraph in cell.paragraphs]
            content = "".join(parts) or "<p></p>"
            try:
                colspan = int(cell._tc.grid_span or 1)
            except Exception:
                colspan = 1
            rowspan = 1
            attrs = ""
            if colspan > 1:
                attrs += f' colspan="{colspan}"'
            cells.append(f"<td{attrs}>{content}</td>")
        rows.append(f"<tr>{''.join(cells)}</tr>")
    return f"<table><tbody>{''.join(rows)}</tbody></table>"


def _iter_blocks(document: Document):
    from docx.oxml.table import CT_Tbl
    from docx.oxml.text.paragraph import CT_P

    for child in document.element.body.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, document)
        elif isinstance(child, CT_Tbl):
            yield Table(child, document)


def docx_to_html(data: bytes) -> ImportResult:
    document = Document(BytesIO(data))
    warnings: set[str] = set()
    blocks: list[str] = []
    list_type: str | None = None
    list_items: list[str] = []

    def flush_list() -> None:
        nonlocal list_type, list_items
        if list_type and list_items:
            blocks.append(f"<{list_type}>{''.join(list_items)}</{list_type}>")
        list_type = None
        list_items = []

    for block in _iter_blocks(document):
        if isinstance(block, Table):
            flush_list()
            blocks.append(_table_html(block, warnings))
            continue

        paragraph = block
        if _is_list_paragraph(paragraph):
            desired = "ol" if "number" in (paragraph.style.name or "").lower() or "编号" in (paragraph.style.name or "") else "ul"
            if list_type and list_type != desired:
                flush_list()
            list_type = desired
            inner = "".join(_run_html(run) for run in paragraph.runs).strip()
            list_items.append(f"<li>{inner}</li>" if inner else "<li></li>")
            continue

        flush_list()
        blocks.append(_paragraph_html(paragraph, warnings))

    flush_list()

    for section in document.sections:
        try:
            header_text = " ".join(p.text.strip() for p in section.header.paragraphs if p.text.strip())
            footer_text = " ".join(p.text.strip() for p in section.footer.paragraphs if p.text.strip())
            if header_text or footer_text:
                warnings.add("Word 页眉页脚内容未导入，如需保留请在模板正文中补充。")
                break
        except Exception:
            break

    content = "".join(blocks) or "<p></p>"
    while content.endswith("<p></p><p></p>"):
        content = content[: -len("<p></p>")]
    name = guess_template_name("", content, fallback="导入的 Word 模板")
    return ImportResult(name=name, content=content, kind="docx", warnings=sorted(warnings))


def _merge_pdf_lines(lines: list[str]) -> list[tuple[str, bool]]:
    paragraphs: list[tuple[str, bool]] = []
    current = ""

    def flush() -> None:
        nonlocal current
        if current.strip():
            paragraphs.append((current.strip(), False))
        current = ""

    for raw in lines:
        line = " ".join(raw.replace("\u3000", " ").split())
        if not line or _PAGE_NUMBER_RE.match(line) or _PAGE_LABEL_RE.match(line):
            continue
        if _SECTION_RE.match(line) or re.match(r"^(甲方|乙方|丙方|附件|附表)", line):
            flush()
            paragraphs.append((line, True))
            continue
        if current:
            separator = ""
            if current[-1:].isascii() and current[-1:].isalnum() and line[:1].isascii() and line[:1].isalnum():
                separator = " "
            current += separator + line
        else:
            current = line
        if re.search(r"[。！？；：!?;:]$", line):
            flush()

    flush()
    return paragraphs


def pdf_to_html(data: bytes) -> ImportResult:
    try:
        reader = PdfReader(BytesIO(data))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception as exc:
                raise ValueError("PDF 文件已加密，无法读取") from exc
        pages = [page.extract_text() or "" for page in reader.pages]
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("PDF 文件解析失败，请确认文件未损坏") from exc

    lines: list[str] = []
    for page in pages:
        lines.extend(page.replace("\x0c", "\n").splitlines())

    paragraphs = _merge_pdf_lines(lines)
    parts: list[str] = []
    for text, is_heading in paragraphs:
        escaped = html_module.escape(text)
        parts.append(f"<p><strong>{escaped}</strong></p>" if is_heading else f"<p>{escaped}</p>")
    content = "".join(parts) or "<p></p>"
    name = guess_template_name("", content, fallback="导入的 PDF 模板")
    return ImportResult(
        name=name,
        content=content,
        kind="pdf",
        warnings=[
            "PDF 仅提取文字内容，表格、图片与复杂排版可能丢失；建议优先上传 Word 版本，或在编辑器中重新排版。"
        ],
    )


def import_document(filename: str, data: bytes) -> ImportResult:
    suffix = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if suffix == ".docx":
        result = docx_to_html(data)
    elif suffix == ".pdf":
        result = pdf_to_html(data)
    else:
        raise ValueError("仅支持 Word（.docx）或 PDF 文件")
    if not html_to_text(result.content).strip():
        raise ValueError("未从文件中识别到文字内容，请尝试其他文件")
    if not result.name or not result.name.strip():
        result.name = guess_template_name(filename, result.content)
    return result
