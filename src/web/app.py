"""PPT Project Planner — mobile-friendly web UI."""
from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from flask import Flask, render_template_string, request, redirect, url_for, jsonify
from src.projects import store

app = Flask(__name__)

_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PPT — Project Planner</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         background: #0f0f0f; color: #e8e8e8; min-height: 100vh; }
  header { background: #1a1a2e; padding: 16px 20px; display: flex;
           align-items: center; gap: 12px; border-bottom: 1px solid #2a2a4a; position: sticky; top:0; z-index:10; }
  header h1 { font-size: 1.2rem; font-weight: 600; color: #7c83ff; }
  header span { font-size: 0.8rem; color: #888; }
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
  .add-form input, .add-form select { background: #0f0f0f; border: 1px solid #2a2a4a;
    color: #e8e8e8; border-radius: 8px; padding: 10px 12px; font-size: 0.9rem; width: 100%; }
  .btn { background: #7c83ff; color: #fff; border: none; border-radius: 8px;
         padding: 10px 16px; font-size: 0.9rem; cursor: pointer; font-weight: 500; }
  .btn:active { opacity: 0.8; }
  .btn-sm { padding: 6px 12px; font-size: 0.8rem; background: #2a2a4a; }
  .section-title { font-size: 0.75rem; font-weight: 600; color: #666; text-transform: uppercase;
                   letter-spacing: 0.05em; margin: 20px 0 8px; }
  .new-project-form { background: #1e1e2e; border-radius: 12px; padding: 16px;
                      border: 1px dashed #2a2a4a; margin-bottom: 12px; }
  .empty { text-align: center; padding: 40px 20px; color: #555; font-size: 0.9rem; }
  form { margin: 0; }
  .inline { display: flex; gap: 8px; }
  .inline input { flex: 1; }
</style>
</head>
<body>
<header>
  <div>
    <h1>🗂 PPT Planner</h1>
    <span>Personal Project Tracker</span>
  </div>
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
      <span class="task-title {{ 'done' if t.status == 'done' else '' }}">{{ t.title }}</span>
      <span class="priority p-{{ t.priority }}">{{ t.priority }}</span>
    </div>
    {% endfor %}

    <!-- Add task -->
    <form method="POST" action="/task/new" style="margin-top:12px">
      <input type="hidden" name="project_id" value="{{ p.id }}">
      <div class="inline">
        <input name="title" placeholder="Add task..." required>
        <select name="priority" style="width:90px">
          <option value="medium">Med</option>
          <option value="high">High</option>
          <option value="low">Low</option>
        </select>
        <button class="btn btn-sm" type="submit">+</button>
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
// Auto-refresh every 30s to pick up voice-command changes
setTimeout(() => location.reload(), 30000);
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
    if project_id and title:
        store.add_task(project_id, title, priority=priority)
    return redirect(url_for("index"))


@app.route("/task/<int:task_id>/toggle", methods=["POST"])
def toggle_task(task_id):
    task = store.get_task(task_id)
    if task:
        new_status = "todo" if task["status"] == "done" else "done"
        store.update_task_status(task_id, new_status)
    return redirect(url_for("index"))


@app.route("/api/projects")
def api_projects():
    return jsonify(store.list_projects())


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
