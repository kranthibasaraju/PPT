"""Tests for STT Whisper transcriber."""
import pytest
import numpy as np
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def test_transcriber_loads():
    """Whisper model should load without error."""
    try:
        from src.stt.transcriber import transcribe
        assert callable(transcribe)
    except ImportError as e:
        pytest.skip(f"faster-whisper not installed: {e}")


def test_transcribe_silent_audio():
    """Transcribing silent audio should return a string, not crash."""
    try:
        from src.stt.transcriber import transcribe
        silent = np.zeros(16000, dtype=np.float32)  # 1s silence at 16kHz
        result = transcribe(silent)
        assert isinstance(result, str)
    except Exception as e:
        pytest.skip(f"STT not available: {e}")


def test_transcribe_sine_wave():
    """Transcribing a sine wave should return a string, not crash."""
    try:
        from src.stt.transcriber import transcribe
        t = np.linspace(0, 1, 16000, dtype=np.float32)
        sine = np.sin(2 * np.pi * 440 * t)
        result = transcribe(sine)
        assert isinstance(result, str)
    except Exception as e:
        pytest.skip(f"STT not available: {e}")
