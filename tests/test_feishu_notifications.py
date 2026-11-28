from __future__ import annotations

from backend import feishu_notify, user_permissions


class FakeFeishuClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def send_card(self, receive_id: str, card: dict, **kwargs) -> dict:
        self.calls.append(
            {"receive_id": receive_id, "card": card, **kwargs}
        )
        return {"code": 0}


def create_contract(client) -> dict:
    template = client.get("/api/templates").json()["items"][0]
    response = client.post(
        "/api/contracts",
        json={
            "template_id": template["id"],
            "title": "飞书通知测试合同",
            "field_values": {},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def action_button(card: dict) -> dict:
    elements = card["elements"]
    action = next(item for item in elements if item.get("tag") == "action")
    return action["actions"][0]


def test_submission_notifies_all_legal_users_with_approval_link(
    client, login_as, monkeypatch
):
    login_as(client, "business", "Business@123")
    contract = create_contract(client)
    fake = FakeFeishuClient()
    monkeypatch.setattr(feishu_notify, "get_feishu_client", lambda: fake)
    monkeypatch.setattr(
        feishu_notify,
        "get_feishu_settings",
        lambda: {"public_base_url": "http://oa.example.com"},
    )
    monkeypatch.setattr(
        user_permissions,
        "list_feishu_recipients",
        lambda role: [
            {"union_id": "on_legal_1", "display_name": "法务一"},
            {"union_id": "on_legal_2", "display_name": "法务二"},
        ],
    )

    feishu_notify.notify_legal_contract_pending(contract["id"])

    assert [item["receive_id"] for item in fake.calls] == [
        "on_legal_1",
        "on_legal_2",
    ]
    button = action_button(fake.calls[0]["card"])
    assert button["text"]["content"] == "去审批"
    assert button["url"] == f"http://oa.example.com/contracts/{contract['id']}"


def test_review_result_notifies_contract_creator(client, login_as, monkeypatch):
    login_as(client, "business", "Business@123")
    contract = create_contract(client)
    fake = FakeFeishuClient()
    monkeypatch.setattr(feishu_notify, "get_feishu_client", lambda: fake)
    monkeypatch.setattr(
        feishu_notify,
        "get_feishu_settings",
        lambda: {"public_base_url": "http://oa.example.com"},
    )
    monkeypatch.setattr(
        user_permissions,
        "feishu_union_id_for_oa_user",
        lambda user_id: "on_creator",
    )

    feishu_notify.notify_contract_review_result(
        contract["id"],
        decision="reject",
        comment="请补充付款节点",
        reviewer_name="林静",
    )

    rejected_card = fake.calls[0]["card"]
    rejected_text = str(rejected_card)
    assert "请补充付款节点" in rejected_text
    assert action_button(rejected_card)["text"]["content"] == "去修改"
    assert action_button(rejected_card)["url"] == (
        f"http://oa.example.com/contracts/{contract['id']}/edit"
    )

    fake.calls.clear()
    feishu_notify.notify_contract_review_result(
        contract["id"],
        decision="approve",
        comment="",
        reviewer_name="林静",
    )
    approved_card = fake.calls[0]["card"]
    assert action_button(approved_card)["text"]["content"] == "去下载"
    assert action_button(approved_card)["url"] == (
        f"http://oa.example.com/contracts/{contract['id']}"
    )


class FakeQueryCursor:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows

    def execute(self, *_args, **_kwargs):
        return self

    def fetchone(self):
        return self.rows.pop(0)


class FakeQueryConnection:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows

    def execute(self, *_args, **_kwargs):
        return FakeQueryCursor(self.rows)


class FakeDbCursor:
    def __init__(self, rows: list[dict]) -> None:
        self.connection = FakeQueryConnection(rows)

    def __enter__(self):
        return self.connection

    def __exit__(self, *_args):
        return False


def test_bundle_approval_waits_for_all_members_before_download(
    monkeypatch, client, login_as
):
    login_as(client, "business", "Business@123")
    contract = create_contract(client)
    fake = FakeFeishuClient()
    monkeypatch.setattr(feishu_notify, "get_feishu_client", lambda: fake)
    monkeypatch.setattr(
        feishu_notify,
        "get_feishu_settings",
        lambda: {"public_base_url": "http://oa.example.com"},
    )
    monkeypatch.setattr(
        user_permissions, "feishu_union_id_for_oa_user", lambda _user_id: "on_creator"
    )
    bundle_contract = {
        "id": contract["id"],
        "bundle_id": 5,
        "title": contract["title"],
        "contract_no": contract["contract_no"],
        "creator_id": 3,
    }
    monkeypatch.setattr(
        feishu_notify,
        "db_cursor",
        lambda: FakeDbCursor([bundle_contract, {"total": 2, "approved": 1}]),
    )

    feishu_notify.notify_contract_review_result(
        contract["id"],
        decision="approve",
        comment="",
        reviewer_name="林静",
    )

    partial_card = fake.calls[0]["card"]
    assert action_button(partial_card)["text"]["content"] == "查看进度"
    assert "还有 1 份合同待审核" in str(partial_card)

    fake.calls.clear()
    monkeypatch.setattr(
        feishu_notify,
        "db_cursor",
        lambda: FakeDbCursor([bundle_contract, {"total": 2, "approved": 2}]),
    )
    feishu_notify.notify_contract_review_result(
        contract["id"],
        decision="approve",
        comment="",
        reviewer_name="林静",
    )
    assert action_button(fake.calls[0]["card"])["text"]["content"] == "去下载"
