"""
src/notify/scheduler.py — APScheduler-based notification engine.

WHY APScheduler?
  It's already in requirements.txt (apscheduler>=3.10.0).
  It runs inside Python — no cron config, no systemd, just `python scripts/notify_daemon.py`.
  Jobs are loaded from the database at startup and can be reloaded live.

HOW it works:
  1. At startup, load_all_jobs() reads every active habit, goal, and reminder
     from the database and schedules them as APScheduler CronTrigger jobs.
  2. Every minute, a heartbeat job checks if new items were added (so you
     don't have to restart the daemon to pick up new habits/reminders).
  3. Each job calls messenger.send() with the right channels.

CHANNELS:
  By default every notification goes to Telegram (phone + watch).
  If PPT_TTS_NOTIFY=1 env variable is set, TTS is also enabled.
  This lets you silence the speaker at night without changing code.

USAGE (from scripts/notify_daemon.py):
    from src.notify.scheduler import start_blocking
    start_blocking()
"""
from __future__ import annotations
import logging
import os
from datetime import datetime, date, timedelta

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from src.notify import store, messenger

log = logging.getLogger(__name__)

# ── Channel config ─────────────────────────────────────────────────────────────

def _channels() -> list[str]:
    """Return active channels based on environment."""
    ch = ["telegram"]
    if os.getenv("PPT_TTS_NOTIFY", "0") == "1":
        ch.append("tts")
    return ch


# ── Job functions (called by APScheduler at fire time) ─────────────────────────

def _fire_habit(habit_id: int, user_id: int) -> None:
    habit = store.get_habit(habit_id, user_id=user_id)
    if not habit or not habit["active"]:
        return
    streak = store.habit_streak(habit_id, user_id=user_id)
    result = messenger.notify_habit(habit["name"], streak=streak, channels=_channels(), user_id=user_id)
    log.info("Habit '%s' fired | streak=%d | result=%s", habit["name"], streak, result)


def _fire_goal(goal_id: int, user_id: int) -> None:
    goal = store.get_goal(goal_id, user_id=user_id)
    if not goal or goal["status"] != "active":
        return
    result = messenger.notify_goal(
        goal["title"],
        progress=goal["progress"],
        deadline=goal.get("deadline"),
        channels=_channels(),
        user_id=user_id,
    )
    log.info("Goal '%s' fired | progress=%d%% | result=%s", goal["title"], goal["progress"], result)


def _fire_reminder(reminder_id: int, user_id: int) -> None:
    reminder = store.get_reminder(reminder_id, user_id=user_id)
    if not reminder or not reminder["active"]:
        return
    text = reminder["message"] or reminder["title"]
    result = messenger.send(
        f"⏰ {reminder['title']}\n{text}" if reminder["message"] else f"⏰ {reminder['title']}",
        channels=_channels(),
        user_id=user_id,
    )
    outcome = "sent" if result.get("telegram") else "failed"
    store.log_reminder_fire(
        user_id,
        reminder_id,
        telegram_message_id=str(result.get("telegram_message_id")) if result.get("telegram_message_id") is not None else None,
        outcome=outcome,
    )
    # Deactivate one-time reminders after firing
    if reminder["repeat"] == "once":
        store.deactivate_reminder(reminder_id, user_id=user_id)
    log.info("Reminder '%s' fired | result=%s", reminder["title"], result)


def _fire_morning_greeting(user_id: int) -> None:
    habits = store.list_habits(active_only=True, user_id=user_id)
    messenger.notify_morning(habit_count=len(habits), channels=_channels(), user_id=user_id)
    log.info("Morning greeting fired | user=%d | %d habits today", user_id, len(habits))


def _fire_checkin_prompt(user_id: int) -> None:
    # Look up yesterday's mood to personalise the prompt
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    prev = store.get_checkin(yesterday, user_id=user_id)
    prev_mood = prev["mood"] if prev else None
    messenger.notify_checkin(prev_mood=prev_mood, channels=_channels(), user_id=user_id)
    log.info("Check-in prompt fired | user=%d", user_id)


# ── Helpers to parse time strings ─────────────────────────────────────────────

def _hhmm(time_str: str) -> tuple[int, int]:
    """Parse 'HH:MM' → (hour, minute)."""
    h, m = time_str.strip().split(":")
    return int(h), int(m)


def _frequency_to_cron(frequency: str) -> dict:
    """Convert our frequency strings to APScheduler CronTrigger kwargs."""
    mapping = {
        "daily":    {"day_of_week": "mon-sun"},
        "weekdays": {"day_of_week": "mon-fri"},
        "weekends": {"day_of_week": "sat,sun"},
        "weekly":   {"day_of_week": "mon"},   # Mondays
    }
    return mapping.get(frequency, {"day_of_week": "mon-sun"})


# ── Job loader ─────────────────────────────────────────────────────────────────

def load_all_jobs(scheduler: BlockingScheduler) -> None:
    """Read the database and schedule every active item.

    WHY we clear and reload instead of diffing:
      Simpler.  The number of jobs is small (< 50 typically).
      Remove all ppt-notify jobs, then re-add from current DB state.
      This makes the heartbeat reload trivially correct.
    """
    # Remove all previously scheduled notify jobs
    for job in scheduler.get_jobs():
        if job.id.startswith("notify_"):
            job.remove()

    delivery_users = store.list_delivery_users()

    for user in delivery_users:
        profile = store.get_profile(user["id"])
        timezone = profile.get("timezone") or "UTC"
        scheduler.add_job(
            _fire_morning_greeting,
            CronTrigger(hour=7, minute=30, timezone=timezone),
            id=f"notify_morning_{user['id']}",
            args=[user["id"]],
            replace_existing=True,
            misfire_grace_time=300,
        )
        scheduler.add_job(
            _fire_checkin_prompt,
            CronTrigger(hour=21, minute=0, timezone=timezone),
            id=f"notify_checkin_{user['id']}",
            args=[user["id"]],
            replace_existing=True,
            misfire_grace_time=300,
        )

    # ── Daily anomaly scan at 20:00 ────────────────────────────────────────
    # WHY 20:00? By 8pm you've logged most of today's data (food, work, sleep).
    # We compute today's benchmarks, check for significant deviations, and
    # send an alert only if something stands out — no unnecessary noise.
    scheduler.add_job(
        _fire_anomaly_scan,
        CronTrigger(hour=20, minute=0),
        id="notify_anomaly_scan",
        replace_existing=True,
        misfire_grace_time=300,
    )

    # ── Habits ────────────────────────────────────────────────────────────
    for user in delivery_users:
        profile = store.get_profile(user["id"])
        timezone = profile.get("timezone") or "UTC"
        for habit in store.list_habits(active_only=True, user_id=user["id"]):
            try:
                h, m = _hhmm(habit["remind_at"])
                cron_kwargs = _frequency_to_cron(habit["frequency"])
                scheduler.add_job(
                    _fire_habit,
                    CronTrigger(hour=h, minute=m, timezone=timezone, **cron_kwargs),
                    id=f"notify_habit_{user['id']}_{habit['id']}",
                    args=[habit["id"], user["id"]],
                    replace_existing=True,
                    misfire_grace_time=300,
                )
                log.info(
                    "Scheduled habit '%s' at %s (%s) for user=%d",
                    habit["name"], habit["remind_at"], habit["frequency"], user["id"]
                )
            except Exception as e:
                log.error("Failed to schedule habit %d for user=%d: %s", habit["id"], user["id"], e)

    # ── Goals with remind_at set ──────────────────────────────────────────
    for user in delivery_users:
        profile = store.get_profile(user["id"])
        timezone = profile.get("timezone") or "UTC"
        for goal in store.list_goals(status="active", user_id=user["id"]):
            if not goal.get("remind_at"):
                continue
            try:
                h, m = _hhmm(goal["remind_at"])
                cron_kwargs = _frequency_to_cron(goal.get("remind_days", "daily"))
                scheduler.add_job(
                    _fire_goal,
                    CronTrigger(hour=h, minute=m, timezone=timezone, **cron_kwargs),
                    id=f"notify_goal_{user['id']}_{goal['id']}",
                    args=[goal["id"], user["id"]],
                    replace_existing=True,
                    misfire_grace_time=300,
                )
                log.info("Scheduled goal '%s' at %s for user=%d", goal["title"], goal["remind_at"], user["id"])
            except Exception as e:
                log.error("Failed to schedule goal %d for user=%d: %s", goal["id"], user["id"], e)

    # ── Reminders ─────────────────────────────────────────────────────────
    for user in delivery_users:
        profile = store.get_profile(user["id"])
        timezone = profile.get("timezone") or "UTC"
        for reminder in store.list_reminders(active_only=True, user_id=user["id"]):
            try:
                h, m = _hhmm(reminder["remind_at"])
                if reminder["repeat"] == "once" and reminder.get("fire_date"):
                    fd = date.fromisoformat(reminder["fire_date"])
                    if fd < date.today():
                        store.deactivate_reminder(reminder["id"], user_id=user["id"])
                        continue
                    trigger = CronTrigger(
                        year=fd.year, month=fd.month, day=fd.day,
                        hour=h, minute=m, timezone=timezone
                    )
                else:
                    cron_kwargs = _frequency_to_cron(reminder.get("repeat", "daily"))
                    trigger = CronTrigger(hour=h, minute=m, timezone=timezone, **cron_kwargs)

                scheduler.add_job(
                    _fire_reminder,
                    trigger,
                    id=f"notify_reminder_{user['id']}_{reminder['id']}",
                    args=[reminder["id"], user["id"]],
                    replace_existing=True,
                    misfire_grace_time=300,
                )
                log.info("Scheduled reminder '%s' at %s for user=%d", reminder["title"], reminder["remind_at"], user["id"])
            except Exception as e:
                log.error("Failed to schedule reminder %d for user=%d: %s", reminder["id"], user["id"], e)

    # ── Journal alerts (smart pattern checks) ────────────────────────────────
    # WHY every 15 minutes?
    #   Each check_* function has its own time-gate (e.g. only fires after 14:00).
    #   Running the full suite every 15min is cheap and means alerts are timely.
    scheduler.add_job(
        _fire_journal_alerts,
        CronTrigger(minute="*/15"),
        id="notify_journal_alerts",
        replace_existing=True,
        misfire_grace_time=120,
    )
    log.info("Journal alert job scheduled (every 15 min)")

    # ── Morning digest (replaces generic morning greeting) ────────────────────
    scheduler.add_job(
        _fire_morning_digest,
        CronTrigger(hour=7, minute=30),
        id="notify_digest",
        replace_existing=True,
        misfire_grace_time=300,
    )
    log.info("Morning digest job scheduled at 07:30")

    # ── Project visibility digest at 08:00 ────────────────────────────────────
    # WHY 08:00 and not 07:30?
    #   The journal digest (above) covers food/sleep/work for the previous day.
    #   Firing the project digest one minute later keeps both messages visually
    #   distinct in your Telegram chat — you see the health summary first, then
    #   the project summary as a separate message you can act on.
    scheduler.add_job(
        _fire_project_digest,
        CronTrigger(hour=8, minute=0),
        id="notify_project_digest",
        replace_existing=True,
        misfire_grace_time=300,
    )
    log.info("Project digest job scheduled at 08:00")

    total = len([j for j in scheduler.get_jobs() if j.id.startswith("notify_")])
    log.info("Loaded %d notify jobs total", total)


def _fire_anomaly_scan() -> None:
    """Run Z-score anomaly detection and alert only if significant deviations found."""
    try:
        from src.analytics.anomalies import detect_today, anomaly_alert_message
        anomalies = detect_today()
        msg = anomaly_alert_message(anomalies)
        if msg:
            messenger.send(msg, channels=_channels())
            log.info("Anomaly alert sent: %d anomalies", len(anomalies))
        else:
            log.info("Anomaly scan: all metrics within normal range")
    except Exception as e:
        log.error("Anomaly scan failed: %s", e)


def _fire_journal_alerts() -> None:
    """Check all journal alert conditions and send those that fire."""
    try:
        from src.journal.alerts import check_all
        messages = check_all()
        for msg in messages:
            messenger.send(msg, channels=_channels())
    except Exception as e:
        log.error("Journal alerts check failed: %s", e)


def _fire_morning_digest() -> None:
    """Send the rich morning digest (replaces plain morning greeting)."""
    try:
        from src.journal.digest import send_digest
        send_digest()
    except Exception as e:
        # Fallback to simple greeting if journal data not available
        log.warning("Digest failed (%s), falling back to simple greeting", e)
        _fire_morning_greeting()


def _fire_project_digest() -> None:
    """Send the project-board morning digest at 08:00.

    WHY a separate function from _fire_morning_digest?
      The journal digest (src/journal/digest.py) is about personal health metrics.
      This digest is about project status and next actions.  Keeping them separate
      means each can fail independently without taking the other down, and you can
      disable one without touching the other.
    """
    try:
        from src.integrations.telegram_digest import send_morning_digest
        send_morning_digest()
    except Exception as e:
        log.error("Project digest failed: %s", e)


# ── Entry point ────────────────────────────────────────────────────────────────

def start_blocking() -> None:
    """Start the scheduler and block forever.  Called from scripts/notify_daemon.py."""
    store.init_db()

    # Also initialise journal DB
    try:
        from src.journal.store import init_db as journal_init
        journal_init()
    except Exception as e:
        log.warning("Journal DB init skipped: %s", e)

    # "local" isn't accepted on macOS Python 3.9 — read the actual tz from /etc/localtime
    import os
    try:
        link = os.readlink('/etc/localtime')
        _tz = '/'.join(link.split('/')[-2:])  # e.g. 'Europe/London' or 'America/New_York'
    except Exception:
        _tz = 'UTC'
    scheduler = BlockingScheduler(timezone=_tz)

    # Initial load
    load_all_jobs(scheduler)

    # Heartbeat: reload jobs every 5 minutes to pick up new habits/reminders
    scheduler.add_job(
        lambda: load_all_jobs(scheduler),
        CronTrigger(minute="*/5"),
        id="notify_reload",
        replace_existing=True,
    )

    log.info("PPT notify scheduler started. Ctrl+C to stop.")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("PPT notify scheduler stopped.")
