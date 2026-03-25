"""Handle incoming Telegram slash commands and route them to PPT actions."""
import logging
from src.integrations.telegram_bot import send_message, get_updates

log = logging.getLogger(__name__)
_offset = None


def poll_commands() -> list[dict]:
    """Return any new slash commands from Telegram since last check."""
    global _offset
    updates = get_updates(offset=_offset)
    commands = []
    for update in updates:
        _offset = update["update_id"] + 1
        msg = update.get("message", {})
        text = msg.get("text", "").strip()
        chat_id = str(msg.get("chat", {}).get("id", ""))
        if text.startswith("/"):
            commands.append({"command": text, "chat_id": chat_id})
    return commands


def handle_command(command: str, chat_id: str) -> str:
    """Route a slash command and return the reply text."""
    parts = command.strip().lower().split()
    cmd = parts[0]

    handlers = {
        "/start": _cmd_start,
        "/help":  _cmd_help,
        "/status": _cmd_status,
    }

    handler = handlers.get(cmd)
    if handler:
        reply = handler(parts[1:])
    else:
        reply = f"❓ Unknown command: `{cmd}`\nType /help to see available commands."

    send_message(reply, chat_id=chat_id)
    return reply


# ── Command handlers ────────────────────────────────────────────────────────

def _cmd_start(_args) -> str:
    return (
        "👋 *PPT is online!*\n\n"
        "I'm your Personal Project Tracker — voice assistant running on your Mac Mini.\n\n"
        "*Commands:*\n"
        "/status — system status\n"
        "/help — show this message"
    )


def _cmd_help(_args) -> str:
    return (
        "📖 *PPT Commands*\n\n"
        "/start — welcome message\n"
        "/status — system status\n"
        "/help — this message\n\n"
        "_More commands coming in Phase 2 (project tracker integration)_"
    )


def _cmd_status(_args) -> str:
    return (
        "🟢 *PPT Status*\n"
        "• Voice pipeline: running\n"
        "• Ollama LLM: online\n"
        "• TTS: active (macOS say)\n"
        "• Telegram: connected ✅"
    )
