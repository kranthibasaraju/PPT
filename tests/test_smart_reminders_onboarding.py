from __future__ import annotations

import importlib
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


@pytest.fixture
def temp_stores(monkeypatch, tmp_path):
    import src.notify.store as notify_store
    import src.projects.store as projects_store
    import src.scheduler.store as scheduler_store

    monkeypatch.setattr(notify_store, "_DB_PATH", tmp_path / "notify.db")
    monkeypatch.setattr(projects_store, "_DB_PATH", tmp_path / "projects.db")
    monkeypatch.setattr(scheduler_store, "_DB_PATH", tmp_path / "scheduler.db")
    monkeypatch.setattr(scheduler_store, "_TOKEN_PATH", tmp_path / "google_token.json")

    notify_store.init_db()
    projects_store.init_db()
    scheduler_store.init_db()

    return notify_store, projects_store, scheduler_store


@pytest.fixture
def app_client(temp_stores):
    import src.web.app as app_module

    importlib.reload(app_module)
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def _accept_user(store, email: str, *, sub: str, name: str):
    invite = store.create_invite(email)
    user = store.accept_invite(invite["token"], google_sub=sub, email=email, display_name=name)
    store.save_user_google_account(
        user["id"],
        google_sub=sub,
        email=email,
        token_json='{"access_token":"fake"}',
        scopes=["openid", "email", "profile", "calendar.readonly"],
    )
    return invite, user


def test_accept_invite_requires_matching_email(temp_stores):
    store, _, _ = temp_stores
    invite = store.create_invite("person@example.com")

    with pytest.raises(ValueError, match="invited email"):
        store.accept_invite(
            invite["token"],
            google_sub="google-sub-1",
            email="other@example.com",
            display_name="Other Person",
        )


def test_notify_data_is_scoped_per_user(temp_stores):
    store, _, _ = temp_stores
    _, user = _accept_user(store, "person@example.com", sub="sub-1", name="Person One")

    legacy_habit = store.add_habit("Legacy habit", user_id=store.default_user_id())
    user_habit = store.add_habit("User habit", user_id=user["id"])
    legacy_reminder = store.add_reminder("Legacy reminder", remind_at="08:00", repeat="daily", user_id=store.default_user_id())
    user_reminder = store.add_reminder("User reminder", remind_at="09:00", repeat="daily", user_id=user["id"])

    assert [habit["id"] for habit in store.list_habits(user_id=store.default_user_id())] == [legacy_habit["id"]]
    assert [habit["id"] for habit in store.list_habits(user_id=user["id"])] == [user_habit["id"]]
    assert [reminder["id"] for reminder in store.list_reminders(user_id=store.default_user_id())] == [legacy_reminder["id"]]
    assert [reminder["id"] for reminder in store.list_reminders(user_id=user["id"])] == [user_reminder["id"]]


def test_telegram_link_tokens_are_per_user(temp_stores):
    store, _, _ = temp_stores
    _, user_one = _accept_user(store, "one@example.com", sub="sub-one", name="One")
    _, user_two = _accept_user(store, "two@example.com", sub="sub-two", name="Two")

    link_one = store.ensure_telegram_link_token(user_one["id"])
    store.link_telegram_account(link_one["link_token"], chat_id="1001", telegram_user_id="u1001", telegram_username="one")

    link_two = store.ensure_telegram_link_token(user_two["id"])
    with pytest.raises(ValueError, match="already linked"):
        store.link_telegram_account(link_two["link_token"], chat_id="1001", telegram_user_id="u1002", telegram_username="two")


def test_onboarding_profile_route_finishes_setup(app_client, temp_stores):
    store, _, _ = temp_stores
    invite, user = _accept_user(store, "smart@example.com", sub="sub-smart", name="Smart User")
    link = store.ensure_telegram_link_token(user["id"])
    store.link_telegram_account(link["link_token"], chat_id="2002", telegram_user_id="2002", telegram_username="smartuser")

    response = app_client.post(
        f"/notify/onboarding/{invite['token']}/profile",
        data={
            "display_name": "Smart User",
            "timezone": "America/New_York",
            "quiet_hours_start": "22:30",
            "quiet_hours_end": "06:45",
            "first_item_kind": "reminder",
            "first_item_time": "09:15",
            "first_item_title": "Review my day",
            "first_item_description": "Daily smart reminder",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert store.get_invite(invite["token"])["status"] == "completed"
    profile = store.get_profile(user["id"])
    reminders = store.list_reminders(user_id=user["id"])

    assert profile["timezone"] == "America/New_York"
    assert profile["quiet_hours_start"] == "22:30"
    assert profile["quiet_hours_end"] == "06:45"
    assert any(reminder["title"] == "Review my day" for reminder in reminders)


def test_planner_index_renders_task_notes(app_client, temp_stores):
    _, projects_store, _ = temp_stores
    project = projects_store.add_project("PPT Smart Reminders")
    projects_store.add_task(
        project["id"],
        "SR-0 Board Story Notes Support",
        priority="high",
        notes="Store task descriptions in tasks.notes and show them in the planner card.",
    )

    response = app_client.get("/")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "PPT Board" in page
    assert "Planner" in page
    assert "Story details" in page
    assert "tasks.notes" in page
