"""
src/analytics/correlations.py — cross-domain pattern detection.

WHY correlations are the most valuable analytics:
  Individual metrics tell you what happened.
  Correlations tell you WHY.

  "You overspent on Tuesday" is data.
  "You overspent on Tuesday — and you slept 5h Monday night" is insight.
  "On every night you sleep under 6h, you spend 40% more the next day"
  is a pattern that can change behaviour.

HOW it works:
  We use Pearson correlation coefficient (r) — standard in statistics.
  r = +1.0  → perfect positive correlation (A goes up, B goes up)
  r = -1.0  → perfect negative correlation (A goes up, B goes down)
  r = 0.0   → no relationship

  We compute r for all meaningful cross-domain pairs, then filter to
  those with |r| >= 0.3 (weak-moderate signal or stronger).

PAIRS WE CHECK:
  sleep_hours   ↔ next_day_spend     (poor sleep → more spending?)
  sleep_hours   ↔ work_hours         (does long work = poor sleep?)
  sleep_quality ↔ habit_completion   (better sleep = better habit day?)
  work_hours    ↔ spend              (busy days = more or less spending?)
  calories      ↔ work_hours         (more work = more food?)
  mood_checkin  ↔ sleep_quality      (mood vs sleep relationship)

PLAIN ENGLISH:
  We translate each significant correlation into a human-readable sentence
  that goes into the training dataset.

  e.g. "On nights when you sleep less than your average, you tend to spend
       more money the following day (r=0.62, strong)."
"""
from __future__ import annotations
import logging
import math
import sqlite3
from datetime import date, timedelta
from pathlib import Path

log = logging.getLogger(__name__)

_JOURNAL_DB = Path(__file__).parent.parent.parent / "data" / "journal.db"
_NOTIFY_DB  = Path(__file__).parent.parent.parent / "data" / "notify.db"
_MIN_POINTS = 7   # Need at least 7 paired points for a correlation to be meaningful
_MIN_R      = 0.3  # Only report correlations with |r| >= 0.3


def _conn(db_path: Path) -> sqlite3.Connection | None:
    if not db_path.exists():
        return None
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    return con


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    """
    Pearson correlation coefficient between two equal-length lists.
    WHY Pearson? It measures linear relationship, which is the right
    question for "does X affect Y?" in daily life data.
    """
    n = len(xs)
    if n < _MIN_POINTS:
        return None
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    num   = sum((xs[i] - mean_x) * (ys[i] - mean_y) for i in range(n))
    den_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
    den_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))
    if den_x == 0 or den_y == 0:
        return None
    return round(num / (den_x * den_y), 3)


def _r_strength(r: float) -> str:
    """Translate r value to a plain-English strength label."""
    a = abs(r)
    if a >= 0.7: return "strong"
    if a >= 0.5: return "moderate"
    if a >= 0.3: return "weak"
    return "negligible"


def _r_direction(r: float) -> str:
    return "positive" if r > 0 else "negative"


# ── Data collectors ──────────────────────────────────────────────────────────

def _collect_sleep(days: int = 60) -> dict[str, tuple[float, float]]:
    """Return {date: (hours, quality)} for sleep logs."""
    con = _conn(_JOURNAL_DB)
    if not con:
        return {}
    start = (date.today() - timedelta(days=days)).isoformat()
    rows = con.execute("""
        SELECT date, duration_min, quality FROM sleep_logs WHERE date >= ?
    """, (start,)).fetchall()
    con.close()
    return {
        r["date"]: (r["duration_min"] / 60 if r["duration_min"] else 0,
                    r["quality"] or 0)
        for r in rows
    }


def _collect_work(days: int = 60) -> dict[str, float]:
    """Return {date: hours_worked}."""
    con = _conn(_JOURNAL_DB)
    if not con:
        return {}
    start = (date.today() - timedelta(days=days)).isoformat()
    rows = con.execute("""
        SELECT date, COALESCE(SUM(duration_min),0) as total
        FROM work_sessions WHERE date >= ? AND end_time IS NOT NULL GROUP BY date
    """, (start,)).fetchall()
    con.close()
    return {r["date"]: r["total"] / 60 for r in rows}


def _collect_spend(days: int = 60) -> dict[str, float]:
    """Return {date: total_spend}."""
    con = _conn(_JOURNAL_DB)
    if not con:
        return {}
    start = (date.today() - timedelta(days=days)).isoformat()
    rows = con.execute("""
        SELECT date, COALESCE(SUM(amount),0) as total
        FROM spending_logs WHERE date >= ? GROUP BY date
    """, (start,)).fetchall()
    con.close()
    return {r["date"]: r["total"] for r in rows}


def _collect_calories(days: int = 60) -> dict[str, float]:
    """Return {date: total_calories}."""
    con = _conn(_JOURNAL_DB)
    if not con:
        return {}
    start = (date.today() - timedelta(days=days)).isoformat()
    rows = con.execute("""
        SELECT date, COALESCE(SUM(calories),0) as cal
        FROM food_logs WHERE date >= ? GROUP BY date
    """, (start,)).fetchall()
    con.close()
    return {r["date"]: r["cal"] for r in rows if r["cal"] > 0}


def _collect_habit_completion(days: int = 60) -> dict[str, float]:
    """Return {date: completion_rate 0-1}."""
    con = _conn(_NOTIFY_DB)
    if not con:
        return {}
    total = con.execute("SELECT COUNT(*) as n FROM habits WHERE active=1").fetchone()["n"]
    if total == 0:
        con.close()
        return {}
    start = (date.today() - timedelta(days=days)).isoformat()
    rows = con.execute("""
        SELECT date, COUNT(DISTINCT habit_id) as done
        FROM habit_logs WHERE date >= ? GROUP BY date
    """, (start,)).fetchall()
    con.close()
    return {r["date"]: min(r["done"] / total, 1.0) for r in rows}


def _collect_mood(days: int = 60) -> dict[str, float]:
    """Return {date: mood 1-5} from notify check-ins."""
    con = _conn(_NOTIFY_DB)
    if not con:
        return {}
    start = (date.today() - timedelta(days=days)).isoformat()
    rows = con.execute("""
        SELECT date, mood FROM check_ins WHERE date >= ? AND mood IS NOT NULL
    """, (start,)).fetchall()
    con.close()
    return {r["date"]: r["mood"] for r in rows}


# ── Paired correlation helpers ────────────────────────────────────────────────

def _shift_dates(data: dict[str, float], days: int = 1) -> dict[str, float]:
    """
    Shift a date-keyed dict forward by N days.
    WHY? "Sleeping poorly tonight affects spending TOMORROW" — so we
    need to align sleep[date] with spend[date + 1].
    """
    result = {}
    for d, v in data.items():
        shifted = (date.fromisoformat(d) + timedelta(days=days)).isoformat()
        result[shifted] = v
    return result


def _paired(a: dict[str, float], b: dict[str, float]) -> tuple[list[float], list[float]]:
    """Return two aligned lists for dates present in both dicts."""
    common = sorted(set(a.keys()) & set(b.keys()))
    return [a[d] for d in common], [b[d] for d in common]


# ── Correlation analysis ─────────────────────────────────────────────────────

def compute_all(days: int = 60) -> list[dict]:
    """
    Compute all cross-domain correlations and return a list of findings.
    Only includes pairs with |r| >= _MIN_R and >= _MIN_POINTS data points.

    Returns a list of dicts:
    {
      "pair": "sleep_hours → next_day_spend",
      "r": 0.62,
      "strength": "moderate",
      "direction": "negative",   # more sleep = less spending
      "n": 34,                   # number of paired data points
      "insight": "On nights when you sleep less, you tend to spend more the next day.",
      "impact": "high"           # high | medium | low (based on |r|)
    }
    """
    sleep  = _collect_sleep(days)
    work   = _collect_work(days)
    spend  = _collect_spend(days)
    cals   = _collect_calories(days)
    habits = _collect_habit_completion(days)
    mood   = _collect_mood(days)

    sleep_hrs = {d: v[0] for d, v in sleep.items()}
    sleep_q   = {d: v[1] for d, v in sleep.items()}

    # Next-day versions (sleep tonight → effect tomorrow)
    sleep_hrs_next = _shift_dates(sleep_hrs, 1)
    sleep_q_next   = _shift_dates(sleep_q, 1)

    PAIRS = [
        # (label, dict_a, dict_b, insight_template)
        (
            "sleep_hours → next_day_spend",
            sleep_hrs_next, spend,
            lambda r: f"On nights when you sleep {'less' if r < 0 else 'more'}, "
                      f"you tend to spend {'more' if r < 0 else 'less'} money the following day.",
        ),
        (
            "work_hours → sleep_hours",
            work, sleep_hrs,
            lambda r: f"On days you work {'more' if r < 0 else 'fewer'} hours, "
                      f"you tend to sleep {'less' if r < 0 else 'more'} that night.",
        ),
        (
            "sleep_quality → habit_completion",
            sleep_q_next, habits,
            lambda r: f"After {'better' if r > 0 else 'worse'}-quality sleep nights, "
                      f"you tend to complete {'more' if r > 0 else 'fewer'} habits the next day.",
        ),
        (
            "work_hours → spend",
            work, spend,
            lambda r: f"On days you work {'more' if r > 0 else 'fewer'} hours, "
                      f"you tend to spend {'more' if r > 0 else 'less'}.",
        ),
        (
            "calories → work_hours",
            cals, work,
            lambda r: f"On days you eat {'more' if r > 0 else 'fewer'} calories, "
                      f"you tend to work {'more' if r > 0 else 'fewer'} hours.",
        ),
        (
            "mood → habit_completion",
            mood, habits,
            lambda r: f"On days you feel {'better' if r > 0 else 'worse'}, "
                      f"you tend to complete {'more' if r > 0 else 'fewer'} habits.",
        ),
        (
            "sleep_hours → work_hours",
            sleep_hrs_next, work,
            lambda r: f"After sleeping {'more' if r > 0 else 'less'}, "
                      f"you tend to work {'more' if r > 0 else 'fewer'} hours the next day.",
        ),
        (
            "mood → spend",
            mood, spend,
            lambda r: f"On {'better' if r < 0 else 'worse'}-mood days, "
                      f"you tend to spend {'less' if r < 0 else 'more'}.",
        ),
    ]

    results = []
    for label, a, b, insight_fn in PAIRS:
        xs, ys = _paired(a, b)
        r = _pearson(xs, ys)
        if r is None or abs(r) < _MIN_R:
            continue
        strength = _r_strength(r)
        results.append({
            "pair":      label,
            "r":         r,
            "strength":  strength,
            "direction": _r_direction(r),
            "n":         len(xs),
            "insight":   insight_fn(r),
            "impact":    "high" if abs(r) >= 0.5 else "medium" if abs(r) >= 0.4 else "low",
        })

    # Sort by |r| descending — strongest insights first
    results.sort(key=lambda x: abs(x["r"]), reverse=True)
    log.info("Found %d significant correlations (min %d points, |r| >= %.1f)",
             len(results), _MIN_POINTS, _MIN_R)
    return results


def top_insights(n: int = 5, days: int = 60) -> list[str]:
    """Return the top N correlation insights as plain English strings."""
    return [c["insight"] for c in compute_all(days)[:n]]
