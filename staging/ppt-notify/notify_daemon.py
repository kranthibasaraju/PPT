#!/usr/bin/env python3
"""
scripts/notify_daemon.py — unified PPT background daemon.

WHAT IT RUNS (3 things simultaneously):
  1. APScheduler  — fires habits, goals, reminders, journal alerts, morning digest
  2. Telegram listener — polls for /food /sleep /work /spend /digest commands
  3. (Optional) TTS — Piper speaks reminders aloud if PPT_TTS_NOTIFY=1

WHY one process?
  Fewer things to manage.  One `python scripts/notify_daemon.py` in the
  background covers everything.  The scheduler runs on the main thread.
  The Telegram listener runs in a daemon thread alongside it.

HOW TO RUN:
  # Normal (Telegram only):
  python scripts/notify_daemon.py

  # With voice (Piper TTS on speaker):
  PPT_TTS_NOTIFY=1 python scripts/notify_daemon.py

  # Background (Mac — logs to file):
  nohup python scripts/notify_daemon.py > logs/notify.log 2>&1 &

  # Stop background process:
  pkill -f notify_daemon.py

ENVIRONMENT VARIABLES:
  PPT_TTS_NOTIFY   = 1   → enable voice notifications via Piper TTS
  PPT_NO_TELEGRAM  = 1   → disable Telegram listener (for testing)
"""
import sys
import os
import logging
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("ppt.daemon")


def start_telegram_listener(stop_event: threading.Event) -> None:
    """Run the Telegram command listener in a background thread."""
    if os.getenv("PPT_NO_TELEGRAM") == "1":
        log.info("Telegram listener disabled (PPT_NO_TELEGRAM=1)")
        return
    from src.integrations.telegram_commands import run_listener
    t = threading.Thread(
        target=run_listener,
        kwargs={"poll_interval": 3.0, "stop_event": stop_event},
        name="telegram-listener",
        daemon=True,   # Thread dies when main process exits
    )
    t.start()
    log.info("Telegram listener thread started")


def main():
    log.info("=" * 60)
    log.info("PPT Daemon starting")
    log.info("Telegram channel  : %s", "OFF" if os.getenv("PPT_NO_TELEGRAM") == "1" else "ON")
    log.info("TTS channel       : %s", "ON (Piper)" if os.getenv("PPT_TTS_NOTIFY") == "1" else "OFF")
    log.info("Scheduler         : ON (APScheduler)")
    log.info("=" * 60)

    stop_event = threading.Event()

    # Start Telegram listener in background thread
    start_telegram_listener(stop_event)

    # Start APScheduler on main thread (blocking)
    from src.notify.scheduler import start_blocking
    try:
        start_blocking()
    except Exception as e:
        log.error("Scheduler crashed: %s", e)
    finally:
        stop_event.set()
        log.info("PPT Daemon stopped.")


if __name__ == "__main__":
    main()
