"""Business logic for the Google-backed PPT scheduler."""
from __future__ import annotations

import hashlib
import logging
import os
from calendar import monthrange
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.scheduler import google_client, store

log = logging.getLogger(__name__)

DEFAULT_TIMEZONE = os.getenv("PPT_DEFAULT_TIMEZONE", "America/New_York")
CONFLICT_WINDOW_DAYS = 60
BASIC_DAILY_ROUTINE_KEY = "basic-daily-rhythm"
BASIC_DAILY_PROFILE_KEY = "basic_daily_profile"
BASIC_DAILY_PROFILE_FIELDS = (
    "timezone",
    "wake_time",
    "breakfast_time",
    "work_notes_time",
    "eat_time",
    "gaming_off_time",
    "sleep_on_time",
)
BASIC_DAILY_ROUTINE_SLUGS = (
    "sleep-off",
    "wake-up",
    "get-ready",
    "breakfast-ready",
    "work-notes-ready",
    "eat-something",
    "gaming-session-off",
    "sleep-on",
)


class SchedulerError(RuntimeError):
    """Base exception for scheduler failures."""


class SchedulerValidationError(SchedulerError):
    """Raised when user input is invalid."""


def _client() -> google_client.CalendarApiClient:
    return google_client.CalendarApiClient()


def google_oauth_web_config_draft() -> dict[str, str]:
    stored_config = store.get_google_oauth_client_config() or {}
    web_config = stored_config.get("web", {}) if isinstance(stored_config, dict) else {}
    return {
        "client_id": web_config.get("client_id", ""),
        "client_secret": "",
        "project_id": web_config.get("project_id", "ppt-scheduler"),
        "auth_uri": web_config.get("auth_uri", google_client.DEFAULT_AUTH_URI),
        "token_uri": web_config.get("token_uri", google_client.DEFAULT_TOKEN_URI),
    }


def connection_status() -> dict[str, Any]:
    client = _client()
    status = client.status()
    default_calendar_id = store.get_default_calendar_id()
    status["default_calendar_id"] = default_calendar_id
    status["default_calendar_summary"] = None
    calendars: list[dict[str, Any]] = []
    if status["connected"]:
        try:
            calendars = list_calendars()
            for cal in calendars:
                if cal["id"] == default_calendar_id:
                    status["default_calendar_summary"] = cal["summary"]
                    break
        except Exception as exc:
            status["calendar_error"] = str(exc)
    status["writable_calendars"] = calendars
    basic_daily_profile = get_basic_daily_profile()
    saved_profile = saved_basic_daily_profile()
    agenda_preview = current_events_preview(calendar_id=default_calendar_id)
    setup_status = build_setup_status(
        status=status,
        agenda_preview=agenda_preview,
        basic_daily_profile_saved=saved_profile is not None,
    )
    status["basic_daily_profile"] = basic_daily_profile
    status["basic_daily_profile_saved"] = saved_profile is not None
    status["agenda_preview"] = agenda_preview
    status["setup_status"] = setup_status
    status["next_actions"] = _next_actions_from_setup_items(setup_status["steps"])
    status["auth_integration"] = build_auth_integration(status)
    return status


def build_auth_integration(status: dict[str, Any]) -> dict[str, Any]:
    configured = bool(status.get("configured"))
    connected = bool(status.get("connected"))
    access_state = "done" if connected else ("pending" if configured else "blocked")
    login_state = "done" if connected else ("pending" if configured else "blocked")

    return {
        "provider": "google-calendar",
        "mode": "browser-oauth",
        "configured": configured,
        "connected": connected,
        "config_source": status.get("config_source", "none"),
        "connect_path": "/scheduler/connect",
        "connect_api_path": "/scheduler/api/connect",
        "disconnect_path": "/scheduler/disconnect",
        "disconnect_api_path": "/scheduler/api/disconnect",
        "callback_path": "/scheduler/oauth/callback",
        "redirect_uri": status.get("redirect_uri"),
        "scopes": list(status.get("scopes", [])),
        "browser_session_reuse_supported": True,
        "requires_user_consent": True,
        "required_access": [
            {
                "key": "google_account_login",
                "label": "Google account sign-in",
                "state": login_state,
                "detail": (
                    "Google account access is already connected for this scheduler."
                    if connected
                    else (
                        "Open the scheduler connect flow in a browser and sign in with the Google account you want PPT to manage."
                        if configured
                        else "Configure Google OAuth before a user can sign in and grant calendar access."
                    )
                ),
            },
            {
                "key": "calendar_events_access",
                "label": "Google Calendar event read/write access",
                "scope": "https://www.googleapis.com/auth/calendar.events",
                "state": access_state,
                "detail": (
                    "Granted. PPT can read, create, update, and delete calendar events after connection."
                    if connected
                    else (
                        "This access is requested during Google consent so PPT can schedule and read events."
                        if configured
                        else "OAuth must be configured before PPT can request event access."
                    )
                ),
            },
            {
                "key": "calendar_list_access",
                "label": "Writable calendar discovery access",
                "scope": "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
                "state": access_state,
                "detail": (
                    "Granted. PPT can list the user's calendars so one writable target can be selected."
                    if connected
                    else (
                        "This access is requested during Google consent so PPT can discover writable calendars."
                        if configured
                        else "OAuth must be configured before PPT can request calendar-list access."
                    )
                ),
            },
        ],
        "notes": [
            "The scheduler owns the Google OAuth flow and should stay the source of truth for connected-account state.",
            "A browser automation plugin can open the connect path and reuse an existing signed-in browser session, but production users still grant access through this app-owned OAuth flow.",
        ],
    }


def integration_contract() -> dict[str, Any]:
    status = connection_status()
    return {
        "id": "ppt-scheduler",
        "name": "PPT Scheduler",
        "kind": "web-module",
        "host_app": "ppt-board",
        "ui_path": "/scheduler",
        "source_of_truth": "google-calendar",
        "auth": status["auth_integration"],
        "required_inputs": [
            {
                "key": "google_account",
                "label": "Connected Google account",
                "state": "done" if status.get("connected") else "pending",
            },
            {
                "key": "default_calendar",
                "label": "Selected writable default calendar",
                "state": "done" if status.get("default_calendar_summary") else "pending",
            },
            {
                "key": "timezone",
                "label": "Scheduler timezone",
                "state": "done" if status["basic_daily_profile"].get("timezone") else "pending",
            },
            {
                "key": "daily_anchors",
                "label": "Daily anchor inputs",
                "state": "done" if status.get("basic_daily_profile_saved") else "pending",
            },
        ],
        "calendar_access": {
            "writes_target": "selected_default_calendar",
            "current_event_preview_scope": "selected_default_calendar",
            "conflict_check_scope": "all_visible_calendars",
            "agenda_api_path": "/scheduler/api/events",
            "status_api_path": "/scheduler/api/status",
        },
        "safe_agent_actions": [
            "open scheduler UI",
            "start Google connect flow",
            "list writable calendars",
            "set default calendar",
            "read current events",
            "create event",
            "update event",
            "delete event",
            "apply basic daily rhythm",
            "preview and import ICS",
        ],
        "next_actions": status.get("next_actions", []),
    }


def build_setup_status(
    *,
    status: dict[str, Any],
    agenda_preview: dict[str, Any],
    basic_daily_profile_saved: bool,
) -> dict[str, Any]:
    default_calendar_id = status.get("default_calendar_id")
    routine_status = basic_daily_routine_status(default_calendar_id)
    items: list[dict[str, Any]] = []

    items.append(
        {
            "key": "oauth_configured",
            "label": "Google OAuth configured",
            "state": "done" if status.get("configured") else "pending",
            "detail": (
                "Google OAuth credentials are configured and ready."
                if status.get("configured")
                else "Add Google OAuth client credentials outside tracked source before connecting."
            ),
            "next_action": None
            if status.get("configured")
            else {
                "label": "Review OAuth requirements",
                "href": "#google-connection",
            },
        }
    )

    connected_state = "done" if status.get("connected") else ("pending" if status.get("configured") else "blocked")
    items.append(
        {
            "key": "google_connected",
            "label": "Google account connected",
            "state": connected_state,
            "detail": (
                "Google Calendar access token is connected for this user."
                if status.get("connected")
                else (
                    "Connect your Google account through the local OAuth flow."
                    if status.get("configured")
                    else "OAuth must be configured before the scheduler can connect to Google."
                )
            ),
            "next_action": None
            if status.get("connected")
            else {
                "label": "Connect Google Calendar" if status.get("configured") else "Configure Google OAuth first",
                "href": "/scheduler/connect" if status.get("configured") else "#google-connection",
            },
        }
    )

    calendar_selected = bool(default_calendar_id and status.get("default_calendar_summary"))
    missing_calendar_detail = "Choose one writable Google calendar as the scheduler write target."
    if default_calendar_id and not status.get("default_calendar_summary"):
        missing_calendar_detail = (
            "The saved default calendar is unavailable. Choose another writable Google calendar."
        )
    items.append(
        {
            "key": "default_calendar_selected",
            "label": "Default writable calendar selected",
            "state": "done" if calendar_selected else ("pending" if status.get("connected") else "blocked"),
            "detail": (
                f"Default calendar set to {status['default_calendar_summary']}."
                if calendar_selected
                else (missing_calendar_detail if status.get("connected") else "Connect Google before choosing a default calendar.")
            ),
            "next_action": None
            if calendar_selected
            else {
                "label": "Choose default calendar" if status.get("connected") else "Connect Google first",
                "href": "#calendar-setup" if status.get("connected") else "/scheduler/connect",
            },
        }
    )

    if agenda_preview["state"] == "ready":
        preview_detail = (
            f"Read access confirmed. {agenda_preview['event_count']} upcoming event"
            f"{'' if agenda_preview['event_count'] == 1 else 's'} loaded from the default calendar."
        )
        preview_state = "done"
        preview_action = None
    elif agenda_preview["state"] == "error":
        preview_detail = f"Could not read current events: {agenda_preview['error']}"
        preview_state = "pending"
        preview_action = {
            "label": "Fix calendar access",
            "href": "#setup-todo",
        }
    else:
        preview_detail = "Select a default calendar before verifying current event access."
        preview_state = "blocked"
        preview_action = {
            "label": "Choose default calendar",
            "href": "#calendar-setup",
        }
    items.append(
        {
            "key": "current_events_readable",
            "label": "Current events readable",
            "state": preview_state,
            "detail": preview_detail,
            "next_action": preview_action,
        }
    )

    inputs_state = "done" if basic_daily_profile_saved else ("pending" if calendar_selected else "blocked")
    items.append(
        {
            "key": "daily_schedule_inputs_saved",
            "label": "Daily schedule inputs saved",
            "state": inputs_state,
            "detail": (
                "Saved timezone and daily anchor inputs are ready to prefill the starter routine."
                if basic_daily_profile_saved
                else (
                    "Save your daily anchors so PPT can prefill the first schedule."
                    if calendar_selected
                    else "Choose a default calendar before saving daily scheduling inputs."
                )
            ),
            "next_action": None
            if basic_daily_profile_saved
            else {
                "label": "Save daily inputs" if calendar_selected else "Choose default calendar first",
                "href": "#starter-routine" if calendar_selected else "#calendar-setup",
            },
        }
    )

    if routine_status["complete"]:
        routine_detail = "The starter routine is already scheduled and managed by PPT."
        routine_state = "done"
        routine_action = None
    elif routine_status["scheduled_count"]:
        routine_detail = (
            f"Starter routine is only partially scheduled ({routine_status['scheduled_count']}/"
            f"{routine_status['required_count']} managed events found). Reapply it to restore the full routine."
        )
        routine_state = "pending"
        routine_action = {
            "label": "Reapply starter routine",
            "href": "#starter-routine",
        }
    else:
        routine_detail = (
            "Apply the Basic Daily Rhythm routine to create the first recurring schedule."
            if basic_daily_profile_saved
            else "Save daily inputs before scheduling the first starter routine."
        )
        routine_state = "pending" if basic_daily_profile_saved else "blocked"
        routine_action = {
            "label": "Apply starter routine" if basic_daily_profile_saved else "Save daily inputs first",
            "href": "#starter-routine",
        }
    items.append(
        {
            "key": "starter_routine_scheduled",
            "label": "First starter routine scheduled",
            "state": routine_state,
            "detail": routine_detail,
            "next_action": routine_action,
        }
    )

    complete_count = sum(1 for item in items if item["state"] == "done")
    return {
        "steps": items,
        "complete_count": complete_count,
        "total_count": len(items),
        "all_complete": complete_count == len(items),
    }


def _next_actions_from_setup_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    actions: list[dict[str, Any]] = []
    for item in items:
        action = item.get("next_action")
        if item.get("state") == "done" or not action:
            continue
        dedupe_key = (action["label"], action["href"])
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        actions.append(action)
        if len(actions) >= 3:
            break
    return actions


def current_events_preview(*, calendar_id: str | None = None, days: int = 7, limit: int = 5) -> dict[str, Any]:
    cal_id = calendar_id or store.get_default_calendar_id()
    today = date.today()
    end_date = today + timedelta(days=max(days - 1, 0))
    preview = {
        "state": "blocked",
        "calendar_id": cal_id,
        "range_start": today.isoformat(),
        "range_end": end_date.isoformat(),
        "events": [],
        "event_count": 0,
        "error": None,
    }
    if not cal_id:
        return preview
    try:
        events = list_agenda_events(
            start=today.isoformat(),
            end=end_date.isoformat(),
            calendar_id=cal_id,
        )
    except Exception as exc:
        preview["state"] = "error"
        preview["error"] = str(exc)
        return preview
    preview["state"] = "ready"
    preview["events"] = events[:limit]
    preview["event_count"] = len(events)
    return preview


def basic_daily_routine_status(calendar_id: str | None) -> dict[str, Any]:
    if not calendar_id:
        return {"complete": False, "scheduled_count": 0, "required_count": len(BASIC_DAILY_ROUTINE_SLUGS)}
    scheduled_count = 0
    for slug in BASIC_DAILY_ROUTINE_SLUGS:
        source_uid = f"{BASIC_DAILY_ROUTINE_KEY}:{slug}"
        if store.get_managed_event_by_source_uid(calendar_id, source_uid):
            scheduled_count += 1
    return {
        "complete": scheduled_count == len(BASIC_DAILY_ROUTINE_SLUGS),
        "scheduled_count": scheduled_count,
        "required_count": len(BASIC_DAILY_ROUTINE_SLUGS),
    }


def list_calendars() -> list[dict[str, Any]]:
    entries = _client().list_calendars()
    calendars: list[dict[str, Any]] = []
    for entry in entries:
        access_role = entry.get("accessRole", "reader")
        writable = access_role in {"writer", "owner"}
        calendars.append(
            {
                "id": entry["id"],
                "summary": entry.get("summaryOverride") or entry.get("summary") or entry["id"],
                "timeZone": entry.get("timeZone") or DEFAULT_TIMEZONE,
                "primary": bool(entry.get("primary")),
                "selected": entry.get("selected", True),
                "hidden": bool(entry.get("hidden")),
                "accessRole": access_role,
                "writable": writable,
            }
        )
    calendars.sort(key=lambda cal: (not cal["primary"], cal["summary"].lower()))
    return calendars


def writable_calendars() -> list[dict[str, Any]]:
    return [cal for cal in list_calendars() if cal["writable"]]


def default_calendar_id() -> str:
    calendar_id = store.get_default_calendar_id()
    if not calendar_id:
        raise SchedulerValidationError("Choose a default writable calendar before scheduling events.")
    return calendar_id


def set_default_calendar(calendar_id: str) -> dict[str, Any]:
    calendar = next((cal for cal in writable_calendars() if cal["id"] == calendar_id), None)
    if not calendar:
        raise SchedulerValidationError("Selected calendar is not writable.")
    store.set_default_calendar_id(calendar_id)
    return calendar


def disconnect_google() -> None:
    _client().disconnect()
    store.delete_setting("default_calendar_id")


def save_google_oauth_web_config(
    payload: dict[str, Any] | None = None,
    *,
    redirect_uri: str | None = None,
) -> dict[str, Any]:
    payload = payload or {}
    existing = store.get_google_oauth_client_config() or {}
    existing_web = existing.get("web", {}) if isinstance(existing, dict) else {}

    client_id = str(payload.get("client_id") or "").strip()
    client_secret = str(payload.get("client_secret") or "").strip()
    project_id = str(payload.get("project_id") or "ppt-scheduler").strip() or "ppt-scheduler"
    auth_uri = str(payload.get("auth_uri") or google_client.DEFAULT_AUTH_URI).strip() or google_client.DEFAULT_AUTH_URI
    token_uri = str(payload.get("token_uri") or google_client.DEFAULT_TOKEN_URI).strip() or google_client.DEFAULT_TOKEN_URI

    if not client_id:
        raise SchedulerValidationError("Google OAuth client ID is required.")
    if not client_secret:
        client_secret = str(existing_web.get("client_secret") or "").strip()
    if not client_secret:
        raise SchedulerValidationError("Google OAuth client secret is required.")

    config = {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "project_id": project_id,
            "auth_uri": auth_uri,
            "token_uri": token_uri,
            "redirect_uris": [_client().redirect_uri(redirect_uri)],
        }
    }
    store.set_google_oauth_client_config(config)
    store.clear_token()
    return {
        "config_source": "web",
        "redirect_uri": config["web"]["redirect_uris"][0],
        "project_id": project_id,
        "client_id": client_id,
    }


def clear_google_oauth_web_config() -> None:
    store.clear_google_oauth_client_config()
    store.clear_token()


def basic_daily_profile_defaults() -> dict[str, str]:
    return {
        "timezone": DEFAULT_TIMEZONE,
        "wake_time": "07:30",
        "breakfast_time": "08:30",
        "work_notes_time": "09:00",
        "eat_time": "13:00",
        "gaming_off_time": "22:00",
        "sleep_on_time": "23:00",
    }


def saved_basic_daily_profile() -> dict[str, str] | None:
    raw_profile = store.get_setting(BASIC_DAILY_PROFILE_KEY)
    if not raw_profile:
        return None
    if not isinstance(raw_profile, dict):
        return None
    normalized = normalize_basic_daily_config(
        {
            **raw_profile,
            "start_date": date.today().isoformat(),
            "calendar_id": store.get_default_calendar_id(),
        }
    )
    return {field: normalized[field] for field in BASIC_DAILY_PROFILE_FIELDS}


def get_basic_daily_profile() -> dict[str, str]:
    return saved_basic_daily_profile() or basic_daily_profile_defaults()


def save_basic_daily_profile(payload: dict[str, Any] | None = None) -> dict[str, str]:
    normalized = normalize_basic_daily_config(payload)
    profile = {field: normalized[field] for field in BASIC_DAILY_PROFILE_FIELDS}
    store.set_setting(BASIC_DAILY_PROFILE_KEY, profile)
    return profile


def basic_daily_schedule_defaults(*, start_date: str | None = None) -> dict[str, Any]:
    defaults = {
        "calendar_id": store.get_default_calendar_id(),
        "start_date": start_date or date.today().isoformat(),
        **basic_daily_profile_defaults(),
    }
    raw_profile = store.get_setting(BASIC_DAILY_PROFILE_KEY)
    if isinstance(raw_profile, dict):
        for field in BASIC_DAILY_PROFILE_FIELDS:
            value = raw_profile.get(field)
            if value:
                defaults[field] = value
    return defaults


def normalize_basic_daily_config(payload: dict[str, Any] | None) -> dict[str, Any]:
    payload = payload or {}
    defaults = basic_daily_schedule_defaults(start_date=str(payload.get("start_date") or date.today().isoformat()))
    timezone_name = str(payload.get("timezone") or defaults["timezone"]).strip() or DEFAULT_TIMEZONE
    try:
        ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise SchedulerValidationError(f"Unknown timezone: {timezone_name}") from exc

    normalized = {
        "calendar_id": (payload.get("calendar_id") or defaults["calendar_id"] or "").strip() or None,
        "start_date": _parse_date(str(payload.get("start_date") or defaults["start_date"])).isoformat(),
        "timezone": timezone_name,
    }
    for field, label in (
        ("wake_time", "Wake time"),
        ("breakfast_time", "Breakfast time"),
        ("work_notes_time", "Work notes time"),
        ("eat_time", "Eat something time"),
        ("gaming_off_time", "Gaming session off time"),
        ("sleep_on_time", "Sleep on time"),
    ):
        normalized[field] = _parse_clock_time(str(payload.get(field) or defaults[field]), label).strftime("%H:%M")
    return normalized


def preview_basic_daily_schedule(config: dict[str, Any] | None = None) -> dict[str, Any]:
    normalized = normalize_basic_daily_config(config)
    return {"config": normalized, "events": build_basic_daily_schedule(normalized)}


def build_basic_daily_schedule(config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    normalized = normalize_basic_daily_config(config)
    timezone_name = normalized["timezone"]
    start_day = _parse_date(normalized["start_date"])

    wake_dt = _combine_local_datetime(start_day, normalized["wake_time"], timezone_name)
    breakfast_dt = _combine_local_datetime(start_day, normalized["breakfast_time"], timezone_name)
    work_notes_dt = _combine_local_datetime(start_day, normalized["work_notes_time"], timezone_name)
    eat_dt = _combine_local_datetime(start_day, normalized["eat_time"], timezone_name)
    gaming_off_dt = _combine_local_datetime(start_day, normalized["gaming_off_time"], timezone_name)
    sleep_on_dt = _combine_local_datetime(start_day, normalized["sleep_on_time"], timezone_name)
    next_sleep_off_dt = _combine_local_datetime(start_day, normalized["wake_time"], timezone_name)
    if next_sleep_off_dt <= sleep_on_dt:
        next_sleep_off_dt += timedelta(days=1)

    return [
        _build_basic_daily_event(
            title="Sleep off",
            description="Ease out of sleep and turn alarms off.",
            start_dt=wake_dt,
            end_dt=wake_dt + timedelta(minutes=10),
            recurrence_kind="daily",
            slug="sleep-off",
        ),
        _build_basic_daily_event(
            title="Wake up",
            description="Get fully awake and start the day.",
            start_dt=wake_dt + timedelta(minutes=10),
            end_dt=wake_dt + timedelta(minutes=30),
            recurrence_kind="daily",
            slug="wake-up",
        ),
        _build_basic_daily_event(
            title="Get ready",
            description="Shower, dress, and get your setup in order.",
            start_dt=wake_dt + timedelta(minutes=30),
            end_dt=wake_dt + timedelta(minutes=75),
            recurrence_kind="daily",
            slug="get-ready",
        ),
        _build_basic_daily_event(
            title="Breakfast ready",
            description="Pause for breakfast before the work block starts.",
            start_dt=breakfast_dt,
            end_dt=breakfast_dt + timedelta(minutes=30),
            recurrence_kind="daily",
            slug="breakfast-ready",
        ),
        _build_basic_daily_event(
            title="Work notes ready",
            description="Weekday prep block for work notes, priorities, and open loops.",
            start_dt=work_notes_dt,
            end_dt=work_notes_dt + timedelta(minutes=30),
            recurrence_kind="weekdays",
            slug="work-notes-ready",
        ),
        _build_basic_daily_event(
            title="Eat something",
            description="Midday food reminder so energy does not crater.",
            start_dt=eat_dt,
            end_dt=eat_dt + timedelta(minutes=30),
            recurrence_kind="daily",
            slug="eat-something",
        ),
        _build_basic_daily_event(
            title="Gaming session off",
            description="Wrap gaming and start winding the evening down.",
            start_dt=gaming_off_dt,
            end_dt=gaming_off_dt + timedelta(minutes=15),
            recurrence_kind="daily",
            slug="gaming-session-off",
        ),
        _build_basic_daily_event(
            title="Sleep on",
            description="Lights out and transition into sleep mode.",
            start_dt=sleep_on_dt,
            end_dt=next_sleep_off_dt,
            recurrence_kind="daily",
            slug="sleep-on",
        ),
    ]


def apply_basic_daily_schedule(
    config: dict[str, Any] | None = None,
    *,
    confirm_conflicts: bool = False,
) -> dict[str, Any]:
    normalized = normalize_basic_daily_config(config)
    save_basic_daily_profile(normalized)
    calendar_id = normalized.get("calendar_id") or default_calendar_id()
    events = build_basic_daily_schedule(normalized)
    conflicts: list[dict[str, Any]] = []
    plan: list[tuple[dict[str, Any], dict[str, Any] | None]] = []
    existing_routine_event_ids: set[str] = set()

    for payload in events:
        existing = store.get_managed_event_by_source_uid(calendar_id, payload.get("source_uid"))
        if existing:
            existing_routine_event_ids.add(existing["google_event_id"])

    for payload in events:
        existing = store.get_managed_event_by_source_uid(calendar_id, payload.get("source_uid"))
        ignore_event_id = existing["google_event_id"] if existing else None
        payload_conflicts = preview_conflicts(
            payload,
            calendar_id=calendar_id,
            ignore_event_id=ignore_event_id,
            ignore_event_ids=existing_routine_event_ids,
        )
        for conflict in payload_conflicts:
            conflicts.append({"candidate_title": payload["title"], **conflict})
            if len(conflicts) >= 40:
                break
        plan.append((payload, existing))

    if conflicts and not confirm_conflicts:
        return {
            "applied": False,
            "requires_confirmation": True,
            "conflicts": conflicts,
            "config": {**normalized, "calendar_id": calendar_id},
            "events": events,
        }

    created_count = 0
    updated_count = 0
    applied_events: list[dict[str, Any]] = []

    for payload, existing in plan:
        if existing:
            try:
                result = update_event(
                    calendar_id,
                    existing["google_event_id"],
                    payload,
                    confirm_conflicts=True,
                )
                updated_count += 1
            except Exception:
                log.warning(
                    "Routine-managed event %s disappeared; recreating it.",
                    existing["google_event_id"],
                    exc_info=True,
                )
                store.remove_managed_event(calendar_id, existing["google_event_id"])
                result = create_event(
                    {**payload, "calendar_id": calendar_id},
                    confirm_conflicts=True,
                )
                created_count += 1
        else:
            result = create_event(
                {**payload, "calendar_id": calendar_id},
                confirm_conflicts=True,
            )
            created_count += 1
        applied_events.append(result["event"])

    return {
        "applied": True,
        "created_count": created_count,
        "updated_count": updated_count,
        "conflicts": conflicts,
        "config": {**normalized, "calendar_id": calendar_id},
        "events": applied_events,
    }


def list_agenda_events(*, start: str, end: str, calendar_id: str | None = None) -> list[dict[str, Any]]:
    cal_id = calendar_id or default_calendar_id()
    start_dt = _start_of_day(_parse_date(start), DEFAULT_TIMEZONE)
    end_dt = _start_of_day(_parse_date(end) + timedelta(days=1), DEFAULT_TIMEZONE)
    raw = _client().list_events(
        cal_id,
        time_min=start_dt.isoformat(),
        time_max=end_dt.isoformat(),
        single_events=True,
    )
    calendar_map = {cal["id"]: cal for cal in list_calendars()}
    summary = calendar_map.get(cal_id, {}).get("summary", cal_id)
    return [_normalize_google_event(item, cal_id, summary) for item in raw]


def get_event(calendar_id: str, event_id: str) -> dict[str, Any]:
    raw = _client().get_event(calendar_id, event_id)
    calendar_map = {cal["id"]: cal for cal in list_calendars()}
    summary = calendar_map.get(calendar_id, {}).get("summary", calendar_id)
    return _normalize_google_event(raw, calendar_id, summary)


def normalize_event_payload(payload: dict[str, Any]) -> dict[str, Any]:
    title = (payload.get("title") or payload.get("summary") or "").strip()
    if not title:
        raise SchedulerValidationError("Event title is required.")

    all_day = _to_bool(payload.get("all_day"))
    tz_name = (payload.get("timezone") or DEFAULT_TIMEZONE).strip() or DEFAULT_TIMEZONE

    normalized = {
        "title": title,
        "description": (payload.get("description") or payload.get("notes") or "").strip(),
        "location": (payload.get("location") or "").strip(),
        "timezone": tz_name,
        "all_day": all_day,
        "recurrence_kind": (payload.get("recurrence_kind") or "once").strip().lower(),
        "recurrence_rule": (payload.get("recurrence_rule") or "").strip() or None,
        "source_type": (payload.get("source_type") or "manual").strip().lower(),
        "source_uid": (payload.get("source_uid") or "").strip() or None,
    }

    if all_day:
        start_date = _parse_date(str(payload.get("start") or payload.get("start_date") or ""))
        end_date = _parse_date(str(payload.get("end") or payload.get("end_date") or start_date.isoformat()))
        if end_date < start_date:
            raise SchedulerValidationError("All-day event end date must not be before the start date.")
        normalized["start"] = start_date.isoformat()
        normalized["end"] = end_date.isoformat()
    else:
        start_dt = _parse_datetime(str(payload.get("start") or ""))
        end_dt = _parse_datetime(str(payload.get("end") or ""))
        if end_dt <= start_dt:
            raise SchedulerValidationError("Event end time must be after the start time.")
        zone = ZoneInfo(tz_name)
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=zone)
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=zone)
        normalized["start"] = start_dt.isoformat()
        normalized["end"] = end_dt.isoformat()

    if normalized["recurrence_kind"] != "custom" and normalized["recurrence_kind"] not in {
        "once",
        "daily",
        "weekdays",
        "weekly",
        "monthly",
    }:
        raise SchedulerValidationError("Unsupported recurrence preset.")

    if normalized["recurrence_kind"] == "custom" and not normalized["recurrence_rule"]:
        raise SchedulerValidationError("Custom recurrence requires a recurrence rule.")

    if normalized["recurrence_kind"] != "custom" and normalized["recurrence_kind"] != "once":
        normalized["recurrence_rule"] = build_recurrence_rule(
            normalized["recurrence_kind"],
            normalized["start"],
            all_day=all_day,
        )

    if normalized["recurrence_kind"] == "once":
        normalized["recurrence_rule"] = None

    return normalized


def build_recurrence_rule(kind: str, start: str, *, all_day: bool = False) -> str | None:
    kind = (kind or "once").lower()
    if kind == "once":
        return None
    if kind == "daily":
        return "RRULE:FREQ=DAILY"
    if kind == "weekdays":
        return "RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR"
    if kind == "weekly":
        return "RRULE:FREQ=WEEKLY"
    if kind == "monthly":
        dt = _payload_start_datetime({"start": start, "all_day": all_day, "timezone": DEFAULT_TIMEZONE})
        return f"RRULE:FREQ=MONTHLY;BYMONTHDAY={dt.day}"
    if kind == "custom":
        return None
    raise SchedulerValidationError("Unsupported recurrence preset.")


def preview_conflicts(
    payload: dict[str, Any],
    *,
    calendar_id: str | None = None,
    ignore_event_id: str | None = None,
    ignore_event_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    normalized = normalize_event_payload(payload)
    start_dt, end_dt = _payload_bounds(normalized)
    candidate_occurrences = _expand_occurrences(normalized, horizon_days=CONFLICT_WINDOW_DAYS)
    target_calendar_id = calendar_id or default_calendar_id()
    ignored_ids = set(ignore_event_ids or set())
    if ignore_event_id:
        ignored_ids.add(ignore_event_id)

    visible = [cal for cal in list_calendars() if not cal["hidden"]]
    calendar_entries = {cal["id"]: cal for cal in visible}
    if not visible:
        return []

    time_min = start_dt.isoformat()
    time_max = (start_dt + timedelta(days=CONFLICT_WINDOW_DAYS)).isoformat()
    seen: set[tuple[str, str, str]] = set()
    conflicts: list[dict[str, Any]] = []

    for cal in visible:
        raw_events = _client().list_events(
            cal["id"],
            time_min=time_min,
            time_max=time_max,
            single_events=True,
        )
        for event in raw_events:
            if event.get("id") in ignored_ids and cal["id"] == target_calendar_id:
                continue
            existing_start, existing_end = _google_event_bounds(event)
            if existing_start is None or existing_end is None:
                continue
            for occurrence_start, occurrence_end in candidate_occurrences:
                if _ranges_overlap(occurrence_start, occurrence_end, existing_start, existing_end):
                    dedupe_key = (cal["id"], event.get("id", ""), occurrence_start.isoformat())
                    if dedupe_key in seen:
                        continue
                    seen.add(dedupe_key)
                    conflicts.append(
                        {
                            "calendar_id": cal["id"],
                            "calendar_summary": calendar_entries[cal["id"]]["summary"],
                            "event_id": event.get("id"),
                            "summary": event.get("summary") or "(untitled event)",
                            "existing_start": _display_datetime(existing_start, _is_all_day_google_event(event)),
                            "existing_end": _display_datetime(existing_end, _is_all_day_google_event(event), end_value=True),
                            "candidate_start": _display_datetime(occurrence_start, normalized["all_day"]),
                            "candidate_end": _display_datetime(occurrence_end, normalized["all_day"], end_value=True),
                            "html_link": event.get("htmlLink"),
                        }
                    )
                    if len(conflicts) >= 25:
                        return conflicts
    return conflicts


def create_event(payload: dict[str, Any], *, confirm_conflicts: bool = False) -> dict[str, Any]:
    normalized = normalize_event_payload(payload)
    calendar_id = payload.get("calendar_id") or default_calendar_id()
    conflicts = preview_conflicts(normalized, calendar_id=calendar_id)
    if conflicts and not confirm_conflicts:
        return {"created": False, "requires_confirmation": True, "conflicts": conflicts, "payload": normalized}

    event = _client().insert_event(calendar_id, _google_event_body(normalized))
    calendar_summary = next(
        (cal["summary"] for cal in list_calendars() if cal["id"] == calendar_id),
        calendar_id,
    )
    store.record_managed_event(
        calendar_id,
        event["id"],
        source_type=normalized["source_type"],
        source_uid=normalized["source_uid"],
    )
    return {"created": True, "event": _normalize_google_event(event, calendar_id, calendar_summary), "conflicts": conflicts}


def update_event(
    calendar_id: str,
    event_id: str,
    payload: dict[str, Any],
    *,
    confirm_conflicts: bool = False,
) -> dict[str, Any]:
    normalized = normalize_event_payload(payload)
    conflicts = preview_conflicts(
        normalized,
        calendar_id=calendar_id,
        ignore_event_id=event_id,
    )
    if conflicts and not confirm_conflicts:
        return {"updated": False, "requires_confirmation": True, "conflicts": conflicts, "payload": normalized}

    event = _client().update_event(calendar_id, event_id, _google_event_body(normalized))
    calendar_summary = next(
        (cal["summary"] for cal in list_calendars() if cal["id"] == calendar_id),
        calendar_id,
    )
    store.record_managed_event(
        calendar_id,
        event["id"],
        source_type=normalized["source_type"],
        source_uid=normalized["source_uid"],
    )
    return {"updated": True, "event": _normalize_google_event(event, calendar_id, calendar_summary), "conflicts": conflicts}


def delete_event(calendar_id: str, event_id: str) -> None:
    _client().delete_event(calendar_id, event_id)
    store.remove_managed_event(calendar_id, event_id)


def preview_ics(file_bytes: bytes, filename: str) -> dict[str, Any]:
    try:
        from icalendar import Calendar
    except ImportError as exc:
        raise SchedulerValidationError(
            "ICS support requires the icalendar package to be installed."
        ) from exc

    calendar_id = default_calendar_id()
    calendar = Calendar.from_ical(file_bytes)
    entries: list[dict[str, Any]] = []
    for component in calendar.walk():
        if component.name != "VEVENT":
            continue
        if str(component.get("STATUS", "")).upper() == "CANCELLED":
            continue
        try:
            payload = _payload_from_ics_component(component)
            conflicts = preview_conflicts(payload, calendar_id=calendar_id)
            duplicate = store.is_imported_uid(calendar_id, payload.get("source_uid"))
            entries.append(
                {
                    "payload": payload,
                    "conflicts": conflicts,
                    "duplicate": duplicate,
                }
            )
        except SchedulerValidationError as exc:
            entries.append(
                {
                    "payload": {
                        "title": str(component.get("SUMMARY") or "(untitled event)"),
                        "source_uid": str(component.get("UID") or _fallback_ics_uid(component)),
                    },
                    "conflicts": [],
                    "duplicate": False,
                    "error": str(exc),
                }
            )

    preview = {"calendar_id": calendar_id, "filename": filename, "entries": entries}
    batch_id = store.create_import_batch(filename, preview)
    preview["batch_id"] = batch_id
    return preview


def import_preview_batch(batch_id: str, *, confirm_conflicts: bool = True) -> dict[str, Any]:
    batch = store.get_import_batch(batch_id)
    if not batch:
        raise SchedulerValidationError("Import batch not found.")

    preview = batch["preview"]
    calendar_id = preview["calendar_id"]
    imported = 0
    for entry in preview.get("entries", []):
        if entry.get("error") or entry.get("duplicate"):
            continue
        payload = entry["payload"]
        if entry.get("conflicts") and not confirm_conflicts:
            raise SchedulerValidationError("Import batch still has unresolved conflicts.")
        result = create_event(payload, confirm_conflicts=confirm_conflicts)
        if result.get("created"):
            imported += 1
            store.record_managed_event(
                calendar_id,
                result["event"]["google_event_id"],
                source_type="ics",
                source_uid=payload.get("source_uid"),
                import_batch_id=batch_id,
            )

    store.update_import_batch(batch_id, status="imported", imported_events=imported)
    return {"batch_id": batch_id, "imported_events": imported, "total_events": batch["total_events"]}


def draft_from_google_event(event: dict[str, Any]) -> dict[str, Any]:
    draft = {
        "calendar_id": event["google_calendar_id"],
        "event_id": event["google_event_id"],
        "title": event["title"],
        "description": event["description"],
        "location": event["location"],
        "all_day": event["all_day"],
        "timezone": event["timezone"],
        "recurrence_kind": event["recurrence_kind"],
        "recurrence_rule": event.get("recurrence_rule"),
    }
    if event["all_day"]:
        draft["start"] = event["start"]
        draft["end"] = event["end"]
    else:
        draft["start"] = event["start"]
        draft["end"] = event["end"]
    return draft


def _payload_from_ics_component(component) -> dict[str, Any]:
    uid = str(component.get("UID") or _fallback_ics_uid(component))
    summary = str(component.get("SUMMARY") or "(untitled event)")
    description = str(component.get("DESCRIPTION") or "")
    location = str(component.get("LOCATION") or "")

    dtstart = component.decoded("DTSTART", None)
    dtend = component.decoded("DTEND", None)
    duration = component.decoded("DURATION", None)
    if dtstart is None:
        raise SchedulerValidationError("ICS event is missing DTSTART.")

    payload: dict[str, Any] = {
        "title": summary,
        "description": description,
        "location": location,
        "source_type": "ics",
        "source_uid": uid,
    }

    if isinstance(dtstart, date) and not isinstance(dtstart, datetime):
        payload["all_day"] = True
        payload["start"] = dtstart.isoformat()
        if dtend and isinstance(dtend, date) and not isinstance(dtend, datetime):
            payload["end"] = (dtend - timedelta(days=1)).isoformat()
        else:
            payload["end"] = dtstart.isoformat()
        payload["timezone"] = DEFAULT_TIMEZONE
    else:
        start_dt = _ensure_datetime(dtstart, DEFAULT_TIMEZONE)
        if dtend:
            end_dt = _ensure_datetime(dtend, DEFAULT_TIMEZONE)
        elif duration:
            end_dt = start_dt + duration
        else:
            end_dt = start_dt + timedelta(hours=1)
        payload["all_day"] = False
        payload["start"] = start_dt.isoformat()
        payload["end"] = end_dt.isoformat()
        payload["timezone"] = str(start_dt.tzinfo or DEFAULT_TIMEZONE)

    rrule = component.get("RRULE")
    if rrule:
        payload["recurrence_kind"] = "custom"
        payload["recurrence_rule"] = _serialize_ical_rrule(rrule)
    else:
        payload["recurrence_kind"] = "once"

    return normalize_event_payload(payload)


def _serialize_ical_rrule(rrule_value: Any) -> str:
    parts = []
    for key, values in dict(rrule_value).items():
        if not isinstance(values, list):
            values = [values]
        rendered = []
        for value in values:
            if isinstance(value, datetime):
                if value.tzinfo is None:
                    rendered.append(value.strftime("%Y%m%dT%H%M%S"))
                else:
                    rendered.append(value.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
            elif isinstance(value, date):
                rendered.append(value.strftime("%Y%m%d"))
            else:
                rendered.append(str(value).upper())
        parts.append(f"{key.upper()}={','.join(rendered)}")
    return "RRULE:" + ";".join(parts)


def _fallback_ics_uid(component) -> str:
    digest = hashlib.sha1(component.to_ical()).hexdigest()
    return f"ppt-{digest}"


def _normalize_google_event(event: dict[str, Any], calendar_id: str, calendar_summary: str) -> dict[str, Any]:
    all_day = _is_all_day_google_event(event)
    start_dt, end_dt = _google_event_bounds(event)
    recurrence_lines = event.get("recurrence") or []
    recurrence_rule = next((line for line in recurrence_lines if line.startswith("RRULE:")), None)
    recurrence_kind = detect_recurrence_kind(recurrence_rule)

    if all_day:
        start_value = event["start"]["date"]
        end_value = (date.fromisoformat(event["end"]["date"]) - timedelta(days=1)).isoformat()
        timezone_name = event.get("start", {}).get("timeZone") or event.get("end", {}).get("timeZone") or DEFAULT_TIMEZONE
    else:
        start_value = start_dt.isoformat() if start_dt else ""
        end_value = end_dt.isoformat() if end_dt else ""
        timezone_name = (
            event.get("start", {}).get("timeZone")
            or event.get("end", {}).get("timeZone")
            or (str(start_dt.tzinfo) if start_dt and start_dt.tzinfo else DEFAULT_TIMEZONE)
        )

    return {
        "google_event_id": event.get("id"),
        "google_calendar_id": calendar_id,
        "google_calendar_summary": calendar_summary,
        "title": event.get("summary") or "(untitled event)",
        "description": event.get("description") or "",
        "location": event.get("location") or "",
        "all_day": all_day,
        "start": start_value,
        "end": end_value,
        "timezone": timezone_name,
        "recurrence_kind": recurrence_kind,
        "recurrence_rule": recurrence_rule,
        "html_link": event.get("htmlLink"),
        "status": event.get("status", "confirmed"),
    }


def detect_recurrence_kind(rrule: str | None) -> str:
    if not rrule:
        return "once"
    normalized = rrule.upper()
    if normalized == "RRULE:FREQ=DAILY":
        return "daily"
    if normalized == "RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR":
        return "weekdays"
    if normalized == "RRULE:FREQ=WEEKLY":
        return "weekly"
    if normalized.startswith("RRULE:FREQ=MONTHLY"):
        return "monthly"
    return "custom"


def _build_basic_daily_event(
    *,
    title: str,
    description: str,
    start_dt: datetime,
    end_dt: datetime,
    recurrence_kind: str,
    slug: str,
) -> dict[str, Any]:
    payload = normalize_event_payload(
        {
            "title": title,
            "description": description,
            "start": start_dt.isoformat(),
            "end": end_dt.isoformat(),
            "timezone": str(start_dt.tzinfo or DEFAULT_TIMEZONE),
            "all_day": False,
            "recurrence_kind": recurrence_kind,
            "source_type": "routine",
            "source_uid": f"{BASIC_DAILY_ROUTINE_KEY}:{slug}",
        }
    )
    payload["template_slug"] = slug
    return payload


def _google_event_body(payload: dict[str, Any]) -> dict[str, Any]:
    body: dict[str, Any] = {
        "summary": payload["title"],
        "description": payload.get("description") or "",
        "location": payload.get("location") or "",
    }
    if payload["all_day"]:
        start_date = date.fromisoformat(payload["start"])
        end_date = date.fromisoformat(payload["end"]) + timedelta(days=1)
        body["start"] = {"date": start_date.isoformat()}
        body["end"] = {"date": end_date.isoformat()}
    else:
        body["start"] = {"dateTime": payload["start"], "timeZone": payload["timezone"]}
        body["end"] = {"dateTime": payload["end"], "timeZone": payload["timezone"]}

    if payload.get("recurrence_rule"):
        body["recurrence"] = [payload["recurrence_rule"]]
    return body


def _payload_bounds(payload: dict[str, Any]) -> tuple[datetime, datetime]:
    if payload["all_day"]:
        zone = ZoneInfo(payload["timezone"])
        start_dt = datetime.combine(date.fromisoformat(payload["start"]), time.min, tzinfo=zone)
        end_dt = datetime.combine(date.fromisoformat(payload["end"]) + timedelta(days=1), time.min, tzinfo=zone)
        return start_dt, end_dt
    return _parse_datetime(payload["start"]), _parse_datetime(payload["end"])


def _payload_start_datetime(payload: dict[str, Any]) -> datetime:
    if _to_bool(payload.get("all_day")):
        return _start_of_day(_parse_date(payload["start"]), payload.get("timezone") or DEFAULT_TIMEZONE)
    start_dt = _parse_datetime(payload["start"])
    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(tzinfo=ZoneInfo(payload.get("timezone") or DEFAULT_TIMEZONE))
    return start_dt


def _expand_occurrences(payload: dict[str, Any], *, horizon_days: int) -> list[tuple[datetime, datetime]]:
    start_dt, end_dt = _payload_bounds(payload)
    duration = end_dt - start_dt
    recurrence_kind = payload.get("recurrence_kind") or "once"
    if recurrence_kind == "once" or not payload.get("recurrence_rule"):
        return [(start_dt, end_dt)]

    horizon_end = start_dt + timedelta(days=horizon_days)
    if recurrence_kind in {"daily", "weekdays", "weekly", "monthly"}:
        return _expand_manual_occurrences(recurrence_kind, start_dt, duration, horizon_end)

    try:
        from dateutil.rrule import rrulestr
    except ImportError as exc:
        raise SchedulerValidationError(
            "Custom recurring schedules require python-dateutil to be installed."
        ) from exc

    rule = payload["recurrence_rule"].replace("RRULE:", "", 1)
    iterator = rrulestr(rule, dtstart=start_dt)
    occurrences = []
    for occurrence_start in iterator.between(start_dt, horizon_end, inc=True):
        occurrences.append((occurrence_start, occurrence_start + duration))
        if len(occurrences) >= 200:
            break
    return occurrences


def _expand_manual_occurrences(
    recurrence_kind: str,
    start_dt: datetime,
    duration: timedelta,
    horizon_end: datetime,
) -> list[tuple[datetime, datetime]]:
    occurrences: list[tuple[datetime, datetime]] = []
    cursor = start_dt
    while cursor <= horizon_end and len(occurrences) < 200:
        if recurrence_kind == "daily":
            occurrences.append((cursor, cursor + duration))
            cursor += timedelta(days=1)
            continue

        if recurrence_kind == "weekdays":
            if cursor.weekday() < 5:
                occurrences.append((cursor, cursor + duration))
            cursor += timedelta(days=1)
            continue

        if recurrence_kind == "weekly":
            occurrences.append((cursor, cursor + duration))
            cursor += timedelta(days=7)
            continue

        if recurrence_kind == "monthly":
            occurrences.append((cursor, cursor + duration))
            year = cursor.year + (1 if cursor.month == 12 else 0)
            month = 1 if cursor.month == 12 else cursor.month + 1
            day = min(cursor.day, monthrange(year, month)[1])
            cursor = cursor.replace(year=year, month=month, day=day)
            continue

    return occurrences


def _google_event_bounds(event: dict[str, Any]) -> tuple[datetime | None, datetime | None]:
    try:
        if _is_all_day_google_event(event):
            zone = ZoneInfo(DEFAULT_TIMEZONE)
            start_dt = datetime.combine(date.fromisoformat(event["start"]["date"]), time.min, tzinfo=zone)
            end_dt = datetime.combine(date.fromisoformat(event["end"]["date"]), time.min, tzinfo=zone)
            return start_dt, end_dt
        return _parse_datetime(event["start"]["dateTime"]), _parse_datetime(event["end"]["dateTime"])
    except (KeyError, ValueError):
        return None, None


def _is_all_day_google_event(event: dict[str, Any]) -> bool:
    return "date" in event.get("start", {})


def _display_datetime(value: datetime, all_day: bool, *, end_value: bool = False) -> str:
    if all_day:
        display = value.date()
        if end_value:
            display = display - timedelta(days=1)
        return display.isoformat()
    return value.isoformat(timespec="minutes")


def _ranges_overlap(start_a: datetime, end_a: datetime, start_b: datetime, end_b: datetime) -> bool:
    return start_a < end_b and start_b < end_a


def _parse_date(value: str) -> date:
    value = value.strip()
    if not value:
        raise SchedulerValidationError("Date value is required.")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise SchedulerValidationError(f"Invalid date: {value}") from exc


def _parse_datetime(value: str) -> datetime:
    value = value.strip()
    if not value:
        raise SchedulerValidationError("Datetime value is required.")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise SchedulerValidationError(f"Invalid datetime: {value}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo(DEFAULT_TIMEZONE))
    return parsed


def _ensure_datetime(value: datetime | date, timezone_name: str) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=ZoneInfo(timezone_name))
        return value
    return _start_of_day(value, timezone_name)


def _parse_clock_time(value: str, label: str) -> time:
    value = value.strip()
    if not value:
        raise SchedulerValidationError(f"{label} is required.")
    try:
        return time.fromisoformat(value)
    except ValueError as exc:
        raise SchedulerValidationError(f"{label} must use HH:MM format.") from exc


def _combine_local_datetime(base_date: date, clock_value: str, timezone_name: str) -> datetime:
    return datetime.combine(
        base_date,
        _parse_clock_time(clock_value, "Time"),
        tzinfo=ZoneInfo(timezone_name),
    )


def _start_of_day(value: date, timezone_name: str) -> datetime:
    return datetime.combine(value, time.min, tzinfo=ZoneInfo(timezone_name))


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).lower() in {"1", "true", "yes", "on"}
