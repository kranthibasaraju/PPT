"""Handle incoming Telegram slash commands."""
import logging
from src.integrations.telegram_bot import send_message, get_updates

log = logging.getLogger(__name__)
_offset = None

def poll_commands() -> list[dict]:
    global _offset
    updates = get_updates(offset=_offset)
    commands = []
    for update in updates:
        _offset = update["update_id"] + 1
        msg = update.get("message", {})
        text = msg.get("text", "")
        chat_id = str(msg.get("chat", {}).get("id", ""))
        if text.startswith("/"):
            commands.append({"command": text, "chat_id": chat_id})
    return commands

def handle_command(command: str, chat_id: str) -> str:
    cmd = command.strip().lower().split()[0]
    responses = {
        "/start": "👋 *PPT is online!* I'm your Personal Project Tracker.\n\nCommands:\n/status — system status\n/help — show commands",
        "/help": "📖 *PPT Commands*\n\n/status — system status\n/start — initialise\n/help — this message",
        "/status": "🟢 *PPT Status*\n• Voice pipeline: running\n• Ollama LLM: online\n• TTS: active",
    }
    reply = responses.get(cmd, f"❓ Unknown: `{cmd}`\nTry /help")
    send_message(reply, chat_id=chat_id)
    return reply
