from __future__ import annotations

from backend import party_db, warehouse_db


PARTY = {
    "party_type": "乙方",
    "contract_code": "",
    "entity_name": "演示主体有限公司",
    "unified_social_credit_code": "91330000TEST000001",
    "account_name": "演示主体有限公司",
    "bank_name": "演示银行杭州分行",
    "bank_branch_code": "305000000001",
    "tax_number": "91330000TEST000001",
    "contact_address": "浙江省杭州市演示路 1 号",
    "contact_phone": "0571-88888888",
}

PARTY_A = {
    **PARTY,
    "party_type": "甲方",
    "contract_code": "MMDY-A",
    "entity_name": "演示甲方有限公司",
    "unified_social_credit_code": "91330000TEST000002",
}

WAREHOUSE = {
    "warehouse_short_name": "临沂云仓",
    "warehouse_address": "临沂市罗庄区龙湖路与广场路交汇南100米路西百七云仓(龙湖路仓)",
}


def test_party_directory_requires_login(client):
    response = client.get("/api/parties")
    assert response.status_code == 401


def test_party_directory_returns_entities(client, login_as, monkeypatch):
    login_as(client, "business", "Business@123")
    monkeypatch.setattr(
        party_db,
        "list_parties",
        lambda force_refresh=False, query="", party_type="": [PARTY],
    )

    response = client.get("/api/parties")

    assert response.status_code == 200
    assert response.json()["items"] == [PARTY]


def test_party_directory_reports_unavailable_database(client, login_as, monkeypatch):
    login_as(client, "business", "Business@123")

    def unavailable(force_refresh=False, query="", party_type=""):
        raise party_db.PartyDatabaseError("offline")

    monkeypatch.setattr(party_db, "list_parties", unavailable)
    response = client.get("/api/parties")

    assert response.status_code == 503
    assert "主体信息库" in response.json()["detail"]


def test_create_party_requires_party_permission(client, login_as):
    login_as(client, "business", "Business@123")
    response = client.post("/api/parties", json=PARTY)
    assert response.status_code == 403


def test_create_party_endpoint(client, login_as, monkeypatch):
    login_as(client, "legal", "Legal@123")
    captured = {}

    def fake_create(values):
        captured.update(values)
        return values

    monkeypatch.setattr(party_db, "create_party", fake_create)
    response = client.post("/api/parties", json=PARTY)

    assert response.status_code == 201
    assert response.json() == PARTY
    assert captured["entity_name"] == PARTY["entity_name"]


def test_create_party_a_requires_contract_code(client, login_as, monkeypatch):
    login_as(client, "legal", "Legal@123")
    captured = {}

    def fake_create(values):
        captured.update(values)
        return values

    monkeypatch.setattr(party_db, "create_party", fake_create)
    response = client.post("/api/parties", json=PARTY_A)

    assert response.status_code == 201, response.text
    assert response.json()["party_type"] == "甲方"
    assert response.json()["contract_code"] == "MMDY-A"
    assert captured["contract_code"] == "MMDY-A"

    missing_code = client.post("/api/parties", json={**PARTY_A, "contract_code": ""})
    assert missing_code.status_code == 422


def test_business_cannot_create_party_a(client, login_as):
    login_as(client, "business", "Business@123")
    response = client.post("/api/parties", json=PARTY_A)
    assert response.status_code == 403


def test_update_party_a_contract_code(client, login_as, monkeypatch):
    login_as(client, "legal", "Legal@123")
    captured = {}

    def fake_update(original_code, values):
        captured["original_code"] = original_code
        captured["values"] = values
        return values

    monkeypatch.setattr(party_db, "update_party", fake_update)
    response = client.put(
        f"/api/parties/{PARTY_A['unified_social_credit_code']}", json=PARTY_A
    )

    assert response.status_code == 200, response.text
    assert captured["original_code"] == PARTY_A["unified_social_credit_code"]
    assert captured["values"]["contract_code"] == "MMDY-A"


def test_create_party_requires_bank_name(client, login_as):
    login_as(client, "legal", "Legal@123")
    payload = {**PARTY, "bank_name": ""}
    response = client.post("/api/parties", json=payload)
    assert response.status_code == 422


def test_warehouse_directory_requires_login(client):
    response = client.get("/api/warehouses")
    assert response.status_code == 401


def test_warehouse_directory_returns_entities(client, login_as, monkeypatch):
    login_as(client, "business", "Business@123")
    monkeypatch.setattr(
        warehouse_db, "list_warehouses", lambda force_refresh=False: [WAREHOUSE]
    )

    response = client.get("/api/warehouses")

    assert response.status_code == 200
    assert response.json()["items"] == [WAREHOUSE]


def test_warehouse_directory_reports_unavailable_database(client, login_as, monkeypatch):
    login_as(client, "business", "Business@123")

    def unavailable(force_refresh=False):
        raise warehouse_db.WarehouseDatabaseError("offline")

    monkeypatch.setattr(warehouse_db, "list_warehouses", unavailable)
    response = client.get("/api/warehouses")

    assert response.status_code == 503
    assert "仓库信息库" in response.json()["detail"]


def test_resolve_warehouse_values_replaces_short_name_for_picker(monkeypatch):
    monkeypatch.setattr(
        warehouse_db, "list_warehouses", lambda force_refresh=False: [WAREHOUSE]
    )
    fields = [
        {
            "key": "仓库简称",
            "label": "仓库简称",
            "auto_fill": "warehouse_address",
        }
    ]

    resolved = warehouse_db.resolve_warehouse_values({"仓库简称": "临沂云仓"}, fields)

    assert resolved == {"仓库简称": WAREHOUSE["warehouse_address"]}


def test_resolve_warehouse_values_keeps_manual_warehouse_field(monkeypatch):
    monkeypatch.setattr(
        warehouse_db, "list_warehouses", lambda force_refresh=False: [WAREHOUSE]
    )
    fields = [{"key": "仓库简称", "label": "仓库简称", "auto_fill": ""}]
    values = {"仓库简称": "临沂云仓"}

    assert warehouse_db.resolve_warehouse_values(values, fields) == values


def test_template_accepts_warehouse_auto_fill(client, login_as):
    login_as(client, "legal", "Legal@123")
    payload = {
        "name": "仓库采购合同",
        "category": "采购类",
        "description": "验证仓库数据来源",
        "instructions": "请选择仓库。",
        "content": "<p>仓库：{{仓库简称}}</p><p>地址：{{仓库地址}}</p>",
        "fields": [
            {
                "key": "仓库简称",
                "label": "仓库简称",
                "auto_fill": "warehouse_short_name",
            },
            {
                "key": "仓库地址",
                "label": "仓库地址",
                "auto_fill": "warehouse_address",
            },
        ],
    }

    response = client.post("/api/templates", json=payload)

    assert response.status_code == 201, response.text
    assert [field["auto_fill"] for field in response.json()["fields"]] == [
        "warehouse_short_name",
        "warehouse_address",
    ]
