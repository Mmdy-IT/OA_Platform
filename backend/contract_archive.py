from __future__ import annotations

import re
from datetime import datetime

import pymysql

from .config import get_database_name, get_table_name
from .contract_number import contract_serial_number
from .party_db import connection_config


class ContractArchiveError(RuntimeError):
    """Raised when contract information cannot be synchronized to mmdy_db."""


STATUS_LABELS = {
    "draft": "草稿",
    "pending": "待审核",
    "rejected": "已驳回",
    "approved": "已通过",
}


_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_]+$")


def _identifier(value: str, label: str) -> str:
    if not _IDENTIFIER_RE.fullmatch(value):
        raise ContractArchiveError(f"{label}配置不正确")
    return f"`{value}`"


def _full_table() -> str:
    database = get_database_name()
    table = get_table_name("contract_archive", "OA_CONTRACT_ARCHIVE_TABLE", "oa_contract_info")
    return f"{_identifier(database, '合同归档数据库')}.{_identifier(table, '合同归档数据表')}"


def _mysql_datetime(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed.strftime("%Y-%m-%d %H:%M:%S")


def _status_label(value: str) -> str:
    status = (value or "").strip()
    if status in STATUS_LABELS:
        return STATUS_LABELS[status]
    if status in STATUS_LABELS.values():
        return status
    raise ContractArchiveError("合同状态配置不正确")


def _ensure_columns(cursor, table: str) -> None:
    cursor.execute(f"SHOW COLUMNS FROM {table}")
    columns = {str(row.get("Field", "")) for row in cursor.fetchall()}
    if "serial_no" not in columns:
        cursor.execute(
            f"ALTER TABLE {table} "
            "ADD COLUMN `serial_no` VARCHAR(4) NOT NULL DEFAULT '0000' "
            "COMMENT '当日流水号' AFTER `contract_code`"
        )
    if "contract_status" not in columns:
        cursor.execute(
            f"ALTER TABLE {table} "
            "ADD COLUMN `contract_status` VARCHAR(20) NOT NULL DEFAULT '草稿' "
            "COMMENT '合同状态：草稿/待审核/已驳回/已通过' AFTER `contract_name`"
        )
    if "contract_category" not in columns:
        cursor.execute(
            f"ALTER TABLE {table} "
            "ADD COLUMN `contract_category` VARCHAR(40) NOT NULL DEFAULT '' "
            "COMMENT '合同分类' AFTER `template_version`"
        )

    cursor.execute(f"SHOW INDEX FROM {table}")
    indexes = {str(row.get("Key_name", "")) for row in cursor.fetchall()}
    if "idx_contract_status" not in indexes:
        cursor.execute(
            f"ALTER TABLE {table} ADD KEY `idx_contract_status` (`contract_status`)"
        )


def sync_contract_record(
    *,
    oa_contract_id: int,
    contract_no: str,
    contract_code: str,
    contract_name: str,
    contract_status: str,
    initiator_name: str,
    approver_name: str,
    template_name: str,
    template_version: str,
    contract_category: str,
    review_comment: str,
    approved_at: str | None,
) -> None:
    table = _full_table()
    serial_no = contract_serial_number(contract_no)
    status_label = _status_label(contract_status)
    approved_value = _mysql_datetime(approved_at) if status_label == "已通过" else None
    create_sql = f"""
        CREATE TABLE IF NOT EXISTS {table} (
          `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
          `oa_contract_id` BIGINT NOT NULL COMMENT 'OA 合同 ID',
          `contract_no` VARCHAR(64) NOT NULL COMMENT '合同编号',
          `contract_code` VARCHAR(40) NOT NULL COMMENT '合同编码',
          `serial_no` VARCHAR(4) NOT NULL DEFAULT '0000' COMMENT '当日流水号',
          `contract_name` VARCHAR(255) NOT NULL COMMENT '合同名称',
          `contract_status` VARCHAR(20) NOT NULL DEFAULT '草稿' COMMENT '合同状态：草稿/待审核/已驳回/已通过',
          `initiator_name` VARCHAR(100) NOT NULL COMMENT '发起人',
          `approver_name` VARCHAR(100) NOT NULL COMMENT '审批人',
          `template_name` VARCHAR(255) NOT NULL DEFAULT '' COMMENT '合同模板',
          `template_version` VARCHAR(32) NOT NULL DEFAULT '' COMMENT '模板版本',
          `contract_category` VARCHAR(40) NOT NULL DEFAULT '' COMMENT '合同分类',
          `review_comment` TEXT NULL COMMENT '审核意见',
          `approved_at` DATETIME NULL COMMENT '审核通过时间',
          `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
          `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          PRIMARY KEY (`id`),
          UNIQUE KEY `uk_oa_contract_id` (`oa_contract_id`),
          UNIQUE KEY `uk_contract_no` (`contract_no`),
          KEY `idx_contract_code` (`contract_code`),
          KEY `idx_contract_status` (`contract_status`),
          KEY `idx_approved_at` (`approved_at`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='OA 合同信息同步表'
    """
    upsert_sql = f"""
        INSERT INTO {table} (
            `oa_contract_id`, `contract_no`, `contract_code`, `serial_no`, `contract_name`,
            `contract_status`, `initiator_name`, `approver_name`, `template_name`,
            `template_version`, `contract_category`, `review_comment`, `approved_at`
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            `contract_no` = VALUES(`contract_no`),
            `contract_code` = VALUES(`contract_code`),
            `serial_no` = VALUES(`serial_no`),
            `contract_name` = VALUES(`contract_name`),
            `contract_status` = VALUES(`contract_status`),
            `initiator_name` = VALUES(`initiator_name`),
            `approver_name` = VALUES(`approver_name`),
            `template_name` = VALUES(`template_name`),
            `template_version` = VALUES(`template_version`),
            `contract_category` = VALUES(`contract_category`),
            `review_comment` = VALUES(`review_comment`),
            `approved_at` = VALUES(`approved_at`)
    """
    connection = None
    try:
        connection = pymysql.connect(**connection_config())
        with connection.cursor() as cursor:
            cursor.execute(create_sql)
            _ensure_columns(cursor, table)
            cursor.execute(
                upsert_sql,
                (
                    oa_contract_id,
                    contract_no,
                    contract_code,
                    serial_no,
                    contract_name,
                    status_label,
                    initiator_name,
                    approver_name,
                    template_name,
                    template_version,
                    contract_category,
                    review_comment,
                    approved_value,
                ),
            )
    except pymysql.MySQLError as exc:
        raise ContractArchiveError("合同信息表同步失败，请稍后重试") from exc
    finally:
        if connection is not None:
            connection.close()


def delete_contract_record(*, oa_contract_id: int) -> None:
    table = _full_table()
    connection = None
    try:
        connection = pymysql.connect(**connection_config())
        with connection.cursor() as cursor:
            cursor.execute(f"DELETE FROM {table} WHERE `oa_contract_id` = %s", (oa_contract_id,))
    except pymysql.MySQLError as exc:
        raise ContractArchiveError("合同信息表删除失败，请稍后重试") from exc
    finally:
        if connection is not None:
            connection.close()
