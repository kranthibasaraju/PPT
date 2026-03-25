"""Parse natural language transcriptions into project management intents.

Uses fast keyword/regex matching first; falls back to LLM for ambiguous input.
"""
from __future__ import annotations
import json
import logging
import re

log = logging.getLogger(__name__)

# ── Fast keyword/regex patterns (checked in order) ────────────────────────────
_PATTERNS: list[tuple[str, str]] = [
    (r'\b(create|new|start)\b.{0,10}\bproject\b.{0,5}\b(?:called|named|for)?\s+(.+)', 'create_project'),
    (r'\badd\s+task\s+(.+?)\s+to\s+(.+)', 'add_task'),
    (r'\b(?:complete|finish|mark)\s+(.+?)\s+(?:as\s+)?(?:done|complete|finished)\b', 'complete_task'),
    (r'\b(list|show|what are my|view)\b.{0,10}\bprojects?\b', 'list_projects'),
    (r'\b(list|show|view)\b.{0,10}\b(tasks?|todos?|to.dos?)\b', 'list_tasks'),
    (r'\b(daily\s+summary|what.s on my plate|summary|standup)\b', 'daily_summary'),
]


def _keyword_parse(text: str) -> dict | None:
    """Try to match text against known command patterns. Returns intent dict or None."""
    t = text.lower().strip()

    for pattern, intent in _PATTERNS:
        m = re.search(pattern, t, re.IGNORECASE)
        if not m:
            continue

        if intent == 'create_project':
            name = m.group(2).strip().rstrip('.!?')
            return {"intent": "create_project", "name": name}

        if intent == 'add_task':
            task = m.group(1).strip().rstrip('.!?')
            project = m.group(2).strip().rstrip('.!?')
            return {"intent": "add_task", "task_title": task, "project_name": project}

        if intent == 'complete_task':
            task = m.group(1).strip().rstrip('.!?')
            return {"intent": "complete_task", "task_title": task}

        if intent == 'list_projects':
            return {"intent": "list_projects"}

        if intent == 'list_tasks':
            return {"intent": "list_tasks"}

        if intent == 'daily_summary':
            return {"intent": "daily_summary"}

    return None


_LLM_SYSTEM = (
    "Extract a project management intent from the user's spoken command. "
    "Reply with ONLY a JSON object — no other text. "
    "Valid intents: create_project (needs name), add_task (needs project_name, task_title), "
    "complete_task (needs task_title), list_projects, list_tasks, daily_summary, unknown. "
    'Example: {"intent": "add_task", "project_name": "PPT", "task_title": "write tests"}'
)


def _llm_parse(text: str) -> dict:
    """Fall back to LLM for ambiguous input."""
    from src.llm.ollama_client import complete
    prompt = f"{_LLM_SYSTEM}\n\nCommand: \"{text.strip()}\"\nJSON:"
    try:
        raw = complete(prompt)
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            return json.loads(match.group())
        log.warning("No JSON in LLM response: %s", raw[:200])
    except json.JSONDecodeError as e:
        log.error("JSON parse failed: %s", e)
    except Exception as e:
        log.error("LLM intent parse failed: %s", e)
    return {"intent": "unknown"}


def parse_intent(text: str) -> dict:
    """Parse a spoken command into a structured intent dict."""
    if not text.strip():
        return {"intent": "unknown"}

    result = _keyword_parse(text)
    if result is not None:
        log.debug("Keyword match: %s", result)
        return result

    log.debug("No keyword match, falling back to LLM")
    return _llm_parse(text)


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
