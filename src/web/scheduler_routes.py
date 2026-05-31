"""Flask Blueprint for the Google-backed PPT scheduler."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from flask import Blueprint, jsonify, redirect, render_template_string, request, url_for

from src.scheduler import store as scheduler_store
from src.scheduler import service as scheduler_service
from src.scheduler.google_client import CalendarApiClient
from src.scheduler.service import SchedulerError, SchedulerValidationError

scheduler_bp = Blueprint("scheduler", __name__, url_prefix="/scheduler")
scheduler_store.init_db()


_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PPT Board — Scheduler</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
:root {
  --bg: #0f0f0f;
  --surface: #171726;
  --surface2: #1d1d31;
  --border: #2b2b47;
  --text: #ececff;
  --muted: #8b8bb0;
  --accent: #4cc9f0;
  --accent2: #7c83ff;
  --success: #4ade80;
  --warn: #fbbf24;
  --danger: #f87171;
}
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  background:
    radial-gradient(circle at top right, rgba(76, 201, 240, 0.18), transparent 32%),
    radial-gradient(circle at top left, rgba(124, 131, 255, 0.14), transparent 30%),
    var(--bg);
  color: var(--text);
  min-height: 100vh;
}
header {
  position: sticky; top: 0; z-index: 20;
  display: flex; align-items: center; justify-content: space-between;
  padding: 16px 22px;
  background: rgba(15, 15, 15, 0.92);
  backdrop-filter: blur(18px);
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}
.title-wrap h1 { font-size: 1.2rem; color: var(--accent); letter-spacing: 0.02em; }
.title-wrap p { font-size: 0.78rem; color: var(--muted); margin-top: 3px; }
.nav { display: flex; gap: 10px; }
.nav a {
  color: var(--muted); text-decoration: none; font-size: 0.8rem;
  border: 1px solid var(--border); border-radius: 999px; padding: 7px 12px;
}
.nav a:hover { color: var(--text); border-color: var(--accent2); }
.container { max-width: 1180px; margin: 0 auto; padding: 24px 18px 40px; }
.flash {
  padding: 12px 14px; border-radius: 12px; margin-bottom: 18px; font-size: 0.9rem;
  border: 1px solid transparent;
}
.flash.ok { background: rgba(74, 222, 128, 0.1); border-color: rgba(74, 222, 128, 0.3); color: #c7f9d8; }
.flash.err { background: rgba(248, 113, 113, 0.1); border-color: rgba(248, 113, 113, 0.3); color: #ffd4d4; }
.flash.warn { background: rgba(251, 191, 36, 0.1); border-color: rgba(251, 191, 36, 0.3); color: #ffe6ac; }
.grid { display: grid; grid-template-columns: 360px minmax(0, 1fr); gap: 18px; }
.stack { display: flex; flex-direction: column; gap: 18px; }
.card {
  background: linear-gradient(180deg, rgba(28, 28, 47, 0.96), rgba(22, 22, 36, 0.98));
  border: 1px solid rgba(255,255,255,0.06);
  border-radius: 18px;
  box-shadow: 0 16px 45px rgba(0,0,0,0.25);
  overflow: hidden;
}
.card-header {
  padding: 16px 18px 12px;
  border-bottom: 1px solid rgba(255,255,255,0.05);
}
.eyebrow { font-size: 0.68rem; letter-spacing: 0.12em; text-transform: uppercase; color: var(--muted); }
.card-title { font-size: 1rem; font-weight: 650; margin-top: 5px; }
.card-body { padding: 16px 18px 18px; }
.meta {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  font-size: 0.82rem; color: var(--muted);
}
.pill {
  display: inline-flex; align-items: center; gap: 7px;
  padding: 6px 11px; border-radius: 999px; font-size: 0.76rem;
  background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.06);
}
.pill.ok { color: #ccffdd; border-color: rgba(74,222,128,0.28); background: rgba(74,222,128,0.10); }
.pill.warn { color: #ffe8a8; border-color: rgba(251,191,36,0.25); background: rgba(251,191,36,0.08); }
.pill.err { color: #ffd4d4; border-color: rgba(248,113,113,0.25); background: rgba(248,113,113,0.08); }
.note {
  font-size: 0.82rem; color: var(--muted); line-height: 1.5;
  background: rgba(255,255,255,0.03); border-radius: 12px; padding: 12px 13px; margin-top: 12px;
}
label { display: block; font-size: 0.75rem; color: var(--muted); margin-bottom: 5px; }
input, select, textarea, button {
  font-family: inherit;
}
input, select, textarea {
  width: 100%;
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid var(--border);
  background: rgba(15,15,15,0.82);
  color: var(--text);
  font-size: 0.88rem;
}
textarea { min-height: 90px; resize: vertical; }
.field { margin-bottom: 12px; }
.row2, .row3 {
  display: grid; gap: 10px;
}
.row2 { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.row3 { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.checkbox {
  display: flex; align-items: center; gap: 8px; margin-bottom: 12px; color: var(--muted); font-size: 0.84rem;
}
.checkbox input { width: auto; }
.btn-row { display: flex; gap: 10px; flex-wrap: wrap; }
.btn {
  border: 1px solid transparent; border-radius: 12px;
  padding: 10px 14px; font-size: 0.86rem; font-weight: 600;
  cursor: pointer;
}
.btn.primary { background: linear-gradient(135deg, var(--accent), var(--accent2)); color: #081018; }
.btn.secondary { background: rgba(255,255,255,0.05); color: var(--text); border-color: rgba(255,255,255,0.06); }
.btn.danger { background: rgba(248,113,113,0.1); color: #ffd6d6; border-color: rgba(248,113,113,0.24); }
.btn.warn { background: rgba(251,191,36,0.12); color: #ffe8a8; border-color: rgba(251,191,36,0.24); }
.btn.link { background: transparent; color: var(--accent); border-color: rgba(76,201,240,0.22); text-decoration: none; display: inline-flex; align-items: center; }
.agenda-toolbar {
  display: flex; gap: 10px; align-items: end; flex-wrap: wrap;
}
.agenda-toolbar .field { flex: 1; min-width: 130px; margin-bottom: 0; }
.agenda-list { display: flex; flex-direction: column; gap: 12px; }
.event {
  padding: 14px 15px;
  border-radius: 16px;
  border: 1px solid rgba(255,255,255,0.06);
  background: rgba(255,255,255,0.035);
}
.event-head { display: flex; gap: 12px; justify-content: space-between; align-items: start; }
.event-title { font-weight: 650; font-size: 0.96rem; }
.event-time { font-size: 0.82rem; color: #dbeafe; margin-top: 5px; }
.event-meta { font-size: 0.78rem; color: var(--muted); margin-top: 8px; line-height: 1.45; }
.event-actions { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }
.empty {
  padding: 28px 16px; text-align: center; color: var(--muted); font-size: 0.9rem;
  border: 1px dashed rgba(255,255,255,0.08); border-radius: 16px;
}
.conflict-list, .import-list { display: flex; flex-direction: column; gap: 10px; margin-top: 12px; }
.conflict, .import-item {
  padding: 11px 12px; border-radius: 14px;
  background: rgba(255,255,255,0.035); border: 1px solid rgba(255,255,255,0.06);
}
.conflict strong, .import-item strong { display: block; font-size: 0.88rem; }
.conflict small, .import-item small { display: block; margin-top: 5px; color: var(--muted); line-height: 1.45; }
.anchor-card { scroll-margin-top: 90px; }
.todo-list { display: flex; flex-direction: column; gap: 10px; margin-top: 14px; }
.todo-item {
  padding: 12px 13px; border-radius: 14px;
  background: rgba(255,255,255,0.035); border: 1px solid rgba(255,255,255,0.06);
}
.todo-top { display: flex; gap: 10px; justify-content: space-between; align-items: start; }
.todo-top strong { font-size: 0.9rem; }
.todo-detail { color: var(--muted); font-size: 0.8rem; line-height: 1.45; margin-top: 6px; }
.todo-action { margin-top: 10px; }
.state-pill {
  display: inline-flex; align-items: center;
  padding: 4px 8px; border-radius: 999px; font-size: 0.72rem;
  text-transform: uppercase; letter-spacing: 0.05em;
}
.state-pill.done { color: #ccffdd; background: rgba(74,222,128,0.12); border: 1px solid rgba(74,222,128,0.24); }
.state-pill.pending { color: #ffe8a8; background: rgba(251,191,36,0.12); border: 1px solid rgba(251,191,36,0.24); }
.state-pill.blocked { color: #ffd4d4; background: rgba(248,113,113,0.12); border: 1px solid rgba(248,113,113,0.24); }
.preview-list { display: flex; flex-direction: column; gap: 10px; margin-top: 12px; }
.preview-item {
  padding: 11px 12px; border-radius: 14px;
  background: rgba(255,255,255,0.035); border: 1px solid rgba(255,255,255,0.06);
}
.preview-item strong { display: block; font-size: 0.88rem; }
.preview-item small { display: block; margin-top: 5px; color: var(--muted); line-height: 1.45; }
.import-tag {
  display: inline-block; padding: 4px 9px; border-radius: 999px;
  font-size: 0.72rem; margin-right: 6px; margin-top: 8px;
}
.import-tag.ok { background: rgba(74,222,128,0.12); color: #ccffdd; }
.import-tag.warn { background: rgba(251,191,36,0.12); color: #ffe8a8; }
.import-tag.err { background: rgba(248,113,113,0.12); color: #ffd4d4; }
details summary { cursor: pointer; color: var(--accent); font-size: 0.84rem; }
@media (max-width: 980px) {
  .grid { grid-template-columns: 1fr; }
}
@media (max-width: 640px) {
  .row2, .row3 { grid-template-columns: 1fr; }
  header { flex-direction: column; align-items: start; gap: 12px; }
}
</style>
</head>
<body>
<header>
  <div class="title-wrap">
    <h1>⚡ PPT Board · Scheduler</h1>
    <p>Google-backed scheduling inside the PPT Board app.</p>
  </div>
  <nav class="nav">
    <a href="/board/">Dashboard</a>
    <a href="/">Planner</a>
    <a href="/notify">Notify</a>
    <a href="/scheduler">Scheduler</a>
  </nav>
</header>

<div class="container">
  {% if message %}
  <div class="flash ok">{{ message }}</div>
  {% endif %}
  {% if error %}
  <div class="flash err">{{ error }}</div>
  {% endif %}
  {% if conflicts %}
  <div class="flash warn">
    {{ conflicts|length }} conflict{{ '' if conflicts|length == 1 else 's' }} found. Review them below. You can adjust the schedule or save anyway.
  </div>
  {% endif %}
  {% if basic_conflicts %}
  <div class="flash warn">
    {{ basic_conflicts|length }} starter routine conflict{{ '' if basic_conflicts|length == 1 else 's' }} found. Review them below, adjust the anchor times, or apply anyway.
  </div>
  {% endif %}

  <div class="grid">
    <div class="stack">
      <section class="card anchor-card" id="setup-todo">
        <div class="card-header">
          <div class="eyebrow">Setup</div>
          <div class="card-title">Setup / To Do</div>
        </div>
        <div class="card-body">
          <div class="meta">
            <span class="pill">{{ scheduler_status.setup_status.complete_count }} / {{ scheduler_status.setup_status.total_count }} complete</span>
            {% if scheduler_status.setup_status.all_complete %}
            <span class="pill ok">Ready to schedule</span>
            {% else %}
            <span class="pill warn">Finish setup</span>
            {% endif %}
          </div>

          <div class="note">
            PPT scheduler needs verified Google access, one write calendar, readable current events, saved daily anchors, and one starter routine before the setup flow is complete.
          </div>

          {% if scheduler_status.next_actions %}
          <div class="btn-row" style="margin-top:12px">
            {% for action in scheduler_status.next_actions %}
            <a class="btn link" href="{{ action.href }}">{{ action.label }}</a>
            {% endfor %}
          </div>
          {% endif %}

          <div class="todo-list">
            {% for item in scheduler_status.setup_status.steps %}
            <div class="todo-item">
              <div class="todo-top">
                <strong>{{ item.label }}</strong>
                <span class="state-pill {{ item.state }}">{{ item.state }}</span>
              </div>
              <div class="todo-detail">{{ item.detail }}</div>
              {% if item.next_action %}
              <div class="todo-action">
                <a class="btn link" href="{{ item.next_action.href }}">{{ item.next_action.label }}</a>
              </div>
              {% endif %}
            </div>
            {% endfor %}
          </div>

          <div class="note">
            Current events preview: {{ scheduler_status.agenda_preview.range_start }} to {{ scheduler_status.agenda_preview.range_end }}
          </div>
          {% if scheduler_status.agenda_preview.state == 'ready' %}
            {% if scheduler_status.agenda_preview.events %}
            <div class="preview-list">
              {% for event in scheduler_status.agenda_preview.events %}
              <div class="preview-item">
                <strong>{{ event.title }}</strong>
                <small>
                  {% if event.all_day %}
                    All day · {{ event.start }}{% if event.end != event.start %} → {{ event.end }}{% endif %}
                  {% else %}
                    {{ event.start }} → {{ event.end }}
                  {% endif %}
                </small>
                <small>{{ event.google_calendar_summary }}</small>
              </div>
              {% endfor %}
            </div>
            {% else %}
            <div class="empty" style="margin-top:12px">No upcoming events in the next 7 days, but live calendar access is working.</div>
            {% endif %}
          {% elif scheduler_status.agenda_preview.state == 'error' %}
          <div class="flash err" style="margin-top:12px">{{ scheduler_status.agenda_preview.error }}</div>
          {% else %}
          <div class="empty" style="margin-top:12px">Current event preview unlocks after you choose a default writable calendar.</div>
          {% endif %}
        </div>
      </section>

      <section class="card anchor-card" id="google-connection">
        <div class="card-header">
          <div class="eyebrow">Connection</div>
          <div class="card-title">Google Calendar</div>
        </div>
        <div class="card-body">
          <div class="meta">
            {% if scheduler_status.connected %}
              <span class="pill ok">Connected</span>
            {% elif scheduler_status.configured %}
              <span class="pill warn">Ready to connect</span>
            {% else %}
              <span class="pill err">Needs OAuth config</span>
            {% endif %}

            {% if scheduler_status.config_source == 'web' %}
              <span class="pill">Web OAuth Config</span>
            {% elif scheduler_status.config_source == 'env_vars' %}
              <span class="pill">Env OAuth Config</span>
            {% elif scheduler_status.config_source == 'env_file' %}
              <span class="pill">Secrets File Config</span>
            {% endif %}

            {% if scheduler_status.default_calendar_summary %}
              <span class="pill">{{ scheduler_status.default_calendar_summary }}</span>
            {% endif %}
          </div>

          {% if not scheduler_status.configured %}
            <div class="note">
              Use the web form below to save the Google OAuth app credentials locally, then connect your Google account through the browser. Google still requires a real OAuth web app in Google Cloud Console. Redirect URI: <code>{{ redirect_uri }}</code>
            </div>
            <div class="note" style="margin-top:10px">
              This is standard browser OAuth. If the browser you open already has a Google session, Google can reuse that session during sign-in and consent.
            </div>
            <form method="POST" action="{{ url_for('scheduler.save_google_oauth_config_route') }}" style="margin-top:12px">
              <div class="field">
                <label for="oauth_client_id">Google OAuth client ID</label>
                <input id="oauth_client_id" name="client_id" value="{{ oauth_config_draft.client_id }}" required>
              </div>
              <div class="field">
                <label for="oauth_client_secret">Google OAuth client secret</label>
                <input id="oauth_client_secret" name="client_secret" type="password" value="" placeholder="Paste the client secret" required>
              </div>
              <div class="field">
                <label for="oauth_project_id">Google project ID</label>
                <input id="oauth_project_id" name="project_id" value="{{ oauth_config_draft.project_id }}">
              </div>
              <button class="btn primary" type="submit">Save Google Web Config</button>
            </form>
          {% elif not scheduler_status.connected %}
            <div class="note">
              The scheduler is configured but not connected yet. Use the local OAuth flow to connect your Google account, then choose one default writable calendar.
            </div>
            <div class="note" style="margin-top:10px">
              The connect flow opens normal browser OAuth, so a browser plugin or existing signed-in browser session can complete consent without extra app-specific setup.
            </div>
            <div class="btn-row" style="margin-top:12px">
              <a class="btn link" href="{{ url_for('scheduler.connect_google') }}">Connect Google Calendar</a>
            </div>
            {% if scheduler_status.config_source == 'web' %}
            <details style="margin-top:12px">
              <summary>Update saved web OAuth config</summary>
              <form method="POST" action="{{ url_for('scheduler.save_google_oauth_config_route') }}" style="margin-top:12px">
                <div class="field">
                  <label for="oauth_client_id_saved">Google OAuth client ID</label>
                  <input id="oauth_client_id_saved" name="client_id" value="{{ oauth_config_draft.client_id }}" required>
                </div>
                <div class="field">
                  <label for="oauth_client_secret_saved">Google OAuth client secret</label>
                  <input id="oauth_client_secret_saved" name="client_secret" type="password" value="" placeholder="Leave blank to keep the saved secret">
                </div>
                <div class="field">
                  <label for="oauth_project_id_saved">Google project ID</label>
                  <input id="oauth_project_id_saved" name="project_id" value="{{ oauth_config_draft.project_id }}">
                </div>
                <div class="btn-row">
                  <button class="btn primary" type="submit">Update Web Config</button>
                </div>
              </form>
              <form method="POST" action="{{ url_for('scheduler.clear_google_oauth_config_route') }}" style="margin-top:10px">
                <button class="btn danger" type="submit">Clear Saved Web Config</button>
              </form>
            </details>
            {% endif %}
          {% else %}
            <div class="note">
              Schedules are written to one selected Google calendar, while conflict checks read across your visible calendars.
            </div>
            <div class="btn-row" style="margin-top:12px">
              <form method="POST" action="{{ url_for('scheduler.disconnect_google_route') }}">
                <button class="btn danger" type="submit">Disconnect Google</button>
              </form>
              {% if scheduler_status.config_source == 'web' %}
              <form method="POST" action="{{ url_for('scheduler.clear_google_oauth_config_route') }}">
                <button class="btn secondary" type="submit">Clear Saved Web Config</button>
              </form>
              {% endif %}
            </div>
          {% endif %}
        </div>
      </section>

      <section class="card anchor-card" id="calendar-setup">
        <div class="card-header">
          <div class="eyebrow">Setup</div>
          <div class="card-title">Default Writable Calendar</div>
        </div>
        <div class="card-body">
          {% if scheduler_status.connected %}
          <form method="POST" action="{{ url_for('scheduler.set_default_calendar_route') }}">
            <div class="field">
              <label for="calendar_id">Calendar</label>
              <select id="calendar_id" name="calendar_id">
                <option value="">Choose a calendar…</option>
                {% for cal in calendars %}
                <option value="{{ cal.id }}" {% if cal.id == scheduler_status.default_calendar_id %}selected{% endif %}>
                  {{ cal.summary }}{% if cal.primary %} · primary{% endif %}
                </option>
                {% endfor %}
              </select>
            </div>
            <button class="btn primary" type="submit">Save Default Calendar</button>
          </form>
          {% else %}
          <div class="empty">Connect Google first to load writable calendars.</div>
          {% endif %}
        </div>
      </section>

      <section class="card anchor-card" id="starter-routine">
        <div class="card-header">
          <div class="eyebrow">Routine</div>
          <div class="card-title">Basic Daily Rhythm</div>
        </div>
        <div class="card-body">
          <div class="note" style="margin-top:0">
            This starter routine creates recurring Google Calendar events for everyday anchors like waking up, breakfast, work prep, winding gaming down, and sleep. Reapplying it updates the same managed routine events instead of duplicating them.
          </div>

          {% if scheduler_status.connected and scheduler_status.default_calendar_id %}
          <form method="POST" action="{{ url_for('scheduler.apply_basic_daily_route') }}" style="margin-top:12px">
            <input type="hidden" name="calendar_id" value="{{ basic_draft.calendar_id or scheduler_status.default_calendar_id }}">
            <div class="row2">
              <div class="field">
                <label for="basic_start_date">Start date</label>
                <input id="basic_start_date" type="date" name="start_date" value="{{ basic_draft.start_date }}" required>
              </div>
              <div class="field">
                <label for="basic_timezone">Timezone</label>
                <input id="basic_timezone" name="timezone" value="{{ basic_draft.timezone }}" required>
              </div>
            </div>
            <div class="row2">
              <div class="field">
                <label for="wake_time">Wake time</label>
                <input id="wake_time" type="time" name="wake_time" value="{{ basic_draft.wake_time }}" required>
              </div>
              <div class="field">
                <label for="breakfast_time">Breakfast ready</label>
                <input id="breakfast_time" type="time" name="breakfast_time" value="{{ basic_draft.breakfast_time }}" required>
              </div>
            </div>
            <div class="row2">
              <div class="field">
                <label for="work_notes_time">Work notes ready</label>
                <input id="work_notes_time" type="time" name="work_notes_time" value="{{ basic_draft.work_notes_time }}" required>
              </div>
              <div class="field">
                <label for="eat_time">Eat something</label>
                <input id="eat_time" type="time" name="eat_time" value="{{ basic_draft.eat_time }}" required>
              </div>
            </div>
            <div class="row2">
              <div class="field">
                <label for="gaming_off_time">Gaming session off</label>
                <input id="gaming_off_time" type="time" name="gaming_off_time" value="{{ basic_draft.gaming_off_time }}" required>
              </div>
              <div class="field">
                <label for="sleep_on_time">Sleep on</label>
                <input id="sleep_on_time" type="time" name="sleep_on_time" value="{{ basic_draft.sleep_on_time }}" required>
              </div>
            </div>
            <div class="btn-row">
              <button class="btn secondary" type="submit" formaction="{{ url_for('scheduler.save_basic_daily_profile_route') }}">Save Inputs</button>
              <button class="btn primary" type="submit">Apply Basic Schedule</button>
              {% if basic_conflicts %}
              <button class="btn warn" type="submit" name="confirm_conflicts" value="1">Apply Anyway</button>
              {% endif %}
            </div>
          </form>
          {% else %}
          <div class="empty" style="margin-top:12px">Connect Google and choose a default writable calendar before applying the starter routine.</div>
          {% endif %}

          {% if basic_preview %}
          <div class="import-list">
            {% for item in basic_preview.events %}
            <div class="import-item">
              <strong>{{ item.title }}</strong>
              <small>{{ item.start }} → {{ item.end }}</small>
              <span class="import-tag ok">{{ item.recurrence_kind }}</span>
              {% if item.description %}
              <small>{{ item.description }}</small>
              {% endif %}
            </div>
            {% endfor %}
          </div>
          {% endif %}

          {% if basic_conflicts %}
          <details style="margin-top:10px">
            <summary>Show starter routine conflicts</summary>
            <div class="conflict-list">
              {% for conflict in basic_conflicts %}
              <div class="conflict">
                <strong>{{ conflict.candidate_title }}</strong>
                <small>{{ conflict.calendar_summary }} · {{ conflict.summary }}</small>
                <small>{{ conflict.existing_start }} → {{ conflict.existing_end }}</small>
                <small>Routine slot: {{ conflict.candidate_start }} → {{ conflict.candidate_end }}</small>
              </div>
              {% endfor %}
            </div>
          </details>
          {% endif %}
        </div>
      </section>

      <section class="card anchor-card" id="manual-editor">
        <div class="card-header">
          <div class="eyebrow">Editor</div>
          <div class="card-title">{{ 'Edit Event' if draft.event_id else 'Create Event' }}</div>
        </div>
        <div class="card-body">
          <div class="note" style="margin-top:0">
            Use the manual editor for one-off or ad hoc calendar events. The starter routine above is the recommended first scheduling path.
          </div>
          {% if scheduler_status.connected and scheduler_status.default_calendar_id %}
          <form method="POST" action="{{ url_for('scheduler.save_event_route') }}" style="margin-top:12px">
            <input type="hidden" name="event_id" value="{{ draft.event_id or '' }}">
            <input type="hidden" name="calendar_id" value="{{ draft.calendar_id or scheduler_status.default_calendar_id }}">
            <div class="field">
              <label for="title">Title</label>
              <input id="title" name="title" value="{{ draft.title }}" required>
            </div>
            <div class="field">
              <label for="description">Description / Notes</label>
              <textarea id="description" name="description">{{ draft.description }}</textarea>
            </div>
            <div class="field">
              <label for="location">Location</label>
              <input id="location" name="location" value="{{ draft.location }}">
            </div>
            <label class="checkbox">
              <input type="checkbox" name="all_day" value="1" {% if draft.all_day %}checked{% endif %}>
              Treat this as an all-day event
            </label>
            <div class="row2">
              <div class="field">
                <label for="start_date">Start date</label>
                <input id="start_date" type="date" name="start_date" value="{{ draft.start_date }}" required>
              </div>
              <div class="field">
                <label for="end_date">End date</label>
                <input id="end_date" type="date" name="end_date" value="{{ draft.end_date }}" required>
              </div>
            </div>
            <div class="row2">
              <div class="field">
                <label for="start_time">Start time</label>
                <input id="start_time" type="time" name="start_time" value="{{ draft.start_time }}">
              </div>
              <div class="field">
                <label for="end_time">End time</label>
                <input id="end_time" type="time" name="end_time" value="{{ draft.end_time }}">
              </div>
            </div>
            <div class="row2">
              <div class="field">
                <label for="timezone">Timezone</label>
                <input id="timezone" name="timezone" value="{{ draft.timezone }}">
              </div>
              <div class="field">
                <label for="recurrence_kind">Recurrence</label>
                <select id="recurrence_kind" name="recurrence_kind">
                  {% for value, label in recurrence_options %}
                  <option value="{{ value }}" {% if draft.recurrence_kind == value %}selected{% endif %}>{{ label }}</option>
                  {% endfor %}
                </select>
              </div>
            </div>
            <div class="field" id="custom-rule-field" {% if draft.recurrence_kind != 'custom' %}style="display:none"{% endif %}>
              <label for="recurrence_rule">Custom RRULE</label>
              <input id="recurrence_rule" name="recurrence_rule" value="{{ draft.recurrence_rule or '' }}" placeholder="RRULE:FREQ=WEEKLY;BYDAY=MO,WE,FR">
            </div>
            <div class="btn-row">
              <button class="btn primary" type="submit">{{ 'Update Event' if draft.event_id else 'Create Event' }}</button>
              {% if conflicts %}
              <button class="btn warn" type="submit" name="confirm_conflicts" value="1">{{ 'Save Anyway' if draft.event_id else 'Create Anyway' }}</button>
              {% endif %}
              {% if draft.event_id %}
              <a class="btn secondary" href="{{ url_for('scheduler.index') }}">Clear Edit State</a>
              {% endif %}
            </div>
          </form>
          {% else %}
          <div class="empty">Connect Google and choose a default writable calendar before creating events.</div>
          {% endif %}

          {% if conflicts %}
          <div class="conflict-list">
            {% for conflict in conflicts %}
            <div class="conflict">
              <strong>{{ conflict.summary }}</strong>
              <small>{{ conflict.calendar_summary }} · {{ conflict.existing_start }} → {{ conflict.existing_end }}</small>
              <small>Candidate occurrence: {{ conflict.candidate_start }} → {{ conflict.candidate_end }}</small>
            </div>
            {% endfor %}
          </div>
          {% endif %}
        </div>
      </section>

      <section class="card">
        <div class="card-header">
          <div class="eyebrow">Imports</div>
          <div class="card-title">ICS Import</div>
        </div>
        <div class="card-body">
          {% if scheduler_status.connected and scheduler_status.default_calendar_id %}
          <form method="POST" action="{{ url_for('scheduler.preview_import_route') }}" enctype="multipart/form-data">
            <div class="field">
              <label for="ics_file">Calendar file</label>
              <input id="ics_file" type="file" name="ics_file" accept=".ics,text/calendar" required>
            </div>
            <button class="btn primary" type="submit">Preview Import</button>
          </form>
          {% else %}
          <div class="empty">Choose a default calendar first. Imports write into that selected Google calendar.</div>
          {% endif %}

          {% if import_preview %}
          <div class="import-list">
            {% for item in import_preview.entries %}
            <div class="import-item">
              <strong>{{ item.payload.title }}</strong>
              <small>
                {% if item.payload.all_day %}
                  {{ item.payload.start }}{% if item.payload.end != item.payload.start %} → {{ item.payload.end }}{% endif %}
                {% else %}
                  {{ item.payload.start }} → {{ item.payload.end }}
                {% endif %}
              </small>
              {% if item.error %}
              <span class="import-tag err">Invalid</span>
              <small>{{ item.error }}</small>
              {% endif %}
              {% if item.duplicate %}
              <span class="import-tag warn">Duplicate UID</span>
              {% endif %}
              {% if item.conflicts %}
              <span class="import-tag warn">{{ item.conflicts|length }} conflict{{ '' if item.conflicts|length == 1 else 's' }}</span>
              {% endif %}
              {% if not item.error and not item.duplicate and not item.conflicts %}
              <span class="import-tag ok">Ready</span>
              {% endif %}
              {% if item.conflicts %}
              <details style="margin-top:8px">
                <summary>Show conflicts</summary>
                <div class="conflict-list">
                  {% for conflict in item.conflicts %}
                  <div class="conflict">
                    <strong>{{ conflict.summary }}</strong>
                    <small>{{ conflict.calendar_summary }} · {{ conflict.existing_start }} → {{ conflict.existing_end }}</small>
                  </div>
                  {% endfor %}
                </div>
              </details>
              {% endif %}
            </div>
            {% endfor %}
          </div>
          <form method="POST" action="{{ url_for('scheduler.commit_import_route') }}" style="margin-top:14px">
            <input type="hidden" name="batch_id" value="{{ import_preview.batch_id }}">
            <button class="btn warn" type="submit">Import Batch Into Google Calendar</button>
          </form>
          {% endif %}
        </div>
      </section>
    </div>

    <section class="card">
      <div class="card-header">
        <div class="eyebrow">Agenda</div>
        <div class="card-title">Upcoming Events</div>
      </div>
      <div class="card-body">
        <form method="GET" action="{{ url_for('scheduler.index') }}" class="agenda-toolbar">
          <div class="field">
            <label for="range_start">From</label>
            <input id="range_start" type="date" name="start" value="{{ range_start }}">
          </div>
          <div class="field">
            <label for="range_end">To</label>
            <input id="range_end" type="date" name="end" value="{{ range_end }}">
          </div>
          <div class="field" style="flex:0 0 auto">
            <button class="btn secondary" type="submit">Refresh Range</button>
          </div>
        </form>

        <div style="height:16px"></div>

        {% if agenda_error %}
          <div class="flash err">{{ agenda_error }}</div>
        {% elif not events %}
          <div class="empty">No events found in this range.</div>
        {% else %}
          <div class="agenda-list">
            {% for event in events %}
            <article class="event">
              <div class="event-head">
                <div>
                  <div class="event-title">{{ event.title }}</div>
                  <div class="event-time">
                    {% if event.all_day %}
                      All day · {{ event.start }}{% if event.end != event.start %} → {{ event.end }}{% endif %}
                    {% else %}
                      {{ event.start }} → {{ event.end }}
                    {% endif %}
                  </div>
                </div>
                <span class="pill">{{ event.recurrence_kind }}</span>
              </div>
              <div class="event-meta">
                {{ event.google_calendar_summary }}
                {% if event.location %} · {{ event.location }}{% endif %}
                {% if event.description %}<br>{{ event.description }}{% endif %}
              </div>
              <div class="event-actions">
                <a class="btn secondary" href="{{ url_for('scheduler.index', start=range_start, end=range_end, edit_event_id=event.google_event_id, edit_calendar_id=event.google_calendar_id) }}">Edit</a>
                {% if event.html_link %}
                <a class="btn secondary" href="{{ event.html_link }}" target="_blank" rel="noreferrer">Open in Google</a>
                {% endif %}
                <form method="POST" action="{{ url_for('scheduler.delete_event_route') }}" onsubmit="return confirm('Delete this Google Calendar event?');">
                  <input type="hidden" name="calendar_id" value="{{ event.google_calendar_id }}">
                  <input type="hidden" name="event_id" value="{{ event.google_event_id }}">
                  <input type="hidden" name="start" value="{{ range_start }}">
                  <input type="hidden" name="end" value="{{ range_end }}">
                  <button class="btn danger" type="submit">Delete</button>
                </form>
              </div>
            </article>
            {% endfor %}
          </div>
        {% endif %}
      </div>
    </section>
  </div>
</div>

<script>
const recurrenceSelect = document.getElementById('recurrence_kind');
const customRuleField = document.getElementById('custom-rule-field');
if (recurrenceSelect && customRuleField) {
  const toggleCustomRule = () => {
    customRuleField.style.display = recurrenceSelect.value === 'custom' ? '' : 'none';
  };
  recurrenceSelect.addEventListener('change', toggleCustomRule);
  toggleCustomRule();
}
</script>
</body>
</html>"""


def _default_range() -> tuple[str, str]:
    start_value = request.args.get("start") or date.today().isoformat()
    end_value = request.args.get("end") or (date.today() + timedelta(days=14)).isoformat()
    return start_value, end_value


def _draft_defaults() -> dict:
    start_value, end_value = _default_range()
    return {
        "event_id": None,
        "calendar_id": scheduler_store.get_default_calendar_id(),
        "title": "",
        "description": "",
        "location": "",
        "all_day": False,
        "start_date": start_value,
        "end_date": start_value,
        "start_time": "09:00",
        "end_time": "10:00",
        "timezone": scheduler_service.DEFAULT_TIMEZONE,
        "recurrence_kind": "once",
        "recurrence_rule": "",
    }


def _basic_draft_defaults() -> dict:
    start_value, _ = _default_range()
    return scheduler_service.basic_daily_schedule_defaults(start_date=start_value)


def _event_to_draft(event: dict) -> dict:
    draft = _draft_defaults()
    draft.update(
        {
            "event_id": event["google_event_id"],
            "calendar_id": event["google_calendar_id"],
            "title": event["title"],
            "description": event["description"],
            "location": event["location"],
            "all_day": event["all_day"],
            "timezone": event["timezone"],
            "recurrence_kind": event["recurrence_kind"],
            "recurrence_rule": event.get("recurrence_rule") or "",
        }
    )
    if event["all_day"]:
        draft["start_date"] = event["start"]
        draft["end_date"] = event["end"]
        draft["start_time"] = ""
        draft["end_time"] = ""
    else:
        start_dt = datetime.fromisoformat(event["start"])
        end_dt = datetime.fromisoformat(event["end"])
        draft["start_date"] = start_dt.date().isoformat()
        draft["end_date"] = end_dt.date().isoformat()
        draft["start_time"] = start_dt.strftime("%H:%M")
        draft["end_time"] = end_dt.strftime("%H:%M")
    return draft


def _payload_from_form() -> dict:
    all_day = "all_day" in request.form
    payload = {
        "title": request.form.get("title", ""),
        "description": request.form.get("description", ""),
        "location": request.form.get("location", ""),
        "all_day": all_day,
        "timezone": request.form.get("timezone") or scheduler_service.DEFAULT_TIMEZONE,
        "recurrence_kind": request.form.get("recurrence_kind", "once"),
        "recurrence_rule": request.form.get("recurrence_rule", ""),
        "calendar_id": request.form.get("calendar_id") or scheduler_store.get_default_calendar_id(),
    }
    start_date = request.form.get("start_date", "")
    end_date = request.form.get("end_date", start_date)
    if all_day:
        payload["start"] = start_date
        payload["end"] = end_date or start_date
    else:
        start_time = request.form.get("start_time", "09:00")
        end_time = request.form.get("end_time", "10:00")
        payload["start"] = f"{start_date}T{start_time}"
        payload["end"] = f"{end_date or start_date}T{end_time}"
    return payload


def _draft_from_payload(payload: dict) -> dict:
    draft = _draft_defaults()
    draft.update(
        {
            "title": payload.get("title", ""),
            "description": payload.get("description", ""),
            "location": payload.get("location", ""),
            "all_day": payload.get("all_day", False),
            "timezone": payload.get("timezone") or scheduler_service.DEFAULT_TIMEZONE,
            "recurrence_kind": payload.get("recurrence_kind", "once"),
            "recurrence_rule": payload.get("recurrence_rule", ""),
            "calendar_id": payload.get("calendar_id"),
            "event_id": payload.get("event_id"),
        }
    )
    if payload.get("all_day"):
        draft["start_date"] = payload.get("start", "")
        draft["end_date"] = payload.get("end", payload.get("start", ""))
        draft["start_time"] = ""
        draft["end_time"] = ""
    else:
        start_dt = datetime.fromisoformat(payload["start"])
        end_dt = datetime.fromisoformat(payload["end"])
        draft["start_date"] = start_dt.date().isoformat()
        draft["end_date"] = end_dt.date().isoformat()
        draft["start_time"] = start_dt.strftime("%H:%M")
        draft["end_time"] = end_dt.strftime("%H:%M")
    return draft


def _basic_payload_from_form() -> dict:
    return {
        "calendar_id": request.form.get("calendar_id") or scheduler_store.get_default_calendar_id(),
        "start_date": request.form.get("start_date", ""),
        "timezone": request.form.get("timezone", scheduler_service.DEFAULT_TIMEZONE),
        "wake_time": request.form.get("wake_time", ""),
        "breakfast_time": request.form.get("breakfast_time", ""),
        "work_notes_time": request.form.get("work_notes_time", ""),
        "eat_time": request.form.get("eat_time", ""),
        "gaming_off_time": request.form.get("gaming_off_time", ""),
        "sleep_on_time": request.form.get("sleep_on_time", ""),
    }


def _oauth_config_from_form() -> dict:
    return {
        "client_id": request.form.get("client_id", ""),
        "client_secret": request.form.get("client_secret", ""),
        "project_id": request.form.get("project_id", "ppt-scheduler"),
    }


def _render_index(
    *,
    message: str | None = None,
    error: str | None = None,
    conflicts=None,
    draft=None,
    import_preview=None,
    basic_draft=None,
    basic_conflicts=None,
    oauth_config_draft=None,
):
    scheduler_status = scheduler_service.connection_status()
    range_start, range_end = _default_range()
    agenda_error = None
    events = []
    calendars = scheduler_status.get("writable_calendars", [])

    if draft is None and request.args.get("edit_event_id") and request.args.get("edit_calendar_id"):
        try:
            event = scheduler_service.get_event(request.args["edit_calendar_id"], request.args["edit_event_id"])
            draft = _event_to_draft(event)
        except Exception as exc:
            error = str(exc)

    if draft is None:
        draft = _draft_defaults()

    if basic_draft is None:
        basic_draft = _basic_draft_defaults()

    if oauth_config_draft is None:
        oauth_config_draft = scheduler_service.google_oauth_web_config_draft()

    try:
        basic_preview = scheduler_service.preview_basic_daily_schedule(basic_draft)
    except SchedulerError:
        basic_preview = None

    if import_preview is None and request.args.get("batch_id"):
        batch = scheduler_store.get_import_batch(request.args["batch_id"])
        if batch:
            import_preview = batch["preview"]
            import_preview["batch_id"] = batch["id"]

    if scheduler_status.get("connected") and scheduler_status.get("default_calendar_id"):
        try:
            events = scheduler_service.list_agenda_events(
                start=range_start,
                end=range_end,
                calendar_id=scheduler_status["default_calendar_id"],
            )
        except Exception as exc:
            agenda_error = str(exc)

    return render_template_string(
        _HTML,
        message=message,
        error=error,
        conflicts=conflicts or [],
        draft=draft,
        import_preview=import_preview,
        basic_draft=basic_draft,
        basic_conflicts=basic_conflicts or [],
        basic_preview=basic_preview,
        oauth_config_draft=oauth_config_draft,
        scheduler_status=scheduler_status,
        calendars=calendars,
        events=events,
        agenda_error=agenda_error,
        range_start=range_start,
        range_end=range_end,
        recurrence_options=[
            ("once", "One time"),
            ("daily", "Daily"),
            ("weekdays", "Weekdays"),
            ("weekly", "Weekly"),
            ("monthly", "Monthly"),
            ("custom", "Custom / preserve existing rule"),
        ],
        redirect_uri=CalendarApiClient().redirect_uri(url_for("scheduler.oauth_callback", _external=True)),
    )


@scheduler_bp.route("/", strict_slashes=False)
def index():
    return _render_index(
        message=request.args.get("message"),
        error=request.args.get("error"),
    )


@scheduler_bp.route("/connect")
def connect_google():
    try:
        scheduler_store.cleanup_oauth_states()
        auth_url, state = CalendarApiClient().authorization_url(
            redirect_uri=url_for("scheduler.oauth_callback", _external=True)
        )
        scheduler_store.store_oauth_state(state)
    except Exception as exc:
        return redirect(url_for("scheduler.index", error=str(exc)))
    return redirect(auth_url)


@scheduler_bp.route("/oauth/configure", methods=["POST"])
def save_google_oauth_config_route():
    oauth_config = _oauth_config_from_form()
    try:
        scheduler_service.save_google_oauth_web_config(
            oauth_config,
            redirect_uri=url_for("scheduler.oauth_callback", _external=True),
        )
    except SchedulerError as exc:
        return _render_index(error=str(exc), oauth_config_draft=oauth_config)
    return redirect(
        url_for(
            "scheduler.index",
            message="Google OAuth app credentials saved. You can now connect your Google account from the browser.",
        )
    )


@scheduler_bp.route("/oauth/configure/clear", methods=["POST"])
def clear_google_oauth_config_route():
    scheduler_service.clear_google_oauth_web_config()
    return redirect(url_for("scheduler.index", message="Saved web OAuth config cleared."))


@scheduler_bp.route("/oauth/callback")
def oauth_callback():
    state = request.args.get("state", "")
    if not state or not scheduler_store.consume_oauth_state(state):
        return redirect(url_for("scheduler.index", error="OAuth state was missing or expired. Try connecting again."))
    if request.args.get("error"):
        return redirect(url_for("scheduler.index", error=f"Google OAuth failed: {request.args['error']}"))
    try:
        CalendarApiClient().exchange_callback(
            full_callback_url=request.url,
            redirect_uri=url_for("scheduler.oauth_callback", _external=True),
        )
    except Exception as exc:
        return redirect(url_for("scheduler.index", error=str(exc)))
    return redirect(url_for("scheduler.index", message="Google Calendar connected. Choose a default writable calendar next."))


@scheduler_bp.route("/disconnect", methods=["POST"])
def disconnect_google_route():
    scheduler_service.disconnect_google()
    return redirect(url_for("scheduler.index", message="Google Calendar disconnected."))


@scheduler_bp.route("/calendar/default", methods=["POST"])
def set_default_calendar_route():
    try:
        calendar = scheduler_service.set_default_calendar(request.form.get("calendar_id", ""))
    except SchedulerError as exc:
        return redirect(url_for("scheduler.index", error=str(exc)))
    return redirect(url_for("scheduler.index", message=f"Default calendar set to {calendar['summary']}.")) 


@scheduler_bp.route("/profile/basic-daily", methods=["POST"])
def save_basic_daily_profile_route():
    basic_payload = _basic_payload_from_form()
    try:
        scheduler_service.save_basic_daily_profile(basic_payload)
    except SchedulerError as exc:
        return _render_index(error=str(exc), basic_draft=basic_payload)
    return redirect(
        url_for(
            "scheduler.index",
            message="Daily schedule inputs saved. You can now apply the starter routine or keep adjusting the anchors.",
        )
    )


@scheduler_bp.route("/templates/basic-daily", methods=["POST"])
def apply_basic_daily_route():
    basic_payload = _basic_payload_from_form()
    try:
        result = scheduler_service.apply_basic_daily_schedule(
            basic_payload,
            confirm_conflicts=request.form.get("confirm_conflicts") == "1",
        )
        if result.get("requires_confirmation"):
            return _render_index(
                error="The starter routine overlaps with existing Google Calendar events.",
                basic_draft=result["config"],
                basic_conflicts=result["conflicts"],
            )
        return redirect(
            url_for(
                "scheduler.index",
                message=(
                    "Basic daily rhythm applied. "
                    f"Created {result['created_count']} event(s) and updated {result['updated_count']} event(s)."
                ),
            )
        )
    except SchedulerError as exc:
        return _render_index(error=str(exc), basic_draft=basic_payload)


@scheduler_bp.route("/event/save", methods=["POST"])
def save_event_route():
    try:
        payload = _payload_from_form()
        event_id = request.form.get("event_id") or None
        confirm_conflicts = request.form.get("confirm_conflicts") == "1"
        if event_id:
            result = scheduler_service.update_event(
                request.form.get("calendar_id", ""),
                event_id,
                payload,
                confirm_conflicts=confirm_conflicts,
            )
            if result.get("requires_confirmation"):
                draft = _draft_from_payload(result["payload"] | {"event_id": event_id})
                return _render_index(
                    conflicts=result["conflicts"],
                    draft=draft,
                    error="This edit overlaps with existing Google Calendar events.",
                )
            return redirect(url_for("scheduler.index", message="Google Calendar event updated successfully."))

        result = scheduler_service.create_event(payload, confirm_conflicts=confirm_conflicts)
        if result.get("requires_confirmation"):
            return _render_index(
                conflicts=result["conflicts"],
                draft=_draft_from_payload(result["payload"]),
                error="This event overlaps with existing Google Calendar events.",
            )
        return redirect(url_for("scheduler.index", message="Google Calendar event created successfully."))
    except SchedulerError as exc:
        return _render_index(error=str(exc), draft=_draft_from_payload(_payload_from_form()))


@scheduler_bp.route("/event/delete", methods=["POST"])
def delete_event_route():
    calendar_id = request.form.get("calendar_id", "")
    event_id = request.form.get("event_id", "")
    start = request.form.get("start")
    end = request.form.get("end")
    try:
        scheduler_service.delete_event(calendar_id, event_id)
    except SchedulerError as exc:
        return redirect(url_for("scheduler.index", start=start, end=end, error=str(exc)))
    return redirect(url_for("scheduler.index", start=start, end=end, message="Google Calendar event deleted."))


@scheduler_bp.route("/imports/preview", methods=["POST"])
def preview_import_route():
    upload = request.files.get("ics_file")
    if not upload or not upload.filename:
        return redirect(url_for("scheduler.index", error="Choose an .ics file to preview."))
    try:
        preview = scheduler_service.preview_ics(upload.read(), upload.filename)
    except SchedulerError as exc:
        return redirect(url_for("scheduler.index", error=str(exc)))
    return _render_index(
        message=f"Previewed {len(preview['entries'])} ICS event(s). Review conflicts and duplicates before importing.",
        import_preview=preview,
    )


@scheduler_bp.route("/imports/commit", methods=["POST"])
def commit_import_route():
    batch_id = request.form.get("batch_id", "")
    try:
        result = scheduler_service.import_preview_batch(batch_id, confirm_conflicts=True)
    except SchedulerError as exc:
        return redirect(url_for("scheduler.index", batch_id=batch_id, error=str(exc)))
    return redirect(
        url_for(
            "scheduler.index",
            message=f"Imported {result['imported_events']} of {result['total_events']} previewed ICS event(s) into Google Calendar.",
        )
    )


def _json_error(message: str, code: int = 400):
    return jsonify({"ok": False, "error": message}), code


@scheduler_bp.route("/api/connect")
def api_connect():
    try:
        scheduler_store.cleanup_oauth_states()
        auth_url, state = CalendarApiClient().authorization_url(
            redirect_uri=url_for("scheduler.oauth_callback", _external=True)
        )
        scheduler_store.store_oauth_state(state)
    except Exception as exc:
        return _json_error(str(exc), 500)
    return jsonify({"ok": True, "authorization_url": auth_url})


@scheduler_bp.route("/api/disconnect", methods=["POST"])
def api_disconnect():
    scheduler_service.disconnect_google()
    return jsonify({"ok": True})


@scheduler_bp.route("/api/status")
def api_status():
    return jsonify({"ok": True, "status": scheduler_service.connection_status()})


@scheduler_bp.route("/api/integration")
def api_integration():
    return jsonify({"ok": True, "integration": scheduler_service.integration_contract()})


@scheduler_bp.route("/api/calendars")
def api_calendars():
    try:
        calendars = scheduler_service.list_calendars()
    except Exception as exc:
        return _json_error(str(exc), 500)
    return jsonify(
        {
            "ok": True,
            "default_calendar_id": scheduler_store.get_default_calendar_id(),
            "calendars": calendars,
        }
    )


@scheduler_bp.route("/api/calendars/default", methods=["POST"])
def api_set_default_calendar():
    payload = request.get_json(silent=True) or {}
    try:
        calendar = scheduler_service.set_default_calendar(payload.get("calendar_id", ""))
    except SchedulerError as exc:
        return _json_error(str(exc))
    return jsonify({"ok": True, "calendar": calendar})


@scheduler_bp.route("/api/oauth/configure", methods=["POST"])
def api_save_google_oauth_config():
    payload = request.get_json(silent=True) or {}
    try:
        result = scheduler_service.save_google_oauth_web_config(
            payload,
            redirect_uri=url_for("scheduler.oauth_callback", _external=True),
        )
    except SchedulerError as exc:
        return _json_error(str(exc))
    return jsonify({"ok": True, **result})


@scheduler_bp.route("/api/oauth/configure", methods=["DELETE"])
def api_clear_google_oauth_config():
    scheduler_service.clear_google_oauth_web_config()
    return jsonify({"ok": True})


@scheduler_bp.route("/api/profile/basic-daily", methods=["POST"])
def api_save_basic_daily_profile():
    payload = request.get_json(silent=True) or {}
    try:
        profile = scheduler_service.save_basic_daily_profile(payload)
    except SchedulerError as exc:
        return _json_error(str(exc))
    return jsonify({"ok": True, "profile": profile})


@scheduler_bp.route("/api/templates/basic-daily/preview", methods=["POST"])
def api_preview_basic_daily():
    payload = request.get_json(silent=True) or {}
    try:
        preview = scheduler_service.preview_basic_daily_schedule(payload)
    except SchedulerError as exc:
        return _json_error(str(exc))
    return jsonify({"ok": True, "preview": preview})


@scheduler_bp.route("/api/templates/basic-daily", methods=["POST"])
def api_apply_basic_daily():
    payload = request.get_json(silent=True) or {}
    confirm_conflicts = bool(payload.pop("confirm_conflicts", False))
    try:
        result = scheduler_service.apply_basic_daily_schedule(
            payload,
            confirm_conflicts=confirm_conflicts,
        )
    except SchedulerError as exc:
        return _json_error(str(exc))
    return jsonify({"ok": True, **result})


@scheduler_bp.route("/api/events")
def api_list_events():
    start = request.args.get("start") or date.today().isoformat()
    end = request.args.get("end") or (date.today() + timedelta(days=14)).isoformat()
    calendar_id = request.args.get("calendar_id")
    try:
        events = scheduler_service.list_agenda_events(start=start, end=end, calendar_id=calendar_id)
    except SchedulerError as exc:
        return _json_error(str(exc))
    return jsonify({"ok": True, "events": events})


@scheduler_bp.route("/api/events/preview-conflicts", methods=["POST"])
def api_preview_conflicts():
    payload = request.get_json(silent=True) or {}
    try:
        conflicts = scheduler_service.preview_conflicts(
            payload,
            calendar_id=payload.get("calendar_id"),
            ignore_event_id=payload.get("event_id"),
        )
    except SchedulerError as exc:
        return _json_error(str(exc))
    return jsonify({"ok": True, "conflicts": conflicts})


@scheduler_bp.route("/api/events", methods=["POST"])
def api_create_event():
    payload = request.get_json(silent=True) or {}
    confirm_conflicts = bool(payload.pop("confirm_conflicts", False))
    try:
        result = scheduler_service.create_event(payload, confirm_conflicts=confirm_conflicts)
    except SchedulerError as exc:
        return _json_error(str(exc))
    return jsonify({"ok": True, **result})


@scheduler_bp.route("/api/events/<event_id>", methods=["GET"])
def api_get_event(event_id: str):
    calendar_id = request.args.get("calendar_id", "")
    try:
        event = scheduler_service.get_event(calendar_id, event_id)
    except SchedulerError as exc:
        return _json_error(str(exc))
    return jsonify({"ok": True, "event": event})


@scheduler_bp.route("/api/events/<event_id>", methods=["PATCH", "POST"])
def api_update_event(event_id: str):
    payload = request.get_json(silent=True) or {}
    calendar_id = payload.get("calendar_id") or request.args.get("calendar_id", "")
    confirm_conflicts = bool(payload.pop("confirm_conflicts", False))
    try:
        result = scheduler_service.update_event(
            calendar_id,
            event_id,
            payload,
            confirm_conflicts=confirm_conflicts,
        )
    except SchedulerError as exc:
        return _json_error(str(exc))
    return jsonify({"ok": True, **result})


@scheduler_bp.route("/api/events/<event_id>", methods=["DELETE"])
def api_delete_event(event_id: str):
    payload = request.get_json(silent=True) or {}
    calendar_id = payload.get("calendar_id") or request.args.get("calendar_id", "")
    try:
        scheduler_service.delete_event(calendar_id, event_id)
    except SchedulerError as exc:
        return _json_error(str(exc))
    return jsonify({"ok": True})


@scheduler_bp.route("/api/imports/preview", methods=["POST"])
def api_preview_import():
    upload = request.files.get("ics_file")
    if not upload:
        return _json_error("Choose an .ics file to preview.")
    try:
        preview = scheduler_service.preview_ics(upload.read(), upload.filename or "import.ics")
    except SchedulerError as exc:
        return _json_error(str(exc))
    return jsonify({"ok": True, "preview": preview})


@scheduler_bp.route("/api/imports/<batch_id>/commit", methods=["POST"])
def api_commit_import(batch_id: str):
    try:
        result = scheduler_service.import_preview_batch(batch_id, confirm_conflicts=True)
    except SchedulerError as exc:
        return _json_error(str(exc))
    return jsonify({"ok": True, **result})
