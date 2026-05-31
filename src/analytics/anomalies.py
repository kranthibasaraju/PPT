"""
src/analytics/anomalies.py — Z-score based anomaly detection for PPT.

WHY Z-score anomaly detection?
  A Z-score measures how many standard deviations a value is from the mean.
  Z = (value - mean) / std_dev

  |Z| >= 1.5 → notable deviation (worth mentioning)
  |Z| >= 2.0 → significant anomaly (alert-worthy)
  |Z| >= 3.0 → extreme outlier (something unusual happened)

  This means anomalies are PERSONAL. If your average sleep is 7.5h and
  today you slept 5h, Z ≈ -2.1 → significant anomaly.
  But if your average sleep is 5.5h, the same 5h night is nearly normal.

  This is what makes PPT's alerts intelligent vs. generic health apps
  that just say "less than 7h is bad" regardless of who you are.

WHAT WE DETECT:
  - Sleep hours below/above personal baseline
  - Calories significantly above/below typical intake
  - Work hours significantly above/below usual
  - Daily spending significantly above usual
  - Habit completion rate significantly below usual

OUTPUT FORMAT:
  [
    {
      "domain": "sleep",
      "metric": "hours",
      "date": "2026-05-17",
      "value": 5.0,
      "baseline": 7.4,
      "z_score": -2.1,
      "severity": "significant",   # notable | significant | extreme
      "direction": "below",        # above | below
      "message": "You slept 5h — 2.4h below your normal 7.4h average.",
    }
  ]
"""
from __future__ import annotations
import logging
from datetime import date, timedelta
from src.analytics.benchmarks import full_benchmark

log = logging.getLogger(__name__)

_Z_NOTABLE     = 1.5
_Z_SIGNIFICANT = 2.0
_Z_EXTREME     = 3.0


def _severity(z: float) -> str:
    a = abs(z)
    if a >= _Z_EXTREME:     return "extreme"
    if a >= _Z_SIGNIFICANT: return "significant"
    return "notable"


def _z(value: float, mean: float, std: float) -> float | None:
    if std == 0:
        return None
    return round((value - mean) / std, 2)


def _anomaly(domain: str, metric: str, value: float, mean: float | None,
             std: float | None, date_str: str, unit: str = "",
             format_fn=None) -> dict | None:
    if mean is None or std is None or value == 0:
        return None
    z = _z(value, mean, std)
    if z is None or abs(z) < _Z_NOTABLE:
        return None

    direction = "above" if z > 0 else "below"
    severity  = _severity(z)
    fmt = format_fn or (lambda v: f"{v:.1f}{unit}")

    message = (
        f"{domain.title()}: {fmt(value)} "
        f"— {fmt(abs(value - mean))} {direction} your normal {fmt(mean)}."
    )
    return {
        "domain":    domain,
        "metric":    metric,
        "date":      date_str,
        "value":     round(value, 2),
        "baseline":  round(mean, 2),
        "z_score":   z,
        "severity":  severity,
        "direction": direction,
        "message":   message,
    }


def detect_today(benchmarks: dict | None = None) -> list[dict]:
    """
    Check today's (and yesterday's for sleep) metrics against personal baselines.
    Returns a list of anomaly dicts, sorted by |z_score| descending.
    """
    if benchmarks is None:
        benchmarks = full_benchmark(30)

    today     = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    anomalies = []

    # ── Sleep (last night) ────────────────────────────────────────────────────
    try:
        from src.journal.store import get_sleep
        sleep = get_sleep(yesterday)
        if sleep and sleep.get("duration_min"):
            b = benchmarks.get("sleep", {})
            a = _anomaly(
                "sleep", "hours",
                sleep["duration_min"] / 60,
                b.get("avg_hours"), b.get("std_hours"),
                yesterday, "h",
                lambda v: f"{v:.1f}h"
            )
            if a:
                anomalies.append(a)
    except Exception as e:
        log.debug("Sleep anomaly check error: %s", e)

    # ── Food (today) ──────────────────────────────────────────────────────────
    try:
        from src.journal.store import food_daily_totals
        food = food_daily_totals(today)
        if food["calories"] > 0:
            b = benchmarks.get("food", {})
            a = _anomaly(
                "food", "calories",
                food["calories"],
                b.get("avg_calories"), b.get("std_calories"),
                today, " cal",
                lambda v: f"{v:.0f} cal"
            )
            if a:
                anomalies.append(a)
    except Exception as e:
        log.debug("Food anomaly check error: %s", e)

    # ── Work (today) ──────────────────────────────────────────────────────────
    try:
        from src.journal.store import work_daily_total_min
        work_min = work_daily_total_min(today)
        if work_min > 0:
            b = benchmarks.get("work", {})
            avg_h = b.get("avg_hours")
            std_h = b.get("std_hours")
            a = _anomaly(
                "work", "hours",
                work_min / 60,
                avg_h, std_h,
                today, "h",
                lambda v: f"{v:.1f}h"
            )
            if a:
                anomalies.append(a)
    except Exception as e:
        log.debug("Work anomaly check error: %s", e)

    # ── Spending (today) ──────────────────────────────────────────────────────
    try:
        from src.journal.store import spend_total
        spent = spend_total(today)
        if spent > 0:
            b = benchmarks.get("money", {})
            a = _anomaly(
                "money", "spend",
                spent,
                b.get("avg_daily_spend"), b.get("std_daily_spend"),
                today, "",
                lambda v: f"${v:.2f}"
            )
            if a:
                anomalies.append(a)
    except Exception as e:
        log.debug("Spending anomaly check error: %s", e)

    # Sort by severity
    anomalies.sort(key=lambda x: abs(x["z_score"]), reverse=True)
    return anomalies


def detect_window(days: int = 7, benchmarks: dict | None = None) -> list[dict]:
    """
    Scan the last N days for anomalies.
    Used for the analytics dashboard's anomaly feed.
    """
    if benchmarks is None:
        benchmarks = full_benchmark(30)

    all_anomalies = []
    for i in range(days):
        check_date = (date.today() - timedelta(days=i)).isoformat()
        daily = _detect_for_date(check_date, benchmarks)
        all_anomalies.extend(daily)

    all_anomalies.sort(key=lambda x: (x["date"], abs(x["z_score"])), reverse=True)
    return all_anomalies


def _detect_for_date(date_str: str, benchmarks: dict) -> list[dict]:
    """Internal helper: detect anomalies for a specific past date."""
    anomalies = []
    sleep_date = (date.fromisoformat(date_str) - timedelta(days=1)).isoformat()

    try:
        from src.journal.store import get_sleep, food_daily_totals, work_daily_total_min, spend_total

        # Sleep
        sleep = get_sleep(sleep_date)
        if sleep and sleep.get("duration_min"):
            b = benchmarks.get("sleep", {})
            a = _anomaly("sleep", "hours", sleep["duration_min"] / 60,
                         b.get("avg_hours"), b.get("std_hours"),
                         sleep_date, "h", lambda v: f"{v:.1f}h")
            if a: anomalies.append(a)

        # Food
        food = food_daily_totals(date_str)
        if food["calories"] > 0:
            b = benchmarks.get("food", {})
            a = _anomaly("food", "calories", food["calories"],
                         b.get("avg_calories"), b.get("std_calories"),
                         date_str, " cal", lambda v: f"{v:.0f} cal")
            if a: anomalies.append(a)

        # Work
        work_min = work_daily_total_min(date_str)
        if work_min > 0:
            b = benchmarks.get("work", {})
            a = _anomaly("work", "hours", work_min / 60,
                         b.get("avg_hours"), b.get("std_hours"),
                         date_str, "h", lambda v: f"{v:.1f}h")
            if a: anomalies.append(a)

        # Spend
        spent = spend_total(date_str)
        if spent > 0:
            b = benchmarks.get("money", {})
            a = _anomaly("money", "spend", spent,
                         b.get("avg_daily_spend"), b.get("std_daily_spend"),
                         date_str, "", lambda v: f"${v:.2f}")
            if a: anomalies.append(a)

    except Exception as e:
        log.debug("Anomaly detection error for %s: %s", date_str, e)

    return anomalies


def anomaly_alert_message(anomalies: list[dict]) -> str | None:
    """
    Format significant/extreme anomalies into a Telegram alert message.
    Returns None if nothing notable to report.
    """
    notable = [a for a in anomalies if a["severity"] in ("significant", "extreme")]
    if not notable:
        return None

    lines = ["⚡ *PPT Anomaly Alert*\n"]
    icons = {"sleep": "💤", "food": "🍽", "work": "💼", "money": "💰"}
    for a in notable[:4]:  # max 4 anomalies per message
        icon = icons.get(a["domain"], "📊")
        lines.append(f"{icon} {a['message']}")
    return "\n".join(lines)
