from __future__ import annotations

import json

import pytest

from backend import security, user_permissions


class _FakeCursor:
    def __init__(self, row):
        self.row = row

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, *_args, **_kwargs):
        return None

    def fetchone(self):
        return self.row


class _FakeConnection:
    def __init__(self, row):
        self.row = row

    def cursor(self):
        return _FakeCursor(self.row)

    def close(self):
        return None


class _FakeLocalResult:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows


class _FakeLocalConnection:
    def __init__(self, rows):
        self.rows = rows

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, *_args, **_kwargs):
        return _FakeLocalResult(self.rows)


class _RecordingCursor:
    def __init__(self):
        self.statements: list[str] = []

    def execute(self, statement, *_args, **_kwargs):
        self.statements.append(statement)


class _FakeReviewCursor:
    def __init__(self, rows):
        self.rows = list(rows)
        self.calls: list[tuple[str, tuple]] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, statement, params=()):
        self.calls.append((statement, tuple(params or ())))

    def fetchone(self):
        return self.rows.pop(0) if self.rows else None

    def fetchall(self):
        return []


class _FakeReviewConnection:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor

    def close(self):
        return None


def test_login_returns_module_permissions(client, login_as):
    login_as(client, "business", "Business@123")
    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["user"]["permissions"] == ["dashboard", "contracts"]

    login_as(client, "legal", "Legal@123")
    legal = client.get("/api/auth/me").json()["user"]
    assert legal["permissions"] == [
        "dashboard",
        "contracts",
        "party_a",
        "parties",
        "reviews",
        "templates",
    ]


def test_new_user_without_permission_record_gets_ordinary_permissions(monkeypatch):
    monkeypatch.setattr(user_permissions, "_TABLE_READY", True)
    monkeypatch.setattr(
        user_permissions,
        "_connect",
        lambda: _FakeConnection(None),
    )

    permissions = user_permissions._fetch_permissions_for_user(
        {"id": 99, "username": "new-legal", "role": "legal"}
    )

    assert permissions == ("dashboard", "contracts")
    assert user_permissions.new_user_permissions() == ("dashboard", "contracts")


def test_existing_permission_record_is_not_replaced_by_default(monkeypatch):
    monkeypatch.setattr(user_permissions, "_TABLE_READY", True)
    monkeypatch.setattr(
        user_permissions,
        "_connect",
        lambda: _FakeConnection(
            {"role": "legal", "permissions_json": '["templates", "contracts"]'}
        ),
    )

    permissions = user_permissions._fetch_permissions_for_user(
        {"id": 100, "username": "configured-legal", "role": "legal"}
    )

    assert permissions == ("contracts", "templates")


def test_permission_table_role_is_authoritative(monkeypatch):
    monkeypatch.setattr(user_permissions, "_TABLE_READY", True)
    monkeypatch.setattr(
        user_permissions,
        "_connect",
        lambda: _FakeConnection(
            {
                "role": "admin",
                "department": "信息管理部",
                "job_title": "系统管理员",
                "permissions_json": '["dashboard", "contracts"]',
            }
        ),
    )

    profile = user_permissions._fetch_access_profile_for_user(
        {
            "id": 101,
            "username": "local-business",
            "role": "business",
            "department": "本地部门",
        }
    )

    assert profile["role"] == "admin"
    assert profile["department"] == "信息管理部"
    assert profile["permissions"] == ["dashboard", "contracts"]


def test_local_user_sync_does_not_overwrite_remote_role(monkeypatch):
    monkeypatch.setattr(
        user_permissions,
        "db_cursor",
        lambda: _FakeLocalConnection(
            [
                {
                    "id": 3,
                    "username": "feishu_user",
                    "display_name": "本地业务人员",
                    "role": "business",
                    "department": "商务拓展部",
                }
            ]
        ),
    )
    cursor = _RecordingCursor()

    user_permissions._sync_local_users(cursor)

    assert len(cursor.statements) == 1
    update_clause = cursor.statements[0].split("ON DUPLICATE KEY UPDATE", 1)[1]
    assert "`role`" not in update_clause
    assert "`permissions_json`" not in update_clause


def test_local_user_sync_skips_legacy_demo_accounts(monkeypatch):
    monkeypatch.setattr(
        user_permissions,
        "db_cursor",
        lambda: _FakeLocalConnection(
            [
                {
                    "id": 2,
                    "username": "legal",
                    "display_name": "林静",
                    "role": "legal",
                    "department": "法务合规部",
                },
                {
                    "id": 3,
                    "username": "business",
                    "display_name": "陈晨",
                    "role": "business",
                    "department": "商务拓展部",
                },
            ]
        ),
    )
    cursor = _RecordingCursor()

    user_permissions._sync_local_users(cursor)

    assert cursor.statements == []


def test_permission_role_change_is_not_hidden_by_default_cache(monkeypatch):
    rows = [
        {"role": "business", "permissions_json": '["dashboard", "contracts"]'},
        {"role": "admin", "permissions_json": '["dashboard", "contracts"]'},
    ]
    monkeypatch.setattr(user_permissions, "_TABLE_READY", True)
    monkeypatch.setattr(user_permissions, "_CACHE_SECONDS", 0)
    monkeypatch.setattr(user_permissions, "_connect", lambda: _FakeConnection(rows.pop(0)))
    user_permissions.clear_permission_cache()
    user = {"id": 102, "username": "role-change", "role": "business"}

    assert user_permissions.resolve_access_profile(user)["role"] == "business"
    assert user_permissions.resolve_access_profile(user)["role"] == "admin"


def test_business_cannot_access_review_module(client, login_as):
    login_as(client, "business", "Business@123")
    response = client.post(
        "/api/contracts/999/review", json={"decision": "approve", "comment": ""}
    )
    assert response.status_code == 403
    assert "子模块" in response.json()["detail"]


def test_review_scope_requires_explicit_all_parameter(client, login_as, monkeypatch):
    login_as(client, "legal", "Legal@123")
    template = client.get("/api/templates").json()["items"][0]
    created = client.post(
        "/api/contracts",
        json={
            "template_id": template["id"],
            "title": "权限范围测试合同",
            "field_values": {},
            "table_adjustments": {},
        },
    )
    assert created.status_code == 201, created.text
    legal_contract_id = created.json()["id"]

    login_as(client, "business", "Business@123")
    own = client.get("/api/contracts").json()["items"]
    own_ids = {item["id"] for item in own}
    assert legal_contract_id not in own_ids

    def custom_profile(user: dict) -> dict:
        if user.get("username") == "business":
            permissions = ["dashboard", "contracts", "reviews"]
        else:
            permissions = list(
                user_permissions.permission_defaults(user.get("role", "business"))
            )
        return {
            "role": user.get("role", "business"),
            "permissions": permissions,
            "department": user.get("department", ""),
            "job_title": "",
        }

    monkeypatch.setattr(security, "resolve_access_profile", custom_profile)
    monkeypatch.setattr("backend.app.resolve_access_profile", custom_profile)

    login_as(client, "business", "Business@123")
    own_with_review_permission = client.get("/api/contracts").json()["items"]
    assert legal_contract_id not in {item["id"] for item in own_with_review_permission}

    expanded = client.get("/api/contracts", params={"scope": "all"}).json()["items"]
    assert legal_contract_id in {item["id"] for item in expanded}


def test_permission_management_endpoints(client, login_as, monkeypatch):
    record = {
        "id": 7,
        "oa_user_id": 3,
        "union_id": "",
        "username": "business",
        "display_name": "陈晨 · 商务经理",
        "role": "business",
        "department": "商务拓展部",
        "permissions": ["dashboard", "contracts"],
        "updated_at": "2026-11-25T10:00:00",
    }
    monkeypatch.setattr(user_permissions, "list_user_permissions", lambda: [record])

    login_as(client, "business", "Business@123")
    forbidden = client.get("/api/admin/permissions")
    assert forbidden.status_code == 403

    login_as(client, "admin", "Admin@123")
    listed = client.get("/api/admin/permissions")
    assert listed.status_code == 200, listed.text
    payload = listed.json()
    assert payload["items"] == [record]
    assert [item["key"] for item in payload["modules"]] == [
        "dashboard",
        "contracts",
        "party_a",
        "parties",
        "reviews",
        "templates",
    ]

    captured: dict = {}

    def fake_update(record_id: int, *, permissions: list[str], union_id: str) -> dict:
        captured.update(
            {"record_id": record_id, "permissions": permissions, "union_id": union_id}
        )
        return {
            **record,
            "permissions": permissions,
            "union_id": union_id,
        }

    monkeypatch.setattr(user_permissions, "update_user_permission", fake_update)
    updated = client.put(
        "/api/admin/permissions/7",
        json={"permissions": ["dashboard", "contracts", "reviews"], "union_id": "on_123"},
    )
    assert updated.status_code == 200, updated.text
    assert captured == {
        "record_id": 7,
        "permissions": ["dashboard", "contracts", "reviews"],
        "union_id": "on_123",
    }
    assert updated.json()["union_id"] == "on_123"


def test_permission_request_endpoints(client, login_as, monkeypatch):
    record = {
        "id": 12,
        "oa_user_id": 3,
        "username": "business",
        "display_name": "陈晨",
        "permissions": ["reviews", "parties"],
        "reason": "需要处理合同审核和主体维护",
        "status": "pending",
        "reviewer_id": None,
        "reviewer_name": "",
        "review_comment": "",
        "reviewed_at": "",
        "created_at": "2026-11-27T09:00:00",
        "updated_at": "2026-11-27T09:00:00",
    }
    monkeypatch.setattr(
        user_permissions,
        "list_permission_requests",
        lambda _user: [record],
    )
    captured: dict = {}

    def fake_create(user, *, permissions, reason):
        captured.update({"user": user["username"], "permissions": permissions, "reason": reason})
        return {**record, "permissions": permissions, "reason": reason}

    def fake_review(request_id, reviewer, *, decision, comment):
        captured.update(
            {
                "request_id": request_id,
                "reviewer": reviewer["username"],
                "decision": decision,
                "comment": comment,
            }
        )
        return {**record, "status": "approved", "reviewer_name": reviewer["display_name"]}

    monkeypatch.setattr(user_permissions, "create_permission_request", fake_create)
    monkeypatch.setattr(user_permissions, "review_permission_request", fake_review)

    login_as(client, "business", "Business@123")
    listed = client.get("/api/permission-requests")
    assert listed.status_code == 200
    assert listed.json()["can_approve"] is False
    assert listed.json()["items"] == [record]

    created = client.post(
        "/api/permission-requests",
        json={"permissions": ["reviews", "parties"], "reason": record["reason"]},
    )
    assert created.status_code == 201, created.text
    assert captured["permissions"] == ["reviews", "parties"]
    assert captured["reason"] == record["reason"]

    forbidden = client.post(
        "/api/permission-requests/12/review",
        json={"decision": "approve", "comment": "同意"},
    )
    assert forbidden.status_code == 403

    captured.clear()
    login_as(client, "admin", "Admin@123")
    admin_list = client.get("/api/permission-requests")
    assert admin_list.status_code == 200
    assert admin_list.json()["can_approve"] is True
    approved = client.post(
        "/api/permission-requests/12/review",
        json={"decision": "approve", "comment": "同意开通"},
    )
    assert approved.status_code == 200, approved.text
    assert captured == {
        "request_id": 12,
        "reviewer": "admin",
        "decision": "approve",
        "comment": "同意开通",
    }


def test_permission_request_approval_merges_existing_permissions(monkeypatch):
    request_row = {
        "id": 12,
        "oa_user_id": 3,
        "username": "business",
        "display_name": "陈晨",
        "permissions_json": '["reviews", "parties"]',
        "reason": "需要处理合同审核和主体维护",
        "status": "pending",
        "reviewer_id": None,
        "reviewer_name": "",
        "review_comment": "",
        "reviewed_at": None,
        "created_at": "2026-11-27 09:00:00",
        "updated_at": "2026-11-27 09:00:00",
    }
    updated_request = {
        **request_row,
        "status": "approved",
        "reviewer_id": 1,
        "reviewer_name": "系统管理员",
        "review_comment": "同意开通",
    }
    target_permission = {
        "id": 7,
        "permissions_json": '["dashboard", "contracts"]',
    }
    cursor = _FakeReviewCursor([request_row, target_permission, updated_request])
    monkeypatch.setattr(user_permissions, "_TABLE_READY", True)
    monkeypatch.setattr(user_permissions, "_REQUEST_TABLE_READY", True)
    monkeypatch.setattr(
        user_permissions,
        "_connect",
        lambda: _FakeReviewConnection(cursor),
    )

    result = user_permissions.review_permission_request(
        12,
        {"id": 1, "username": "admin", "display_name": "系统管理员"},
        decision="approve",
        comment="同意开通",
    )

    permission_updates = [
        params
        for statement, params in cursor.calls
        if "UPDATE" in statement
        and "permissions_json" in statement
        and params
        and str(params[0]).startswith("[")
    ]
    assert permission_updates
    merged = set(json.loads(permission_updates[0][0]))
    assert merged == {"dashboard", "contracts", "reviews", "parties"}
    assert result["status"] == "approved"
    assert result["reviewer_name"] == "系统管理员"


def test_permission_values_are_validated(monkeypatch):
    with pytest.raises(user_permissions.UserPermissionValidationError):
        user_permissions._normalize_permission_keys(["dashboard", "unknown"])

    assert user_permissions._load_permissions_json(
        '["templates", "contracts", "contracts", "bad"]', "business"
    ) == ("contracts", "templates")
