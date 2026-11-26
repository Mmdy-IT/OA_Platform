from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request, status

from .db import db_cursor, utcnow
from .user_permissions import resolve_access_profile


SESSION_COOKIE = "oa_session"
SESSION_TTL_HOURS = int(os.getenv("OA_SESSION_HOURS", "8"))
PASSWORD_ITERATIONS = 310_000


def hash_password(password: str) -> str:
    if len(password) < 8:
        raise ValueError("密码至少需要 8 位")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS
    )
    return "pbkdf2_sha256${}${}${}".format(
        PASSWORD_ITERATIONS,
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(digest).decode("ascii"),
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt_b64, digest_b64 = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, int(iterations)
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def create_session(user_id: int) -> tuple[str, int]:
    token = secrets.token_urlsafe(40)
    now = datetime.now(timezone.utc)
    expires = now + timedelta(hours=SESSION_TTL_HOURS)
    with db_cursor(commit=True) as conn:
        conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (utcnow(),))
        conn.execute(
            "INSERT INTO sessions(token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (token, user_id, now.isoformat(timespec="seconds"), expires.isoformat(timespec="seconds")),
        )
        conn.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (utcnow(), user_id))
    return token, SESSION_TTL_HOURS * 3600


def delete_session(token: str | None) -> None:
    if not token:
        return
    with db_cursor(commit=True) as conn:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))


def _token_from_request(request: Request) -> str | None:
    authorization = request.headers.get("Authorization", "")
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return request.cookies.get(SESSION_COOKIE)


def get_current_user(request: Request) -> dict:
    token = _token_from_request(request)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")

    with db_cursor() as conn:
        row = conn.execute(
            """
            SELECT u.id, u.username, u.display_name, u.role, u.department,
                   s.expires_at
              FROM sessions s
              JOIN users u ON u.id = s.user_id
             WHERE s.token = ?
            """,
            (token,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录已失效，请重新登录")
        if datetime.fromisoformat(row["expires_at"]) <= datetime.now(timezone.utc):
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
            conn.commit()
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录已过期，请重新登录")
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
    return user


def require_roles(*roles: str):
    def dependency(user: dict = Depends(get_current_user)) -> dict:
        if user["role"] not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="没有权限执行此操作")
        return user

    return dependency


def require_permission(*permissions: str):
    def dependency(user: dict = Depends(get_current_user)) -> dict:
        granted = set(user.get("permissions") or [])
        if not granted.intersection(permissions):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="没有权限访问该子模块",
            )
        return user

    return dependency
