from __future__ import annotations

import re
from datetime import datetime

from backend import contract_archive
from backend.contract_number import contract_serial_number
from backend.pdf import _contract_document_values, _format_field_values, render_contract_text


def sample_field_value(field: dict) -> str:
    if field["type"] == "date":
        return "2026-12-31"
    if field["type"] == "currency":
        return "1000.00"
    if field["type"] == "number":
        return "10"
    if field["type"] == "select":
        return (field.get("options") or ["测试选项"])[0]
    return "测试填写内容"


def test_authentication_is_required(client):
    response = client.get("/api/dashboard")
    assert response.status_code == 401

    response = client.post(
        "/api/auth/login", json={"username": "business", "password": "wrong-password"}
    )
    assert response.status_code == 401


def test_business_to_legal_contract_flow(client, login_as):
    login_as(client, "business", "Business@123")
    templates = client.get("/api/templates").json()["items"]
    assert len(templates) == 3
    template = templates[0]

    forbidden = client.post("/api/templates", json={})
    assert forbidden.status_code == 403

    values = {field["key"]: sample_field_value(field) for field in template["fields"]}
    created = client.post(
        "/api/contracts",
        json={"template_id": template["id"], "title": "自动化测试合同", "field_values": values},
    )
    assert created.status_code == 201, created.text
    contract = created.json()
    assert contract["status"] == "draft"
    assert re.fullmatch(re.escape(template["contract_code"]) + r"\d{12}", contract["contract_no"])

    submitted = client.post(f"/api/contracts/{contract['id']}/submit")
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "pending"

    assert client.post(
        f"/api/contracts/{contract['id']}/review",
        json={"decision": "approve", "comment": "ok"},
    ).status_code == 403

    login_as(client, "legal", "Legal@123")
    pending = client.get("/api/contracts", params={"status": "pending"}).json()["items"]
    assert any(item["id"] == contract["id"] for item in pending)

    approved = client.post(
        f"/api/contracts/{contract['id']}/review",
        json={"decision": "approve", "comment": "条款核对无误，同意签署。"},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"

    pdf = client.get(f"/api/contracts/{contract['id']}/pdf")
    assert pdf.status_code == 200
    assert pdf.headers["content-type"].startswith("application/pdf")
    assert pdf.content.startswith(b"%PDF")
    assert len(pdf.content) > 10_000


def test_contract_number_uses_template_code_and_daily_sequence(client, login_as):
    login_as(client, "legal", "Legal@123")
    created_template = client.post(
        "/api/templates",
        json={
            "name": "编号规则测试模板",
            "contract_code": "MMDY-",
            "category": "通用",
            "description": "",
            "instructions": "",
            "content": "<p>{{甲方}}</p>",
            "fields": [
                {
                    "key": "甲方",
                    "label": "甲方",
                    "type": "text",
                    "required": False,
                    "hint": "",
                    "placeholder": "",
                    "options": [],
                }
            ],
        },
    )
    assert created_template.status_code == 201, created_template.text
    template = created_template.json()
    login_as(client, "business", "Business@123")
    today = datetime.now().strftime("%Y%m%d")

    first = client.post(
        "/api/contracts",
        json={"template_id": template["id"], "title": "编号规则测试一"},
    )
    second = client.post(
        "/api/contracts",
        json={"template_id": template["id"], "title": "编号规则测试二"},
    )

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert first.json()["contract_no"] == f"MMDY-{today}0001"
    assert second.json()["contract_no"] == f"MMDY-{today}0002"


def test_contract_record_syncs_through_status_transitions(client, login_as, monkeypatch):
    archived: list[dict] = []
    monkeypatch.setattr(
        contract_archive,
        "sync_contract_record",
        lambda **kwargs: archived.append(kwargs),
    )
    login_as(client, "business", "Business@123")
    template = client.get("/api/templates").json()["items"][0]
    values = {field["key"]: sample_field_value(field) for field in template["fields"]}
    contract = client.post(
        "/api/contracts",
        json={
            "template_id": template["id"],
            "title": "归档接口测试合同",
            "field_values": values,
        },
    ).json()
    assert contract_serial_number(contract["contract_no"]) == contract["contract_no"][-4:]
    assert archived[-1]["contract_status"] == "draft"

    updated = client.put(
        f"/api/contracts/{contract['id']}",
        json={
            "title": "归档状态流转测试合同",
            "field_values": values,
        },
    )
    assert updated.status_code == 200, updated.text
    assert archived[-1]["contract_status"] == "draft"

    assert client.post(f"/api/contracts/{contract['id']}/submit").status_code == 200
    assert archived[-1]["contract_status"] == "pending"

    login_as(client, "legal", "Legal@123")
    rejected = client.post(
        f"/api/contracts/{contract['id']}/review",
        json={"decision": "reject", "comment": "请补充付款节点"},
    )
    assert rejected.status_code == 200, rejected.text
    assert archived[-1]["contract_status"] == "rejected"
    assert archived[-1]["approver_name"] == "林静 · 法务专员"
    assert archived[-1]["review_comment"] == "请补充付款节点"
    assert archived[-1]["approved_at"] is None

    login_as(client, "business", "Business@123")
    assert client.put(
        f"/api/contracts/{contract['id']}",
        json={"title": "归档状态流转测试合同", "field_values": values},
    ).status_code == 200
    assert archived[-1]["contract_status"] == "rejected"
    assert client.post(f"/api/contracts/{contract['id']}/submit").status_code == 200
    assert archived[-1]["contract_status"] == "pending"

    login_as(client, "legal", "Legal@123")
    approved = client.post(
        f"/api/contracts/{contract['id']}/review",
        json={"decision": "approve", "comment": "同意归档"},
    )

    assert approved.status_code == 200, approved.text
    assert [item["contract_status"] for item in archived] == [
        "draft",
        "draft",
        "pending",
        "rejected",
        "rejected",
        "pending",
        "approved",
    ]
    payload = archived[-1]
    assert payload["oa_contract_id"] == contract["id"]
    assert payload["contract_no"] == contract["contract_no"]
    assert payload["contract_code"] == template["contract_code"]
    assert payload["contract_name"] == "归档状态流转测试合同"
    assert payload["initiator_name"] == "陈晨 · 商务经理"
    assert payload["approver_name"] == "林静 · 法务专员"
    assert payload["approved_at"]


def test_deleting_draft_removes_company_record(client, login_as, monkeypatch):
    deleted: list[dict] = []
    monkeypatch.setattr(
        contract_archive,
        "delete_contract_record",
        lambda **kwargs: deleted.append(kwargs),
    )
    login_as(client, "business", "Business@123")
    template = client.get("/api/templates").json()["items"][0]
    contract = client.post(
        "/api/contracts",
        json={"template_id": template["id"], "title": "待删除草稿"},
    ).json()

    response = client.delete(f"/api/contracts/{contract['id']}")

    assert response.status_code == 200, response.text
    assert deleted == [{"oa_contract_id": contract["id"]}]


def test_pdf_currency_values_use_plain_thousands_format():
    values = _format_field_values(
        [{"key": "amount", "type": "currency"}],
        {"amount": "268000"},
    )
    assert values["amount"] == "268,000.00"


def test_pdf_date_values_use_chinese_format():
    values = _format_field_values(
        [{"key": "delivery_date", "type": "date"}],
        {"delivery_date": "2026-11-25"},
    )
    assert values["delivery_date"] == "2026年11月25日"


def test_contract_number_placeholder_uses_generated_contract_number():
    values = _contract_document_values(
        {
            "contract_no": "CG202611250001",
            "fields_schema": [],
            "field_values": {},
        }
    )
    assert render_contract_text("合同编号：{{合同编号}}", values) == "合同编号：CG202611250001"


def test_pdf_uses_auto_prepayment_and_final_payment_values():
    values = _contract_document_values(
        {
            "contract_no": "YZ202611250001",
            "template_content": "<p>预付款：{{预付款}}；尾款：{{尾款}}</p>",
            "table_adjustments": {},
            "fields_schema": [
                {"key": "合同金额", "label": "合同金额", "type": "currency"}
            ],
            "field_values": {"合同金额": "1000"},
        }
    )

    assert (
        render_contract_text("预付款：{{预付款}}；尾款：{{尾款}}", values)
        == "预付款：叁佰元整；尾款：柒佰元整"
    )


def test_required_fields_and_template_management(client, login_as):
    login_as(client, "business", "Business@123")
    template = client.get("/api/templates").json()["items"][0]
    contract = client.post(
        "/api/contracts",
        json={"template_id": template["id"], "title": "缺少必填项合同", "field_values": {}},
    ).json()
    response = client.post(f"/api/contracts/{contract['id']}/submit")
    assert response.status_code == 422
    assert response.json()["detail"]["fields"]

    login_as(client, "legal", "Legal@123")
    payload = {
        "name": "自动化测试模板",
        "category": "测试类",
        "description": "用于验证模板 CRUD",
        "instructions": "请完整填写。",
        "content": "测试合同\n\n甲方：{{party_a}}\n乙方：{{party_b}}",
        "fields": [
            {
                "key": "party_a",
                "label": "甲方",
                "type": "text",
                "required": True,
                "hint": "填写全称",
                "placeholder": "",
                "options": [],
            },
            {
                "key": "party_b",
                "label": "乙方",
                "type": "text",
                "required": True,
                "hint": "填写全称",
                "placeholder": "",
                "options": [],
            },
        ],
    }
    created = client.post("/api/templates", json=payload)
    assert created.status_code == 201, created.text
    template_id = created.json()["id"]

    payload["name"] = "自动化测试模板（修订）"
    updated = client.put(f"/api/templates/{template_id}", json=payload)
    assert updated.status_code == 200
    assert updated.json()["name"].endswith("修订）")

    active_delete = client.delete(f"/api/templates/{template_id}/permanent")
    assert active_delete.status_code == 409

    archived = client.delete(f"/api/templates/{template_id}")
    assert archived.status_code == 200
    assert client.get(f"/api/templates/{template_id}").json()["status"] == "archived"

    login_as(client, "business", "Business@123")
    forbidden = client.delete(f"/api/templates/{template_id}/permanent")
    assert forbidden.status_code == 403
    visible = client.get("/api/templates").json()["items"]
    assert all(item["id"] != template_id for item in visible)

    login_as(client, "legal", "Legal@123")
    deleted = client.delete(f"/api/templates/{template_id}/permanent")
    assert deleted.status_code == 200, deleted.text
    assert client.get(f"/api/templates/{template_id}").status_code == 404


def test_permanently_deleting_archived_template_keeps_contract_snapshot(client, login_as):
    login_as(client, "legal", "Legal@123")
    created = client.post(
        "/api/templates",
        json={
            "name": "历史合同快照测试模板",
            "category": "通用",
            "description": "",
            "instructions": "",
            "content": "<p>模板正文：{{甲方}}</p>",
            "fields": [{"key": "甲方", "label": "甲方"}],
        },
    )
    assert created.status_code == 201, created.text
    template = created.json()

    login_as(client, "business", "Business@123")
    contract_response = client.post(
        "/api/contracts",
        json={
            "template_id": template["id"],
            "title": "模板删除后的历史合同",
            "field_values": {"甲方": "测试甲方"},
        },
    )
    assert contract_response.status_code == 201, contract_response.text
    contract = contract_response.json()

    login_as(client, "legal", "Legal@123")
    assert client.delete(f"/api/templates/{template['id']}").status_code == 200
    assert client.delete(f"/api/templates/{template['id']}/permanent").status_code == 200

    login_as(client, "business", "Business@123")
    historical = client.get(f"/api/contracts/{contract['id']}")
    assert historical.status_code == 200, historical.text
    data = historical.json()
    assert data["title"] == "模板删除后的历史合同"
    assert data["template_id"] is None
    assert "模板正文" in data["template_content"]
