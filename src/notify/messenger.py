"""
src/notify/messenger.py — multi-channel message delivery for ppt-notify.

WHY multi-channel?
  You want to be notified on your phone, your watch, and your physical device.
  - Phone + Watch  → Telegram (single message hits both if Telegram is installed)
  - Physical device → Piper TTS speaks the message through the RPi4's speaker
  - Web (in-browser) → returned as a string for the Flask UI to display

Channels are tried independently — if Telegram fails, TTS still fires (and vice versa).

USAGE:
    from src.notify.messenger import send
    send("Time to drink water!", channels=["telegram", "tts"])
"""
from __future__ import annotations
import logging
import subprocess
import sys
from pathlib import Path

log = logging.getLogger(__name__)


# ── Telegram channel ──────────────────────────────────────────────────────────

def send_telegram_result(
    text: str,
    *,
    user_id: int | None = None,
    chat_id: str | None = None,
) -> dict:
    """Send a plain text message via the existing PPT Telegram bot."""
    try:
        from src.integrations import telegram_bot
        resolved_chat_id = chat_id
        if resolved_chat_id is None and user_id is not None:
            from src.notify import store
            resolved_chat_id = store.telegram_chat_for_user(user_id)
        return telegram_bot.send_message_result(text, chat_id=resolved_chat_id)
    except Exception as e:
        log.error("Telegram channel failed: %s", e)
        return {"ok": False, "message_id": None}


def send_telegram(
    text: str,
    *,
    user_id: int | None = None,
    chat_id: str | None = None,
) -> bool:
    return bool(send_telegram_result(text, user_id=user_id, chat_id=chat_id).get("ok"))


# ── TTS (Piper) channel ───────────────────────────────────────────────────────

def send_tts(text: str) -> bool:
    """Speak the message aloud via Piper TTS (same engine as the voice assistant).

    WHY we reuse Piper here:
      Piper is already set up and the voice model is downloaded.
      Reusing it for proactive notifications means your physical device speaks
      to you in the same voice as the assistant — consistent personality.

    HOW it works:
      We pipe the text into Piper's stdin and Piper plays it via the default
      audio output device.  This is the same pattern as src/tts/speaker.py.
    """
    try:
        # Resolve the piper binary path relative to project root
        project_root = Path(__file__).parent.parent.parent
        piper_bin = project_root / "bin" / "piper" / "piper"

        if not piper_bin.exists():
            # Fall back to system piper if installed
            piper_bin = "piper"

        from config.settings import PIPER_MODEL_DIR, PIPER_VOICE
        model_path = project_root / PIPER_MODEL_DIR / f"{PIPER_VOICE}.onnx"

        if not model_path.exists():
            log.warning("Piper model not found at %s — TTS skipped.", model_path)
            return False

        # piper reads from stdin, writes raw PCM to stdout → pipe to aplay/afplay
        import platform
        player = "afplay" if platform.system() == "Darwin" else "aplay"

        cmd = (
            f'echo "{text}" | {piper_bin} '
            f'--model "{model_path}" --output-raw | {player} -'
        )
        subprocess.run(cmd, shell=True, check=True, timeout=30)
        return True
    except Exception as e:
        log.error("TTS channel failed: %s", e)
        return False


# ── Unified send ──────────────────────────────────────────────────────────────

def send(text: str,
         channels: list[str] | None = None,
         tts_enabled: bool = True,
         user_id: int | None = None,
         chat_id: str | None = None) -> dict[str, bool | str | int | None]:
    """Send a message to one or more channels.

    Args:
        text:        The message to deliver.
        channels:    List of 'telegram' and/or 'tts'.  Defaults to ['telegram'].
        tts_enabled: Quick override to silence TTS (useful during sleep hours).

    Returns:
        Dict of {channel: success_bool} for each channel attempted.
    """
    if channels is None:
        channels = ["telegram"]

    results: dict[str, bool | str | int | None] = {}

    if "telegram" in channels:
        delivery = send_telegram_result(text, user_id=user_id, chat_id=chat_id)
        results["telegram"] = bool(delivery.get("ok"))
        results["telegram_message_id"] = delivery.get("message_id")
        log.info("Telegram → %s", "✓" if results["telegram"] else "✗")

    if "tts" in channels and tts_enabled:
        results["tts"] = send_tts(text)
        log.info("TTS → %s", "✓" if results["tts"] else "✗")

    return results


# ── Convenience wrappers ──────────────────────────────────────────────────────

def notify_habit(habit_name: str, streak: int = 0,
                 channels: list[str] | None = None,
                 user_id: int | None = None) -> dict:
    """Generate and send a relationship-aware habit reminder."""
    from src.notify.relationship import habit_reminder
    msg = habit_reminder(habit_name, streak, user_id=user_id)
    return send(msg, channels=channels, user_id=user_id)


def notify_goal(goal_title: str, progress: int = 0, deadline: str | None = None,
                channels: list[str] | None = None,
                user_id: int | None = None) -> dict:
    """Generate and send a relationship-aware goal reminder."""
    from src.notify.relationship import goal_reminder
    msg = goal_reminder(goal_title, progress, deadline, user_id=user_id)
    return send(msg, channels=channels, user_id=user_id)


def notify_checkin(prev_mood: int | None = None,
                   channels: list[str] | None = None,
                   user_id: int | None = None) -> dict:
    """Prompt the user for their daily mood check-in."""
    from src.notify.relationship import checkin_prompt
    msg = checkin_prompt(prev_mood, user_id=user_id)
    return send(msg, channels=channels, user_id=user_id)


def notify_morning(habit_count: int = 0,
                   channels: list[str] | None = None,
                   user_id: int | None = None) -> dict:
    """Send the morning greeting with today's habit count."""
    from src.notify.relationship import morning_greeting
    msg = morning_greeting(habit_count, user_id=user_id)
    return send(msg, channels=channels, user_id=user_id)
