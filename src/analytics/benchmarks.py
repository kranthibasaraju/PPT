"""
src/analytics/benchmarks.py — personal baseline calculator.

WHY baselines matter:
  "You slept 6 hours" is a fact.
  "You slept 6 hours — 1.5h below your normal" is meaningful.
  "You slept 6 hours — your worst night in 3 weeks" is actionable.

  Without a personal baseline, you can't have anomaly detection,
  meaningful correlations, or a training dataset that reflects YOU.
  The baseline is the foundation of everything else in this analytics layer.

HOW baselines work:
  We compute rolling statistics (mean, std_dev, min, max, median) over
  the last N days of data for each tracked domain.

  WHY rolling? Because you change. The baseline from 90 days ago may not
  reflect who you are today. A 30-day window is a good "current you" signal.

RETURNED STRUCTURE:
  {
    "sleep": {
      "avg_hours": 7.4, "std_hours": 0.8, "avg_quality": 3.8,
      "typical_bedtime": "23:15", "typical_waketime": "06:45",
      "days_tracked": 28
    },
    "food": {
      "avg_calories": 1820, "avg_protein_g": 75, "avg_carbs_g": 215, "avg_fat_g": 62,
      "avg_meals_per_day": 3.2, "days_tracked": 22
    },
    "work": {
      "avg_hours": 7.1, "avg_sessions": 2.4, "most_common_start": "09:30",
      "days_tracked": 20
    },
    "money": {
      "avg_daily_spend": 34.50, "avg_weekly_spend": 189.0,
      "top_categories": ["food", "transport"],
      "days_tracked": 25
    },
    "habits": {
      "avg_completion_rate": 0.72,   # 72% of habits done per day
      "strongest_streak": {"name": "Drink water", "streak": 14}
    },
    "computed_at": "2026-05-17T07:30:00",
    "window_days": 30
  }
"""
from __future__ import annotations
import logging
import math
import sqlite3
from datetime import datetime, date, timedelta
from pathlib import Path

log = logging.getLogger(__name__)

_JOURNAL_DB = Path(__file__).parent.parent.parent / "data" / "journal.db"
_NOTIFY_DB  = Path(__file__).parent.parent.parent / "data" / "notify.db"
_DEFAULT_WINDOW = 30  # days


# ── Stats helpers ─────────────────────────────────────────────────────────────

def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


def _std(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    m = _mean(values)
    variance = sum((x - m) ** 2 for x in values) / len(values)
    return round(math.sqrt(variance), 2)


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    s = sorted(values)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def _conn(db_path: Path) -> sqlite3.Connection | None:
    if not db_path.exists():
        return None
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    return con


def _date_range(window_days: int) -> tuple[str, str]:
    end   = date.today().isoformat()
    start = (date.today() - timedelta(days=window_days)).isoformat()
    return start, end


# ── Domain benchmarks ─────────────────────────────────────────────────────────

def sleep_benchmark(window_days: int = _DEFAULT_WINDOW) -> dict:
    con = _conn(_JOURNAL_DB)
    if not con:
        return {"days_tracked": 0}
    start, end = _date_range(window_days)
    rows = con.execute("""
        SELECT duration_min, quality, bedtime, waketime
        FROM sleep_logs WHERE date >= ? AND date <= ?
    """, (start, end)).fetchall()
    con.close()

    durations = [r["duration_min"] / 60 for r in rows if r["duration_min"]]
    qualities = [r["quality"] for r in rows if r["quality"]]
    bedtimes  = [r["bedtime"] for r in rows if r["bedtime"]]
    waketimes = [r["waketime"] for r in rows if r["waketime"]]

    def _modal_time(times: list[str]) -> str | None:
        """Return the most common hour:minute bin (rounded to 15min)."""
        if not times:
            return None
        # Convert to minutes-since-midnight, find mean, convert back
        mins = []
        for t in times:
            try:
                h, m = map(int, t.split(":"))
                mins.append(h * 60 + m)
            except Exception:
                pass
        if not mins:
            return None
        avg_min = int(sum(mins) / len(mins))
        return f"{avg_min // 60:02d}:{avg_min % 60:02d}"

    return {
        "avg_hours":       _mean(durations),
        "std_hours":       _std(durations),
        "min_hours":       round(min(durations), 1) if durations else None,
        "max_hours":       round(max(durations), 1) if durations else None,
        "avg_quality":     _mean(qualities),
        "typical_bedtime": _modal_time(bedtimes),
        "typical_waketime":_modal_time(waketimes),
        "days_tracked":    len(rows),
    }


def food_benchmark(window_days: int = _DEFAULT_WINDOW) -> dict:
    con = _conn(_JOURNAL_DB)
    if not con:
        return {"days_tracked": 0}
    start, end = _date_range(window_days)

    # Daily aggregates
    rows = con.execute("""
        SELECT date,
               COUNT(*) as meals,
               COALESCE(SUM(calories),0)  as calories,
               COALESCE(SUM(protein_g),0) as protein_g,
               COALESCE(SUM(carbs_g),0)   as carbs_g,
               COALESCE(SUM(fat_g),0)     as fat_g
        FROM food_logs WHERE date >= ? AND date <= ?
        GROUP BY date
    """, (start, end)).fetchall()
    con.close()

    days_with_food = [r for r in rows if r["calories"] > 0]
    return {
        "avg_calories":     _mean([r["calories"] for r in days_with_food]),
        "std_calories":     _std([r["calories"] for r in days_with_food]),
        "avg_protein_g":    _mean([r["protein_g"] for r in days_with_food]),
        "avg_carbs_g":      _mean([r["carbs_g"] for r in days_with_food]),
        "avg_fat_g":        _mean([r["fat_g"] for r in days_with_food]),
        "avg_meals_per_day":_mean([r["meals"] for r in days_with_food]),
        "days_tracked":     len(days_with_food),
    }


def work_benchmark(window_days: int = _DEFAULT_WINDOW) -> dict:
    con = _conn(_JOURNAL_DB)
    if not con:
        return {"days_tracked": 0}
    start, end = _date_range(window_days)

    rows = con.execute("""
        SELECT date,
               COUNT(*) as sessions,
               COALESCE(SUM(duration_min),0) as total_min,
               MIN(start_time) as first_start
        FROM work_sessions
        WHERE date >= ? AND date <= ? AND end_time IS NOT NULL
        GROUP BY date
    """, (start, end)).fetchall()
    con.close()

    work_days = [r for r in rows if r["total_min"] > 0]
    start_times = [r["first_start"] for r in work_days if r["first_start"]]

    # Typical start time
    start_mins = []
    for t in start_times:
        try:
            h, m = map(int, t.split(":"))
            start_mins.append(h * 60 + m)
        except Exception:
            pass
    avg_start = None
    if start_mins:
        avg = int(sum(start_mins) / len(start_mins))
        avg_start = f"{avg // 60:02d}:{avg % 60:02d}"

    return {
        "avg_hours":        _mean([r["total_min"] / 60 for r in work_days]),
        "std_hours":        _std([r["total_min"] / 60 for r in work_days]),
        "avg_sessions":     _mean([r["sessions"] for r in work_days]),
        "typical_start":    avg_start,
        "days_tracked":     len(work_days),
    }


def money_benchmark(window_days: int = _DEFAULT_WINDOW) -> dict:
    con = _conn(_JOURNAL_DB)
    if not con:
        return {"days_tracked": 0}
    start, end = _date_range(window_days)

    daily = con.execute("""
        SELECT date, COALESCE(SUM(amount),0) as total
        FROM spending_logs WHERE date >= ? AND date <= ?
        GROUP BY date
    """, (start, end)).fetchall()

    cats = con.execute("""
        SELECT category, COALESCE(SUM(amount),0) as total
        FROM spending_logs WHERE date >= ? AND date <= ?
        GROUP BY category ORDER BY total DESC LIMIT 3
    """, (start, end)).fetchall()
    con.close()

    spend_days = [r for r in daily if r["total"] > 0]
    return {
        "avg_daily_spend":  _mean([r["total"] for r in spend_days]),
        "std_daily_spend":  _std([r["total"] for r in spend_days]),
        "avg_weekly_spend": round(_mean([r["total"] for r in spend_days]) * 7, 2)
                            if spend_days else None,
        "top_categories":   [r["category"] for r in cats],
        "days_tracked":     len(spend_days),
    }


def habits_benchmark(window_days: int = _DEFAULT_WINDOW) -> dict:
    con = _conn(_NOTIFY_DB)
    if not con:
        return {"days_tracked": 0}
    start, end = _date_range(window_days)

    # Completion rate: how many active habits were logged per day vs. total active
    habits = con.execute(
        "SELECT id, name FROM habits WHERE active=1"
    ).fetchall()
    total_habits = len(habits)

    if total_habits == 0:
        con.close()
        return {"avg_completion_rate": None, "days_tracked": 0}

    daily_logs = con.execute("""
        SELECT date, COUNT(DISTINCT habit_id) as done
        FROM habit_logs WHERE date >= ? AND date <= ?
        GROUP BY date
    """, (start, end)).fetchall()

    # Streak per habit
    streaks = []
    for h in habits:
        rows = con.execute("""
            SELECT date FROM habit_logs
            WHERE habit_id=? ORDER BY date DESC
        """, (h["id"],)).fetchall()
        streak = 0
        check = date.today()
        for r in rows:
            logged = date.fromisoformat(r["date"])
            if logged == check:
                streak += 1
                check -= timedelta(days=1)
            else:
                break
        streaks.append({"name": h["name"], "streak": streak})

    con.close()

    rates = [min(r["done"] / total_habits, 1.0) for r in daily_logs]
    best = max(streaks, key=lambda x: x["streak"]) if streaks else None

    return {
        "avg_completion_rate": _mean(rates),
        "total_active_habits": total_habits,
        "strongest_streak":    best,
        "days_tracked":        len(daily_logs),
    }


# ── Combined profile ──────────────────────────────────────────────────────────

def full_benchmark(window_days: int = _DEFAULT_WINDOW) -> dict:
    """
    Compute and return all personal baselines in one call.
    This is the primary input for:
      - anomaly detection (is today unusual vs. my normal?)
      - training data generation (what are Rana's patterns?)
      - context building (what should the LLM know about me right now?)
    """
    return {
        "sleep":         sleep_benchmark(window_days),
        "food":          food_benchmark(window_days),
        "work":          work_benchmark(window_days),
        "money":         money_benchmark(window_days),
        "habits":        habits_benchmark(window_days),
        "window_days":   window_days,
        "computed_at":   datetime.utcnow().isoformat(),
    }
