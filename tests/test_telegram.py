"""Tests for Telegram bot integration."""
import pytest
from unittest.mock import patch, MagicMock
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# ── send_message ─────────────────────────────────────────────────────────────

def test_send_message_no_chat_id_returns_false():
    """send_message with no chat_id and no config should return False gracefully."""
    import config.settings as s
    original = s.TELEGRAM_CHAT_ID
    s.TELEGRAM_CHAT_ID = None
    import importlib, src.integrations.telegram_bot as tb
    importlib.reload(tb)
    result = tb.send_message("test", chat_id=None)
    assert result is False
    s.TELEGRAM_CHAT_ID = original


def test_send_message_success():
    """send_message should POST to Telegram and return True on success."""
    with patch("requests.post") as mock_post:
        mock_post.return_value = MagicMock(raise_for_status=MagicMock())
        from src.integrations import telegram_bot
        result = telegram_bot.send_message("hello PPT", chat_id="123456")
        assert result is True
        mock_post.assert_called_once()
        call_json = mock_post.call_args[1]["json"]
        assert call_json["chat_id"] == "123456"
        assert call_json["text"] == "hello PPT"


def test_send_message_request_error_returns_false():
    """send_message should return False (not raise) on network error."""
    with patch("requests.post", side_effect=Exception("network error")):
        from src.integrations import telegram_bot
        result = telegram_bot.send_message("hello", chat_id="123")
        assert result is False


# ── notify ───────────────────────────────────────────────────────────────────

def test_notify_task_done_includes_checkmark():
    """notify('task_done') should include ✅ icon."""
    with patch("src.integrations.telegram_bot.send_message") as mock_send:
        mock_send.return_value = True
        from src.integrations.telegram_bot import notify
        notify("task_done", "Setup complete")
        text = mock_send.call_args[0][0]
        assert "✅" in text
        assert "Setup complete" in text


def test_notify_error_includes_cross():
    """notify('error') should include ❌ icon."""
    with patch("src.integrations.telegram_bot.send_message") as mock_send:
        mock_send.return_value = True
        from src.integrations.telegram_bot import notify
        notify("error", "Ollama unreachable")
        text = mock_send.call_args[0][0]
        assert "❌" in text


def test_notify_unknown_event_uses_default_icon():
    """notify() with unknown event should still send a message."""
    with patch("src.integrations.telegram_bot.send_message") as mock_send:
        mock_send.return_value = True
        from src.integrations.telegram_bot import notify
        notify("some_unknown_event", "detail")
        mock_send.assert_called_once()


# ── verify_connection ────────────────────────────────────────────────────────

def test_verify_connection_success():
    """verify_connection should return True when API responds ok."""
    with patch("requests.get") as mock_get:
        mock_get.return_value = MagicMock(
            json=lambda: {"ok": True, "result": {"username": "pptbot", "first_name": "PPT"}}
        )
        from src.integrations.telegram_bot import verify_connection
        assert verify_connection() is True


def test_verify_connection_failure():
    """verify_connection should return False on bad token."""
    with patch("requests.get") as mock_get:
        mock_get.return_value = MagicMock(
            json=lambda: {"ok": False, "description": "Unauthorized"}
        )
        from src.integrations.telegram_bot import verify_connection
        assert verify_connection() is False


def test_verify_connection_network_error():
    """verify_connection should return False on network error."""
    with patch("requests.get", side_effect=Exception("timeout")):
        from src.integrations.telegram_bot import verify_connection
        assert verify_connection() is False


# ── command_handler ───────────────────────────────────────────────────────────

def test_handle_start_command():
    """/start should return PPT online message."""
    with patch("src.integrations.telegram_bot.send_message"):
        from src.integrations.command_handler import handle_command
        reply = handle_command("/start", "123")
        assert "PPT is online" in reply


def test_handle_help_command():
    """/help should return command list."""
    with patch("src.integrations.telegram_bot.send_message"):
        from src.integrations.command_handler import handle_command
        reply = handle_command("/help", "123")
        assert "/status" in reply


def test_handle_status_command():
    """/status should mention voice pipeline."""
    with patch("src.integrations.telegram_bot.send_message"):
        from src.integrations.command_handler import handle_command
        reply = handle_command("/status", "123")
        assert "Voice pipeline" in reply or "pipeline" in reply.lower()


def test_handle_unknown_command():
    """Unknown commands should return helpful error."""
    with patch("src.integrations.telegram_bot.send_message"):
        from src.integrations.command_handler import handle_command
        reply = handle_command("/foobar", "123")
        assert "Unknown" in reply or "unknown" in reply.lower()


def test_handle_command_sends_reply():
    """handle_command should always call send_message."""
    with patch("src.integrations.command_handler.send_message") as mock_send:
        mock_send.return_value = True
        from src.integrations.command_handler import handle_command
        handle_command("/start", "456")
        mock_send.assert_called_once_with(mock_send.call_args[0][0], chat_id="456")
