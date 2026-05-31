"""
src/web/notify_routes.py — Flask Blueprint for ppt-notify.

WHY a Blueprint?
  Flask Blueprints let you split a big app into modules.
  This file registers all /notify/* routes without touching the main app.py.
  Think of it as a plugin — app.py just does: app.register_blueprint(notify_bp).

ROUTES:
  GET  /notify/             — dashboard: habits, goals, reminders, check-in, relationship level
  POST /notify/habit/add    — add a new habit
  POST /notify/habit/done   — mark a habit done today
  POST /notify/habit/delete — soft-delete a habit
  POST /notify/goal/add     — add a new goal
  POST /notify/goal/progress— update goal progress
  POST /notify/reminder/add — add a custom reminder
  POST /notify/checkin      — save today's mood check-in
"""
from __future__ import annotations
from flask import Blueprint, render_template_string, request, redirect, url_for, jsonify
from src.notify import store
from src.notify.relationship import get_level_progress

notify_bp = Blueprint("notify", __name__, url_prefix="/notify")


# ── HTML template ─────────────────────────────────────────────────────────────

_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PPT Board — Notify</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       background: #0f0f0f; color: #e8e8e8; min-height: 100vh; }

/* ── Header ── */
header { background: #1a1a2e; padding: 14px 20px; display: flex; align-items: center;
         justify-content: space-between; border-bottom: 1px solid #2a2a4a;
         position: sticky; top: 0; z-index: 10; }
header h1 { font-size: 1.15rem; font-weight: 600; color: #a78bfa; }
header .nav { display: flex; gap: 12px; }
header .nav a { font-size: 0.8rem; color: #666; text-decoration: none; }
header .nav a:hover { color: #a78bfa; }

.container { padding: 16px; max-width: 640px; margin: 0 auto; }

/* ── Relationship card ── */
.rel-card { background: linear-gradient(135deg, #1a1a2e 0%, #2a1a3e 100%);
            border: 1px solid #3a2a5a; border-radius: 14px; padding: 18px;
            margin-bottom: 20px; }
.rel-level { font-size: 0.7rem; color: #a78bfa; text-transform: uppercase;
             letter-spacing: 0.1em; margin-bottom: 4px; }
.rel-name  { font-size: 1.3rem; font-weight: 700; color: #e8e8e8; margin-bottom: 2px; }
.rel-xp    { font-size: 0.8rem; color: #888; margin-bottom: 12px; }
.progress-bar { background: #2a2a3a; border-radius: 20px; height: 8px; overflow: hidden; }
.progress-fill { background: linear-gradient(90deg, #a78bfa, #7c83ff);
                 height: 100%; border-radius: 20px; transition: width 0.4s ease; }
.rel-next { font-size: 0.75rem; color: #666; margin-top: 6px; }

/* ── Section titles ── */
.section-title { font-size: 0.72rem; font-weight: 600; color: #666;
                 text-transform: uppercase; letter-spacing: 0.06em;
                 margin: 20px 0 8px; }

/* ── Cards ── */
.card { background: #1e1e2e; border-radius: 12px; padding: 14px 16px;
        margin-bottom: 10px; border: 1px solid #2a2a4a; }
.card-row { display: flex; align-items: center; gap: 10px; }
.card-title { font-size: 0.95rem; font-weight: 500; flex: 1; color: #c8d0ff; }
.card-sub { font-size: 0.78rem; color: #666; margin-top: 3px; }

/* ── Streak badge ── */
.streak { font-size: 0.75rem; background: #2a1a0a; color: #f59e0b;
          border: 1px solid #5a3a1a; border-radius: 20px;
          padding: 3px 9px; white-space: nowrap; }
.streak-done { background: #1a2a1a; color: #4ade80; border-color: #2d4a2d; }

/* ── Buttons ── */
.btn { border: none; border-radius: 8px; padding: 8px 14px; font-size: 0.82rem;
       cursor: pointer; font-weight: 500; transition: opacity 0.15s; }
.btn:active { opacity: 0.75; }
.btn-primary { background: #a78bfa; color: #fff; }
.btn-small   { background: #2a2a4a; color: #aaa; padding: 6px 10px; font-size: 0.75rem; }
.btn-done    { background: #1a2a1a; color: #4ade80; }
.btn-del     { background: #2a1a1a; color: #f87171; }

/* ── Add form ── */
.add-form { background: #181828; border: 1px dashed #2a2a4a; border-radius: 12px;
            padding: 14px; margin-top: 10px; display: none; }
.add-form.open { display: block; }
.add-form input, .add-form select, .add-form textarea {
  background: #0f0f0f; border: 1px solid #2a2a4a; color: #e8e8e8;
  border-radius: 8px; padding: 9px 11px; font-size: 0.88rem; width: 100%;
  margin-bottom: 8px; }
.add-form textarea { height: 70px; resize: vertical; }
.row2 { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.form-label { font-size: 0.72rem; color: #666; margin-bottom: 3px; }

/* ── Goal progress ── */
.goal-progress { height: 4px; background: #2a2a3a; border-radius: 4px;
                 margin-top: 8px; overflow: hidden; }
.goal-fill { height: 100%; background: #7c83ff; border-radius: 4px; }
.goal-pct  { font-size: 0.72rem; color: #7c83ff; margin-top: 4px; }

/* ── Mood check-in ── */
.mood-grid { display: flex; gap: 8px; justify-content: space-between; margin: 10px 0; }
.mood-btn  { flex: 1; background: #1e1e2e; border: 2px solid #2a2a4a;
             border-radius: 10px; padding: 10px 4px; text-align: center;
             cursor: pointer; transition: all 0.2s; }
.mood-btn:hover { border-color: #a78bfa; }
.mood-btn.selected { border-color: #a78bfa; background: #2a1a4a; }
.mood-emoji { font-size: 1.4rem; display: block; margin-bottom: 2px; }
.mood-label { font-size: 0.65rem; color: #888; }
#mood-val   { display: none; }

/* ── Empty state ── */
.empty { text-align: center; padding: 24px; color: #555; font-size: 0.88rem; }
.empty span { font-size: 1.5rem; display: block; margin-bottom: 6px; }

/* ── Toast ── */
#toast { position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%) translateY(60px);
         background: #a78bfa; color: #fff; padding: 10px 20px; border-radius: 20px;
         font-size: 0.85rem; font-weight: 500; transition: transform 0.3s ease;
         pointer-events: none; z-index: 99; }
#toast.show { transform: translateX(-50%) translateY(0); }
</style>
</head>
<body>

<header>
  <h1>⚡ PPT Board · Notify</h1>
  <div class="nav">
    <a href="/board">📊 Dashboard</a>
    <a href="/">📋 Planner</a>
    <a href="/notify">🔔 Notify</a>
    <a href="/notify/users">👤 Users</a>
    <a href="/scheduler">🗓 Scheduler</a>
  </div>
</header>

<div class="container">

  <!-- Relationship card -->
  <div class="rel-card">
    <div class="rel-level">Relationship · {{ rel.level }}</div>
    <div class="rel-name">{{ profile.name }}</div>
    <div class="rel-xp">{{ rel.xp }} XP earned</div>
    <div class="progress-bar">
      <div class="progress-fill" style="width: {{ rel.pct }}%"></div>
    </div>
    {% if rel.next_level %}
    <div class="rel-next">{{ rel.pct }}% toward {{ rel.next_level }} · {{ rel.next_at - rel.xp }} XP to go</div>
    {% else %}
    <div class="rel-next">Maximum level reached 💙</div>
    {% endif %}
  </div>

  <!-- ── HABITS ── -->
  <div class="section-title">Daily Habits</div>

  {% for h in habits %}
  <div class="card">
    <div class="card-row">
      <div style="flex:1">
        <div class="card-title">{{ h.name }}</div>
        <div class="card-sub">{{ h.frequency | capitalize }} · {{ h.remind_at }}</div>
      </div>
      {% if h.done_today %}
        <span class="streak streak-done">✓ {{ h.streak }}d</span>
      {% else %}
        <span class="streak">🔥 {{ h.streak }}d</span>
        <form method="POST" action="/notify/habit/done" style="margin:0">
          <input type="hidden" name="habit_id" value="{{ h.id }}">
          <button class="btn btn-small btn-done">Done ✓</button>
        </form>
      {% endif %}
      <form method="POST" action="/notify/habit/delete" style="margin:0">
        <input type="hidden" name="habit_id" value="{{ h.id }}">
        <button class="btn btn-small btn-del" onclick="return confirm('Remove this habit?')">✕</button>
      </form>
    </div>
    {% if h.description %}
    <div class="card-sub" style="margin-top:6px">{{ h.description }}</div>
    {% endif %}
  </div>
  {% else %}
  <div class="empty"><span>🌱</span>No habits yet. Add your first one below.</div>
  {% endfor %}

  <button class="btn btn-small" onclick="toggle('habit-form')">+ Add Habit</button>
  <div class="add-form" id="habit-form">
    <form method="POST" action="/notify/habit/add">
      <div class="form-label">Habit name</div>
      <input name="name" placeholder="e.g. Drink water" required>
      <div class="form-label">Description (optional)</div>
      <input name="description" placeholder="Why this matters to you...">
      <div class="row2">
        <div>
          <div class="form-label">Frequency</div>
          <select name="frequency">
            <option value="daily">Every day</option>
            <option value="weekdays">Weekdays</option>
            <option value="weekends">Weekends</option>
            <option value="weekly">Weekly</option>
          </select>
        </div>
        <div>
          <div class="form-label">Remind at</div>
          <input name="remind_at" type="time" value="08:00" required>
        </div>
      </div>
      <button class="btn btn-primary" type="submit">Add Habit</button>
    </form>
  </div>

  <!-- ── GOALS ── -->
  <div class="section-title">Personal Goals</div>

  {% for g in goals %}
  <div class="card">
    <div class="card-row">
      <div style="flex:1">
        <div class="card-title">{{ g.title }}</div>
        <div class="card-sub">
          {% if g.deadline %}📅 {{ g.deadline }}{% endif %}
          {% if g.remind_at %} · 🔔 {{ g.remind_at }}{% endif %}
        </div>
      </div>
      <span style="font-size:0.8rem; color:#7c83ff; font-weight:600">{{ g.progress }}%</span>
    </div>
    {% if g.description %}
    <div class="card-sub" style="margin-top:5px">{{ g.description }}</div>
    {% endif %}
    <div class="goal-progress"><div class="goal-fill" style="width:{{ g.progress }}%"></div></div>
    <form method="POST" action="/notify/goal/progress" style="margin-top:8px">
      <input type="hidden" name="goal_id" value="{{ g.id }}">
      <div style="display:flex;gap:8px;align-items:center">
        <input name="progress" type="range" min="0" max="100" value="{{ g.progress }}"
               style="flex:1;accent-color:#7c83ff"
               oninput="this.nextElementSibling.textContent=this.value+'%'">
        <span style="font-size:0.78rem;color:#7c83ff;width:36px">{{ g.progress }}%</span>
        <button class="btn btn-small">Save</button>
      </div>
    </form>
  </div>
  {% else %}
  <div class="empty"><span>🎯</span>No personal goals yet.</div>
  {% endfor %}

  <button class="btn btn-small" onclick="toggle('goal-form')">+ Add Personal Goal</button>
  <div class="add-form" id="goal-form">
    <form method="POST" action="/notify/goal/add">
      <div class="form-label">Goal title</div>
      <input name="title" placeholder="e.g. Learn Spanish to B2" required>
      <div class="form-label">Description (optional)</div>
      <textarea name="description" placeholder="Why this goal matters..."></textarea>
      <div class="row2">
        <div>
          <div class="form-label">Deadline (optional)</div>
          <input name="deadline" type="date">
        </div>
        <div>
          <div class="form-label">Daily reminder at</div>
          <input name="remind_at" type="time">
        </div>
      </div>
      <button class="btn btn-primary" type="submit">Add Goal</button>
    </form>
  </div>

  <!-- ── REMINDERS ── -->
  <div class="section-title">Custom Reminders</div>

  {% for r in reminders %}
  <div class="card">
    <div class="card-row">
      <div style="flex:1">
        <div class="card-title">⏰ {{ r.title }}</div>
        <div class="card-sub">{{ r.repeat | capitalize }} · {{ r.remind_at }}
          {% if r.fire_date %} · {{ r.fire_date }}{% endif %}
        </div>
      </div>
      <form method="POST" action="/notify/reminder/delete" style="margin:0">
        <input type="hidden" name="reminder_id" value="{{ r.id }}">
        <button class="btn btn-small btn-del">✕</button>
      </form>
    </div>
    {% if r.message %}
    <div class="card-sub" style="margin-top:5px">{{ r.message }}</div>
    {% endif %}
  </div>
  {% else %}
  <div class="empty"><span>📌</span>No reminders set.</div>
  {% endfor %}

  <button class="btn btn-small" onclick="toggle('reminder-form')">+ Add Reminder</button>
  <div class="add-form" id="reminder-form">
    <form method="POST" action="/notify/reminder/add">
      <div class="form-label">Title</div>
      <input name="title" placeholder="e.g. Take vitamins" required>
      <div class="form-label">Message (optional detail)</div>
      <input name="message" placeholder="Extra info for the notification...">
      <div class="row2">
        <div>
          <div class="form-label">Repeat</div>
          <select name="repeat">
            <option value="once">One time</option>
            <option value="daily">Daily</option>
            <option value="weekdays">Weekdays</option>
            <option value="weekly">Weekly</option>
          </select>
        </div>
        <div>
          <div class="form-label">Time</div>
          <input name="remind_at" type="time" value="09:00" required>
        </div>
      </div>
      <div>
        <div class="form-label">Date (for one-time reminders)</div>
        <input name="fire_date" type="date">
      </div>
      <button class="btn btn-primary" type="submit" style="margin-top:4px">Add Reminder</button>
    </form>
  </div>

  <!-- ── MOOD CHECK-IN ── -->
  <div class="section-title">Today's Check-in</div>
  <div class="card">
    {% if checkin %}
    <div style="display:flex;align-items:center;gap:10px">
      <span style="font-size:1.6rem">{{ ['','😞','😔','😐','🙂','😄'][checkin.mood] }}</span>
      <div>
        <div style="font-size:0.9rem;color:#c8d0ff;font-weight:500">
          {{ ['','Rough','Tough','Okay','Good','Great!'][checkin.mood] }} today
        </div>
        {% if checkin.note %}
        <div class="card-sub">{{ checkin.note }}</div>
        {% endif %}
      </div>
    </div>
    {% else %}
    <form method="POST" action="/notify/checkin">
      <div style="font-size:0.88rem;color:#888;margin-bottom:10px">How are you feeling today?</div>
      <div class="mood-grid">
        {% for emoji, label, val in [('😞','Rough',1),('😔','Tough',2),('😐','Okay',3),('🙂','Good',4),('😄','Great',5)] %}
        <div class="mood-btn" onclick="selectMood(this, {{ val }})">
          <span class="mood-emoji">{{ emoji }}</span>
          <span class="mood-label">{{ label }}</span>
        </div>
        {% endfor %}
      </div>
      <input type="hidden" name="mood" id="mood-val">
      <textarea name="note" placeholder="A note about your day... (optional)"
                style="background:#0f0f0f;border:1px solid #2a2a4a;color:#e8e8e8;
                       border-radius:8px;padding:9px 11px;font-size:0.85rem;
                       width:100%;height:60px;resize:vertical;margin-bottom:8px"></textarea>
      <button class="btn btn-primary" type="submit" id="checkin-btn" disabled>Save Check-in</button>
    </form>
    {% endif %}
  </div>

  <div style="height: 40px"></div>
</div>

<div id="toast">✓ Saved!</div>

<script>
function toggle(id) {
  const el = document.getElementById(id);
  el.classList.toggle('open');
}

function selectMood(el, val) {
  document.querySelectorAll('.mood-btn').forEach(b => b.classList.remove('selected'));
  el.classList.add('selected');
  document.getElementById('mood-val').value = val;
  document.getElementById('checkin-btn').disabled = false;
}

// Show toast if ?saved=1 in URL
if (new URLSearchParams(window.location.search).get('saved')) {
  const t = document.getElementById('toast');
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2500);
  history.replaceState({}, '', window.location.pathname);
}
</script>
</body>
</html>"""


# ── Routes ────────────────────────────────────────────────────────────────────

@notify_bp.route("/")
def index():
    profile = store.get_profile()
    xp = profile.get("relationship_xp", 0)
    rel = get_level_progress(xp)

    raw_habits = store.list_habits()
    habits = []
    for h in raw_habits:
        h = dict(h)
        h["streak"]    = store.habit_streak(h["id"])
        h["done_today"] = store.habit_done_today(h["id"])
        habits.append(h)

    goals    = store.list_goals()
    reminders = store.list_reminders()
    checkin  = store.get_checkin()

    return render_template_string(
        _HTML,
        profile=profile,
        rel=rel,
        habits=habits,
        goals=goals,
        reminders=reminders,
        checkin=checkin,
    )


@notify_bp.route("/habit/add", methods=["POST"])
def habit_add():
    store.add_habit(
        name=request.form["name"],
        description=request.form.get("description", ""),
        frequency=request.form.get("frequency", "daily"),
        remind_at=request.form.get("remind_at", "08:00"),
    )
    return redirect(url_for("notify.index") + "?saved=1")


@notify_bp.route("/habit/done", methods=["POST"])
def habit_done():
    store.log_habit_done(int(request.form["habit_id"]))
    return redirect(url_for("notify.index") + "?saved=1")


@notify_bp.route("/habit/delete", methods=["POST"])
def habit_delete():
    store.delete_habit(int(request.form["habit_id"]))
    return redirect(url_for("notify.index") + "?saved=1")


@notify_bp.route("/goal/add", methods=["POST"])
def goal_add():
    store.add_goal(
        title=request.form["title"],
        description=request.form.get("description", ""),
        deadline=request.form.get("deadline") or None,
        remind_at=request.form.get("remind_at") or None,
    )
    return redirect(url_for("notify.index") + "?saved=1")


@notify_bp.route("/goal/progress", methods=["POST"])
def goal_progress():
    goal = store.update_goal_progress(
        int(request.form["goal_id"]),
        int(request.form["progress"]),
    )
    # If just completed, send a congratulations
    if goal and goal["status"] == "done":
        from src.notify.messenger import send
        from src.notify.relationship import goal_completed_message
        send(goal_completed_message(goal["title"], user_id=goal.get("user_id")), user_id=goal.get("user_id"))
    return redirect(url_for("notify.index") + "?saved=1")


@notify_bp.route("/reminder/add", methods=["POST"])
def reminder_add():
    store.add_reminder(
        title=request.form["title"],
        message=request.form.get("message", ""),
        remind_at=request.form.get("remind_at", "09:00"),
        repeat=request.form.get("repeat", "once"),
        fire_date=request.form.get("fire_date") or None,
    )
    return redirect(url_for("notify.index") + "?saved=1")


@notify_bp.route("/reminder/delete", methods=["POST"])
def reminder_delete():
    store.deactivate_reminder(int(request.form["reminder_id"]))
    return redirect(url_for("notify.index") + "?saved=1")


@notify_bp.route("/checkin", methods=["POST"])
def checkin():
    mood = request.form.get("mood")
    note = request.form.get("note", "")
    if mood:
        store.save_checkin(int(mood), note)
    return redirect(url_for("notify.index") + "?saved=1")


# ── API endpoints (for future watch/IoT integration) ─────────────────────────

@notify_bp.route("/api/habits")
def api_habits():
    """JSON endpoint — future smartwatch / RPi4 can poll this."""
    habits = store.list_habits()
    result = []
    for h in habits:
        h = dict(h)
        h["streak"]     = store.habit_streak(h["id"])
        h["done_today"] = store.habit_done_today(h["id"])
        result.append(h)
    return jsonify(result)


@notify_bp.route("/api/profile")
def api_profile():
    """JSON endpoint for the relationship profile."""
    profile = store.get_profile()
    xp = profile.get("relationship_xp", 0)
    return jsonify({**profile, **get_level_progress(xp)})
