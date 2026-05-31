"""
ppt-notify — relationship-aware habit, goal, and reminder engine for PPT.

Why this module exists:
  The voice assistant already reacts when you talk to it.
  This module makes PPT proactive — it reaches out to YOU on a schedule,
  tracks your habits, celebrates streaks, and builds a persistent relationship
  that deepens the more you engage with it.

Public API (import from here):
  from src.notify import store, messenger, relationship, scheduler

NOTE: scheduler imports APScheduler — only import it from the daemon script.
      The web app only needs store, messenger, relationship.
"""
from src.notify import store, messenger, relationship

# Scheduler is imported lazily (only by notify_daemon.py) because it
# requires APScheduler which may not be installed in all environments.
def get_scheduler():
    from src.notify import scheduler
    return scheduler

__all__ = ["store", "messenger", "relationship", "get_scheduler"]
