from __future__ import annotations

import os
from configparser import ConfigParser
from functools import lru_cache
from pathlib import Path


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
