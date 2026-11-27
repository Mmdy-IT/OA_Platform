from __future__ import annotations

def create_general_template(client, login_as) -> dict:
    login_as(client, "legal", "Legal@123")
    response = client.post(
        "/api/templates",
        json={
            "name": "合同包通用附件",
            "contract_code": "HT",
            "category": "通用类",
            "description": "合同包配套通用合同",
            "instructions": "",
            "content": "<p>通用合同附件正文</p>",
            "fields": [],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_bundle_creation_defers_general_companion_until_saved(client, login_as):
    login_as(client, "legal", "Legal@123")
    templates = client.get("/api/templates?status=active").json()["items"]
    trigger = next(item for item in templates if item["category"] != "通用类")
    required = create_general_template(client, login_as)
    login_as(client, "legal", "Legal@123")

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
    assert len(contract["bundle"]["members"]) == 1

    ensured = client.post(f"/api/contracts/{contract['id']}/bundle-companions")
    assert ensured.status_code == 200, ensured.text
    assert ensured.json()["next_contract_id"]
    contract = ensured.json()["contract"]
    assert len(contract["bundle"]["members"]) == 2
    assert contract["bundle"]["all_approved"] is False
    companion_id = contract["bundle"]["members"][1]["id"]
    companion = client.get(f"/api/contracts/{companion_id}").json()
    assert companion["title"] == "合同包自动配套测试·合同包通用附件"
    assert companion["template_category"] == "通用类"
    assert companion["contract_no"] == ""
    assert companion["contract_code"] == contract["contract_code"]


def test_bundle_submit_requires_all_members_complete(client, login_as):
    login_as(client, "legal", "Legal@123")
    templates = client.get("/api/templates?status=active").json()["items"]
    trigger = next(item for item in templates if item["category"] != "通用类")
    required = create_general_template(client, login_as)
    login_as(client, "legal", "Legal@123")
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
    ensure_response = client.post(f"/api/contracts/{contract_id}/bundle-companions")
    assert ensure_response.status_code == 200, ensure_response.text
    submitted = client.post(f"/api/contracts/{contract_id}/submit")
    assert submitted.status_code == 422
    assert "空白项" in submitted.json()["detail"]["message"]


def test_general_template_cannot_be_used_as_standalone_contract(client, login_as):
    general = create_general_template(client, login_as)
    login_as(client, "business", "Business@123")

    response = client.post(
        "/api/contracts",
        json={
            "template_id": general["id"],
            "title": "不应创建的通用合同",
            "field_values": {},
        },
    )

    assert response.status_code == 422
    assert "通用类合同模板" in response.json()["detail"]


def test_deleting_one_bundle_member_deletes_the_whole_package(client, login_as):
    login_as(client, "legal", "Legal@123")
    templates = client.get("/api/templates?status=active").json()["items"]
    trigger = next(item for item in templates if item["category"] != "通用类")
    required = create_general_template(client, login_as)
    login_as(client, "legal", "Legal@123")
    assert client.post(
        "/api/bundle-rules",
        json={
            "name": "合同包删除测试",
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
            "title": "合同包删除测试合同",
            "field_values": {},
            "table_adjustments": {},
        },
    )
    assert created.status_code == 201, created.text
    contract = created.json()
    ensured = client.post(f"/api/contracts/{contract['id']}/bundle-companions")
    assert ensured.status_code == 200, ensured.text
    contract = ensured.json()["contract"]
    companion_id = contract["bundle"]["members"][1]["id"]

    deleted = client.delete(f"/api/contracts/{companion_id}")

    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["deleted_count"] == 2
    assert client.get(f"/api/contracts/{contract['id']}").status_code == 404
    assert client.get(f"/api/contracts/{companion_id}").status_code == 404


def test_main_contract_submit_requires_general_companion(client, login_as):
    login_as(client, "legal", "Legal@123")
    templates = client.get("/api/templates?status=active").json()["items"]
    trigger = next(item for item in templates if item["category"] != "通用类")
    required = create_general_template(client, login_as)
    login_as(client, "legal", "Legal@123")
    assert client.post(
        "/api/bundle-rules",
        json={
            "name": "通用合同存在性校验",
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
            "title": "通用合同存在性校验合同",
            "field_values": {},
            "table_adjustments": {},
        },
    )
    assert created.status_code == 201, created.text
    contract = created.json()

    response = client.post(f"/api/contracts/{contract['id']}/submit")

    assert response.status_code == 422
    assert "通用合同模板" in response.json()["detail"]
