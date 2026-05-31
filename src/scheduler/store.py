"""Local state for the PPT scheduler."""
from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

log = logging.getLogger(__name__)

_DB_PATH = Path(__file__).parent.parent.parent / "data" / "scheduler.db"
_TOKEN_PATH = Path(__file__).parent.parent.parent / "data" / "google_calendar_token.json"
_GOOGLE_OAUTH_CONFIG_KEY = "google_oauth_client_config"


def _conn() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(_DB_PATH))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    return con


def init_db() -> None:
    with _conn() as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS scheduler_settings (
                key      TEXT PRIMARY KEY,
                value    TEXT NOT NULL,
                updated  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS oauth_states (
                state    TEXT PRIMARY KEY,
                created  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS import_batches (
                id              TEXT PRIMARY KEY,
                filename        TEXT NOT NULL,
                preview_json    TEXT NOT NULL,
                status          TEXT NOT NULL DEFAULT 'previewed',
                total_events    INTEGER NOT NULL DEFAULT 0,
                imported_events INTEGER NOT NULL DEFAULT 0,
                created         TEXT NOT NULL,
                updated         TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS managed_events (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                calendar_id    TEXT NOT NULL,
                google_event_id TEXT NOT NULL,
                source_type    TEXT NOT NULL DEFAULT 'manual',
                source_uid     TEXT,
                import_batch_id TEXT,
                created        TEXT NOT NULL,
                updated        TEXT NOT NULL,
                UNIQUE(calendar_id, google_event_id),
                UNIQUE(calendar_id, source_uid)
            );
            """
        )
    log.info("scheduler.db initialised at %s", _DB_PATH)


def get_setting(key: str, default: Any = None) -> Any:
    with _conn() as con:
        row = con.execute(
            "SELECT value FROM scheduler_settings WHERE key=?",
            (key,),
        ).fetchone()
    if not row:
        return default
    try:
        return json.loads(row["value"])
    except json.JSONDecodeError:
        return row["value"]


def set_setting(key: str, value: Any) -> None:
    now = datetime.utcnow().isoformat()
    payload = json.dumps(value)
    with _conn() as con:
        con.execute(
            """
            INSERT INTO scheduler_settings (key, value, updated)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated=excluded.updated
            """,
            (key, payload, now),
        )


def delete_setting(key: str) -> None:
    with _conn() as con:
        con.execute("DELETE FROM scheduler_settings WHERE key=?", (key,))


def get_default_calendar_id() -> str | None:
    value = get_setting("default_calendar_id")
    return str(value) if value else None


def set_default_calendar_id(calendar_id: str) -> None:
    set_setting("default_calendar_id", calendar_id)


def get_google_oauth_client_config() -> dict[str, Any] | None:
    value = get_setting(_GOOGLE_OAUTH_CONFIG_KEY)
    return value if isinstance(value, dict) else None


def set_google_oauth_client_config(config: dict[str, Any]) -> None:
    set_setting(_GOOGLE_OAUTH_CONFIG_KEY, config)


def clear_google_oauth_client_config() -> None:
    delete_setting(_GOOGLE_OAUTH_CONFIG_KEY)


def store_oauth_state(state: str) -> None:
    now = datetime.utcnow().isoformat()
    with _conn() as con:
        con.execute(
            """
            INSERT OR REPLACE INTO oauth_states (state, created)
            VALUES (?, ?)
            """,
            (state, now),
        )


def consume_oauth_state(state: str) -> bool:
    with _conn() as con:
        row = con.execute(
            "SELECT state FROM oauth_states WHERE state=?",
            (state,),
        ).fetchone()
        if not row:
            return False
        con.execute("DELETE FROM oauth_states WHERE state=?", (state,))
    return True


def cleanup_oauth_states(max_age_hours: int = 4) -> None:
    cutoff = datetime.utcnow().timestamp() - (max_age_hours * 3600)
    with _conn() as con:
        rows = con.execute("SELECT state, created FROM oauth_states").fetchall()
        for row in rows:
            try:
                created_ts = datetime.fromisoformat(row["created"]).timestamp()
            except ValueError:
                created_ts = 0
            if created_ts < cutoff:
                con.execute("DELETE FROM oauth_states WHERE state=?", (row["state"],))


def create_import_batch(filename: str, preview: dict[str, Any]) -> str:
    batch_id = uuid4().hex
    now = datetime.utcnow().isoformat()
    payload = json.dumps(preview)
    with _conn() as con:
        con.execute(
            """
            INSERT INTO import_batches
                (id, filename, preview_json, status, total_events, imported_events, created, updated)
            VALUES (?, ?, ?, 'previewed', ?, 0, ?, ?)
            """,
            (batch_id, filename, payload, len(preview.get("entries", [])), now, now),
        )
    return batch_id


def get_import_batch(batch_id: str) -> dict[str, Any] | None:
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM import_batches WHERE id=?",
            (batch_id,),
        ).fetchone()
    if not row:
        return None
    result = dict(row)
    result["preview"] = json.loads(result["preview_json"])
    return result


def update_import_batch(batch_id: str, *, status: str, imported_events: int | None = None) -> None:
    now = datetime.utcnow().isoformat()
    with _conn() as con:
        if imported_events is None:
            con.execute(
                "UPDATE import_batches SET status=?, updated=? WHERE id=?",
                (status, now, batch_id),
            )
        else:
            con.execute(
                """
                UPDATE import_batches
                SET status=?, imported_events=?, updated=?
                WHERE id=?
                """,
                (status, imported_events, now, batch_id),
            )


def record_managed_event(
    calendar_id: str,
    google_event_id: str,
    *,
    source_type: str = "manual",
    source_uid: str | None = None,
    import_batch_id: str | None = None,
) -> None:
    now = datetime.utcnow().isoformat()
    with _conn() as con:
        if source_uid:
            con.execute(
                """
                DELETE FROM managed_events
                WHERE calendar_id=? AND source_uid=? AND google_event_id!=?
                """,
                (calendar_id, source_uid, google_event_id),
            )
        con.execute(
            """
            INSERT INTO managed_events
                (calendar_id, google_event_id, source_type, source_uid, import_batch_id, created, updated)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(calendar_id, google_event_id) DO UPDATE SET
                source_type=excluded.source_type,
                source_uid=excluded.source_uid,
                import_batch_id=excluded.import_batch_id,
                updated=excluded.updated
            """,
            (calendar_id, google_event_id, source_type, source_uid, import_batch_id, now, now),
        )


def get_managed_event_by_source_uid(calendar_id: str, source_uid: str | None) -> dict[str, Any] | None:
    if not source_uid:
        return None
    with _conn() as con:
        row = con.execute(
            """
            SELECT * FROM managed_events
            WHERE calendar_id=? AND source_uid=?
            """,
            (calendar_id, source_uid),
        ).fetchone()
    return dict(row) if row else None


def is_imported_uid(calendar_id: str, source_uid: str | None) -> bool:
    if not source_uid:
        return False
    with _conn() as con:
        row = con.execute(
            """
            SELECT 1 FROM managed_events
            WHERE calendar_id=? AND source_uid=?
            """,
            (calendar_id, source_uid),
        ).fetchone()
    return row is not None


def remove_managed_event(calendar_id: str, google_event_id: str) -> None:
    with _conn() as con:
        con.execute(
            "DELETE FROM managed_events WHERE calendar_id=? AND google_event_id=?",
            (calendar_id, google_event_id),
        )


def token_path() -> Path:
    _TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    return _TOKEN_PATH


def save_token_json(payload: str) -> None:
    path = token_path()
    path.write_text(payload, encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def load_token_json() -> str | None:
    path = token_path()
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def clear_token() -> None:
    path = token_path()
    if path.exists():
        path.unlink()


init_db()
