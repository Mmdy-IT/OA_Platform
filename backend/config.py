from __future__ import annotations

import os
from configparser import ConfigParser
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = BASE_DIR / "config.ini"

DEFAULT_DB_NAME = "mmdy_db"


@lru_cache(maxsize=1)
def _read_config() -> ConfigParser:
    parser = ConfigParser(interpolation=None)
    path = Path(os.getenv("OA_CONFIG_FILE", str(DEFAULT_CONFIG_PATH)))
    if path.exists():
        parser.read(path, encoding="utf-8-sig")
    return parser


def get_setting(
    section: str,
    key: str,
    env_name: str | None = None,
    default: str = "",
) -> str:
    if env_name:
        env_value = os.getenv(env_name)
        if env_value not in (None, ""):
            return env_value

    parser = _read_config()
    if parser.has_option(section, key):
        value = parser.get(section, key).strip()
        if value:
            return value
    return default


def get_database_settings() -> dict[str, object]:
    settings = {
        "host": get_setting("database", "host", "OA_PARTY_DB_HOST", ""),
        "port": int(get_setting("database", "port", "OA_PARTY_DB_PORT", "3306")),
        "user": get_setting("database", "user", "OA_PARTY_DB_USER", ""),
        "password": get_setting("database", "password", "OA_PARTY_DB_PASSWORD", ""),
        "database": get_setting(
            "database", "name", "OA_PARTY_DB_NAME", DEFAULT_DB_NAME
        ),
    }
    missing = [
        label
        for key, label in (
            ("host", "database.host"),
            ("user", "database.user"),
            ("password", "database.password"),
        )
        if not settings[key]
    ]
    if missing:
        raise RuntimeError(
            "数据库配置缺失："
            + ", ".join(missing)
            + "。请检查 config.ini 或对应的环境变量。"
        )
    return settings


def get_database_name() -> str:
    return str(get_database_settings()["database"])


def get_table_name(key: str, env_name: str, default: str) -> str:
    return get_setting("tables", key, env_name, default)


def _as_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def password_login_enabled() -> bool:
    return _as_bool(
        get_setting("auth", "password_login", "OA_PASSWORD_LOGIN_ENABLED", "false")
    )


def get_feishu_settings() -> dict[str, object]:
    redirect_uri = get_setting("feishu", "redirect_uri", "OA_FEISHU_REDIRECT_URI", "")
    public_base_url = get_setting(
        "feishu", "public_base_url", "OA_PUBLIC_BASE_URL", ""
    ).rstrip("/")
    if not public_base_url and redirect_uri:
        parsed = urlsplit(redirect_uri)
        if parsed.scheme and parsed.netloc:
            public_base_url = f"{parsed.scheme}://{parsed.netloc}"
    settings = {
        "enabled": _as_bool(
            get_setting("feishu", "enabled", "OA_FEISHU_ENABLED", "false")
        ),
        "app_id": get_setting("feishu", "app_id", "OA_FEISHU_APP_ID", ""),
        "app_secret": get_setting(
            "feishu", "app_secret", "OA_FEISHU_APP_SECRET", ""
        ),
        "redirect_uri": redirect_uri,
        "public_base_url": public_base_url,
        "auto_provision": _as_bool(
            get_setting("feishu", "auto_provision", "OA_FEISHU_AUTO_PROVISION", "true")
        ),
    }
    if settings["enabled"]:
        missing = [
            label
            for key, label in (
                ("app_id", "feishu.app_id"),
                ("app_secret", "feishu.app_secret"),
                ("redirect_uri", "feishu.redirect_uri"),
            )
            if not settings[key]
        ]
        if missing:
            raise RuntimeError(
                "飞书配置缺失："
                + ", ".join(missing)
                + "。请检查 config.ini 或对应的环境变量。"
            )
    return settings
