from __future__ import annotations

import pytest


def create_validation_template(client, login_as) -> int:
    login_as(client, "legal", "Legal@123")
    response = client.post(
        "/api/templates",
        json={
            "name": "空白项格式校验模板",
            "contract_code": "VAL-",
            "category": "测试类",
            "description": "",
            "instructions": "",
            "content": (
                "<p>{{合同金额}}</p><p>{{采购数量}}</p>"
                "<p>{{签署日期}}</p><p>{{结算方式}}</p>"
            ),
            "fields": [
                {
                    "key": "合同金额",
                    "label": "合同金额",
                    "type": "currency",
                    "required": False,
                    "hint": "",
                    "placeholder": "",
                    "options": [],
                },
                {
                    "key": "采购数量",
                    "label": "采购数量",
                    "type": "number",
                    "required": False,
                    "hint": "",
                    "placeholder": "",
                    "options": [],
                },
                {
                    "key": "签署日期",
                    "label": "签署日期",
                    "type": "date",
                    "required": False,
                    "hint": "",
                    "placeholder": "",
                    "options": [],
                },
                {
                    "key": "结算方式",
                    "label": "结算方式",
                    "type": "select",
                    "required": False,
                    "hint": "",
                    "placeholder": "",
                    "options": ["月结", "现结"],
                },
            ],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("合同金额", "一千元", "合同金额（仅可填写数字金额，最多两位小数）"),
        ("合同金额", "12.345", "合同金额（仅可填写数字金额，最多两位小数）"),
        ("采购数量", "三台", "采购数量（仅可填写数字，最多六位小数）"),
        ("采购数量", "1.1234567", "采购数量（仅可填写数字，最多六位小数）"),
        ("签署日期", "2026-02-30", "签署日期（请选择有效日期）"),
        ("结算方式", "转账", "结算方式（请从下拉选项中选择）"),
    ],
)
def test_contract_rejects_values_that_do_not_match_field_type(
    client, login_as, key, value, message
):
    template_id = create_validation_template(client, login_as)
    login_as(client, "business", "Business@123")

    response = client.post(
        "/api/contracts",
        json={
            "template_id": template_id,
            "title": "空白项格式校验",
            "field_values": {key: value},
        },
    )

    assert response.status_code == 422
    assert message in response.json()["detail"]["message"]


def test_contract_accepts_values_matching_each_field_type(client, login_as):
    template_id = create_validation_template(client, login_as)
    login_as(client, "business", "Business@123")

    response = client.post(
        "/api/contracts",
        json={
            "template_id": template_id,
            "title": "空白项格式正确",
            "field_values": {
                "合同金额": "1,000.50",
                "采购数量": "-2.5",
                "签署日期": "2026年12月31日",
                "结算方式": "月结",
            },
        },
    )

    assert response.status_code == 201, response.text
    values = response.json()["field_values"]
    assert values["合同金额"] == "1,000.50"
    assert values["采购数量"] == "-2.5"
    assert values["签署日期"] == "2026年12月31日"
    assert values["结算方式"] == "月结"


def test_contract_update_rejects_invalid_numeric_value(client, login_as):
    template_id = create_validation_template(client, login_as)
    login_as(client, "business", "Business@123")
    created = client.post(
        "/api/contracts",
        json={"template_id": template_id, "title": "更新格式校验"},
    )
    assert created.status_code == 201, created.text

    response = client.put(
        f"/api/contracts/{created.json()['id']}",
        json={"title": "更新格式校验", "field_values": {"合同金额": "abc"}},
    )

    assert response.status_code == 422
    assert "合同金额" in response.json()["detail"]["message"]


def test_auto_amount_fields_are_not_rejected_as_manual_numeric_input(client, login_as):
    login_as(client, "legal", "Legal@123")
    template = client.post(
        "/api/templates",
        json={
            "name": "自动金额格式校验模板",
            "contract_code": "AUTO-",
            "category": "测试类",
            "description": "",
            "instructions": "",
            "content": (
                "<p>{{合同金额}}</p><p>{{合同金额大写}}</p>"
                "<p>{{预付款}}</p><p>{{尾款}}</p>"
            ),
            "fields": [
                {
                    "key": key,
                    "label": label,
                    "type": "currency",
                    "required": False,
                    "hint": "",
                    "placeholder": "",
                    "options": [],
                }
                for key, label in [
                    ("合同金额", "合同金额"),
                    ("合同金额大写", "合同金额大写"),
                    ("预付款", "预付款"),
                    ("尾款", "尾款"),
                ]
            ],
        },
    )
    assert template.status_code == 201, template.text

    login_as(client, "business", "Business@123")
    created = client.post(
        "/api/contracts",
        json={
            "template_id": template.json()["id"],
            "title": "自动金额格式校验",
            "field_values": {"合同金额": "1000"},
        },
    )

    assert created.status_code == 201, created.text
    values = created.json()["field_values"]
    assert values["合同金额大写"] == "壹仟"
    assert values["预付款"] == "叁佰元整"
    assert values["尾款"] == "柒佰元整"
