"""PPT Board — planner page for the unified web app."""
from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from flask import Flask, render_template_string, request, redirect, url_for, jsonify, send_from_directory, Response
from src.projects import store

app = Flask(__name__)
app.secret_key = os.getenv("PPT_SECRET_KEY", "ppt-dev-secret")

# ── ppt-notify Blueprint ──────────────────────────────────────────────────────
# WHY register here: Blueprints keep the notify UI in its own file but share
# the same Flask app instance (same port, same session, same dev server).
from src.web.notify_routes import notify_bp
app.register_blueprint(notify_bp)

from src.web.onboarding_routes import onboarding_bp
app.register_blueprint(onboarding_bp)

# ── ppt-journal Blueprint ─────────────────────────────────────────────────────
# WHY: The journal (food/sleep/work/money) is a separate concern from project
# tracking.  Blueprint keeps it isolated but accessible on the same Flask app.
from src.web.journal_routes import journal_bp
app.register_blueprint(journal_bp)

# ── ppt-analytics Blueprint ───────────────────────────────────────────────────
# WHY: Analytics + training data export is its own concern — it reads from
# all other modules (notify, journal) but writes only to data/training/*.jsonl.
from src.web.analytics_routes import analytics_bp
app.register_blueprint(analytics_bp)

# ── ppt-scheduler Blueprint ───────────────────────────────────────────────────
# WHY: Scheduling is its own app boundary — it talks to Google Calendar and
# manages conflict-aware agenda operations without mixing concerns with notify.
from src.web.scheduler_routes import scheduler_bp
app.register_blueprint(scheduler_bp)

# ── ppt-board Blueprint ───────────────────────────────────────────────────────
# WHY: The board aggregates all data sources into one always-on dashboard.
# Lives at /board (HTML) and /board/api/board (JSON).
from src.web.board_routes import board_bp
app.register_blueprint(board_bp)

_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PPT Board — Planner</title>
<!-- PWA: manifest tells the browser this is installable -->
<link rel="manifest" href="/static/manifest.json">
<!-- PWA: mobile-web-app-capable enables standalone mode on Android Chrome -->
<meta name="mobile-web-app-capable" content="yes">
<!-- PWA: apple-mobile-web-app-capable enables Add to Home Screen on iOS Safari -->
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="PPT Board">
<!-- PWA: theme-color tints the browser chrome (address bar) on Android -->
<meta name="theme-color" content="#1a1a2e">
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         background: #0f0f0f; color: #e8e8e8; min-height: 100vh; }
  header { background: #1a1a2e; padding: 16px 20px; display: flex;
           align-items: center; justify-content: space-between; gap: 16px;
           border-bottom: 1px solid #2a2a4a; position: sticky; top:0; z-index:10; }
  .header-copy h1 { font-size: 1.2rem; font-weight: 600; color: #7c83ff; }
  .header-copy span { font-size: 0.8rem; color: #888; }
  .nav { display: flex; gap: 10px; flex-wrap: wrap; }
  .nav a { font-size: 0.78rem; color: #888; text-decoration: none;
           border: 1px solid #2a2a4a; border-radius: 999px; padding: 7px 11px; }
  .nav a:hover { color: #e8e8e8; border-color: #7c83ff; }
  .container { padding: 16px; max-width: 600px; margin: 0 auto; }
  .card { background: #1e1e2e; border-radius: 12px; padding: 16px; margin-bottom: 12px;
          border: 1px solid #2a2a4a; }
  .project-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
  .project-name { font-size: 1rem; font-weight: 600; color: #c8d0ff; }
  .badge { font-size: 0.7rem; padding: 3px 8px; border-radius: 20px; font-weight: 500; }
  .badge-active { background: #1e3a2e; color: #4ade80; border: 1px solid #2d5a40; }
  .badge-done   { background: #2a2a2a; color: #888; border: 1px solid #3a3a3a; }
  .badge-paused { background: #3a2a1a; color: #f59e0b; border: 1px solid #5a4a2a; }
  .goal { font-size: 0.8rem; color: #888; margin-bottom: 10px; }
  .task { display: flex; align-items: center; gap: 10px; padding: 8px 0;
          border-bottom: 1px solid #2a2a4a; }
  .task:last-child { border-bottom: none; }
  .task-check { width: 18px; height: 18px; border-radius: 50%; border: 2px solid #555;
                cursor: pointer; display: flex; align-items: center; justify-content: center;
                flex-shrink: 0; transition: all 0.2s; }
  .task-check.done { background: #4ade80; border-color: #4ade80; }
  .task-title { font-size: 0.9rem; flex: 1; }
  .task-title.done { text-decoration: line-through; color: #555; }
  .priority { font-size: 0.7rem; padding: 2px 6px; border-radius: 10px; }
  .p-high   { background: #3a1a1a; color: #f87171; }
  .p-medium { background: #2a2a2a; color: #fbbf24; }
  .p-low    { background: #1a2a1a; color: #6ee7b7; }
  .task-stats { font-size: 0.8rem; color: #666; margin-top: 4px; }
  .add-form { display: flex; flex-direction: column; gap: 10px; margin-top: 12px; }
  .add-form input, .add-form select, .add-form textarea { background: #0f0f0f; border: 1px solid #2a2a4a;
    color: #e8e8e8; border-radius: 8px; padding: 10px 12px; font-size: 0.9rem; width: 100%; }
  .add-form textarea { min-height: 88px; resize: vertical; }
  .btn { background: #7c83ff; color: #fff; border: none; border-radius: 8px;
         padding: 10px 16px; font-size: 0.9rem; cursor: pointer; font-weight: 500; }
  .btn:active { opacity: 0.8; }
  .btn-sm { padding: 6px 12px; font-size: 0.8rem; background: #2a2a4a; }
  .btn-link { background: transparent; color: #888; border: 1px solid #2a2a4a; }
  .section-title { font-size: 0.75rem; font-weight: 600; color: #666; text-transform: uppercase;
                   letter-spacing: 0.05em; margin: 20px 0 8px; }
  .new-project-form { background: #1e1e2e; border-radius: 12px; padding: 16px;
                      border: 1px dashed #2a2a4a; margin-bottom: 12px; }
  .empty { text-align: center; padding: 40px 20px; color: #555; font-size: 0.9rem; }
  form { margin: 0; }
  .inline { display: flex; gap: 8px; }
  .inline input { flex: 1; }
  .task-body { flex: 1; min-width: 0; }
  .task-row { display: flex; align-items: center; gap: 10px; width: 100%; }
  .task-meta { display: flex; align-items: center; gap: 8px; }
  .task-notes { margin-top: 6px; font-size: 0.78rem; color: #8f93b8; line-height: 1.45; }
  .task-notes summary { cursor: pointer; color: #7c83ff; list-style: none; }
  .task-notes summary::-webkit-details-marker { display: none; }
  .task-edit { margin-top: 8px; display: none; }
  .task-edit.open { display: block; }
  .task-edit .add-form { margin-top: 0; padding: 12px; border-style: solid; }
  .muted { color: #666; font-size: 0.78rem; margin-top: 6px; }
</style>
</head>
<body>
<header>
  <div class="header-copy">
    <h1>⚡ PPT Board</h1>
    <span>Planner</span>
  </div>
  <nav class="nav">
    <a href="/board/">Dashboard</a>
    <a href="/">Planner</a>
    <a href="/notify">Notify</a>
    <a href="/notify/users">Users</a>
    <a href="/scheduler">Scheduler</a>
  </nav>
</header>
<div class="container">

  <!-- New project -->
  <div class="section-title">New Project</div>
  <div class="new-project-form">
    <form method="POST" action="/project/new">
      <div class="add-form">
        <input name="name" placeholder="Project name" required>
        <input name="goal" placeholder="Goal (optional)">
        <button class="btn" type="submit">+ Create Project</button>
      </div>
    </form>
  </div>

  <!-- Projects -->
  <div class="section-title">Active Projects</div>
  {% if not projects %}
    <div class="empty">No projects yet. Create one above.</div>
  {% endif %}
  {% for p in projects %}
  <div class="card">
    <div class="project-header">
      <span class="project-name">{{ p.name }}</span>
      <span class="badge badge-{{ p.status }}">{{ p.status }}</span>
    </div>
    {% if p.goal %}<div class="goal">{{ p.goal }}</div>{% endif %}

    <!-- Tasks -->
    {% set tasks = task_map[p.id] %}
    {% set open_tasks = tasks | selectattr('status', 'ne', 'done') | list %}
    {% set done_tasks = tasks | selectattr('status', 'eq', 'done') | list %}
    <div class="task-stats">{{ open_tasks|length }} open · {{ done_tasks|length }} done</div>

    {% for t in tasks %}
    <div class="task">
      <form method="POST" action="/task/{{ t.id }}/toggle">
        <button type="submit" class="task-check {{ 'done' if t.status == 'done' else '' }}"
                title="Mark done">{% if t.status == 'done' %}✓{% endif %}</button>
      </form>
      <div class="task-body">
        <div class="task-row">
          <span class="task-title {{ 'done' if t.status == 'done' else '' }}">{{ t.title }}</span>
          <div class="task-meta">
            <span class="priority p-{{ t.priority }}">{{ t.priority }}</span>
            <button class="btn btn-sm btn-link" type="button" onclick="toggleEdit('task-edit-{{ t.id }}')">Edit</button>
          </div>
        </div>
        {% if t.notes %}
        <details class="task-notes">
          <summary>Story details</summary>
          <div style="white-space: pre-wrap">{{ t.notes }}</div>
        </details>
        {% else %}
        <div class="muted">No story description yet.</div>
        {% endif %}
        <div class="task-edit" id="task-edit-{{ t.id }}">
          <form method="POST" action="/task/{{ t.id }}/update" class="add-form open">
            <input name="title" value="{{ t.title }}" required>
            <select name="priority">
              <option value="medium" {{ 'selected' if t.priority == 'medium' else '' }}>Med</option>
              <option value="high" {{ 'selected' if t.priority == 'high' else '' }}>High</option>
              <option value="low" {{ 'selected' if t.priority == 'low' else '' }}>Low</option>
            </select>
            <textarea name="notes" placeholder="Story description, acceptance notes, implementation detail...">{{ t.notes or '' }}</textarea>
            <button class="btn btn-sm" type="submit">Save</button>
          </form>
        </div>
      </div>
    </div>
    {% endfor %}

    <!-- Add task -->
    <form method="POST" action="/task/new" style="margin-top:12px">
      <input type="hidden" name="project_id" value="{{ p.id }}">
      <div class="add-form" style="display:flex">
        <div class="inline">
          <input name="title" placeholder="Add task..." required>
          <select name="priority" style="width:90px">
            <option value="medium">Med</option>
            <option value="high">High</option>
            <option value="low">Low</option>
          </select>
          <button class="btn btn-sm" type="submit">+</button>
        </div>
        <textarea name="notes" placeholder="Story description (optional)"></textarea>
      </div>
    </form>
  </div>
  {% endfor %}

  <!-- Done projects -->
  {% if done_projects %}
  <div class="section-title">Completed</div>
  {% for p in done_projects %}
  <div class="card" style="opacity:0.5">
    <div class="project-header">
      <span class="project-name">{{ p.name }}</span>
      <span class="badge badge-done">done</span>
    </div>
  </div>
  {% endfor %}
  {% endif %}

</div>
<script>
function toggleEdit(id) {
  const el = document.getElementById(id);
  if (!el) return;
  el.classList.toggle('open');
}

// Auto-refresh every 30s to pick up voice-command changes
setTimeout(() => location.reload(), 30000);

// PWA: Register service worker so Chrome shows the "Add to Home Screen" prompt.
// WHY /sw.js and not /static/sw.js?  The SW scope = the directory it is served
// from.  /sw.js is at root scope ("/"), so it can intercept requests for ALL
// routes (/notify, /scheduler, etc.).  A SW at /static/sw.js would be scoped
// only to /static/ — useless for an app at "/".
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js')
      .then(reg => console.log('[PPT PWA] SW registered, scope:', reg.scope))
      .catch(err => console.warn('[PPT PWA] SW registration failed:', err));
  });
}
</script>
</body>
</html>"""


@app.route("/")
def index():
    store.init_db()
    projects = store.list_projects(status="active")
    done_projects = store.list_projects(status="done")
    task_map = {p["id"]: store.list_tasks(project_id=p["id"]) for p in projects}
    return render_template_string(_HTML, projects=projects, done_projects=done_projects, task_map=task_map)


@app.route("/project/new", methods=["POST"])
def new_project():
    name = request.form.get("name", "").strip()
    goal = request.form.get("goal", "").strip()
    if name:
        store.add_project(name, goal)
    return redirect(url_for("index"))


@app.route("/task/new", methods=["POST"])
def new_task():
    project_id = int(request.form.get("project_id", 0))
    title = request.form.get("title", "").strip()
    priority = request.form.get("priority", "medium")
    notes = request.form.get("notes", "").strip()
    if project_id and title:
        store.add_task(project_id, title, priority=priority, notes=notes)
    return redirect(url_for("index"))


@app.route("/task/<int:task_id>/toggle", methods=["POST"])
def toggle_task(task_id):
    task = store.get_task(task_id)
    if task:
        new_status = "todo" if task["status"] == "done" else "done"
        store.update_task_status(task_id, new_status)
    return redirect(url_for("index"))


@app.route("/task/<int:task_id>/update", methods=["POST"])
def update_task(task_id):
    store.update_task(
        task_id,
        title=request.form.get("title"),
        priority=request.form.get("priority"),
        notes=request.form.get("notes", ""),
    )
    return redirect(url_for("index"))


@app.route("/api/projects")
def api_projects():
    return jsonify(store.list_projects())


@app.route("/health")
def health():
    """Health check endpoint for ppt-control and Uptime Kuma to poll.
    Returns 200 OK when the app is up and the DB is reachable."""
    try:
        store.init_db()
        store.list_projects(status="active")
        return jsonify({"status": "ok", "service": "ppt-board"}), 200
    except Exception as e:
        return jsonify({"status": "error", "detail": str(e)}), 500


@app.route("/sw.js")
def service_worker():
    """Serve the service worker from root scope so it can intercept all routes.

    WHY a dedicated route instead of /static/sw.js?
    Service worker scope = the URL directory it is served from.  If we served
    it from /static/sw.js its scope would be /static/ — it could not intercept
    requests to / or /notify.  Serving from /sw.js gives scope "/".

    The Service-Worker-Allowed header is an extra safety valve that lets the
    SW claim a broader scope than its path, but serving from root is cleaner.
    """
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    response = send_from_directory(static_dir, "sw.js")
    response.headers["Content-Type"] = "application/javascript"
    response.headers["Service-Worker-Allowed"] = "/"
    response.headers["Cache-Control"] = "no-cache"
    return response


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=False)
