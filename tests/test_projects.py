"""Tests for the project planner store and manager."""
from __future__ import annotations
import pytest
import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def temp_db(monkeypatch, tmp_path):
    """Redirect the DB to a temp file so tests don't touch the real data."""
    db_path = tmp_path / "test_projects.db"
    import src.projects.store as store
    monkeypatch.setattr(store, "_DB_PATH", db_path)
    store.init_db()
    yield
    # cleanup handled by tmp_path


# ── Store tests ───────────────────────────────────────────────────────────────

def test_add_and_get_project():
    from src.projects.store import add_project, get_project
    p = add_project("PPT Dev", "Build the voice assistant")
    assert p["name"] == "PPT Dev"
    assert p["goal"] == "Build the voice assistant"
    assert p["status"] == "active"
    fetched = get_project(p["id"])
    assert fetched["name"] == "PPT Dev"


def test_list_projects_empty():
    from src.projects.store import list_projects
    assert list_projects() == []


def test_list_projects_returns_active():
    from src.projects.store import add_project, list_projects, update_project_status
    add_project("Active Project")
    p2 = add_project("Done Project")
    update_project_status(p2["id"], "done")
    active = list_projects(status="active")
    assert len(active) == 1
    assert active[0]["name"] == "Active Project"


def test_add_and_list_tasks():
    from src.projects.store import add_project, add_task, list_tasks
    p = add_project("Test Project")
    add_task(p["id"], "Write unit tests", priority="high")
    add_task(p["id"], "Review PR", priority="low")
    tasks = list_tasks(project_id=p["id"])
    assert len(tasks) == 2
    titles = [t["title"] for t in tasks]
    assert "Write unit tests" in titles


def test_complete_task():
    from src.projects.store import add_project, add_task, update_task_status, get_task
    p = add_project("Test Project")
    t = add_task(p["id"], "Deploy app")
    assert t["status"] == "todo"
    updated = update_task_status(t["id"], "done")
    assert updated["status"] == "done"


def test_find_task_by_fragment():
    from src.projects.store import add_project, add_task, find_task
    p = add_project("My Project")
    add_task(p["id"], "Implement login feature")
    found = find_task("login")
    assert found is not None
    assert "login" in found["title"].lower()


def test_get_project_by_name_partial():
    from src.projects.store import add_project, get_project_by_name
    add_project("Website Redesign")
    found = get_project_by_name("Website")
    assert found is not None
    assert "Website" in found["name"]


# ── Manager tests ─────────────────────────────────────────────────────────────

def test_manager_create_project():
    from unittest.mock import patch
    with patch("src.integrations.telegram_bot.send_message", return_value=True):
        from src.projects.manager import create_project
        result = create_project("New Feature", "ship it fast")
        assert "New Feature" in result


def test_manager_add_task():
    from unittest.mock import patch
    with patch("src.integrations.telegram_bot.send_message", return_value=True):
        from src.projects.manager import create_project, add_task
        create_project("Backend API")
        result = add_task("Backend API", "Set up endpoints")
        assert "Set up endpoints" in result


def test_manager_add_task_unknown_project():
    from src.projects.manager import add_task
    result = add_task("NonExistentProject", "some task")
    assert "couldn't find" in result.lower()


def test_manager_complete_task():
    from unittest.mock import patch
    with patch("src.integrations.telegram_bot.send_message", return_value=True):
        from src.projects.manager import create_project, add_task, complete_task
        create_project("Alpha")
        add_task("Alpha", "Write docs")
        result = complete_task("Write docs")
        assert "done" in result.lower()


def test_manager_list_projects_empty():
    from src.projects.manager import list_projects_summary
    result = list_projects_summary()
    assert "no active projects" in result.lower()


def test_manager_list_projects_with_data():
    from unittest.mock import patch
    with patch("src.integrations.telegram_bot.send_message", return_value=True):
        from src.projects.manager import create_project, list_projects_summary
        create_project("Project Alpha")
        create_project("Project Beta")
        result = list_projects_summary()
        assert "2 active projects" in result or "Project Alpha" in result


def test_manager_daily_summary():
    from unittest.mock import patch
    with patch("src.integrations.telegram_bot.send_message", return_value=True):
        from src.projects.manager import create_project, add_task, get_daily_summary
        create_project("Daily Project")
        add_task("Daily Project", "Morning standup")
        result = get_daily_summary()
        assert "Daily Project" in result or "summary" in result.lower()
