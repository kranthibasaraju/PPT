"""
tests/test_transcriber.py
Basic tests for the Whisper STT transcriber.

Run with:
    python -m pytest tests/test_transcriber.py -v
    # or directly:
    python tests/test_transcriber.py
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pytest
from src.stt import transcriber
from config.settings import SAMPLE_RATE


def _make_sine(freq_hz: float = 440.0, duration_s: float = 2.0) -> np.ndarray:
    """Generate a mono sine wave as a float32 numpy array."""
    t = np.linspace(0, duration_s, int(SAMPLE_RATE * duration_s), endpoint=False)
    wave = 0.5 * np.sin(2 * np.pi * freq_hz * t)
    return wave.astype(np.float32)


def _make_silence(duration_s: float = 1.0) -> np.ndarray:
    """Generate silence (all zeros) as a float32 numpy array."""
    return np.zeros(int(SAMPLE_RATE * duration_s), dtype=np.float32)


def test_transcribe_does_not_crash_on_sine():
    """
    Transcribing a sine wave should not raise an exception.
    The output may be empty or nonsensical — that's expected for non-speech audio.
    """
    audio = _make_sine(freq_hz=440.0, duration_s=2.0)
    result = transcriber.transcribe(audio, SAMPLE_RATE)
    assert isinstance(result, str), "transcribe() must return a string."


def test_transcribe_does_not_crash_on_silence():
    """
    Transcribing silence should not raise an exception.
    Whisper with VAD filtering will typically return an empty string.
    """
    audio = _make_silence(duration_s=2.0)
    result = transcriber.transcribe(audio, SAMPLE_RATE)
    assert isinstance(result, str), "transcribe() must return a string."


def test_transcribe_returns_string_type():
    """Return type is always str, never None."""
    audio = _make_sine(freq_hz=1000.0, duration_s=1.5)
    result = transcriber.transcribe(audio, SAMPLE_RATE)
    assert result is not None
    assert isinstance(result, str)


def test_model_singleton():
    """Calling _get_model() twice returns the same object."""
    m1 = transcriber._get_model()
    m2 = transcriber._get_model()
    assert m1 is m2, "Model should be a singleton."


if __name__ == "__main__":
    print("Testing Whisper transcriber with synthetic audio…\n")

    print("1. Sine wave (440 Hz, 2s)…")
    audio = _make_sine()
    result = transcriber.transcribe(audio, SAMPLE_RATE)
    print(f"   Result: {result!r}  (may be empty — that's fine)\n")

    print("2. Silence (2s)…")
    audio = _make_silence()
    result = transcriber.transcribe(audio, SAMPLE_RATE)
    print(f"   Result: {result!r}\n")

    print("3. Singleton check…")
    m1 = transcriber._get_model()
    m2 = transcriber._get_model()
    assert m1 is m2
    print("   Model is singleton: OK\n")

    print("All transcriber tests passed.")
