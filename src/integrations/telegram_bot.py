"""Telegram bot integration for PPT notifications and commands."""
import logging
import requests
from config.settings import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

log = logging.getLogger(__name__)
BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

def send_message(text: str, chat_id: str = None) -> bool:
    cid = chat_id or TELEGRAM_CHAT_ID
    if not cid:
        log.warning("No TELEGRAM_CHAT_ID set.")
        return False
    try:
        r = requests.post(f"{BASE_URL}/sendMessage",
            json={"chat_id": cid, "text": text, "parse_mode": "Markdown"}, timeout=10)
        r.raise_for_status()
        return True
    except Exception as e:
        log.error("Telegram send failed: %s", e)
        return False

def notify(event: str, detail: str = "") -> bool:
    icons = {"task_done":"✅","error":"❌","daily_summary":"📋","reminder":"⏰","info":"ℹ️","listening":"🎙️","response":"🤖"}
    icon = icons.get(event, "📢")
    msg = f"{icon} *PPT* — {event.replace('_',' ').title()}"
    if detail:
        msg += f"\n{detail}"
    return send_message(msg)

def get_updates(offset: int = None) -> list:
    params = {"timeout": 5}
    if offset:
        params["offset"] = offset
    try:
        r = requests.get(f"{BASE_URL}/getUpdates", params=params, timeout=10)
        r.raise_for_status()
        return r.json().get("result", [])
    except Exception as e:
        log.error("getUpdates failed: %s", e)
        return []

def get_my_chat_id() -> "str | None":
    for update in reversed(get_updates()):
        msg = update.get("message") or update.get("channel_post")
        if msg:
            return str(msg["chat"]["id"])
    return None

def verify_connection() -> bool:
    try:
        r = requests.get(f"{BASE_URL}/getMe", timeout=5)
        data = r.json()
        if data.get("ok"):
            bot = data["result"]
            log.info("Telegram bot: @%s", bot["username"])
            print(f"Bot connected: @{bot['username']} ({bot['first_name']})")
            return True
        return False
    except Exception as e:
        log.error("Telegram check failed: %s", e)
        return False
