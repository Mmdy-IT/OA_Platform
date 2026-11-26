from __future__ import annotations

from decimal import Decimal

import pytest

from backend.amounts import (
    amount_to_chinese_upper,
    amount_to_chinese_upper_short,
    apply_auto_amounts,
    apply_table_summary_totals,
    apply_table_row_auto_values,
    apply_table_row_sequences,
    apply_table_row_totals,
    sum_contract_table_total,
)


AMOUNT_TABLE = """
<p>采购清单</p>
<table>
  <tbody>
    <tr><td>产品名称</td><td>单价（元）</td><td>总额（元）</td></tr>
    <tr><td>办公椅</td><td>500</td><td>1,000.00</td></tr>
    <tr><td>办公桌</td><td>800</td><td>2,000.50</td></tr>
    <tr><td>合计</td><td colspan="2">¥3,000.50（大写：人民币叁仟元伍角）</td></tr>
  </tbody>
</table>
<p>总额：{{总额}}；大写：{{大写总额}}</p>
"""

ROW_TOTAL_TABLE = """
<p>采购清单</p>
<table>
  <tbody>
    <tr><td>产品名称</td><td>数量（个）</td><td>单价（元）</td><td>总额（元）</td></tr>
    <tr><td>办公椅</td><td>2</td><td>500</td><td>1,000.00</td></tr>
    <tr><td>合计</td><td colspan="3">¥1,000.00</td></tr>
  </tbody>
</table>
<p>总额：{{总额}}；大写：{{大写总额}}</p>
"""

SEQUENCE_TABLE = """
<p>采购清单</p>
<table>
  <tbody>
    <tr><td>序号</td><td>产品名称</td><td>数量（个）</td><td>单价（元）</td><td>总额（元）</td></tr>
    <tr><td>1</td><td>办公椅</td><td>2</td><td>500</td><td>1,000.00</td></tr>
    <tr><td></td><td>合计</td><td colspan="3">¥1,000.00</td></tr>
  </tbody>
</table>
<p>总额：{{总额}}；大写：{{大写总额}}</p>
"""


def test_sum_contract_table_total_uses_total_column_and_skips_summary_row():
    assert sum_contract_table_total(AMOUNT_TABLE, None) == Decimal("3000.50")


def test_sum_contract_table_total_includes_added_rows():
    adjustments = {
        "0": [
            0,
            1,
            2,
            3,
            {"id": "new-row", "cells": ["文件柜", "300", "500.25"]},
        ]
    }
    assert sum_contract_table_total(AMOUNT_TABLE, adjustments) == Decimal("3500.75")


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        ("0", "零元整"),
        ("1", "壹元整"),
        ("10", "壹拾元整"),
        ("1001", "壹仟零壹元整"),
        ("10000", "壹万元整"),
        ("100000001", "壹亿零壹元整"),
        ("3000.50", "叁仟元伍角"),
        ("3500.75", "叁仟伍佰元柒角伍分"),
        ("0.05", "零元零伍分"),
    ],
)
def test_amount_to_chinese_upper(amount: str, expected: str):
    assert amount_to_chinese_upper(amount) == expected


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        ("30", "叁拾"),
        ("30.00", "叁拾"),
        ("30.5", "叁拾元伍角"),
        ("30.05", "叁拾元零伍分"),
        ("0", "零"),
    ],
)
def test_amount_to_chinese_upper_short(amount: str, expected: str):
    assert amount_to_chinese_upper_short(amount) == expected


def test_apply_auto_amounts_fills_custom_uppercase_field():
    fields = [
        {"key": "总费用", "type": "currency"},
        {"key": "总费用大写", "type": "text"},
    ]

    updated = apply_auto_amounts(
        "<p>总费用：{{总费用}}；大写：{{总费用大写}}</p>",
        None,
        fields,
        {"总费用": "30"},
    )

    assert updated == {"总费用": "30", "总费用大写": "叁拾"}


def test_table_summary_row_uses_row_total_sum_and_uppercase():
    content = """
    <table>
      <tbody>
        <tr><td>产品名称</td><td>单价（元）</td><td>总额（元）</td></tr>
        <tr><td>办公椅</td><td>500</td><td>1,000.00</td></tr>
        <tr><td>办公桌</td><td>800</td><td>2,000.50</td></tr>
        <tr><td colspan="2">合计</td><td>¥ 元（大写：人民币 圆整）</td></tr>
        <tr><td colspan="3">备注：以上费用包含全部费用。</td></tr>
      </tbody>
    </table>
    """

    updated = apply_table_summary_totals(content)

    assert "¥ 3,000.50 元" in updated
    assert "大写：人民币 叁仟元伍角" in updated


def test_table_summary_row_stays_blank_without_data_rows():
    content = """
    <table>
      <tbody>
        <tr><td>产品名称</td><td>总额（元）</td></tr>
        <tr><td>合计</td><td>¥ 元（大写：人民币 圆整）</td></tr>
        <tr><td>备注：暂无明细。</td></tr>
      </tbody>
    </table>
    """

    assert apply_table_summary_totals(content) == content


def test_apply_auto_amounts_only_updates_configured_fields():
    fields = [{"key": "总额"}, {"key": "大写总额"}, {"key": "备注"}]
    values = {"总额": "手工填写的值", "备注": "保留"}

    updated = apply_auto_amounts(AMOUNT_TABLE, None, fields, values)

    assert updated == {
        "总额": "3000.50",
        "大写总额": "叁仟元伍角",
        "备注": "保留",
    }


def test_auto_payment_fields_use_table_total_and_chinese_upper():
    fields = [{"key": "预付款"}, {"key": "尾款"}]

    updated = apply_auto_amounts(AMOUNT_TABLE, None, fields, {})

    assert updated["预付款"] == "玖佰元壹角伍分"
    assert updated["尾款"] == "贰仟壹佰元叁角伍分"


def test_auto_payment_fields_fall_back_to_contract_amount_field():
    content = "<p>总费用：{{总费用}}</p><p>预付款：{{预付款}}；尾款：{{尾款}}</p>"
    fields = [
        {"key": "总费用", "label": "总费用", "type": "currency"},
        {"key": "预付款", "label": "预付款", "type": "text"},
        {"key": "尾款", "label": "尾款", "type": "text"},
    ]

    updated = apply_auto_amounts(content, None, fields, {"总费用": "30"})

    assert updated["总费用"] == "30"
    assert updated["预付款"] == "玖元整"
    assert updated["尾款"] == "贰拾壹元整"


def test_auto_payment_rounding_keeps_prepayment_and_final_payment_in_balance():
    content = "<p>合同金额：{{合同金额}}</p>"
    fields = [
        {"key": "合同金额", "label": "合同金额", "type": "currency"},
        {"key": "预付款", "label": "预付款", "type": "text"},
        {"key": "尾款", "label": "尾款", "type": "text"},
    ]

    updated = apply_auto_amounts(content, None, fields, {"合同金额": "30.05"})

    assert updated["预付款"] == "玖元零贰分"
    assert updated["尾款"] == "贰拾壹元零叁分"


def test_apply_table_row_totals_multiplies_quantity_and_unit_price():
    adjustments = {
        "0": [
            0,
            1,
            2,
            {"id": "new-row", "cells": ["文件柜", "3", "300", ""]},
        ]
    }

    updated = apply_table_row_totals(ROW_TOTAL_TABLE, adjustments)

    assert updated["0"][-1]["cells"] == ["文件柜", "3", "300", "900.00"]


def test_apply_table_row_totals_clears_total_when_inputs_are_invalid():
    adjustments = {
        "0": [0, 1, 2, {"id": "new-row", "cells": ["文件柜", "三", "300", "900.00"]}]
    }

    updated = apply_table_row_totals(ROW_TOTAL_TABLE, adjustments)

    assert updated["0"][-1]["cells"] == ["文件柜", "三", "300", ""]


def test_apply_table_row_sequences_follows_effective_row_order():
    adjustments = {
        "0": [
            0,
            1,
            2,
            {"id": "new-1", "cells": ["", "文件柜", "3", "300", ""]},
            {"id": "new-2", "cells": ["", "显示器", "2", "800", ""]},
        ]
    }

    updated = apply_table_row_sequences(SEQUENCE_TABLE, adjustments)

    assert updated["0"][-2]["cells"][0] == "2"
    assert updated["0"][-1]["cells"][0] == "3"


def test_apply_table_row_auto_values_combines_sequence_and_total():
    adjustments = {
        "0": [
            0,
            1,
            2,
            {"id": "new-1", "cells": ["", "文件柜", "3", "300", ""]},
        ]
    }

    updated = apply_table_row_auto_values(SEQUENCE_TABLE, adjustments)

    assert updated["0"][-1]["cells"] == ["2", "文件柜", "3", "300", "900.00"]


def test_contract_api_calculates_amounts_from_table_rows(client, login_as):
    fields = [
        {
            "key": "总额",
            "label": "总额",
            "type": "currency",
            "required": True,
            "hint": "",
            "placeholder": "",
            "options": [],
        },
        {
            "key": "大写总额",
            "label": "大写总额",
            "type": "text",
            "required": True,
            "hint": "",
            "placeholder": "",
            "options": [],
        },
    ]
    login_as(client, "legal", "Legal@123")
    created_template = client.post(
        "/api/templates",
        json={
            "name": "金额自动汇总测试模板",
            "contract_code": "AMT-",
            "category": "测试类",
            "description": "",
            "instructions": "",
            "content": AMOUNT_TABLE,
            "fields": fields,
        },
    )
    assert created_template.status_code == 201, created_template.text
    template_id = created_template.json()["id"]

    login_as(client, "business", "Business@123")
    created = client.post(
        "/api/contracts",
        json={
            "template_id": template_id,
            "title": "金额自动汇总合同",
            "field_values": {},
            "table_adjustments": {
                "0": [
                    0,
                    1,
                    2,
                    3,
                    {"id": "new-row", "cells": ["文件柜", "300", "500.25"]},
                ]
            },
        },
    )
    assert created.status_code == 201, created.text
    contract = created.json()
    assert contract["field_values"]["总额"] == "3500.75"
    assert contract["field_values"]["大写总额"] == "叁仟伍佰元柒角伍分"

    submitted = client.post(f"/api/contracts/{contract['id']}/submit")
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["field_values"]["总额"] == "3500.75"
    assert submitted.json()["field_values"]["大写总额"] == "叁仟伍佰元柒角伍分"


def test_contract_api_calculates_row_total_before_summing(client, login_as):
    fields = [
        {
            "key": "总额",
            "label": "总额",
            "type": "currency",
            "required": True,
            "hint": "",
            "placeholder": "",
            "options": [],
        },
        {
            "key": "大写总额",
            "label": "大写总额",
            "type": "text",
            "required": True,
            "hint": "",
            "placeholder": "",
            "options": [],
        },
    ]
    login_as(client, "legal", "Legal@123")
    template_response = client.post(
        "/api/templates",
        json={
            "name": "行总额测试模板",
            "contract_code": "ROW-",
            "category": "测试类",
            "description": "",
            "instructions": "",
            "content": ROW_TOTAL_TABLE,
            "fields": fields,
        },
    )
    assert template_response.status_code == 201, template_response.text

    login_as(client, "business", "Business@123")
    created = client.post(
        "/api/contracts",
        json={
            "template_id": template_response.json()["id"],
            "title": "行总额测试合同",
            "field_values": {},
            "table_adjustments": {
                "0": [
                    0,
                    1,
                    2,
                    {"id": "new-row", "cells": ["文件柜", "3", "300", ""]},
                ]
            },
        },
    )
    assert created.status_code == 201, created.text
    contract = created.json()
    assert contract["table_adjustments"]["0"][-1]["cells"] == [
        "文件柜",
        "3",
        "300",
        "900.00",
    ]
    assert contract["field_values"]["总额"] == "1900.00"
    assert contract["field_values"]["大写总额"] == "壹仟玖佰元整"


def test_contract_api_generates_sequence_for_added_rows(client, login_as):
    fields = [
        {
            "key": "总额",
            "label": "总额",
            "type": "currency",
            "required": True,
            "hint": "",
            "placeholder": "",
            "options": [],
        },
        {
            "key": "大写总额",
            "label": "大写总额",
            "type": "text",
            "required": True,
            "hint": "",
            "placeholder": "",
            "options": [],
        },
    ]
    login_as(client, "legal", "Legal@123")
    template_response = client.post(
        "/api/templates",
        json={
            "name": "序号自动生成测试模板",
            "contract_code": "SEQ-",
            "category": "测试类",
            "description": "",
            "instructions": "",
            "content": SEQUENCE_TABLE,
            "fields": fields,
        },
    )
    assert template_response.status_code == 201, template_response.text

    login_as(client, "business", "Business@123")
    created = client.post(
        "/api/contracts",
        json={
            "template_id": template_response.json()["id"],
            "title": "序号自动生成测试合同",
            "field_values": {},
            "table_adjustments": {
                "0": [
                    0,
                    1,
                    2,
                    {"id": "new-1", "cells": ["", "文件柜", "3", "300", ""]},
                    {"id": "new-2", "cells": ["", "显示器", "2", "800", ""]},
                ]
            },
        },
    )
    assert created.status_code == 201, created.text
    contract = created.json()
    assert contract["table_adjustments"]["0"][-2]["cells"] == [
        "2",
        "文件柜",
        "3",
        "300",
        "900.00",
    ]
    assert contract["table_adjustments"]["0"][-1]["cells"] == [
        "3",
        "显示器",
        "2",
        "800",
        "1600.00",
    ]
    assert contract["field_values"]["总额"] == "3500.00"
