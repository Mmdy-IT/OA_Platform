from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from lxml import etree, html

from .richtext import FINAL_PAYMENT_PLACEHOLDER, PREPAYMENT_PLACEHOLDER
from .tables import apply_table_adjustments


TOTAL_AMOUNT_FIELD_KEY = "总额"
TOTAL_AMOUNT_UPPER_FIELD_KEY = "大写总额"
TOTAL_AMOUNT_COLUMN_LABEL = "总额（元）"
PREPAYMENT_FIELD_KEY = PREPAYMENT_PLACEHOLDER
FINAL_PAYMENT_FIELD_KEY = FINAL_PAYMENT_PLACEHOLDER
PAYMENT_FIELD_KEYS = frozenset({PREPAYMENT_FIELD_KEY, FINAL_PAYMENT_FIELD_KEY})
_PAYMENT_BASE_FIELD_KEYS = (
    "总额",
    "总费用",
    "合同金额",
    "合同金额（元）",
    "合同总价",
    "价税合计",
    "服务费",
    "金额",
    "金额（元）",
)
_PAYMENT_BASE_LABEL_HINTS = (
    "总额",
    "总费用",
    "合同金额",
    "合同总价",
    "价税合计",
    "服务费",
    "金额",
)

_CN_DIGITS = "零壹贰叁肆伍陆柒捌玖"
_CN_SMALL_UNITS = ("", "拾", "佰", "仟")
_CN_BIG_UNITS = ("", "万", "亿", "万亿")
_SUMMARY_PREFIXES = ("合计", "总计", "小计")
_NON_DATA_PREFIXES = ("合计", "总计", "小计", "备注")
_SUMMARY_AMOUNT_RE = re.compile(r"[¥￥]\s*[\d,，]*(?:\.\d+)?\s*元")
_SUMMARY_UPPER_RE = re.compile(r"(大写[：:]\s*(?:人民币)?\s*)[^）)]*")
_HEADER_HINTS = (
    "序号", "名称", "规格", "型号", "数量", "单价", "总额", "金额",
    "单位", "备注", "项目", "内容", "日期", "税率",
)


def _normalize_label(value: str | None) -> str:
    return re.sub(r"[\s\u00a0]+", "", value or "")


def _serialize_fragment(root) -> str:
    parts: list[str] = []
    if root.text:
        parts.append(root.text)
    for child in root:
        parts.append(html.tostring(child, encoding="unicode", method="html"))
    return "".join(parts)


def _uppercase_base_key(keys: set[str], key: str) -> str | None:
    candidates: list[str] = []
    if key.startswith("大写") and len(key) > 2:
        candidates.append(key[2:])
    if key.endswith("大写") and len(key) > 2:
        candidates.append(key[:-2])
    for candidate in candidates:
        if candidate in keys:
            return candidate
    return None


def _parse_amount(value: str | None) -> Decimal | None:
    cleaned = re.sub(r"[\s\u00a0,，¥￥]", "", value or "")
    cleaned = re.sub(r"元$", "", cleaned)
    if not re.fullmatch(r"[+-]?\d+(?:\.\d+)?", cleaned):
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def _logical_cells(row) -> list[tuple[object, int]]:
    cells: list[tuple[object, int]] = []
    column = 0
    for cell in row.xpath("./td | ./th"):
        cells.append((cell, column))
        try:
            colspan = max(1, int(cell.get("colspan") or 1))
        except ValueError:
            colspan = 1
        column += colspan
    return cells


def _is_summary_row(row) -> bool:
    return any(
        _normalize_label(cell.text_content()).startswith(_SUMMARY_PREFIXES)
        for cell, _ in _logical_cells(row)
    )


def _column_role(row, keyword: str) -> int | None:
    for cell, column in _logical_cells(row):
        if keyword in _normalize_label(cell.text_content()):
            return column
    return None


def _label_row(rows):
    for row in rows:
        cells = _logical_cells(row)
        if not cells:
            continue
        labels = [_normalize_label(cell.text_content()) for cell, _ in cells]
        if len(labels) >= 2 and all(labels) and any(
            hint in label for label in labels for hint in _HEADER_HINTS
        ):
            return row
    return None


def _table_roles(rows):
    label_row = _label_row(rows)
    if label_row is None:
        return None
    return {
        "label_row": label_row,
        "sequence": _column_role(label_row, "序号"),
        "quantity": _column_role(label_row, "数量"),
        "unit_price": _column_role(label_row, "单价"),
        "total": _column_role(label_row, "总额"),
    }


def _is_header_row(row) -> bool:
    parent = row.getparent()
    if parent is not None and str(parent.tag).lower() == "thead":
        return True
    cells = row.xpath("./td | ./th")
    return bool(cells) and all(str(cell.tag).lower() == "th" for cell in cells)


def _body_rows(table) -> list:
    rows = table.xpath("./thead/tr | ./tbody/tr | ./tfoot/tr | ./tr")
    header_count = 0
    while header_count < len(rows) and _is_header_row(rows[header_count]):
        header_count += 1
    return rows[header_count:]


def _data_row_flags(body_rows: list, label_row) -> list[bool]:
    flags: list[bool] = []
    for row in body_rows:
        if row is label_row:
            flags.append(False)
            continue
        text = _normalize_label(row.text_content())
        if not text:
            flags.append(False)
            continue
        cells = _logical_cells(row)
        first_text = _normalize_label(cells[0][0].text_content()) if cells else ""
        flags.append(not (first_text or text).startswith(_NON_DATA_PREFIXES))
    return flags


def apply_table_row_totals(content: str, adjustments: dict | None) -> dict:
    if not adjustments or not isinstance(adjustments, dict):
        return adjustments or {}
    try:
        root = html.fragment_fromstring(content or "", create_parent="div")
    except (etree.ParserError, ValueError):
        return adjustments

    roles_by_table: dict[int, tuple[int, int, int]] = {}
    for index, table in enumerate(root.xpath(".//table")):
        rows = table.xpath("./thead/tr | ./tbody/tr | ./tfoot/tr | ./tr")
        roles = _table_roles(rows)
        if (
            roles is not None
            and roles["quantity"] is not None
            and roles["unit_price"] is not None
            and roles["total"] is not None
        ):
            roles_by_table[index] = (
                roles["quantity"],
                roles["unit_price"],
                roles["total"],
            )
    if not roles_by_table:
        return adjustments

    result: dict = {}
    for raw_key, rows in adjustments.items():
        if not isinstance(rows, list):
            result[raw_key] = rows
            continue
        key = str(raw_key).strip()
        roles = roles_by_table.get(int(key)) if key.isdigit() else None
        if roles is None:
            result[raw_key] = rows
            continue
        quantity_column, unit_price_column, total_column = roles
        normalized_rows: list = []
        for item in rows:
            if not isinstance(item, dict):
                normalized_rows.append(item)
                continue
            cells = list(item.get("cells") or [])
            if len(cells) <= max(quantity_column, unit_price_column, total_column):
                normalized_rows.append(item)
                continue
            quantity = _parse_amount(str(cells[quantity_column] or ""))
            unit_price = _parse_amount(str(cells[unit_price_column] or ""))
            if quantity is None or unit_price is None:
                cells[total_column] = ""
            else:
                total = (quantity * unit_price).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                cells[total_column] = f"{total:.2f}"
            normalized_rows.append({**item, "cells": cells})
        result[raw_key] = normalized_rows
    return result


def apply_table_row_sequences(content: str, adjustments: dict | None) -> dict:
    if not adjustments or not isinstance(adjustments, dict):
        return adjustments or {}
    try:
        root = html.fragment_fromstring(content or "", create_parent="div")
    except (etree.ParserError, ValueError):
        return adjustments

    sequences_by_table: dict[int, tuple[int, list[bool]]] = {}
    for index, table in enumerate(root.xpath(".//table")):
        rows = table.xpath("./thead/tr | ./tbody/tr | ./tfoot/tr | ./tr")
        roles = _table_roles(rows)
        if roles is None or roles["sequence"] is None:
            continue
        body_rows = _body_rows(table)
        sequences_by_table[index] = (
            roles["sequence"],
            _data_row_flags(body_rows, roles["label_row"]),
        )
    if not sequences_by_table:
        return adjustments

    result: dict = {}
    for raw_key, rows in adjustments.items():
        if not isinstance(rows, list):
            result[raw_key] = rows
            continue
        key = str(raw_key).strip()
        config = sequences_by_table.get(int(key)) if key.isdigit() else None
        if config is None:
            result[raw_key] = rows
            continue
        sequence_column, data_flags = config
        sequence = 0
        normalized_rows: list = []
        for item in rows:
            if isinstance(item, dict):
                sequence += 1
                cells = list(item.get("cells") or [])
                if len(cells) > sequence_column:
                    cells[sequence_column] = str(sequence)
                normalized_rows.append({**item, "cells": cells})
                continue
            if (
                isinstance(item, int)
                and not isinstance(item, bool)
                and 0 <= item < len(data_flags)
                and data_flags[item]
            ):
                sequence += 1
            normalized_rows.append(item)
        result[raw_key] = normalized_rows
    return result


def apply_table_row_auto_values(content: str, adjustments: dict | None) -> dict:
    return apply_table_row_sequences(
        content, apply_table_row_totals(content, adjustments)
    )


def sum_contract_table_total(
    content: str,
    adjustments: dict | None,
    column_label: str = TOTAL_AMOUNT_COLUMN_LABEL,
) -> Decimal | None:
    adjusted = apply_table_adjustments(content or "", adjustments)
    try:
        root = html.fragment_fromstring(adjusted, create_parent="div")
    except (etree.ParserError, ValueError):
        return None

    total = Decimal("0")
    has_column = False
    wanted = _normalize_label(column_label)
    for table in root.xpath(".//table"):
        rows = table.xpath("./thead/tr | ./tbody/tr | ./tfoot/tr | ./tr")
        header_index = -1
        target_column = -1
        for row_index, row in enumerate(rows):
            for cell, column in _logical_cells(row):
                if _normalize_label(cell.text_content()) == wanted:
                    header_index = row_index
                    target_column = column
                    has_column = True
                    break
            if header_index >= 0:
                break
        if header_index < 0 or target_column < 0:
            continue

        for row in rows[header_index + 1 :]:
            if _is_summary_row(row):
                continue
            for cell, column in _logical_cells(row):
                try:
                    colspan = max(1, int(cell.get("colspan") or 1))
                except ValueError:
                    colspan = 1
                if column <= target_column < column + colspan:
                    amount = _parse_amount(cell.text_content())
                    if amount is not None:
                        total += amount
                    break

    return total if has_column else None


def _four_digits_to_chinese(value: int) -> str:
    digits = [
        (value // 1000) % 10,
        (value // 100) % 10,
        (value // 10) % 10,
        value % 10,
    ]
    parts: list[str] = []
    zero_pending = False
    for index, digit in enumerate(digits):
        if digit == 0:
            if parts:
                zero_pending = True
            continue
        if zero_pending:
            parts.append("零")
            zero_pending = False
        parts.append(_CN_DIGITS[digit] + _CN_SMALL_UNITS[3 - index])
    return "".join(parts)


def _integer_to_chinese(value: int) -> str:
    if value == 0:
        return "零"
    groups: list[int] = []
    remaining = value
    while remaining > 0:
        groups.append(remaining % 10000)
        remaining //= 10000

    parts: list[str] = []
    for index in range(len(groups) - 1, -1, -1):
        group = groups[index]
        if group == 0:
            if parts and any(item > 0 for item in groups[:index]) and parts[-1] != "零":
                parts.append("零")
            continue
        if parts and group < 1000 and parts[-1] != "零":
            parts.append("零")
        parts.append(_four_digits_to_chinese(group))
        if index > 0:
            parts.append(_CN_BIG_UNITS[index] if index < len(_CN_BIG_UNITS) else "")
    return re.sub(r"零+", "零", "".join(parts)).rstrip("零") or "零"


def _amount_parts(
    value: str | int | float | Decimal,
) -> tuple[bool, int, int, int] | None:
    cleaned = re.sub(r"[\s\u00a0,，¥￥]", "", str(value or ""))
    cleaned = re.sub(r"元$", "", cleaned)
    try:
        amount = Decimal(cleaned)
    except InvalidOperation:
        return None
    negative = amount < 0
    amount = abs(amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    cents = int(amount * 100)
    integer, remainder = divmod(cents, 100)
    jiao, fen = divmod(remainder, 10)
    return negative, integer, jiao, fen


def amount_to_chinese_upper(value: str | int | float | Decimal) -> str:
    parts = _amount_parts(value)
    if parts is None:
        return ""
    negative, integer, jiao, fen = parts

    text = f"{_integer_to_chinese(integer)}元"
    if jiao == 0 and fen == 0:
        text += "整"
    else:
        if jiao:
            text += f"{_CN_DIGITS[jiao]}角"
        elif fen:
            text += "零"
        if fen:
            text += f"{_CN_DIGITS[fen]}分"
    return f"{'负' if negative else ''}{text}"


def amount_to_chinese_upper_short(value: str | int | float | Decimal) -> str:
    parts = _amount_parts(value)
    if parts is None:
        return ""
    negative, integer, jiao, fen = parts
    integer_text = _integer_to_chinese(integer)
    if jiao == 0 and fen == 0:
        text = integer_text
    else:
        text = f"{integer_text}元" if integer else ""
        if jiao:
            text += f"{_CN_DIGITS[jiao]}角"
        elif fen and integer:
            text += "零"
        if fen:
            text += f"{_CN_DIGITS[fen]}分"
    return f"{'负' if negative else ''}{text}"


def _replace_cell_text(cell, pattern: re.Pattern[str], replacer) -> bool:
    changed = False
    for node in cell.iter():
        if node.text and pattern.search(node.text):
            node.text = pattern.sub(replacer, node.text)
            changed = True
        if node is not cell and node.tail and pattern.search(node.tail):
            node.tail = pattern.sub(replacer, node.tail)
            changed = True
    return changed


def apply_table_summary_totals(content: str) -> str:
    if not content or "<table" not in content.lower():
        return content
    try:
        root = html.fragment_fromstring(content, create_parent="div")
    except (etree.ParserError, ValueError):
        return content

    changed = False
    wanted = _normalize_label(TOTAL_AMOUNT_COLUMN_LABEL)
    for table in root.xpath(".//table"):
        rows = table.xpath("./thead/tr | ./tbody/tr | ./tfoot/tr | ./tr")
        header_index = -1
        target_column = -1
        for row_index, row in enumerate(rows):
            for cell, column in _logical_cells(row):
                if _normalize_label(cell.text_content()) == wanted:
                    header_index = row_index
                    target_column = column
                    break
            if header_index >= 0:
                break
        if header_index < 0 or target_column < 0:
            continue

        total = Decimal("0")
        has_data_row = False
        summary_row = None
        for row in rows[header_index + 1 :]:
            if _is_summary_row(row):
                if summary_row is None:
                    summary_row = row
                continue
            cells = _logical_cells(row)
            first_text = _normalize_label(cells[0][0].text_content()) if cells else ""
            if first_text.startswith(_NON_DATA_PREFIXES):
                continue
            has_data_row = True
            for cell, column in cells:
                try:
                    colspan = max(1, int(cell.get("colspan") or 1))
                except ValueError:
                    colspan = 1
                if column <= target_column < column + colspan:
                    amount = _parse_amount(cell.text_content())
                    if amount is not None:
                        total += amount
                    break
        if not has_data_row or summary_row is None:
            continue

        candidates = [
            cell
            for cell, _ in _logical_cells(summary_row)
            if not _normalize_label(cell.text_content()).startswith(_SUMMARY_PREFIXES)
        ]
        if not candidates:
            continue
        amount_cell = next(
            (
                cell
                for cell in candidates
                if re.search(r"[¥￥]|元", cell.text_content() or "")
            ),
            candidates[-1],
        )
        upper_cell = next(
            (cell for cell in candidates if "大写" in (cell.text_content() or "")),
            None,
        )
        raw_total = f"{total.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):.2f}"
        total_text = f"{total:,.2f}"
        upper_text = amount_to_chinese_upper_short(raw_total)

        same_cell = upper_cell is amount_cell
        amount_changed = _replace_cell_text(
            amount_cell, _SUMMARY_AMOUNT_RE, f"¥ {total_text} 元"
        )
        upper_changed = (
            _replace_cell_text(
                upper_cell,
                _SUMMARY_UPPER_RE,
                lambda match: f"{match.group(1)}{upper_text}",
            )
            if upper_cell is not None
            else False
        )

        if same_cell:
            if not amount_changed or not upper_changed:
                for child in list(amount_cell):
                    amount_cell.remove(child)
                amount_cell.text = f"¥ {total_text} 元（大写：人民币 {upper_text}）"
        else:
            if not amount_changed:
                for child in list(amount_cell):
                    amount_cell.remove(child)
                amount_cell.text = f"¥ {total_text} 元"
            if upper_cell is not None:
                if not upper_changed:
                    for child in list(upper_cell):
                        upper_cell.remove(child)
                    upper_cell.text = f"（大写：人民币 {upper_text}）"
            else:
                for child in list(amount_cell):
                    amount_cell.remove(child)
                amount_cell.text = f"¥ {total_text} 元（大写：人民币 {upper_text}）"
        changed = True

    return _serialize_fragment(root) if changed else content


def _looks_like_payment_source(key: str, label: str) -> bool:
    normalized_key = key.strip()
    normalized_text = _normalize_label(label)
    if not normalized_key or normalized_key in PAYMENT_FIELD_KEYS:
        return False
    if "预付款" in normalized_key or "尾款" in normalized_key:
        return False
    if "预付款" in normalized_text or "尾款" in normalized_text:
        return False
    if "大写" in normalized_key or "大写" in normalized_text:
        return False
    return normalized_key in _PAYMENT_BASE_FIELD_KEYS or any(
        hint in normalized_text for hint in _PAYMENT_BASE_LABEL_HINTS
    )


def resolve_payment_base_amount(
    content: str,
    adjustments: dict | None,
    fields: list[dict],
    values: dict[str, str],
) -> Decimal | None:
    table_total = sum_contract_table_total(content, adjustments)
    if table_total is not None:
        return table_total
    for field in fields or []:
        key = str(field.get("key") or "").strip()
        label = str(field.get("label") or "")
        if not _looks_like_payment_source(key, label):
            continue
        amount = _parse_amount(values.get(key))
        if amount is not None:
            return amount
    for key in _PAYMENT_BASE_FIELD_KEYS:
        amount = _parse_amount(values.get(key))
        if amount is not None:
            return amount
    return None


def payment_upper_texts(base: Decimal) -> dict[str, str]:
    total = base.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    prepayment = (total * Decimal("0.3")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    final_payment = (total - prepayment).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    return {
        PREPAYMENT_FIELD_KEY: amount_to_chinese_upper(prepayment),
        FINAL_PAYMENT_FIELD_KEY: amount_to_chinese_upper(final_payment),
    }


def apply_auto_amounts(
    content: str,
    adjustments: dict | None,
    fields: list[dict],
    values: dict[str, str],
) -> dict[str, str]:
    keys = {str(field.get("key") or "") for field in fields or []}
    uppercase_sources: dict[str, str] = {}
    for key in keys:
        if key == TOTAL_AMOUNT_UPPER_FIELD_KEY:
            continue
        base_key = _uppercase_base_key(keys, key)
        if base_key:
            uppercase_sources[key] = base_key

    needs_table_total = (
        TOTAL_AMOUNT_FIELD_KEY in keys or TOTAL_AMOUNT_UPPER_FIELD_KEY in keys
    )
    payment_keys = keys & PAYMENT_FIELD_KEYS
    if not needs_table_total and not uppercase_sources and not payment_keys:
        return values

    result = dict(values)

    if needs_table_total:
        total = sum_contract_table_total(content, adjustments)
        if total is not None:
            total_text = f"{total.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):.2f}"
            if TOTAL_AMOUNT_FIELD_KEY in keys:
                result[TOTAL_AMOUNT_FIELD_KEY] = total_text
            if TOTAL_AMOUNT_UPPER_FIELD_KEY in keys:
                result[TOTAL_AMOUNT_UPPER_FIELD_KEY] = amount_to_chinese_upper(total_text)

    if payment_keys:
        payment_base = resolve_payment_base_amount(content, adjustments, fields, values)
        if payment_base is not None:
            for key, text in payment_upper_texts(payment_base).items():
                if key in payment_keys:
                    result[key] = text

    for upper_key, base_key in uppercase_sources.items():
        raw = result.get(base_key) or values.get(base_key) or ""
        result[upper_key] = (
            amount_to_chinese_upper_short(raw) if str(raw).strip() else ""
        )
    return result
