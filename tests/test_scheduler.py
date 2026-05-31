"""Tests for the Google-backed PPT scheduler."""
from __future__ import annotations

import io
import sys
import os
from datetime import date

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


class FakeGoogleClient:
    """Simple in-memory Google Calendar stub for scheduler tests."""

    def __init__(self):
        self.connected = True
        self.configured = True
        self.list_events_error = None
        self.calendars = [
            {
                "id": "primary",
                "summary": "Rana Primary",
                "primary": True,
                "selected": True,
                "hidden": False,
                "accessRole": "owner",
            },
            {
                "id": "work",
                "summary": "Work",
                "primary": False,
                "selected": True,
                "hidden": False,
                "accessRole": "writer",
            },
        ]
        self.events = {
            "primary": [],
            "work": [],
        }
        self._counter = 0

    def status(self):
        return {
            "configured": self.configured,
            "connected": self.connected,
            "config_source": "web" if self.configured else "none",
            "redirect_uri": "http://localhost:5001/scheduler/oauth/callback",
            "scopes": [
                "https://www.googleapis.com/auth/calendar.events",
                "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
            ],
            "token_path": "/tmp/token.json",
        }

    def list_calendars(self):
        return list(self.calendars)

    def list_events(self, calendar_id, **_kwargs):
        if self.list_events_error:
            raise RuntimeError(self.list_events_error)
        return list(self.events.get(calendar_id, []))

    def get_event(self, calendar_id, event_id):
        for event in self.events.get(calendar_id, []):
            if event["id"] == event_id:
                return dict(event)
        raise KeyError(event_id)

    def insert_event(self, calendar_id, body):
        self._counter += 1
        event_id = f"evt-{self._counter}"
        event = {"id": event_id, "status": "confirmed", "htmlLink": f"https://example.com/{event_id}", **body}
        self.events.setdefault(calendar_id, []).append(event)
        return dict(event)

    def update_event(self, calendar_id, event_id, body):
        items = self.events.get(calendar_id, [])
        for idx, event in enumerate(items):
            if event["id"] == event_id:
                updated = {"id": event_id, "status": "confirmed", "htmlLink": event.get("htmlLink"), **body}
                items[idx] = updated
                return dict(updated)
        raise KeyError(event_id)

    def delete_event(self, calendar_id, event_id):
        self.events[calendar_id] = [event for event in self.events.get(calendar_id, []) if event["id"] != event_id]

    def authorization_url(self, **_kwargs):
        return "https://accounts.google.com/o/oauth2/auth?fake=1", "state-123"

    def redirect_uri(self, fallback):
        return fallback or "http://localhost:5001/scheduler/oauth/callback"

    def exchange_callback(self, **_kwargs):
        self.connected = True

    def disconnect(self):
        self.connected = False


@pytest.fixture(autouse=True)
def temp_scheduler_db(monkeypatch, tmp_path):
    import src.scheduler.store as scheduler_store

    monkeypatch.setattr(scheduler_store, "_DB_PATH", tmp_path / "scheduler.db")
    monkeypatch.setattr(scheduler_store, "_TOKEN_PATH", tmp_path / "google_token.json")
    for env_name in (
        "GOOGLE_OAUTH_CLIENT_ID",
        "GOOGLE_OAUTH_CLIENT_SECRET",
        "GOOGLE_OAUTH_CLIENT_SECRETS_FILE",
        "GOOGLE_OAUTH_PROJECT_ID",
        "GOOGLE_OAUTH_REDIRECT_URI",
        "GOOGLE_OAUTH_AUTH_URI",
        "GOOGLE_OAUTH_TOKEN_URI",
    ):
        monkeypatch.delenv(env_name, raising=False)
    scheduler_store.init_db()
    yield


@pytest.fixture
def fake_google(monkeypatch):
    import src.scheduler.service as scheduler_service
    import src.web.scheduler_routes as scheduler_routes

    client = FakeGoogleClient()
    monkeypatch.setattr(scheduler_service, "_client", lambda: client)
    monkeypatch.setattr(scheduler_routes, "CalendarApiClient", lambda: client)
    return client


def test_default_calendar_setting_round_trip():
    from src.scheduler import store

    store.set_default_calendar_id("primary")
    assert store.get_default_calendar_id() == "primary"


def test_google_oauth_web_config_round_trip():
    from src.scheduler.service import connection_status, google_oauth_web_config_draft, save_google_oauth_web_config

    before = connection_status()
    assert before["configured"] is False
    assert before["config_source"] == "none"

    saved = save_google_oauth_web_config(
        {
            "client_id": "web-client-id",
            "client_secret": "web-client-secret",
            "project_id": "ppt-web",
        },
        redirect_uri="http://localhost:5001/scheduler/oauth/callback",
    )
    assert saved["config_source"] == "web"

    after = connection_status()
    assert after["configured"] is True
    assert after["connected"] is False
    assert after["config_source"] == "web"

    draft = google_oauth_web_config_draft()
    assert draft["client_id"] == "web-client-id"
    assert draft["client_secret"] == ""
    assert draft["project_id"] == "ppt-web"


def test_basic_daily_profile_persistence():
    from src.scheduler.service import basic_daily_schedule_defaults, get_basic_daily_profile, save_basic_daily_profile

    saved = save_basic_daily_profile(
        {
            "timezone": "America/New_York",
            "wake_time": "06:45",
            "breakfast_time": "07:30",
            "work_notes_time": "08:45",
            "eat_time": "12:30",
            "gaming_off_time": "21:30",
            "sleep_on_time": "22:45",
        }
    )
    assert saved["wake_time"] == "06:45"

    profile = get_basic_daily_profile()
    assert profile["sleep_on_time"] == "22:45"

    defaults = basic_daily_schedule_defaults(start_date="2026-05-18")
    assert defaults["start_date"] == "2026-05-18"
    assert defaults["work_notes_time"] == "08:45"


def test_build_recurrence_rules():
    from src.scheduler.service import build_recurrence_rule

    assert build_recurrence_rule("daily", "2026-05-17T09:00:00-04:00") == "RRULE:FREQ=DAILY"
    assert build_recurrence_rule("weekdays", "2026-05-17T09:00:00-04:00") == "RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR"
    assert build_recurrence_rule("weekly", "2026-05-17T09:00:00-04:00") == "RRULE:FREQ=WEEKLY"
    assert build_recurrence_rule("monthly", "2026-05-17T09:00:00-04:00").startswith("RRULE:FREQ=MONTHLY;BYMONTHDAY=17")


def test_build_basic_daily_schedule():
    from src.scheduler.service import build_basic_daily_schedule

    events = build_basic_daily_schedule(
        {
            "start_date": "2026-05-17",
            "timezone": "America/New_York",
            "wake_time": "07:30",
            "breakfast_time": "08:30",
            "work_notes_time": "09:00",
            "eat_time": "13:00",
            "gaming_off_time": "22:00",
            "sleep_on_time": "23:00",
        }
    )

    assert [event["title"] for event in events] == [
        "Sleep off",
        "Wake up",
        "Get ready",
        "Breakfast ready",
        "Work notes ready",
        "Eat something",
        "Gaming session off",
        "Sleep on",
    ]
    assert events[4]["recurrence_kind"] == "weekdays"
    assert events[-1]["end"].startswith("2026-05-18T07:30:00")


def test_normalize_all_day_payload_single_day():
    from src.scheduler.service import normalize_event_payload

    payload = normalize_event_payload(
        {
            "title": "Day off",
            "all_day": True,
            "start": "2026-05-20",
            "end": "2026-05-20",
        }
    )
    assert payload["start"] == "2026-05-20"
    assert payload["end"] == "2026-05-20"
    assert payload["all_day"] is True


def test_preview_conflicts_detects_overlap(fake_google):
    from src.scheduler import store
    from src.scheduler.service import preview_conflicts

    store.set_default_calendar_id("primary")
    fake_google.events["work"].append(
        {
            "id": "busy-1",
            "summary": "Team Sync",
            "start": {"dateTime": "2026-05-20T10:00:00-04:00"},
            "end": {"dateTime": "2026-05-20T11:00:00-04:00"},
        }
    )
    conflicts = preview_conflicts(
        {
            "title": "Editor Session",
            "start": "2026-05-20T10:30:00-04:00",
            "end": "2026-05-20T11:30:00-04:00",
            "timezone": "America/New_York",
            "recurrence_kind": "once",
        }
    )
    assert len(conflicts) == 1
    assert conflicts[0]["summary"] == "Team Sync"


def test_create_event_requires_confirmation_on_conflict(fake_google):
    from src.scheduler import store
    from src.scheduler.service import create_event

    store.set_default_calendar_id("primary")
    fake_google.events["work"].append(
        {
            "id": "busy-2",
            "summary": "Focus Block",
            "start": {"dateTime": "2026-05-21T09:00:00-04:00"},
            "end": {"dateTime": "2026-05-21T10:00:00-04:00"},
        }
    )
    payload = {
        "title": "Import Review",
        "start": "2026-05-21T09:30:00-04:00",
        "end": "2026-05-21T10:30:00-04:00",
        "timezone": "America/New_York",
        "recurrence_kind": "once",
    }
    first = create_event(payload, confirm_conflicts=False)
    assert first["created"] is False
    assert first["requires_confirmation"] is True

    second = create_event(payload, confirm_conflicts=True)
    assert second["created"] is True
    assert second["event"]["title"] == "Import Review"


def test_apply_basic_daily_schedule_upserts_existing_events(fake_google):
    from src.scheduler import store
    from src.scheduler.service import apply_basic_daily_schedule

    store.set_default_calendar_id("primary")
    first = apply_basic_daily_schedule(
        {
            "start_date": "2026-05-20",
            "wake_time": "07:30",
            "breakfast_time": "08:30",
            "work_notes_time": "09:00",
            "eat_time": "13:00",
            "gaming_off_time": "22:00",
            "sleep_on_time": "23:00",
            "timezone": "America/New_York",
        }
    )
    assert first["applied"] is True
    assert first["created_count"] == 8
    assert first["updated_count"] == 0
    assert len(fake_google.events["primary"]) == 8
    first_ids = {event["google_event_id"] for event in first["events"]}

    second = apply_basic_daily_schedule(
        {
            "start_date": "2026-05-20",
            "wake_time": "08:00",
            "breakfast_time": "08:45",
            "work_notes_time": "09:15",
            "eat_time": "13:15",
            "gaming_off_time": "22:15",
            "sleep_on_time": "23:30",
            "timezone": "America/New_York",
        }
    )
    assert second["applied"] is True
    assert second["created_count"] == 0
    assert second["updated_count"] == 8
    assert len(fake_google.events["primary"]) == 8
    assert {event["google_event_id"] for event in second["events"]} == first_ids
    assert fake_google.events["primary"][0]["start"]["dateTime"].startswith("2026-05-20T08:00:00")


def test_connection_status_setup_progression(fake_google):
    from src.scheduler import store
    from src.scheduler.service import apply_basic_daily_schedule, connection_status, save_basic_daily_profile

    def items_for(status):
        return {item["key"]: item for item in status["setup_status"]["steps"]}

    fake_google.events["primary"].append(
        {
            "id": "existing-1",
            "summary": "Existing Event",
            "start": {"dateTime": "2026-05-18T10:00:00-04:00"},
            "end": {"dateTime": "2026-05-18T11:00:00-04:00"},
        }
    )

    initial = connection_status()
    initial_items = items_for(initial)
    assert initial["setup_status"]["complete_count"] == 2
    assert initial_items["default_calendar_selected"]["state"] == "pending"
    assert initial_items["current_events_readable"]["state"] == "blocked"

    store.set_default_calendar_id("primary")
    after_calendar = connection_status()
    after_calendar_items = items_for(after_calendar)
    assert after_calendar_items["default_calendar_selected"]["state"] == "done"
    assert after_calendar_items["current_events_readable"]["state"] == "done"
    assert after_calendar["agenda_preview"]["event_count"] == 1
    assert after_calendar_items["daily_schedule_inputs_saved"]["state"] == "pending"

    save_basic_daily_profile(
        {
            "timezone": "America/New_York",
            "wake_time": "07:00",
            "breakfast_time": "08:00",
            "work_notes_time": "09:00",
            "eat_time": "13:00",
            "gaming_off_time": "22:00",
            "sleep_on_time": "23:00",
        }
    )
    after_profile = connection_status()
    after_profile_items = items_for(after_profile)
    assert after_profile_items["daily_schedule_inputs_saved"]["state"] == "done"
    assert after_profile_items["starter_routine_scheduled"]["state"] == "pending"

    apply_basic_daily_schedule(
        {
            "start_date": "2026-05-18",
            "timezone": "America/New_York",
            "wake_time": "07:00",
            "breakfast_time": "08:00",
            "work_notes_time": "09:00",
            "eat_time": "13:00",
            "gaming_off_time": "22:00",
            "sleep_on_time": "23:00",
        },
        confirm_conflicts=True,
    )
    complete = connection_status()
    complete_items = items_for(complete)
    assert complete["setup_status"]["all_complete"] is True
    assert complete_items["starter_routine_scheduled"]["state"] == "done"


def test_connection_status_handles_event_access_error(fake_google):
    from src.scheduler import store
    from src.scheduler.service import connection_status

    store.set_default_calendar_id("primary")
    fake_google.list_events_error = "Calendar read failed"

    status = connection_status()
    items = {item["key"]: item for item in status["setup_status"]["steps"]}
    assert status["agenda_preview"]["state"] == "error"
    assert items["current_events_readable"]["state"] == "pending"
    assert "Calendar read failed" in items["current_events_readable"]["detail"]


def test_ics_preview_marks_duplicates(fake_google):
    from src.scheduler import store
    from src.scheduler.service import preview_ics

    try:
        import icalendar  # noqa: F401
    except ImportError:
        pytest.skip("icalendar not installed")

    store.set_default_calendar_id("primary")
    store.record_managed_event("primary", "gcal-1", source_type="ics", source_uid="uid-123")

    ics_text = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:uid-123
DTSTART:20260522T130000Z
DTEND:20260522T140000Z
SUMMARY:Duplicate Event
END:VEVENT
END:VCALENDAR
"""
    preview = preview_ics(ics_text.encode("utf-8"), "duplicate.ics")
    assert preview["entries"][0]["duplicate"] is True


def test_scheduler_page_loads(fake_google):
    from src.scheduler import store
    from src.web.app import app

    store.set_default_calendar_id("primary")
    client = app.test_client()
    response = client.get("/scheduler")
    assert response.status_code == 200
    assert b"PPT Board" in response.data
    assert b"Scheduler" in response.data
    assert b"Setup / To Do" in response.data
    assert b"Basic Daily Rhythm" in response.data


def test_scheduler_page_shows_web_oauth_setup_when_unconfigured():
    from src.web.app import app

    client = app.test_client()
    response = client.get("/scheduler")
    assert response.status_code == 200
    assert b"Save Google Web Config" in response.data
    assert b"Connect Google Calendar" not in response.data


def test_scheduler_web_oauth_config_route():
    from src.web.app import app

    client = app.test_client()
    response = client.post(
        "/scheduler/oauth/configure",
        data={
            "client_id": "browser-client-id",
            "client_secret": "browser-client-secret",
            "project_id": "ppt-browser",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Google OAuth app credentials saved" in response.data
    assert b"Connect Google Calendar" in response.data

    status = client.get("/scheduler/api/status").get_json()["status"]
    assert status["configured"] is True
    assert status["config_source"] == "web"


def test_scheduler_api_status_includes_setup_and_preview(fake_google):
    from src.scheduler import store
    from src.web.app import app

    store.set_default_calendar_id("primary")
    fake_google.events["primary"].append(
        {
            "id": "agenda-1",
            "summary": "Agenda Preview",
            "start": {"dateTime": "2026-05-23T09:00:00-04:00"},
            "end": {"dateTime": "2026-05-23T10:00:00-04:00"},
        }
    )

    client = app.test_client()
    response = client.get("/scheduler/api/status")
    assert response.status_code == 200
    status = response.get_json()["status"]
    assert "setup_status" in status
    assert "agenda_preview" in status
    assert "basic_daily_profile" in status
    assert "next_actions" in status
    assert "auth_integration" in status
    assert status["auth_integration"]["connect_path"] == "/scheduler/connect"
    assert status["agenda_preview"]["state"] == "ready"
    assert len(status["agenda_preview"]["events"]) == 1


def test_scheduler_api_integration_contract(fake_google):
    from src.scheduler import store
    from src.web.app import app

    store.set_default_calendar_id("primary")
    client = app.test_client()

    response = client.get("/scheduler/api/integration")
    assert response.status_code == 200
    integration = response.get_json()["integration"]
    assert integration["id"] == "ppt-scheduler"
    assert integration["auth"]["provider"] == "google-calendar"
    assert integration["auth"]["browser_session_reuse_supported"] is True
    assert integration["auth"]["connect_path"] == "/scheduler/connect"
    assert integration["calendar_access"]["status_api_path"] == "/scheduler/api/status"


def test_scheduler_api_save_google_oauth_config():
    from src.web.app import app

    client = app.test_client()
    response = client.post(
        "/scheduler/api/oauth/configure",
        json={
            "client_id": "api-client-id",
            "client_secret": "api-client-secret",
            "project_id": "ppt-api",
        },
    )
    assert response.status_code == 200
    assert response.get_json()["config_source"] == "web"

    status = client.get("/scheduler/api/status").get_json()["status"]
    assert status["configured"] is True
    assert status["config_source"] == "web"


def test_scheduler_api_save_basic_daily_profile(fake_google):
    from src.scheduler import store
    from src.web.app import app

    store.set_default_calendar_id("primary")
    client = app.test_client()

    response = client.post(
        "/scheduler/api/profile/basic-daily",
        json={
            "timezone": "America/New_York",
            "wake_time": "06:30",
            "breakfast_time": "07:15",
            "work_notes_time": "08:45",
            "eat_time": "12:15",
            "gaming_off_time": "21:45",
            "sleep_on_time": "22:30",
        },
    )
    assert response.status_code == 200
    assert response.get_json()["profile"]["wake_time"] == "06:30"

    status = client.get("/scheduler/api/status").get_json()["status"]
    items = {item["key"]: item for item in status["setup_status"]["steps"]}
    assert status["basic_daily_profile"]["sleep_on_time"] == "22:30"
    assert items["daily_schedule_inputs_saved"]["state"] == "done"


def test_scheduler_api_full_crud(fake_google):
    from src.scheduler import store
    from src.web.app import app

    store.set_default_calendar_id("primary")
    client = app.test_client()

    create = client.post(
        "/scheduler/api/events",
        json={
            "title": "Write runbook",
            "start": "2026-05-23T13:00:00-04:00",
            "end": "2026-05-23T14:00:00-04:00",
            "timezone": "America/New_York",
            "recurrence_kind": "weekly",
        },
    )
    assert create.status_code == 200
    create_data = create.get_json()
    assert create_data["created"] is True
    event_id = create_data["event"]["google_event_id"]

    update = client.patch(
        f"/scheduler/api/events/{event_id}",
        json={
            "calendar_id": "primary",
            "title": "Write scheduler runbook",
            "start": "2026-05-23T15:00:00-04:00",
            "end": "2026-05-23T16:00:00-04:00",
            "timezone": "America/New_York",
            "recurrence_kind": "once",
        },
    )
    assert update.status_code == 200
    assert update.get_json()["updated"] is True

    listing = client.get(
        "/scheduler/api/events",
        query_string={"start": "2026-05-23", "end": "2026-05-24"},
    )
    assert listing.status_code == 200
    assert len(listing.get_json()["events"]) == 1

    delete = client.delete(
        f"/scheduler/api/events/{event_id}",
        json={"calendar_id": "primary"},
    )
    assert delete.status_code == 200
    assert delete.get_json()["ok"] is True


def test_scheduler_import_endpoints(fake_google, monkeypatch):
    from src.web.app import app

    preview_payload = {
        "batch_id": "batch-1",
        "entries": [
            {
                "payload": {
                    "title": "Imported Session",
                    "start": "2026-05-24T10:00:00-04:00",
                    "end": "2026-05-24T11:00:00-04:00",
                    "all_day": False,
                },
                "conflicts": [],
                "duplicate": False,
            }
        ],
    }
    monkeypatch.setattr("src.web.scheduler_routes.scheduler_service.preview_ics", lambda _bytes, _name: preview_payload)
    monkeypatch.setattr(
        "src.web.scheduler_routes.scheduler_service.import_preview_batch",
        lambda batch_id, confirm_conflicts=True: {"batch_id": batch_id, "imported_events": 1, "total_events": 1},
    )

    client = app.test_client()
    response = client.post(
        "/scheduler/api/imports/preview",
        data={"ics_file": (io.BytesIO(b"BEGIN:VCALENDAR\nEND:VCALENDAR"), "test.ics")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    assert response.get_json()["preview"]["batch_id"] == "batch-1"

    commit = client.post("/scheduler/api/imports/batch-1/commit")
    assert commit.status_code == 200
    assert commit.get_json()["imported_events"] == 1


def test_scheduler_api_basic_daily_template(fake_google):
    from src.scheduler import store
    from src.web.app import app

    store.set_default_calendar_id("primary")
    client = app.test_client()

    preview = client.post(
        "/scheduler/api/templates/basic-daily/preview",
        json={
            "start_date": "2026-05-24",
            "wake_time": "07:15",
            "breakfast_time": "08:15",
            "work_notes_time": "09:00",
            "eat_time": "13:00",
            "gaming_off_time": "22:00",
            "sleep_on_time": "23:00",
            "timezone": "America/New_York",
        },
    )
    assert preview.status_code == 200
    assert len(preview.get_json()["preview"]["events"]) == 8

    apply = client.post(
        "/scheduler/api/templates/basic-daily",
        json={
            "start_date": "2026-05-24",
            "wake_time": "07:15",
            "breakfast_time": "08:15",
            "work_notes_time": "09:00",
            "eat_time": "13:00",
            "gaming_off_time": "22:00",
            "sleep_on_time": "23:00",
            "timezone": "America/New_York",
        },
    )
    assert apply.status_code == 200
    apply_data = apply.get_json()
    assert apply_data["applied"] is True
    assert apply_data["created_count"] == 8

    reapply = client.post(
        "/scheduler/api/templates/basic-daily",
        json={
            "start_date": "2026-05-24",
            "wake_time": "07:45",
            "breakfast_time": "08:45",
            "work_notes_time": "09:15",
            "eat_time": "13:15",
            "gaming_off_time": "22:15",
            "sleep_on_time": "23:15",
            "timezone": "America/New_York",
        },
    )
    assert reapply.status_code == 200
    assert reapply.get_json()["updated_count"] == 8
