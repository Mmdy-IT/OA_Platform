from __future__ import annotations

import os
import re
import threading
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)

from .amounts import (
    apply_auto_amounts,
    apply_table_summary_totals,
    payment_upper_texts,
    resolve_payment_base_amount,
)
from .warehouse_db import resolve_warehouse_values
from .richpdf import build_html_flowables
from .richtext import BLANK, CONTRACT_NUMBER_PLACEHOLDER, PLACEHOLDER_RE, is_html
from .tables import apply_table_adjustments

SECTION_RE = re.compile(r"^第[一二三四五六七八九十百]+条")

_font_lock = threading.Lock()
_fonts_ready = False
_regular_font = "STSong-Light"
_bold_font = "STSong-Light"
_font_families: dict[str, str] = {}


def _register_font_file(name: str, path: Path, subfont_index: int | None = None) -> bool:
    if not path.exists():
        return False
    try:
        if subfont_index is None:
            pdfmetrics.registerFont(TTFont(name, str(path)))
        else:
            pdfmetrics.registerFont(TTFont(name, str(path), subfontIndex=subfont_index))
        return True
    except Exception:
        return False


def _register_family(name: str, bold_name: str) -> None:
    try:
        pdfmetrics.registerFontFamily(
            name, normal=name, bold=bold_name, italic=name, boldItalic=bold_name
        )
    except Exception:
        pass


def _register_fonts() -> None:
    global _fonts_ready, _regular_font, _bold_font, _font_families
    if _fonts_ready:
        return
    with _font_lock:
        if _fonts_ready:
            return
        custom_paths = [
            Path(part.strip().strip('"'))
            for part in os.getenv("OA_PDF_FONT", "").split(os.pathsep)
            if part.strip()
        ]
        regular_candidates = [
            *[("OAContractSans", path) for path in custom_paths],
            ("OAContractSans", Path(r"C:\Windows\Fonts\simfang.ttf")),
            ("OAContractSans", Path(r"C:\Windows\Fonts\simhei.ttf")),
            ("OAContractSans", Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")),
        ]
        bold_candidates = [
            *[("OAContractSansBold", path) for path in custom_paths],
            ("OAContractSansBold", Path(r"C:\Windows\Fonts\simhei.ttf")),
            ("OAContractSansBold", Path(r"C:\Windows\Fonts\simfang.ttf")),
        ]

        regular = None
        for name, path in regular_candidates:
            if path.exists():
                try:
                    pdfmetrics.registerFont(TTFont(name, str(path)))
                    regular = name
                    break
                except Exception:
                    continue
        bold = None
        for name, path in bold_candidates:
            if path.exists():
                try:
                    pdfmetrics.registerFont(TTFont(name, str(path)))
                    bold = name
                    break
                except Exception:
                    continue

        if regular is None:
            try:
                pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
                regular = "STSong-Light"
            except Exception:
                regular = "Helvetica"
        _regular_font = regular
        _bold_font = bold or regular
        _register_family(_regular_font, _bold_font)

        extras = {
            "SimSun": (Path(r"C:\Windows\Fonts\simsun.ttc"), 0, Path(r"C:\Windows\Fonts\simhei.ttf")),
            "SimHei": (Path(r"C:\Windows\Fonts\simhei.ttf"), None, Path(r"C:\Windows\Fonts\simhei.ttf")),
            "FangSong": (Path(r"C:\Windows\Fonts\simfang.ttf"), None, Path(r"C:\Windows\Fonts\simhei.ttf")),
            "KaiTi": (Path(r"C:\Windows\Fonts\simkai.ttf"), None, Path(r"C:\Windows\Fonts\simhei.ttf")),
            "MicrosoftYaHei": (Path(r"C:\Windows\Fonts\msyh.ttc"), 0, Path(r"C:\Windows\Fonts\msyhbd.ttc")),
        }
        aliases = {
            "simsun": "SimSun",
            "宋体": "SimSun",
            "simhei": "SimHei",
            "黑体": "SimHei",
            "fangsong": "FangSong",
            "仿宋": "FangSong",
            "仿宋_gb2312": "FangSong",
            "kaiti": "KaiTi",
            "楷体": "KaiTi",
            "楷体_gb2312": "KaiTi",
            "microsoft yahei": "MicrosoftYaHei",
            "微软雅黑": "MicrosoftYaHei",
        }
        families = {"oacontractsans": _regular_font}
        for family, (path, index, bold_path) in extras.items():
            if not _register_font_file(family, path, index):
                continue
            bold_family = f"{family}Bold"
            if not _register_font_file(
                bold_family, bold_path, index if bold_path.suffix.lower() == ".ttc" else None
            ):
                bold_family = family
            _register_family(family, bold_family)
            families[family.lower()] = family
        for alias, family in aliases.items():
            if family.lower() in families:
                families[alias] = family
        _font_families = families
        _fonts_ready = True


def render_contract_text(content: str, values: dict[str, str]) -> str:
    def replace(match: re.Match) -> str:
        key = match.group(1)
        value = values.get(key, "")
        return value.strip() if value and value.strip() else BLANK

    return PLACEHOLDER_RE.sub(replace, content)


_DATE_VALUE_RE = re.compile(
    r"^(\d{4})(?:-|/|\.|年)(\d{1,2})(?:-|/|\.|月)(\d{1,2})日?"
)


def _format_chinese_date(value: str) -> str:
    match = _DATE_VALUE_RE.match(str(value or "").strip())
    if not match:
        return value
    year, month, day = (int(part) for part in match.groups())
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return value
    return f"{year}年{month:02d}月{day:02d}日"


def _format_field_values(fields: list[dict], values: dict[str, str]) -> dict[str, str]:
    formatted = dict(values)
    for field in fields or []:
        field_type = field.get("type")
        key = field.get("key", "")
        raw = formatted.get(key, "")
        if not raw:
            continue
        if field_type == "currency":
            try:
                formatted[key] = f"{float(str(raw).replace(',', '')):,.2f}"
            except (TypeError, ValueError):
                continue
        elif field_type == "date":
            formatted[key] = _format_chinese_date(str(raw))
    return formatted


def _contract_document_values(contract: dict) -> dict[str, str]:
    fields = contract.get("fields_schema", [])
    template_content = contract.get("template_content", "")
    adjustments = contract.get("table_adjustments") or {}
    values = resolve_warehouse_values(contract.get("field_values", {}), fields)
    values = apply_auto_amounts(
        template_content,
        adjustments,
        fields,
        values,
    )
    payment_base = resolve_payment_base_amount(
        template_content, adjustments, fields, values
    )
    if payment_base is not None:
        values.update(payment_upper_texts(payment_base))
    values = _format_field_values(fields, values)
    values[CONTRACT_NUMBER_PLACEHOLDER] = (
        "\u200b"
        if contract.get("template_category") == "通用类" and contract.get("bundle_id")
        else str(contract.get("contract_no") or "").strip()
    )
    return values


def _xml_text(text: str) -> str:
    return escape(text).replace("\n", "<br/>")


def build_contract_pdf(contract: dict) -> bytes:
    _register_fonts()
    buffer = BytesIO()

    title_style = ParagraphStyle(
        "contract-title",
        fontName=_bold_font,
        fontSize=18,
        leading=28,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#132238"),
        spaceAfter=8 * mm,
    )
    body_style = ParagraphStyle(
        "contract-body",
        fontName=_regular_font,
        fontSize=10.5,
        leading=19,
        alignment=TA_JUSTIFY,
        textColor=colors.HexColor("#202b3b"),
        firstLineIndent=21,
        spaceAfter=2.2 * mm,
        wordWrap="CJK",
    )
    section_style = ParagraphStyle(
        "contract-section",
        parent=body_style,
        fontName=_bold_font,
        fontSize=11,
        leading=20,
        firstLineIndent=0,
        spaceBefore=3.5 * mm,
        spaceAfter=1.8 * mm,
    )
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=24 * mm,
        bottomMargin=22 * mm,
        title=contract["title"],
        author="绵绵聚道",
        subject=contract.get("contract_no", ""),
    )

    story = []
    story.append(Paragraph(_xml_text(contract["title"]), title_style))

    field_values = _contract_document_values(contract)
    template_content = apply_table_adjustments(
        contract["template_content"], contract.get("table_adjustments") or {}
    )
    template_content = apply_table_summary_totals(template_content)
    if is_html(template_content):
        story.extend(
            build_html_flowables(
                template_content,
                field_values,
                body_font=_regular_font,
                bold_font=_bold_font,
                font_family_map=_font_families,
                base_size=10.5,
                base_leading=19.0,
                base_color="#202b3b",
                content_width=A4[0] - 40 * mm,
            )
        )
    else:
        joined = render_contract_text(template_content, field_values)
        source_lines = [line.rstrip() for line in joined.splitlines()]
        while source_lines and not source_lines[0].strip():
            source_lines.pop(0)
        if source_lines:
            first = source_lines[0].strip()
            if (
                len(first) <= 24
                and ("合同" in first or "协议" in first)
                and "{{" not in first
                and not any(punct in first for punct in "：:，,。；;")
            ):
                source_lines.pop(0)
                while source_lines and not source_lines[0].strip():
                    source_lines.pop(0)

        for line in source_lines:
            stripped = line.strip()
            if not stripped:
                story.append(Spacer(1, 2 * mm))
                continue
            style = section_style if SECTION_RE.match(stripped) else body_style
            story.append(Paragraph(_xml_text(stripped), style))

    comment = (contract.get("review_comment") or "").strip()
    if comment:
        story.append(Spacer(1, 8 * mm))
        story.append(Paragraph("法务审核意见", section_style))
        story.append(Paragraph(_xml_text(comment), body_style))

    def draw_page(canvas, document):
        width, height = A4
        canvas.saveState()
        canvas.setFont(_regular_font, 9)
        canvas.setFillColor(colors.HexColor("#666666"))
        canvas.drawCentredString(width / 2, 10 * mm, f"第 {document.page} 页")
        canvas.restoreState()

    doc.build(story, onFirstPage=draw_page, onLaterPages=draw_page)
    return buffer.getvalue()
