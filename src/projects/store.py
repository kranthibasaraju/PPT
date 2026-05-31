"""SQLite-backed project and task store for PPT."""
from __future__ import annotations
import sqlite3
import logging
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

_DB_PATH = Path(__file__).parent.parent.parent / "data" / "projects.db"


def _conn() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(_DB_PATH))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    return con


def init_db() -> None:
    """Create tables if they don't exist."""
    with _conn() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS projects (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            name     TEXT NOT NULL UNIQUE,
            status   TEXT NOT NULL DEFAULT 'active',   -- active | paused | done
            goal     TEXT,
            created  TEXT NOT NULL,
            updated  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS tasks (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id  INTEGER NOT NULL REFERENCES projects(id),
            title       TEXT NOT NULL,
            status      TEXT NOT NULL DEFAULT 'todo',  -- todo | in_progress | done | blocked
            priority    TEXT NOT NULL DEFAULT 'medium', -- low | medium | high
            due_date    TEXT,
            notes       TEXT,
            created     TEXT NOT NULL,
            updated     TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS conversation_history (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            role     TEXT NOT NULL,   -- 'user' | 'assistant'
            content  TEXT NOT NULL,
            created  TEXT NOT NULL
        );
        """)
    log.info("DB initialised at %s", _DB_PATH)


# ── Projects ──────────────────────────────────────────────────────────────────

def add_project(name: str, goal: str = "") -> dict:
    now = datetime.utcnow().isoformat()
    with _conn() as con:
        cur = con.execute(
            "INSERT INTO projects (name, goal, created, updated) VALUES (?,?,?,?)",
            (name.strip(), goal.strip(), now, now),
        )
        row_id = cur.lastrowid
    return get_project(row_id)


def get_project(project_id: int) -> dict | None:
    with _conn() as con:
        row = con.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        return dict(row) if row else None


def get_project_by_name(name: str) -> dict | None:
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM projects WHERE name LIKE ?", (f"%{name.strip()}%",)
        ).fetchone()
        return dict(row) if row else None


def list_projects(status: str = None) -> list[dict]:
    with _conn() as con:
        if status:
            rows = con.execute("SELECT * FROM projects WHERE status=? ORDER BY updated DESC", (status,)).fetchall()
        else:
            rows = con.execute("SELECT * FROM projects ORDER BY updated DESC").fetchall()
        return [dict(r) for r in rows]


def update_project_status(project_id: int, status: str) -> dict | None:
    now = datetime.utcnow().isoformat()
    with _conn() as con:
        con.execute("UPDATE projects SET status=?, updated=? WHERE id=?", (status, now, project_id))
    return get_project(project_id)


# ── Tasks ─────────────────────────────────────────────────────────────────────

def add_task(project_id: int, title: str, priority: str = "medium", due_date: str = None, notes: str = "") -> dict:
    now = datetime.utcnow().isoformat()
    with _conn() as con:
        cur = con.execute(
            "INSERT INTO tasks (project_id, title, priority, due_date, notes, created, updated) VALUES (?,?,?,?,?,?,?)",
            (project_id, title.strip(), priority, due_date, notes.strip(), now, now),
        )
        row_id = cur.lastrowid
    return get_task(row_id)


def get_task(task_id: int) -> dict | None:
    with _conn() as con:
        row = con.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        return dict(row) if row else None


def list_tasks(project_id: int = None, status: str = None) -> list[dict]:
    with _conn() as con:
        query = "SELECT * FROM tasks WHERE 1=1"
        params: list = []
        if project_id:
            query += " AND project_id=?"
            params.append(project_id)
        if status:
            if status == "open":
                query += " AND status!=?"
                params.append("done")
            else:
                query += " AND status=?"
                params.append(status)
        query += " ORDER BY priority DESC, updated DESC"
        rows = con.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def update_task_status(task_id: int, status: str) -> dict | None:
    now = datetime.utcnow().isoformat()
    with _conn() as con:
        con.execute("UPDATE tasks SET status=?, updated=? WHERE id=?", (status, now, task_id))
    return get_task(task_id)


def update_task(
    task_id: int,
    *,
    title: str | None = None,
    priority: str | None = None,
    due_date: str | None = None,
    notes: str | None = None,
    status: str | None = None,
) -> dict | None:
    current = get_task(task_id)
    if not current:
        return None

    now = datetime.utcnow().isoformat()
    payload = {
        "title": current["title"] if title is None else title.strip(),
        "priority": current["priority"] if priority is None else priority,
        "due_date": current["due_date"] if due_date is None else due_date,
        "notes": current["notes"] if notes is None else notes.strip(),
        "status": current["status"] if status is None else status,
    }
    with _conn() as con:
        con.execute(
            """
            UPDATE tasks
            SET title=?, priority=?, due_date=?, notes=?, status=?, updated=?
            WHERE id=?
            """,
            (
                payload["title"],
                payload["priority"],
                payload["due_date"],
                payload["notes"],
                payload["status"],
                now,
                task_id,
            ),
        )
    return get_task(task_id)


def find_task(title_fragment: str, project_id: int = None) -> dict | None:
    with _conn() as con:
        query = "SELECT * FROM tasks WHERE title LIKE ?"
        params: list = [f"%{title_fragment.strip()}%"]
        if project_id:
            query += " AND project_id=?"
            params.append(project_id)
        query += " ORDER BY updated DESC LIMIT 1"
        row = con.execute(query, params).fetchone()
        return dict(row) if row else None


# ── Conversation history ──────────────────────────────────────────────────────

def save_turn(role: str, content: str) -> None:
    """Persist a single message (role='user'|'assistant') to the DB."""
    now = datetime.utcnow().isoformat()
    with _conn() as con:
        con.execute(
            "INSERT INTO conversation_history (role, content, created) VALUES (?,?,?)",
            (role, content, now),
        )


def load_recent_turns(n: int = 10) -> list[dict]:
    """
    Return the last *n* messages from conversation history in chronological order.

    A value of n=10 returns the 10 most recent messages (roughly 5 exchanges).
    """
    with _conn() as con:
        rows = con.execute(
            "SELECT role, content FROM conversation_history ORDER BY id DESC LIMIT ?",
            (n,),
        ).fetchall()
    # Rows come back newest-first; reverse so history is chronological
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


def trim_history(max_rows: int = 20) -> None:
    """Delete the oldest rows so that at most max_rows messages are kept."""
    with _conn() as con:
        count = con.execute(
            "SELECT COUNT(*) FROM conversation_history"
        ).fetchone()[0]
        if count > max_rows:
            excess = count - max_rows
            con.execute(
                "DELETE FROM conversation_history WHERE id IN "
                "(SELECT id FROM conversation_history ORDER BY id ASC LIMIT ?)",
                (excess,),
            )
            log.debug("Trimmed %d old conversation message(s)", excess)


# Initialise on import
init_db()
