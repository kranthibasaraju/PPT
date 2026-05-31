"""
src/context/builder.py — assembles the personal context block for LLM injection.

HOW context injection works:
  Every query to Ollama gets a system prompt that looks like:

  === PERSONAL CONTEXT ===
  [Identity]
  Name: Rana  |  Relationship level: Friend  |  XP: 312

  [Right Now — 2026-05-17]
  Sleep last night: 5.2h (normal: 7.4h) ⚠️ BELOW BASELINE
  Food today: 830 cal logged (2 meals)
  Work today: 2.5h (1 session — active)
  Spent today: $18.50

  [Your Patterns — 30-day baselines]
  Sleep: avg 7.4h/night  |  Work: avg 7.1h/day  |  Spend: avg $34/day

  [Active Goals]
  • Learn Python — 45% complete

  [Habits — today]
  ✓ Drink water (14-day streak)  |  ○ Exercise (due 7am)
  === END CONTEXT ===

WHY this format?
  - Structured headings help the LLM parse sections
  - Baseline comparisons let the LLM know what's unusual
  - Emoji markers help the LLM prioritise what to focus on
  - Concise but complete — fits in ~500 tokens

OUTPUT MODES:
  build_context()        → full context string
  build_system_prompt()  → full system prompt (context + role instructions)
  build_dict()           → structured dict (for training data generation)
"""
from __future__ import annotations
import logging
from datetime import date, timedelta
from typing import Any

log = logging.getLogger(__name__)


def build_dict(user_id: int | None = None) -> dict[str, Any]:
    """
    Assemble all personal context data as a structured dictionary.
    Used by: training exporter, analytics dashboard, context string builder.
    """
    ctx: dict[str, Any] = {"date": date.today().isoformat()}
    yesterday = (date.today() - timedelta(days=1)).isoformat()

    # ── Identity ──────────────────────────────────────────────────────────────
    try:
        from src.notify.store import default_user_id, get_profile, list_habits, list_goals
        from src.notify.relationship import get_level, get_level_progress
        effective_user_id = user_id or default_user_id()
        profile = get_profile(user_id=effective_user_id)
        xp      = profile.get("relationship_xp", 0)
        ctx["identity"] = {
            "name":  profile.get("name", "Rana"),
            "xp":    xp,
            "level": get_level(xp),
            "level_progress": get_level_progress(xp),
        }
        active_habits = list_habits(active_only=True, user_id=effective_user_id)
        active_goals  = list_goals(status="active", user_id=effective_user_id)
        include_shared_journal = effective_user_id == default_user_id()
    except Exception as e:
        log.debug("Identity context error: %s", e)
        active_habits, active_goals = [], []
        ctx["identity"] = {"name": "Rana", "xp": 0, "level": "Stranger"}
        include_shared_journal = False

    # ── Today snapshot ────────────────────────────────────────────────────────
    today_str = date.today().isoformat()
    if include_shared_journal:
        try:
            from src.journal.store import (
                get_sleep, food_daily_totals, work_daily_total_min,
                active_session, spend_total
            )
            sleep       = get_sleep(yesterday)
            food_totals = food_daily_totals(today_str)
            work_min    = work_daily_total_min(today_str)
            live_sess   = active_session()
            spent_today = spend_total(today_str)

            ctx["today"] = {
                "sleep_last_night": {
                    "hours": round(sleep["duration_min"] / 60, 1) if sleep and sleep.get("duration_min") else None,
                    "quality": sleep.get("quality") if sleep else None,
                    "bedtime": sleep.get("bedtime") if sleep else None,
                    "waketime": sleep.get("waketime") if sleep else None,
                } if sleep else None,
                "food": {
                    "calories": int(food_totals["calories"]),
                    "meals": food_totals["meals"],
                    "protein_g": round(food_totals["protein_g"], 1),
                    "carbs_g": round(food_totals["carbs_g"], 1),
                    "fat_g": round(food_totals["fat_g"], 1),
                },
                "work": {
                    "hours": round(work_min / 60, 1),
                    "active_session": bool(live_sess),
                    "task": live_sess.get("task") if live_sess else None,
                },
                "spending": spent_today,
            }
        except Exception as e:
            log.debug("Today context error: %s", e)
            ctx["today"] = {}
    else:
        ctx["today"] = {}

    # ── Personal benchmarks ───────────────────────────────────────────────────
    if include_shared_journal:
        try:
            from src.analytics.benchmarks import full_benchmark
            bench = full_benchmark(30)
            ctx["benchmarks"] = {
                "sleep_avg_hours": bench["sleep"].get("avg_hours"),
                "work_avg_hours":  bench["work"].get("avg_hours"),
                "food_avg_cal":    bench["food"].get("avg_calories"),
                "spend_avg_daily": bench["money"].get("avg_daily_spend"),
                "habit_completion":bench["habits"].get("avg_completion_rate"),
            }
            ctx["_benchmarks_full"] = bench  # for training exporter
        except Exception as e:
            log.debug("Benchmarks context error: %s", e)
            ctx["benchmarks"] = {}
    else:
        ctx["benchmarks"] = {}

    # ── Today's anomalies ─────────────────────────────────────────────────────
    if include_shared_journal:
        try:
            from src.analytics.anomalies import detect_today
            ctx["anomalies"] = detect_today(ctx.get("_benchmarks_full"))
        except Exception as e:
            log.debug("Anomaly context error: %s", e)
            ctx["anomalies"] = []
    else:
        ctx["anomalies"] = []

    # ── Correlations (top 3 insights) ────────────────────────────────────────
    try:
        from src.analytics.correlations import top_insights
        ctx["insights"] = top_insights(3)
    except Exception as e:
        log.debug("Correlations context error: %s", e)
        ctx["insights"] = []

    # ── Habits ────────────────────────────────────────────────────────────────
    try:
        from src.notify.store import habit_streak, habit_done_today
        habits_ctx = []
        for h in active_habits:
            habits_ctx.append({
                "name":      h["name"],
                "streak":    habit_streak(h["id"], user_id=effective_user_id),
                "done_today": habit_done_today(h["id"], user_id=effective_user_id),
                "remind_at": h["remind_at"],
            })
        ctx["habits"] = habits_ctx
    except Exception as e:
        log.debug("Habits context error: %s", e)
        ctx["habits"] = []

    # ── Goals ─────────────────────────────────────────────────────────────────
    ctx["goals"] = [
        {"title": g["title"], "progress": g["progress"], "deadline": g.get("deadline")}
        for g in active_goals
    ]
    ctx["personal_goals"] = list(ctx["goals"])

    return ctx


def build_context(ctx: dict | None = None, *, user_id: int | None = None) -> str:
    """
    Build the context string to inject into an LLM prompt.
    Returns a compact, structured text block (~400-600 tokens).
    """
    if ctx is None:
        ctx = build_dict(user_id=user_id)

    identity  = ctx.get("identity", {})
    today     = ctx.get("today", {})
    bench     = ctx.get("benchmarks", {})
    anomalies = ctx.get("anomalies", [])
    insights  = ctx.get("insights", [])
    habits    = ctx.get("habits", [])
    goals     = ctx.get("goals", [])
    name      = identity.get("name", "Rana")
    level     = identity.get("level", "Stranger")

    lines = ["=== PPT PERSONAL CONTEXT ==="]
    lines.append(f"[Identity] Name: {name}  |  Relationship level: {level}  |  XP: {identity.get('xp', 0)}")
    lines.append(f"[Date] {ctx.get('date', 'unknown')}")
    lines.append("")

    # Today
    lines.append("[Right Now]")
    sleep_t = today.get("sleep_last_night")
    if sleep_t and sleep_t.get("hours"):
        avg_sl = bench.get("sleep_avg_hours")
        flag = ""
        if avg_sl and sleep_t["hours"] < avg_sl - 1:
            flag = " ⚠️ BELOW BASELINE"
        elif avg_sl and sleep_t["hours"] > avg_sl + 1:
            flag = " ✅ ABOVE BASELINE"
        q_str = f"  quality {sleep_t['quality']}/5" if sleep_t.get("quality") else ""
        lines.append(f"  Sleep: {sleep_t['hours']}h{q_str}{flag}")
    else:
        lines.append("  Sleep: not logged")

    food_t = today.get("food", {})
    if food_t.get("calories", 0) > 0:
        lines.append(f"  Food:  {food_t['calories']} cal · {food_t['meals']} meals"
                     f"  (P:{food_t.get('protein_g',0)}g C:{food_t.get('carbs_g',0)}g F:{food_t.get('fat_g',0)}g)")
    else:
        lines.append("  Food:  not logged today")

    work_t = today.get("work", {})
    live = " 🔴 LIVE SESSION" if work_t.get("active_session") else ""
    task_str = f" — {work_t['task']}" if work_t.get("task") else ""
    lines.append(f"  Work:  {work_t.get('hours', 0)}h{task_str}{live}")
    lines.append(f"  Spend: ${today.get('spending', 0):.2f}")
    lines.append("")

    # Benchmarks
    if any(v is not None for v in bench.values()):
        lines.append("[30-day Baselines]")
        if bench.get("sleep_avg_hours"):
            lines.append(f"  Sleep: {bench['sleep_avg_hours']}h/night avg")
        if bench.get("work_avg_hours"):
            lines.append(f"  Work:  {bench['work_avg_hours']}h/day avg")
        if bench.get("food_avg_cal"):
            lines.append(f"  Food:  {bench['food_avg_cal']} cal/day avg")
        if bench.get("spend_avg_daily"):
            lines.append(f"  Spend: ${bench['spend_avg_daily']:.2f}/day avg")
        if bench.get("habit_completion") is not None:
            pct = round(bench["habit_completion"] * 100)
            lines.append(f"  Habits: {pct}% completion rate")
        lines.append("")

    # Anomalies
    if anomalies:
        lines.append("[Today's Anomalies]")
        for a in anomalies[:3]:
            lines.append(f"  ⚡ {a['message']}")
        lines.append("")

    # Habits
    if habits:
        lines.append("[Habits Today]")
        for h in habits:
            done = "✓" if h["done_today"] else "○"
            lines.append(f"  {done} {h['name']} (streak: {h['streak']}d) @ {h['remind_at']}")
        lines.append("")

    # Goals
    if goals:
        lines.append("[Personal Goals]")
        for g in goals:
            dl = f" · due {g['deadline']}" if g.get("deadline") else ""
            lines.append(f"  • {g['title']} — {g['progress']}%{dl}")
        lines.append("")

    # Insights
    if insights:
        lines.append("[Your Patterns]")
        for ins in insights:
            lines.append(f"  → {ins}")
        lines.append("")

    lines.append("=== END CONTEXT ===")
    return "\n".join(lines)


def build_system_prompt(ctx: dict | None = None, *, user_id: int | None = None) -> str:
    """
    Full system prompt = PPT role definition + personal context.
    Pass this as the system message to every Ollama query.
    """
    if ctx is None:
        ctx = build_dict(user_id=user_id)
    name  = ctx.get("identity", {}).get("name", "Rana")
    level = ctx.get("identity", {}).get("level", "Stranger")

    role = (
        f"You are PPT, {name}'s personal AI assistant. "
        f"Your relationship with {name} is at level '{level}'. "
        f"You know {name}'s daily patterns, habits, personal goals, and life data. "
        f"Use the personal context below to give specific, relevant, personalised advice. "
        f"Be warm, direct, and honest. Never be generic — always connect to {name}'s actual data.\n\n"
    )
    return role + build_context(ctx, user_id=user_id)
