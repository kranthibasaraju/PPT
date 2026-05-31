"""
src/integrations/telegram_commands.py — Telegram bot command handler for PPT.

WHY Telegram for quick capture?
  Your phone is always with you.  Web UI is good for review.
  But the fastest way to log "just bought coffee" or "going to sleep" is a
  single message to your PPT bot.  No app switch, no loading — just type.

COMMANDS:
  /food [meal_type] [name] [calories?] [p:Xg] [c:Xg] [f:Xg]
    Examples:
      /food lunch oatmeal 350
      /food dinner grilled salmon 480 p:42 c:5 f:22
      /food snack almonds 160

  /sleep [hours] [quality?]
    Examples:
      /sleep 7.5
      /sleep 8 4
      /sleep 23:30 07:00 4   ← bedtime, waketime, quality

  /work start [task?] [project?]
  /work end
  /work status
    Examples:
      /work start PPT journal module
      /work end
      /work status

  /spend [amount] [category?] [description]
    Examples:
      /spend 12.50 food coffee at Blue Tokai
      /spend 45 shopping amazon order
      /spend 3.50 transport rickshaw

  /digest               ← send today's morning digest now
  /balance              ← work-life balance score
  /help                 ← show all commands

HOW IT WORKS:
  The listener runs in a background thread inside the notify daemon.
  It polls Telegram's getUpdates endpoint every 3 seconds, looks for
  messages that start with '/', parses them, and stores to journal.store.
  It also sends a confirmation reply so you know the log was saved.
"""
from __future__ import annotations
import logging
import re
import time
from typing import Callable

log = logging.getLogger(__name__)

# Tracks the last processed update_id to avoid re-processing
_last_update_id: int = 0

# Per-chat conversation history — keyed by chat_id string.
# WHY in-memory: simple, no DB needed for v1.
# Resets on daemon restart; last_active used to clear stale sessions after 2h.
_chat_histories: dict[str, list[dict]] = {}
_chat_last_active: dict[str, float] = {}
_HISTORY_TTL_SECS = 7200  # 2 hours


# ── Parser helpers ────────────────────────────────────────────────────────────

def _parse_food(args: list[str]) -> dict:
    """
    Parse /food arguments.
    Format: [meal_type?] name [calories?] [p:Xg?] [c:Xg?] [f:Xg?]

    WHY flexible parsing?
      People type differently.  We try to be tolerant — grab what we can.
    """
    meal_types = {"breakfast", "lunch", "dinner", "snack", "drink"}
    result = {"meal_type": "meal", "name": "", "calories": None,
              "protein_g": None, "carbs_g": None, "fat_g": None}

    remaining = []
    for a in args:
        a_lower = a.lower().rstrip("g")
        if a_lower in meal_types:
            result["meal_type"] = a_lower
        elif a.lower().startswith("p:"):
            try: result["protein_g"] = float(a[2:].rstrip("g"))
            except ValueError: pass
        elif a.lower().startswith("c:"):
            try: result["carbs_g"] = float(a[2:].rstrip("g"))
            except ValueError: pass
        elif a.lower().startswith("f:"):
            try: result["fat_g"] = float(a[2:].rstrip("g"))
            except ValueError: pass
        elif re.match(r"^\d+$", a):
            # First standalone integer = calories; subsequent ones go into name
            if result["calories"] is None:
                try: result["calories"] = int(a)
                except ValueError: remaining.append(a)
            else:
                remaining.append(a)
        else:
            remaining.append(a)

    result["name"] = " ".join(remaining).strip() or "food"
    return result


def _parse_sleep(args: list[str]) -> dict:
    """
    Parse /sleep arguments.
    Formats:
      /sleep 7.5            → 7.5 hours, no quality
      /sleep 7.5 4          → 7.5 hours, quality 4
      /sleep 23:30 07:00 4  → bedtime 23:30, wake 07:00, quality 4
    """
    result = {"duration_min": 0, "bedtime": None, "waketime": None, "quality": None}
    time_re = re.compile(r"^\d{1,2}:\d{2}$")

    bedtime = waketime = None
    remaining = []
    for a in args:
        if time_re.match(a):
            if bedtime is None:
                bedtime = a
            else:
                waketime = a
        elif re.match(r"^[1-5]$", a):
            result["quality"] = int(a)
        else:
            remaining.append(a)

    if bedtime and waketime:
        result["bedtime"]  = bedtime
        result["waketime"] = waketime
        from datetime import datetime
        b = datetime.strptime(bedtime, "%H:%M")
        w = datetime.strptime(waketime, "%H:%M")
        diff = int((w - b).seconds / 60)
        if diff < 0:
            diff += 24 * 60
        result["duration_min"] = diff
    elif remaining:
        try:
            result["duration_min"] = int(float(remaining[0]) * 60)
        except (ValueError, IndexError):
            pass

    return result


def _parse_spend(args: list[str]) -> dict:
    """
    Parse /spend arguments.
    Format: amount [category?] description...
    """
    categories = {"food", "transport", "shopping", "health",
                  "entertainment", "bills", "education", "other"}
    result = {"amount": 0.0, "category": "other", "description": "purchase"}

    if not args:
        return result

    # First arg = amount
    try:
        result["amount"] = float(args[0].lstrip("$"))
        rest = args[1:]
    except ValueError:
        rest = args

    # Second arg might be a category
    if rest and rest[0].lower() in categories:
        result["category"] = rest[0].lower()
        rest = rest[1:]

    if rest:
        result["description"] = " ".join(rest)

    return result


# ── Command handlers ──────────────────────────────────────────────────────────

def handle_food(args: list[str]) -> str:
    from src.journal.store import log_food
    p = _parse_food(args)
    log_food(
        name=p["name"], meal_type=p["meal_type"],
        calories=p["calories"], protein_g=p["protein_g"],
        carbs_g=p["carbs_g"], fat_g=p["fat_g"],
        source="telegram"
    )
    parts = [f"✅ Logged: *{p['name']}*"]
    if p["meal_type"] != "meal":
        parts[0] += f" ({p['meal_type']})"
    if p["calories"]:
        parts.append(f"{p['calories']} cal")
    if p["protein_g"]:
        parts.append(f"P:{p['protein_g']}g")
    if p["carbs_g"]:
        parts.append(f"C:{p['carbs_g']}g")
    if p["fat_g"]:
        parts.append(f"F:{p['fat_g']}g")
    return "  ·  ".join(parts[:1]) + ("\n" + "  ·  ".join(parts[1:]) if len(parts) > 1 else "")


def handle_sleep(args: list[str]) -> str:
    from src.journal.store import log_sleep
    p = _parse_sleep(args)
    if p["duration_min"] == 0:
        return "❓ I didn't catch that. Try: `/sleep 7.5 4` or `/sleep 23:30 07:00 4`"
    log_sleep(
        duration_min=p["duration_min"],
        quality=p["quality"],
        bedtime=p["bedtime"],
        waketime=p["waketime"],
        source="telegram"
    )
    h  = p["duration_min"] // 60
    m  = p["duration_min"] % 60
    dur = f"{h}h {m}m" if m else f"{h}h"
    q = f" · Quality {p['quality']}/5" if p["quality"] else ""
    return f"✅ Sleep logged: *{dur}*{q}"


def handle_work(args: list[str]) -> str:
    from src.journal import store as jstore
    sub = args[0].lower() if args else "status"

    if sub == "start":
        task    = " ".join(args[1:]) if len(args) > 1 else ""
        session = jstore.clock_in(task=task, source="telegram")
        task_str = f" — {session['task']}" if session.get("task") else ""
        return f"▶️ Clocked in at *{session['start_time']}*{task_str}\nType `/work end` when done."

    elif sub == "end":
        session = jstore.clock_out()
        if not session:
            return "❓ No active work session found. Use `/work start` to begin one."
        h = (session["duration_min"] or 0) // 60
        m = (session["duration_min"] or 0) % 60
        dur = f"{h}h {m}m" if m else f"{h}h"
        task_str = f" on *{session['task']}*" if session.get("task") else ""
        return f"⏹ Session ended. Worked *{dur}*{task_str}."

    else:  # status
        session = jstore.active_session()
        if session:
            from datetime import datetime
            start = datetime.strptime(session["date"] + " " + session["start_time"],
                                      "%Y-%m-%d %H:%M")
            elapsed = int((datetime.now() - start).total_seconds() / 60)
            h, m = elapsed // 60, elapsed % 60
            task_str = f"*{session['task']}*" if session.get("task") else "unnamed task"
            return f"▶️ Currently working on {task_str} — {h}h {m}m elapsed."
        total_min = jstore.work_daily_total_min()
        h, m = total_min // 60, total_min % 60
        return f"💼 No active session. Today's total: *{h}h {m}m*."


def handle_spend(args: list[str]) -> str:
    from src.journal.store import log_spend
    p = _parse_spend(args)
    if p["amount"] <= 0:
        return "❓ Usage: `/spend 12.50 food coffee`"
    log_spend(
        amount=p["amount"],
        description=p["description"],
        category=p["category"],
        source="telegram"
    )
    return f"✅ Logged: *${p['amount']:.2f}* for {p['description']} ({p['category']})"


def handle_digest(_: list[str]) -> str:
    from src.journal.digest import build
    return build()


def handle_projects(_: list[str]) -> str:
    """Return a status summary of all active projects."""
    from src.integrations.telegram_digest import handle_projects_command
    return handle_projects_command()


def handle_next(_: list[str]) -> str:
    """Return the single highest-priority open task across all projects."""
    from src.integrations.telegram_digest import handle_next_command
    return handle_next_command()


def handle_remind(args: list[str], *, user_id: int | None = None) -> str:
    """
    /remind add [repeat] HH:MM title   — create a reminder
    /remind list                        — show active reminders
    /remind delete <id>                 — remove a reminder
    /remind done <id>                   — mark one-time reminder done

    WHY this command?
      The daemon fires reminders automatically, but you need a way to create
      and manage them without touching the database directly.

    Repeat values: once (default), daily, weekdays, weekly
    Examples:
      /remind add 14:30 Take medicine
      /remind add daily 09:00 Morning walk
      /remind add weekly 10:00 Review goals
      /remind list
      /remind delete 3
    """
    from src.notify import store as nstore
    from datetime import date

    sub = args[0].lower() if args else "list"

    # ── list ──────────────────────────────────────────────────────────────
    if sub == "list":
        reminders = nstore.list_reminders(active_only=True, user_id=user_id)
        if not reminders:
            return "📭 No active reminders.\nAdd one: `/remind add 14:30 Take medicine`"
        lines = ["⏰ *Active Reminders*\n"]
        for r in reminders:
            repeat = f" ({r['repeat']})" if r["repeat"] != "once" else ""
            fire = f" · {r['fire_date']}" if r.get("fire_date") else ""
            lines.append(f"`[{r['id']}]` *{r['title']}* — {r['remind_at']}{repeat}{fire}")
            if r.get("message"):
                lines.append(f"      _{r['message']}_")
        return "\n".join(lines)

    # ── delete ────────────────────────────────────────────────────────────
    if sub in ("delete", "del", "remove") and len(args) > 1:
        try:
            rid = int(args[1])
            r = nstore.get_reminder(rid, user_id=user_id)
            if not r:
                return f"❓ No reminder with id {rid}."
            nstore.deactivate_reminder(rid, user_id=user_id)
            return f"🗑 Deleted: *{r['title']}*"
        except ValueError:
            return "❓ Usage: `/remind delete <id>`  (use `/remind list` to find ids)"

    # ── done (alias for one-time reminders) ───────────────────────────────
    if sub == "done" and len(args) > 1:
        try:
            rid = int(args[1])
            r = nstore.get_reminder(rid, user_id=user_id)
            if not r:
                return f"❓ No reminder with id {rid}."
            nstore.deactivate_reminder(rid, user_id=user_id)
            return f"✅ Marked done: *{r['title']}*"
        except ValueError:
            return "❓ Usage: `/remind done <id>`"

    # ── add ───────────────────────────────────────────────────────────────
    if sub == "add" and len(args) > 1:
        rest = args[1:]
        repeat_words = {"daily", "weekdays", "weekends", "weekly", "once"}
        time_re = re.compile(r"^\d{1,2}:\d{2}$")

        # Optional repeat keyword first
        repeat = "once"
        if rest[0].lower() in repeat_words:
            repeat = rest[0].lower()
            rest = rest[1:]

        if not rest:
            return "❓ Usage: `/remind add [daily] HH:MM Title`"

        # Next token should be time
        if not time_re.match(rest[0]):
            return f"❓ Expected a time like `14:30`, got `{rest[0]}`.\nUsage: `/remind add [daily] 14:30 Title`"

        remind_at = rest[0]
        # Ensure HH:MM format (pad single-digit hour)
        h, m = remind_at.split(":")
        remind_at = f"{int(h):02d}:{int(m):02d}"
        title = " ".join(rest[1:]).strip() if len(rest) > 1 else "Reminder"

        fire_date = date.today().isoformat() if repeat == "once" else None
        r = nstore.add_reminder(
            title=title, remind_at=remind_at,
            repeat=repeat, fire_date=fire_date, user_id=user_id
        )
        repeat_str = f" · repeats {repeat}" if repeat != "once" else f" · today"
        return (
            f"✅ Reminder set!\n"
            f"*{r['title']}* at {r['remind_at']}{repeat_str}\n"
            f"_id: {r['id']} — use `/remind delete {r['id']}` to remove_"
        )

    return (
        "⏰ *Remind commands*\n"
        "`/remind list` — show active reminders\n"
        "`/remind add 14:30 Title` — one-time today\n"
        "`/remind add daily 09:00 Title` — recurring\n"
        "`/remind delete <id>` — remove\n"
        "`/remind done <id>` — mark complete"
    )


def handle_habit(args: list[str], *, user_id: int | None = None) -> str:
    """
    /habit add <name> [HH:MM] [frequency]  — create a habit
    /habit list                             — show active habits
    /habit done <id>                        — log habit done today
    /habit delete <id>                      — remove a habit

    WHY habits vs reminders?
      Habits are recurring by nature and track streaks — PPT notices if you
      break a 7-day streak and says something about it.  Reminders are just
      one-off or simple recurring nudges with no streak tracking.

    Examples:
      /habit add Morning walk 07:00 daily
      /habit add Drink 2L water 12:00 weekdays
      /habit list
      /habit done 2
    """
    from src.notify import store as nstore

    sub = args[0].lower() if args else "list"

    # ── list ──────────────────────────────────────────────────────────────
    if sub == "list":
        habits = nstore.list_habits(active_only=True, user_id=user_id)
        if not habits:
            return "📭 No active habits.\nAdd one: `/habit add Morning walk 07:00`"
        lines = ["🔄 *Active Habits*\n"]
        for h in habits:
            streak = nstore.habit_streak(h["id"], user_id=user_id)
            done = "✅" if nstore.habit_done_today(h["id"], user_id=user_id) else "⬜"
            streak_str = f" · 🔥 {streak}d streak" if streak > 0 else ""
            lines.append(f"{done} `[{h['id']}]` *{h['name']}* — {h['remind_at']} ({h['frequency']}){streak_str}")
        return "\n".join(lines)

    # ── done ──────────────────────────────────────────────────────────────
    if sub == "done" and len(args) > 1:
        try:
            hid = int(args[1])
            h = nstore.get_habit(hid, user_id=user_id)
            if not h:
                return f"❓ No habit with id {hid}."
            nstore.log_habit_done(hid, user_id=user_id)
            streak = nstore.habit_streak(hid, user_id=user_id)
            streak_str = f" · 🔥 {streak}d streak!" if streak > 1 else ""
            return f"✅ *{h['name']}* logged for today.{streak_str}"
        except ValueError:
            return "❓ Usage: `/habit done <id>`"

    # ── delete ────────────────────────────────────────────────────────────
    if sub in ("delete", "del") and len(args) > 1:
        try:
            hid = int(args[1])
            h = nstore.get_habit(hid, user_id=user_id)
            if not h:
                return f"❓ No habit with id {hid}."
            nstore.delete_habit(hid, user_id=user_id)
            return f"🗑 Removed habit: *{h['name']}*"
        except ValueError:
            return "❓ Usage: `/habit delete <id>`"

    # ── add ───────────────────────────────────────────────────────────────
    if sub == "add" and len(args) > 1:
        rest = args[1:]
        freq_words = {"daily", "weekdays", "weekends", "weekly"}
        time_re = re.compile(r"^\d{1,2}:\d{2}$")

        # Extract optional time and frequency from the end
        frequency = "daily"
        remind_at = "08:00"

        if rest and rest[-1].lower() in freq_words:
            frequency = rest[-1].lower()
            rest = rest[:-1]

        if rest and time_re.match(rest[-1]):
            h_str, m_str = rest[-1].split(":")
            remind_at = f"{int(h_str):02d}:{int(m_str):02d}"
            rest = rest[:-1]

        name = " ".join(rest).strip()
        if not name:
            return "❓ Usage: `/habit add Morning walk 07:00 daily`"

        h = nstore.add_habit(name=name, frequency=frequency, remind_at=remind_at, user_id=user_id)
        return (
            f"✅ Habit created!\n"
            f"*{h['name']}* · {h['remind_at']} · {h['frequency']}\n"
            f"_id: {h['id']} — use `/habit done {h['id']}` to log it_"
        )

    return (
        "🔄 *Habit commands*\n"
        "`/habit list` — show active habits + streaks\n"
        "`/habit add Morning walk 07:00` — create daily habit\n"
        "`/habit add Gym 18:00 weekdays` — weekday habit\n"
        "`/habit done <id>` — log done today\n"
        "`/habit delete <id>` — remove habit"
    )


def handle_balance(_: list[str]) -> str:
    from src.journal.alerts import work_life_score
    s = work_life_score(7)
    daily = s["daily"]
    bar = ""
    for score in daily:
        if score >= 80: bar += "█"
        elif score >= 60: bar += "▓"
        elif score >= 40: bar += "▒"
        else: bar += "░"
    return (
        f"⚖️ *Work-Life Balance*\n"
        f"7-day score: *{s['score']}/100* — {s['label']}\n"
        f"Trend: `{bar}`\n"
        f"_Sleep 40% · Work 40% · Food 20%_"
    )


def handle_help(_: list[str]) -> str:
    return (
        "🤖 *PPT Bot Commands*\n\n"
        "⏰ *Reminders*\n"
        "`/remind list` · `/remind add 14:30 Title` · `/remind add daily 09:00 Title`\n"
        "`/remind delete <id>` · `/remind done <id>`\n\n"
        "🔄 *Habits*\n"
        "`/habit list` · `/habit add Morning walk 07:00`\n"
        "`/habit done <id>` · `/habit delete <id>`\n\n"
        "📓 *Journal*\n"
        "`/food lunch oatmeal 350 p:10 c:60`\n"
        "`/sleep 7.5 4` or `/sleep 23:30 07:00 4`\n"
        "`/work start task name` · `/work end` · `/work status`\n"
        "`/spend 12.50 food coffee`\n\n"
        "📋 `/digest` · ⚖️ `/balance` · 📁 `/projects` · ▶️ `/next`\n"
        "🔄 `/sync` — sync epics → board tasks\n"
        "❓ `/help`"
    )


# ── Command router ────────────────────────────────────────────────────────────

def handle_start(args: list[str], *, chat_id: str, chat_meta: dict | None = None) -> str:
    payload = args[0] if args else ""
    if payload.startswith("link_"):
        if chat_meta and chat_meta.get("type") != "private":
            return "❌ Telegram onboarding only works in a private chat with the PPT bot."
        token = payload.removeprefix("link_").strip()
        if not token:
            return "❓ Missing link token."
        from src.notify import store as nstore
        try:
            linked = nstore.link_telegram_account(
                token,
                chat_id=chat_id,
                telegram_user_id=str(chat_meta.get("user_id")) if chat_meta and chat_meta.get("user_id") else None,
                telegram_username=chat_meta.get("username") if chat_meta else None,
            )
            return (
                "✅ Telegram linked for smart reminders.\n"
                f"Chat: `{linked.get('telegram_chat_id')}`\n"
                "You can go back to the onboarding page and finish your profile."
            )
        except Exception as exc:
            return f"❌ Could not link this Telegram account: {exc}"

    return (
        "✅ PPT is online.\n"
        "If you're onboarding for smart reminders, use the exact `/start link_<token>` "
        "command shown on your onboarding page."
    )


def _legacy_only_command(cmd: str) -> bool:
    return cmd in {"food", "sleep", "work", "spend", "digest", "balance", "sync"}


def _resolve_user(chat_id: str | None) -> int | None:
    if not chat_id:
        return None
    from src.notify import store as nstore
    return nstore.resolve_user_id_for_chat(chat_id)

def handle_sync(_: list[str]) -> str:
    """Run sync_epics_to_board.py and report what changed."""
    import subprocess, sys
    from pathlib import Path
    script = Path(__file__).parent.parent.parent / "scripts" / "sync_epics_to_board.py"
    result = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True, text=True, timeout=30
    )
    output = result.stdout.strip()
    # Extract the summary line
    for line in output.splitlines():
        if "Sync complete" in line or "Normalised" in line:
            return f"🔄 Board synced\n{line.strip()}"
    return f"🔄 Sync ran\n{output[-200:] if output else result.stderr[-200:]}"


_HANDLERS: dict[str, Callable] = {
    "start":    handle_start,
    "food":     handle_food,
    "sleep":    handle_sleep,
    "work":     handle_work,
    "spend":    handle_spend,
    "remind":   handle_remind,
    "reminder": handle_remind,
    "habit":    handle_habit,
    "digest":   handle_digest,
    "balance":  handle_balance,
    "projects": handle_projects,
    "next":     handle_next,
    "sync":     handle_sync,
    "help":     handle_help,
}


def process_message(text: str, *, chat_id: str | None = None, chat_meta: dict | None = None) -> str | None:
    """
    Parse a Telegram message and route to the right handler.
    Returns a reply string, or None if the message is not a command.
    """
    text = text.strip()
    if not text.startswith("/"):
        return None

    # Strip leading / and optional @botname suffix
    parts = text.lstrip("/").split("@")[0].split()
    if not parts:
        return None

    cmd  = parts[0].lower()
    args = parts[1:]
    user_id = _resolve_user(chat_id)

    handler = _HANDLERS.get(cmd)
    if handler:
        try:
            if cmd == "start":
                return handler(args, chat_id=chat_id or "", chat_meta=chat_meta)

            if _legacy_only_command(cmd) and user_id not in {None, 1}:
                return "🔒 This command still belongs to the legacy personal journal account. Your smart-reminder account is limited to reminders, habits, and onboarding for now."

            if cmd in {"remind", "reminder"}:
                if user_id is None:
                    return "🔒 Link your Telegram account from the onboarding page before using reminder commands."
                return handler(args, user_id=user_id)

            if cmd == "habit":
                if user_id is None:
                    return "🔒 Link your Telegram account from the onboarding page before using habit commands."
                return handler(args, user_id=user_id)

            return handler(args)
        except Exception as e:
            log.error("Command /%s failed: %s", cmd, e)
            return f"❌ Error processing /{cmd}: {e}"
    return None


# ── Chat handler (plain-text → Ollama) ───────────────────────────────────────

def handle_chat(text: str, chat_id: str) -> str | None:
    """
    Route a plain-text (non-command) message to Ollama with live board context.

    WHY per-chat history:
      Each chat_id gets its own conversation list so Rana can have a multi-turn
      conversation ("what's my top task?" → "mark it done" → "what's next?").
      History is cleared after 2h inactivity to keep context fresh.

    Returns the LLM reply string, or None if Ollama is unreachable.
    """
    import time
    from src.llm.ollama_client import complete, check_connection
    from src.notify import store as nstore

    # Prune stale sessions
    now = time.time()
    stale = [cid for cid, t in _chat_last_active.items() if now - t > _HISTORY_TTL_SECS]
    for cid in stale:
        _chat_histories.pop(cid, None)
        _chat_last_active.pop(cid, None)

    # Check Ollama is up before committing to a reply
    if not check_connection():
        return (
            "My brain (Ollama) is offline right now.\n"
            "Start it with: ollama serve\n"
            "You can still use /remind, /habit, /food and other commands."
        )

    history = _chat_histories.setdefault(chat_id, [])
    _chat_last_active[chat_id] = now

    try:
        user_id = nstore.resolve_user_id_for_chat(chat_id)
        if user_id and user_id != nstore.default_user_id():
            from src.context.builder import build_system_prompt
            system = build_system_prompt(user_id=user_id)
        else:
            from src.llm.context_builder import build_system_prompt
            system = build_system_prompt()
        reply  = complete(text, conversation_history=history, system_prompt=system)
        return reply
    except Exception as e:
        log.error("Ollama chat failed: %s", e)
        return f"Something went wrong talking to Ollama: {e}"


# ── Polling loop ──────────────────────────────────────────────────────────────

def run_listener(poll_interval: float = 3.0, stop_event=None) -> None:
    """
    Poll Telegram for new messages and process commands.
    Runs in a background thread — call from notify_daemon.py.

    WHY poll instead of webhooks?
      Polling works without a public URL or SSL cert.
      For a personal bot on a home server, this is simpler and reliable enough.
    """
    global _last_update_id
    from src.integrations.telegram_bot import get_updates, send_message
    log.info("Telegram command listener started (polling every %.0fs)", poll_interval)

    while True:
        if stop_event and stop_event.is_set():
            break
        try:
            updates = get_updates(offset=_last_update_id + 1 if _last_update_id else None)
            for update in updates:
                _last_update_id = update["update_id"]
                msg = update.get("message") or update.get("channel_post")
                if not msg:
                    continue
                text = msg.get("text", "").strip()
                if not text:
                    continue
                chat_id = str(msg["chat"]["id"])
                chat_meta = {
                    "type": msg.get("chat", {}).get("type"),
                    "username": (msg.get("from") or {}).get("username"),
                    "user_id": (msg.get("from") or {}).get("id"),
                }

                if text.startswith("/"):
                    # Fast path — slash command
                    reply = process_message(text, chat_id=chat_id, chat_meta=chat_meta)
                    if reply:
                        send_message(reply, chat_id=chat_id)
                        log.info("Command '%s' handled", text.split()[0])
                else:
                    # Chat path — send typing indicator, route to Ollama
                    try:
                        from src.integrations.telegram_bot import send_typing
                        send_typing(chat_id)
                    except Exception:
                        pass
                    reply = handle_chat(text, chat_id)
                    if reply:
                        send_message(reply, chat_id=chat_id)
                        log.info("Chat reply sent to %s", chat_id)
        except Exception as e:
            log.error("Telegram listener error: %s", e)
        time.sleep(poll_interval)
