from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation


_CURRENCY_VALUE_RE = re.compile(r"\d+(?:\.\d{0,2})?")
_NUMBER_VALUE_RE = re.compile(r"[+-]?\d+(?:\.\d{0,6})?")
_DATE_VALUE_RE = re.compile(
    r"(\d{4})(?:-|/|\.|年)(\d{1,2})(?:-|/|\.|月)(\d{1,2})日?"
)
_NUMERIC_SEPARATORS_RE = re.compile(r"[\s\u00a0,，¥￥]")
_SYSTEM_AMOUNT_FIELD_KEYS = frozenset({"预付款", "尾款"})


def _field_message(field: dict, value: str) -> str:
    field_type = str(field.get("type") or "text")
    if field_type == "currency":
        compact = _NUMERIC_SEPARATORS_RE.sub("", value)
        if not _CURRENCY_VALUE_RE.fullmatch(compact):
            return "仅可填写数字金额，最多两位小数"
        try:
            amount = Decimal(compact)
        except InvalidOperation:
            return "金额格式不正确"
        if not amount.is_finite() or amount < 0:
            return "金额须为大于或等于 0 的数字"
        return ""

    if field_type == "number":
        compact = _NUMERIC_SEPARATORS_RE.sub("", value)
        if not _NUMBER_VALUE_RE.fullmatch(compact):
            return "仅可填写数字，最多六位小数"
        try:
            number = Decimal(compact)
        except InvalidOperation:
            return "数字格式不正确"
        return "" if number.is_finite() else "数字格式不正确"

    if field_type == "date":
        match = _DATE_VALUE_RE.fullmatch(value)
        if not match:
            return "请选择有效日期"
        try:
            date(*(int(part) for part in match.groups()))
        except ValueError:
            return "请选择有效日期"
        return ""

    if field_type == "select":
        options = field.get("options") or []
        return "" if value in options else "请从下拉选项中选择"

    return ""


def _uppercase_base_key(keys: set[str], key: str) -> str | None:
    candidates: list[str] = []
    if key.startswith("大写") and len(key) > 2:
        candidates.append(key[2:])
    if key.endswith("大写") and len(key) > 2:
        candidates.append(key[:-2])
    return next((candidate for candidate in candidates if candidate in keys), None)


def invalid_field_values(fields: list[dict], values: dict[str, str]) -> list[dict]:
    invalid: list[dict] = []
    keys = {str(field.get("key") or "") for field in fields}
    for field in fields:
        key = str(field.get("key") or "")
        if key in _SYSTEM_AMOUNT_FIELD_KEYS or _uppercase_base_key(keys, key):
            continue
        value = str(values.get(key) or "").strip()
        if not value:
            continue
        message = _field_message(field, value)
        if message:
            invalid.append(
                {
                    "key": key,
                    "label": str(field.get("label") or key),
                    "message": message,
                }
            )
    return invalid


def invalid_field_summary(items: list[dict]) -> str:
    details = "、".join(f"{item['label']}（{item['message']}）" for item in items)
    return f"以下空白项填写格式不正确：{details}"
