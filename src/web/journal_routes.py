"""
src/web/journal_routes.py — Flask Blueprint for the PPT journal dashboard.

WHY a tab-based single page?
  Mobile-first: one URL, JavaScript switches tabs without page reloads.
  Each tab = one life domain.  The "Today" tab = the overview digest.

TABS:
  Today   — balance score, yesterday summary, today's schedule
  Food    — log meals, daily totals, weekly calorie chart
  Sleep   — log sleep, 7-night history, quality trends
  Work    — clock in/out, today's sessions, weekly hours
  Money   — log spending, category breakdown, budget gauge

ROUTES:
  GET  /journal/          → main tabbed page
  POST /journal/food/add  → log a meal
  POST /journal/food/del  → delete a food log
  POST /journal/sleep     → log last night's sleep
  POST /journal/work/in   → clock in
  POST /journal/work/out  → clock out
  POST /journal/spend/add → log a purchase
  POST /journal/spend/del → delete a purchase
  POST /journal/budget    → set weekly budget
  GET  /journal/api/today → JSON snapshot for watch/IoT
"""
from __future__ import annotations
from datetime import date, timedelta
from flask import Blueprint, render_template_string, request, redirect, url_for, jsonify
from src.journal import store
from src.journal.alerts import work_life_score

journal_bp = Blueprint("journal", __name__, url_prefix="/journal")
store.init_db()


# ═══════════════════════════════════════════════════════════════════════════════
# HTML template
# ═══════════════════════════════════════════════════════════════════════════════

_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PPT Board — Journal</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
     background:#0f0f0f;color:#e8e8e8;min-height:100vh;padding-bottom:80px}

/* Header */
header{background:#1a1a2e;padding:12px 18px;display:flex;align-items:center;
       justify-content:space-between;border-bottom:1px solid #2a2a4a;
       position:sticky;top:0;z-index:20}
header h1{font-size:1.1rem;font-weight:600;color:#c084fc}
.nav-links{display:flex;gap:14px}
.nav-links a{font-size:0.78rem;color:#555;text-decoration:none}
.nav-links a:hover{color:#c084fc}

/* Tab bar */
.tabs{display:flex;background:#111;border-bottom:1px solid #222;
      position:sticky;top:49px;z-index:15;overflow-x:auto}
.tab{flex:1;min-width:60px;padding:11px 4px;text-align:center;
     font-size:0.72rem;color:#555;cursor:pointer;border-bottom:2px solid transparent;
     transition:all 0.2s;white-space:nowrap}
.tab.active{color:#c084fc;border-bottom-color:#c084fc}
.tab-icon{font-size:1.1rem;display:block;margin-bottom:2px}

/* Panels */
.panel{display:none;padding:14px;max-width:640px;margin:0 auto}
.panel.active{display:block}

/* Cards */
.card{background:#1e1e2e;border-radius:12px;padding:14px 16px;
      margin-bottom:10px;border:1px solid #2a2a4a}
.card-title{font-size:0.95rem;font-weight:500;color:#c8d0ff;margin-bottom:4px}
.card-sub{font-size:0.78rem;color:#666}
.section{font-size:0.7rem;font-weight:600;color:#555;text-transform:uppercase;
         letter-spacing:.06em;margin:16px 0 7px}

/* Score ring */
.score-wrap{display:flex;align-items:center;gap:16px;padding:4px 0}
.score-ring{width:72px;height:72px;flex-shrink:0}
.score-ring svg{transform:rotate(-90deg)}
.score-ring circle{fill:none;stroke-width:8}
.ring-bg{stroke:#2a2a3a}
.ring-fill{stroke:#c084fc;stroke-linecap:round;transition:stroke-dashoffset .4s}
.score-num{font-size:1.5rem;font-weight:700;color:#c084fc;text-anchor:middle;dominant-baseline:central}
.score-info{flex:1}
.score-label{font-size:1rem;font-weight:600;color:#e8e8e8}
.score-sub{font-size:0.78rem;color:#666;margin-top:3px}

/* Stat row */
.stats{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:10px}
.stat{background:#181828;border-radius:10px;padding:12px;text-align:center}
.stat-val{font-size:1.2rem;font-weight:700;color:#c8d0ff}
.stat-lbl{font-size:0.68rem;color:#666;margin-top:2px}

/* Food items */
.meal-row{display:flex;align-items:center;gap:8px;padding:8px 0;
          border-bottom:1px solid #222}
.meal-row:last-child{border-bottom:none}
.meal-type{font-size:0.65rem;background:#252540;color:#888;padding:2px 7px;
           border-radius:10px;text-transform:capitalize;flex-shrink:0}
.meal-name{flex:1;font-size:0.88rem}
.meal-cal{font-size:0.78rem;color:#888}
.del-btn{background:none;border:none;color:#3a2a2a;cursor:pointer;font-size:1rem;padding:2px 6px}
.del-btn:hover{color:#f87171}

/* Sleep chart */
.sleep-bars{display:flex;align-items:flex-end;gap:5px;height:70px;margin:10px 0}
.sleep-bar-wrap{flex:1;display:flex;flex-direction:column;align-items:center;gap:3px}
.sleep-bar{width:100%;background:#252540;border-radius:4px 4px 0 0;min-height:3px;
           transition:height .3s;position:relative}
.sleep-bar.good{background:#c084fc}
.sleep-bar.ok{background:#7c83ff}
.sleep-bar.bad{background:#f87171}
.bar-day{font-size:0.6rem;color:#555}

/* Work session */
.session{display:flex;align-items:center;gap:10px;padding:8px 0;
         border-bottom:1px solid #222}
.session:last-child{border-bottom:none}
.session-time{font-size:0.72rem;color:#888;white-space:nowrap;min-width:80px}
.session-task{flex:1;font-size:0.88rem}
.session-dur{font-size:0.75rem;color:#c084fc;white-space:nowrap}
.live-badge{font-size:0.65rem;background:#1a2a1a;color:#4ade80;border:1px solid #2d4a2d;
            border-radius:10px;padding:2px 7px;animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.5}}

/* Spending */
.spend-row{display:flex;align-items:center;gap:8px;padding:8px 0;
           border-bottom:1px solid #222}
.spend-row:last-child{border-bottom:none}
.spend-cat{font-size:0.65rem;background:#252540;color:#888;padding:2px 7px;
           border-radius:10px;text-transform:capitalize;flex-shrink:0}
.spend-desc{flex:1;font-size:0.88rem}
.spend-amt{font-size:0.88rem;color:#4ade80;white-space:nowrap;font-weight:600}

/* Budget gauge */
.budget-gauge{height:8px;background:#252540;border-radius:20px;overflow:hidden;margin:8px 0}
.budget-fill{height:100%;border-radius:20px;transition:width .4s}
.fill-ok{background:linear-gradient(90deg,#4ade80,#22d3ee)}
.fill-warn{background:linear-gradient(90deg,#fbbf24,#f59e0b)}
.fill-over{background:#f87171}

/* Category bars */
.cat-row{display:flex;align-items:center;gap:8px;margin-bottom:6px}
.cat-name{font-size:0.75rem;color:#888;width:80px;flex-shrink:0;text-transform:capitalize}
.cat-bar-wrap{flex:1;height:6px;background:#252540;border-radius:10px;overflow:hidden}
.cat-bar-fill{height:100%;background:#c084fc;border-radius:10px}
.cat-amt{font-size:0.75rem;color:#aaa;white-space:nowrap;min-width:45px;text-align:right}

/* Forms */
.add-form{background:#181828;border:1px dashed #2a2a4a;border-radius:12px;
          padding:14px;margin-top:8px;display:none}
.add-form.open{display:block}
input,select,textarea{background:#0f0f0f;border:1px solid #2a2a4a;color:#e8e8e8;
  border-radius:8px;padding:9px 11px;font-size:0.86rem;width:100%;margin-bottom:8px}
textarea{height:60px;resize:vertical}
.row2{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.row3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px}
.flbl{font-size:0.7rem;color:#666;margin-bottom:3px}
.btn{border:none;border-radius:8px;padding:9px 15px;font-size:0.82rem;
     cursor:pointer;font-weight:500;transition:opacity .15s}
.btn:active{opacity:.75}
.btn-p{background:#c084fc;color:#fff}
.btn-s{background:#252540;color:#aaa;padding:7px 12px;font-size:0.76rem}
.btn-danger{background:#2a1a1a;color:#f87171}

/* Toast */
#toast{position:fixed;bottom:20px;left:50%;transform:translateX(-50%) translateY(60px);
       background:#c084fc;color:#fff;padding:10px 20px;border-radius:20px;
       font-size:0.85rem;font-weight:500;transition:transform .3s;
       pointer-events:none;z-index:99}
#toast.show{transform:translateX(-50%) translateY(0)}

.empty{text-align:center;padding:20px;color:#444;font-size:0.85rem}
.empty span{font-size:1.5rem;display:block;margin-bottom:5px}
</style>
</head>
<body>

<header>
  <h1>⚡ PPT Board · Journal</h1>
  <div class="nav-links">
    <a href="/board">📊 Dashboard</a>
    <a href="/">📋 Planner</a>
    <a href="/notify">🔔 Notify</a>
    <a href="/journal">📓 Journal</a>
  </div>
</header>

<!-- Tab bar -->
<div class="tabs">
  <div class="tab active" onclick="showTab('today')">
    <span class="tab-icon">🌅</span>Today
  </div>
  <div class="tab" onclick="showTab('food')">
    <span class="tab-icon">🍽</span>Food
  </div>
  <div class="tab" onclick="showTab('sleep')">
    <span class="tab-icon">💤</span>Sleep
  </div>
  <div class="tab" onclick="showTab('work')">
    <span class="tab-icon">💼</span>Work
  </div>
  <div class="tab" onclick="showTab('money')">
    <span class="tab-icon">💰</span>Money
  </div>
</div>

<!-- ═══════════════════════ TODAY PANEL ═══════════════════════ -->
<div class="panel active" id="panel-today">
  <!-- Balance score ring -->
  <div class="card" style="margin-top:14px">
    <div class="score-wrap">
      <div class="score-ring">
        <svg viewBox="0 0 72 72" width="72" height="72">
          <circle class="ring-bg" cx="36" cy="36" r="28"/>
          <circle class="ring-fill" cx="36" cy="36" r="28"
            stroke-dasharray="{{ score.score * 1.759 }} 175.9"
            stroke-dashoffset="0"/>
          <text x="36" y="36" class="score-num" fill="#c084fc"
                transform="rotate(90,36,36)">{{ score.score }}</text>
        </svg>
      </div>
      <div class="score-info">
        <div class="score-label">{{ score.label }}</div>
        <div class="score-sub">7-day balance score</div>
        <div class="score-sub" style="margin-top:6px">
          Sleep · Work · Food tracked daily
        </div>
      </div>
    </div>
  </div>

  <!-- Yesterday summary -->
  <div class="section">Yesterday</div>
  <div class="stats">
    <div class="stat">
      <div class="stat-val">{% if sleep_yday %}{{ "%.1f"|format(sleep_yday.duration_min / 60) }}h{% else %}—{% endif %}</div>
      <div class="stat-lbl">💤 Sleep</div>
    </div>
    <div class="stat">
      <div class="stat-val">{{ food_yday.calories | int }}</div>
      <div class="stat-lbl">🍽 Calories</div>
    </div>
    <div class="stat">
      <div class="stat-val">{{ "%.1f"|format(work_yday_min / 60) }}h</div>
      <div class="stat-lbl">💼 Work</div>
    </div>
    <div class="stat">
      <div class="stat-val">${{ "%.0f"|format(spend_yday) }}</div>
      <div class="stat-lbl">💰 Spent</div>
    </div>
  </div>

  <!-- Today quick stats -->
  <div class="section">Today so far</div>
  <div class="stats">
    <div class="stat">
      <div class="stat-val">{{ food_today.meals }}</div>
      <div class="stat-lbl">🍽 Meals logged</div>
    </div>
    <div class="stat">
      <div class="stat-val">{{ "%.1f"|format(work_today_min / 60) }}h</div>
      <div class="stat-lbl">💼 Work</div>
    </div>
    <div class="stat">
      <div class="stat-val">{{ food_today.calories | int }}</div>
      <div class="stat-lbl">🔥 Calories</div>
    </div>
    <div class="stat">
      <div class="stat-val">${{ "%.0f"|format(spend_today_total) }}</div>
      <div class="stat-lbl">💰 Spent today</div>
    </div>
  </div>

  <!-- Budget mini -->
  {% if budget.budget %}
  <div class="card">
    <div style="display:flex;justify-content:space-between;margin-bottom:6px">
      <span style="font-size:0.85rem;color:#888">Weekly budget</span>
      <span style="font-size:0.85rem;font-weight:600;color:{% if budget.over %}#f87171{% elif budget.pct >= 80 %}#fbbf24{% else %}#4ade80{% endif %}">
        ${{ "%.2f"|format(budget.spent) }} / ${{ "%.2f"|format(budget.budget) }}
      </span>
    </div>
    <div class="budget-gauge">
      <div class="budget-fill {% if budget.over %}fill-over{% elif budget.pct >= 80 %}fill-warn{% else %}fill-ok{% endif %}"
           style="width:{{ [budget.pct, 100] | min }}%"></div>
    </div>
    <div style="font-size:0.72rem;color:#555">{{ budget.pct }}% used · ${{ "%.2f"|format(budget.remaining) }} remaining</div>
  </div>
  {% endif %}
</div>

<!-- ═══════════════════════ FOOD PANEL ═══════════════════════ -->
<div class="panel" id="panel-food">
  <!-- Today totals -->
  <div class="card" style="margin-top:14px">
    <div class="card-title">Today · {{ food_today.calories | int }} cal</div>
    <div style="display:flex;gap:16px;margin-top:6px">
      <div><div style="font-size:0.72rem;color:#666">Protein</div>
           <div style="font-weight:600;color:#c8d0ff">{{ food_today.protein_g | int }}g</div></div>
      <div><div style="font-size:0.72rem;color:#666">Carbs</div>
           <div style="font-weight:600;color:#c8d0ff">{{ food_today.carbs_g | int }}g</div></div>
      <div><div style="font-size:0.72rem;color:#666">Fat</div>
           <div style="font-weight:600;color:#c8d0ff">{{ food_today.fat_g | int }}g</div></div>
    </div>
  </div>

  <!-- Today's meals -->
  <div class="section">Meals logged today</div>
  {% if meals_today %}
  <div class="card">
    {% for m in meals_today %}
    <div class="meal-row">
      <span class="meal-type">{{ m.meal_type }}</span>
      <span class="meal-name">{{ m.name }}</span>
      {% if m.calories %}<span class="meal-cal">{{ m.calories }} cal</span>{% endif %}
      <form method="POST" action="/journal/food/del" style="margin:0">
        <input type="hidden" name="log_id" value="{{ m.id }}">
        <button class="del-btn" onclick="return confirm('Remove?')">✕</button>
      </form>
    </div>
    {% endfor %}
  </div>
  {% else %}
  <div class="empty"><span>🍽</span>No meals logged yet today.</div>
  {% endif %}

  <button class="btn btn-s" onclick="toggle('food-form')">+ Log Meal</button>
  <div class="add-form" id="food-form">
    <form method="POST" action="/journal/food/add">
      <div class="row2">
        <div>
          <div class="flbl">Meal type</div>
          <select name="meal_type">
            {% for t in meal_types %}<option>{{ t }}</option>{% endfor %}
          </select>
        </div>
        <div>
          <div class="flbl">Calories</div>
          <input name="calories" type="number" placeholder="e.g. 350" min="0" max="5000">
        </div>
      </div>
      <div class="flbl">Food name</div>
      <input name="name" placeholder="e.g. Oatmeal with banana" required>
      <div class="row3">
        <div>
          <div class="flbl">Protein (g)</div>
          <input name="protein_g" type="number" step="0.1" placeholder="0">
        </div>
        <div>
          <div class="flbl">Carbs (g)</div>
          <input name="carbs_g" type="number" step="0.1" placeholder="0">
        </div>
        <div>
          <div class="flbl">Fat (g)</div>
          <input name="fat_g" type="number" step="0.1" placeholder="0">
        </div>
      </div>
      <button class="btn btn-p" type="submit">Log Food</button>
    </form>
  </div>

  <!-- 7-day history -->
  <div class="section">This week (calories)</div>
  <div class="card">
    <div style="display:flex;align-items:flex-end;gap:6px;height:80px">
      {% set max_cal = food_week | map(attribute='calories') | max | default(1) %}
      {% for d in food_week %}
      {% set pct = (d.calories / max_cal * 100) | int if max_cal > 0 else 0 %}
      <div style="flex:1;display:flex;flex-direction:column;align-items:center;gap:3px">
        <div style="height:{{ pct }}%;min-height:3px;width:100%;background:#c084fc;
                    border-radius:3px 3px 0 0;opacity:0.7"></div>
        <div style="font-size:0.58rem;color:#555">{{ d.date[-5:] }}</div>
      </div>
      {% endfor %}
    </div>
  </div>
</div>

<!-- ═══════════════════════ SLEEP PANEL ═══════════════════════ -->
<div class="panel" id="panel-sleep">
  <!-- Last night -->
  <div class="card" style="margin-top:14px">
    {% if sleep_last %}
    <div class="card-title">Last night · {{ "%.1f"|format(sleep_last.duration_min / 60) }}h</div>
    <div style="display:flex;gap:16px;margin-top:6px">
      {% if sleep_last.bedtime %}
      <div><div style="font-size:0.72rem;color:#666">Bedtime</div>
           <div style="font-weight:600;color:#c8d0ff">{{ sleep_last.bedtime }}</div></div>
      {% endif %}
      {% if sleep_last.waketime %}
      <div><div style="font-size:0.72rem;color:#666">Wake</div>
           <div style="font-weight:600;color:#c8d0ff">{{ sleep_last.waketime }}</div></div>
      {% endif %}
      {% if sleep_last.quality %}
      <div><div style="font-size:0.72rem;color:#666">Quality</div>
           <div style="font-weight:600;color:#c8d0ff">{{ sleep_last.quality }}/5</div></div>
      {% endif %}
    </div>
    {% else %}
    <div class="card-title">Last night</div>
    <div class="card-sub">Not logged yet</div>
    {% endif %}
  </div>

  <button class="btn btn-s" onclick="toggle('sleep-form')">+ Log Sleep</button>
  <div class="add-form" id="sleep-form">
    <form method="POST" action="/journal/sleep">
      <div class="row2">
        <div>
          <div class="flbl">Bedtime</div>
          <input name="bedtime" type="time" value="23:00">
        </div>
        <div>
          <div class="flbl">Wake time</div>
          <input name="waketime" type="time" value="07:00">
        </div>
      </div>
      <div class="row2">
        <div>
          <div class="flbl">Duration (hours)</div>
          <input name="hours" type="number" step="0.5" min="0" max="24" placeholder="e.g. 7.5">
        </div>
        <div>
          <div class="flbl">Quality (1–5)</div>
          <select name="quality">
            <option value="">—</option>
            <option value="5">5 — Excellent</option>
            <option value="4">4 — Good</option>
            <option value="3">3 — Okay</option>
            <option value="2">2 — Poor</option>
            <option value="1">1 — Terrible</option>
          </select>
        </div>
      </div>
      <div class="flbl">Notes</div>
      <input name="notes" placeholder="Anything affecting sleep?">
      <button class="btn btn-p" type="submit">Save Sleep Log</button>
    </form>
  </div>

  <!-- 7-night chart -->
  <div class="section">Last 7 nights</div>
  <div class="card">
    <div class="sleep-bars">
      {% for s in sleep_week %}
      {% set hrs = (s.duration_min / 60) if s.duration_min else 0 %}
      {% set pct = [(hrs / 10 * 100) | int, 100] | min %}
      <div class="sleep-bar-wrap">
        <div class="sleep-bar {% if hrs >= 7 %}good{% elif hrs >= 5 %}ok{% elif hrs > 0 %}bad{% endif %}"
             style="height:{{ pct }}%"></div>
        <span class="bar-day">{{ s.date[-5:] }}</span>
      </div>
      {% endfor %}
    </div>
    <div style="font-size:0.72rem;color:#666;margin-top:4px">
      7-day avg: {{ sleep_avg }}h &nbsp;·&nbsp;
      <span style="color:#c084fc">■</span> ≥7h
      <span style="color:#7c83ff;margin-left:6px">■</span> 5–7h
      <span style="color:#f87171;margin-left:6px">■</span> &lt;5h
    </div>
  </div>
</div>

<!-- ═══════════════════════ WORK PANEL ═══════════════════════ -->
<div class="panel" id="panel-work">
  <!-- Active session banner -->
  {% if active_session %}
  <div class="card" style="margin-top:14px;border-color:#2d4a2d">
    <div style="display:flex;align-items:center;justify-content:space-between">
      <div>
        <div style="display:flex;align-items:center;gap:8px">
          <span class="live-badge">● LIVE</span>
          <span style="font-weight:600;color:#4ade80">Working</span>
        </div>
        <div class="card-sub" style="margin-top:4px">
          {{ active_session.task or 'No task set' }}
          {% if active_session.project %} · {{ active_session.project }}{% endif %}
        </div>
        <div class="card-sub">Started {{ active_session.start_time }}</div>
      </div>
      <form method="POST" action="/journal/work/out" style="margin:0">
        <button class="btn btn-s" style="background:#1a2a1a;color:#4ade80">Clock Out</button>
      </form>
    </div>
  </div>
  {% else %}
  <div style="margin-top:14px">
    <button class="btn btn-p" onclick="toggle('workin-form')" style="width:100%;margin-bottom:10px">
      ▶ Clock In
    </button>
    <div class="add-form" id="workin-form">
      <form method="POST" action="/journal/work/in">
        <div class="flbl">Task / what are you working on?</div>
        <input name="task" placeholder="e.g. PPT notify module">
        <div class="flbl">Project</div>
        <input name="project" placeholder="e.g. PPT">
        <div class="flbl">Mood before (1–5)</div>
        <select name="mood_before">
          <option value="">—</option>
          <option value="5">5 — Energised</option>
          <option value="4">4 — Good</option>
          <option value="3">3 — Neutral</option>
          <option value="2">2 — Tired</option>
          <option value="1">1 — Drained</option>
        </select>
        <button class="btn btn-p" type="submit">Start Session</button>
      </form>
    </div>
  </div>
  {% endif %}

  <!-- Today's sessions -->
  <div class="section">Today · {{ "%.1f"|format(work_today_min / 60) }}h total</div>
  {% if work_sessions %}
  <div class="card">
    {% for s in work_sessions %}
    <div class="session">
      <span class="session-time">{{ s.start_time }}{% if s.end_time %} – {{ s.end_time }}{% endif %}</span>
      <span class="session-task">{{ s.task or '—' }}{% if s.project %} <span style="color:#666;font-size:0.75rem">· {{ s.project }}</span>{% endif %}</span>
      {% if s.duration_min %}
      <span class="session-dur">{{ s.duration_min // 60 }}h {{ s.duration_min % 60 }}m</span>
      {% elif not s.end_time %}
      <span class="live-badge">LIVE</span>
      {% endif %}
    </div>
    {% endfor %}
  </div>
  {% else %}
  <div class="empty"><span>💼</span>No sessions yet today.</div>
  {% endif %}

  <!-- Weekly chart -->
  <div class="section">This week (hours worked)</div>
  <div class="card">
    <div style="display:flex;align-items:flex-end;gap:6px;height:70px">
      {% set max_h = work_week | map(attribute='total_min') | max | default(1) %}
      {% for d in work_week %}
      {% set pct = (d.total_min / max_h * 100) | int if max_h > 0 else 0 %}
      <div style="flex:1;display:flex;flex-direction:column;align-items:center;gap:3px">
        <div style="height:{{ pct }}%;min-height:2px;width:100%;background:#7c83ff;
                    border-radius:3px 3px 0 0"></div>
        <div style="font-size:0.58rem;color:#555">{{ d.date[-5:] }}</div>
      </div>
      {% endfor %}
    </div>
  </div>
</div>

<!-- ═══════════════════════ MONEY PANEL ═══════════════════════ -->
<div class="panel" id="panel-money">
  <!-- Budget card -->
  <div class="card" style="margin-top:14px">
    {% if budget.budget %}
    <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:8px">
      <span class="card-title">Weekly Budget</span>
      <span style="font-size:0.85rem;color:{% if budget.over %}#f87171{% elif budget.pct >= 80 %}#fbbf24{% else %}#4ade80{% endif %};font-weight:600">
        ${{ "%.2f"|format(budget.spent) }} / ${{ "%.2f"|format(budget.budget) }}
      </span>
    </div>
    <div class="budget-gauge">
      <div class="budget-fill {% if budget.over %}fill-over{% elif budget.pct >= 80 %}fill-warn{% else %}fill-ok{% endif %}"
           style="width:{{ [budget.pct, 100] | min }}%"></div>
    </div>
    <div style="font-size:0.72rem;color:#555;margin-top:5px">{{ budget.pct }}% · ${{ "%.2f"|format(budget.remaining) }} remaining</div>
    {% else %}
    <div class="card-title">No budget set</div>
    <div class="card-sub">Set a weekly budget to track spending against it.</div>
    {% endif %}
  </div>

  <!-- Set budget -->
  <button class="btn btn-s" onclick="toggle('budget-form')">⚙ Set Budget</button>
  <div class="add-form" id="budget-form">
    <form method="POST" action="/journal/budget">
      <div class="flbl">Weekly budget ($)</div>
      <input name="amount" type="number" step="0.01" min="1"
             placeholder="e.g. 200" value="{{ budget.budget or '' }}">
      <button class="btn btn-p" type="submit">Save Budget</button>
    </form>
  </div>

  <!-- Today's spending -->
  <div class="section">Today · ${{ "%.2f"|format(spend_today_total) }}</div>
  <button class="btn btn-s" onclick="toggle('spend-form')">+ Log Purchase</button>
  <div class="add-form" id="spend-form">
    <form method="POST" action="/journal/spend/add">
      <div class="row2">
        <div>
          <div class="flbl">Amount ($)</div>
          <input name="amount" type="number" step="0.01" min="0.01" placeholder="12.50" required>
        </div>
        <div>
          <div class="flbl">Category</div>
          <select name="category">
            {% for c in spend_categories %}<option>{{ c }}</option>{% endfor %}
          </select>
        </div>
      </div>
      <div class="flbl">Description</div>
      <input name="description" placeholder="e.g. Coffee at Blue Tokai" required>
      <div class="flbl">Payment method</div>
      <select name="payment_method">
        <option value="">—</option>
        <option>card</option>
        <option>upi</option>
        <option>cash</option>
        <option>other</option>
      </select>
      <button class="btn btn-p" type="submit">Log Purchase</button>
    </form>
  </div>

  {% if spend_today_list %}
  <div class="card">
    {% for s in spend_today_list %}
    <div class="spend-row">
      <span class="spend-cat">{{ s.category }}</span>
      <span class="spend-desc">{{ s.description }}</span>
      <span class="spend-amt">${{ "%.2f"|format(s.amount) }}</span>
      <form method="POST" action="/journal/spend/del" style="margin:0">
        <input type="hidden" name="spend_id" value="{{ s.id }}">
        <button class="del-btn">✕</button>
      </form>
    </div>
    {% endfor %}
  </div>
  {% else %}
  <div class="empty"><span>💳</span>No purchases logged today.</div>
  {% endif %}

  <!-- Category breakdown this week -->
  {% if spend_categories_week %}
  <div class="section">This week by category</div>
  <div class="card">
    {% set max_cat = spend_categories_week[0].total if spend_categories_week else 1 %}
    {% for c in spend_categories_week %}
    <div class="cat-row">
      <span class="cat-name">{{ c.category }}</span>
      <div class="cat-bar-wrap">
        <div class="cat-bar-fill" style="width:{{ (c.total / max_cat * 100) | int }}%"></div>
      </div>
      <span class="cat-amt">${{ "%.0f"|format(c.total) }}</span>
    </div>
    {% endfor %}
  </div>
  {% endif %}
</div>

<div id="toast">✓ Saved!</div>

<script>
function showTab(name) {
  document.querySelectorAll('.tab').forEach((t,i) => {
    const names = ['today','food','sleep','work','money'];
    t.classList.toggle('active', names[i] === name);
  });
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.getElementById('panel-'+name).classList.add('active');
  // persist tab choice
  localStorage.setItem('journal_tab', name);
}
function toggle(id) {
  document.getElementById(id).classList.toggle('open');
}
// Restore last tab
const saved = localStorage.getItem('journal_tab');
if (saved) showTab(saved);
// Toast
if (new URLSearchParams(window.location.search).get('saved')) {
  const t = document.getElementById('toast');
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2500);
  history.replaceState({}, '', window.location.pathname);
}
</script>
</body>
</html>"""


# ═══════════════════════════════════════════════════════════════════════════════
# Route handlers
# ═══════════════════════════════════════════════════════════════════════════════

def _ctx():
    """Build template context — called on every GET /journal/."""
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    today_str  = date.today().isoformat()

    # Week ranges for category spend
    week_start = (date.today() - timedelta(days=date.today().weekday())).isoformat()
    week_end   = today_str

    return dict(
        score             = work_life_score(7),
        sleep_last        = store.get_sleep(yesterday),
        sleep_yday        = store.get_sleep(yesterday),
        sleep_week        = store.sleep_week_summary(),
        sleep_avg         = store.sleep_avg_hours(7) or 0,
        food_yday         = store.food_daily_totals(yesterday),
        food_today        = store.food_daily_totals(today_str),
        meals_today       = store.food_today(today_str),
        food_week         = store.food_week_summary(),
        work_yday_min     = store.work_daily_total_min(yesterday),
        work_today_min    = store.work_daily_total_min(today_str),
        work_sessions     = store.work_today(today_str),
        work_week         = store.work_week_summary(),
        active_session    = store.active_session(),
        spend_yday        = store.spend_total(yesterday),
        spend_today_total = store.spend_total(today_str),
        spend_today_list  = store.spend_today(today_str),
        spend_categories_week = store.spend_by_category(week_start, week_end),
        budget            = store.budget_status(),
        meal_types        = store.MEAL_TYPES,
        spend_categories  = store.SPEND_CATEGORIES,
    )


@journal_bp.route("/")
def index():
    return render_template_string(_HTML, **_ctx())


# ── Food ──────────────────────────────────────────────────────────────────────

@journal_bp.route("/food/add", methods=["POST"])
def food_add():
    def _f(k): return request.form.get(k) or None
    cal   = int(_f("calories"))   if _f("calories")   else None
    prot  = float(_f("protein_g")) if _f("protein_g") else None
    carbs = float(_f("carbs_g"))   if _f("carbs_g")   else None
    fat   = float(_f("fat_g"))     if _f("fat_g")     else None
    store.log_food(
        name=request.form["name"],
        meal_type=request.form.get("meal_type", "meal"),
        calories=cal, protein_g=prot, carbs_g=carbs, fat_g=fat,
    )
    return redirect(url_for("journal.index") + "?saved=1")


@journal_bp.route("/food/del", methods=["POST"])
def food_del():
    store.delete_food_log(int(request.form["log_id"]))
    return redirect(url_for("journal.index") + "?saved=1")


# ── Sleep ─────────────────────────────────────────────────────────────────────

@journal_bp.route("/sleep", methods=["POST"])
def sleep_log():
    hours = request.form.get("hours") or ""
    bedtime  = request.form.get("bedtime") or None
    waketime = request.form.get("waketime") or None
    quality  = request.form.get("quality") or None

    # Calculate duration from bedtime/waketime if hours not given
    if hours:
        duration_min = int(float(hours) * 60)
    elif bedtime and waketime:
        from datetime import datetime as dt
        b = dt.strptime(bedtime, "%H:%M")
        w = dt.strptime(waketime, "%H:%M")
        diff = (w - b).seconds // 60
        if diff < 0:
            diff += 24 * 60  # crossed midnight
        duration_min = diff
    else:
        duration_min = 0

    store.log_sleep(
        duration_min=duration_min,
        quality=int(quality) if quality else None,
        bedtime=bedtime, waketime=waketime,
        notes=request.form.get("notes", ""),
    )
    return redirect(url_for("journal.index") + "?saved=1")


# ── Work ──────────────────────────────────────────────────────────────────────

@journal_bp.route("/work/in", methods=["POST"])
def work_in():
    mood = request.form.get("mood_before") or None
    store.clock_in(
        task=request.form.get("task", ""),
        project=request.form.get("project", ""),
        mood_before=int(mood) if mood else None,
    )
    return redirect(url_for("journal.index") + "?saved=1")


@journal_bp.route("/work/out", methods=["POST"])
def work_out():
    mood = request.form.get("mood_after") or None
    store.clock_out(mood_after=int(mood) if mood else None)
    return redirect(url_for("journal.index") + "?saved=1")


# ── Money ─────────────────────────────────────────────────────────────────────

@journal_bp.route("/spend/add", methods=["POST"])
def spend_add():
    store.log_spend(
        amount=float(request.form["amount"]),
        description=request.form["description"],
        category=request.form.get("category", "other"),
        payment_method=request.form.get("payment_method", ""),
    )
    return redirect(url_for("journal.index") + "?saved=1")


@journal_bp.route("/spend/del", methods=["POST"])
def spend_del():
    store.delete_spend(int(request.form["spend_id"]))
    return redirect(url_for("journal.index") + "?saved=1")


@journal_bp.route("/budget", methods=["POST"])
def budget_set():
    store.set_budget(float(request.form["amount"]))
    return redirect(url_for("journal.index") + "?saved=1")


# ── API (for watch / RPi4 / future IoT) ──────────────────────────────────────

@journal_bp.route("/api/today")
def api_today():
    """JSON snapshot of today's stats — poll from any device."""
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    today_str  = date.today().isoformat()
    return jsonify({
        "date":         today_str,
        "sleep":        store.get_sleep(yesterday),
        "food":         store.food_daily_totals(today_str),
        "work_min":     store.work_daily_total_min(today_str),
        "active_session": store.active_session(),
        "spent_today":  store.spend_total(today_str),
        "budget":       store.budget_status(),
        "balance_score": work_life_score(7),
    })
