"""High-level project manager — voice-friendly interface over the store."""
from __future__ import annotations
import logging
from src.projects import store
from src.integrations.telegram_bot import notify

log = logging.getLogger(__name__)


def create_project(name: str, goal: str = "") -> str:
    """Create a new project. Returns spoken confirmation."""
    try:
        p = store.add_project(name, goal)
        msg = f"Project '{p['name']}' created."
        if goal:
            msg += f" Goal: {goal}."
        notify("task_done", msg)
        log.info("Created project: %s", p)
        return msg
    except Exception as e:
        log.error("create_project failed: %s", e)
        return f"Sorry, I couldn't create the project. Error: {e}"


def add_task(project_name: str, task_title: str, priority: str = "medium") -> str:
    """Add a task to a project. Returns spoken confirmation."""
    project = store.get_project_by_name(project_name)
    if not project:
        return f"I couldn't find a project called '{project_name}'. Try listing your projects first."
    try:
        task = store.add_task(project["id"], task_title, priority=priority)
        msg = f"Task '{task['title']}' added to {project['name']}."
        notify("task_done", msg)
        return msg
    except Exception as e:
        log.error("add_task failed: %s", e)
        return f"Sorry, I couldn't add the task. Error: {e}"


def complete_task(task_title: str, project_name: str = None) -> str:
    """Mark a task as done. Returns spoken confirmation."""
    project_id = None
    if project_name:
        p = store.get_project_by_name(project_name)
        if p:
            project_id = p["id"]

    task = store.find_task(task_title, project_id=project_id)
    if not task:
        return f"I couldn't find a task matching '{task_title}'."

    store.update_task_status(task["id"], "done")
    msg = f"Task '{task['title']}' marked as done."
    notify("task_done", msg)
    return msg


def list_projects_summary() -> str:
    """Return a spoken summary of all active projects."""
    projects = store.list_projects(status="active")
    if not projects:
        return "You have no active projects. Say 'create project' to start one."

    lines = [f"You have {len(projects)} active project{'s' if len(projects) != 1 else ''}."]
    for p in projects:
        tasks = store.list_tasks(project_id=p["id"])
        todo = sum(1 for t in tasks if t["status"] == "todo")
        done = sum(1 for t in tasks if t["status"] == "done")
        lines.append(f"  {p['name']}: {todo} tasks to do, {done} done.")
    return " ".join(lines)


def list_tasks_summary(project_name: str = None) -> str:
    """Return a spoken summary of tasks, optionally for one project."""
    project_id = None
    label = "all projects"

    if project_name:
        p = store.get_project_by_name(project_name)
        if not p:
            return f"I couldn't find a project called '{project_name}'."
        project_id = p["id"]
        label = p["name"]

    tasks = store.list_tasks(project_id=project_id, status="todo")
    if not tasks:
        return f"No open tasks in {label}."

    lines = [f"{len(tasks)} open task{'s' if len(tasks) != 1 else ''} in {label}:"]
    for t in tasks[:5]:  # speak at most 5
        priority_tag = f" [{t['priority']}]" if t["priority"] != "medium" else ""
        lines.append(f"  {t['title']}{priority_tag}.")
    if len(tasks) > 5:
        lines.append(f"  ...and {len(tasks) - 5} more.")
    return " ".join(lines)


def get_daily_summary() -> str:
    """Build a full daily summary and send it to Telegram."""
    projects = store.list_projects(status="active")
    if not projects:
        summary = "No active projects today."
        notify("daily_summary", summary)
        return summary

    lines = ["📋 *Daily PPT Summary*\n"]
    for p in projects:
        tasks = store.list_tasks(project_id=p["id"])
        todo   = [t for t in tasks if t["status"] == "todo"]
        in_prog = [t for t in tasks if t["status"] == "in_progress"]
        done   = [t for t in tasks if t["status"] == "done"]
        lines.append(f"*{p['name']}*")
        if in_prog:
            lines.append(f"  🔄 In progress: {', '.join(t['title'] for t in in_prog[:3])}")
        if todo:
            lines.append(f"  📌 To do ({len(todo)}): {', '.join(t['title'] for t in todo[:3])}")
        if done:
            lines.append(f"  ✅ Done: {len(done)} tasks")
        lines.append("")

    summary = "\n".join(lines)
    notify("daily_summary", summary)
    return summary
