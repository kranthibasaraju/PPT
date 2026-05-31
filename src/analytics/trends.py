"""
src/analytics/trends.py — time-series data for dashboards and training.

WHY trends matter for training data:
  A single data point tells you nothing about direction.
  A trend tells the LLM whether things are improving, declining, or stable.
  "Your sleep has been improving over the past two weeks" is only possible
  because we track the direction of change, not just the value.

WHAT THIS PROVIDES:
  - time_series(domain, metric, days)  → list of (date, value) pairs
  - moving_average(values, window)     → smoothed trend line
  - week_over_week(domain, metric)     → % change this week vs last week
  - summary(days)                      → all domains, all metrics, ready for charts

USAGE:
  from src.analytics.trends import summary
  data = summary(30)
  # data["sleep"]["hours"] = [(date, value), ...]
  # data["sleep"]["wow_change"] = +5.2  (5.2% better than last week)
"""
from __future__ import annotations
import logging
import sqlite3
from datetime import date, timedelta
from pathlib import Path

log = logging.getLogger(__name__)

_JOURNAL_DB = Path(__file__).parent.parent.parent / "data" / "journal.db"
_NOTIFY_DB  = Path(__file__).parent.parent.parent / "data" / "notify.db"


def _conn(db_path: Path) -> sqlite3.Connection | None:
    if not db_path.exists():
        return None
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    return con


def _date_list(days: int) -> list[str]:
    """Return list of ISO date strings for the last N days."""
    return [(date.today() - timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]


def moving_average(values: list[float | None], window: int = 7) -> list[float | None]:
    """
    Compute a rolling average.
    WHY moving average? Raw daily data is noisy. A 7-day moving average
    reveals the true trend underneath day-to-day variance.
    None values (missing days) are skipped in the window calculation.
    """
    result = []
    for i in range(len(values)):
        window_vals = [v for v in values[max(0, i - window + 1): i + 1] if v is not None]
        result.append(round(sum(window_vals) / len(window_vals), 2) if window_vals else None)
    return result


def wow_change(current: float | None, previous: float | None) -> float | None:
    """
    Week-over-week percentage change.
    WHY percentage? Absolute change is hard to compare across metrics.
    +8% sleep is meaningful regardless of whether your baseline is 6h or 8h.
    """
    if current is None or previous is None or previous == 0:
        return None
    return round((current - previous) / previous * 100, 1)


# ── Domain-specific series ────────────────────────────────────────────────────

def sleep_series(days: int = 30) -> dict:
    con = _conn(_JOURNAL_DB)
    dates = _date_list(days)
    hours_map: dict[str, float | None] = {d: None for d in dates}
    quality_map: dict[str, float | None] = {d: None for d in dates}

    if con:
        start = dates[0]
        rows = con.execute("""
            SELECT date, duration_min, quality FROM sleep_logs
            WHERE date >= ? ORDER BY date
        """, (start,)).fetchall()
        con.close()
        for r in rows:
            if r["date"] in hours_map:
                hours_map[r["date"]] = round(r["duration_min"] / 60, 2) if r["duration_min"] else None
                quality_map[r["date"]] = r["quality"]

    hours   = [hours_map[d] for d in dates]
    quality = [quality_map[d] for d in dates]

    # Week-over-week
    this_week = [h for h in hours[-7:] if h is not None]
    last_week = [h for h in hours[-14:-7] if h is not None]
    avg_this  = sum(this_week) / len(this_week) if this_week else None
    avg_last  = sum(last_week) / len(last_week) if last_week else None

    return {
        "dates":   dates,
        "hours":   hours,
        "quality": quality,
        "ma7":     moving_average(hours, 7),
        "wow":     wow_change(avg_this, avg_last),
    }


def food_series(days: int = 30) -> dict:
    con = _conn(_JOURNAL_DB)
    dates = _date_list(days)
    cal_map: dict[str, float | None] = {d: None for d in dates}

    if con:
        start = dates[0]
        rows = con.execute("""
            SELECT date, COALESCE(SUM(calories),0) as cal
            FROM food_logs WHERE date >= ?
            GROUP BY date
        """, (start,)).fetchall()
        con.close()
        for r in rows:
            if r["date"] in cal_map and r["cal"] > 0:
                cal_map[r["date"]] = r["cal"]

    calories = [cal_map[d] for d in dates]
    this_week = [c for c in calories[-7:] if c is not None]
    last_week = [c for c in calories[-14:-7] if c is not None]

    return {
        "dates":    dates,
        "calories": calories,
        "ma7":      moving_average(calories, 7),
        "wow":      wow_change(
            sum(this_week) / len(this_week) if this_week else None,
            sum(last_week) / len(last_week) if last_week else None,
        ),
    }


def work_series(days: int = 30) -> dict:
    con = _conn(_JOURNAL_DB)
    dates = _date_list(days)
    hours_map: dict[str, float | None] = {d: None for d in dates}

    if con:
        start = dates[0]
        rows = con.execute("""
            SELECT date, COALESCE(SUM(duration_min),0) as total
            FROM work_sessions WHERE date >= ? AND end_time IS NOT NULL
            GROUP BY date
        """, (start,)).fetchall()
        con.close()
        for r in rows:
            if r["date"] in hours_map and r["total"] > 0:
                hours_map[r["date"]] = round(r["total"] / 60, 2)

    hours = [hours_map[d] for d in dates]
    this_week = [h for h in hours[-7:] if h is not None]
    last_week = [h for h in hours[-14:-7] if h is not None]

    return {
        "dates": dates,
        "hours": hours,
        "ma7":   moving_average(hours, 7),
        "wow":   wow_change(
            sum(this_week) / len(this_week) if this_week else None,
            sum(last_week) / len(last_week) if last_week else None,
        ),
    }


def money_series(days: int = 30) -> dict:
    con = _conn(_JOURNAL_DB)
    dates = _date_list(days)
    spend_map: dict[str, float | None] = {d: None for d in dates}

    if con:
        start = dates[0]
        rows = con.execute("""
            SELECT date, COALESCE(SUM(amount),0) as total
            FROM spending_logs WHERE date >= ?
            GROUP BY date
        """, (start,)).fetchall()
        con.close()
        for r in rows:
            if r["date"] in spend_map and r["total"] > 0:
                spend_map[r["date"]] = round(r["total"], 2)

    spend = [spend_map[d] for d in dates]
    this_week = [s for s in spend[-7:] if s is not None]
    last_week = [s for s in spend[-14:-7] if s is not None]

    return {
        "dates": dates,
        "spend": spend,
        "ma7":   moving_average(spend, 7),
        "wow":   wow_change(
            sum(this_week) / len(this_week) if this_week else None,
            sum(last_week) / len(last_week) if last_week else None,
        ),
    }


def habits_series(days: int = 30) -> dict:
    con = _conn(_NOTIFY_DB)
    dates = _date_list(days)
    rate_map: dict[str, float | None] = {d: None for d in dates}

    if con:
        total_habits = con.execute(
            "SELECT COUNT(*) as n FROM habits WHERE active=1"
        ).fetchone()["n"]
        if total_habits > 0:
            start = dates[0]
            rows = con.execute("""
                SELECT date, COUNT(DISTINCT habit_id) as done
                FROM habit_logs WHERE date >= ?
                GROUP BY date
            """, (start,)).fetchall()
            for r in rows:
                if r["date"] in rate_map:
                    rate_map[r["date"]] = round(min(r["done"] / total_habits, 1.0), 2)
        con.close()

    rates = [rate_map[d] for d in dates]
    this_week = [r for r in rates[-7:] if r is not None]
    last_week = [r for r in rates[-14:-7] if r is not None]

    return {
        "dates": dates,
        "rates": rates,
        "ma7":   moving_average(rates, 7),
        "wow":   wow_change(
            sum(this_week) / len(this_week) if this_week else None,
            sum(last_week) / len(last_week) if last_week else None,
        ),
    }


# ── Combined summary ──────────────────────────────────────────────────────────

def summary(days: int = 30) -> dict:
    """All trends in one dict. Used by the dashboard and training exporter."""
    return {
        "sleep":   sleep_series(days),
        "food":    food_series(days),
        "work":    work_series(days),
        "money":   money_series(days),
        "habits":  habits_series(days),
        "days":    days,
    }
