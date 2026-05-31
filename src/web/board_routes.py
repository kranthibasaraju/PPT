"""
src/web/board_routes.py — PPT Board: live aggregated dashboard API + page.

WHY one API endpoint for everything:
  Web, mobile, and the microcontroller all need the same data.
  /api/board is the single source of truth — every platform polls it.
  Logic lives here once, not scattered across clients.

ROUTES:
  GET /board          — full-page HTML dashboard (Story 2)
  GET /api/board      — JSON payload consumed by the page + all other clients

SECTIONS in /api/board:
  epics       — parsed from docs/EPIC_*.md (checkbox counting)
  reminders   — today's active reminders from notify.db
  habits      — today's habits + streaks from notify.db
  goals       — active goals + progress from notify.db
  projects    — open task count + next task per project from projects.db
  journal     — today's sleep/calories/work summary from journal.db
  relationship— XP level progress from notify.db
"""
from __future__ import annotations
import re
import logging
from datetime import datetime, date
from pathlib import Path
from flask import Blueprint, jsonify, render_template_string

log = logging.getLogger(__name__)

board_bp = Blueprint("board", __name__, url_prefix="/board")

# Project root — two levels up from this file (src/web/board_routes.py)
_ROOT = Path(__file__).parent.parent.parent


# ══════════════════════════════════════════════════════════════════════════════
# DATA COLLECTORS
# ══════════════════════════════════════════════════════════════════════════════

def _collect_epics() -> list[dict]:
    """
    Parse docs/EPIC_*.md files to extract epic name, story counts, and status.

    WHY markdown parsing instead of a DB:
      Epics live in .md files — they're the source of truth today.
      We parse checkbox lines: `- [x]` = done, `- [ ]` = open.
      When Plane is set up later this collector swaps to a Plane API call.
    """
    docs_dir = _ROOT / "docs"
    epics = []

    for f in sorted(docs_dir.glob("EPIC_*.md")):
        try:
            text = f.read_text(encoding="utf-8")

            # First H1 heading = epic name
            name_match = re.search(r"^#\s+(.+)", text, re.MULTILINE)
            name = name_match.group(1).strip() if name_match else f.stem

            # Count story-level checkboxes (lines starting with `| ✅` or `- [x]`)
            done  = len(re.findall(r"^\s*[-|]\s*\[x\]", text, re.MULTILINE | re.IGNORECASE))
            total = len(re.findall(r"^\s*[-|]\s*\[[x ]\]", text, re.MULTILINE | re.IGNORECASE))
            pct   = round(done / total * 100) if total else 0

            # Status from the Status line
            status_match = re.search(r"\*\*Status:\*\*\s*(.+)", text)
            raw_status   = status_match.group(1).strip() if status_match else ""
            if "Done" in raw_status or "Complete" in raw_status:
                status = "done"
            elif "Progress" in raw_status or "progress" in raw_status:
                status = "in_progress"
            else:
                status = "planned"

            epics.append({
                "name":           name,
                "file":           f.name,
                "stories_done":   done,
                "stories_total":  total,
                "pct":            pct,
                "status":         status,
            })
        except Exception as e:
            log.warning("Failed to parse epic %s: %s", f.name, e)

    return epics


def _collect_reminders() -> list[dict]:
    """
    Today's reminders from notify.db — both upcoming (active) and already
    fired today (active=0, fire_date=today). Recurring reminders always shown.

    WHY include fired-today:
      A board that only shows future items gives you no sense of what
      already happened today. Showing fired ones (greyed out) gives context.
    """
    try:
        import sqlite3
        from src.notify.store import _DB_PATH
        today = date.today().isoformat()
        con = sqlite3.connect(str(_DB_PATH))
        con.row_factory = sqlite3.Row
        rows = con.execute("""
            SELECT id, title, message, remind_at, repeat, fire_date, active
            FROM reminders
            WHERE
              (active = 1)                              -- all active (recurring + future once)
              OR (active = 0 AND fire_date = ?)         -- fired today (show as done)
            ORDER BY remind_at
        """, (today,)).fetchall()
        con.close()

        result = []
        for r in rows:
            result.append({
                "id":        r["id"],
                "title":     r["title"],
                "message":   r["message"] or "",
                "remind_at": r["remind_at"],
                "repeat":    r["repeat"],
                "fired":     r["active"] == 0,   # True = already fired today
            })
        return result
    except Exception as e:
        log.warning("Reminders collect failed: %s", e)
        return []


def _collect_habits() -> list[dict]:
    """
    All active habits with today's done status and current streak.
    """
    try:
        from src.notify import store as nstore
        habits = nstore.list_habits(active_only=True)
        result = []
        for h in habits:
            result.append({
                "id":         h["id"],
                "name":       h["name"],
                "remind_at":  h["remind_at"],
                "frequency":  h["frequency"],
                "streak":     nstore.habit_streak(h["id"]),
                "done_today": nstore.habit_done_today(h["id"]),
            })
        return sorted(result, key=lambda x: x["remind_at"])
    except Exception as e:
        log.warning("Habits collect failed: %s", e)
        return []


def _collect_goals() -> list[dict]:
    """
    Active goals with progress percentage and days until deadline.
    """
    try:
        from src.notify import store as nstore
        goals = nstore.list_goals(status="active")
        today = date.today()
        result = []
        for g in goals:
            days_left = None
            if g.get("deadline"):
                try:
                    d = date.fromisoformat(g["deadline"])
                    days_left = (d - today).days
                except ValueError:
                    pass
            result.append({
                "id":        g["id"],
                "title":     g["title"],
                "progress":  g["progress"],
                "deadline":  g.get("deadline"),
                "days_left": days_left,
            })
        return result
    except Exception as e:
        log.warning("Goals collect failed: %s", e)
        return []


def _collect_projects() -> list[dict]:
    """
    Active projects with open task count and the next open task title.
    """
    try:
        from src.projects import store as pstore
        projects = pstore.list_projects(status="active")
        result = []
        for p in projects:
            open_tasks = pstore.list_tasks(project_id=p["id"], status="open")
            next_task  = open_tasks[0]["title"] if open_tasks else None
            result.append({
                "id":         p["id"],
                "name":       p["name"],
                "open_tasks": len(open_tasks),
                "next_task":  next_task,
            })
        return sorted(result, key=lambda x: -x["open_tasks"])
    except Exception as e:
        log.warning("Projects collect failed: %s", e)
        return []


def _collect_journal_today() -> dict:
    """
    Today's snapshot: sleep, food (with meal names), work, mood.

    WHY include meal names not just calories:
      Most quick Telegram logs don't include calorie counts — just the food name.
      Showing "lentil rice, banana" is more useful than showing "0 cal".
    """
    try:
        from src.journal import store as jstore
        today = date.today().isoformat()

        sleep = jstore.get_sleep(today)
        sleep_hrs = round(sleep["duration_min"] / 60, 1) if sleep else None

        food_rows = jstore.food_today(today)
        meal_names    = [r["name"] for r in food_rows if r.get("name")]
        total_cal     = sum(r["calories"] for r in food_rows if r.get("calories")) or None
        meal_count    = len(food_rows)

        work_min = jstore.work_daily_total_min(today)
        work_hrs = round(work_min / 60, 1) if work_min else None

        from src.notify import store as nstore
        checkin = nstore.get_checkin(today)
        mood = checkin["mood"] if checkin else None

        return {
            "sleep_hrs":  sleep_hrs,
            "calories":   total_cal,
            "meal_count": meal_count,
            "meals":      meal_names,
            "work_hrs":   work_hrs,
            "mood":       mood,
        }
    except Exception as e:
        log.warning("Journal today collect failed: %s", e)
        return {"sleep_hrs": None, "calories": None, "meal_count": 0,
                "meals": [], "work_hrs": None, "mood": None}


def _collect_relationship() -> dict:
    """
    Current relationship XP level — how "close" PPT feels to Rana.
    """
    try:
        from src.notify import store as nstore
        from src.notify.relationship import get_level_progress
        profile = nstore.get_profile()
        xp = profile.get("relationship_xp", 0)
        return get_level_progress(xp)
    except Exception as e:
        log.warning("Relationship collect failed: %s", e)
        return {"level": "Stranger", "xp": 0, "next_at": 50, "pct": 0, "next_level": "Acquaintance"}


# ══════════════════════════════════════════════════════════════════════════════
# ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@board_bp.route("/api/board")
def api_board():
    """
    Single JSON endpoint consumed by the board page, mobile PWA, and
    microcontroller display. All sections fail independently — a broken
    journal DB won't take down the epics or reminders section.
    """
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "epics":        _collect_epics(),
        "reminders":    _collect_reminders(),
        "habits":       _collect_habits(),
        "goals":        _collect_goals(),
        "projects":     _collect_projects(),
        "journal_today":_collect_journal_today(),
        "relationship": _collect_relationship(),
    }
    return jsonify(payload)


@board_bp.route("/")
def board_page():
    return render_template_string(_BOARD_HTML)


# ── API: all projects with task counts ────────────────────────────────────────
@board_bp.route("/api/projects")
def api_projects():
    from src.projects import store as pstore
    projects = pstore.list_projects(status="active")
    result = []
    for p in projects:
        open_tasks = pstore.list_tasks(project_id=p["id"], status="open")
        done_tasks = pstore.list_tasks(project_id=p["id"], status="done")
        high = len([t for t in open_tasks if t["priority"] == "high"])
        result.append({
            "id": p["id"], "name": p["name"], "goal": p.get("goal",""),
            "open": len(open_tasks), "done": len(done_tasks), "high": high,
            "next": open_tasks[0]["title"] if open_tasks else None,
        })
    return jsonify(sorted(result, key=lambda x: -x["open"]))


# ── API: tasks for a project (sortable) ───────────────────────────────────────
@board_bp.route("/api/project/<int:project_id>/tasks")
def api_project_tasks(project_id):
    from src.projects import store as pstore
    from flask import request
    sort  = request.args.get("sort", "priority")
    filt  = request.args.get("status", "open")
    tasks = pstore.list_tasks(project_id=project_id, status=filt if filt != "all" else None)
    prio_order = {"high": 0, "medium": 1, "low": 2}
    if sort == "priority":
        tasks = sorted(tasks, key=lambda t: (prio_order.get(t.get("priority","low"), 2), t["id"]))
    elif sort == "status":
        tasks = sorted(tasks, key=lambda t: t.get("status",""))
    elif sort == "title":
        tasks = sorted(tasks, key=lambda t: t.get("title","").lower())
    p = pstore.get_project(project_id)
    return jsonify({"project": p, "tasks": tasks})


# ── API: single task detail ───────────────────────────────────────────────────
@board_bp.route("/api/task/<int:task_id>")
def api_task(task_id):
    from src.projects import store as pstore
    t = pstore.get_task(task_id)
    if not t:
        return jsonify({"error": "not found"}), 404
    p = pstore.get_project(t["project_id"]) if t.get("project_id") else None
    return jsonify({"task": t, "project": p})


# ── API: mark task done ───────────────────────────────────────────────────────
@board_bp.route("/api/task/<int:task_id>/done", methods=["POST"])
def api_task_done(task_id):
    from src.projects import store as pstore
    pstore.update_task_status(task_id, "done")
    return jsonify({"ok": True})


# ── API: journal history ──────────────────────────────────────────────────────
@board_bp.route("/api/journal")
def api_journal():
    from flask import request
    from src.journal import store as jstore
    from src.notify import store as nstore
    d = request.args.get("date", date.today().isoformat())
    return jsonify({
        "date":     d,
        "food":     jstore.food_today(d),
        "sleep":    jstore.get_sleep(d),
        "work":     jstore.work_today(d),
        "work_min": jstore.work_daily_total_min(d),
        "mood":     nstore.get_checkin(d),
    })


# ── Projects list page ────────────────────────────────────────────────────────
@board_bp.route("/projects")
def projects_page():
    return render_template_string(_PROJECTS_HTML)


# ── Project detail page ───────────────────────────────────────────────────────
@board_bp.route("/project/<int:project_id>")
def project_detail_page(project_id):
    return render_template_string(_PROJECT_DETAIL_HTML, project_id=project_id)


# ── Journal page ──────────────────────────────────────────────────────────────
@board_bp.route("/journal")
def journal_page():
    return render_template_string(_JOURNAL_HTML)


# ══════════════════════════════════════════════════════════════════════════════
# SHARED NAV + STYLES
# ══════════════════════════════════════════════════════════════════════════════

_SHARED_CSS = """
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#0d0d0d;--surface:#141414;--surface2:#1c1c1c;--border:#272727;
  --text:#ddd;--muted:#666;--accent:#7c83ff;--green:#22c55e;
  --orange:#f97316;--yellow:#f59e0b;--red:#ef4444;--purple:#a78bfa;
  --radius:10px;
}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
  background:var(--bg);color:var(--text);min-height:100vh;font-size:13px;}
a{color:inherit;text-decoration:none;}
/* Nav */
nav{background:var(--surface);border-bottom:1px solid var(--border);
  padding:10px 18px;display:flex;align-items:center;gap:6px;
  position:sticky;top:0;z-index:100;flex-wrap:wrap;}
.nav-logo{font-weight:700;color:var(--accent);font-size:.9rem;margin-right:10px;}
.nav-link{padding:5px 12px;border-radius:6px;font-size:.75rem;color:var(--muted);
  transition:background .15s,color .15s;}
.nav-link:hover{background:var(--surface2);color:var(--text);}
.nav-link.active{background:var(--surface2);color:var(--accent);}
/* Page container */
.page{max-width:1100px;margin:0 auto;padding:16px;}
.page-title{font-size:1.1rem;font-weight:700;margin-bottom:4px;}
.page-sub{font-size:.75rem;color:var(--muted);margin-bottom:18px;}
/* Card */
.card{background:var(--surface);border:1px solid var(--border);
  border-radius:var(--radius);padding:14px 16px;margin-bottom:10px;}
/* Priority badges */
.badge{display:inline-block;font-size:.65rem;font-weight:700;padding:2px 7px;
  border-radius:10px;text-transform:uppercase;letter-spacing:.04em;}
.badge-high{background:#2a0f0f;color:var(--red);}
.badge-medium{background:#1a1a0a;color:var(--yellow);}
.badge-low{background:#0f1a0f;color:var(--green);}
.badge-open{background:#12122a;color:var(--accent);}
.badge-done{background:#0f1a0f;color:var(--green);}
/* Table */
.tbl{width:100%;border-collapse:collapse;font-size:.78rem;}
.tbl th{text-align:left;padding:8px 10px;border-bottom:2px solid var(--border);
  color:var(--muted);font-size:.65rem;text-transform:uppercase;letter-spacing:.06em;
  cursor:pointer;user-select:none;white-space:nowrap;}
.tbl th:hover{color:var(--text);}
.tbl th.sorted{color:var(--accent);}
.tbl td{padding:9px 10px;border-bottom:1px solid var(--border);vertical-align:top;}
.tbl tr:hover td{background:var(--surface2);}
.tbl tr.done-row td{opacity:.45;}
/* Task title link */
.task-link{color:var(--text);cursor:pointer;}
.task-link:hover{color:var(--accent);}
/* Filters row */
.filters{display:flex;gap:8px;margin-bottom:14px;flex-wrap:wrap;align-items:center;}
.filter-btn{padding:5px 12px;border-radius:6px;border:1px solid var(--border);
  background:var(--surface);color:var(--muted);font-size:.72rem;cursor:pointer;
  transition:all .15s;}
.filter-btn.active,.filter-btn:hover{border-color:var(--accent);color:var(--accent);}
/* Modal */
.modal-overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,.7);
  z-index:200;align-items:flex-start;justify-content:center;padding:40px 16px;}
.modal-overlay.open{display:flex;}
.modal{background:var(--surface);border:1px solid var(--border);border-radius:12px;
  padding:22px;width:100%;max-width:640px;max-height:80vh;overflow-y:auto;
  position:relative;}
.modal-close{position:absolute;top:12px;right:14px;background:none;border:none;
  color:var(--muted);font-size:1.2rem;cursor:pointer;}
.modal-close:hover{color:var(--text);}
/* Journal cells */
.j-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:14px;}
.j-cell{background:var(--surface2);border-radius:8px;padding:10px 8px;text-align:center;}
.j-val{font-size:1.1rem;font-weight:700;}
.j-label{font-size:.62rem;color:var(--muted);margin-top:2px;}
.j-val.dim{color:var(--muted);font-size:.85rem;}
/* Journal log rows */
.log-row{display:flex;gap:10px;padding:8px 0;border-bottom:1px solid var(--border);
  align-items:baseline;font-size:.78rem;}
.log-row:last-child{border-bottom:none;}
.log-time{color:var(--muted);font-size:.7rem;min-width:48px;}
.log-text{flex:1;}
.log-meta{color:var(--muted);font-size:.7rem;}
/* Date nav */
.date-nav{display:flex;align-items:center;gap:10px;margin-bottom:16px;}
.date-nav button{padding:4px 10px;border-radius:6px;border:1px solid var(--border);
  background:var(--surface);color:var(--muted);cursor:pointer;font-size:.75rem;}
.date-nav button:hover{border-color:var(--accent);color:var(--accent);}
#date-display{font-weight:600;font-size:.85rem;min-width:140px;text-align:center;}
/* Progress bar */
.pbar{height:4px;background:var(--border);border-radius:2px;overflow:hidden;margin-top:5px;}
.pbar-fill{height:100%;border-radius:2px;background:var(--accent);}
/* Empty */
.empty{color:var(--muted);font-size:.75rem;padding:12px 0;text-align:center;}
/* Pulse */
#pulse{width:6px;height:6px;border-radius:50%;background:var(--green);
  animation:pulse 2s infinite;margin-left:auto;}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
@media(max-width:480px){
  .j-grid{grid-template-columns:repeat(2,1fr);}
  .tbl th:nth-child(4),.tbl td:nth-child(4){display:none;}
}
</style>
"""

_NAV = """
<nav>
  <span class="nav-logo">⚡ PPT</span>
  <a href="/"             class="nav-link" id="nav-planner">Planner</a>
  <a href="/board/"       class="nav-link" id="nav-board">Dashboard</a>
  <a href="/board/projects" class="nav-link" id="nav-projects">Projects</a>
  <a href="/board/journal"  class="nav-link" id="nav-journal">Journal</a>
  <div id="pulse"></div>
</nav>
<script>
// Highlight active nav link
(function(){
  const path = location.pathname.replace(/\/$/, '') || '/board';
  const map = {'/':'nav-planner','/board':'nav-board','/board/projects':'nav-projects','/board/journal':'nav-journal'};
  const key = Object.keys(map).find(k => path === k || path.startsWith(k+'/'));
  if(key) document.getElementById(map[key])?.classList.add('active');
})();
</script>
"""

# ══════════════════════════════════════════════════════════════════════════════
# PROJECTS LIST PAGE
# ══════════════════════════════════════════════════════════════════════════════

_PROJECTS_HTML = """<!DOCTYPE html><html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>PPT — Projects</title>""" + _SHARED_CSS + """</head><body>
""" + _NAV + """
<div class="page">
  <div class="page-title">Projects</div>
  <div class="page-sub" id="proj-sub">Loading…</div>
  <div id="proj-list"></div>
</div>
<script>
async function load() {
  const res  = await fetch('/board/api/projects');
  const data = await res.json();
  document.getElementById('proj-sub').textContent =
    data.length + ' active projects · ' + data.reduce((s,p)=>s+p.open,0) + ' open tasks';
  document.getElementById('proj-list').innerHTML = data.map(p => {
    const pct = p.done+p.open > 0 ? Math.round(p.done/(p.done+p.open)*100) : 0;
    return `<div class="card" style="cursor:pointer" onclick="location.href='/board/project/${p.id}'">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:6px">
        <span style="font-weight:600;font-size:.88rem;flex:1">${p.name}</span>
        ${p.high ? `<span class="badge badge-high">${p.high} high</span>` : ''}
        <span class="badge badge-open">${p.open} open</span>
        <span class="badge badge-done">${p.done} done</span>
      </div>
      ${p.goal ? `<div style="font-size:.72rem;color:var(--muted);margin-bottom:6px">${p.goal}</div>` : ''}
      ${p.next ? `<div style="font-size:.72rem;color:var(--muted)">▶ ${p.next}</div>` : ''}
      <div class="pbar" style="margin-top:8px">
        <div class="pbar-fill" style="width:${pct}%;background:${p.high?'var(--red)':'var(--accent)'}"></div>
      </div>
    </div>`;
  }).join('');
}
load();
</script></body></html>"""

# ══════════════════════════════════════════════════════════════════════════════
# PROJECT DETAIL PAGE
# ══════════════════════════════════════════════════════════════════════════════

_PROJECT_DETAIL_HTML = """<!DOCTYPE html><html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>PPT — Project</title>""" + _SHARED_CSS + """</head><body>
""" + _NAV + """
<div class="page">
  <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
    <a href="/board/projects" style="color:var(--muted);font-size:.8rem">← Projects</a>
  </div>
  <div class="page-title" id="proj-name">Loading…</div>
  <div class="page-sub"   id="proj-goal"></div>

  <div class="filters">
    <span style="font-size:.72rem;color:var(--muted)">Filter:</span>
    <button class="filter-btn active" onclick="setFilter('open',this)">Open</button>
    <button class="filter-btn" onclick="setFilter('done',this)">Done</button>
    <button class="filter-btn" onclick="setFilter('all',this)">All</button>
    <span style="margin-left:10px;font-size:.72rem;color:var(--muted)">Sort:</span>
    <button class="filter-btn active" onclick="setSort('priority',this)">Priority</button>
    <button class="filter-btn" onclick="setSort('title',this)">Title</button>
    <button class="filter-btn" onclick="setSort('status',this)">Status</button>
    <span id="task-count" style="margin-left:auto;font-size:.72rem;color:var(--muted)"></span>
  </div>

  <table class="tbl">
    <thead><tr>
      <th style="width:48%">Task</th>
      <th style="width:10%">Priority</th>
      <th style="width:10%">Status</th>
      <th style="width:32%">Notes</th>
    </tr></thead>
    <tbody id="task-body"></tbody>
  </table>
</div>

<!-- Task detail modal -->
<div class="modal-overlay" id="modal">
  <div class="modal">
    <button class="modal-close" onclick="closeModal()">✕</button>
    <div id="modal-content"></div>
  </div>
</div>

<script>
const PROJECT_ID = {{ project_id }};
let currentFilter = 'open';
let currentSort   = 'priority';

function setFilter(f, btn) {
  currentFilter = f;
  document.querySelectorAll('.filters .filter-btn').forEach(b => {
    if(['Open','Done','All'].includes(b.textContent)) b.classList.remove('active');
  });
  btn.classList.add('active');
  load();
}
function setSort(s, btn) {
  currentSort = s;
  document.querySelectorAll('.filters .filter-btn').forEach(b => {
    if(['Priority','Title','Status'].includes(b.textContent)) b.classList.remove('active');
  });
  btn.classList.add('active');
  load();
}

async function load() {
  const res  = await fetch(`/board/api/project/${PROJECT_ID}/tasks?sort=${currentSort}&status=${currentFilter}`);
  const data = await res.json();
  document.getElementById('proj-name').textContent = data.project?.name || 'Project';
  document.getElementById('proj-goal').textContent = data.project?.goal || '';
  document.getElementById('task-count').textContent = data.tasks.length + ' tasks';

  const pmap = {high:'badge-high',medium:'badge-medium',low:'badge-low'};
  const smap = {open:'badge-open',done:'badge-done'};

  document.getElementById('task-body').innerHTML = data.tasks.map(t => `
    <tr class="${t.status==='done'?'done-row':''}">
      <td>
        <span class="task-link" onclick="showTask(${t.id})">${t.title}</span>
      </td>
      <td><span class="badge ${pmap[t.priority]||'badge-low'}">${t.priority||'low'}</span></td>
      <td><span class="badge ${smap[t.status]||'badge-open'}">${t.status||'open'}</span></td>
      <td style="color:var(--muted);font-size:.7rem;line-height:1.5">
        ${t.notes ? t.notes.substring(0,90)+(t.notes.length>90?'…':'') : ''}
      </td>
    </tr>`).join('') || `<tr><td colspan="4" class="empty">No tasks</td></tr>`;
}

async function showTask(id) {
  const res  = await fetch(`/board/api/task/${id}`);
  const data = await res.json();
  const t    = data.task;
  const pmap = {high:'badge-high',medium:'badge-medium',low:'badge-low'};
  document.getElementById('modal-content').innerHTML = `
    <div style="display:flex;gap:8px;align-items:center;margin-bottom:12px;flex-wrap:wrap">
      <span class="badge ${pmap[t.priority]||'badge-low'}">${t.priority||'low'}</span>
      <span class="badge ${t.status==='done'?'badge-done':'badge-open'}">${t.status}</span>
      ${t.status!=='done'?`<button onclick="markDone(${t.id})" style="margin-left:auto;padding:5px 14px;border-radius:6px;border:1px solid var(--green);background:none;color:var(--green);cursor:pointer;font-size:.75rem">✓ Mark Done</button>`:''}
    </div>
    <div style="font-size:.95rem;font-weight:600;margin-bottom:10px;line-height:1.4">${t.title}</div>
    ${t.notes ? `<div style="font-size:.78rem;color:var(--muted);line-height:1.7;white-space:pre-wrap;background:var(--surface2);padding:10px 12px;border-radius:6px">${t.notes}</div>` : ''}
    ${t.due_date ? `<div style="margin-top:10px;font-size:.72rem;color:var(--muted)">Due: ${t.due_date}</div>` : ''}
  `;
  document.getElementById('modal').classList.add('open');
}

async function markDone(id) {
  await fetch(`/board/api/task/${id}/done`, {method:'POST'});
  closeModal();
  load();
}

function closeModal() {
  document.getElementById('modal').classList.remove('open');
}
document.getElementById('modal').addEventListener('click', e => {
  if(e.target === document.getElementById('modal')) closeModal();
});

load();
</script></body></html>"""

# ══════════════════════════════════════════════════════════════════════════════
# JOURNAL PAGE
# ══════════════════════════════════════════════════════════════════════════════

_JOURNAL_HTML = """<!DOCTYPE html><html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>PPT — Journal</title>""" + _SHARED_CSS + """</head><body>
""" + _NAV + """
<div class="page">
  <div class="page-title">Journal</div>

  <div class="date-nav">
    <button onclick="changeDate(-1)">← Prev</button>
    <span id="date-display"></span>
    <button onclick="changeDate(1)" id="next-btn">Next →</button>
    <button onclick="goToday()" style="margin-left:4px">Today</button>
  </div>

  <!-- Stats strip -->
  <div class="j-grid" id="stats-grid">
    <div class="j-cell"><div class="j-val dim">—</div><div class="j-label">Sleep</div></div>
    <div class="j-cell"><div class="j-val dim">—</div><div class="j-label">Food</div></div>
    <div class="j-cell"><div class="j-val dim">—</div><div class="j-label">Work</div></div>
    <div class="j-cell"><div class="j-val dim">—</div><div class="j-label">Mood</div></div>
  </div>

  <!-- Food logs -->
  <div class="card">
    <div style="font-size:.65rem;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin-bottom:10px">🍽 Food</div>
    <div id="food-list"><div class="empty">No food logged</div></div>
  </div>

  <!-- Work sessions -->
  <div class="card">
    <div style="font-size:.65rem;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin-bottom:10px">💼 Work Sessions</div>
    <div id="work-list"><div class="empty">No sessions logged</div></div>
  </div>

  <!-- Sleep -->
  <div class="card">
    <div style="font-size:.65rem;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin-bottom:10px">😴 Sleep</div>
    <div id="sleep-info"><div class="empty">No sleep logged</div></div>
  </div>

  <!-- Mood check-in -->
  <div class="card">
    <div style="font-size:.65rem;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin-bottom:10px">💭 Mood Check-in</div>
    <div id="mood-info"><div class="empty">No check-in logged</div></div>
  </div>

  <div style="margin-top:10px;font-size:.7rem;color:var(--muted);text-align:center">
    Log via Telegram: /food · /sleep · /work start|end · /digest
  </div>
</div>

<script>
const today = new Date().toISOString().split('T')[0];
let currentDate = today;

function fmt(d) {
  const dt = new Date(d + 'T12:00:00');
  const isToday = d === today;
  const opts = {weekday:'long',month:'long',day:'numeric'};
  return (isToday ? 'Today — ' : '') + dt.toLocaleDateString(undefined, opts);
}

function changeDate(delta) {
  const dt = new Date(currentDate + 'T12:00:00');
  dt.setDate(dt.getDate() + delta);
  const nd = dt.toISOString().split('T')[0];
  if(nd > today) return;
  currentDate = nd;
  load();
}
function goToday() { currentDate = today; load(); }

const moodEmoji = {1:'😞',2:'😕',3:'😐',4:'🙂',5:'😊'};
const moodLabel = {1:'Rough',2:'Tough',3:'Okay',4:'Good',5:'Great'};

async function load() {
  document.getElementById('date-display').textContent = fmt(currentDate);
  document.getElementById('next-btn').disabled = currentDate >= today;

  const res  = await fetch('/board/api/journal?date=' + currentDate);
  const data = await res.json();

  // Stats strip
  const sleep = data.sleep;
  const sleepHrs = sleep ? (sleep.duration_min/60).toFixed(1)+'h' : null;
  const foodCount = data.food?.length || 0;
  const workHrs = data.work_min ? (data.work_min/60).toFixed(1)+'h' : null;
  const mood = data.mood?.mood;
  document.getElementById('stats-grid').innerHTML = `
    <div class="j-cell"><div class="j-val ${sleepHrs?'':'dim'}">${sleepHrs||'—'}</div><div class="j-label">Sleep</div></div>
    <div class="j-cell"><div class="j-val ${foodCount?'':'dim'}">${foodCount||'—'}</div><div class="j-label">Meals</div></div>
    <div class="j-cell"><div class="j-val ${workHrs?'':'dim'}">${workHrs||'—'}</div><div class="j-label">Work</div></div>
    <div class="j-cell"><div class="j-val ${mood?'':'dim'}">${mood?moodEmoji[mood]:'—'}</div><div class="j-label">Mood</div></div>
  `;

  // Food
  document.getElementById('food-list').innerHTML = data.food?.length
    ? data.food.map(f => `
        <div class="log-row">
          <span class="log-time">${f.meal_type||'meal'}</span>
          <span class="log-text">${f.name}</span>
          <span class="log-meta">${f.calories?f.calories+' cal':''} ${f.protein_g?'P:'+f.protein_g+'g':''}</span>
        </div>`).join('')
    : '<div class="empty">No food logged — try /food lunch oatmeal 350</div>';

  // Work
  document.getElementById('work-list').innerHTML = data.work?.length
    ? data.work.map(s => {
        const dur = s.duration_min ? Math.floor(s.duration_min/60)+'h '+(s.duration_min%60)+'m' : 'ongoing';
        return `<div class="log-row">
          <span class="log-time">${s.start_time||''}</span>
          <span class="log-text">${s.task||'Work session'}</span>
          <span class="log-meta">${dur}</span>
        </div>`;
      }).join('')
    : '<div class="empty">No sessions — try /work start task name</div>';

  // Sleep
  document.getElementById('sleep-info').innerHTML = sleep
    ? `<div class="log-row">
        <span class="log-time">${sleep.bedtime||'—'}</span>
        <span class="log-text">${(sleep.duration_min/60).toFixed(1)}h sleep${sleep.waketime?' · wake '+sleep.waketime:''}</span>
        <span class="log-meta">${sleep.quality?'Quality '+sleep.quality+'/5':''}</span>
       </div>`
    : '<div class="empty">No sleep logged — try /sleep 7.5 4</div>';

  // Mood
  const m = data.mood;
  document.getElementById('mood-info').innerHTML = m
    ? `<div style="display:flex;align-items:center;gap:12px;padding:8px 0">
        <span style="font-size:2rem">${moodEmoji[m.mood]}</span>
        <div>
          <div style="font-weight:600">${moodLabel[m.mood]} (${m.mood}/5)</div>
          ${m.note?`<div style="font-size:.75rem;color:var(--muted);margin-top:3px">${m.note}</div>`:''}
        </div>
       </div>`
    : '<div class="empty">No check-in — try /checkin or tap ✓ on evening prompt</div>';
}

load();
</script></body></html>"""

# ══════════════════════════════════════════════════════════════════════════════
# BOARD HTML
# ══════════════════════════════════════════════════════════════════════════════

_BOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PPT Board</title>
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="PPT Board">
<meta name="theme-color" content="#0d0d0d">
<style>
/* ── Reset & tokens ─────────────────────────────────────────────────────── */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
:root {
  --bg:       #0d0d0d;
  --surface:  #141414;
  --surface2: #1c1c1c;
  --border:   #272727;
  --text:     #ddd;
  --muted:    #666;
  --accent:   #7c83ff;
  --green:    #22c55e;
  --orange:   #f97316;
  --yellow:   #f59e0b;
  --red:      #ef4444;
  --purple:   #a78bfa;
  --radius:   10px;
}
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  background: var(--bg); color: var(--text);
  min-height: 100vh; font-size: 13px;
}

/* ── Header ─────────────────────────────────────────────────────────────── */
header {
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  padding: 12px 18px;
  display: flex; align-items: center; justify-content: space-between;
  position: sticky; top: 0; z-index: 10;
}
.logo { font-weight: 700; color: var(--accent); font-size: 0.95rem; }
#status-bar { font-size: 0.68rem; color: var(--muted); display: flex; align-items: center; gap: 6px; }
#pulse { width: 6px; height: 6px; border-radius: 50%; background: var(--green);
         animation: pulse 2s infinite; }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.3} }

/* ── Grid layout ────────────────────────────────────────────────────────── */
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 14px;
  padding: 16px;
  max-width: 1200px;
  margin: 0 auto;
}

/* ── Section card ───────────────────────────────────────────────────────── */
.section {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14px;
}
.section-title {
  font-size: 0.65rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: .08em; color: var(--muted); margin-bottom: 12px;
  display: flex; align-items: center; gap: 6px;
}
.section-title span { font-size: 0.85rem; }

/* ── Epic rows ──────────────────────────────────────────────────────────── */
.epic-row { margin-bottom: 10px; }
.epic-header { display: flex; justify-content: space-between;
               align-items: baseline; margin-bottom: 4px; }
.epic-name { font-size: 0.8rem; font-weight: 600; }
.epic-pct  { font-size: 0.7rem; color: var(--muted); }
.progress-bar { height: 5px; background: var(--border); border-radius: 3px; overflow: hidden; }
.progress-fill { height: 100%; border-radius: 3px; transition: width .4s ease; }
.status-in_progress .progress-fill { background: var(--accent); }
.status-done        .progress-fill { background: var(--green); }
.status-planned     .progress-fill { background: var(--muted); }
.epic-meta { font-size: 0.65rem; color: var(--muted); margin-top: 3px; }

/* ── Reminder rows ──────────────────────────────────────────────────────── */
.reminder-row {
  display: flex; align-items: flex-start; gap: 10px;
  padding: 8px 0; border-bottom: 1px solid var(--border);
}
.reminder-row:last-child { border-bottom: none; }
.reminder-time { font-size: 0.75rem; color: var(--orange);
                 font-variant-numeric: tabular-nums; min-width: 38px; }
.reminder-title { font-size: 0.8rem; font-weight: 500; }
.reminder-msg   { font-size: 0.7rem; color: var(--muted); margin-top: 2px; }
.repeat-badge {
  font-size: 0.6rem; padding: 1px 5px; border-radius: 4px;
  background: var(--surface2); color: var(--muted);
  margin-left: auto; white-space: nowrap; align-self: center;
}

/* ── Habit grid ─────────────────────────────────────────────────────────── */
.habit-list { display: flex; flex-direction: column; gap: 8px; }
.habit-row {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 10px; border-radius: 8px;
  background: var(--surface2); cursor: pointer;
  transition: background .15s;
}
.habit-row:hover { background: #222; }
.habit-check {
  width: 18px; height: 18px; border-radius: 50%;
  border: 2px solid var(--border);
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0; font-size: 10px;
  transition: all .15s;
}
.habit-check.done { background: var(--green); border-color: var(--green); }
.habit-info { flex: 1; }
.habit-name  { font-size: 0.8rem; font-weight: 500; }
.habit-meta  { font-size: 0.68rem; color: var(--muted); }
.streak-badge {
  font-size: 0.68rem; color: var(--orange); font-weight: 600;
}

/* ── Goal rows ──────────────────────────────────────────────────────────── */
.goal-row { margin-bottom: 10px; }
.goal-header { display: flex; justify-content: space-between; margin-bottom: 4px; }
.goal-title  { font-size: 0.8rem; font-weight: 500; }
.goal-pct    { font-size: 0.7rem; color: var(--muted); }
.goal-fill   { background: var(--yellow); }
.goal-meta   { font-size: 0.65rem; color: var(--muted); margin-top: 3px; }

/* ── Project rows ───────────────────────────────────────────────────────── */
.project-row {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 0; border-bottom: 1px solid var(--border);
}
.project-row:last-child { border-bottom: none; }
.project-name { font-size: 0.8rem; font-weight: 600; flex: 1; }
.project-count {
  font-size: 0.7rem; color: var(--muted);
  background: var(--surface2); padding: 2px 7px; border-radius: 10px;
}
.project-next { font-size: 0.68rem; color: var(--muted); margin-top: 2px; }

/* ── Journal strip ──────────────────────────────────────────────────────── */
.journal-grid {
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px;
}
.journal-cell {
  background: var(--surface2); border-radius: 8px;
  padding: 10px 8px; text-align: center;
}
.journal-value { font-size: 1.1rem; font-weight: 700; color: var(--text); }
.journal-label { font-size: 0.62rem; color: var(--muted); margin-top: 2px; }
.journal-value.dim { color: var(--muted); font-size: 0.8rem; }

/* ── Relationship bar ───────────────────────────────────────────────────── */
.rel-header { display: flex; justify-content: space-between; margin-bottom: 8px; }
.rel-level  { font-size: 0.85rem; font-weight: 700; color: var(--purple); }
.rel-xp     { font-size: 0.7rem; color: var(--muted); }
.rel-fill   { background: var(--purple); }
.rel-next   { font-size: 0.65rem; color: var(--muted); margin-top: 5px;
              display: flex; justify-content: space-between; }

/* ── Empty state ────────────────────────────────────────────────────────── */
.empty { color: var(--muted); font-size: 0.75rem; padding: 6px 0; }

/* ── Loading skeleton ───────────────────────────────────────────────────── */
.skeleton { background: var(--surface2); border-radius: 4px; height: 12px;
            animation: shimmer 1.5s infinite; margin-bottom: 8px; }
@keyframes shimmer { 0%,100%{opacity:.4} 50%{opacity:.8} }

/* ── Mobile ─────────────────────────────────────────────────────────────── */
@media (max-width: 480px) {
  .grid { grid-template-columns: 1fr; padding: 10px; gap: 10px; }
  header { padding: 10px 14px; }
  .journal-grid { grid-template-columns: repeat(2, 1fr); }
}
</style>
</head>
<body>

<nav style="background:var(--surface);border-bottom:1px solid var(--border);padding:10px 18px;display:flex;align-items:center;gap:6px;position:sticky;top:0;z-index:100">
  <span style="font-weight:700;color:var(--accent);font-size:.9rem;margin-right:10px">⚡ PPT</span>
  <a href="/board/"        style="padding:5px 12px;border-radius:6px;font-size:.75rem;color:var(--accent);background:var(--surface2)">Dashboard</a>
  <a href="/board/projects" style="padding:5px 12px;border-radius:6px;font-size:.75rem;color:var(--muted)">Projects</a>
  <a href="/board/journal"  style="padding:5px 12px;border-radius:6px;font-size:.75rem;color:var(--muted)">Journal</a>
  <div id="refresh-badge" style="width:7px;height:7px;border-radius:50%;background:var(--green);margin-left:auto;animation:pulse 2s infinite"></div>
</nav>

<header style="background:var(--surface);border-bottom:1px solid var(--border);padding:10px 18px;display:flex;align-items:center;justify-content:space-between">
  <div class="logo" style="display:none">⚡ PPT Board</div>
  <div id="status-bar" style="font-size:.68rem;color:var(--muted);display:flex;align-items:center;gap:6px">
    <span id="last-updated">loading…</span>
  </div>
</header>

<div class="grid" id="board">
  <!-- Epics -->
  <div class="section" id="sec-epics">
    <div class="section-title"><span>🗺</span> Epics</div>
    <div id="epics-body"><div class="skeleton"></div><div class="skeleton" style="width:70%"></div></div>
  </div>

  <!-- Reminders -->
  <div class="section" id="sec-reminders">
    <div class="section-title"><span>⏰</span> Today's Reminders</div>
    <div id="reminders-body"><div class="skeleton"></div><div class="skeleton" style="width:80%"></div></div>
  </div>

  <!-- Habits -->
  <div class="section" id="sec-habits">
    <div class="section-title"><span>🔄</span> Habits</div>
    <div id="habits-body"><div class="skeleton"></div><div class="skeleton" style="width:60%"></div></div>
  </div>

  <!-- Personal goals -->
  <div class="section" id="sec-goals">
    <div class="section-title"><span>🎯</span> Personal Goals</div>
    <div id="goals-body"><div class="skeleton"></div><div class="skeleton" style="width:75%"></div></div>
  </div>

  <!-- Projects -->
  <div class="section" id="sec-projects">
    <div class="section-title"><span>📁</span> Projects</div>
    <div id="projects-body"><div class="skeleton"></div><div class="skeleton" style="width:65%"></div></div>
  </div>

  <!-- Journal Today -->
  <div class="section" id="sec-journal">
    <div class="section-title"><span>📓</span> Today</div>
    <div id="journal-body"><div class="skeleton"></div></div>
  </div>

  <!-- Relationship -->
  <div class="section" id="sec-rel">
    <div class="section-title"><span>💜</span> Relationship</div>
    <div id="rel-body"><div class="skeleton"></div></div>
  </div>
</div>

<script>
const REFRESH_MS = 30_000;

// ── Render helpers ────────────────────────────────────────────────────────────

function renderEpics(epics) {
  if (!epics.length) return '<p class="empty">No epics found in docs/</p>';
  return epics.map(e => `
    <div class="epic-row status-${e.status}">
      <div class="epic-header">
        <span class="epic-name">${e.name}</span>
        <span class="epic-pct">${e.pct}%</span>
      </div>
      <div class="progress-bar">
        <div class="progress-fill" style="width:${e.pct}%"></div>
      </div>
      <div class="epic-meta">${e.stories_done}/${e.stories_total} stories · ${e.status.replace('_',' ')}</div>
    </div>`).join('');
}

function renderReminders(reminders) {
  if (!reminders.length) return '<p class="empty">No reminders today — add one via Telegram:<br><code>/remind add 14:30 Title</code></p>';
  return reminders.map(r => `
    <div class="reminder-row" style="${r.fired ? 'opacity:.45' : ''}">
      <span class="reminder-time" style="${r.fired ? 'text-decoration:line-through' : ''}">${r.remind_at}</span>
      <div style="flex:1">
        <div class="reminder-title">${r.fired ? '✓ ' : ''}${r.title}</div>
        ${r.message ? `<div class="reminder-msg">${r.message}</div>` : ''}
      </div>
      ${r.repeat !== 'once' ? `<span class="repeat-badge">${r.repeat}</span>` : (r.fired ? '<span class="repeat-badge">fired</span>' : '')}
    </div>`).join('');
}

function renderHabits(habits) {
  if (!habits.length) return '<p class="empty">No habits yet — try /habit add Morning walk 07:00</p>';
  return '<div class="habit-list">' + habits.map(h => `
    <div class="habit-row" onclick="markHabitDone(${h.id})" title="Tap to mark done">
      <div class="habit-check ${h.done_today ? 'done' : ''}">${h.done_today ? '✓' : ''}</div>
      <div class="habit-info">
        <div class="habit-name">${h.name}</div>
        <div class="habit-meta">${h.remind_at} · ${h.frequency}</div>
      </div>
      ${h.streak > 0 ? `<span class="streak-badge">🔥${h.streak}d</span>` : ''}
    </div>`).join('') + '</div>';
}

function renderGoals(goals) {
  if (!goals.length) return '<p class="empty">No active personal goals</p>';
  return goals.map(g => {
    const deadlineStr = g.days_left !== null
      ? (g.days_left < 0 ? '⚠️ overdue' : g.days_left === 0 ? '🚨 due today' : `📅 ${g.days_left}d left`)
      : '';
    return `
    <div class="goal-row">
      <div class="goal-header">
        <span class="goal-title">${g.title}</span>
        <span class="goal-pct">${g.progress}%</span>
      </div>
      <div class="progress-bar">
        <div class="progress-fill goal-fill" style="width:${g.progress}%"></div>
      </div>
      <div class="goal-meta">${deadlineStr}</div>
    </div>`;
  }).join('');
}

function renderProjects(projects) {
  if (!projects.length) return '<p class="empty">No active projects</p>';
  return projects.map(p => `
    <div class="project-row" style="cursor:pointer" onclick="location.href='/board/project/${p.id}'">
      <div style="flex:1">
        <div class="project-name">${p.name}</div>
        ${p.next_task ? `<div class="project-next">▶ ${p.next_task}</div>` : ''}
      </div>
      <span class="project-count">${p.open_tasks} open</span>
    </div>`).join('');
}

function renderJournal(j) {
  const val = (v, unit) => v !== null ? `<span class="journal-value">${v}${unit}</span>` : '<span class="journal-value dim">—</span>';
  const moodEmoji = {1:'😞',2:'😕',3:'😐',4:'🙂',5:'😊'};

  // Food cell: show calorie count if present, else meal count, else —
  const foodValue = j.calories !== null
    ? `<span class="journal-value">${j.calories}</span>`
    : j.meal_count > 0
      ? `<span class="journal-value" style="font-size:.85rem">${j.meal_count} meal${j.meal_count>1?'s':''}</span>`
      : '<span class="journal-value dim">—</span>';

  // Show meal names as a small subtitle if logged
  const mealNames = j.meals && j.meals.length
    ? `<div class="journal-label" style="margin-top:3px;line-height:1.4">${j.meals.join(', ')}</div>`
    : '';

  return `<div class="journal-grid">
    <div class="journal-cell">${val(j.sleep_hrs,'h')}<div class="journal-label">Sleep</div></div>
    <div class="journal-cell">${foodValue}<div class="journal-label">Food</div>${mealNames}</div>
    <div class="journal-cell">${val(j.work_hrs,'h')}<div class="journal-label">Work</div></div>
    <div class="journal-cell">
      ${j.mood ? `<span class="journal-value">${moodEmoji[j.mood]}</span>` : '<span class="journal-value dim">—</span>'}
      <div class="journal-label">Mood</div>
    </div>
  </div>`;
}

function renderRelationship(r) {
  return `
    <div class="rel-header">
      <span class="rel-level">${r.level}</span>
      <span class="rel-xp">${r.xp} XP</span>
    </div>
    <div class="progress-bar" style="height:7px">
      <div class="progress-fill rel-fill" style="width:${r.pct}%"></div>
    </div>
    <div class="rel-next">
      <span>Current: ${r.level}</span>
      ${r.next_level ? `<span>Next: ${r.next_level} @ ${r.next_at} XP</span>` : '<span>Max level 💙</span>'}
    </div>`;
}

// ── Actions ───────────────────────────────────────────────────────────────────

async function markHabitDone(id) {
  try {
    await fetch(`/notify/habit/done`, {
      method: 'POST',
      headers: {'Content-Type':'application/x-www-form-urlencoded'},
      body: `habit_id=${id}`
    });
    fetchBoard(); // Refresh immediately
  } catch(e) { console.warn('markHabitDone failed', e); }
}

// ── Fetch & patch DOM ─────────────────────────────────────────────────────────

async function fetchBoard() {
  try {
    const res  = await fetch('/board/api/board');
    const data = await res.json();

    document.getElementById('epics-body').innerHTML     = renderEpics(data.epics);
    document.getElementById('reminders-body').innerHTML = renderReminders(data.reminders);
    document.getElementById('habits-body').innerHTML    = renderHabits(data.habits);
    document.getElementById('goals-body').innerHTML     = renderGoals(data.goals);
    document.getElementById('projects-body').innerHTML  = renderProjects(data.projects);
    document.getElementById('journal-body').innerHTML   = renderJournal(data.journal_today);
    document.getElementById('rel-body').innerHTML       = renderRelationship(data.relationship);

    const t = new Date(data.generated_at);
    document.getElementById('last-updated').textContent =
      'updated ' + t.toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'});

    document.getElementById('pulse').style.background = 'var(--green)';
  } catch(e) {
    console.error('Board fetch failed', e);
    document.getElementById('pulse').style.background = 'var(--red)';
    document.getElementById('last-updated').textContent = 'fetch failed';
  }
}

// Initial load + polling
fetchBoard();
setInterval(fetchBoard, REFRESH_MS);
</script>
</body>
</html>"""
