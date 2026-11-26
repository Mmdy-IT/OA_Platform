from __future__ import annotations

import os
import re
import threading
import time

import pymysql
from pymysql.cursors import DictCursor


class PartyDatabaseError(RuntimeError):
    """Raised when the external party directory cannot be queried."""


PARTY_COLUMNS = (
    "entity_name",
    "unified_social_credit_code",
    "account_name",
    "bank_name",
    "bank_branch_code",
    "tax_number",
    "contact_address",
    "contact_phone",
)

_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_]+$")
_CACHE_TTL_SECONDS = float(os.getenv("OA_PARTY_CACHE_SECONDS", "120"))
_CACHE_LOCK = threading.Lock()
_CACHE_ITEMS: list[dict[str, str]] = []
_CACHE_EXPIRES_AT = 0.0


def _identifier(value: str, label: str) -> str:
    if not _IDENTIFIER_RE.fullmatch(value):
        raise PartyDatabaseError(f"{label}配置不正确")
    return f"`{value}`"


def connection_config() -> dict[str, object]:
    return {
        "host": os.getenv("OA_PARTY_DB_HOST", "rm-bp1pk2rf9z16l9x7aio.mysql.rds.aliyuncs.com"),
        "port": int(os.getenv("OA_PARTY_DB_PORT", "3306")),
        "user": os.getenv("OA_PARTY_DB_USER", "mmdy_rpa"),
        "password": os.getenv("OA_PARTY_DB_PASSWORD", "MMDY@rpa"),
        "database": os.getenv("OA_PARTY_DB_NAME", "mmdy_db"),
        "charset": "utf8mb4",
        "cursorclass": DictCursor,
        "connect_timeout": 5,
        "read_timeout": 8,
        "write_timeout": 8,
        "autocommit": True,
    }


def _fetch_parties() -> list[dict[str, str]]:
    database = os.getenv("OA_PARTY_DB_NAME", "mmdy_db")
    table = os.getenv("OA_PARTY_DB_TABLE", "mmdy_party_info")
    full_table = f"{_identifier(database, '主体库数据库')}.{_identifier(table, '主体库数据表')}"
    columns = ", ".join(f"`{column}`" for column in PARTY_COLUMNS)
    sql = f"SELECT {columns} FROM {full_table} ORDER BY `entity_name` ASC LIMIT 1000"
    connection = None
    try:
        connection = pymysql.connect(**connection_config())
        with connection.cursor() as cursor:
            cursor.execute(sql)
            rows = cursor.fetchall()
    except pymysql.MySQLError as exc:
        raise PartyDatabaseError("主体信息库连接失败") from exc
    finally:
        if connection is not None:
            connection.close()

    items: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        name = str(row.get("entity_name") or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        items.append({column: str(row.get(column) or "").strip() for column in PARTY_COLUMNS})
    return items


def list_parties(force_refresh: bool = False) -> list[dict[str, str]]:
    global _CACHE_EXPIRES_AT, _CACHE_ITEMS
    now = time.monotonic()
    with _CACHE_LOCK:
        if not force_refresh and now < _CACHE_EXPIRES_AT:
            return list(_CACHE_ITEMS)
        try:
            items = _fetch_parties()
        except PartyDatabaseError:
            if _CACHE_ITEMS:
                return list(_CACHE_ITEMS)
            raise
        _CACHE_ITEMS = items
        _CACHE_EXPIRES_AT = now + _CACHE_TTL_SECONDS
        return list(items)


def clear_cache() -> None:
    global _CACHE_EXPIRES_AT, _CACHE_ITEMS
    with _CACHE_LOCK:
        _CACHE_ITEMS = []
        _CACHE_EXPIRES_AT = 0.0
