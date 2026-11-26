from __future__ import annotations

import re
from datetime import datetime


DEFAULT_CONTRACT_CODE = "HT"
MAX_DAILY_SEQUENCE = 9999
CONTRACT_CODE_RE = re.compile(r"^[-A-Za-z0-9_\u3400-\u4dbf\u4e00-\u9fff]{1,20}$")
CONTRACT_SEQUENCE_RE = re.compile(r"\d{8}(\d{4})$")


def normalize_contract_code(value: str) -> str:
    code = (value or "").strip()
    if not code:
        raise ValueError("请填写合同编码")
    if not CONTRACT_CODE_RE.fullmatch(code):
        raise ValueError("合同编码只能包含中文、字母、数字、下划线或短横线，且不超过 20 位")
    return code


def next_contract_number(conn, contract_code: str, now: datetime | None = None) -> str:
    code = normalize_contract_code(contract_code or DEFAULT_CONTRACT_CODE)
    date_part = (now or datetime.now()).strftime("%Y%m%d")
    prefix = f"{code}{date_part}"
    rows = conn.execute(
        "SELECT contract_no FROM contracts WHERE substr(contract_no, 1, ?) = ?",
        (len(prefix), prefix),
    ).fetchall()

    sequence = 0
    for row in rows:
        suffix = str(row[0])[len(prefix):]
        if len(suffix) == 4 and suffix.isdigit():
            sequence = max(sequence, int(suffix))

    while sequence < MAX_DAILY_SEQUENCE:
        sequence += 1
        candidate = f"{prefix}{sequence:04d}"
        exists = conn.execute(
            "SELECT 1 FROM contracts WHERE contract_no = ?", (candidate,)
        ).fetchone()
        if not exists:
            return candidate
    raise ValueError("当日合同编号流水号已用尽（0001-9999）")


def contract_serial_number(contract_no: str) -> str:
    match = CONTRACT_SEQUENCE_RE.search(contract_no or "")
    return match.group(1) if match else ""
