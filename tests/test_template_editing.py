from __future__ import annotations

from io import BytesIO

from docx import Document

from backend.richtext import extract_placeholders, fields_from_placeholders, next_version


def _payload(content: str, fields: list[dict], name: str = "中文占位符模板") -> dict:
    return {
        "name": name,
        "category": "采购类",
        "description": "验证中文占位符与自动版本号",
        "instructions": "请按实际业务填写。",
        "content": content,
        "fields": fields,
    }


def _docx_bytes() -> bytes:
    document = Document()
    document.add_heading("设备采购合同", level=1)
    paragraph = document.add_paragraph()
    paragraph.add_run("甲方：")
    emphasized = paragraph.add_run("{{甲方}}")
    emphasized.bold = True
    paragraph.add_run("    乙方：{{乙方}}")
    amount = document.add_paragraph()
    amount.add_run("合同金额：")
    amount.add_run("{{合同金额}}")
    amount.add_run(" 元（大写：{{金额大写}}）")

    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "设备名称"
    table.cell(0, 1).text = "数量"
    table.cell(1, 0).text = "服务器"
    table.cell(1, 1).text = "2"

    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def test_chinese_placeholders_are_accepted_and_invalid_keys_rejected(client, login_as):
    login_as(client, "legal", "Legal@123")
    content = (
        "<h2>采购合同</h2>"
        "<p>甲方：{{甲方}}</p>"
        "<p>乙方：{{乙方}}</p>"
        "<p>合同金额：{{合同金额}}</p>"
    )
    fields = [
        {"key": "甲方", "label": "甲方"},
        {"key": "乙方", "label": "乙方"},
        {"key": "合同金额", "label": "合同金额", "type": "currency"},
    ]
    assert extract_placeholders(content) == ["甲方", "乙方", "合同金额"]

    created = client.post("/api/templates", json=_payload(content, fields))
    assert created.status_code == 201, created.text
    assert created.json()["version"] == "V1.0"

    invalid = client.post(
        "/api/templates",
        json=_payload(content, fields + [{"key": "1甲方", "label": "非法字段"}]),
    )
    assert invalid.status_code == 422

    undefined = client.post(
        "/api/templates",
        json=_payload(content + "<p>{{未定义}}</p>", fields),
    )
    assert undefined.status_code == 422
    assert "未定义的空白项" in undefined.text


def test_contract_number_is_a_system_placeholder(client, login_as):
    login_as(client, "legal", "Legal@123")
    content = "<p>合同编号：{{合同编号}}</p><p>甲方：{{甲方}}</p>"
    fields = [{"key": "甲方", "label": "甲方"}]

    created = client.post("/api/templates", json=_payload(content, fields))
    assert created.status_code == 201, created.text

    reserved = client.post(
        "/api/templates",
        json=_payload(content, fields + [{"key": "合同编号", "label": "合同编号"}]),
    )
    assert reserved.status_code == 422
    assert "由系统自动生成" in reserved.text

    imported_keys = [field["key"] for field in fields_from_placeholders(["合同编号", "甲方"])]
    assert imported_keys == ["甲方"]


def test_payment_placeholders_are_auto_fields_without_configuration(client, login_as):
    login_as(client, "legal", "Legal@123")
    content = (
        "<p>合同金额：{{合同金额}}</p>"
        "<p>预付款：{{预付款}}</p>"
        "<p>尾款：{{尾款}}</p>"
    )
    fields = [{"key": "合同金额", "label": "合同金额", "type": "currency"}]

    created = client.post("/api/templates", json=_payload(content, fields))
    assert created.status_code == 201, created.text

    imported_keys = [
        field["key"]
        for field in fields_from_placeholders(["预付款", "尾款", "合同金额"])
    ]
    assert imported_keys == ["合同金额"]


def test_version_upgrades_only_when_content_or_fields_change(client, login_as):
    login_as(client, "legal", "Legal@123")
    payload = _payload(
        "<p>甲方：{{甲方}}</p><p>乙方：{{乙方}}</p>",
        [{"key": "甲方", "label": "甲方"}, {"key": "乙方", "label": "乙方"}],
        name="版本号测试模板",
    )
    created = client.post("/api/templates", json=payload)
    assert created.status_code == 201, created.text
    template_id = created.json()["id"]
    assert created.json()["version"] == "V1.0"

    payload["name"] = "版本号测试模板（改名）"
    renamed = client.put(f"/api/templates/{template_id}", json=payload)
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["version"] == "V1.0"

    payload["content"] = "<p>甲方：{{甲方}}</p><p>乙方：{{乙方}}</p><p>签订日期：{{签订日期}}</p>"
    payload["fields"].append({"key": "签订日期", "label": "签订日期", "type": "date"})
    revised = client.put(f"/api/templates/{template_id}", json=payload)
    assert revised.status_code == 200, revised.text
    assert revised.json()["version"] == "V1.1"

    assert next_version("V1.9") == "V1.10"
    assert next_version("") == "V1.0"


def test_docx_import_extracts_chinese_placeholders_and_table(client, login_as):
    login_as(client, "legal", "Legal@123")
    response = client.post(
        "/api/templates/import",
        files={
            "file": (
                "设备采购合同.docx",
                _docx_bytes(),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    assert response.status_code == 200, response.text
    draft = response.json()

    assert draft["source"]["type"] == "docx"
    assert draft["source"]["placeholder_count"] == 4
    keys = [field["key"] for field in draft["fields"]]
    assert keys == ["甲方", "乙方", "合同金额", "金额大写"]
    field_types = {field["key"]: field["type"] for field in draft["fields"]}
    assert field_types["合同金额"] == "currency"
    assert field_types["金额大写"] == "text"
    assert "<table" in draft["content"]
    assert "{{甲方}}" in draft["content"]
    assert "<strong>" in draft["content"]
    assert draft["name"] == "设备采购合同"

    saved = client.post(
        "/api/templates",
        json={key: draft[key] for key in ("name", "category", "description", "instructions", "content", "fields")},
    )
    assert saved.status_code == 201, saved.text
    assert saved.json()["version"] == "V1.0"


def test_import_requires_legal_role_and_supported_extension(client, login_as):
    login_as(client, "business", "Business@123")
    forbidden = client.post(
        "/api/templates/import",
        files={"file": ("合同.docx", _docx_bytes(), "application/octet-stream")},
    )
    assert forbidden.status_code == 403

    login_as(client, "legal", "Legal@123")
    unsupported = client.post(
        "/api/templates/import",
        files={"file": ("合同.txt", b"hello", "text/plain")},
    )
    assert unsupported.status_code == 400

    empty = client.post(
        "/api/templates/import",
        files={"file": ("合同.docx", b"", "application/octet-stream")},
    )
    assert empty.status_code == 400
