"""
src/analytics/ — PPT observability and pattern intelligence layer.

WHY this layer exists:
  Raw data tells you what happened.
  Analytics tells you what it MEANS.

  Collecting that you slept 6h is data.
  Knowing your personal average is 7.5h means 6h is anomalous.
  Knowing that on 6h nights you spend 45% more is a correlation.
  These insights are what make PPT genuinely intelligent — and what make
  the training data it exports actually useful for adapting an LLM to you.

MODULES:
  benchmarks   — your personal baselines ("what is normal for Rana")
  trends       — time-series helpers (7d / 30d / 90d windows)
  correlations — cross-domain pattern detection
  anomalies    — deviation from baseline, Z-score based

DATA FLOW:
  journal.store + notify.store
        ↓
  analytics.benchmarks  → personal_profile
        ↓
  analytics.correlations → insight_list
  analytics.anomalies   → anomaly_events
        ↓
  training.exporter     → JSONL fine-tuning dataset
  context.builder       → LLM context block
"""
from src.analytics import benchmarks, trends, correlations, anomalies

__all__ = ["benchmarks", "trends", "correlations", "anomalies"]
