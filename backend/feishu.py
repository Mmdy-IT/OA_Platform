from __future__ import annotations

import threading
import time
from urllib.parse import urlencode

import httpx

from .config import get_feishu_settings


class FeishuAuthError(RuntimeError):
    """Raised when Feishu OAuth or user lookup fails."""


class FeishuClient:
    OPEN_API_BASE = "https://open.feishu.cn/open-apis"

    def __init__(self, app_id: str, app_secret: str, redirect_uri: str) -> None:
        self.app_id = app_id
        self.app_secret = app_secret
        self.redirect_uri = redirect_uri
        self._app_access_token = ""
        self._token_expires_at = 0.0
        self._token_lock = threading.Lock()

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict:
        try:
            with httpx.Client(timeout=12) as client:
                response = client.request(
                    method,
                    self.OPEN_API_BASE + path,
                    json=json,
                    headers=headers,
                )
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise FeishuAuthError("飞书接口连接失败") from exc

        if payload.get("code") != 0:
            message = payload.get("msg") or payload.get("message") or "未知错误"
            raise FeishuAuthError(f"飞书接口返回错误：{message}")
        return payload

    def get_app_access_token(self) -> str:
        now = time.time()
        with self._token_lock:
            if self._app_access_token and now < self._token_expires_at - 60:
                return self._app_access_token
            payload = self._request(
                "POST",
                "/auth/v3/app_access_token/internal",
                json={"app_id": self.app_id, "app_secret": self.app_secret},
            )
            token = str(payload.get("app_access_token") or "")
            if not token:
                raise FeishuAuthError("飞书应用访问令牌获取失败")
            self._app_access_token = token
            self._token_expires_at = now + int(payload.get("expire") or 7200)
            return token

    def build_auth_url(self, state: str) -> str:
        query = urlencode(
            {
                "app_id": self.app_id,
                "redirect_uri": self.redirect_uri,
                "state": state,
            }
        )
        return f"{self.OPEN_API_BASE}/authen/v1/index?{query}"

    def get_user_info_by_code(self, code: str) -> dict[str, str]:
        app_token = self.get_app_access_token()
        payload = self._request(
            "POST",
            "/authen/v1/access_token",
            json={"grant_type": "authorization_code", "code": code},
            headers={"Authorization": f"Bearer {app_token}"},
        )
        data = payload.get("data") or {}
        user_access_token = str(data.get("access_token") or "")
        if user_access_token:
            user_info_payload = self._request(
                "GET",
                "/authen/v1/user_info",
                headers={"Authorization": f"Bearer {user_access_token}"},
            )
            user_info = user_info_payload.get("data") or {}
            if user_info:
                data = {**data, **user_info}
        return {
            key: str(data.get(key) or "")
            for key in (
                "open_id",
                "union_id",
                "name",
                "avatar_url",
                "email",
                "mobile",
                "employee_no",
                "department_name",
                "department",
            )
        }


def get_feishu_client() -> FeishuClient:
    settings = get_feishu_settings()
    if not settings["enabled"]:
        raise FeishuAuthError("飞书登录未启用")
    return FeishuClient(
        app_id=str(settings["app_id"]),
        app_secret=str(settings["app_secret"]),
        redirect_uri=str(settings["redirect_uri"]),
    )
