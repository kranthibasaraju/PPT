"""
src/llm/context_builder.py — build a compact board context string for the LLM.

WHY this exists:
  Ollama knows nothing about Rana by default.  Injecting a live snapshot of
  the board into every system prompt gives it real personal context — what
  habits are pending, which goal is due, how the epics are progressing.

  This is the difference between a generic chatbot and a personal assistant.

HOW it works:
  Calls the same data collectors as /api/board, formats them as compact text
  (not JSON — LLMs read prose better), and returns a string under ~600 tokens
  so it fits comfortably in every model's context window.

USAGE:
    from src.llm.context_builder import build_context
    ctx = build_context()
    # Pass as prefix to system prompt in ollama_client.complete()
"""
from __future__ import annotations
import logging
from datetime import datetime, date
from pathlib import Path
import re

log = logging.getLogger(__name__)

_ROOT = Path(__file__).parent.parent.parent


def build_context() -> str:
    """
    Return a compact multi-line string summarising Rana's current board state.
    Each section fails silently — a broken DB won't take down the whole context.
    """
    lines: list[str] = []
    today = date.today().isoformat()
    now   = datetime.now().strftime("%A %d %B %Y, %H:%M")

    lines.append(f"Today: {now}")

    # ── Habits ────────────────────────────────────────────────────────────────
    try:
        from src.notify import store as nstore
        habits = nstore.list_habits(active_only=True)
        pending = [h["name"] for h in habits if not nstore.habit_done_today(h["id"])]
        done    = [h["name"] for h in habits if nstore.habit_done_today(h["id"])]
        streaks = {h["name"]: nstore.habit_streak(h["id"]) for h in habits if nstore.habit_streak(h["id"]) > 1}
        if pending:
            lines.append(f"Habits pending: {', '.join(pending)}")
        if done:
            lines.append(f"Habits done today: {', '.join(f'{n} ✓' for n in done)}")
        if streaks:
            streak_strs = [f"{n} 🔥{d}d" for n, d in streaks.items()]
            lines.append(f"Streaks: {', '.join(streak_strs)}")
    except Exception as e:
        log.debug("Habits context failed: %s", e)

    # ── Reminders ─────────────────────────────────────────────────────────────
    try:
        from src.notify import store as nstore
        reminders = nstore.list_reminders(active_only=True)
        today_reminders = [
            f"{r['remind_at']} {r['title']}"
            for r in reminders
            if r["repeat"] != "once" or r.get("fire_date") == today
        ]
        if today_reminders:
            lines.append(f"Reminders today: {', '.join(today_reminders)}")
    except Exception as e:
        log.debug("Reminders context failed: %s", e)

    # ── Goals ─────────────────────────────────────────────────────────────────
    try:
        from src.notify import store as nstore
        goals = nstore.list_goals(status="active")
        goal_strs = []
        for g in goals:
            s = f"{g['title']} ({g['progress']}%"
            if g.get("deadline"):
                days = (date.fromisoformat(g["deadline"]) - date.today()).days
                if days < 0:
                    s += ", overdue!"
                elif days == 0:
                    s += ", due today!"
                else:
                    s += f", {days}d left"
            s += ")"
            goal_strs.append(s)
        if goal_strs:
            lines.append(f"Personal goals: {', '.join(goal_strs)}")
    except Exception as e:
        log.debug("Goals context failed: %s", e)

    # ── Epics ─────────────────────────────────────────────────────────────────
    try:
        docs_dir = _ROOT / "docs"
        epic_strs = []
        for f in sorted(docs_dir.glob("EPIC_*.md")):
            text = f.read_text(encoding="utf-8")
            name_match = re.search(r"^#\s+Epic:\s*(.+)", text, re.MULTILINE)
            name = name_match.group(1).strip() if name_match else f.stem
            done  = len(re.findall(r"^\s*[-|]\s*\[x\]", text, re.MULTILINE | re.IGNORECASE))
            total = len(re.findall(r"^\s*[-|]\s*\[[x ]\]", text, re.MULTILINE | re.IGNORECASE))
            pct   = round(done / total * 100) if total else 0
            epic_strs.append(f"{name} ({pct}%)")
        if epic_strs:
            lines.append(f"Epics: {', '.join(epic_strs)}")
    except Exception as e:
        log.debug("Epics context failed: %s", e)

    # ── Journal today ─────────────────────────────────────────────────────────
    try:
        from src.journal import store as jstore
        sleep = jstore.get_sleep(today)
        sleep_str = f"{round(sleep['duration_min']/60, 1)}h" if sleep else "not logged"

        food_rows = jstore.food_today(today)
        if food_rows:
            meal_names = [r["name"] for r in food_rows if r.get("name")]
            food_str = ", ".join(meal_names) if meal_names else f"{len(food_rows)} meal(s)"
        else:
            food_str = "not logged"

        work_min = jstore.work_daily_total_min(today)
        work_str = f"{round(work_min/60, 1)}h" if work_min else "0h"

        lines.append(f"Today's journal — Sleep: {sleep_str}, Food: {food_str}, Work: {work_str}")
    except Exception as e:
        log.debug("Journal context failed: %s", e)

    # ── Top open tasks ────────────────────────────────────────────────────────
    try:
        from src.projects import store as pstore
        all_tasks = pstore.list_tasks(status="open")
        top = [t["title"] for t in all_tasks[:3]]
        if top:
            lines.append(f"Top open tasks: {', '.join(top)}")
    except Exception as e:
        log.debug("Tasks context failed: %s", e)

    return "\n".join(lines)


def build_system_prompt() -> str:
    """
    Full system prompt for Telegram chat: personality + live board context.
    This replaces the basic prompt in ollama_client._build_system_prompt().
    """
    ctx = build_context()
    return (
        "You are PPT, Rana's personal AI companion running on his Mac Mini. "
        "You know his board, habits, personal goals, projects and daily journal. "
        "Be conversational, smart, and concise — 2-3 sentences unless more detail is asked. "
        "When Rana asks you to do something (set a reminder, mark a habit done, etc.), "
        "tell him to use the slash command — e.g. '/remind add 15:00 Take medicine'. "
        "Never use markdown formatting in replies — plain text only.\n\n"
        "--- Rana's current board ---\n"
        f"{ctx}\n"
        "---------------------------"
    )
