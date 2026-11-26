from __future__ import annotations

from copy import deepcopy

from lxml import etree, html


MAX_TABLES = 40
MAX_BODY_ROWS = 200


def _parse_fragment(content: str):
    try:
        return html.fragment_fromstring(content, create_parent="div")
    except (etree.ParserError, ValueError):
        return None


def _serialize_fragment(root) -> str:
    parts: list[str] = []
    if root.text:
        parts.append(root.text)
    for child in root:
        parts.append(html.tostring(child, encoding="unicode", method="html"))
    return "".join(parts)


def _direct_rows(table) -> list:
    return table.xpath("./thead/tr | ./tbody/tr | ./tfoot/tr | ./tr")


def _is_header_row(row) -> bool:
    parent = row.getparent()
    if parent is not None and str(parent.tag).lower() == "thead":
        return True
    cells = row.xpath("./td | ./th")
    return bool(cells) and all(str(cell.tag).lower() == "th" for cell in cells)


def _table_models(root) -> list[dict]:
    models: list[dict] = []
    for index, table in enumerate(root.xpath(".//table")):
        rows = _direct_rows(table)
        header_count = 0
        while header_count < len(rows) and _is_header_row(rows[header_count]):
            header_count += 1
        body_rows = rows[header_count:]
        header_rows = rows[:header_count]
        column_count = max(
            [len(row.xpath("./td | ./th")) for row in body_rows]
            + [len(row.xpath("./td | ./th")) for row in header_rows]
            + [1]
        )
        models.append(
            {
                "index": index,
                "table": table,
                "header_count": header_count,
                "body_rows": body_rows,
                "column_count": column_count,
            }
        )
    return models


def _row_dict(item) -> dict | None:
    if hasattr(item, "model_dump"):
        item = item.model_dump()
    return item if isinstance(item, dict) else None


def _new_row(item: dict, table_index: int, position: int, column_count: int, seen_ids: set[str]) -> dict:
    cells = item.get("cells") if isinstance(item.get("cells"), list) else []
    normalized_cells = [str(value or "")[:2000] for value in cells[:column_count]]
    normalized_cells.extend([""] * (column_count - len(normalized_cells)))
    row_id = str(item.get("id") or "").strip()[:80] or f"table-{table_index}-row-{position}"
    while row_id in seen_ids:
        row_id = f"{row_id[:72]}-{position}-{len(seen_ids)}"
    seen_ids.add(row_id)
    return {"id": row_id, "cells": normalized_cells}


def _normalize_rows(
    rows,
    body_count: int,
    column_count: int,
    table_index: int,
) -> list[int | dict]:
    chosen: list[int | dict] = []
    seen: set[int] = set()
    seen_ids: set[str] = set()
    for position, item in enumerate(list(rows)[:MAX_BODY_ROWS]):
        if item is None:
            chosen.append(_new_row({}, table_index, position, column_count, seen_ids))
            continue
        row = _row_dict(item)
        if row is not None:
            chosen.append(_new_row(row, table_index, position, column_count, seen_ids))
            continue
        if isinstance(item, bool) or not isinstance(item, int):
            continue
        if 0 <= item < body_count and item not in seen:
            chosen.append(item)
            seen.add(item)
    return chosen or [_new_row({}, table_index, 0, column_count, seen_ids)]


def normalize_table_adjustments(content: str, adjustments: dict | None) -> dict[str, list[int | dict]]:
    """Keep only row selections that refer to real body rows in this template."""
    if not adjustments or not isinstance(adjustments, dict):
        return {}
    root = _parse_fragment(content)
    if root is None:
        return {}
    models = _table_models(root)
    normalized: dict[str, list[int | dict]] = {}
    for raw_key, raw_rows in list(adjustments.items())[:MAX_TABLES]:
        key = str(raw_key).strip()
        if not key.isdigit() or not isinstance(raw_rows, list):
            continue
        index = int(key)
        if index < 0 or index >= len(models):
            continue
        body_count = len(models[index]["body_rows"])
        if not body_count:
            continue
        rows = _normalize_rows(
            raw_rows,
            body_count,
            int(models[index]["column_count"]),
            index,
        )
        if rows == list(range(body_count)):
            continue
        normalized[key] = rows
    return normalized


def apply_table_adjustments(content: str, adjustments: dict | None) -> str:
    """Rebuild contract table bodies from the template snapshot and saved row selections."""
    if not content or not adjustments:
        return content
    root = _parse_fragment(content)
    if root is None:
        return content
    models = _table_models(root)
    normalized = normalize_table_adjustments(content, adjustments)
    if not normalized:
        return content

    for raw_key, chosen in normalized.items():
        model = models[int(raw_key)]
        table = model["table"]
        if root not in table.iterancestors():
            continue
        source_rows = [deepcopy(row) for row in model["body_rows"]]
        for row in model["body_rows"]:
            parent = row.getparent()
            if parent is not None:
                parent.remove(row)

        targets = table.xpath("./tbody")
        if targets:
            target = targets[0]
        else:
            target = html.Element("tbody")
            head = table.find("thead")
            if head is not None:
                head.addnext(target)
            else:
                table.insert(0, target)

        for item in chosen:
            if isinstance(item, dict):
                row = html.Element("tr")
                cells = item.get("cells") if isinstance(item.get("cells"), list) else []
                for column in range(max(1, model["column_count"])):
                    value = str(cells[column] if column < len(cells) else "")
                    cell = html.Element("td")
                    lines = value.splitlines() or [""]
                    cell.text = lines[0] or "\u00a0"
                    for line in lines[1:]:
                        br = html.Element("br")
                        br.tail = line or "\u00a0"
                        cell.append(br)
                    row.append(cell)
                target.append(row)
            else:
                target.append(source_rows[item])

    return _serialize_fragment(root)
