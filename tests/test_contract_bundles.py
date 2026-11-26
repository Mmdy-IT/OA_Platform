from __future__ import annotations


def test_bundle_rule_and_automatic_companion_contract(client, login_as):
    login_as(client, "legal", "Legal@123")
    templates = client.get("/api/templates?status=active").json()["items"]
    assert len(templates) >= 2
    trigger = templates[0]
    required = templates[1]

    rule = client.post(
        "/api/bundle-rules",
        json={
            "name": "商务合同包测试",
            "trigger_template_id": trigger["id"],
            "required_template_id": required["id"],
            "enabled": True,
        },
    )
    assert rule.status_code == 201, rule.text
    assert "trigger_department" not in rule.json()

    login_as(client, "business", "Business@123")
    requirements = client.get(
        f"/api/bundle-requirements?template_id={trigger['id']}"
    )
    assert requirements.status_code == 200
    assert [item["id"] for item in requirements.json()["items"]] == [required["id"]]

    created = client.post(
        "/api/contracts/bundle",
        json={
            "template_id": trigger["id"],
            "title": "合同包自动配套测试",
            "field_values": {},
            "table_adjustments": {},
        },
    )
    assert created.status_code == 201, created.text
    contract = created.json()
    assert contract["bundle_id"]
    assert contract["bundle"]["bundle_no"].startswith("BND")
    assert len(contract["bundle"]["members"]) == 2
    assert contract["bundle"]["all_approved"] is False


def test_bundle_submit_requires_all_members_complete(client, login_as):
    login_as(client, "legal", "Legal@123")
    templates = client.get("/api/templates?status=active").json()["items"]
    trigger = templates[0]
    required = templates[1]
    assert client.post(
        "/api/bundle-rules",
        json={
            "name": "合同包提交校验",
            "trigger_template_id": trigger["id"],
            "required_template_id": required["id"],
            "enabled": True,
        },
    ).status_code == 201

    login_as(client, "business", "Business@123")
    created = client.post(
        "/api/contracts/bundle",
        json={
            "template_id": trigger["id"],
            "title": "合同包提交校验测试",
            "field_values": {},
            "table_adjustments": {},
        },
    )
    assert created.status_code == 201
    contract_id = created.json()["id"]
    submitted = client.post(f"/api/contracts/{contract_id}/submit")
    assert submitted.status_code == 422
    assert "合同包" in submitted.json()["detail"]["message"]
