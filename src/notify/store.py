"""
src/notify/store.py — SQLite persistence for ppt-notify.

The original notify store assumed exactly one user. This version keeps the
legacy owner working, but upgrades the reminder domain to proper multi-user
storage with invite-based onboarding metadata, per-user Google/Telegram links,
and strict personal-goal scoping.
"""
from __future__ import annotations

import json
import logging
import secrets
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_DB_PATH = Path(__file__).parent.parent.parent / "data" / "notify.db"

_DEFAULT_USER_ID = 1
_DEFAULT_EMAIL = "legacy-owner@ppt.local"
_DEFAULT_TIMEZONE = "America/New_York"
_DEFAULT_QUIET_START = "22:00"
_DEFAULT_QUIET_END = "07:00"


def _utcnow() -> str:
    return datetime.utcnow().isoformat()


def _conn() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(_DB_PATH))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    return con


def _table_exists(con: sqlite3.Connection, table_name: str) -> bool:
    row = con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def _columns(con: sqlite3.Connection, table_name: str) -> set[str]:
    if not _table_exists(con, table_name):
        return set()
    rows = con.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row["name"] for row in rows}


def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def default_user_id() -> int:
    return _DEFAULT_USER_ID


def _effective_user_id(user_id: int | None) -> int:
    return int(user_id or default_user_id())


def init_db() -> None:
    with _conn() as con:
        _create_identity_tables(con)
        legacy_profile = _legacy_profile_snapshot(con)
        legacy_user_id = _ensure_legacy_user(con, legacy_profile)
        _migrate_habits(con, legacy_user_id)
        _migrate_reminders(con, legacy_user_id)
        _migrate_checkins(con, legacy_user_id)
        _migrate_habit_logs(con, legacy_user_id)
        _create_personal_goals_table(con)
        _migrate_goals(con, legacy_user_id)
        _create_reminder_fires_table(con)
    log.info("notify.db initialised at %s", _DB_PATH)


def _create_identity_tables(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            google_sub   TEXT UNIQUE,
            email        TEXT UNIQUE,
            display_name TEXT,
            status       TEXT NOT NULL DEFAULT 'active',
            created      TEXT NOT NULL,
            updated      TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS user_profiles (
            user_id             INTEGER PRIMARY KEY REFERENCES users(id),
            timezone            TEXT NOT NULL DEFAULT 'America/New_York',
            quiet_hours_start   TEXT NOT NULL DEFAULT '22:00',
            quiet_hours_end     TEXT NOT NULL DEFAULT '07:00',
            relationship_xp     INTEGER NOT NULL DEFAULT 0,
            total_checkins      INTEGER NOT NULL DEFAULT 0,
            longest_streak      INTEGER NOT NULL DEFAULT 0,
            created             TEXT NOT NULL,
            updated             TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS user_invites (
            token              TEXT PRIMARY KEY,
            email              TEXT NOT NULL,
            status             TEXT NOT NULL DEFAULT 'pending',
            expires_at         TEXT NOT NULL,
            created_by         TEXT,
            accepted_user_id   INTEGER REFERENCES users(id),
            created            TEXT NOT NULL,
            updated            TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS user_google_accounts (
            user_id             INTEGER PRIMARY KEY REFERENCES users(id),
            google_sub          TEXT UNIQUE,
            email               TEXT,
            token_json          TEXT,
            scopes_json         TEXT,
            calendar_connected  INTEGER NOT NULL DEFAULT 0,
            created             TEXT NOT NULL,
            updated             TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS user_telegram_links (
            user_id            INTEGER PRIMARY KEY REFERENCES users(id),
            telegram_chat_id   TEXT UNIQUE,
            telegram_user_id   TEXT UNIQUE,
            telegram_username  TEXT,
            link_state         TEXT NOT NULL DEFAULT 'pending',
            link_token         TEXT UNIQUE,
            token_expires_at   TEXT,
            linked_at          TEXT,
            created            TEXT NOT NULL,
            updated            TEXT NOT NULL
        );
        """
    )


def _legacy_profile_snapshot(con: sqlite3.Connection) -> dict[str, Any]:
    if not _table_exists(con, "user_profile"):
        return {}
    row = con.execute("SELECT * FROM user_profile WHERE id=1").fetchone()
    return dict(row) if row else {}


def _ensure_legacy_user(con: sqlite3.Connection, legacy_profile: dict[str, Any]) -> int:
    now = _utcnow()
    name = (legacy_profile.get("name") or "Rana").strip() or "Rana"
    con.execute(
        """
        INSERT INTO users (id, email, display_name, status, created, updated)
        VALUES (?, ?, ?, 'active', ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            email=excluded.email,
            display_name=excluded.display_name,
            updated=excluded.updated
        """,
        (_DEFAULT_USER_ID, _DEFAULT_EMAIL, name, now, now),
    )
    con.execute(
        """
        INSERT INTO user_profiles (
            user_id, timezone, quiet_hours_start, quiet_hours_end,
            relationship_xp, total_checkins, longest_streak, created, updated
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            relationship_xp=excluded.relationship_xp,
            total_checkins=excluded.total_checkins,
            longest_streak=excluded.longest_streak,
            updated=excluded.updated
        """,
        (
            _DEFAULT_USER_ID,
            _DEFAULT_TIMEZONE,
            _DEFAULT_QUIET_START,
            _DEFAULT_QUIET_END,
            int(legacy_profile.get("relationship_xp", 0) or 0),
            int(legacy_profile.get("total_checkins", 0) or 0),
            int(legacy_profile.get("longest_streak", 0) or 0),
            legacy_profile.get("created") or now,
            now,
        ),
    )
    return _DEFAULT_USER_ID


def _create_habits_table(con: sqlite3.Connection) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS habits (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL REFERENCES users(id),
            name        TEXT NOT NULL,
            description TEXT,
            frequency   TEXT NOT NULL DEFAULT 'daily',
            remind_at   TEXT NOT NULL DEFAULT '08:00',
            active      INTEGER NOT NULL DEFAULT 1,
            created     TEXT NOT NULL,
            updated     TEXT NOT NULL
        )
        """
    )


def _migrate_habits(con: sqlite3.Connection, legacy_user_id: int) -> None:
    columns = _columns(con, "habits")
    if not columns:
        _create_habits_table(con)
        return
    if "user_id" in columns:
        _create_habits_table(con)
        return

    con.execute("ALTER TABLE habits RENAME TO habits_legacy")
    _create_habits_table(con)
    con.execute(
        """
        INSERT INTO habits (id, user_id, name, description, frequency, remind_at, active, created, updated)
        SELECT id, ?, name, description, frequency, remind_at, active, created, updated
        FROM habits_legacy
        """,
        (legacy_user_id,),
    )
    con.execute("DROP TABLE habits_legacy")


def _create_reminders_table(con: sqlite3.Connection) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS reminders (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL REFERENCES users(id),
            title       TEXT NOT NULL,
            message     TEXT,
            remind_at   TEXT NOT NULL,
            repeat      TEXT NOT NULL DEFAULT 'once',
            fire_date   TEXT,
            active      INTEGER NOT NULL DEFAULT 1,
            created     TEXT NOT NULL,
            updated     TEXT NOT NULL
        )
        """
    )


def _migrate_reminders(con: sqlite3.Connection, legacy_user_id: int) -> None:
    columns = _columns(con, "reminders")
    if not columns:
        _create_reminders_table(con)
        return
    if "user_id" in columns:
        _create_reminders_table(con)
        return

    con.execute("ALTER TABLE reminders RENAME TO reminders_legacy")
    _create_reminders_table(con)
    con.execute(
        """
        INSERT INTO reminders (id, user_id, title, message, remind_at, repeat, fire_date, active, created, updated)
        SELECT id, ?, title, message, remind_at, repeat, fire_date, active, created, updated
        FROM reminders_legacy
        """,
        (legacy_user_id,),
    )
    con.execute("DROP TABLE reminders_legacy")


def _create_checkins_table(con: sqlite3.Connection) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS check_ins (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL REFERENCES users(id),
            date       TEXT NOT NULL,
            mood       INTEGER,
            note       TEXT,
            created    TEXT NOT NULL,
            UNIQUE(user_id, date)
        )
        """
    )


def _migrate_checkins(con: sqlite3.Connection, legacy_user_id: int) -> None:
    columns = _columns(con, "check_ins")
    if not columns:
        _create_checkins_table(con)
        return
    if "user_id" in columns:
        _create_checkins_table(con)
        return

    con.execute("ALTER TABLE check_ins RENAME TO check_ins_legacy")
    _create_checkins_table(con)
    con.execute(
        """
        INSERT INTO check_ins (id, user_id, date, mood, note, created)
        SELECT id, ?, date, mood, note, created
        FROM check_ins_legacy
        """,
        (legacy_user_id,),
    )
    con.execute("DROP TABLE check_ins_legacy")


def _create_habit_logs_table(con: sqlite3.Connection) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS habit_logs (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL REFERENCES users(id),
            habit_id   INTEGER NOT NULL REFERENCES habits(id),
            date       TEXT NOT NULL,
            created    TEXT NOT NULL,
            UNIQUE(user_id, habit_id, date)
        )
        """
    )


def _migrate_habit_logs(con: sqlite3.Connection, legacy_user_id: int) -> None:
    columns = _columns(con, "habit_logs")
    if not columns:
        _create_habit_logs_table(con)
        return
    if "user_id" in columns:
        _create_habit_logs_table(con)
        return

    con.execute("ALTER TABLE habit_logs RENAME TO habit_logs_legacy")
    _create_habit_logs_table(con)
    con.execute(
        """
        INSERT INTO habit_logs (id, user_id, habit_id, date, created)
        SELECT id, ?, habit_id, date, created
        FROM habit_logs_legacy
        """,
        (legacy_user_id,),
    )
    con.execute("DROP TABLE habit_logs_legacy")


def _create_personal_goals_table(con: sqlite3.Connection) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS personal_goals (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL REFERENCES users(id),
            title       TEXT NOT NULL,
            description TEXT,
            deadline    TEXT,
            status      TEXT NOT NULL DEFAULT 'active',
            progress    INTEGER NOT NULL DEFAULT 0,
            remind_at   TEXT,
            remind_days TEXT DEFAULT 'daily',
            created     TEXT NOT NULL,
            updated     TEXT NOT NULL
        )
        """
    )


def _migrate_goals(con: sqlite3.Connection, legacy_user_id: int) -> None:
    if not _table_exists(con, "goals"):
        return
    existing = con.execute("SELECT COUNT(*) AS c FROM personal_goals").fetchone()["c"]
    if existing:
        return
    columns = _columns(con, "goals")
    if not columns:
        return

    user_expr = "COALESCE(user_id, ?)" if "user_id" in columns else "?"
    params: list[Any] = [legacy_user_id]
    con.execute(
        f"""
        INSERT INTO personal_goals (
            id, user_id, title, description, deadline, status, progress,
            remind_at, remind_days, created, updated
        )
        SELECT id, {user_expr}, title, description, deadline, status, progress,
               remind_at, COALESCE(remind_days, 'daily'), created, updated
        FROM goals
        """,
        params,
    )


def _create_reminder_fires_table(con: sqlite3.Connection) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS reminder_fires (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id              INTEGER NOT NULL REFERENCES users(id),
            reminder_id          INTEGER NOT NULL REFERENCES reminders(id),
            telegram_message_id  TEXT,
            fired_at             TEXT NOT NULL,
            acknowledged_at      TEXT,
            outcome              TEXT NOT NULL DEFAULT 'sent',
            retry_count          INTEGER NOT NULL DEFAULT 0
        )
        """
    )


# ── User + onboarding helpers ───────────────────────────────────────────────

def list_users(status: str | None = None) -> list[dict]:
    init_db()
    with _conn() as con:
        query = """
            SELECT u.*,
                   p.timezone,
                   p.quiet_hours_start,
                   p.quiet_hours_end,
                   p.relationship_xp,
                   p.total_checkins,
                   p.longest_streak,
                   g.calendar_connected,
                   t.telegram_chat_id,
                   t.telegram_username,
                   t.link_state
            FROM users u
            LEFT JOIN user_profiles p ON p.user_id = u.id
            LEFT JOIN user_google_accounts g ON g.user_id = u.id
            LEFT JOIN user_telegram_links t ON t.user_id = u.id
        """
        params: list[Any] = []
        if status:
            query += " WHERE u.status=?"
            params.append(status)
        query += " ORDER BY u.created ASC"
        return [dict(row) for row in con.execute(query, params).fetchall()]


def get_user(user_id: int) -> dict | None:
    user_id = _effective_user_id(user_id)
    users = [u for u in list_users() if u["id"] == user_id]
    return users[0] if users else None


def get_user_by_email(email: str) -> dict | None:
    init_db()
    email = _normalize_email(email)
    if not email:
        return None
    with _conn() as con:
        row = con.execute("SELECT id FROM users WHERE lower(email)=?", (email,)).fetchone()
    return get_user(row["id"]) if row else None


def get_user_by_google_sub(google_sub: str) -> dict | None:
    init_db()
    if not google_sub:
        return None
    with _conn() as con:
        row = con.execute("SELECT id FROM users WHERE google_sub=?", (google_sub,)).fetchone()
    return get_user(row["id"]) if row else None


def _ensure_profile_row(con: sqlite3.Connection, user_id: int) -> None:
    now = _utcnow()
    con.execute(
        """
        INSERT OR IGNORE INTO user_profiles (
            user_id, timezone, quiet_hours_start, quiet_hours_end,
            relationship_xp, total_checkins, longest_streak, created, updated
        )
        VALUES (?, ?, ?, ?, 0, 0, 0, ?, ?)
        """,
        (user_id, _DEFAULT_TIMEZONE, _DEFAULT_QUIET_START, _DEFAULT_QUIET_END, now, now),
    )


def get_profile(user_id: int | None = None) -> dict:
    init_db()
    user_id = _effective_user_id(user_id)
    with _conn() as con:
        _ensure_profile_row(con, user_id)
        row = con.execute(
            """
            SELECT u.id,
                   u.email,
                   u.google_sub,
                   u.display_name,
                   u.status,
                   p.timezone,
                   p.quiet_hours_start,
                   p.quiet_hours_end,
                   p.relationship_xp,
                   p.total_checkins,
                   p.longest_streak,
                   p.created,
                   p.updated
            FROM users u
            JOIN user_profiles p ON p.user_id = u.id
            WHERE u.id=?
            """,
            (user_id,),
        ).fetchone()
    if not row:
        return {}
    profile = dict(row)
    profile["name"] = profile.get("display_name") or profile.get("email") or "User"
    return profile


def upsert_user_profile(
    user_id: int,
    *,
    display_name: str | None = None,
    timezone: str | None = None,
    quiet_hours_start: str | None = None,
    quiet_hours_end: str | None = None,
) -> dict:
    init_db()
    user_id = _effective_user_id(user_id)
    current = get_profile(user_id)
    now = _utcnow()
    with _conn() as con:
        _ensure_profile_row(con, user_id)
        if display_name is not None:
            con.execute(
                "UPDATE users SET display_name=?, updated=? WHERE id=?",
                (display_name.strip(), now, user_id),
            )
        con.execute(
            """
            UPDATE user_profiles
            SET timezone=?,
                quiet_hours_start=?,
                quiet_hours_end=?,
                updated=?
            WHERE user_id=?
            """,
            (
                timezone or current.get("timezone") or _DEFAULT_TIMEZONE,
                quiet_hours_start or current.get("quiet_hours_start") or _DEFAULT_QUIET_START,
                quiet_hours_end or current.get("quiet_hours_end") or _DEFAULT_QUIET_END,
                now,
                user_id,
            ),
        )
    return get_profile(user_id)


def add_xp(points: int, user_id: int | None = None) -> dict:
    init_db()
    user_id = _effective_user_id(user_id)
    now = _utcnow()
    with _conn() as con:
        _ensure_profile_row(con, user_id)
        con.execute(
            """
            UPDATE user_profiles
            SET relationship_xp = relationship_xp + ?,
                updated = ?
            WHERE user_id = ?
            """,
            (points, now, user_id),
        )
    return get_profile(user_id)


def create_invite(
    email: str,
    *,
    created_by: str = "admin",
    expires_in_days: int = 7,
) -> dict:
    init_db()
    email = _normalize_email(email)
    if not email:
        raise ValueError("Invite email is required.")
    now = _utcnow()
    token = secrets.token_urlsafe(24)
    expires_at = (datetime.utcnow() + timedelta(days=expires_in_days)).isoformat()
    with _conn() as con:
        con.execute(
            """
            INSERT INTO user_invites (token, email, status, expires_at, created_by, created, updated)
            VALUES (?, ?, 'pending', ?, ?, ?, ?)
            """,
            (token, email, expires_at, created_by, now, now),
        )
    return get_invite(token) or {}


def list_invites(status: str | None = None) -> list[dict]:
    init_db()
    with _conn() as con:
        query = """
            SELECT i.*,
                   u.display_name AS accepted_user_name,
                   u.email AS accepted_user_email
            FROM user_invites i
            LEFT JOIN users u ON u.id = i.accepted_user_id
        """
        params: list[Any] = []
        if status:
            query += " WHERE i.status=?"
            params.append(status)
        query += " ORDER BY i.created DESC"
        return [dict(row) for row in con.execute(query, params).fetchall()]


def get_invite(token: str) -> dict | None:
    token = (token or "").strip()
    if not token:
        return None
    invites = [invite for invite in list_invites() if invite["token"] == token]
    return invites[0] if invites else None


def _invite_is_expired(invite: dict[str, Any]) -> bool:
    expires_at = invite.get("expires_at")
    if not expires_at:
        return False
    try:
        return datetime.fromisoformat(expires_at) < datetime.utcnow()
    except ValueError:
        return False


def accept_invite(token: str, *, google_sub: str, email: str, display_name: str) -> dict:
    init_db()
    email = _normalize_email(email)
    invite = get_invite(token)
    if not invite:
        raise ValueError("Invite not found.")
    if invite["status"] not in {"pending", "accepted"}:
        raise ValueError("Invite is no longer active.")
    if _invite_is_expired(invite):
        raise ValueError("Invite has expired.")
    if email != _normalize_email(invite["email"]):
        raise ValueError("Google account email does not match the invited email.")

    existing = get_user_by_google_sub(google_sub) or get_user_by_email(email)
    now = _utcnow()
    with _conn() as con:
        if existing:
            user_id = existing["id"]
            con.execute(
                """
                UPDATE users
                SET google_sub=?, email=?, display_name=?, status='active', updated=?
                WHERE id=?
                """,
                (google_sub, email, display_name.strip(), now, user_id),
            )
        else:
            cur = con.execute(
                """
                INSERT INTO users (google_sub, email, display_name, status, created, updated)
                VALUES (?, ?, ?, 'active', ?, ?)
                """,
                (google_sub, email, display_name.strip(), now, now),
            )
            user_id = int(cur.lastrowid)
        _ensure_profile_row(con, user_id)
        con.execute(
            """
            UPDATE user_invites
            SET status='accepted', accepted_user_id=?, updated=?
            WHERE token=?
            """,
            (user_id, now, token),
        )
    return get_user(user_id) or {}


def mark_invite_completed(token: str) -> dict | None:
    invite = get_invite(token)
    if not invite:
        return None
    with _conn() as con:
        con.execute(
            "UPDATE user_invites SET status='completed', updated=? WHERE token=?",
            (_utcnow(), token),
        )
    return get_invite(token)


def save_user_google_account(
    user_id: int,
    *,
    google_sub: str,
    email: str,
    token_json: str,
    scopes: list[str],
    calendar_connected: bool = True,
) -> dict:
    init_db()
    user_id = _effective_user_id(user_id)
    now = _utcnow()
    with _conn() as con:
        con.execute(
            """
            INSERT INTO user_google_accounts (
                user_id, google_sub, email, token_json, scopes_json,
                calendar_connected, created, updated
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                google_sub=excluded.google_sub,
                email=excluded.email,
                token_json=excluded.token_json,
                scopes_json=excluded.scopes_json,
                calendar_connected=excluded.calendar_connected,
                updated=excluded.updated
            """,
            (
                user_id,
                google_sub,
                _normalize_email(email),
                token_json,
                json.dumps(scopes),
                1 if calendar_connected else 0,
                now,
                now,
            ),
        )
    return get_user_google_account(user_id) or {}


def get_user_google_account(user_id: int) -> dict | None:
    init_db()
    user_id = _effective_user_id(user_id)
    with _conn() as con:
        row = con.execute("SELECT * FROM user_google_accounts WHERE user_id=?", (user_id,)).fetchone()
    if not row:
        return None
    result = dict(row)
    result["scopes"] = json.loads(result.get("scopes_json") or "[]")
    result["calendar_connected"] = bool(result.get("calendar_connected"))
    return result


def ensure_telegram_link_token(user_id: int, *, ttl_hours: int = 24) -> dict:
    init_db()
    user_id = _effective_user_id(user_id)
    now = _utcnow()
    expires_at = (datetime.utcnow() + timedelta(hours=ttl_hours)).isoformat()
    token = secrets.token_urlsafe(18)
    with _conn() as con:
        existing = con.execute("SELECT created FROM user_telegram_links WHERE user_id=?", (user_id,)).fetchone()
        created = existing["created"] if existing else now
        con.execute(
            """
            INSERT INTO user_telegram_links (
                user_id, link_state, link_token, token_expires_at, created, updated
            )
            VALUES (?, 'pending', ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                link_state='pending',
                link_token=excluded.link_token,
                token_expires_at=excluded.token_expires_at,
                updated=excluded.updated
            """,
            (user_id, token, expires_at, created, now),
        )
    return get_user_telegram_link(user_id) or {}


def get_user_telegram_link(user_id: int) -> dict | None:
    init_db()
    user_id = _effective_user_id(user_id)
    with _conn() as con:
        row = con.execute("SELECT * FROM user_telegram_links WHERE user_id=?", (user_id,)).fetchone()
    return dict(row) if row else None


def link_telegram_account(
    link_token: str,
    *,
    chat_id: str,
    telegram_user_id: str | None = None,
    telegram_username: str | None = None,
) -> dict:
    init_db()
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM user_telegram_links WHERE link_token=?",
            ((link_token or "").strip(),),
        ).fetchone()
        if not row:
            raise ValueError("Telegram link token is invalid.")
        link = dict(row)
        if link.get("token_expires_at") and datetime.fromisoformat(link["token_expires_at"]) < datetime.utcnow():
            raise ValueError("Telegram link token has expired.")

        existing_chat = con.execute(
            "SELECT user_id FROM user_telegram_links WHERE telegram_chat_id=?",
            (str(chat_id),),
        ).fetchone()
        if existing_chat and existing_chat["user_id"] != link["user_id"]:
            raise ValueError("This Telegram chat is already linked to another user.")

        con.execute(
            """
            UPDATE user_telegram_links
            SET telegram_chat_id=?,
                telegram_user_id=?,
                telegram_username=?,
                link_state='linked',
                link_token=NULL,
                token_expires_at=NULL,
                linked_at=?,
                updated=?
            WHERE user_id=?
            """,
            (
                str(chat_id),
                str(telegram_user_id) if telegram_user_id else None,
                telegram_username,
                _utcnow(),
                _utcnow(),
                link["user_id"],
            ),
        )
    return get_user_telegram_link(link["user_id"]) or {}


def get_user_by_chat_id(chat_id: str) -> dict | None:
    init_db()
    chat_id = str(chat_id)
    with _conn() as con:
        row = con.execute(
            """
            SELECT u.id
            FROM users u
            JOIN user_telegram_links t ON t.user_id = u.id
            WHERE t.telegram_chat_id=? AND t.link_state='linked'
            """,
            (chat_id,),
        ).fetchone()
    return get_user(row["id"]) if row else None


def resolve_user_id_for_chat(chat_id: str) -> int | None:
    linked = get_user_by_chat_id(chat_id)
    if linked:
        return linked["id"]
    try:
        from config.settings import TELEGRAM_CHAT_ID
    except Exception:
        TELEGRAM_CHAT_ID = None
    if TELEGRAM_CHAT_ID and str(chat_id) == str(TELEGRAM_CHAT_ID):
        return default_user_id()
    return None


def telegram_chat_for_user(user_id: int) -> str | None:
    user_id = _effective_user_id(user_id)
    link = get_user_telegram_link(user_id)
    if link and link.get("link_state") == "linked" and link.get("telegram_chat_id"):
        return str(link["telegram_chat_id"])
    if user_id == default_user_id():
        try:
            from config.settings import TELEGRAM_CHAT_ID
        except Exception:
            TELEGRAM_CHAT_ID = None
        return str(TELEGRAM_CHAT_ID) if TELEGRAM_CHAT_ID else None
    return None


def list_delivery_users() -> list[dict]:
    return [user for user in list_users(status="active") if telegram_chat_for_user(user["id"])]


# ── Habits ──────────────────────────────────────────────────────────────────

def add_habit(
    name: str,
    description: str = "",
    frequency: str = "daily",
    remind_at: str = "08:00",
    *,
    user_id: int | None = None,
) -> dict:
    init_db()
    user_id = _effective_user_id(user_id)
    now = _utcnow()
    with _conn() as con:
        cur = con.execute(
            """
            INSERT INTO habits (user_id, name, description, frequency, remind_at, created, updated)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, name.strip(), description.strip(), frequency, remind_at, now, now),
        )
        row_id = int(cur.lastrowid)
    return get_habit(row_id, user_id=user_id)


def get_habit(habit_id: int, *, user_id: int | None = None) -> dict | None:
    init_db()
    with _conn() as con:
        query = "SELECT * FROM habits WHERE id=?"
        params: list[Any] = [habit_id]
        if user_id is not None:
            query += " AND user_id=?"
            params.append(_effective_user_id(user_id))
        row = con.execute(query, params).fetchone()
    return dict(row) if row else None


def list_habits(active_only: bool = True, *, user_id: int | None = None) -> list[dict]:
    init_db()
    user_id = _effective_user_id(user_id)
    with _conn() as con:
        query = "SELECT * FROM habits WHERE user_id=?"
        params: list[Any] = [user_id]
        if active_only:
            query += " AND active=1"
        query += " ORDER BY remind_at"
        return [dict(row) for row in con.execute(query, params).fetchall()]


def delete_habit(habit_id: int, *, user_id: int | None = None) -> None:
    owner = get_habit(habit_id, user_id=user_id)
    if not owner:
        return
    with _conn() as con:
        con.execute(
            "UPDATE habits SET active=0, updated=? WHERE id=?",
            (_utcnow(), habit_id),
        )


def log_habit_done(
    habit_id: int,
    for_date: str | None = None,
    *,
    user_id: int | None = None,
) -> dict:
    habit = get_habit(habit_id, user_id=user_id)
    if not habit:
        raise ValueError(f"Habit {habit_id} not found.")
    d = for_date or date.today().isoformat()
    now = _utcnow()
    with _conn() as con:
        con.execute(
            """
            INSERT OR IGNORE INTO habit_logs (user_id, habit_id, date, created)
            VALUES (?, ?, ?, ?)
            """,
            (habit["user_id"], habit_id, d, now),
        )
    add_xp(10, user_id=habit["user_id"])
    return {"habit_id": habit_id, "date": d, "user_id": habit["user_id"]}


def habit_streak(habit_id: int, *, user_id: int | None = None) -> int:
    init_db()
    habit = get_habit(habit_id, user_id=user_id)
    if not habit:
        return 0
    with _conn() as con:
        rows = con.execute(
            """
            SELECT date FROM habit_logs
            WHERE habit_id=? AND user_id=?
            ORDER BY date DESC
            """,
            (habit_id, habit["user_id"]),
        ).fetchall()
    if not rows:
        return 0
    streak = 0
    cursor = date.today()
    for row in rows:
        logged = date.fromisoformat(row["date"])
        if logged == cursor:
            streak += 1
            cursor -= timedelta(days=1)
        else:
            break
    return streak


def habit_done_today(habit_id: int, *, user_id: int | None = None) -> bool:
    init_db()
    habit = get_habit(habit_id, user_id=user_id)
    if not habit:
        return False
    with _conn() as con:
        row = con.execute(
            "SELECT 1 FROM habit_logs WHERE habit_id=? AND user_id=? AND date=?",
            (habit_id, habit["user_id"], date.today().isoformat()),
        ).fetchone()
    return row is not None


# ── Personal goals ──────────────────────────────────────────────────────────

def add_goal(
    title: str,
    description: str = "",
    deadline: str | None = None,
    remind_at: str | None = None,
    remind_days: str = "daily",
    *,
    user_id: int | None = None,
) -> dict:
    init_db()
    user_id = _effective_user_id(user_id)
    now = _utcnow()
    with _conn() as con:
        cur = con.execute(
            """
            INSERT INTO personal_goals (
                user_id, title, description, deadline, remind_at, remind_days, created, updated
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, title.strip(), description.strip(), deadline, remind_at, remind_days, now, now),
        )
        row_id = int(cur.lastrowid)
    return get_goal(row_id, user_id=user_id)


def get_goal(goal_id: int, *, user_id: int | None = None) -> dict | None:
    init_db()
    with _conn() as con:
        query = "SELECT * FROM personal_goals WHERE id=?"
        params: list[Any] = [goal_id]
        if user_id is not None:
            query += " AND user_id=?"
            params.append(_effective_user_id(user_id))
        row = con.execute(query, params).fetchone()
    return dict(row) if row else None


def list_goals(status: str = "active", *, user_id: int | None = None) -> list[dict]:
    init_db()
    user_id = _effective_user_id(user_id)
    with _conn() as con:
        rows = con.execute(
            """
            SELECT * FROM personal_goals
            WHERE user_id=? AND status=?
            ORDER BY deadline IS NULL, deadline, updated DESC
            """,
            (user_id, status),
        ).fetchall()
        return [dict(row) for row in rows]


def update_goal_progress(goal_id: int, progress: int, *, user_id: int | None = None) -> dict | None:
    goal = get_goal(goal_id, user_id=user_id)
    if not goal:
        return None
    progress = max(0, min(100, progress))
    status = "done" if progress == 100 else "active"
    with _conn() as con:
        con.execute(
            """
            UPDATE personal_goals
            SET progress=?, status=?, updated=?
            WHERE id=?
            """,
            (progress, status, _utcnow(), goal_id),
        )
    if progress == 100:
        add_xp(100, user_id=goal["user_id"])
    return get_goal(goal_id, user_id=goal["user_id"])


# ── Reminders ───────────────────────────────────────────────────────────────

def add_reminder(
    title: str,
    message: str = "",
    remind_at: str = "09:00",
    repeat: str = "once",
    fire_date: str | None = None,
    *,
    user_id: int | None = None,
) -> dict:
    init_db()
    user_id = _effective_user_id(user_id)
    now = _utcnow()
    with _conn() as con:
        cur = con.execute(
            """
            INSERT INTO reminders (user_id, title, message, remind_at, repeat, fire_date, created, updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, title.strip(), message.strip(), remind_at, repeat, fire_date, now, now),
        )
        row_id = int(cur.lastrowid)
    return get_reminder(row_id, user_id=user_id)


def get_reminder(reminder_id: int, *, user_id: int | None = None) -> dict | None:
    init_db()
    with _conn() as con:
        query = "SELECT * FROM reminders WHERE id=?"
        params: list[Any] = [reminder_id]
        if user_id is not None:
            query += " AND user_id=?"
            params.append(_effective_user_id(user_id))
        row = con.execute(query, params).fetchone()
    return dict(row) if row else None


def list_reminders(active_only: bool = True, *, user_id: int | None = None) -> list[dict]:
    init_db()
    user_id = _effective_user_id(user_id)
    with _conn() as con:
        query = "SELECT * FROM reminders WHERE user_id=?"
        params: list[Any] = [user_id]
        if active_only:
            query += " AND active=1"
        query += " ORDER BY remind_at"
        return [dict(row) for row in con.execute(query, params).fetchall()]


def deactivate_reminder(reminder_id: int, *, user_id: int | None = None) -> None:
    reminder = get_reminder(reminder_id, user_id=user_id)
    if not reminder:
        return
    with _conn() as con:
        con.execute(
            "UPDATE reminders SET active=0, updated=? WHERE id=?",
            (_utcnow(), reminder_id),
        )


def log_reminder_fire(
    user_id: int,
    reminder_id: int,
    *,
    telegram_message_id: str | None = None,
    outcome: str = "sent",
    retry_count: int = 0,
) -> dict:
    init_db()
    user_id = _effective_user_id(user_id)
    fired_at = _utcnow()
    with _conn() as con:
        cur = con.execute(
            """
            INSERT INTO reminder_fires (
                user_id, reminder_id, telegram_message_id, fired_at, outcome, retry_count
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, reminder_id, telegram_message_id, fired_at, outcome, retry_count),
        )
        fire_id = int(cur.lastrowid)
        row = con.execute("SELECT * FROM reminder_fires WHERE id=?", (fire_id,)).fetchone()
    return dict(row) if row else {}


def list_reminder_fires(*, user_id: int | None = None) -> list[dict]:
    init_db()
    with _conn() as con:
        query = "SELECT * FROM reminder_fires"
        params: list[Any] = []
        if user_id is not None:
            query += " WHERE user_id=?"
            params.append(_effective_user_id(user_id))
        query += " ORDER BY fired_at DESC"
        return [dict(row) for row in con.execute(query, params).fetchall()]


# ── Check-ins ───────────────────────────────────────────────────────────────

def save_checkin(
    mood: int,
    note: str = "",
    for_date: str | None = None,
    *,
    user_id: int | None = None,
) -> dict:
    init_db()
    user_id = _effective_user_id(user_id)
    d = for_date or date.today().isoformat()
    now = _utcnow()
    existing = get_checkin(d, user_id=user_id)
    with _conn() as con:
        con.execute(
            """
            INSERT OR REPLACE INTO check_ins (id, user_id, date, mood, note, created)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (existing["id"] if existing else None, user_id, d, mood, note.strip(), now),
        )
        _ensure_profile_row(con, user_id)
        if not existing:
            con.execute(
                """
                UPDATE user_profiles
                SET total_checkins = total_checkins + 1,
                    relationship_xp = relationship_xp + 5,
                    updated = ?
                WHERE user_id = ?
                """,
                (now, user_id),
            )
    return get_checkin(d, user_id=user_id) or {}


def get_checkin(for_date: str | None = None, user_id: int | None = None) -> dict | None:
    init_db()
    d = for_date or date.today().isoformat()
    user_id = _effective_user_id(user_id)
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM check_ins WHERE user_id=? AND date=?",
            (user_id, d),
        ).fetchone()
    return dict(row) if row else None


def recent_checkins(days: int = 7, *, user_id: int | None = None) -> list[dict]:
    init_db()
    user_id = _effective_user_id(user_id)
    with _conn() as con:
        rows = con.execute(
            """
            SELECT * FROM check_ins
            WHERE user_id=?
            ORDER BY date DESC
            LIMIT ?
            """,
            (user_id, days),
        ).fetchall()
        return [dict(row) for row in rows]
