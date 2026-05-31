"""
src/journal/store.py — SQLite persistence for all journal domains.

WHY one store for all 4 modules?
  Food, sleep, work, and money all have *daily* entries.
  Keeping them in one DB file means one connection, one backup,
  and easy cross-domain queries (e.g. "on days I slept < 6h, did I spend more?").

TABLES:
  food_logs      — individual meal entries
  sleep_logs     — one entry per night
  work_sessions  — each work block (clock-in → clock-out)
  spending_logs  — each purchase/transaction
  budgets        — weekly or monthly spending caps per category

DATA PHILOSOPHY:
  Everything is keyed by ISO date (YYYY-MM-DD) or datetime.
  source column tracks whether entry came from 'web' or 'telegram'
  so we can later show quick-capture vs deliberate-entry stats.
"""
from __future__ import annotations
import sqlite3
import logging
from datetime import datetime, date, timedelta
from pathlib import Path

log = logging.getLogger(__name__)

_DB_PATH = Path(__file__).parent.parent.parent / "data" / "journal.db"

MEAL_TYPES = ["breakfast", "lunch", "dinner", "snack", "drink"]
SPEND_CATEGORIES = ["food", "transport", "shopping", "health",
                    "entertainment", "bills", "education", "other"]


# ── Connection ────────────────────────────────────────────────────────────────

def _conn() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(_DB_PATH))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    return con


# ── Schema ────────────────────────────────────────────────────────────────────

def init_db() -> None:
    """Create all tables. Safe to call on every startup."""
    with _conn() as con:
        con.executescript("""
        -- ── FOOD ──────────────────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS food_logs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            date        TEXT    NOT NULL,          -- YYYY-MM-DD
            meal_type   TEXT    NOT NULL DEFAULT 'meal', -- breakfast|lunch|dinner|snack|drink
            name        TEXT    NOT NULL,
            calories    INTEGER,
            protein_g   REAL,
            carbs_g     REAL,
            fat_g       REAL,
            notes       TEXT,
            source      TEXT    NOT NULL DEFAULT 'web',
            created     TEXT    NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_food_date ON food_logs(date);

        -- ── SLEEP ─────────────────────────────────────────────────────────
        -- One row per night.  date = the night you went to bed.
        CREATE TABLE IF NOT EXISTS sleep_logs (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            date         TEXT    NOT NULL UNIQUE,  -- YYYY-MM-DD (night of)
            bedtime      TEXT,                     -- HH:MM 24h
            waketime     TEXT,                     -- HH:MM 24h
            duration_min INTEGER,                  -- total minutes asleep
            quality      INTEGER,                  -- 1 (terrible) – 5 (excellent)
            deep_pct     INTEGER,                  -- % deep sleep (from device, optional)
            rem_pct      INTEGER,                  -- % REM sleep (from device, optional)
            notes        TEXT,
            source       TEXT    NOT NULL DEFAULT 'web',
            created      TEXT    NOT NULL
        );

        -- ── WORK ──────────────────────────────────────────────────────────
        -- Each row = one work session (a block of focused work).
        -- end_time NULL means currently clocked in.
        CREATE TABLE IF NOT EXISTS work_sessions (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            date         TEXT    NOT NULL,         -- YYYY-MM-DD
            start_time   TEXT    NOT NULL,         -- HH:MM
            end_time     TEXT,                     -- HH:MM or NULL if ongoing
            duration_min INTEGER,                  -- filled when session ends
            task         TEXT,
            project      TEXT,
            mood_before  INTEGER,                  -- 1-5 how you felt starting
            mood_after   INTEGER,                  -- 1-5 how you felt finishing
            notes        TEXT,
            source       TEXT    NOT NULL DEFAULT 'web',
            created      TEXT    NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_work_date ON work_sessions(date);

        -- ── MONEY ─────────────────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS spending_logs (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            date           TEXT    NOT NULL,       -- YYYY-MM-DD
            amount         REAL    NOT NULL,
            currency       TEXT    NOT NULL DEFAULT 'USD',
            category       TEXT    NOT NULL DEFAULT 'other',
            description    TEXT    NOT NULL,
            payment_method TEXT,                   -- cash|card|upi|other
            notes          TEXT,
            source         TEXT    NOT NULL DEFAULT 'web',
            created        TEXT    NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_spend_date ON spending_logs(date);

        -- Budget caps (weekly or monthly, per category or 'total')
        CREATE TABLE IF NOT EXISTS budgets (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            period   TEXT    NOT NULL DEFAULT 'weekly',  -- weekly|monthly
            category TEXT    NOT NULL DEFAULT 'total',
            amount   REAL    NOT NULL,
            currency TEXT    NOT NULL DEFAULT 'USD',
            active   INTEGER NOT NULL DEFAULT 1,
            created  TEXT    NOT NULL
        );
        """)
    log.info("journal.db initialised at %s", _DB_PATH)


# ── FOOD ──────────────────────────────────────────────────────────────────────

def log_food(name: str, meal_type: str = "meal", date_str: str | None = None,
             calories: int | None = None, protein_g: float | None = None,
             carbs_g: float | None = None, fat_g: float | None = None,
             notes: str = "", source: str = "web") -> dict:
    d = date_str or date.today().isoformat()
    now = datetime.utcnow().isoformat()
    with _conn() as con:
        cur = con.execute("""
            INSERT INTO food_logs
              (date, meal_type, name, calories, protein_g, carbs_g, fat_g, notes, source, created)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (d, meal_type, name.strip(), calories, protein_g, carbs_g, fat_g,
              notes.strip(), source, now))
        row_id = cur.lastrowid
    with _conn() as con:
        return dict(con.execute("SELECT * FROM food_logs WHERE id=?", (row_id,)).fetchone())


def food_today(date_str: str | None = None) -> list[dict]:
    d = date_str or date.today().isoformat()
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM food_logs WHERE date=? ORDER BY created", (d,)
        ).fetchall()
    return [dict(r) for r in rows]


def food_daily_totals(date_str: str | None = None) -> dict:
    """Return summed macros for a given day."""
    d = date_str or date.today().isoformat()
    with _conn() as con:
        row = con.execute("""
            SELECT
              COUNT(*) as meals,
              COALESCE(SUM(calories), 0)  as calories,
              COALESCE(SUM(protein_g), 0) as protein_g,
              COALESCE(SUM(carbs_g), 0)   as carbs_g,
              COALESCE(SUM(fat_g), 0)     as fat_g
            FROM food_logs WHERE date=?
        """, (d,)).fetchone()
    return dict(row) if row else {"meals": 0, "calories": 0}


def food_week_summary() -> list[dict]:
    """Returns daily totals for the last 7 days."""
    result = []
    for i in range(6, -1, -1):
        d = (date.today() - timedelta(days=i)).isoformat()
        totals = food_daily_totals(d)
        totals["date"] = d
        result.append(totals)
    return result


def delete_food_log(log_id: int) -> None:
    with _conn() as con:
        con.execute("DELETE FROM food_logs WHERE id=?", (log_id,))


# ── SLEEP ─────────────────────────────────────────────────────────────────────

def log_sleep(duration_min: int, quality: int, date_str: str | None = None,
              bedtime: str | None = None, waketime: str | None = None,
              deep_pct: int | None = None, rem_pct: int | None = None,
              notes: str = "", source: str = "web") -> dict:
    """Log a sleep session.  date = the night you went to bed."""
    d = date_str or (date.today() - timedelta(days=1)).isoformat()  # default = last night
    now = datetime.utcnow().isoformat()
    with _conn() as con:
        con.execute("""
            INSERT OR REPLACE INTO sleep_logs
              (date, bedtime, waketime, duration_min, quality, deep_pct, rem_pct, notes, source, created)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (d, bedtime, waketime, duration_min, quality, deep_pct, rem_pct,
              notes.strip(), source, now))
    with _conn() as con:
        row = con.execute("SELECT * FROM sleep_logs WHERE date=?", (d,)).fetchone()
    return dict(row) if row else {}


def get_sleep(date_str: str | None = None) -> dict | None:
    d = date_str or (date.today() - timedelta(days=1)).isoformat()
    with _conn() as con:
        row = con.execute("SELECT * FROM sleep_logs WHERE date=?", (d,)).fetchone()
    return dict(row) if row else None


def sleep_week_summary() -> list[dict]:
    result = []
    for i in range(6, -1, -1):
        d = (date.today() - timedelta(days=i+1)).isoformat()  # sleep nights
        entry = get_sleep(d) or {"date": d, "duration_min": None, "quality": None}
        if "date" not in entry:
            entry["date"] = d
        result.append(entry)
    return result


def sleep_avg_hours(days: int = 7) -> float | None:
    """Average sleep duration in hours over the last N nights."""
    with _conn() as con:
        rows = con.execute("""
            SELECT duration_min FROM sleep_logs
            ORDER BY date DESC LIMIT ?
        """, (days,)).fetchall()
    if not rows:
        return None
    valid = [r["duration_min"] for r in rows if r["duration_min"]]
    return round(sum(valid) / len(valid) / 60, 1) if valid else None


# ── WORK ──────────────────────────────────────────────────────────────────────

def clock_in(task: str = "", project: str = "", mood_before: int | None = None,
             date_str: str | None = None, source: str = "web") -> dict:
    """Start a new work session.  Returns the session row."""
    d = date_str or date.today().isoformat()
    now_str = datetime.now().strftime("%H:%M")
    now_iso = datetime.utcnow().isoformat()
    with _conn() as con:
        cur = con.execute("""
            INSERT INTO work_sessions
              (date, start_time, task, project, mood_before, source, created)
            VALUES (?,?,?,?,?,?,?)
        """, (d, now_str, task.strip(), project.strip(), mood_before, source, now_iso))
        row_id = cur.lastrowid
    with _conn() as con:
        return dict(con.execute("SELECT * FROM work_sessions WHERE id=?", (row_id,)).fetchone())


def clock_out(session_id: int | None = None, mood_after: int | None = None,
              notes: str = "") -> dict | None:
    """End the most recent active (open) work session."""
    now_str = datetime.now().strftime("%H:%M")
    with _conn() as con:
        if session_id:
            row = con.execute(
                "SELECT * FROM work_sessions WHERE id=?", (session_id,)
            ).fetchone()
        else:
            row = con.execute("""
                SELECT * FROM work_sessions
                WHERE end_time IS NULL
                ORDER BY created DESC LIMIT 1
            """).fetchone()
        if not row:
            return None
        row = dict(row)
        # Calculate duration
        try:
            start = datetime.strptime(row["date"] + " " + row["start_time"], "%Y-%m-%d %H:%M")
            end   = datetime.strptime(row["date"] + " " + now_str, "%Y-%m-%d %H:%M")
            duration = max(0, int((end - start).total_seconds() / 60))
        except Exception:
            duration = 0
        con.execute("""
            UPDATE work_sessions
            SET end_time=?, duration_min=?, mood_after=?, notes=?
            WHERE id=?
        """, (now_str, duration, mood_after, notes.strip(), row["id"]))
    with _conn() as con:
        r = con.execute("SELECT * FROM work_sessions WHERE id=?", (row["id"],)).fetchone()
    return dict(r) if r else None


def active_session() -> dict | None:
    """Return the currently open work session, if any."""
    with _conn() as con:
        row = con.execute("""
            SELECT * FROM work_sessions
            WHERE end_time IS NULL
            ORDER BY created DESC LIMIT 1
        """).fetchone()
    return dict(row) if row else None


def work_today(date_str: str | None = None) -> list[dict]:
    d = date_str or date.today().isoformat()
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM work_sessions WHERE date=? ORDER BY start_time", (d,)
        ).fetchall()
    return [dict(r) for r in rows]


def work_daily_total_min(date_str: str | None = None) -> int:
    d = date_str or date.today().isoformat()
    with _conn() as con:
        row = con.execute("""
            SELECT COALESCE(SUM(duration_min), 0) as total
            FROM work_sessions WHERE date=? AND end_time IS NOT NULL
        """, (d,)).fetchone()
    return row["total"] if row else 0


def work_week_summary() -> list[dict]:
    result = []
    for i in range(6, -1, -1):
        d = (date.today() - timedelta(days=i)).isoformat()
        sessions = work_today(d)
        total = sum(s["duration_min"] or 0 for s in sessions if s["end_time"])
        result.append({"date": d, "sessions": len(sessions), "total_min": total})
    return result


# ── MONEY ─────────────────────────────────────────────────────────────────────

def log_spend(amount: float, description: str, category: str = "other",
              date_str: str | None = None, payment_method: str = "",
              notes: str = "", source: str = "web") -> dict:
    d = date_str or date.today().isoformat()
    now = datetime.utcnow().isoformat()
    with _conn() as con:
        cur = con.execute("""
            INSERT INTO spending_logs
              (date, amount, category, description, payment_method, notes, source, created)
            VALUES (?,?,?,?,?,?,?,?)
        """, (d, round(float(amount), 2), category, description.strip(),
              payment_method, notes.strip(), source, now))
        row_id = cur.lastrowid
    with _conn() as con:
        return dict(con.execute("SELECT * FROM spending_logs WHERE id=?", (row_id,)).fetchone())


def spend_today(date_str: str | None = None) -> list[dict]:
    d = date_str or date.today().isoformat()
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM spending_logs WHERE date=? ORDER BY created DESC", (d,)
        ).fetchall()
    return [dict(r) for r in rows]


def spend_total(date_str: str | None = None) -> float:
    d = date_str or date.today().isoformat()
    with _conn() as con:
        row = con.execute(
            "SELECT COALESCE(SUM(amount), 0) as total FROM spending_logs WHERE date=?", (d,)
        ).fetchone()
    return round(row["total"], 2) if row else 0.0


def spend_week_total(weeks_back: int = 0) -> float:
    """Total spending for the current (or past) week."""
    today = date.today()
    week_start = today - timedelta(days=today.weekday() + 7 * weeks_back)
    week_end   = week_start + timedelta(days=6)
    with _conn() as con:
        row = con.execute("""
            SELECT COALESCE(SUM(amount), 0) as total FROM spending_logs
            WHERE date >= ? AND date <= ?
        """, (week_start.isoformat(), week_end.isoformat())).fetchone()
    return round(row["total"], 2) if row else 0.0


def spend_by_category(date_from: str, date_to: str) -> list[dict]:
    with _conn() as con:
        rows = con.execute("""
            SELECT category,
                   COUNT(*) as count,
                   COALESCE(SUM(amount), 0) as total
            FROM spending_logs
            WHERE date >= ? AND date <= ?
            GROUP BY category ORDER BY total DESC
        """, (date_from, date_to)).fetchall()
    return [dict(r) for r in rows]


def delete_spend(spend_id: int) -> None:
    with _conn() as con:
        con.execute("DELETE FROM spending_logs WHERE id=?", (spend_id,))


# ── Budgets ───────────────────────────────────────────────────────────────────

def set_budget(amount: float, period: str = "weekly", category: str = "total") -> dict:
    now = datetime.utcnow().isoformat()
    with _conn() as con:
        # Deactivate any existing budget for this period+category
        con.execute("""
            UPDATE budgets SET active=0 WHERE period=? AND category=?
        """, (period, category))
        cur = con.execute("""
            INSERT INTO budgets (period, category, amount, created) VALUES (?,?,?,?)
        """, (period, category, round(float(amount), 2), now))
        row_id = cur.lastrowid
    with _conn() as con:
        return dict(con.execute("SELECT * FROM budgets WHERE id=?", (row_id,)).fetchone())


def get_budget(period: str = "weekly", category: str = "total") -> dict | None:
    with _conn() as con:
        row = con.execute("""
            SELECT * FROM budgets WHERE period=? AND category=? AND active=1
            ORDER BY created DESC LIMIT 1
        """, (period, category)).fetchone()
    return dict(row) if row else None


def budget_status() -> dict:
    """Compare this week's spending against the weekly budget."""
    budget = get_budget("weekly", "total")
    spent = spend_week_total()
    if not budget:
        return {"budget": None, "spent": spent, "pct": None, "over": False}
    pct = round(spent / budget["amount"] * 100) if budget["amount"] else 0
    return {
        "budget": budget["amount"],
        "spent": spent,
        "pct": pct,
        "over": spent > budget["amount"],
        "remaining": round(budget["amount"] - spent, 2)
    }
