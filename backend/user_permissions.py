from __future__ import annotations

import json
import os
import re
import threading
import time
from datetime import datetime
from typing import Any

import pymysql

from .config import get_database_name, get_table_name
from .db import db_cursor, utcnow
from .party_db import connection_config


class UserPermissionError(RuntimeError):
    """Raised when the external permission table cannot be accessed."""


class UserPermissionNotFound(UserPermissionError):
    """Raised when a permission record does not exist."""


class UserPermissionConflict(UserPermissionError):
    """Raised when a union_id is already bound to another user."""


class UserPermissionValidationError(UserPermissionError):
    """Raised when submitted permission data is invalid."""


class FeishuProvisionError(UserPermissionError):
    """Raised when a Feishu identity cannot be mapped to an OA user."""


MODULES: list[dict[str, str]] = [
    {
        "key": "dashboard",
        "label": "工作台",
        "group": "工作台",
        "description": "查看个人待办、合同概览与最近流转。",
    },
    {
        "key": "contracts",
        "label": "合同列表",
        "group": "合同管理",
        "description": "起草、查看、提交并下载本人发起的合同。",
    },
    {
        "key": "party_a",
        "label": "甲方主体信息",
        "group": "合同管理",
        "description": "查看、搜索并维护甲方主体及主体编号。",
    },
    {
        "key": "parties",
        "label": "乙方主体信息",
        "group": "合同管理",
        "description": "查看、搜索和新增公司主体信息。",
    },
    {
        "key": "reviews",
        "label": "审核工作台",
        "group": "合同管理",
        "description": "查看全部合同并执行法务审核、驳回与留痕。",
    },
    {
        "key": "templates",
        "label": "合同模板",
        "group": "合同管理",
        "description": "新增、编辑、导入、归档和删除合同模板。",
    },
]

MODULE_KEYS = tuple(item["key"] for item in MODULES)
MODULE_ORDER = {key: index for index, key in enumerate(MODULE_KEYS)}

ROLE_DEFAULT_PERMISSIONS: dict[str, tuple[str, ...]] = {
    "admin": MODULE_KEYS,
    "legal": ("dashboard", "contracts", "party_a", "parties", "reviews", "templates"),
    "business": ("dashboard", "contracts"),
}

NEW_USER_PERMISSIONS: tuple[str, ...] = ROLE_DEFAULT_PERMISSIONS["business"]

_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_]+$")
_TABLE_READY = False
_REQUEST_TABLE_READY = False
_CACHE_LOCK = threading.Lock()
_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_CACHE_SECONDS = max(float(os.getenv("OA_PERMISSION_CACHE_SECONDS", "0")), 0.0)


def permission_defaults(role: str) -> tuple[str, ...]:
    return ROLE_DEFAULT_PERMISSIONS.get(role, ROLE_DEFAULT_PERMISSIONS["business"])


def new_user_permissions() -> tuple[str, ...]:
    return NEW_USER_PERMISSIONS


def _identifier(value: str, label: str) -> str:
    if not _IDENTIFIER_RE.fullmatch(value):
        raise UserPermissionError(f"{label}配置不正确")
    return f"`{value}`"


def _full_table() -> str:
    database = get_database_name()
    table = get_table_name("user_permission", "OA_USER_PERMISSION_TABLE", "oa_user_permission")
    return f"{_identifier(database, '人员权限数据库')}.{_identifier(table, '人员权限数据表')}"


def _employee_table() -> str:
    database = get_database_name()
    table = get_table_name("employee", "OA_EMPLOYEE_TABLE", "mmdy_employee_info")
    return f"{_identifier(database, '员工数据库')}.{_identifier(table, '员工数据表')}"


def _request_table() -> str:
    database = get_database_name()
    table = get_table_name(
        "permission_request",
        "OA_PERMISSION_REQUEST_TABLE",
        "oa_permission_request",
    )
    return f"{_identifier(database, '权限申请数据库')}.{_identifier(table, '权限申请数据表')}"


def _connect():
    return pymysql.connect(**connection_config())


def _ensure_table(cursor) -> None:
    global _TABLE_READY
    if _TABLE_READY:
        return
    table = _full_table()
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {table} (
          `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
          `oa_user_id` BIGINT NULL COMMENT 'OA 用户 ID',
          `union_id` VARCHAR(64) NULL COMMENT '飞书 union_id',
          `username` VARCHAR(64) NOT NULL DEFAULT '' COMMENT 'OA 登录账号',
          `display_name` VARCHAR(100) NOT NULL DEFAULT '' COMMENT '人员姓名',
          `role` VARCHAR(20) NOT NULL DEFAULT 'business' COMMENT '系统角色：admin/legal/business',
          `department` VARCHAR(100) NOT NULL DEFAULT '' COMMENT '所属部门',
          `job_title` VARCHAR(100) NOT NULL DEFAULT '' COMMENT '岗位',
          `avatar_url` VARCHAR(1000) NOT NULL DEFAULT '' COMMENT '飞书头像地址',
          `permissions_json` TEXT NOT NULL COMMENT '已开通的子模块权限 JSON 数组',
          `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
          `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          PRIMARY KEY (`id`),
          UNIQUE KEY `uk_oa_user_id` (`oa_user_id`),
          UNIQUE KEY `uk_union_id` (`union_id`),
          KEY `idx_username` (`username`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='OA 人员子模块权限表'
        """
    )
    cursor.execute(f"SHOW COLUMNS FROM {table}")
    columns = {str(row.get("Field") or "") for row in cursor.fetchall()}
    if "job_title" not in columns:
        cursor.execute(
            f"ALTER TABLE {table} "
            "ADD COLUMN `job_title` VARCHAR(100) NOT NULL DEFAULT '' "
            "COMMENT '岗位' AFTER `department`"
        )
    if "avatar_url" not in columns:
        cursor.execute(
            f"ALTER TABLE {table} "
            "ADD COLUMN `avatar_url` VARCHAR(1000) NOT NULL DEFAULT '' "
            "COMMENT '飞书头像地址' AFTER `job_title`"
        )
    _TABLE_READY = True


def _ensure_request_table(cursor) -> None:
    global _REQUEST_TABLE_READY
    if _REQUEST_TABLE_READY:
        return
    table = _request_table()
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {table} (
          `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
          `oa_user_id` BIGINT NOT NULL COMMENT '申请人 OA 用户 ID',
          `username` VARCHAR(64) NOT NULL DEFAULT '' COMMENT '申请人账号',
          `display_name` VARCHAR(100) NOT NULL DEFAULT '' COMMENT '申请人姓名',
          `permissions_json` TEXT NOT NULL COMMENT '申请开通的模块权限 JSON 数组',
          `reason` VARCHAR(1000) NOT NULL COMMENT '开通事由',
          `status` VARCHAR(20) NOT NULL DEFAULT 'pending' COMMENT 'pending/approved/rejected',
          `reviewer_id` BIGINT NULL COMMENT '审批管理员 OA 用户 ID',
          `reviewer_name` VARCHAR(100) NOT NULL DEFAULT '' COMMENT '审批管理员姓名',
          `review_comment` VARCHAR(1000) NOT NULL DEFAULT '' COMMENT '审批意见',
          `reviewed_at` DATETIME NULL COMMENT '审批时间',
          `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
          `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          PRIMARY KEY (`id`),
          KEY `idx_permission_request_user` (`oa_user_id`),
          KEY `idx_permission_request_status` (`status`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='OA 权限申请表'
        """
    )
    _REQUEST_TABLE_READY = True


def _sync_local_users(cursor) -> None:
    table = _full_table()
    with db_cursor() as local:
        users = local.execute(
            "SELECT id, username, display_name, role, department FROM users ORDER BY id ASC"
        ).fetchall()
    for user in users:
        if str(user["username"]) in {"legal", "business"}:
            continue
        defaults = json.dumps(new_user_permissions(), ensure_ascii=False)
        cursor.execute(
            f"""
            INSERT INTO {table} (
                `oa_user_id`, `username`, `display_name`, `role`, `department`, `permissions_json`
            ) VALUES (%s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                `oa_user_id` = COALESCE(`oa_user_id`, VALUES(`oa_user_id`)),
                `username` = IF(`username` = '', VALUES(`username`), `username`),
                `display_name` = IF(
                    `display_name` = '', VALUES(`display_name`), `display_name`
                ),
                `department` = IF(
                    `department` = '', VALUES(`department`), `department`
                )
            """,
            (
                user["id"],
                user["username"],
                user["display_name"],
                user["role"],
                user["department"],
                defaults,
            ),
        )


def _load_permissions_json(raw: Any, role: str = "business") -> tuple[str, ...]:
    if raw is None or str(raw).strip() == "":
        return permission_defaults(role)
    try:
        values = json.loads(str(raw))
    except (json.JSONDecodeError, TypeError):
        return permission_defaults(role)
    if not isinstance(values, list):
        return permission_defaults(role)
    keys = {str(item).strip() for item in values}
    return tuple(sorted((key for key in keys if key in MODULE_ORDER), key=MODULE_ORDER.get))


def _normalize_permission_keys(values: list[str]) -> tuple[str, ...]:
    keys = {str(item).strip() for item in values if str(item).strip()}
    unknown = sorted(keys - set(MODULE_KEYS))
    if unknown:
        raise UserPermissionValidationError(f"未知的子模块权限：{', '.join(unknown)}")
    return tuple(sorted(keys, key=MODULE_ORDER.get))


def _row_to_record(row: dict) -> dict:
    role = str(row.get("role") or "business")
    updated_at = row.get("updated_at")
    if isinstance(updated_at, datetime):
        updated_at = updated_at.isoformat(timespec="seconds")
    return {
        "id": int(row["id"]),
        "oa_user_id": int(row["oa_user_id"]) if row.get("oa_user_id") is not None else None,
        "union_id": str(row.get("union_id") or ""),
        "username": str(row.get("username") or ""),
        "display_name": str(row.get("display_name") or ""),
        "role": role,
        "department": str(row.get("department") or ""),
        "job_title": str(row.get("job_title") or ""),
        "avatar_url": str(row.get("avatar_url") or ""),
        "permissions": list(_load_permissions_json(row.get("permissions_json"), role)),
        "updated_at": updated_at or "",
    }


def _select_by_union_id(cursor, union_id: str) -> dict | None:
    table = _full_table()
    cursor.execute(
        f"""
        SELECT `id`, `oa_user_id`, `union_id`, `username`, `display_name`,
               `role`, `department`, `job_title`, `avatar_url`,
               `permissions_json`, `updated_at`
          FROM {table}
         WHERE `union_id` = %s
         LIMIT 1
        """,
        (union_id,),
    )
    row = cursor.fetchone()
    return dict(row) if row else None


def _fetch_employee_info(
    cursor,
    union_id: str,
    employee_no: str,
    open_id: str,
) -> dict:
    table = _employee_table()
    queries = [
        ("`union_id` = %s", union_id),
        ("`employee_no` = %s", employee_no),
        ("`open_id` = %s", open_id),
    ]
    for clause, value in queries:
        if not value:
            continue
        try:
            cursor.execute(
                f"""
                SELECT `union_id`, `open_id`, `employee_no`, `name`,
                       `job_title`, `dept_path`
                  FROM {table}
                 WHERE {clause}
                 LIMIT 1
                """,
                (value,),
            )
            row = cursor.fetchone()
        except pymysql.MySQLError:
            return {}
        if row:
            return dict(row)
    return {}


def _local_user_by_id(user_id: int | None) -> dict | None:
    if user_id is None:
        return None
    with db_cursor() as conn:
        row = conn.execute(
            "SELECT id, username, display_name, role, department FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    return dict(row) if row else None


def _local_user_by_username(username: str) -> dict | None:
    if not username:
        return None
    with db_cursor() as conn:
        row = conn.execute(
            "SELECT id, username, display_name, role, department FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    return dict(row) if row else None


def _create_or_get_local_user(
    *,
    union_id: str,
    username: str,
    display_name: str,
    role: str,
    department: str,
) -> dict:
    existing = _local_user_by_username(username)
    if existing:
        return existing

    clean_role = role if role in {"admin", "legal", "business"} else "business"
    clean_name = display_name or "飞书用户"
    with db_cursor(commit=True) as conn:
        try:
            cursor = conn.execute(
                """
                INSERT INTO users(
                    username, password_hash, display_name, role, department, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (username, "!", clean_name, clean_role, department or "", utcnow()),
            )
            user_id = int(cursor.lastrowid)
        except Exception:
            row = conn.execute(
                "SELECT id FROM users WHERE username = ?", (username,)
            ).fetchone()
            if not row:
                raise
            user_id = int(row["id"])
        row = conn.execute(
            "SELECT id, username, display_name, role, department FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    if not row:
        raise FeishuProvisionError("无法创建飞书对应的 OA 用户")
    return dict(row)


def ensure_feishu_user(
    *,
    union_id: str,
    display_name: str,
    avatar_url: str = "",
    department: str = "",
    employee_no: str = "",
    open_id: str = "",
    auto_provision: bool = True,
) -> dict:
    """Resolve a Feishu union_id to an OA user, creating an ordinary account if needed."""
    union_value = (union_id or "").strip()
    if not union_value:
        raise FeishuProvisionError("飞书用户信息缺少 union_id")
    if len(union_value) > 64:
        raise FeishuProvisionError("飞书 union_id 超过 64 个字符")

    table = _full_table()
    connection = None
    try:
        connection = _connect()
        with connection.cursor() as cursor:
            _ensure_table(cursor)
            record = _select_by_union_id(cursor, union_value)
            employee = _fetch_employee_info(
                cursor,
                union_value,
                (employee_no or "").strip(),
                (open_id or "").strip(),
            )
            employee_department = str(employee.get("dept_path") or "").strip()
            employee_job_title = str(employee.get("job_title") or "").strip()

            local_user = None
            if record:
                local_user = _local_user_by_id(record.get("oa_user_id"))
                if not local_user and record.get("username"):
                    local_user = _local_user_by_username(str(record["username"]))

            if not local_user:
                if not auto_provision:
                    raise FeishuProvisionError("飞书账号尚未绑定 OA 人员，请联系管理员")
                role = str(record.get("role") or "business") if record else "business"
                username = str(record.get("username") or "").strip() if record else ""
                local_user = _create_or_get_local_user(
                    union_id=union_value,
                    username=username or f"feishu_{union_value}",
                    display_name=(
                        str(record.get("display_name") or "").strip()
                        if record
                        else display_name
                    ),
                    role=role,
                    department=(
                        str(record.get("department") or "").strip()
                        if record
                        else employee_department or department
                    ),
                )

            if record:
                avatar_value = avatar_url.strip() or str(record.get("avatar_url") or "")
                cursor.execute(
                    f"""
                    UPDATE {table}
                       SET `oa_user_id` = %s,
                           `username` = %s,
                           `display_name` = %s,
                           `department` = IF(`department` = '', %s, `department`),
                           `job_title` = IF(`job_title` = '', %s, `job_title`),
                           `avatar_url` = %s
                     WHERE `id` = %s
                    """,
                    (
                        local_user["id"],
                        local_user["username"],
                        local_user["display_name"],
                        employee_department or local_user["department"],
                        str(record.get("job_title") or "").strip()
                        or employee_job_title,
                        avatar_value,
                        record["id"],
                    ),
                )
            else:
                cursor.execute(
                    f"""
                    INSERT INTO {table} (
                        `oa_user_id`, `union_id`, `username`, `display_name`,
                        `role`, `department`, `job_title`, `avatar_url`,
                        `permissions_json`
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        local_user["id"],
                        union_value,
                        local_user["username"],
                        local_user["display_name"],
                        local_user["role"],
                        employee_department or local_user["department"],
                        employee_job_title,
                        avatar_url.strip(),
                        json.dumps(new_user_permissions(), ensure_ascii=False),
                    ),
                )
    except pymysql.IntegrityError as exc:
        raise UserPermissionConflict("该飞书账号已绑定其他 OA 人员") from exc
    except pymysql.MySQLError as exc:
        raise UserPermissionError("人员权限表连接失败，请稍后重试") from exc
    finally:
        if connection is not None:
            connection.close()

    clear_permission_cache()
    return local_user


def _select_record(cursor, record_id: int) -> dict | None:
    table = _full_table()
    cursor.execute(
        f"""
        SELECT `id`, `oa_user_id`, `union_id`, `username`, `display_name`,
               `role`, `department`, `job_title`, `avatar_url`,
               `permissions_json`, `updated_at`
          FROM {table}
         WHERE `id` = %s
        """,
        (record_id,),
    )
    return cursor.fetchone()


def list_user_permissions() -> list[dict]:
    table = _full_table()
    connection = None
    try:
        connection = _connect()
        with connection.cursor() as cursor:
            _ensure_table(cursor)
            _sync_local_users(cursor)
            cursor.execute(
                f"""
                SELECT `id`, `oa_user_id`, `union_id`, `username`, `display_name`,
                       `role`, `department`, `job_title`, `avatar_url`,
                       `permissions_json`, `updated_at`
                  FROM {table}
                 ORDER BY FIELD(`role`, 'admin', 'legal', 'business'), `display_name` ASC, `id` ASC
                """
            )
            rows = cursor.fetchall()
    except pymysql.MySQLError as exc:
        raise UserPermissionError("人员权限表连接失败，请稍后重试") from exc
    finally:
        if connection is not None:
            connection.close()
    return [_row_to_record(row) for row in rows]


def update_user_permission(
    record_id: int,
    *,
    permissions: list[str],
    union_id: str = "",
) -> dict:
    normalized = _normalize_permission_keys(permissions)
    union_value = (union_id or "").strip()
    if len(union_value) > 64:
        raise UserPermissionValidationError("飞书 union_id 不能超过 64 个字符")
    table = _full_table()
    connection = None
    try:
        connection = _connect()
        with connection.cursor() as cursor:
            _ensure_table(cursor)
            _sync_local_users(cursor)
            if not _select_record(cursor, record_id):
                raise UserPermissionNotFound("人员权限记录不存在")
            try:
                cursor.execute(
                    f"""
                    UPDATE {table}
                       SET `permissions_json` = %s,
                           `union_id` = %s
                     WHERE `id` = %s
                    """,
                    (
                        json.dumps(normalized, ensure_ascii=False),
                        union_value or None,
                        record_id,
                    ),
                )
            except pymysql.IntegrityError as exc:
                if exc.args and exc.args[0] == 1062:
                    raise UserPermissionConflict("该飞书 union_id 已绑定其他人员") from exc
                raise
            row = _select_record(cursor, record_id)
    except pymysql.MySQLError as exc:
        raise UserPermissionError("人员权限表保存失败，请稍后重试") from exc
    finally:
        if connection is not None:
            connection.close()
    clear_permission_cache()
    return _row_to_record(row)


def _select_permission_request(cursor, request_id: int) -> dict | None:
    table = _request_table()
    cursor.execute(
        f"""
        SELECT `id`, `oa_user_id`, `username`, `display_name`, `permissions_json`,
               `reason`, `status`, `reviewer_id`, `reviewer_name`, `review_comment`,
               `reviewed_at`, `created_at`, `updated_at`
          FROM {table}
         WHERE `id` = %s
        """,
        (request_id,),
    )
    return cursor.fetchone()


def _permission_request_record(row: dict) -> dict:
    reviewed_at = row.get("reviewed_at")
    created_at = row.get("created_at")
    updated_at = row.get("updated_at")
    for key in ("reviewed_at", "created_at", "updated_at"):
        value = row.get(key)
        if isinstance(value, datetime):
            row = {**row, key: value.isoformat(timespec="seconds")}
    return {
        "id": int(row["id"]),
        "oa_user_id": int(row["oa_user_id"]),
        "username": str(row.get("username") or ""),
        "display_name": str(row.get("display_name") or ""),
        "permissions": list(_load_permissions_json(row.get("permissions_json"))),
        "reason": str(row.get("reason") or ""),
        "status": str(row.get("status") or "pending"),
        "reviewer_id": int(row["reviewer_id"]) if row.get("reviewer_id") is not None else None,
        "reviewer_name": str(row.get("reviewer_name") or ""),
        "review_comment": str(row.get("review_comment") or ""),
        "reviewed_at": row.get("reviewed_at") or "",
        "created_at": row.get("created_at") or "",
        "updated_at": row.get("updated_at") or "",
    }


def create_permission_request(
    user: dict,
    *,
    permissions: list[str],
    reason: str,
) -> dict:
    normalized = _normalize_permission_keys(permissions)
    if not normalized:
        raise UserPermissionValidationError("请至少选择一个申请开通的权限")
    reason_value = (reason or "").strip()
    if not reason_value:
        raise UserPermissionValidationError("请填写开通事由")
    granted = set(user.get("permissions") or [])
    if all(key in granted for key in normalized):
        raise UserPermissionValidationError("所选权限均已开通，无需重复申请")

    table = _request_table()
    connection = None
    try:
        connection = _connect()
        with connection.cursor() as cursor:
            _ensure_request_table(cursor)
            cursor.execute(
                f"""
                SELECT `permissions_json`
                  FROM {table}
                 WHERE `oa_user_id` = %s AND `status` = 'pending'
                """,
                (user["id"],),
            )
            pending_keys: set[str] = set()
            for row in cursor.fetchall():
                pending_keys.update(_load_permissions_json(row.get("permissions_json")))
            duplicate = pending_keys.intersection(normalized)
            if duplicate:
                raise UserPermissionConflict("所选权限已有待审批申请，请勿重复提交")
            cursor.execute(
                f"""
                INSERT INTO {table} (
                    `oa_user_id`, `username`, `display_name`,
                    `permissions_json`, `reason`, `status`
                ) VALUES (%s, %s, %s, %s, %s, 'pending')
                """,
                (
                    user["id"],
                    str(user.get("username") or ""),
                    str(user.get("display_name") or ""),
                    json.dumps(normalized, ensure_ascii=False),
                    reason_value,
                ),
            )
            row = _select_permission_request(cursor, int(cursor.lastrowid))
    except (UserPermissionConflict, UserPermissionValidationError):
        raise
    except pymysql.MySQLError as exc:
        raise UserPermissionError("权限申请提交失败，请稍后重试") from exc
    finally:
        if connection is not None:
            connection.close()
    return _permission_request_record(row)


def list_permission_requests(user: dict) -> list[dict]:
    table = _request_table()
    connection = None
    try:
        connection = _connect()
        with connection.cursor() as cursor:
            _ensure_request_table(cursor)
            where = ""
            params: tuple = ()
            if user.get("role") != "admin":
                where = "WHERE `oa_user_id` = %s"
                params = (user["id"],)
            cursor.execute(
                f"""
                SELECT `id`, `oa_user_id`, `username`, `display_name`, `permissions_json`,
                       `reason`, `status`, `reviewer_id`, `reviewer_name`, `review_comment`,
                       `reviewed_at`, `created_at`, `updated_at`
                  FROM {table}
                  {where}
                 ORDER BY FIELD(`status`, 'pending', 'approved', 'rejected'), `id` DESC
                 LIMIT 300
                """,
                params,
            )
            rows = cursor.fetchall()
    except pymysql.MySQLError as exc:
        raise UserPermissionError("权限申请列表加载失败，请稍后重试") from exc
    finally:
        if connection is not None:
            connection.close()
    return [_permission_request_record(row) for row in rows]


def review_permission_request(
    request_id: int,
    reviewer: dict,
    *,
    decision: str,
    comment: str = "",
) -> dict:
    if decision not in {"approve", "reject"}:
        raise UserPermissionValidationError("审批结果不正确")
    request_table = _request_table()
    permission_table = _full_table()
    connection = None
    try:
        connection = _connect()
        with connection.cursor() as cursor:
            _ensure_request_table(cursor)
            _ensure_table(cursor)
            request_row = _select_permission_request(cursor, request_id)
            if not request_row:
                raise UserPermissionNotFound("权限申请不存在")
            if str(request_row.get("status")) != "pending":
                raise UserPermissionConflict("该权限申请已处理")
            if int(request_row["oa_user_id"]) == int(reviewer["id"]):
                raise UserPermissionConflict("不能审批本人提交的权限申请")
            if decision == "approve":
                cursor.execute(
                    f"""
                    SELECT `id`, `permissions_json`
                      FROM {permission_table}
                     WHERE `oa_user_id` = %s OR `username` = %s
                     LIMIT 1
                    """,
                    (request_row["oa_user_id"], request_row.get("username") or ""),
                )
                target = cursor.fetchone()
                if not target:
                    raise UserPermissionNotFound("申请人的权限记录不存在")
                merged = set(_load_permissions_json(target.get("permissions_json")))
                merged.update(_load_permissions_json(request_row.get("permissions_json")))
                normalized = tuple(sorted(merged, key=MODULE_ORDER.get))
                cursor.execute(
                    f"""
                    UPDATE {permission_table}
                       SET `permissions_json` = %s
                     WHERE `id` = %s
                    """,
                    (json.dumps(normalized, ensure_ascii=False), target["id"]),
                )
            cursor.execute(
                f"""
                UPDATE {request_table}
                   SET `status` = %s,
                       `reviewer_id` = %s,
                       `reviewer_name` = %s,
                       `review_comment` = %s,
                       `reviewed_at` = %s
                 WHERE `id` = %s
                """,
                (
                    "approved" if decision == "approve" else "rejected",
                    reviewer["id"],
                    str(reviewer.get("display_name") or ""),
                    (comment or "").strip(),
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    request_id,
                ),
            )
            row = _select_permission_request(cursor, request_id)
    except (UserPermissionConflict, UserPermissionNotFound, UserPermissionValidationError):
        raise
    except pymysql.MySQLError as exc:
        raise UserPermissionError("权限申请审批失败，请稍后重试") from exc
    finally:
        if connection is not None:
            connection.close()
    clear_permission_cache()
    return _permission_request_record(row)


def _fallback_access_profile(user: dict, *, default_permissions: bool) -> dict[str, Any]:
    role = str(user.get("role") or "business")
    permissions = (
        new_user_permissions() if default_permissions else permission_defaults(role)
    )
    return {
        "role": role,
        "permissions": list(permissions),
        "department": str(user.get("department") or ""),
        "job_title": str(user.get("job_title") or ""),
        "avatar_url": str(user.get("avatar_url") or ""),
    }


def _fetch_access_profile_for_user(user: dict) -> dict[str, Any]:
    table = _full_table()
    clauses: list[str] = []
    params: list[Any] = []
    oa_user_id = user.get("id")
    username = str(user.get("username") or "").strip()
    union_id = str(user.get("union_id") or "").strip()
    if oa_user_id is not None:
        clauses.append("`oa_user_id` = %s")
        params.append(oa_user_id)
    if username:
        clauses.append("`username` = %s")
        params.append(username)
    if union_id:
        clauses.append("`union_id` = %s")
        params.append(union_id)
    if not clauses:
        return _fallback_access_profile(user, default_permissions=True)

    connection = None
    try:
        connection = _connect()
        with connection.cursor() as cursor:
            _ensure_table(cursor)
            cursor.execute(
                f"""
                SELECT `role`, `department`, `job_title`, `avatar_url`,
                       `permissions_json`
                  FROM {table}
                 WHERE {' OR '.join(clauses)}
                 LIMIT 1
                """,
                params,
            )
            row = cursor.fetchone()
    except pymysql.MySQLError as exc:
        raise UserPermissionError("人员权限表连接失败") from exc
    finally:
        if connection is not None:
            connection.close()
    if not row:
        return _fallback_access_profile(user, default_permissions=True)
    role = str(row.get("role") or user.get("role") or "business")
    return {
        "role": role,
        "permissions": list(
            _load_permissions_json(row.get("permissions_json"), role)
        ),
        "department": str(row.get("department") or user.get("department") or ""),
        "job_title": str(row.get("job_title") or ""),
        "avatar_url": str(row.get("avatar_url") or user.get("avatar_url") or ""),
    }


def _fetch_permissions_for_user(user: dict) -> tuple[str, ...]:
    return tuple(_fetch_access_profile_for_user(user)["permissions"])


def resolve_access_profile(user: dict) -> dict[str, Any]:
    oa_user_id = user.get("id")
    username = str(user.get("username") or "").strip()
    union_id = str(user.get("union_id") or "").strip()
    cache_key = f"id:{oa_user_id}" if oa_user_id is not None else f"union:{union_id or username}"
    now = time.monotonic()
    if _CACHE_SECONDS > 0:
        with _CACHE_LOCK:
            cached = _CACHE.get(cache_key)
            if cached and cached[0] > now:
                return dict(cached[1])
    try:
        profile = _fetch_access_profile_for_user(user)
    except UserPermissionError:
        profile = _fallback_access_profile(user, default_permissions=False)
    if _CACHE_SECONDS > 0:
        with _CACHE_LOCK:
            _CACHE[cache_key] = (now + _CACHE_SECONDS, dict(profile))
    return profile


def resolve_permissions(user: dict) -> list[str]:
    return list(resolve_access_profile(user)["permissions"])


def clear_permission_cache() -> None:
    with _CACHE_LOCK:
        _CACHE.clear()
