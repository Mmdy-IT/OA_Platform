from __future__ import annotations

import json
import logging
import os
import re
import secrets
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote, unquote

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import contract_archive, party_db, user_permissions, warehouse_db
from .amounts import apply_auto_amounts, apply_table_row_auto_values
from .contract_number import DEFAULT_CONTRACT_CODE, next_contract_number
from .config import get_feishu_settings, password_login_enabled
from .db import BASE_DIR, db_cursor, init_db, utcnow
from .feishu import FeishuAuthError, get_feishu_client
from .field_validation import invalid_field_summary, invalid_field_values
from .importers import import_document
from .pdf import build_contract_pdf
from .richtext import (
    SYSTEM_PLACEHOLDER_KEYS,
    extract_placeholders,
    fields_from_placeholders,
    next_version,
    normalize_content,
)
from .schemas import (
    ContractCreate,
    ContractUpdate,
    BundleRulePayload,
    LoginRequest,
    PartyCreate,
    PermissionUpdate,
    ReviewRequest,
    TemplatePayload,
    normalize_field_values,
)
from .security import (
    SESSION_COOKIE,
    create_session,
    delete_session,
    get_current_user,
    require_permission,
    require_roles,
    verify_password,
)
from .tables import normalize_table_adjustments
from .user_permissions import resolve_access_profile


FRONTEND_DIST = BASE_DIR / "frontend" / "dist"
MAX_TEMPLATE_IMPORT_BYTES = 12 * 1024 * 1024
FEISHU_STATE_COOKIE = "oa_feishu_state"
FEISHU_NEXT_COOKIE = "oa_feishu_next"
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="绵绵聚道 · OA 平台",
    description="绵绵聚道内部协同办公平台，一期上线合同模板、合同起草、法务审核与 PDF 下载",
    version="1.0.0",
    lifespan=lifespan,
)

cors_origins = [
    item.strip()
    for item in os.getenv("OA_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
    if item.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if (FRONTEND_DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")


def _load_json(raw: str | None, default):
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return default


def _public_user(user: dict) -> dict:
    data = {
        key: user.get(key)
        for key in (
            "id",
            "username",
            "display_name",
            "role",
            "department",
            "job_title",
        )
    }
    data["permissions"] = list(user.get("permissions") or [])
    return data


def _cookie_secure() -> bool:
    return os.getenv("OA_SECURE_COOKIE", "false").lower() == "true"


def _set_session_cookie(response: Response, token: str, max_age: int) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=max_age,
        httponly=True,
        samesite="lax",
        secure=_cookie_secure(),
    )


def _safe_next_path(value: str | None, default: str = "/dashboard") -> str:
    candidate = (value or "").strip()
    if not candidate.startswith("/") or candidate.startswith("//"):
        return default
    return candidate


def _decode_cookie_value(value: str | None) -> str:
    candidate = (value or "").strip()
    if len(candidate) >= 2 and candidate.startswith('"') and candidate.endswith('"'):
        candidate = candidate[1:-1]
    return unquote(candidate)


def _feishu_login_error(code: str) -> RedirectResponse:
    return RedirectResponse(f"/login?feishu_error={quote(code)}", status_code=302)


def _template_dict(row) -> dict:
    data = dict(row)
    data["fields"] = _filter_system_fields(_load_json(data.pop("fields_json", "[]"), []))
    return data


def _filter_system_fields(fields: list[dict]) -> list[dict]:
    return [
        field
        for field in fields
        if str(field.get("key", "")).strip() not in SYSTEM_PLACEHOLDER_KEYS
    ]


def _sync_contract_archive(
    *,
    oa_contract_id: int,
    contract_no: str,
    contract_code: str,
    contract_name: str,
    contract_status: str,
    initiator_name: str,
    template_name: str,
    template_version: str,
    approver_name: str = "",
    review_comment: str = "",
    approved_at: str | None = None,
) -> None:
    try:
        contract_archive.sync_contract_record(
            oa_contract_id=oa_contract_id,
            contract_no=contract_no,
            contract_code=contract_code,
            contract_name=contract_name,
            contract_status=contract_status,
            initiator_name=initiator_name,
            approver_name=approver_name,
            template_name=template_name,
            template_version=template_version,
            review_comment=review_comment,
            approved_at=approved_at,
        )
    except contract_archive.ContractArchiveError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _contract_summary(row) -> dict:
    keys = (
        "id",
        "contract_no",
        "contract_code",
        "title",
        "template_name",
        "template_version",
        "bundle_id",
        "status",
        "creator_id",
        "creator_name",
        "created_at",
        "updated_at",
        "submitted_at",
        "reviewed_at",
        "review_comment",
    )
    return {key: row[key] for key in keys}


def _event_dict(row) -> dict:
    return {
        "id": row["id"],
        "action": row["action"],
        "actor_name": row["actor_name"],
        "from_status": row["from_status"],
        "to_status": row["to_status"],
        "comment": row["comment"],
        "created_at": row["created_at"],
    }


def _bundle_members(conn, bundle_id: int) -> list[dict]:
    rows = conn.execute(
        """
        SELECT id, contract_no, title, template_name, status, updated_at
          FROM contracts
         WHERE bundle_id = ?
         ORDER BY id ASC
        """,
        (bundle_id,),
    ).fetchall()
    return [
        {
            "id": row["id"],
            "contract_no": row["contract_no"],
            "title": row["title"],
            "template_name": row["template_name"],
            "status": row["status"],
            "updated_at": row["updated_at"],
        }
        for row in rows
    ]


def _bundle_dict(conn, bundle_id: int) -> dict | None:
    row = conn.execute(
        "SELECT * FROM contract_bundles WHERE id = ?", (bundle_id,)
    ).fetchone()
    if not row:
        return None
    members = _bundle_members(conn, bundle_id)
    return {
        "id": row["id"],
        "bundle_no": row["bundle_no"],
        "creator_name": row["creator_name"],
        "department": row["department"],
        "members": members,
        "all_approved": bool(members)
        and all(item["status"] == "approved" for item in members),
    }


def _bundle_number(conn, now: str) -> str:
    date_part = now[:10].replace("-", "")
    prefix = f"BND{date_part}"
    row = conn.execute(
        "SELECT COUNT(*) AS total FROM contract_bundles WHERE bundle_no LIKE ?",
        (f"{prefix}%",),
    ).fetchone()
    sequence = int(row["total"] or 0) + 1
    while True:
        candidate = f"{prefix}{sequence:04d}"
        exists = conn.execute(
            "SELECT 1 FROM contract_bundles WHERE bundle_no = ?", (candidate,)
        ).fetchone()
        if not exists:
            return candidate
        sequence += 1


def _required_bundle_templates(conn, template_id: int, department: str) -> list[dict]:
    rows = conn.execute(
        """
        SELECT r.id AS rule_id, r.name AS rule_name, r.required_template_id,
               t.name, t.category, t.version
          FROM contract_bundle_rules r
          JOIN templates t ON t.id = r.required_template_id
         WHERE r.enabled = 1
           AND r.trigger_template_id = ?
           AND (r.trigger_department = '' OR r.trigger_department = ?)
           AND t.status = 'active'
         ORDER BY r.id ASC
        """,
        (template_id, department or ""),
    ).fetchall()
    unique: dict[int, dict] = {}
    for row in rows:
        unique.setdefault(
            int(row["required_template_id"]),
            {
                "rule_id": row["rule_id"],
                "rule_name": row["rule_name"],
                "id": row["required_template_id"],
                "name": row["name"],
                "category": row["category"],
                "version": row["version"],
            },
        )
    return list(unique.values())


def _insert_contract_record(
    conn,
    template_row,
    *,
    title: str,
    field_values: dict,
    table_adjustments: dict,
    user: dict,
    bundle_id: int | None = None,
) -> int:
    fields = _load_json(template_row["fields_json"], [])
    values = normalize_field_values(field_values)
    values = warehouse_db.resolve_warehouse_values(values, fields)
    adjustments = normalize_table_adjustments(
        template_row["content"], table_adjustments
    )
    adjustments = apply_table_row_auto_values(template_row["content"], adjustments)
    values = apply_auto_amounts(template_row["content"], adjustments, fields, values)
    values = _filter_values(values, fields)
    _ensure_valid_field_values(fields, values)
    now = utcnow()
    contract_code = template_row["contract_code"] or DEFAULT_CONTRACT_CODE
    try:
        contract_no = next_contract_number(conn, contract_code)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    cursor = conn.execute(
        """
        INSERT INTO contracts(
            contract_no, contract_code, template_id, template_name, template_version,
            template_content, fields_schema_json, title, field_values_json,
            table_adjustments_json, bundle_id,
            status, creator_id, creator_name, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'draft', ?, ?, ?, ?)
        """,
        (
            contract_no,
            contract_code,
            template_row["id"],
            template_row["name"],
            template_row["version"],
            template_row["content"],
            template_row["fields_json"],
            title.strip(),
            json.dumps(values, ensure_ascii=False),
            json.dumps(adjustments, ensure_ascii=False),
            bundle_id,
            user["id"],
            user["display_name"],
            now,
            now,
        ),
    )
    contract_id = cursor.lastrowid
    _insert_event(conn, contract_id, "created", user, None, "draft", "创建合同草稿")
    _sync_contract_archive(
        oa_contract_id=contract_id,
        contract_no=contract_no,
        contract_code=contract_code,
        contract_name=title.strip(),
        contract_status="draft",
        initiator_name=user["display_name"],
        template_name=template_row["name"],
        template_version=template_row["version"],
    )
    return contract_id


def _submit_bundle(conn, row, user: dict) -> dict:
    members = conn.execute(
        "SELECT * FROM contracts WHERE bundle_id = ? ORDER BY id ASC",
        (row["bundle_id"],),
    ).fetchall()
    if not members:
        raise HTTPException(status_code=409, detail="合同包内没有合同")

    for member in members:
        if member["status"] in {"pending", "approved"}:
            continue
        fields = _load_json(member["fields_schema_json"], [])
        values = _load_json(member["field_values_json"], {})
        adjustments = _load_json(member["table_adjustments_json"], {})
        adjustments = apply_table_row_auto_values(member["template_content"], adjustments)
        values = warehouse_db.resolve_warehouse_values(values, fields)
        values = apply_auto_amounts(member["template_content"], adjustments, fields, values)
        values = _filter_values(values, fields)
        _ensure_valid_field_values(fields, values)
        missing = _missing_required(fields, values)
        if missing:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": f"合同包内《{member['title']}》尚未填写完整",
                    "fields": missing,
                },
            )

    now = utcnow()
    for member in members:
        if member["status"] in {"pending", "approved"}:
            continue
        fields = _load_json(member["fields_schema_json"], [])
        values = _load_json(member["field_values_json"], {})
        adjustments = _load_json(member["table_adjustments_json"], {})
        adjustments = apply_table_row_auto_values(member["template_content"], adjustments)
        values = warehouse_db.resolve_warehouse_values(values, fields)
        values = apply_auto_amounts(member["template_content"], adjustments, fields, values)
        conn.execute(
            """
            UPDATE contracts
               SET status = 'pending', submitted_at = ?, updated_at = ?,
                   field_values_json = ?, table_adjustments_json = ?,
                   reviewed_at = NULL, reviewer_id = NULL, reviewer_name = NULL,
                   review_comment = ''
             WHERE id = ?
            """,
            (
                now,
                now,
                json.dumps(values, ensure_ascii=False),
                json.dumps(adjustments, ensure_ascii=False),
                member["id"],
            ),
        )
        _insert_event(
            conn,
            member["id"],
            "submitted",
            user,
            member["status"],
            "pending",
            "合同包提交法务审核",
        )
        _sync_contract_archive(
            oa_contract_id=member["id"],
            contract_no=member["contract_no"],
            contract_code=member["contract_code"] or DEFAULT_CONTRACT_CODE,
            contract_name=member["title"],
            contract_status="pending",
            initiator_name=member["creator_name"],
            template_name=member["template_name"],
            template_version=member["template_version"],
        )

    conn.execute(
        "UPDATE contract_bundles SET updated_at = ? WHERE id = ?",
        (now, row["bundle_id"]),
    )
    return _fetch_contract(conn, row["id"], user)


def _bundle_rule_dict(row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "trigger_department": row["trigger_department"],
        "trigger_template_id": row["trigger_template_id"],
        "trigger_template_name": row["trigger_template_name"],
        "required_template_id": row["required_template_id"],
        "required_template_name": row["required_template_name"],
        "enabled": bool(row["enabled"]),
        "updated_at": row["updated_at"],
    }


def _contract_detail(conn, row) -> dict:
    fields = _filter_system_fields(_load_json(row["fields_schema_json"], []))
    adjustments = apply_table_row_auto_values(
        row["template_content"], _load_json(row["table_adjustments_json"], {})
    )
    values = _load_json(row["field_values_json"], {})
    values = warehouse_db.resolve_warehouse_values(values, fields)
    data = _contract_summary(row)
    data.update(
        {
            "template_id": row["template_id"],
            "template_content": row["template_content"],
            "fields_schema": fields,
            "field_values": apply_auto_amounts(
                row["template_content"], adjustments, fields, values
            ),
            "table_adjustments": adjustments,
            "creator_id": row["creator_id"],
            "reviewer_name": row["reviewer_name"],
        }
    )
    events = conn.execute(
        "SELECT * FROM contract_events WHERE contract_id = ? ORDER BY id ASC",
        (row["id"],),
    ).fetchall()
    data["events"] = [_event_dict(event) for event in events]
    data["bundle"] = _bundle_dict(conn, row["bundle_id"]) if row["bundle_id"] else None
    return data


def _fetch_template(conn, template_id: int, user: dict | None = None) -> dict:
    row = conn.execute(
        """
        SELECT t.*, u.display_name AS creator_name,
               (SELECT COUNT(*) FROM contracts c WHERE c.template_id = t.id) AS usage_count
          FROM templates t
          LEFT JOIN users u ON u.id = t.created_by
         WHERE t.id = ?
        """,
        (template_id,),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="合同模板不存在")
    if (
        user
        and "templates" not in set(user.get("permissions") or [])
        and row["status"] != "active"
    ):
        raise HTTPException(status_code=404, detail="合同模板不存在")
    return _template_dict(row)


def _fetch_contract(conn, contract_id: int, user: dict) -> dict:
    row = conn.execute("SELECT * FROM contracts WHERE id = ?", (contract_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="合同不存在")
    if (
        "reviews" not in set(user.get("permissions") or [])
        and row["creator_id"] != user["id"]
    ):
        raise HTTPException(status_code=403, detail="无权查看该合同")
    return _contract_detail(conn, row)


def _filter_values(values: dict[str, str], fields: list[dict]) -> dict[str, str]:
    allowed = {field["key"] for field in fields}
    return {key: value for key, value in values.items() if key in allowed}


def _ensure_valid_field_values(fields: list[dict], values: dict[str, str]) -> None:
    invalid = invalid_field_values(fields, values)
    if invalid:
        raise HTTPException(
            status_code=422,
            detail={
                "message": invalid_field_summary(invalid),
                "fields": [item["label"] for item in invalid],
            },
        )


def _missing_required(fields: list[dict], values: dict[str, str]) -> list[str]:
    return [
        field["label"]
        for field in fields
        if field.get("required") and not values.get(field["key"], "").strip()
    ]


def _insert_event(
    conn,
    contract_id: int,
    action: str,
    user: dict,
    from_status: str | None,
    to_status: str | None,
    comment: str = "",
) -> None:
    conn.execute(
        """
        INSERT INTO contract_events(
            contract_id, action, actor_id, actor_name,
            from_status, to_status, comment, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            contract_id,
            action,
            user["id"],
            user["display_name"],
            from_status,
            to_status,
            comment,
            utcnow(),
        ),
    )


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "绵绵聚道"}


@app.post("/api/auth/login")
def login(payload: LoginRequest, response: Response):
    if not password_login_enabled():
        raise HTTPException(status_code=403, detail="当前仅支持飞书登录")
    with db_cursor() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ?", (payload.username.strip(),)
        ).fetchone()
    if not row or not verify_password(payload.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="账号或密码错误")
    token, max_age = create_session(row["id"])
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=max_age,
        httponly=True,
        samesite="lax",
        secure=os.getenv("OA_SECURE_COOKIE", "false").lower() == "true",
    )
    user = {
        "id": row["id"],
        "username": row["username"],
        "display_name": row["display_name"],
        "role": row["role"],
        "department": row["department"],
    }
    profile = resolve_access_profile(user)
    user.update(
        {
            "role": profile["role"],
            "department": profile["department"],
            "job_title": profile["job_title"],
            "permissions": profile["permissions"],
        }
    )
    return {"user": _public_user(user)}


@app.post("/api/auth/logout")
def logout(request: Request, response: Response):
    delete_session(request.cookies.get(SESSION_COOKIE))
    response.delete_cookie(SESSION_COOKIE, httponly=True, samesite="lax")
    return {"ok": True}


@app.get("/api/auth/me")
def me(user: dict = Depends(get_current_user)):
    return {"user": user}


@app.get("/api/auth/feishu/config")
def feishu_config():
    try:
        settings = get_feishu_settings()
    except RuntimeError:
        return {"enabled": False}
    return {"enabled": bool(settings["enabled"])}


@app.get("/api/auth/feishu/login")
def feishu_login(
    next_path: str = Query(default="/dashboard", alias="next"),
):
    try:
        settings = get_feishu_settings()
        client = get_feishu_client()
    except (RuntimeError, FeishuAuthError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not settings["enabled"]:
        raise HTTPException(status_code=503, detail="飞书登录未启用")

    state = secrets.token_urlsafe(24)
    target = _safe_next_path(next_path)
    response = RedirectResponse(client.build_auth_url(state), status_code=302)
    response.set_cookie(
        FEISHU_STATE_COOKIE,
        state,
        max_age=600,
        httponly=True,
        samesite="lax",
        secure=_cookie_secure(),
    )
    response.set_cookie(
        FEISHU_NEXT_COOKIE,
        quote(target, safe=""),
        max_age=600,
        httponly=True,
        samesite="lax",
        secure=_cookie_secure(),
    )
    return response


@app.get("/api/auth/feishu/callback")
def feishu_callback(request: Request):
    params = request.query_params
    if params.get("error"):
        return _feishu_login_error("cancelled")

    code = (params.get("code") or "").strip()
    state = (params.get("state") or "").strip()
    saved_state = _decode_cookie_value(request.cookies.get(FEISHU_STATE_COOKIE))
    if (
        not code
        or not state
        or not saved_state
        or not secrets.compare_digest(state, saved_state)
    ):
        return _feishu_login_error("state_invalid")

    target = _safe_next_path(_decode_cookie_value(request.cookies.get(FEISHU_NEXT_COOKIE)))
    try:
        settings = get_feishu_settings()
        profile = get_feishu_client().get_user_info_by_code(code)
        union_id = str(profile.get("union_id") or "").strip()
        if not union_id:
            return _feishu_login_error("missing_union_id")
        user = user_permissions.ensure_feishu_user(
            union_id=union_id,
            display_name=str(profile.get("name") or "").strip(),
            department=str(profile.get("department_name") or "").strip(),
            employee_no=str(profile.get("employee_no") or ""),
            open_id=str(profile.get("open_id") or ""),
            auto_provision=bool(settings["auto_provision"]),
        )
    except user_permissions.FeishuProvisionError as exc:
        logger.warning("Feishu user is not bound: %s", exc)
        return _feishu_login_error("unbound")
    except FeishuAuthError as exc:
        logger.warning("Feishu OAuth failed: %s", exc)
        return _feishu_login_error("auth_failed")
    except (RuntimeError, user_permissions.UserPermissionError) as exc:
        logger.exception("Feishu login dependency failed: %s", exc)
        return _feishu_login_error("permission_unavailable")

    token, max_age = create_session(int(user["id"]))
    response = RedirectResponse(target, status_code=302)
    _set_session_cookie(response, token, max_age)
    response.delete_cookie(FEISHU_STATE_COOKIE)
    response.delete_cookie(FEISHU_NEXT_COOKIE)
    return response


@app.get("/feishu")
def feishu_entry(request: Request):
    if request.cookies.get(SESSION_COOKIE):
        return RedirectResponse("/dashboard", status_code=302)
    return RedirectResponse(
        "/api/auth/feishu/login?next=/dashboard", status_code=302
    )


@app.get("/api/dashboard")
def dashboard(user: dict = Depends(require_permission("dashboard"))):
    can_review = "reviews" in set(user.get("permissions") or [])
    with db_cursor() as conn:
        if not can_review:
            counts_rows = conn.execute(
                "SELECT status, COUNT(*) AS total FROM contracts WHERE creator_id = ? GROUP BY status",
                (user["id"],),
            ).fetchall()
            recent = conn.execute(
                "SELECT * FROM contracts WHERE creator_id = ? ORDER BY updated_at DESC LIMIT 6",
                (user["id"],),
            ).fetchall()
            pending = conn.execute(
                "SELECT * FROM contracts WHERE creator_id = ? AND status = 'pending' ORDER BY submitted_at DESC LIMIT 5",
                (user["id"],),
            ).fetchall()
            scope = "mine"
        else:
            counts_rows = conn.execute(
                "SELECT status, COUNT(*) AS total FROM contracts GROUP BY status"
            ).fetchall()
            recent = conn.execute(
                "SELECT * FROM contracts ORDER BY updated_at DESC LIMIT 6"
            ).fetchall()
            pending = conn.execute(
                "SELECT * FROM contracts WHERE status = 'pending' ORDER BY submitted_at ASC LIMIT 5"
            ).fetchall()
            scope = "all"

        counts = {row["status"]: row["total"] for row in counts_rows}
        template_count = conn.execute(
            "SELECT COUNT(*) AS total FROM templates WHERE status = 'active'"
        ).fetchone()["total"]

    stats = {
        "total": sum(counts.values()),
        "draft": counts.get("draft", 0),
        "pending": counts.get("pending", 0),
        "approved": counts.get("approved", 0),
        "rejected": counts.get("rejected", 0),
        "templates": template_count,
    }
    return {
        "scope": scope,
        "stats": stats,
        "recent_contracts": [_contract_summary(row) for row in recent],
        "pending_contracts": [_contract_summary(row) for row in pending],
    }


@app.get("/api/notifications")
def notifications(user: dict = Depends(get_current_user)):
    can_review = "reviews" in set(user.get("permissions") or [])
    items: list[dict] = []
    with db_cursor() as conn:
        if can_review:
            rows = conn.execute(
                """
                SELECT id, title, contract_no, creator_name, status,
                       submitted_at, updated_at
                  FROM contracts
                 WHERE status = 'pending' AND creator_id != ?
                 ORDER BY COALESCE(submitted_at, updated_at) DESC
                 LIMIT 20
                """,
                (user["id"],),
            ).fetchall()
            for row in rows:
                items.append(
                    {
                        "id": f"review-{row['id']}",
                        "kind": "review",
                        "title": "待审核合同",
                        "description": f"{row['title']} · 发起人 {row['creator_name']}",
                        "contract_id": row["id"],
                        "contract_no": row["contract_no"],
                        "status": row["status"],
                        "created_at": row["submitted_at"] or row["updated_at"],
                    }
                )

        rows = conn.execute(
            """
            SELECT id, title, contract_no, status, review_comment, updated_at
              FROM contracts
             WHERE creator_id = ? AND status IN ('rejected', 'approved')
             ORDER BY updated_at DESC
             LIMIT 20
            """,
            (user["id"],),
        ).fetchall()
        for row in rows:
            rejected = row["status"] == "rejected"
            items.append(
                {
                    "id": f"status-{row['id']}",
                    "kind": "rejected" if rejected else "approved",
                    "title": "合同被驳回" if rejected else "合同审核通过",
                    "description": (
                        f"{row['title']} · {row['review_comment'] or '请查看审核意见'}"
                        if rejected
                        else f"{row['title']} · 可下载正式 PDF"
                    ),
                    "contract_id": row["id"],
                    "contract_no": row["contract_no"],
                    "status": row["status"],
                    "created_at": row["updated_at"],
                }
            )

    items.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    items = items[:20]
    return {"items": items, "unread_count": len(items)}


@app.get("/api/parties")
def parties(
    q: str = "",
    party_type: str = "",
    _user: dict = Depends(require_permission("parties", "contracts", "templates")),
):
    try:
        items = party_db.list_parties(query=q, party_type=party_type)
    except party_db.PartyDatabaseError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="主体信息库暂时不可用，请稍后重试或手动填写主体名称。",
        ) from None
    return {"items": items}


@app.post("/api/parties", status_code=status.HTTP_201_CREATED)
def create_party(
    payload: PartyCreate,
    _user: dict = Depends(require_permission("parties")),
):
    try:
        return party_db.create_party(payload.model_dump())
    except party_db.PartyConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except party_db.PartyDatabaseError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="主体信息库暂时不可用，请稍后重试。",
        ) from exc


@app.get("/api/warehouses")
def warehouses(_user: dict = Depends(require_permission("contracts", "templates"))):
    try:
        items = warehouse_db.list_warehouses()
    except warehouse_db.WarehouseDatabaseError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="仓库信息库暂时不可用，请稍后重试。",
        ) from None
    return {"items": items}


@app.get("/api/templates")
def list_templates(
    q: str = "",
    template_status: str = Query(default="", alias="status"),
    user: dict = Depends(require_permission("contracts", "templates")),
):
    clauses = []
    params: list = []
    if "templates" not in set(user.get("permissions") or []):
        clauses.append("t.status = 'active'")
    elif template_status in {"active", "archived"}:
        clauses.append("t.status = ?")
        params.append(template_status)
    if q.strip():
        clauses.append("(t.name LIKE ? OR t.category LIKE ? OR t.description LIKE ?)")
        keyword = f"%{q.strip()}%"
        params.extend([keyword, keyword, keyword])
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with db_cursor() as conn:
        rows = conn.execute(
            f"""
            SELECT t.*, u.display_name AS creator_name,
                   (SELECT COUNT(*) FROM contracts c WHERE c.template_id = t.id) AS usage_count
              FROM templates t
              LEFT JOIN users u ON u.id = t.created_by
              {where}
             ORDER BY CASE t.status WHEN 'active' THEN 0 ELSE 1 END, t.updated_at DESC
            """,
            params,
        ).fetchall()
    return {"items": [_template_dict(row) for row in rows], "total": len(rows)}


@app.post("/api/templates/import")
async def import_template(
    file: UploadFile = File(...),
    _user: dict = Depends(require_permission("templates")),
):
    filename = Path(file.filename or "template").name
    suffix = Path(filename).suffix.lower()
    if suffix not in {".docx", ".pdf"}:
        raise HTTPException(status_code=400, detail="仅支持 Word（.docx）或 PDF 文件")
    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=400, detail="文件内容为空，请重新选择")
    if len(payload) > MAX_TEMPLATE_IMPORT_BYTES:
        raise HTTPException(status_code=413, detail="文件超过 12MB，请压缩或精简后重试")
    try:
        result = import_document(filename, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail="文件解析失败，请确认文件格式后重试") from exc

    content = normalize_content(result.content)
    keys = extract_placeholders(content)
    return {
        "name": result.name,
        "contract_code": DEFAULT_CONTRACT_CODE,
        "category": "通用",
        "description": f"由 {filename} 导入，请在保存前核对正文、空白项与填写要求。",
        "instructions": "",
        "content": content,
        "fields": fields_from_placeholders(keys),
        "source": {
            "filename": filename,
            "type": result.kind,
            "warnings": result.warnings,
            "placeholder_count": len(keys),
        },
    }


@app.get("/api/templates/{template_id}")
def get_template(
    template_id: int,
    user: dict = Depends(require_permission("contracts", "templates")),
):
    with db_cursor() as conn:
        return _fetch_template(conn, template_id, user)


@app.post("/api/templates", status_code=status.HTTP_201_CREATED)
def create_template(
    payload: TemplatePayload,
    user: dict = Depends(require_permission("templates")),
):
    data = payload.model_dump()
    content = normalize_content(data["content"])
    now = utcnow()
    with db_cursor(commit=True) as conn:
        cursor = conn.execute(
            """
            INSERT INTO templates(
                name, contract_code, category, description, instructions, content, fields_json,
                version, status, created_by, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)
            """,
            (
                data["name"],
                data["contract_code"],
                data["category"],
                data["description"].strip(),
                data["instructions"].strip(),
                content,
                json.dumps(data["fields"], ensure_ascii=False),
                "V1.0",
                user["id"],
                now,
                now,
            ),
        )
        template_id = cursor.lastrowid
        return _fetch_template(conn, template_id, user)


@app.put("/api/templates/{template_id}")
def update_template(
    template_id: int,
    payload: TemplatePayload,
    user: dict = Depends(require_permission("templates")),
):
    data = payload.model_dump()
    content = normalize_content(data["content"])
    fields_json = json.dumps(data["fields"], ensure_ascii=False)
    with db_cursor(commit=True) as conn:
        existing = conn.execute(
            "SELECT content, fields_json, version FROM templates WHERE id = ?", (template_id,)
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="合同模板不存在")
        current_version = existing["version"] or "V1.0"
        changed = existing["content"] != content or existing["fields_json"] != fields_json
        version = next_version(current_version) if changed else current_version
        conn.execute(
            """
            UPDATE templates
               SET name = ?, contract_code = ?, category = ?, description = ?, instructions = ?,
                   content = ?, fields_json = ?, version = ?, updated_at = ?
             WHERE id = ?
            """,
            (
                data["name"],
                data["contract_code"],
                data["category"],
                data["description"].strip(),
                data["instructions"].strip(),
                content,
                fields_json,
                version,
                utcnow(),
                template_id,
            ),
        )
        return _fetch_template(conn, template_id, user)


@app.delete("/api/templates/{template_id}")
def archive_template(
    template_id: int,
    user: dict = Depends(require_permission("templates")),
):
    with db_cursor(commit=True) as conn:
        row = conn.execute("SELECT id FROM templates WHERE id = ?", (template_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="合同模板不存在")
        conn.execute(
            "UPDATE templates SET status = 'archived', updated_at = ? WHERE id = ?",
            (utcnow(), template_id),
        )
    return {"ok": True, "message": "模板已归档，历史合同不受影响"}


@app.delete("/api/templates/{template_id}/permanent")
def permanently_delete_template(
    template_id: int,
    _user: dict = Depends(require_permission("templates")),
):
    with db_cursor(commit=True) as conn:
        row = conn.execute(
            "SELECT id, status FROM templates WHERE id = ?", (template_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="合同模板不存在")
        if row["status"] != "archived":
            raise HTTPException(status_code=409, detail="仅已归档的合同模板可以删除")
        conn.execute("DELETE FROM templates WHERE id = ?", (template_id,))
    return {"ok": True, "message": "模板已永久删除，历史合同快照不受影响"}


@app.get("/api/contracts")
def list_contracts(
    q: str = "",
    contract_status: str = Query(default="", alias="status"),
    template_id: int | None = None,
    user: dict = Depends(require_permission("contracts", "reviews")),
):
    clauses = []
    params: list = []
    if "reviews" not in set(user.get("permissions") or []):
        clauses.append("creator_id = ?")
        params.append(user["id"])
    if contract_status in {"draft", "pending", "approved", "rejected"}:
        clauses.append("status = ?")
        params.append(contract_status)
    if template_id:
        clauses.append("template_id = ?")
        params.append(template_id)
    if q.strip():
        clauses.append("(title LIKE ? OR contract_no LIKE ? OR template_name LIKE ? OR creator_name LIKE ?)")
        keyword = f"%{q.strip()}%"
        params.extend([keyword, keyword, keyword, keyword])
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with db_cursor() as conn:
        rows = conn.execute(
            f"SELECT * FROM contracts {where} ORDER BY updated_at DESC LIMIT 300",
            params,
        ).fetchall()
    return {"items": [_contract_summary(row) for row in rows], "total": len(rows)}


@app.get("/api/bundle-requirements")
def bundle_requirements(
    template_id: int,
    user: dict = Depends(require_permission("contracts", "templates")),
):
    with db_cursor() as conn:
        items = _required_bundle_templates(
            conn, template_id, str(user.get("department") or "")
        )
    return {"items": items, "department": str(user.get("department") or "")}


@app.get("/api/bundle-rules")
def list_bundle_rules(_user: dict = Depends(require_permission("templates"))):
    with db_cursor() as conn:
        rows = conn.execute(
            """
            SELECT r.*, tt.name AS trigger_template_name,
                   rt.name AS required_template_name
              FROM contract_bundle_rules r
              JOIN templates tt ON tt.id = r.trigger_template_id
              JOIN templates rt ON rt.id = r.required_template_id
             ORDER BY r.id DESC
            """
        ).fetchall()
    return {"items": [_bundle_rule_dict(row) for row in rows]}


@app.post("/api/bundle-rules", status_code=status.HTTP_201_CREATED)
def create_bundle_rule(
    payload: BundleRulePayload,
    _user: dict = Depends(require_permission("templates")),
):
    data = payload.model_dump()
    if data["trigger_template_id"] == data["required_template_id"]:
        raise HTTPException(status_code=422, detail="触发模板和配套模板不能相同")
    now = utcnow()
    with db_cursor(commit=True) as conn:
        templates = conn.execute(
            "SELECT id, name FROM templates WHERE id IN (?, ?)",
            (data["trigger_template_id"], data["required_template_id"]),
        ).fetchall()
        template_map = {int(row["id"]): str(row["name"]) for row in templates}
        if len(template_map) != 2:
            raise HTTPException(status_code=422, detail="模板不存在")
        name = data["name"].strip() or (
            f"{data['trigger_department']} · "
            f"{template_map[data['trigger_template_id']]} → "
            f"{template_map[data['required_template_id']]}"
        )
        try:
            cursor = conn.execute(
                """
                INSERT INTO contract_bundle_rules(
                    name, trigger_department, trigger_template_id,
                    required_template_id, enabled, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    name,
                    data["trigger_department"],
                    data["trigger_template_id"],
                    data["required_template_id"],
                    1 if data["enabled"] else 0,
                    now,
                    now,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=409, detail="相同的合同包规则已存在") from exc
        row = conn.execute(
            """
            SELECT r.*, tt.name AS trigger_template_name,
                   rt.name AS required_template_name
              FROM contract_bundle_rules r
              JOIN templates tt ON tt.id = r.trigger_template_id
              JOIN templates rt ON rt.id = r.required_template_id
             WHERE r.id = ?
            """,
            (cursor.lastrowid,),
        ).fetchone()
    return _bundle_rule_dict(row)


@app.put("/api/bundle-rules/{rule_id}")
def update_bundle_rule(
    rule_id: int,
    payload: BundleRulePayload,
    _user: dict = Depends(require_permission("templates")),
):
    data = payload.model_dump()
    if data["trigger_template_id"] == data["required_template_id"]:
        raise HTTPException(status_code=422, detail="触发模板和配套模板不能相同")
    with db_cursor(commit=True) as conn:
        existing = conn.execute(
            "SELECT id FROM contract_bundle_rules WHERE id = ?", (rule_id,)
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="合同包规则不存在")
        templates = conn.execute(
            "SELECT id, name FROM templates WHERE id IN (?, ?)",
            (data["trigger_template_id"], data["required_template_id"]),
        ).fetchall()
        template_map = {int(row["id"]): str(row["name"]) for row in templates}
        if len(template_map) != 2:
            raise HTTPException(status_code=422, detail="模板不存在")
        try:
            conn.execute(
                """
                UPDATE contract_bundle_rules
                   SET name = ?, trigger_department = ?, trigger_template_id = ?,
                       required_template_id = ?, enabled = ?, updated_at = ?
                 WHERE id = ?
                """,
                (
                    data["name"].strip()
                    or (
                        f"{data['trigger_department']} · "
                        f"{template_map[data['trigger_template_id']]} → "
                        f"{template_map[data['required_template_id']]}"
                    ),
                    data["trigger_department"],
                    data["trigger_template_id"],
                    data["required_template_id"],
                    1 if data["enabled"] else 0,
                    utcnow(),
                    rule_id,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=409, detail="相同的合同包规则已存在") from exc
        row = conn.execute(
            """
            SELECT r.*, tt.name AS trigger_template_name,
                   rt.name AS required_template_name
              FROM contract_bundle_rules r
              JOIN templates tt ON tt.id = r.trigger_template_id
              JOIN templates rt ON rt.id = r.required_template_id
             WHERE r.id = ?
            """,
            (rule_id,),
        ).fetchone()
    return _bundle_rule_dict(row)


@app.delete("/api/bundle-rules/{rule_id}")
def delete_bundle_rule(
    rule_id: int,
    _user: dict = Depends(require_permission("templates")),
):
    with db_cursor(commit=True) as conn:
        cursor = conn.execute(
            "DELETE FROM contract_bundle_rules WHERE id = ?", (rule_id,)
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="合同包规则不存在")
    return {"ok": True}


@app.get("/api/contracts/{contract_id}")
def get_contract(
    contract_id: int,
    user: dict = Depends(require_permission("contracts", "reviews")),
):
    with db_cursor() as conn:
        return _fetch_contract(conn, contract_id, user)


@app.post("/api/contracts", status_code=status.HTTP_201_CREATED)
def create_contract(
    payload: ContractCreate,
    user: dict = Depends(require_permission("contracts")),
):
    with db_cursor(commit=True) as conn:
        template_row = conn.execute(
            "SELECT * FROM templates WHERE id = ? AND status = 'active'", (payload.template_id,)
        ).fetchone()
        if not template_row:
            raise HTTPException(status_code=404, detail="合同模板不存在或已归档")
        contract_id = _insert_contract_record(
            conn,
            template_row,
            title=payload.title,
            field_values=payload.field_values,
            table_adjustments=payload.table_adjustments,
            user=user,
        )
        return _fetch_contract(conn, contract_id, user)


@app.post("/api/contracts/bundle", status_code=status.HTTP_201_CREATED)
def create_contract_bundle(
    payload: ContractCreate,
    user: dict = Depends(require_permission("contracts")),
):
    with db_cursor(commit=True) as conn:
        template_row = conn.execute(
            "SELECT * FROM templates WHERE id = ? AND status = 'active'",
            (payload.template_id,),
        ).fetchone()
        if not template_row:
            raise HTTPException(status_code=404, detail="合同模板不存在或已归档")

        required_templates = _required_bundle_templates(
            conn, payload.template_id, str(user.get("department") or "")
        )
        bundle_id = None
        if required_templates:
            now = utcnow()
            bundle_no = _bundle_number(conn, now)
            cursor = conn.execute(
                """
                INSERT INTO contract_bundles(
                    bundle_no, creator_id, creator_name, department, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    bundle_no,
                    user["id"],
                    user["display_name"],
                    str(user.get("department") or ""),
                    now,
                    now,
                ),
            )
            bundle_id = int(cursor.lastrowid)

        primary_id = _insert_contract_record(
            conn,
            template_row,
            title=payload.title,
            field_values=payload.field_values,
            table_adjustments=payload.table_adjustments,
            user=user,
            bundle_id=bundle_id,
        )

        if bundle_id is not None:
            for required in required_templates:
                required_row = conn.execute(
                    "SELECT * FROM templates WHERE id = ? AND status = 'active'",
                    (required["id"],),
                ).fetchone()
                if not required_row:
                    continue
                companion_title = (
                    f"{payload.title.strip()} · {required_row['name']}"
                )[:200]
                _insert_contract_record(
                    conn,
                    required_row,
                    title=companion_title,
                    field_values=payload.field_values,
                    table_adjustments={},
                    user=user,
                    bundle_id=bundle_id,
                )
            conn.execute(
                "UPDATE contract_bundles SET updated_at = ? WHERE id = ?",
                (utcnow(), bundle_id),
            )

        return _fetch_contract(conn, primary_id, user)


@app.put("/api/contracts/{contract_id}")
def update_contract(
    contract_id: int,
    payload: ContractUpdate,
    user: dict = Depends(require_permission("contracts")),
):
    with db_cursor(commit=True) as conn:
        row = conn.execute("SELECT * FROM contracts WHERE id = ?", (contract_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="合同不存在")
        if row["creator_id"] != user["id"] and user["role"] != "admin":
            raise HTTPException(status_code=403, detail="无权修改该合同")
        if row["status"] not in {"draft", "rejected"}:
            raise HTTPException(status_code=409, detail="仅草稿或已驳回的合同可以修改")

        title = payload.title.strip() if payload.title is not None else row["title"]
        if not title:
            raise HTTPException(status_code=422, detail="合同名称不能为空")
        fields = _load_json(row["fields_schema_json"], [])
        current_values = _load_json(row["field_values_json"], {})
        current_adjustments = _load_json(row["table_adjustments_json"], {})
        if payload.field_values is not None:
            current_values = _filter_values(normalize_field_values(payload.field_values), fields)
        if payload.table_adjustments is not None:
            current_adjustments = normalize_table_adjustments(
                row["template_content"], payload.table_adjustments
            )
        current_adjustments = apply_table_row_auto_values(
            row["template_content"], current_adjustments
        )
        current_values = warehouse_db.resolve_warehouse_values(current_values, fields)
        current_values = apply_auto_amounts(
            row["template_content"], current_adjustments, fields, current_values
        )
        current_values = _filter_values(current_values, fields)
        _ensure_valid_field_values(fields, current_values)
        conn.execute(
            """
            UPDATE contracts
               SET title = ?, field_values_json = ?, table_adjustments_json = ?, updated_at = ?
             WHERE id = ?
            """,
            (
                title,
                json.dumps(current_values, ensure_ascii=False),
                json.dumps(current_adjustments, ensure_ascii=False),
                utcnow(),
                contract_id,
            ),
        )
        _insert_event(conn, contract_id, "updated", user, row["status"], row["status"], "更新合同内容")
        _sync_contract_archive(
            oa_contract_id=contract_id,
            contract_no=row["contract_no"],
            contract_code=row["contract_code"] or DEFAULT_CONTRACT_CODE,
            contract_name=title,
            contract_status=row["status"],
            initiator_name=row["creator_name"],
            approver_name=row["reviewer_name"] or "",
            template_name=row["template_name"],
            template_version=row["template_version"],
            review_comment=row["review_comment"] or "",
        )
        return _fetch_contract(conn, contract_id, user)


@app.post("/api/contracts/{contract_id}/submit")
def submit_contract(
    contract_id: int,
    user: dict = Depends(require_permission("contracts")),
):
    with db_cursor(commit=True) as conn:
        row = conn.execute("SELECT * FROM contracts WHERE id = ?", (contract_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="合同不存在")
        if row["creator_id"] != user["id"]:
            raise HTTPException(status_code=403, detail="仅合同发起人可以提交审核")
        if row["status"] not in {"draft", "rejected"}:
            raise HTTPException(status_code=409, detail="当前状态不可提交审核")
        if row["bundle_id"]:
            return _submit_bundle(conn, row, user)
        fields = _load_json(row["fields_schema_json"], [])
        values = _load_json(row["field_values_json"], {})
        adjustments = _load_json(row["table_adjustments_json"], {})
        adjustments = apply_table_row_auto_values(row["template_content"], adjustments)
        values = warehouse_db.resolve_warehouse_values(values, fields)
        values = apply_auto_amounts(
            row["template_content"], adjustments, fields, values
        )
        values = _filter_values(values, fields)
        _ensure_valid_field_values(fields, values)
        missing = _missing_required(fields, values)
        if missing:
            raise HTTPException(
                status_code=422,
                detail={"message": "请补充以下必填内容", "fields": missing},
            )
        now = utcnow()
        action = "resubmitted" if row["status"] == "rejected" else "submitted"
        conn.execute(
            """
            UPDATE contracts
               SET status = 'pending', submitted_at = ?, updated_at = ?, field_values_json = ?,
                   table_adjustments_json = ?,
                   reviewed_at = NULL, reviewer_id = NULL, reviewer_name = NULL,
                   review_comment = ''
             WHERE id = ?
            """,
            (
                now,
                now,
                json.dumps(values, ensure_ascii=False),
                json.dumps(adjustments, ensure_ascii=False),
                contract_id,
            ),
        )
        _insert_event(
            conn,
            contract_id,
            action,
            user,
            row["status"],
            "pending",
            "提交法务审核" if action == "submitted" else "根据审核意见修改后重新提交",
        )
        _sync_contract_archive(
            oa_contract_id=contract_id,
            contract_no=row["contract_no"],
            contract_code=row["contract_code"] or DEFAULT_CONTRACT_CODE,
            contract_name=row["title"],
            contract_status="pending",
            initiator_name=row["creator_name"],
            template_name=row["template_name"],
            template_version=row["template_version"],
        )
        return _fetch_contract(conn, contract_id, user)


@app.post("/api/contracts/{contract_id}/withdraw")
def withdraw_contract(
    contract_id: int,
    user: dict = Depends(require_permission("contracts")),
):
    with db_cursor(commit=True) as conn:
        row = conn.execute("SELECT * FROM contracts WHERE id = ?", (contract_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="合同不存在")
        if row["creator_id"] != user["id"]:
            raise HTTPException(status_code=403, detail="仅合同发起人可以撤回")
        if row["status"] != "pending":
            raise HTTPException(status_code=409, detail="仅待审核合同可以撤回")
        conn.execute(
            "UPDATE contracts SET status = 'draft', submitted_at = NULL, updated_at = ? WHERE id = ?",
            (utcnow(), contract_id),
        )
        _insert_event(conn, contract_id, "withdrawn", user, "pending", "draft", "撤回审核")
        _sync_contract_archive(
            oa_contract_id=contract_id,
            contract_no=row["contract_no"],
            contract_code=row["contract_code"] or DEFAULT_CONTRACT_CODE,
            contract_name=row["title"],
            contract_status="draft",
            initiator_name=row["creator_name"],
            template_name=row["template_name"],
            template_version=row["template_version"],
        )
        return _fetch_contract(conn, contract_id, user)


@app.post("/api/contracts/{contract_id}/review")
def review_contract(
    contract_id: int,
    payload: ReviewRequest,
    user: dict = Depends(require_permission("reviews")),
):
    with db_cursor(commit=True) as conn:
        row = conn.execute("SELECT * FROM contracts WHERE id = ?", (contract_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="合同不存在")
        if row["status"] != "pending":
            raise HTTPException(status_code=409, detail="仅待审核合同可以执行审核")
        if row["creator_id"] == user["id"]:
            raise HTTPException(status_code=409, detail="不能审核本人发起的合同")
        new_status = "approved" if payload.decision == "approve" else "rejected"
        now = utcnow()
        conn.execute(
            """
            UPDATE contracts
               SET status = ?, reviewed_at = ?, updated_at = ?,
                   reviewer_id = ?, reviewer_name = ?, review_comment = ?
             WHERE id = ?
            """,
            (new_status, now, now, user["id"], user["display_name"], payload.comment, contract_id),
        )
        _insert_event(
            conn,
            contract_id,
            new_status,
            user,
            "pending",
            new_status,
            payload.comment or ("审核通过" if new_status == "approved" else "退回修改"),
        )
        _sync_contract_archive(
            oa_contract_id=contract_id,
            contract_no=row["contract_no"],
            contract_code=row["contract_code"] or DEFAULT_CONTRACT_CODE,
            contract_name=row["title"],
            contract_status=new_status,
            initiator_name=row["creator_name"],
            approver_name=user["display_name"],
            template_name=row["template_name"],
            template_version=row["template_version"],
            review_comment=payload.comment,
            approved_at=now if new_status == "approved" else None,
        )
        return _fetch_contract(conn, contract_id, user)


@app.delete("/api/contracts/{contract_id}")
def delete_contract(
    contract_id: int,
    user: dict = Depends(require_permission("contracts")),
):
    with db_cursor(commit=True) as conn:
        row = conn.execute("SELECT * FROM contracts WHERE id = ?", (contract_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="合同不存在")
        if row["creator_id"] != user["id"] and user["role"] != "admin":
            raise HTTPException(status_code=403, detail="无权删除该合同")
        if row["status"] not in {"draft", "rejected"}:
            raise HTTPException(status_code=409, detail="仅草稿或已驳回的合同可以删除")
        if row["bundle_id"]:
            raise HTTPException(
                status_code=409,
                detail="合同包合同不能单独删除，请保持同包合同完整",
            )
        conn.execute("DELETE FROM contracts WHERE id = ?", (contract_id,))
        try:
            contract_archive.delete_contract_record(oa_contract_id=contract_id)
        except contract_archive.ContractArchiveError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"ok": True}


@app.get("/api/contracts/{contract_id}/pdf")
def contract_pdf(
    contract_id: int,
    user: dict = Depends(require_permission("contracts", "reviews")),
):
    with db_cursor() as conn:
        contract = _fetch_contract(conn, contract_id, user)
    if contract["status"] != "approved":
        raise HTTPException(status_code=409, detail="法务审核通过后方可下载 PDF")
    if contract.get("bundle") and not contract["bundle"]["all_approved"]:
        raise HTTPException(
            status_code=409,
            detail="合同包内全部合同审核通过后方可下载 PDF",
        )
    pdf_bytes = build_contract_pdf(contract)
    safe_title = re.sub(r'[\\/:*?"<>|]', "_", contract["title"]).strip(" .") or contract["contract_no"]
    headers = {
        "Content-Disposition": (
            f'attachment; filename="{contract["contract_no"]}.pdf"; '
            f"filename*=UTF-8''{quote(safe_title + '.pdf')}"
        ),
        "Cache-Control": "private, no-store",
    }
    return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)


@app.get("/api/admin/permissions")
def list_permission_records(_user: dict = Depends(require_roles("admin"))):
    try:
        items = user_permissions.list_user_permissions()
    except user_permissions.UserPermissionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"modules": user_permissions.MODULES, "items": items}


@app.put("/api/admin/permissions/{record_id}")
def update_permission_record(
    record_id: int,
    payload: PermissionUpdate,
    _user: dict = Depends(require_roles("admin")),
):
    try:
        item = user_permissions.update_user_permission(
            record_id,
            permissions=payload.permissions,
            union_id=payload.union_id,
        )
    except user_permissions.UserPermissionNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except user_permissions.UserPermissionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except user_permissions.UserPermissionValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except user_permissions.UserPermissionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return item


@app.get("/{full_path:path}", include_in_schema=False)
def serve_frontend(full_path: str):
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="接口不存在")
    index_file = FRONTEND_DIST / "index.html"
    if not index_file.exists():
        return HTMLResponse(
            """
            <html lang="zh-CN"><body style="font-family: sans-serif; padding: 48px; color: #1f2937">
              <h2>绵绵聚道后端已启动</h2>
              <p>前端尚未构建。请执行 <code>cd frontend; npm install; npm run build</code>，然后重启服务。</p>
              <p>接口文档：<a href="/docs">/docs</a></p>
            </body></html>
            """,
            status_code=200,
        )
    candidate = (FRONTEND_DIST / full_path).resolve()
    if full_path and candidate.is_file() and FRONTEND_DIST in candidate.parents:
        return FileResponse(candidate)
    return FileResponse(index_file, headers={"Cache-Control": "no-cache"})
