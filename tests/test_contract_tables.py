from __future__ import annotations

from lxml import html as lxml_html

from backend.tables import apply_table_adjustments, normalize_table_adjustments


TABLE_CONTENT = """
<p>设备清单合同</p>
<table>
  <thead><tr><th>设备名称</th><th>数量</th></tr></thead>
  <tbody>
    <tr><td>打印机</td><td>2</td></tr>
    <tr><td>显示器</td><td>6</td></tr>
  </tbody>
</table>
"""


def _table_rows(content: str) -> list[list[str]]:
    root = lxml_html.fragment_fromstring(content, create_parent="div")
    return [
        [cell.text_content().strip() for cell in row.xpath("./td | ./th")]
        for row in root.xpath(".//table//tr")
    ]


def test_apply_table_adjustments_inserts_and_deletes_body_rows():
    adjusted = apply_table_adjustments(
        TABLE_CONTENT,
        {"0": [1, {"id": "row-new", "cells": ["键盘", "3"]}, 0]},
    )
    rows = _table_rows(adjusted)

    assert rows[0] == ["设备名称", "数量"]
    assert rows[1] == ["显示器", "6"]
    assert rows[2] == ["键盘", "3"]
    assert rows[3] == ["打印机", "2"]


def test_table_adjustments_are_validated_and_keep_one_row():
    assert normalize_table_adjustments(TABLE_CONTENT, {"0": [0, 1]}) == {}
    assert normalize_table_adjustments(TABLE_CONTENT, {"9": [0]}) == {}
    fallback = normalize_table_adjustments(TABLE_CONTENT, {"0": [99, None]})
    assert fallback["0"][0]["cells"] == ["", ""]
    empty = normalize_table_adjustments(TABLE_CONTENT, {"0": []})
    assert empty["0"][0]["cells"] == ["", ""]


def test_contract_table_rows_round_trip_and_generate_pdf(client, login_as):
    login_as(client, "legal", "Legal@123")
    template_response = client.post(
        "/api/templates",
        json={
            "name": "表格行测试模板",
            "category": "测试类",
            "description": "验证合同起草时可增删表格正文行",
            "instructions": "仅可调整表格行数。",
            "content": TABLE_CONTENT,
            "fields": [],
        },
    )
    assert template_response.status_code == 201, template_response.text
    template_id = template_response.json()["id"]

    login_as(client, "business", "Business@123")
    created = client.post(
        "/api/contracts",
        json={
            "template_id": template_id,
            "title": "表格行测试合同",
            "field_values": {},
            "table_adjustments": {
                "0": [0, {"id": "row-new", "cells": ["键盘", "3"]}, 1]
            },
        },
    )
    assert created.status_code == 201, created.text
    contract = created.json()
    created_rows = contract["table_adjustments"]["0"]
    assert created_rows[0] == 0
    assert created_rows[1]["id"] == "row-new"
    assert created_rows[1]["cells"] == ["键盘", "3"]
    assert created_rows[2] == 1

    updated = client.put(
        f"/api/contracts/{contract['id']}",
        json={
            "title": contract["title"],
            "field_values": {},
            "table_adjustments": {
                "0": [{"id": "row-new", "cells": ["键盘", "3"]}, 1]
            },
        },
    )
    assert updated.status_code == 200, updated.text
    updated_rows = updated.json()["table_adjustments"]["0"]
    assert updated_rows[0]["id"] == "row-new"
    assert updated_rows[0]["cells"] == ["键盘", "3"]
    assert updated_rows[1] == 1

    submitted = client.post(f"/api/contracts/{contract['id']}/submit")
    assert submitted.status_code == 200, submitted.text

    login_as(client, "legal", "Legal@123")
    approved = client.post(
        f"/api/contracts/{contract['id']}/review",
        json={"decision": "approve", "comment": "表格行调整无误。"},
    )
    assert approved.status_code == 200, approved.text

    pdf = client.get(f"/api/contracts/{contract['id']}/pdf")
    assert pdf.status_code == 200
    assert pdf.content.startswith(b"%PDF")
    assert len(pdf.content) > 10_000
