"""
src/journal/alerts.py — smart pattern detection for ppt-journal.

WHY smart alerts?
  Dumb reminders fire at a fixed time regardless of what you've done.
  Smart alerts check what actually happened and only fire when needed.

  Examples:
    "You haven't logged any food today"  → only fires at 14:00 if no entries
    "Your sleep dropped below 6h"        → only fires if avg drops, not every day
    "You're 80% through your budget"     → fires once when threshold is crossed
    "3h in a work session — take a break"→ fires only if an active session exists

EACH ALERT FUNCTION:
  - Returns a message string if the alert should fire
  - Returns None if conditions are not met (alert should NOT fire)
  - This pattern makes it easy for the scheduler to decide: fire or skip

USAGE (from scheduler.py):
    from src.journal.alerts import check_all
    alerts = check_all()
    for msg in alerts:
        messenger.send(msg)
"""
from __future__ import annotations
import logging
from datetime import datetime, date, timedelta
from src.journal import store

log = logging.getLogger(__name__)


# ── Individual alert checks ────────────────────────────────────────────────────

def check_food_logging() -> str | None:
    """
    Fire if no food has been logged today and it's past 14:00.
    WHY 14:00? Before noon it's too early to worry. By 2pm, if nothing is logged,
    either you forgot to eat or forgot to log — both are worth a nudge.
    """
    now_hour = datetime.now().hour
    if now_hour < 14:
        return None
    totals = store.food_daily_totals()
    if totals["meals"] == 0:
        return "🍽 Hey — you haven't logged any food today. Don't forget to eat, Rana!"
    return None


def check_food_calories() -> str | None:
    """Alert if today's calories are very low (< 800 by 20:00) — possible undereating."""
    now_hour = datetime.now().hour
    if now_hour < 20:
        return None
    totals = store.food_daily_totals()
    cal = totals.get("calories", 0)
    if 0 < cal < 800:
        return f"⚠️ You've only logged {cal} calories today. That seems low — make sure you're eating enough."
    return None


def check_sleep_average() -> str | None:
    """
    Alert if the 7-day average sleep drops below 7 hours.
    WHY 7h? WHO recommends 7-9h for adults. Below 7 is a meaningful signal.
    Only fires on Monday mornings (weekly check to avoid nagging).
    """
    if date.today().weekday() != 0:  # Monday only
        return None
    avg = store.sleep_avg_hours(7)
    if avg is None:
        return None
    if avg < 6.0:
        return f"😴 Your 7-day sleep average is {avg}h — that's well below the recommended 7h. Try to prioritise rest this week."
    if avg < 7.0:
        return f"💤 Your weekly sleep average is {avg}h. A little under 7h — small improvements add up."
    return None


def check_sleep_logged_today() -> str | None:
    """
    Fire at 22:00 if tonight's sleep hasn't been set up yet.
    The point is to remind you to log yesterday's sleep if you haven't.
    """
    now_hour = datetime.now().hour
    if now_hour != 22:
        return None
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    sleep = store.get_sleep(yesterday)
    if not sleep:
        return "🌙 Don't forget to log last night's sleep before you head to bed, Rana."
    return None


def check_work_break() -> str | None:
    """
    If there's an active (unclosed) work session that started > 90 minutes ago,
    suggest a break. Fires once — caller is responsible for not re-firing too soon.
    """
    session = store.active_session()
    if not session:
        return None
    try:
        start = datetime.strptime(
            session["date"] + " " + session["start_time"], "%Y-%m-%d %H:%M"
        )
        elapsed_min = (datetime.now() - start).total_seconds() / 60
        if elapsed_min >= 90:
            h = int(elapsed_min // 60)
            m = int(elapsed_min % 60)
            duration_str = f"{h}h {m}m" if h else f"{m}m"
            task = session.get("task") or "your task"
            return (
                f"🧘 You've been working on '{task}' for {duration_str} straight. "
                f"Take a 5-minute break — your brain will thank you."
            )
    except Exception as e:
        log.debug("Work break check error: %s", e)
    return None


def check_work_hours() -> str | None:
    """
    At 19:00 on weekdays, if total work today > 9h, flag potential overwork.
    WHY 19:00? Evening is when work-life balance matters most.
    """
    if date.today().weekday() >= 5:  # skip weekends
        return None
    if datetime.now().hour != 19:
        return None
    total_min = store.work_daily_total_min()
    if total_min >= 540:  # 9 hours
        total_h = round(total_min / 60, 1)
        return (
            f"⚠️ You've logged {total_h}h of work today. "
            f"Make sure to log off and recharge, Rana. Work-life balance matters."
        )
    return None


def check_budget() -> str | None:
    """
    Alert when weekly spend crosses 80% of budget.
    Only alerts once per day (caller manages this via scheduling).
    """
    status = store.budget_status()
    if status["budget"] is None:
        return None
    pct = status.get("pct", 0)
    if pct >= 100:
        return (
            f"🚨 Budget alert: you've spent ${status['spent']:.2f} "
            f"— that's over your ${status['budget']:.2f} weekly budget."
        )
    if pct >= 80:
        return (
            f"💸 Heads up: you've used {pct}% of your weekly budget "
            f"(${status['spent']:.2f} of ${status['budget']:.2f}). "
            f"${status['remaining']:.2f} remaining."
        )
    return None


def check_spend_logged() -> str | None:
    """
    At 21:00, remind to log any purchases made today if nothing logged.
    This builds the habit of tracking spending every day.
    """
    if datetime.now().hour != 21:
        return None
    today_spend = store.spend_today()
    if not today_spend:
        return "💰 Did you spend anything today? Quick log before bed keeps your money tracking accurate."
    return None


# ── Combined check ─────────────────────────────────────────────────────────────

def check_all() -> list[str]:
    """
    Run all alert checks and return a list of messages that should be sent.
    Returns empty list if nothing needs firing.

    WHY return a list?
      Some situations generate multiple alerts simultaneously.
      The caller decides how to bundle or prioritise them.
    """
    checks = [
        check_food_logging,
        check_food_calories,
        check_sleep_average,
        check_sleep_logged_today,
        check_work_break,
        check_work_hours,
        check_budget,
        check_spend_logged,
    ]
    messages = []
    for fn in checks:
        try:
            msg = fn()
            if msg:
                messages.append(msg)
                log.info("Alert triggered: %s", fn.__name__)
        except Exception as e:
            log.error("Alert check %s failed: %s", fn.__name__, e)
    return messages


# ── Work-life balance score ────────────────────────────────────────────────────

def work_life_score(days: int = 7) -> dict:
    """
    Calculate a simple work-life balance score (0–100) for the last N days.

    HOW it works:
      - Target: 8h work, 8h sleep, 1h+ food time (proxy for meals logged)
      - For each day: score each dimension 0–100 based on how close to target
      - Average across all days
      - Overall score = weighted average: sleep 40%, work 40%, food 20%

    WHY this matters:
      The score is shown in the Today overview so Rana has a single number
      that tells her if life is balanced or if something needs attention.
    """
    from datetime import timedelta
    today = date.today()
    scores = []

    for i in range(days):
        d = (today - timedelta(days=i)).isoformat()

        # Sleep score (target 7.5h = 450min)
        sleep = store.get_sleep(d)
        sleep_min = sleep["duration_min"] if sleep and sleep["duration_min"] else 0
        sleep_score = min(100, int(sleep_min / 450 * 100))

        # Work score (target 7-8h = penalise both under AND over)
        work_min = store.work_daily_total_min(d)
        if work_min == 0:
            work_score = 50  # neutral if not tracked
        elif work_min <= 480:  # up to 8h = good
            work_score = min(100, int(work_min / 480 * 100))
        else:  # over 8h = penalise overwork
            work_score = max(0, 100 - int((work_min - 480) / 60 * 15))

        # Food score (at least some logging = proxy for eating regularly)
        food = store.food_daily_totals(d)
        food_score = min(100, food["meals"] * 25)  # 4+ meals = 100

        day_score = int(sleep_score * 0.4 + work_score * 0.4 + food_score * 0.2)
        scores.append(day_score)

    avg = int(sum(scores) / len(scores)) if scores else 50
    label = (
        "Excellent" if avg >= 85 else
        "Good"      if avg >= 70 else
        "Fair"      if avg >= 50 else
        "Needs attention"
    )
    return {"score": avg, "label": label, "days": days, "daily": list(reversed(scores))}
