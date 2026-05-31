"""
src/integrations/telegram_digest.py — Project-aware morning digest and on-demand commands.

WHY this module exists:
  The existing journal digest (src/journal/digest.py) covers food/sleep/work stats.
  This module adds a *project-board* layer: how many tasks are done, when did you
  last touch each project, and what's the single best next action right now.

WHAT IT PROVIDES:
  send_morning_digest()    — called by the 08:00 scheduler job
  handle_projects_command() — called by Telegram /projects command
  handle_next_command()    — called by Telegram /next command

HOW DB PATHS WORK:
  We compute the path to data/projects.db relative to this file so it works
  regardless of the cwd when the daemon is launched.
  This file lives at:  src/integrations/telegram_digest.py
  Project root is:     ../../..  (three levels up)
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

# ── Path resolution ────────────────────────────────────────────────────────────
# src/integrations/ → src/ → project_root/
_PROJECT_ROOT = Path(__file__).parent.parent.parent
_DB_PATH = _PROJECT_ROOT / "data" / "projects.db"


# ── DB helpers ─────────────────────────────────────────────────────────────────

def _connect() -> sqlite3.Connection:
    """Open a read-only-friendly connection with Row factory."""
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _days_ago(iso_ts: str | None) -> int | None:
    """
    Return how many whole days ago an ISO-8601 timestamp was.

    WHY whole days?
      The digest is a daily message — fractional days add noise.
      '0 days ago' means 'today', '1 day ago' means 'yesterday', etc.
    """
    if not iso_ts:
        return None
    try:
        # Handle both 'YYYY-MM-DDTHH:MM:SS.ffffff' and 'YYYY-MM-DD HH:MM:SS'
        ts = iso_ts.replace(" ", "T").split(".")[0]
        dt = datetime.fromisoformat(ts)
        # Treat stored timestamps as local time (the daemon runs locally)
        now = datetime.now()
        delta = now - dt
        return max(0, delta.days)
    except (ValueError, TypeError):
        return None


def _relative_label(days: int | None, all_todo: bool = False) -> str:
    """
    Convert a days-since-last-touch number into a human label.

      0  → 'active today'
      1  → '1d ago'   (or 'started 1d ago' if the project has no done tasks yet)
      N  → 'Nd ago'
    """
    if days is None:
        return "new"
    if days == 0:
        return "active today"
    label = f"{days}d ago"
    if all_todo and days <= 3:
        return f"started {label}"
    return label


# ── Core query ─────────────────────────────────────────────────────────────────

def get_project_summary() -> list[dict]:
    """
    Query data/projects.db and return one dict per active project.

    Each dict contains:
      name          str   — project name
      total_tasks   int   — total number of tasks
      done_tasks    int   — tasks with status='done'
      open_tasks    int   — tasks NOT done (todo | in_progress | blocked)
      last_updated  str   — ISO timestamp of most recent activity
      days_since    int   — whole days since last_updated (0 = today)

    WHY we compute last_updated as max(task.updated, project.updated)?
      A project's board row is touched when its name/status changes.
      A task row is touched whenever a task is ticked or edited.
      We want to reward either kind of activity so a project doesn't look
      stale just because you only edited the project row, not a task.
    """
    sql = """
        SELECT
            p.id,
            p.name,
            p.status,
            p.created,
            COUNT(t.id)                                              AS total_tasks,
            COALESCE(SUM(CASE WHEN t.status = 'done' THEN 1 ELSE 0 END), 0) AS done_tasks,
            -- last activity = whichever is newer: task or project row
            MAX(
                CASE
                    WHEN t.updated IS NOT NULL AND t.updated > p.updated
                        THEN t.updated
                    ELSE p.updated
                END
            )                                                        AS last_updated
        FROM  projects p
        LEFT  JOIN tasks t ON t.project_id = p.id
        WHERE p.status = 'active'
        GROUP BY p.id, p.name, p.status, p.created
        ORDER BY last_updated DESC
    """
    try:
        conn = _connect()
        rows = conn.execute(sql).fetchall()
        conn.close()
    except Exception as e:
        log.error("get_project_summary DB error: %s", e)
        return []

    results = []
    for r in rows:
        total     = r["total_tasks"]
        done      = r["done_tasks"]
        open_cnt  = total - done
        days      = _days_ago(r["last_updated"])
        all_todo  = (done == 0)
        results.append({
            "id":           r["id"],
            "name":         r["name"],
            "total_tasks":  total,
            "done_tasks":   done,
            "open_tasks":   open_cnt,
            "last_updated": r["last_updated"],
            "days_since":   days,
            "label":        _relative_label(days, all_todo=all_todo),
        })
    return results


def get_top_next_task() -> dict | None:
    """
    Return the single highest-priority open task across all active projects.

    Priority order: high → medium → low.
    Within the same priority, prefer tasks whose project was most recently active.

    WHY 'todo' AND 'in_progress' but not 'blocked'?
      'blocked' tasks can't be acted on without unblocking something first.
      Surfacing them as 'next' would frustrate rather than help.
    """
    sql = """
        SELECT
            t.id,
            t.title,
            t.priority,
            t.status,
            p.name AS project_name,
            t.updated
        FROM  tasks t
        JOIN  projects p ON p.id = t.project_id
        WHERE p.status = 'active'
          AND t.status IN ('todo', 'in_progress')
        ORDER BY
            CASE t.priority
                WHEN 'high'   THEN 1
                WHEN 'medium' THEN 2
                WHEN 'low'    THEN 3
                ELSE 4
            END,
            t.updated DESC
        LIMIT 1
    """
    try:
        conn = _connect()
        row = conn.execute(sql).fetchone()
        conn.close()
    except Exception as e:
        log.error("get_top_next_task DB error: %s", e)
        return None

    if not row:
        return None
    return {
        "id":           row["id"],
        "title":        row["title"],
        "priority":     row["priority"],
        "status":       row["status"],
        "project_name": row["project_name"],
    }


# ── Formatting ─────────────────────────────────────────────────────────────────

def format_morning_digest(projects: list[dict], top_task: dict | None = None) -> str:
    """
    Build a clean Telegram-ready morning digest string.

    Markdown rules used here:
      *bold*  — project names and task title
      _italic_ — subtle hint text
      No headers (Telegram renders them oddly without HTML mode)

    WHY show done/total instead of percent?
      '3/8 done' is instantly scannable; '37.5%' requires mental arithmetic.
    """
    lines = ["🌅 *Good morning, Rana!*", ""]

    if not projects:
        lines.append("📋 No active projects found.")
    else:
        lines.append("📋 *Your active projects:*")
        for p in projects:
            done  = p["done_tasks"]
            total = p["total_tasks"]
            label = p["label"]
            name  = p["name"]
            # Shorten very long project names for the digest line
            short_name = name if len(name) <= 28 else name[:25] + "…"
            lines.append(f"• *{short_name}* — {done}/{total} done · {label}")

    lines.append("")

    if top_task:
        lines.append("🔥 *Top priority next task:*")
        lines.append(f"_{top_task['title']}_ → {top_task['project_name']}")
    else:
        lines.append("🎉 No open tasks — everything is done!")

    lines.append("")
    lines.append("Type /next for your next action, /projects for full view.")

    return "\n".join(lines)


def format_projects_command(projects: list[dict]) -> str:
    """
    Format the /projects response — a slightly more verbose version of the digest.

    WHY more verbose than the digest?
      The digest is a push notification — brevity matters.
      /projects is a pull request — you asked, so more detail is welcome.
    """
    if not projects:
        return "📋 No active projects."

    lines = ["📋 *Active projects:*", ""]
    for p in projects:
        done  = p["done_tasks"]
        total = p["total_tasks"]
        open_ = p["open_tasks"]
        label = p["label"]
        pct   = int(done / total * 100) if total else 0
        name  = p["name"]
        lines.append(f"*{name}*")
        lines.append(f"  {done}/{total} tasks done ({pct}%) · {open_} open · {label}")
        lines.append("")

    lines.append("_/next — show the single best next action_")
    return "\n".join(lines).rstrip()


# ── Public send functions ──────────────────────────────────────────────────────

def send_morning_digest() -> bool:
    """
    Fetch project data, format the digest, and send it via Telegram.

    Called by the 08:00 APScheduler job in src/notify/scheduler.py.

    WHY 08:00 and not 07:30 (where the journal digest fires)?
      The journal digest covers sleep/food/work stats for the previous day.
      The project digest is about what to work on *today* — a minute later
      keeps the two messages visually distinct in your chat history.
    """
    try:
        projects = get_project_summary()
        top_task = get_top_next_task()
        text = format_morning_digest(projects, top_task)
        from src.integrations.telegram_bot import send_message
        ok = send_message(text)
        if ok:
            log.info("Project morning digest sent (%d projects)", len(projects))
        else:
            log.warning("Project morning digest: Telegram send returned False")
        return ok
    except Exception as e:
        log.error("send_morning_digest failed: %s", e)
        return False


def handle_projects_command() -> str:
    """
    Return the /projects reply string.

    Called from src/integrations/telegram_commands.py when the user types /projects.
    Returns a string so the command handler can send it via send_message().
    """
    try:
        projects = get_project_summary()
        return format_projects_command(projects)
    except Exception as e:
        log.error("handle_projects_command failed: %s", e)
        return f"❌ Could not fetch projects: {e}"


def handle_next_command() -> str:
    """
    Return the /next reply string — the single best next task across all projects.

    WHY single task?
      Decision fatigue is real.  Showing one clear action is more actionable
      than a ranked list.  If you want more, use /projects.
    """
    try:
        task = get_top_next_task()
        if not task:
            return "🎉 No open tasks! All projects are up to date."
        priority_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(task["priority"], "⚪")
        return (
            f"▶️ *Next action:*\n"
            f"{priority_icon} _{task['title']}_\n"
            f"📁 {task['project_name']}"
        )
    except Exception as e:
        log.error("handle_next_command failed: %s", e)
        return f"❌ Could not fetch next task: {e}"
