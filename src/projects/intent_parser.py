"""Parse natural language transcriptions into project management intents.

Uses the LLM to classify and extract structured commands from speech.
"""
from __future__ import annotations
import json
import logging
import re
from src.llm.ollama_client import complete

log = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a project management intent parser for PPT (Personal Project Tracker).

Given a user's spoken command, extract the intent and entities as JSON.

Valid intents:
- create_project   → needs: name (required), goal (optional)
- add_task         → needs: project_name (required), task_title (required), priority (optional: low/medium/high)
- complete_task    → needs: task_title (required), project_name (optional)
- list_projects    → no entities needed
- list_tasks       → needs: project_name (optional)
- daily_summary    → no entities needed
- unknown          → when the command is not project-related

Respond with ONLY valid JSON. Example:
{"intent": "add_task", "project_name": "PPT", "task_title": "write tests", "priority": "high"}
{"intent": "create_project", "name": "Website Redesign", "goal": "launch by April"}
{"intent": "complete_task", "task_title": "write tests"}
{"intent": "list_projects"}
{"intent": "unknown"}
"""


def parse_intent(text: str) -> dict:
    """Parse a spoken command into a structured intent dict."""
    if not text.strip():
        return {"intent": "unknown"}

    prompt = f"{_SYSTEM_PROMPT}\n\nUser said: \"{text.strip()}\"\n\nJSON:"
    try:
        raw = complete(prompt, temperature=0.1)
        # Extract JSON from response (LLM might add extra text)
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            return json.loads(match.group())
        log.warning("No JSON found in LLM response: %s", raw)
        return {"intent": "unknown"}
    except json.JSONDecodeError as e:
        log.error("JSON parse failed: %s — raw: %s", e, raw[:200])
        return {"intent": "unknown"}
    except Exception as e:
        log.error("Intent parsing failed: %s", e)
        return {"intent": "unknown"}


def dispatch(intent: dict) -> str | None:
    """Execute the parsed intent. Returns spoken response or None if not a project command."""
    from src.projects import manager

    i = intent.get("intent", "unknown")

    if i == "create_project":
        return manager.create_project(
            name=intent.get("name", "Untitled"),
            goal=intent.get("goal", ""),
        )
    elif i == "add_task":
        return manager.add_task(
            project_name=intent.get("project_name", ""),
            task_title=intent.get("task_title", ""),
            priority=intent.get("priority", "medium"),
        )
    elif i == "complete_task":
        return manager.complete_task(
            task_title=intent.get("task_title", ""),
            project_name=intent.get("project_name"),
        )
    elif i == "list_projects":
        return manager.list_projects_summary()
    elif i == "list_tasks":
        return manager.list_tasks_summary(project_name=intent.get("project_name"))
    elif i == "daily_summary":
        return manager.get_daily_summary()
    else:
        return None  # Not a project command — let normal LLM handle it
