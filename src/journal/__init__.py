"""
src/journal/ — PPT's daily life journal engine.

WHY a journal?
  Notifications are only as smart as the data behind them.
  This module gives PPT a record of your daily life — what you ate,
  how you slept, when you worked, what you spent.  That record is what
  lets PPT say "you've been sleeping under 6 hours for 3 days" instead
  of just "time for bed."

MODULES:
  store   — SQLite persistence for all 4 domains (food, sleep, work, money)
  alerts  — pattern detection → generates smart notification triggers
  digest  — builds the daily morning summary across all modules

DOMAINS:
  Food    — meal logs, calories, macros (protein / carbs / fat)
  Sleep   — sleep sessions with duration, quality, bedtime/waketime
  Work    — work sessions with clock-in/out, project, task
  Money   — spending logs with category and budget tracking

INPUT CHANNELS (both write to the same store):
  Web UI      → /journal/* routes in src/web/journal_routes.py
  Telegram    → /food /sleep /work /spend /digest commands
"""
from src.journal import store, alerts, digest

__all__ = ["store", "alerts", "digest"]
