from __future__ import annotations

import pytest

from backend import app as app_module
from backend import user_permissions


class FakeFeishuClient:
    def build_auth_url(self, state: str) -> str:
        return f"https://open.feishu.cn/open-apis/authen/v1/index?state={state}"

    def get_user_info_by_code(self, code: str) -> dict[str, str]:
        assert code == "test-code"
        return {
            "open_id": "ou_test",
            "union_id": "on_test_union",
            "name": "飞书测试用户",
            "department_name": "测试部门",
        }


@pytest.fixture()
def feishu_settings(monkeypatch):
    settings = {
        "enabled": True,
        "app_id": "cli_test",
        "app_secret": "secret",
        "redirect_uri": "http://127.0.0.1:9650/api/auth/feishu/callback",
        "auto_provision": True,
    }
    monkeypatch.setattr(app_module, "get_feishu_settings", lambda: settings)
    monkeypatch.setattr(app_module, "get_feishu_client", lambda: FakeFeishuClient())
    return settings


def test_feishu_login_sets_state_and_redirects(client, feishu_settings):
    response = client.get(
        "/api/auth/feishu/login?next=/contracts", follow_redirects=False
    )
    assert response.status_code == 302
    assert response.headers["location"].startswith(
        "https://open.feishu.cn/open-apis/authen/v1/index"
    )
    assert client.cookies.get("oa_feishu_state")
    assert client.cookies.get("oa_feishu_next")


def test_feishu_callback_creates_oa_session(client, feishu_settings, monkeypatch):
    login_response = client.get(
        "/api/auth/feishu/login?next=/contracts", follow_redirects=False
    )
    state = client.cookies.get("oa_feishu_state")
    assert state

    monkeypatch.setattr(
        user_permissions,
        "ensure_feishu_user",
        lambda **_: {
            "id": 3,
            "username": "business",
            "display_name": "飞书测试用户",
            "role": "business",
            "department": "测试部门",
        },
    )

    response = client.get(
        f"/api/auth/feishu/callback?code=test-code&state={state}",
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/contracts"
    assert client.cookies.get("oa_session")

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["user"]["username"] == "business"


def test_feishu_callback_rejects_invalid_state(client, feishu_settings):
    client.get("/api/auth/feishu/login?next=/contracts", follow_redirects=False)
    response = client.get(
        "/api/auth/feishu/callback?code=test-code&state=wrong",
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/login?feishu_error=state_invalid"
    assert not client.cookies.get("oa_session")
