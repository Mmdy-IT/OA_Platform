from __future__ import annotations


def create_contract(client) -> dict:
    template = client.get("/api/templates").json()["items"][0]
    response = client.post(
        "/api/contracts",
        json={
            "template_id": template["id"],
            "title": "附件上传测试合同",
            "field_values": {},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_contract_attachment_upload_download_and_delete(client, login_as):
    login_as(client, "business", "Business@123")
    contract = create_contract(client)

    uploaded = client.post(
        f"/api/contracts/{contract['id']}/attachments",
        files=[
            (
                "files",
                (
                    "报价单.xlsx",
                    b"xlsx-content",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
            ),
            ("files", ("现场照片.png", b"png-content", "image/png")),
            ("files", ("补充说明.pdf", b"pdf-content", "application/pdf")),
        ],
    )

    assert uploaded.status_code == 201, uploaded.text
    items = uploaded.json()["items"]
    assert [item["original_name"] for item in items] == [
        "报价单.xlsx",
        "现场照片.png",
        "补充说明.pdf",
    ]

    detail = client.get(f"/api/contracts/{contract['id']}")
    assert detail.status_code == 200
    assert len(detail.json()["attachments"]) == 3

    downloaded = client.get(f"/api/attachments/{items[1]['id']}/download")
    assert downloaded.status_code == 200
    assert downloaded.content == b"png-content"

    deleted = client.delete(f"/api/attachments/{items[1]['id']}")
    assert deleted.status_code == 200
    remaining = client.get(f"/api/contracts/{contract['id']}/attachments")
    assert [item["id"] for item in remaining.json()["items"]] == [
        items[0]["id"],
        items[2]["id"],
    ]


def test_contract_attachment_rejects_unsupported_extension(client, login_as):
    login_as(client, "business", "Business@123")
    contract = create_contract(client)

    response = client.post(
        f"/api/contracts/{contract['id']}/attachments",
        files=[("files", ("恶意程序.exe", b"binary", "application/octet-stream"))],
    )

    assert response.status_code == 422
    assert "不支持的附件格式" in response.json()["detail"]


def test_contract_attachment_upload_requires_login(client):
    response = client.post(
        "/api/contracts/1/attachments",
        files=[("files", ("图片.png", b"png", "image/png"))],
    )
    assert response.status_code == 401
