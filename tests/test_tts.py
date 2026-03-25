"""Tests for TTS speaker module."""
import subprocess
from unittest.mock import patch, MagicMock
import pytest
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def test_speak_calls_say():
    """speak() should call macOS say command."""
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        from src.tts.speaker import speak
        speak("Hello PPT")
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert 'say' in args
        assert 'Hello PPT' in args


def test_speak_with_empty_string():
    """speak() with empty string should not raise."""
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        from src.tts.speaker import speak
        speak("")  # should not raise


def test_speak_with_long_text():
    """speak() with long text should not raise."""
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        from src.tts.speaker import speak
        long_text = "This is a test sentence. " * 30
        speak(long_text)
        mock_run.assert_called_once()


def test_speak_with_special_chars():
    """speak() with numbers and punctuation should not raise."""
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        from src.tts.speaker import speak
        speak("Task #1 is done! 100% complete.")
        mock_run.assert_called_once()
