from __future__ import annotations

import os
import re
import threading
import time

import pymysql
from pymysql.cursors import DictCursor

from .config import get_database_name, get_database_settings, get_table_name


class PartyDatabaseError(RuntimeError):
    """Raised when the external party directory cannot be queried."""


class PartyConflictError(PartyDatabaseError):
    """Raised when a party with the same name already exists."""


PARTY_COLUMNS = (
    "party_type",
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
_SCHEMA_READY = False


def _identifier(value: str, label: str) -> str:
    if not _IDENTIFIER_RE.fullmatch(value):
        raise PartyDatabaseError(f"{label}配置不正确")
    return f"`{value}`"


def connection_config() -> dict[str, object]:
    database_settings = get_database_settings()
    return {
        **database_settings,
        "charset": "utf8mb4",
        "cursorclass": DictCursor,
        "connect_timeout": 5,
        "read_timeout": 8,
        "write_timeout": 8,
        "autocommit": True,
    }


def _ensure_schema(cursor, full_table: str) -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    cursor.execute(f"SHOW COLUMNS FROM {full_table}")
    columns = {str(row.get("Field") or "") for row in cursor.fetchall()}
    if "party_type" not in columns:
        cursor.execute(
            f"ALTER TABLE {full_table} "
            "ADD COLUMN `party_type` VARCHAR(10) NOT NULL DEFAULT '乙方' "
            "COMMENT '主体类型：甲方/乙方' AFTER `entity_name`"
        )
        cursor.execute(f"UPDATE {full_table} SET `party_type` = '甲方'")
    _SCHEMA_READY = True


def _fetch_parties() -> list[dict[str, str]]:
    database = get_database_name()
    table = get_table_name("party", "OA_PARTY_DB_TABLE", "mmdy_party_info")
    full_table = f"{_identifier(database, '主体库数据库')}.{_identifier(table, '主体库数据表')}"
    columns = ", ".join(f"`{column}`" for column in PARTY_COLUMNS)
    sql = f"SELECT {columns} FROM {full_table} ORDER BY `entity_name` ASC LIMIT 1000"
    connection = None
    try:
        connection = pymysql.connect(**connection_config())
        with connection.cursor() as cursor:
            _ensure_schema(cursor, full_table)
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


def list_parties(
    force_refresh: bool = False,
    query: str = "",
    party_type: str = "",
) -> list[dict[str, str]]:
    global _CACHE_EXPIRES_AT, _CACHE_ITEMS
    now = time.monotonic()
    with _CACHE_LOCK:
        if not force_refresh and now < _CACHE_EXPIRES_AT:
            items = list(_CACHE_ITEMS)
            keyword = query.strip().lower()
            return [
                item
                for item in items
                if (not party_type or item.get("party_type") == party_type)
                and (not keyword or keyword in item["entity_name"].lower())
            ]
        try:
            items = _fetch_parties()
        except PartyDatabaseError:
            if _CACHE_ITEMS:
                return list(_CACHE_ITEMS)
            raise
        _CACHE_ITEMS = items
        _CACHE_EXPIRES_AT = now + _CACHE_TTL_SECONDS
        keyword = query.strip().lower()
        return [
            item
            for item in items
            if (not party_type or item.get("party_type") == party_type)
            and (not keyword or keyword in item["entity_name"].lower())
        ]


def create_party(values: dict[str, str]) -> dict[str, str]:
    database = get_database_name()
    table = get_table_name("party", "OA_PARTY_DB_TABLE", "mmdy_party_info")
    full_table = f"{_identifier(database, '主体库数据库')}.{_identifier(table, '主体库数据表')}"
    cleaned = {
        column: str(values.get(column) or "").strip()
        for column in PARTY_COLUMNS
    }
    cleaned["party_type"] = "乙方"
    connection = None
    try:
        connection = pymysql.connect(**connection_config())
        with connection.cursor() as cursor:
            _ensure_schema(cursor, full_table)
            cursor.execute(
                f"""
                SELECT 1
                  FROM {full_table}
                 WHERE `entity_name` = %s
                    OR `unified_social_credit_code` = %s
                 LIMIT 1
                """,
                (
                    cleaned["entity_name"],
                    cleaned["unified_social_credit_code"],
                ),
            )
            if cursor.fetchone():
                raise PartyConflictError("该主体名称或统一社会信用代码已存在")
            placeholders = ", ".join(["%s"] * len(PARTY_COLUMNS))
            columns = ", ".join(f"`{column}`" for column in PARTY_COLUMNS)
            cursor.execute(
                f"INSERT INTO {full_table} ({columns}) VALUES ({placeholders})",
                tuple(cleaned[column] for column in PARTY_COLUMNS),
            )
        connection.commit()
    except PartyConflictError:
        raise
    except pymysql.MySQLError as exc:
        raise PartyDatabaseError("主体信息保存失败") from exc
    finally:
        if connection is not None:
            connection.close()
    clear_cache()
    return cleaned


def clear_cache() -> None:
    global _CACHE_EXPIRES_AT, _CACHE_ITEMS
    with _CACHE_LOCK:
        _CACHE_ITEMS = []
        _CACHE_EXPIRES_AT = 0.0
