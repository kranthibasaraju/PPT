"""
src/web/analytics_routes.py — PPT analytics and training dashboard.

WHY this page exists:
  Raw data is invisible to you until it's visualised.
  This dashboard makes your patterns, anomalies, and training readiness
  visible — so you understand what PPT knows about you, and can see the
  data flywheel turning: more tracking → richer patterns → better model.

TABS:
  Overview   — benchmarks, balance score, wow% changes
  Trends     — 30-day charts for all 4 domains
  Patterns   — correlation matrix + plain-English insights
  Anomalies  — recent deviations feed
  Training   — dataset readiness + export button

ROUTES:
  GET  /analytics/            → main tabbed dashboard
  POST /analytics/export      → generate + download JSONL training file
  GET  /analytics/api/context → raw JSON context block (for Ollama integration)
"""
from __future__ import annotations
import json
from datetime import date, timedelta
from flask import Blueprint, render_template_string, request, redirect, url_for, jsonify, send_file
from pathlib import Path

analytics_bp = Blueprint("analytics", __name__, url_prefix="/analytics")


# ── HTML template ─────────────────────────────────────────────────────────────

_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PPT Board — Analytics</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
     background:#0f0f0f;color:#e8e8e8;min-height:100vh;padding-bottom:60px}

header{background:#1a1a2e;padding:12px 18px;display:flex;align-items:center;
       justify-content:space-between;border-bottom:1px solid #2a2a4a;
       position:sticky;top:0;z-index:20}
header h1{font-size:1.1rem;font-weight:600;color:#34d399}
.nav-links{display:flex;gap:14px}
.nav-links a{font-size:0.78rem;color:#555;text-decoration:none}
.nav-links a:hover{color:#34d399}

.tabs{display:flex;background:#111;border-bottom:1px solid #222;
      position:sticky;top:49px;z-index:15;overflow-x:auto}
.tab{flex:1;min-width:68px;padding:11px 4px;text-align:center;
     font-size:0.7rem;color:#555;cursor:pointer;
     border-bottom:2px solid transparent;transition:all .2s;white-space:nowrap}
.tab.active{color:#34d399;border-bottom-color:#34d399}
.tab-icon{font-size:1.05rem;display:block;margin-bottom:2px}

.panel{display:none;padding:14px;max-width:680px;margin:0 auto}
.panel.active{display:block}

.card{background:#1e1e2e;border-radius:12px;padding:14px 16px;
      margin-bottom:10px;border:1px solid #2a2a4a}
.section{font-size:0.68rem;font-weight:600;color:#444;text-transform:uppercase;
         letter-spacing:.06em;margin:16px 0 7px}

/* Benchmark grid */
.bench-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.bench-item{background:#181828;border-radius:10px;padding:12px}
.bench-val{font-size:1.3rem;font-weight:700;color:#34d399}
.bench-lbl{font-size:0.68rem;color:#555;margin-top:2px}
.bench-std{font-size:0.7rem;color:#444;margin-top:3px}

/* WoW badges */
.wow{display:inline-block;font-size:0.7rem;font-weight:600;padding:2px 7px;
     border-radius:10px;margin-left:6px}
.wow-up{background:#1a2a1a;color:#4ade80}
.wow-dn{background:#2a1a1a;color:#f87171}
.wow-nc{background:#222;color:#666}

/* Charts (CSS bar charts) */
.chart-wrap{overflow-x:auto}
.bar-chart{display:flex;align-items:flex-end;gap:3px;height:80px;
           padding:0 2px;min-width:300px}
.bar-col{flex:1;display:flex;flex-direction:column;align-items:center;gap:2px;min-width:12px}
.bar{width:100%;border-radius:3px 3px 0 0;transition:height .3s}
.bar-lbl{font-size:0.55rem;color:#444;white-space:nowrap}
.bar-val{font-size:0.55rem;color:#666;white-space:nowrap}
.ma-line{border-top:2px dashed #34d399;opacity:0.5;position:absolute}
.legend{display:flex;gap:12px;margin-top:6px;font-size:0.68rem;color:#555}
.legend span{display:flex;align-items:center;gap:4px}

/* Correlation matrix */
.corr-row{display:flex;align-items:center;gap:10px;padding:8px 0;
          border-bottom:1px solid #1a1a2a}
.corr-row:last-child{border-bottom:none}
.corr-pair{font-size:0.75rem;color:#888;flex:1;font-family:monospace}
.corr-bar-wrap{width:80px;height:6px;background:#252540;border-radius:10px;overflow:hidden;flex-shrink:0}
.corr-bar{height:100%;border-radius:10px}
.corr-pos{background:#34d399}
.corr-neg{background:#f87171}
.corr-r{font-size:0.72rem;font-weight:600;width:40px;text-align:right;flex-shrink:0}
.insight-card{background:#181828;border:1px solid #252540;border-radius:10px;
              padding:10px 12px;margin-bottom:8px}
.insight-text{font-size:0.82rem;color:#c8d0ff;line-height:1.4}
.impact-badge{font-size:0.62rem;padding:2px 6px;border-radius:8px;
              float:right;margin-left:6px}
.imp-high{background:#1a2a1a;color:#4ade80}
.imp-med{background:#2a2a1a;color:#fbbf24}
.imp-low{background:#222;color:#666}

/* Anomaly feed */
.anomaly{display:flex;align-items:flex-start;gap:10px;padding:10px 0;
         border-bottom:1px solid #1a1a2a}
.anomaly:last-child{border-bottom:none}
.anom-icon{font-size:1.1rem;flex-shrink:0;margin-top:1px}
.anom-msg{font-size:0.82rem;color:#c8d0ff;line-height:1.4}
.anom-date{font-size:0.68rem;color:#444;margin-top:3px}
.sev-extreme{color:#f87171}
.sev-significant{color:#fbbf24}
.sev-notable{color:#888}

/* Training panel */
.training-card{background:linear-gradient(135deg,#1a2a1a 0%,#1e1e2e 100%);
               border:1px solid #2d4a2d;border-radius:14px;padding:18px}
.training-title{font-size:1rem;font-weight:600;color:#4ade80;margin-bottom:4px}
.training-sub{font-size:0.78rem;color:#666;margin-bottom:14px;line-height:1.5}
.readiness-grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-bottom:14px}
.ready-item{background:#0f1f0f;border-radius:8px;padding:10px;text-align:center}
.ready-val{font-size:1.2rem;font-weight:700;color:#4ade80}
.ready-lbl{font-size:0.62rem;color:#444;margin-top:2px}
.btn{border:none;border-radius:8px;padding:10px 18px;font-size:0.85rem;
     cursor:pointer;font-weight:500;transition:opacity .15s}
.btn:active{opacity:.75}
.btn-export{background:#34d399;color:#0f1f0f;width:100%;margin-bottom:8px}
.btn-ctx{background:#252540;color:#aaa;width:100%}
.note-box{background:#0f0f0f;border:1px solid #252540;border-radius:8px;
          padding:10px;font-size:0.75rem;color:#666;margin-top:8px;line-height:1.5}
.format-tag{background:#1a2a3a;color:#7c83ff;border-radius:4px;padding:1px 5px;
            font-family:monospace;font-size:0.72rem}

.empty{text-align:center;padding:20px;color:#333;font-size:0.85rem}
</style>
</head>
<body>

<header>
  <h1>⚡ PPT Board · Analytics</h1>
  <div class="nav-links">
    <a href="/board">📊 Dashboard</a>
    <a href="/">📋 Planner</a>
    <a href="/notify">🔔 Notify</a>
    <a href="/journal">📓 Journal</a>
    <a href="/analytics">📊 Analytics</a>
  </div>
</header>

<div class="tabs">
  <div class="tab active" onclick="showTab('overview')">
    <span class="tab-icon">🎯</span>Overview
  </div>
  <div class="tab" onclick="showTab('trends')">
    <span class="tab-icon">📈</span>Trends
  </div>
  <div class="tab" onclick="showTab('patterns')">
    <span class="tab-icon">🔗</span>Patterns
  </div>
  <div class="tab" onclick="showTab('anomalies')">
    <span class="tab-icon">⚡</span>Anomalies
  </div>
  <div class="tab" onclick="showTab('training')">
    <span class="tab-icon">🧠</span>Training
  </div>
</div>

<!-- ═══════════════ OVERVIEW ═══════════════ -->
<div class="panel active" id="panel-overview">
  <div style="margin-top:14px"></div>

  <div class="section">30-Day Personal Benchmarks</div>
  <div class="bench-grid">
    <!-- Sleep -->
    <div class="bench-item">
      <div class="bench-val">
        {{ bench.sleep.avg_hours or '—' }}h
        {% if trends.sleep.wow is not none %}
        <span class="wow {{ 'wow-up' if trends.sleep.wow > 0 else ('wow-dn' if trends.sleep.wow < 0 else 'wow-nc') }}">
          {{ '+' if trends.sleep.wow > 0 else '' }}{{ trends.sleep.wow }}% WoW
        </span>
        {% endif %}
      </div>
      <div class="bench-lbl">💤 Avg sleep/night</div>
      {% if bench.sleep.std_hours %}
      <div class="bench-std">±{{ bench.sleep.std_hours }}h variance</div>
      {% endif %}
    </div>
    <!-- Work -->
    <div class="bench-item">
      <div class="bench-val">
        {{ bench.work.avg_hours or '—' }}h
        {% if trends.work.wow is not none %}
        <span class="wow {{ 'wow-up' if trends.work.wow > 0 else ('wow-dn' if trends.work.wow < 0 else 'wow-nc') }}">
          {{ '+' if trends.work.wow > 0 else '' }}{{ trends.work.wow }}% WoW
        </span>
        {% endif %}
      </div>
      <div class="bench-lbl">💼 Avg work/day</div>
      {% if bench.work.typical_start %}
      <div class="bench-std">Typically starts {{ bench.work.typical_start }}</div>
      {% endif %}
    </div>
    <!-- Food -->
    <div class="bench-item">
      <div class="bench-val">
        {{ bench.food.avg_calories | int if bench.food.avg_calories else '—' }}
        {% if trends.food.wow is not none %}
        <span class="wow {{ 'wow-dn' if trends.food.wow > 10 else ('wow-up' if trends.food.wow < -10 else 'wow-nc') }}">
          {{ '+' if trends.food.wow > 0 else '' }}{{ trends.food.wow }}% WoW
        </span>
        {% endif %}
      </div>
      <div class="bench-lbl">🍽 Avg cal/day</div>
    </div>
    <!-- Spend -->
    <div class="bench-item">
      <div class="bench-val">
        ${{ "%.0f"|format(bench.money.avg_daily_spend) if bench.money.avg_daily_spend else '—' }}
        {% if trends.money.wow is not none %}
        <span class="wow {{ 'wow-dn' if trends.money.wow > 10 else ('wow-up' if trends.money.wow < -10 else 'wow-nc') }}">
          {{ '+' if trends.money.wow > 0 else '' }}{{ trends.money.wow }}% WoW
        </span>
        {% endif %}
      </div>
      <div class="bench-lbl">💰 Avg spend/day</div>
    </div>
  </div>

  <!-- Habit & sleep quality -->
  <div class="section">Behaviour Benchmarks</div>
  <div class="bench-grid">
    <div class="bench-item">
      <div class="bench-val">{{ (bench.habits.avg_completion_rate * 100) | int if bench.habits.avg_completion_rate else '—' }}%</div>
      <div class="bench-lbl">🔔 Habit completion</div>
      {% if bench.habits.strongest_streak %}
      <div class="bench-std">Best streak: {{ bench.habits.strongest_streak.name }} · {{ bench.habits.strongest_streak.streak }}d</div>
      {% endif %}
    </div>
    <div class="bench-item">
      <div class="bench-val">{{ bench.sleep.avg_quality or '—' }}/5</div>
      <div class="bench-lbl">😴 Avg sleep quality</div>
      {% if bench.sleep.typical_bedtime %}
      <div class="bench-std">Bedtime: {{ bench.sleep.typical_bedtime }}</div>
      {% endif %}
    </div>
  </div>

  <!-- Top insight preview -->
  {% if correlations %}
  <div class="section">Top Pattern This Month</div>
  <div class="insight-card">
    <span class="impact-badge imp-{{ correlations[0].impact }}">{{ correlations[0].impact }} impact</span>
    <div class="insight-text">{{ correlations[0].insight }}</div>
    <div style="font-size:0.68rem;color:#444;margin-top:6px">r = {{ correlations[0].r }} ({{ correlations[0].strength }})</div>
  </div>
  {% endif %}
</div>

<!-- ═══════════════ TRENDS ═══════════════ -->
<div class="panel" id="panel-trends">
  {% macro bar_chart(values, dates, color, label, fmt='') %}
  <div class="section">{{ label }}</div>
  <div class="card">
    <div class="chart-wrap">
      <div class="bar-chart">
        {% set valid = values | select('ne', none) | list %}
        {% set max_v = valid | max if valid else 1 %}
        {% for i in range(values | length) %}
        {% set v = values[i] %}
        {% set pct = ((v / max_v * 100) | int) if v else 0 %}
        <div class="bar-col">
          <div class="bar" style="height:{{ pct }}%;background:{{ color }};opacity:{% if v %}0.85{% else %}0.15{% endif %};min-height:3px"></div>
          <div class="bar-lbl">{{ dates[i][-5:] if loop.index % 5 == 0 else '' }}</div>
        </div>
        {% endfor %}
      </div>
    </div>
    {% if valid %}
    <div class="legend">
      <span><span style="color:{{ color }}">■</span> {{ label }}</span>
    </div>
    {% else %}
    <div class="empty">No data in this period yet</div>
    {% endif %}
  </div>
  {% endmacro %}

  {{ bar_chart(trends.sleep.hours,   trends.sleep.dates,   '#a78bfa', '💤 Sleep (hours/night)') }}
  {{ bar_chart(trends.work.hours,    trends.work.dates,    '#7c83ff', '💼 Work (hours/day)') }}
  {{ bar_chart(trends.food.calories, trends.food.dates,    '#34d399', '🍽 Food (calories/day)') }}
  {{ bar_chart(trends.money.spend,   trends.money.dates,   '#f59e0b', '💰 Spending ($/day)') }}
  {{ bar_chart(trends.habits.rates,  trends.habits.dates,  '#c084fc', '🔔 Habit completion rate') }}
</div>

<!-- ═══════════════ PATTERNS ═══════════════ -->
<div class="panel" id="panel-patterns">
  <div style="margin-top:14px"></div>

  {% if correlations %}
  <div class="section">Cross-Domain Correlations</div>
  <div class="card">
    {% for c in correlations %}
    <div class="corr-row">
      <div style="flex:1">
        <div class="corr-pair">{{ c.pair }}</div>
        <div style="font-size:0.72rem;color:#888;margin-top:2px">{{ c.insight }}</div>
      </div>
      <div style="display:flex;align-items:center;gap:8px;flex-shrink:0">
        <div class="corr-bar-wrap">
          <div class="corr-bar {{ 'corr-pos' if c.r > 0 else 'corr-neg' }}"
               style="width:{{ (c.r | abs * 100) | int }}%"></div>
        </div>
        <div class="corr-r" style="color:{{ '#4ade80' if c.r > 0 else '#f87171' }}">
          r={{ c.r }}
        </div>
      </div>
    </div>
    {% endfor %}
  </div>

  <div class="section">Plain-English Insights</div>
  {% for c in correlations %}
  <div class="insight-card">
    <span class="impact-badge imp-{{ c.impact }}">{{ c.impact }}</span>
    <div class="insight-text">{{ c.insight }}</div>
    <div style="font-size:0.65rem;color:#444;margin-top:5px">
      Based on {{ c.n }} data points  ·  {{ c.strength }} correlation (r={{ c.r }})
    </div>
  </div>
  {% endfor %}
  {% else %}
  <div class="empty" style="margin-top:20px">
    <span style="font-size:2rem;display:block;margin-bottom:8px">🔗</span>
    No significant patterns yet.<br>
    Keep tracking for 2+ weeks — patterns emerge with more data.
  </div>
  {% endif %}
</div>

<!-- ═══════════════ ANOMALIES ═══════════════ -->
<div class="panel" id="panel-anomalies">
  <div style="margin-top:14px"></div>

  {% if anomalies %}
  <div class="section">Recent Anomalies (7 days)</div>
  <div class="card">
    {% for a in anomalies %}
    <div class="anomaly">
      <div class="anom-icon">
        {{ '💤' if a.domain == 'sleep' else '🍽' if a.domain == 'food' else '💼' if a.domain == 'work' else '💰' }}
      </div>
      <div>
        <div class="anom-msg">
          <span class="sev-{{ a.severity }}">{{ a.severity | upper }}</span> ·
          {{ a.message }}
        </div>
        <div class="anom-date">{{ a.date }}  ·  Z={{ a.z_score }}</div>
      </div>
    </div>
    {% endfor %}
  </div>

  <div class="note-box" style="margin-top:8px">
    <strong>What is a Z-score?</strong> It measures how many standard deviations
    a value is from your personal average. |Z| ≥ 1.5 = notable · |Z| ≥ 2 = significant · |Z| ≥ 3 = extreme.
    All thresholds are calculated from YOUR data, not generic targets.
  </div>
  {% else %}
  <div class="empty" style="margin-top:20px">
    <span style="font-size:2rem;display:block;margin-bottom:8px">✅</span>
    No anomalies in the last 7 days.<br>
    Everything is within your personal normal range.
  </div>
  {% endif %}
</div>

<!-- ═══════════════ TRAINING ═══════════════ -->
<div class="panel" id="panel-training">
  <div style="margin-top:14px"></div>

  <div class="training-card">
    <div class="training-title">🧠 LLM Fine-Tuning Dataset</div>
    <div class="training-sub">
      PPT converts your life data into structured <span class="format-tag">JSONL</span>
      training examples — facts about you, contextual Q&A, pattern explanations, and
      coaching conversations. Fine-tune any local model (Ollama, Mistral) to know
      your patterns and adapt to you personally.
    </div>

    <!-- Readiness metrics -->
    <div class="readiness-grid">
      <div class="ready-item">
        <div class="ready-val">~{{ training_meta.estimated_examples }}</div>
        <div class="ready-lbl">Examples ready</div>
      </div>
      <div class="ready-item">
        <div class="ready-val">{{ training_meta.data_richness.sleep_days }}</div>
        <div class="ready-lbl">Sleep nights</div>
      </div>
      <div class="ready-item">
        <div class="ready-val">{{ training_meta.data_richness.correlations }}</div>
        <div class="ready-lbl">Correlations</div>
      </div>
    </div>

    <!-- Richness detail -->
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:14px">
      {% for key, val in training_meta.data_richness.items() %}
      <div style="background:#0f1f0f;border-radius:6px;padding:6px 10px;
                  display:flex;justify-content:space-between;font-size:0.72rem">
        <span style="color:#555">{{ key.replace('_', ' ') }}</span>
        <span style="color:#4ade80;font-weight:600">{{ val }}</span>
      </div>
      {% endfor %}
    </div>

    <div class="note-box" style="margin-bottom:12px">
      {{ training_meta.note }}
    </div>

    <form method="POST" action="/analytics/export">
      <button class="btn btn-export" type="submit"
              {% if not training_meta.ready %}disabled{% endif %}>
        ⬇ Export Training Data (.jsonl)
      </button>
    </form>

    <a href="/analytics/api/context" target="_blank">
      <button class="btn btn-ctx" type="button">🔍 View Raw Context JSON</button>
    </a>
  </div>

  <!-- Training data format explanation -->
  <div class="section">What gets exported</div>
  <div class="card">
    {% for type_name, desc in training_types %}
    <div style="padding:8px 0;border-bottom:1px solid #1a1a2a">
      <div style="font-size:0.82rem;font-weight:500;color:#c8d0ff">{{ type_name }}</div>
      <div style="font-size:0.72rem;color:#555;margin-top:3px">{{ desc }}</div>
    </div>
    {% endfor %}
  </div>

  <!-- Ollama integration note -->
  <div class="section">How to use with Ollama</div>
  <div class="note-box">
    1. Export the JSONL file<br>
    2. Create a Modelfile referencing your base model + the JSONL<br>
    3. Run: <span class="format-tag">ollama create ppt-personal -f Modelfile</span><br>
    4. Use: <span class="format-tag">ollama run ppt-personal</span><br><br>
    The more data you track, the better the model knows you.
    Re-export monthly for fresh training data.
  </div>
</div>

<script>
function showTab(name) {
  const names = ['overview','trends','patterns','anomalies','training'];
  document.querySelectorAll('.tab').forEach((t, i) =>
    t.classList.toggle('active', names[i] === name));
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.getElementById('panel-' + name).classList.add('active');
  localStorage.setItem('analytics_tab', name);
}
const saved = localStorage.getItem('analytics_tab');
if (saved) showTab(saved);
</script>
</body>
</html>"""


# ── Context builder ────────────────────────────────────────────────────────────

def _build_ctx():
    try:
        from src.context.builder import build_dict
        return build_dict()
    except Exception:
        return {}


# ── Routes ────────────────────────────────────────────────────────────────────

@analytics_bp.route("/")
def index():
    ctx = _build_ctx()

    # Benchmarks
    try:
        from src.analytics.benchmarks import full_benchmark
        bench = full_benchmark(30)
    except Exception:
        bench = {"sleep": {}, "food": {}, "work": {}, "money": {}, "habits": {}}

    # Trends (30 days)
    try:
        from src.analytics.trends import summary
        trends = summary(30)
    except Exception:
        trends = {"sleep": {}, "food": {}, "work": {}, "money": {}, "habits": {}}

    # Correlations
    try:
        from src.analytics.correlations import compute_all
        correlations = compute_all(60)
    except Exception:
        correlations = []

    # Anomalies (last 7 days)
    try:
        from src.analytics.anomalies import detect_window
        anomalies = detect_window(7)
    except Exception:
        anomalies = []

    # Training metadata
    try:
        from src.training.exporter import export_metadata
        training_meta = export_metadata(ctx)
    except Exception:
        training_meta = {"estimated_examples": 0, "data_richness": {}, "ready": False,
                         "note": "Data unavailable"}

    training_types = [
        ("Personal Facts", "Q&A about your sleep, work, food, and spending patterns based on 30-day averages."),
        ("Contextual Q&A", "Questions answered using today's real snapshot — what you did, how it compares."),
        ("Pattern Explanations", "Natural language explanations of your correlations (e.g. sleep → spending)."),
        ("Habit & Goal Coaching", "Personalised coaching conversations about your specific habits and goals."),
        ("Anomaly Explanations", "Training examples for explaining unusual days in your data."),
        ("Trend Reflections", "Week-over-week comparisons in natural language."),
    ]

    return render_template_string(
        _HTML,
        bench=bench,
        trends=trends,
        correlations=correlations,
        anomalies=anomalies,
        training_meta=training_meta,
        training_types=training_types,
    )


@analytics_bp.route("/export", methods=["POST"])
def export():
    """Generate JSONL training file and serve it as a download."""
    try:
        from src.training.exporter import export_to_file
        path = export_to_file()
        return send_file(str(path), as_attachment=True,
                         download_name=path.name, mimetype="application/jsonl")
    except Exception as e:
        return f"Export failed: {e}", 500


@analytics_bp.route("/api/context")
def api_context():
    """Raw JSON context block — pipe this into Ollama or any LLM."""
    ctx = _build_ctx()
    try:
        from src.context.builder import build_context
        ctx["context_string"] = build_context(ctx)
    except Exception:
        pass
    # Remove internal keys before sending
    ctx.pop("_benchmarks_full", None)
    return jsonify(ctx)
