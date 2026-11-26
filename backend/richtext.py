from __future__ import annotations

import html as html_module
import re
from html.parser import HTMLParser

KEY_START = r"A-Za-z_\u3400-\u4dbf\u4e00-\u9fff"
KEY_BODY = r"A-Za-z0-9_\u3400-\u4dbf\u4e00-\u9fff"

PLACEHOLDER_RE = re.compile(r"\{\{\s*([" + KEY_START + r"][" + KEY_BODY + r"]{0,39})\s*\}\}")
FIELD_KEY_RE = re.compile(r"^[" + KEY_START + r"][" + KEY_BODY + r"]{0,39}$")

CONTRACT_NUMBER_PLACEHOLDER = "合同编号"
PREPAYMENT_PLACEHOLDER = "预付款"
FINAL_PAYMENT_PLACEHOLDER = "尾款"
SYSTEM_PLACEHOLDER_KEYS = frozenset({CONTRACT_NUMBER_PLACEHOLDER})
AUTO_PLACEHOLDER_KEYS = frozenset({PREPAYMENT_PLACEHOLDER, FINAL_PAYMENT_PLACEHOLDER})

BLANK = "________________"

_HTML_TAG_RE = re.compile(
    r"</?(?:p|div|br|h[1-6]|strong|b|em|i|u|s|strike|span|font|table|thead|tbody|tfoot|"
    r"tr|td|th|ul|ol|li|blockquote|hr|sub|sup|pre|colgroup|col)\b[^>]*>",
    re.IGNORECASE,
)
_SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b.*?</\1\s*>", re.IGNORECASE | re.DOTALL)
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_BLOCK_CLOSE_RE = re.compile(
    r"</(?:p|div|h[1-6]|li|tr|td|th|table|ul|ol|blockquote|pre)>", re.IGNORECASE
)
_TAG_RE = re.compile(r"<[^>]+>")

_ALLOWED_TAGS = {
    "p", "div", "br", "hr", "h1", "h2", "h3", "h4", "h5", "h6",
    "strong", "b", "em", "i", "u", "s", "strike", "del", "span", "font", "mark",
    "table", "thead", "tbody", "tfoot", "tr", "td", "th", "colgroup", "col",
    "ul", "ol", "li", "blockquote", "pre", "sub", "sup",
}
_DROP_WITH_CONTENT = {"script", "style", "iframe", "object", "embed", "noscript", "template"}
_VOID_TAGS = {"br", "hr", "col"}
_ALLOWED_STYLES = {
    "font-family", "font-size", "font-weight", "font-style", "text-decoration",
    "text-align", "text-indent", "line-height", "margin-left", "margin-right",
    "margin-top", "margin-bottom", "color", "background-color", "width",
    "vertical-align", "border", "border-collapse", "padding", "letter-spacing",
}


def is_html(content: str | None) -> bool:
    return bool(content and _HTML_TAG_RE.search(content))


def html_to_text(content: str) -> str:
    text = _SCRIPT_STYLE_RE.sub("", content or "")
    text = _BR_RE.sub("\n", text)
    text = _BLOCK_CLOSE_RE.sub("\n", text)
    text = _TAG_RE.sub("", text)
    text = html_module.unescape(text).replace("\xa0", " ")
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return "\n".join(lines).strip("\n")


def document_text(content: str | None) -> str:
    if not content:
        return ""
    return html_to_text(content) if is_html(content) else content.replace("\r", "")


def has_text(content: str | None) -> bool:
    return bool(document_text(content).strip())


def extract_placeholders(content: str | None) -> list[str]:
    text = document_text(content)
    found: list[str] = []
    for match in PLACEHOLDER_RE.finditer(text):
        key = match.group(1)
        if key not in found:
            found.append(key)
    return found


def plain_text_to_html(text: str | None) -> str:
    lines = (text or "").replace("\r", "").split("\n")
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    parts: list[str] = []
    for line in lines:
        if line.strip():
            parts.append(f"<p>{html_module.escape(line.rstrip())}</p>")
        else:
            parts.append("<p></p>")
    return "".join(parts) or "<p></p>"


def _clean_style(raw: str | None) -> str:
    declarations: list[str] = []
    for chunk in (raw or "").split(";"):
        if ":" not in chunk:
            continue
        name, _, value = chunk.partition(":")
        name = name.strip().lower()
        value = value.strip()
        if name not in _ALLOWED_STYLES or not value:
            continue
        lowered = value.lower()
        if any(blocked in lowered for blocked in ("url(", "expression", "javascript:", "<", ">", "@import")):
            continue
        declarations.append(f"{name}: {value}")
    return "; ".join(declarations)


class _Sanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.stack: list[str] = []
        self.drop_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if self.drop_depth:
            if tag not in _VOID_TAGS:
                self.drop_depth += 1
            return
        if tag in _DROP_WITH_CONTENT:
            self.drop_depth = 1
            return
        if tag not in _ALLOWED_TAGS:
            return

        clean_attrs: list[str] = []
        for name, value in attrs:
            name = name.lower()
            value = value or ""
            if name == "style":
                style = _clean_style(value)
                if style:
                    clean_attrs.append(f'style="{html_module.escape(style, quote=True)}"')
            elif name in {"colspan", "rowspan", "start"}:
                digits = re.sub(r"\D", "", value)
                if digits and 1 <= int(digits) <= 64:
                    clean_attrs.append(f'{name}="{int(digits)}"')
        suffix = (" " + " ".join(clean_attrs)) if clean_attrs else ""
        self.parts.append(f"<{tag}{suffix}>")
        if tag not in _VOID_TAGS:
            self.stack.append(tag)

    def handle_startendtag(self, tag: str, attrs) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() not in _VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self.drop_depth:
            self.drop_depth = max(0, self.drop_depth - 1)
            return
        if tag not in self.stack:
            return
        while self.stack:
            current = self.stack.pop()
            self.parts.append(f"</{current}>")
            if current == tag:
                break

    def handle_data(self, data: str) -> None:
        if self.drop_depth:
            return
        self.parts.append(html_module.escape(data))

    def close(self) -> None:
        super().close()
        while self.stack:
            self.parts.append(f"</{self.stack.pop()}>")


def sanitize_html(content: str | None) -> str:
    if not content:
        return ""
    parser = _Sanitizer()
    parser.feed(content)
    parser.close()
    cleaned = "".join(parser.parts).strip()
    return cleaned or ""


def normalize_content(content: str | None) -> str:
    if is_html(content):
        return sanitize_html(content)
    return plain_text_to_html(content)


def next_version(version: str | None) -> str:
    match = re.fullmatch(r"[Vv](\d+)\.(\d+)", (version or "").strip())
    if not match:
        return "V1.0"
    return f"V{int(match.group(1))}.{int(match.group(2)) + 1}"


def initial_version() -> str:
    return "V1.0"


def _guess_field_type(key: str) -> str:
    if "大写" in key:
        return "text"
    if any(word in key for word in ("金额", "总额", "价款", "费用", "价格", "报酬", "租金", "工资")):
        return "currency"
    if any(word in key for word in ("日期", "时间", "签订日", "签署日", "生效日", "到期日")):
        return "date"
    if any(word in key for word in ("数量", "天数", "年限", "期限", "人数", "比例", "百分比", "次数")):
        return "number"
    if any(word in key for word in ("内容", "说明", "事项", "范围", "描述", "要求", "条款", "义务", "责任", "备注")):
        return "textarea"
    return "text"


def fields_from_placeholders(keys: list[str]) -> list[dict]:
    fields: list[dict] = []
    for key in keys:
        if key in SYSTEM_PLACEHOLDER_KEYS or key in AUTO_PLACEHOLDER_KEYS:
            continue
        optional = any(word in key for word in ("备注", "可选", "其他"))
        fields.append(
            {
                "key": key,
                "label": key,
                "type": _guess_field_type(key),
                "required": not optional,
                "hint": "",
                "placeholder": "",
                "options": [],
            }
        )
    return fields


def guess_template_name(filename: str, content: str, fallback: str = "导入模板") -> str:
    for line in document_text(content).splitlines():
        candidate = line.strip()
        if not candidate or len(candidate) > 40:
            continue
        if any(word in candidate for word in ("合同", "协议", "证明", "承诺", "函", "书")):
            return candidate
    stem = re.sub(r"\.(docx|pdf)$", "", filename or "", flags=re.IGNORECASE).strip()
    return stem or fallback
