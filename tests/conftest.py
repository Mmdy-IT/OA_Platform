from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend import (
    contract_archive,
    db,
    feishu_notify,
    party_db,
    security,
    user_permissions,
)
from backend.app import app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("OA_PASSWORD_LOGIN_ENABLED", "true")
    monkeypatch.setattr(db, "DATA_DIR", tmp_path)
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "oa.db")
    monkeypatch.setattr(contract_archive, "sync_contract_record", lambda **_: None)
    monkeypatch.setattr(contract_archive, "delete_contract_record", lambda **_: None)
    class NoopFeishuClient:
        def send_card(self, *_, **__):
            return {"code": 0}

    monkeypatch.setattr(feishu_notify, "get_feishu_client", NoopFeishuClient)
    monkeypatch.setattr(
        user_permissions, "list_feishu_recipients", lambda _role: []
    )
    monkeypatch.setattr(
        user_permissions, "feishu_union_id_for_oa_user", lambda _user_id: ""
    )
    def fake_list_parties(force_refresh=False, query="", party_type=""):
        if party_type != "甲方":
            return []
        entity_name = (query or "测试甲方").strip()
        return [
            {
                "party_type": "甲方",
                "party_no": "TEST",
                "entity_name": entity_name,
                "unified_social_credit_code": "",
                "account_name": "",
                "bank_name": "",
                "bank_branch_code": "",
                "tax_number": "",
                "contact_address": "",
                "contact_phone": "",
            }
        ]

    monkeypatch.setattr(party_db, "list_parties", fake_list_parties)

    def test_profile(user: dict) -> dict:
        return {
            "role": user.get("role", "business"),
            "permissions": list(
                user_permissions.permission_defaults(user.get("role", "business"))
            ),
            "department": user.get("department", ""),
            "job_title": "",
        }

    monkeypatch.setattr(security, "resolve_access_profile", test_profile)
    monkeypatch.setattr("backend.app.resolve_access_profile", test_profile)
    with TestClient(app) as test_client:
        yield test_client


def login(client: TestClient, username: str, password: str) -> None:
    response = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200, response.text


@pytest.fixture()
def login_as():
    return login
