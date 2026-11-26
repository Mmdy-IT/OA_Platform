from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("OA_DATA_DIR", str(BASE_DIR / "data"))).resolve()
DB_PATH = DATA_DIR / "oa.db"


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    display_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin', 'legal', 'business')),
    department TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    last_login_at TEXT
);

CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at);

CREATE TABLE IF NOT EXISTS templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    contract_code TEXT NOT NULL DEFAULT 'HT',
    category TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    instructions TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL,
    fields_json TEXT NOT NULL DEFAULT '[]',
    version TEXT NOT NULL DEFAULT 'V1.0',
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived')),
    created_by INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_templates_status ON templates(status);

CREATE TABLE IF NOT EXISTS contracts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_no TEXT NOT NULL UNIQUE,
    contract_code TEXT NOT NULL DEFAULT 'HT',
    template_id INTEGER REFERENCES templates(id) ON DELETE SET NULL,
    template_name TEXT NOT NULL,
    template_version TEXT NOT NULL,
    template_content TEXT NOT NULL,
    fields_schema_json TEXT NOT NULL DEFAULT '[]',
    title TEXT NOT NULL,
    field_values_json TEXT NOT NULL DEFAULT '{}',
    table_adjustments_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'pending', 'approved', 'rejected')),
    creator_id INTEGER NOT NULL REFERENCES users(id),
    creator_name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    submitted_at TEXT,
    reviewed_at TEXT,
    reviewer_id INTEGER REFERENCES users(id),
    reviewer_name TEXT,
    review_comment TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_contracts_creator ON contracts(creator_id);
CREATE INDEX IF NOT EXISTS idx_contracts_status ON contracts(status);
CREATE INDEX IF NOT EXISTS idx_contracts_updated ON contracts(updated_at DESC);

CREATE TABLE IF NOT EXISTS contract_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_id INTEGER NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
    action TEXT NOT NULL,
    actor_id INTEGER REFERENCES users(id),
    actor_name TEXT NOT NULL,
    from_status TEXT,
    to_status TEXT,
    comment TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_contract ON contract_events(contract_id, id);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_connection() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def db_cursor(commit: bool = False):
    conn = get_connection()
    try:
        yield conn
        if commit:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with db_cursor(commit=True) as conn:
        conn.executescript(SCHEMA)
        template_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(templates)").fetchall()
        }
        template_code_added = "contract_code" not in template_columns
        if template_code_added:
            conn.execute(
                "ALTER TABLE templates ADD COLUMN contract_code TEXT NOT NULL DEFAULT 'HT'"
            )
            from .seed_data import TEMPLATE_SEEDS

            for item in TEMPLATE_SEEDS:
                conn.execute(
                    "UPDATE templates SET contract_code = ? WHERE name = ?",
                    (item["contract_code"], item["name"]),
                )
        contract_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(contracts)").fetchall()
        }
        if "table_adjustments_json" not in contract_columns:
            conn.execute(
                "ALTER TABLE contracts ADD COLUMN table_adjustments_json TEXT NOT NULL DEFAULT '{}'"
            )
        if "contract_code" not in contract_columns:
            conn.execute(
                "ALTER TABLE contracts ADD COLUMN contract_code TEXT NOT NULL DEFAULT ''"
            )
        conn.execute(
            """
            UPDATE contracts
               SET contract_code = COALESCE(
                   NULLIF(contract_code, ''),
                   (SELECT t.contract_code FROM templates t WHERE t.id = contracts.template_id),
                   'HT'
               )
             WHERE contract_code = '' OR contract_code IS NULL
            """
        )

    from .seed import seed_database

    seed_database()
