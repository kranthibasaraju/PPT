"""Admin + invite onboarding routes for smart reminders."""
from __future__ import annotations

from flask import Blueprint, jsonify, redirect, render_template_string, request, session, url_for

from config.settings import TELEGRAM_BOT_TOKEN
from src.notify import google_oauth, store

onboarding_bp = Blueprint("onboarding", __name__)

_ADMIN_HTML = """<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PPT Board — Reminder Users</title>
<style>
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0f0f0f;color:#e8e8e8;margin:0}
header{background:#1a1a2e;padding:16px 20px;border-bottom:1px solid #2a2a4a;display:flex;justify-content:space-between;align-items:center;gap:12px}
a{color:#7c83ff;text-decoration:none}
.container{max-width:760px;margin:0 auto;padding:18px}
.card{background:#1e1e2e;border:1px solid #2a2a4a;border-radius:12px;padding:16px;margin-bottom:12px}
.label{font-size:.72rem;color:#777;text-transform:uppercase;letter-spacing:.05em;margin-bottom:8px}
input,select,textarea,button{font:inherit}
input,select,textarea{width:100%;background:#0f0f0f;border:1px solid #2a2a4a;color:#e8e8e8;border-radius:8px;padding:10px 12px;margin-bottom:10px}
button{background:#7c83ff;color:#fff;border:none;border-radius:8px;padding:10px 14px;cursor:pointer}
.row{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.pill{display:inline-block;border:1px solid #2a2a4a;border-radius:999px;padding:3px 9px;font-size:.72rem;color:#9aa0d3}
.muted{color:#888;font-size:.85rem}
</style>
</head><body>
<header>
  <div>
    <div style="font-size:1.05rem;font-weight:600;color:#c8d0ff">Smart Reminder Users</div>
    <div class="muted">Invite users, monitor onboarding, and keep reminder identities separated.</div>
  </div>
  <nav><a href="/board/">Dashboard</a> · <a href="/">Planner</a> · <a href="/notify">Notify</a></nav>
</header>
<div class="container">
  <div class="card">
    <div class="label">Invite User</div>
    <form method="POST" action="{{ url_for('onboarding.create_invite_route') }}">
      <input name="email" type="email" placeholder="user@gmail.com" required>
      <button type="submit">Create invite</button>
    </form>
    {% if latest_invite %}
    <div class="muted">Latest invite:
      <a href="{{ url_for('onboarding.onboarding_home', invite_token=latest_invite.token, _external=True) }}">{{ url_for('onboarding.onboarding_home', invite_token=latest_invite.token, _external=True) }}</a>
    </div>
    {% endif %}
  </div>

  <div class="card">
    <div class="label">Users</div>
    {% for user in users %}
    <div style="padding:10px 0;border-bottom:1px solid #2a2a4a">
      <div style="display:flex;justify-content:space-between;gap:12px;align-items:center">
        <strong>{{ user.display_name or user.email }}</strong>
        <span class="pill">{{ user.status }}</span>
      </div>
      <div class="muted">{{ user.email or 'No email yet' }}</div>
      <div class="muted">Google: {{ 'connected' if user.calendar_connected else 'pending' }} · Telegram: {{ user.link_state or 'pending' }}</div>
    </div>
    {% else %}
    <div class="muted">No onboarded users yet.</div>
    {% endfor %}
  </div>

  <div class="card">
    <div class="label">Invites</div>
    {% for invite in invites %}
    <div style="padding:10px 0;border-bottom:1px solid #2a2a4a">
      <div style="display:flex;justify-content:space-between;gap:12px;align-items:center">
        <strong>{{ invite.email }}</strong>
        <span class="pill">{{ invite.status }}</span>
      </div>
      <div class="muted">Expires {{ invite.expires_at }}</div>
      <div class="muted"><a href="{{ url_for('onboarding.onboarding_home', invite_token=invite.token) }}">Open onboarding</a></div>
    </div>
    {% else %}
    <div class="muted">No invites yet.</div>
    {% endfor %}
  </div>
</div>
</body></html>"""

_ONBOARDING_HTML = """<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PPT Board — Smart Reminders Onboarding</title>
<style>
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0f0f0f;color:#e8e8e8;margin:0}
.page{max-width:760px;margin:0 auto;padding:24px 16px}
.hero{margin-bottom:18px}
.hero h1{font-size:1.5rem;margin:0 0 6px;color:#d9ddff}
.hero p{color:#9aa0d3;line-height:1.5}
.step{background:#1e1e2e;border:1px solid #2a2a4a;border-radius:14px;padding:16px;margin-bottom:12px}
.step h2{font-size:1rem;margin:0 0 6px}
.meta{font-size:.82rem;color:#888;line-height:1.5}
.ok{color:#6ee7b7}
.pending{color:#fbbf24}
.err{color:#f87171}
a{color:#7c83ff;text-decoration:none}
input,select,textarea,button{font:inherit}
input,select,textarea{width:100%;background:#0f0f0f;border:1px solid #2a2a4a;color:#e8e8e8;border-radius:8px;padding:10px 12px;margin:8px 0 10px}
textarea{min-height:88px;resize:vertical}
button{background:#7c83ff;color:#fff;border:none;border-radius:8px;padding:10px 14px;cursor:pointer}
.row{display:grid;grid-template-columns:1fr 1fr;gap:12px}
code{background:#111827;border-radius:6px;padding:2px 6px}
</style>
</head><body>
<div class="page">
  <div class="hero">
    <h1>Smart Reminders Onboarding</h1>
    <p>Connect Google, link Telegram, set your timezone and quiet hours, and create your first personal reminder or habit.</p>
    <div class="meta">Invite for <strong>{{ invite.email }}</strong> · status <strong>{{ invite.status }}</strong></div>
    {% if error %}<div class="err" style="margin-top:10px">{{ error }}</div>{% endif %}
  </div>

  <div class="step">
    <h2>1. Google sign-in + Calendar access</h2>
    {% if google_connected %}
      <div class="meta ok">Connected as {{ user.email }}.</div>
    {% else %}
      <div class="meta pending">This invite only works for the invited Google account.</div>
      <a href="{{ url_for('onboarding.start_google_onboarding', invite_token=invite.token) }}"><button type="button">Continue with Google</button></a>
    {% endif %}
  </div>

  <div class="step">
    <h2>2. Telegram link</h2>
    {% if telegram_linked %}
      <div class="meta ok">Linked to Telegram chat {{ telegram_link.telegram_chat_id }}{% if telegram_link.telegram_username %} (@{{ telegram_link.telegram_username }}){% endif %}.</div>
    {% elif user %}
      <div class="meta pending">Open the PPT bot and send this exact command:</div>
      <div style="margin-top:10px"><code>/start link_{{ telegram_link.link_token }}</code></div>
      <div class="meta" style="margin-top:10px">After you send it, this page can be refreshed or polled at <code>{{ url_for('onboarding.telegram_status', invite_token=invite.token, _external=True) }}</code>.</div>
    {% else %}
      <div class="meta">Google sign-in unlocks the Telegram link step.</div>
    {% endif %}
  </div>

  <div class="step">
    <h2>3. Minimal profile + first reminder</h2>
    {% if onboarding_complete %}
      <div class="meta ok">Onboarding complete. Smart reminders are ready for {{ user.display_name or user.email }}.</div>
    {% elif user and telegram_linked %}
      <form method="POST" action="{{ url_for('onboarding.save_profile', invite_token=invite.token) }}">
        <div class="row">
          <div>
            <label>Timezone</label>
            <input name="timezone" value="{{ profile.timezone or 'America/New_York' }}" required>
          </div>
          <div>
            <label>Display name</label>
            <input name="display_name" value="{{ user.display_name or '' }}" required>
          </div>
        </div>
        <div class="row">
          <div>
            <label>Quiet hours start</label>
            <input name="quiet_hours_start" type="time" value="{{ profile.quiet_hours_start or '22:00' }}" required>
          </div>
          <div>
            <label>Quiet hours end</label>
            <input name="quiet_hours_end" type="time" value="{{ profile.quiet_hours_end or '07:00' }}" required>
          </div>
        </div>
        <div class="row">
          <div>
            <label>First item type</label>
            <select name="first_item_kind">
              <option value="reminder">Reminder</option>
              <option value="habit">Habit</option>
            </select>
          </div>
          <div>
            <label>Reminder time</label>
            <input name="first_item_time" type="time" value="09:00" required>
          </div>
        </div>
        <label>First reminder or habit</label>
        <input name="first_item_title" placeholder="Drink water, review your calendar, stand up and stretch..." required>
        <label>Optional detail</label>
        <textarea name="first_item_description" placeholder="Extra context for the reminder or habit..."></textarea>
        <button type="submit">Finish onboarding</button>
      </form>
    {% else %}
      <div class="meta">Finish Google and Telegram first.</div>
    {% endif %}
  </div>
</div>
</body></html>"""


def _invite_error(message: str, invite_token: str) -> str:
    return url_for("onboarding.onboarding_home", invite_token=invite_token, error=message)


@onboarding_bp.route("/notify/users")
def admin_users():
    invites = store.list_invites()
    users = store.list_users()
    latest_invite = invites[0] if invites else None
    return render_template_string(_ADMIN_HTML, invites=invites, users=users, latest_invite=latest_invite)


@onboarding_bp.route("/notify/users/invite", methods=["POST"])
def create_invite_route():
    email = request.form.get("email", "").strip()
    if email:
        store.create_invite(email)
    return redirect(url_for("onboarding.admin_users"))


@onboarding_bp.route("/notify/onboarding/<invite_token>")
def onboarding_home(invite_token: str):
    invite = store.get_invite(invite_token)
    if not invite:
        return "Invite not found.", 404

    user = store.get_user(invite["accepted_user_id"]) if invite.get("accepted_user_id") else None
    google_account = store.get_user_google_account(user["id"]) if user else None
    telegram_link = store.get_user_telegram_link(user["id"]) if user else None
    if user and google_account and (not telegram_link or telegram_link.get("link_state") != "linked"):
        telegram_link = store.ensure_telegram_link_token(user["id"])

    return render_template_string(
        _ONBOARDING_HTML,
        invite=invite,
        user=user,
        profile=store.get_profile(user["id"]) if user else {},
        google_connected=bool(google_account),
        telegram_link=telegram_link or {},
        telegram_linked=bool(telegram_link and telegram_link.get("link_state") == "linked"),
        onboarding_complete=invite.get("status") == "completed",
        error=request.args.get("error"),
        bot_token_prefix=TELEGRAM_BOT_TOKEN[:8],
    )


@onboarding_bp.route("/notify/onboarding/<invite_token>/google/start")
def start_google_onboarding(invite_token: str):
    invite = store.get_invite(invite_token)
    if not invite:
        return "Invite not found.", 404
    callback_url = url_for("onboarding.google_callback", _external=True)
    auth_url, state = google_oauth.authorization_url(callback_url=callback_url)
    session["onboarding_invite_token"] = invite_token
    session["onboarding_google_state"] = state
    return redirect(auth_url)


@onboarding_bp.route("/notify/onboarding/google/callback")
def google_callback():
    invite_token = session.get("onboarding_invite_token")
    expected_state = session.get("onboarding_google_state")
    returned_state = request.args.get("state")
    if not invite_token or not expected_state or returned_state != expected_state:
        return "Invalid onboarding state.", 400

    callback_url = url_for("onboarding.google_callback", _external=True)
    try:
        result = google_oauth.exchange_callback(
            full_callback_url=request.url,
            callback_url=callback_url,
        )
        user_info = result["user_info"]
        user = store.accept_invite(
            invite_token,
            google_sub=user_info["sub"],
            email=user_info["email"],
            display_name=user_info["name"],
        )
        store.save_user_google_account(
            user["id"],
            google_sub=user_info["sub"],
            email=user_info["email"],
            token_json=result["token_json"],
            scopes=result["scopes"],
        )
        store.ensure_telegram_link_token(user["id"])
    except Exception as exc:
        return redirect(_invite_error(str(exc), invite_token))

    session.pop("onboarding_google_state", None)
    return redirect(url_for("onboarding.onboarding_home", invite_token=invite_token))


@onboarding_bp.route("/notify/onboarding/<invite_token>/telegram/status")
def telegram_status(invite_token: str):
    invite = store.get_invite(invite_token)
    if not invite or not invite.get("accepted_user_id"):
        return jsonify({"linked": False, "state": "pending"})
    link = store.get_user_telegram_link(invite["accepted_user_id"]) or {}
    return jsonify(
        {
            "linked": link.get("link_state") == "linked",
            "state": link.get("link_state") or "pending",
            "chat_id": link.get("telegram_chat_id"),
            "username": link.get("telegram_username"),
        }
    )


@onboarding_bp.route("/notify/onboarding/<invite_token>/profile", methods=["POST"])
def save_profile(invite_token: str):
    invite = store.get_invite(invite_token)
    if not invite or not invite.get("accepted_user_id"):
        return redirect(_invite_error("Finish Google sign-in first.", invite_token))

    user_id = int(invite["accepted_user_id"])
    link = store.get_user_telegram_link(user_id)
    if not link or link.get("link_state") != "linked":
        return redirect(_invite_error("Link Telegram before saving your profile.", invite_token))

    store.upsert_user_profile(
        user_id,
        display_name=request.form.get("display_name", "").strip(),
        timezone=request.form.get("timezone", "").strip() or "America/New_York",
        quiet_hours_start=request.form.get("quiet_hours_start", "22:00"),
        quiet_hours_end=request.form.get("quiet_hours_end", "07:00"),
    )

    title = request.form.get("first_item_title", "").strip()
    detail = request.form.get("first_item_description", "").strip()
    remind_at = request.form.get("first_item_time", "09:00")
    kind = request.form.get("first_item_kind", "reminder")
    if not title:
        return redirect(_invite_error("Add a first reminder or habit.", invite_token))

    if kind == "habit":
        store.add_habit(
            title,
            description=detail,
            remind_at=remind_at,
            user_id=user_id,
        )
    else:
        store.add_reminder(
            title,
            message=detail,
            remind_at=remind_at,
            repeat="daily",
            user_id=user_id,
        )
    store.mark_invite_completed(invite_token)
    return redirect(url_for("onboarding.onboarding_home", invite_token=invite_token))
