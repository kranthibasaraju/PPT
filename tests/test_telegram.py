import pytest
from unittest.mock import patch, MagicMock
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

def test_send_message_no_chat_id():
    import config.settings as s
    s.TELEGRAM_CHAT_ID = None
    from src.integrations.telegram_bot import send_message
    assert send_message("test", chat_id=None) is False

def test_send_message_mocked():
    with patch('requests.post') as mock_post:
        mock_post.return_value = MagicMock(raise_for_status=MagicMock())
        from src.integrations import telegram_bot
        assert telegram_bot.send_message("hello", chat_id="123") is True

def test_verify_connection_mocked():
    with patch('requests.get') as mock_get:
        mock_get.return_value = MagicMock(json=lambda: {"ok": True, "result": {"username": "pptbot", "first_name": "PPT"}})
        from src.integrations.telegram_bot import verify_connection
        assert verify_connection() is True

def test_notify_sends_message():
    with patch('src.integrations.telegram_bot.send_message') as mock_send:
        mock_send.return_value = True
        from src.integrations.telegram_bot import notify
        notify("task_done", "Done!")
        mock_send.assert_called_once()
        assert "✅" in mock_send.call_args[0][0]

def test_handle_start_command():
    with patch('src.integrations.telegram_bot.send_message'):
        from src.integrations.command_handler import handle_command
        reply = handle_command("/start", "123")
        assert "PPT is online" in reply

def test_handle_unknown_command():
    with patch('src.integrations.telegram_bot.send_message'):
        from src.integrations.command_handler import handle_command
        reply = handle_command("/foobar", "123")
        assert "Unknown" in reply
