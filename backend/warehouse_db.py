from __future__ import annotations

import os
import re
import threading
import time

import pymysql

from .party_db import connection_config


class WarehouseDatabaseError(RuntimeError):
    """Raised when the external warehouse directory cannot be queried."""


WAREHOUSE_COLUMNS = ("warehouse_short_name", "warehouse_address")

_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_]+$")
_CACHE_TTL_SECONDS = float(os.getenv("OA_WAREHOUSE_CACHE_SECONDS", "120"))
_CACHE_LOCK = threading.Lock()
_CACHE_ITEMS: list[dict[str, str]] = []
_CACHE_EXPIRES_AT = 0.0


def _identifier(value: str, label: str) -> str:
    if not _IDENTIFIER_RE.fullmatch(value):
        raise WarehouseDatabaseError(f"{label}配置不正确")
    return f"`{value}`"


def _fetch_warehouses() -> list[dict[str, str]]:
    database = os.getenv("OA_WAREHOUSE_DB_NAME", os.getenv("OA_PARTY_DB_NAME", "mmdy_db"))
    table = os.getenv("OA_WAREHOUSE_DB_TABLE", "mmdy_warehouse_info")
    full_table = f"{_identifier(database, '仓库数据库')}.{_identifier(table, '仓库数据表')}"
    columns = ", ".join(f"`{column}`" for column in WAREHOUSE_COLUMNS)
    sql = (
        f"SELECT {columns} FROM {full_table} "
        "ORDER BY `warehouse_short_name` ASC LIMIT 1000"
    )
    connection = None
    try:
        connection = pymysql.connect(**connection_config())
        with connection.cursor() as cursor:
            cursor.execute(sql)
            rows = cursor.fetchall()
    except pymysql.MySQLError as exc:
        raise WarehouseDatabaseError("仓库信息库连接失败") from exc
    finally:
        if connection is not None:
            connection.close()

    items: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        short_name = str(row.get("warehouse_short_name") or "").strip()
        if not short_name or short_name in seen:
            continue
        seen.add(short_name)
        items.append(
            {column: str(row.get(column) or "").strip() for column in WAREHOUSE_COLUMNS}
        )
    return items


def list_warehouses(force_refresh: bool = False) -> list[dict[str, str]]:
    global _CACHE_EXPIRES_AT, _CACHE_ITEMS
    now = time.monotonic()
    with _CACHE_LOCK:
        if not force_refresh and now < _CACHE_EXPIRES_AT:
            return list(_CACHE_ITEMS)
        try:
            items = _fetch_warehouses()
        except WarehouseDatabaseError:
            if _CACHE_ITEMS:
                return list(_CACHE_ITEMS)
            raise
        _CACHE_ITEMS = items
        _CACHE_EXPIRES_AT = now + _CACHE_TTL_SECONDS
        return list(items)


def resolve_warehouse_values(
    values: dict[str, str], fields: list[dict] | None
) -> dict[str, str]:
    picker_keys: list[str] = []
    for field in fields or []:
        key = str(field.get("key") or "")
        if not key:
            continue
        auto_fill = field.get("auto_fill")
        text = f"{key} {field.get('label') or ''}"
        is_picker = auto_fill == "warehouse_short_name" or (
            auto_fill in (None, "warehouse_address")
            and bool(re.search(r"仓库简称|仓库名称", text))
        )
        if is_picker:
            picker_keys.append(key)
    if not picker_keys:
        return values
    try:
        items = list_warehouses()
    except WarehouseDatabaseError:
        return values
    addresses = {
        item["warehouse_short_name"]: item["warehouse_address"]
        for item in items
        if item["warehouse_short_name"] and item["warehouse_address"]
    }
    resolved = dict(values)
    changed = False
    for key in picker_keys:
        raw = str(resolved.get(key) or "").strip()
        address = addresses.get(raw)
        if address and address != raw:
            resolved[key] = address
            changed = True
    return resolved if changed else values


def clear_cache() -> None:
    global _CACHE_EXPIRES_AT, _CACHE_ITEMS
    with _CACHE_LOCK:
        _CACHE_ITEMS = []
        _CACHE_EXPIRES_AT = 0.0
