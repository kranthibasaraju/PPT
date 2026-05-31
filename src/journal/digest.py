"""
src/journal/digest.py — daily morning digest builder.

WHY a digest?
  Individual notifications tell you one thing at a time.
  The morning digest is the overview: one message that answers
  "how did yesterday go and what does today look like?"

  It combines data from ALL modules + the notify system (habits + goals)
  into a single, rich Telegram message you receive at 07:30.

FORMAT (Telegram Markdown):
  🌅 Good morning, Rana!

  *Yesterday*
  💤 Sleep: 7.5h · Quality 4/5
  🍽 Food: 1,840 cal · P: 78g · C: 220g · F: 65g
  💼 Work: 6.5h (3 sessions)
  💰 Spent: $34.50  (food $12 · transport $8 · other $14.50)
  ⚖️ Balance score: 82/100 — Good

  *Today*
  🔔 3 habits scheduled
  🎯 2 active personal goals

USAGE:
    from src.journal.digest import build, send_digest
    text = build()           # returns the message string
    send_digest()            # builds + sends via Telegram
"""
from __future__ import annotations
import logging
from datetime import date, timedelta
from src.journal import store as jstore
from src.journal.alerts import work_life_score

log = logging.getLogger(__name__)


def build(for_date: str | None = None) -> str:
    """
    Build the full morning digest for a given date (defaults to yesterday's data).
    Returns a Markdown-formatted string ready for Telegram.
    """
    yesterday = for_date or (date.today() - timedelta(days=1)).isoformat()
    today_str = date.today().isoformat()

    lines = []

    # ── Greeting ──────────────────────────────────────────────────────────────
    from src.notify.relationship import morning_greeting, get_level
    from src.notify.store import get_profile, list_habits, list_goals
    profile = get_profile()
    name    = profile.get("name", "Rana")
    xp      = profile.get("relationship_xp", 0)
    level   = get_level(xp)

    active_habits = list_habits(active_only=True)
    active_goals  = list_goals(status="active")

    lines.append(f"🌅 *Good morning, {name}!*")
    lines.append("")

    # ── Yesterday summary ─────────────────────────────────────────────────────
    lines.append("*Yesterday*")

    # Sleep
    sleep = jstore.get_sleep(yesterday)
    if sleep and sleep.get("duration_min"):
        h = sleep["duration_min"] // 60
        m = sleep["duration_min"] % 60
        dur_str = f"{h}h {m}m" if m else f"{h}h"
        q = sleep.get("quality")
        quality_str = f"· Quality {q}/5" if q else ""
        lines.append(f"💤 *Sleep:* {dur_str} {quality_str}".strip())
    else:
        lines.append("💤 *Sleep:* not logged")

    # Food
    food = jstore.food_daily_totals(yesterday)
    if food["meals"] > 0:
        cal    = int(food["calories"])
        p      = int(food["protein_g"])
        c      = int(food["carbs_g"])
        f_     = int(food["fat_g"])
        macros = f"P: {p}g · C: {c}g · F: {f_}g" if (p or c or f_) else ""
        lines.append(f"🍽 *Food:* {cal} cal · {food['meals']} entries  {macros}".strip())
    else:
        lines.append("🍽 *Food:* not logged")

    # Work
    work_min = jstore.work_daily_total_min(yesterday)
    sessions = jstore.work_today(yesterday)
    if work_min > 0:
        wh = work_min // 60
        wm = work_min % 60
        w_str = f"{wh}h {wm}m" if wm else f"{wh}h"
        lines.append(f"💼 *Work:* {w_str} ({len(sessions)} session{'s' if len(sessions)!=1 else ''})")
    else:
        lines.append("💼 *Work:* not tracked")

    # Money
    spent_yday = jstore.spend_total(yesterday)
    if spent_yday > 0:
        spend_list = jstore.spend_by_category(yesterday, yesterday)
        top = ", ".join(f"{r['category']} ${r['total']:.0f}" for r in spend_list[:3])
        lines.append(f"💰 *Spent:* ${spent_yday:.2f}  ({top})")
    else:
        lines.append("💰 *Spent:* $0")

    # Balance score
    score = work_life_score(7)
    lines.append(f"⚖️ *Balance:* {score['score']}/100 — {score['label']}")
    lines.append("")

    # ── Today outlook ─────────────────────────────────────────────────────────
    lines.append("*Today*")

    # Habits
    if active_habits:
        # Show next 3 habits with their reminder times
        habit_strs = []
        for h in sorted(active_habits, key=lambda x: x["remind_at"])[:3]:
            habit_strs.append(f"{h['name']} ({h['remind_at']})")
        extra = f" +{len(active_habits)-3} more" if len(active_habits) > 3 else ""
        lines.append(f"🔔 *Habits:* {', '.join(habit_strs)}{extra}")
    else:
        lines.append("🔔 *Habits:* none set up — add some at /notify")

    # Personal goals
    if active_goals:
        in_progress = [g for g in active_goals if g["progress"] > 0]
        top_goal = in_progress[0] if in_progress else active_goals[0]
        lines.append(f"🎯 *Personal goals:* {len(active_goals)} active · '{top_goal['title']}' at {top_goal['progress']}%")
    else:
        lines.append("🎯 *Personal goals:* none active")

    # Budget
    budget_st = jstore.budget_status()
    if budget_st["budget"]:
        pct = budget_st["pct"]
        lines.append(f"💳 *Budget:* ${budget_st['spent']:.2f} / ${budget_st['budget']:.2f} this week ({pct}%)")

    # Relationship level note (only show if level is high enough to feel personal)
    if level in ("Friend", "Companion", "Partner"):
        lines.append("")
        if level == "Partner":
            lines.append(f"💙 {name}, I'm here whenever you need me.")
        elif level == "Companion":
            lines.append(f"🌱 Have a good one, {name}.")
        else:
            lines.append(f"☀️ Make it a good day, {name}!")

    return "\n".join(lines)


def send_digest(for_date: str | None = None) -> bool:
    """Build the digest and send it via Telegram."""
    try:
        from src.notify.messenger import send_telegram
        msg = build(for_date)
        ok = send_telegram(msg)
        log.info("Morning digest sent: %s", "✓" if ok else "✗")
        return ok
    except Exception as e:
        log.error("send_digest failed: %s", e)
        return False
