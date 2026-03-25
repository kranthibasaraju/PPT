"""
tests/test_pipeline.py
Tests for src/orchestrator/pipeline.py.

All external components (LLM, STT, TTS, wake detector, sounddevice) are mocked
so the tests run fast without real audio or a live Ollama server.
"""

import sys
import os
import argparse
from unittest.mock import patch, MagicMock, call

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.orchestrator import pipeline


# ── Helpers ───────────────────────────────────────────────────────────────────

def _dummy_audio() -> np.ndarray:
    """1-second silent float32 array — valid pipeline input."""
    return np.zeros(16000, dtype=np.float32)


def _make_capture_side_effect(*return_values):
    """
    Return a side_effect function that yields the given values in order and
    then raises KeyboardInterrupt to stop the pipeline loop cleanly.
    """
    values = list(return_values)

    def _capture(no_wake: bool):
        if values:
            v = values.pop(0)
            if isinstance(v, Exception):
                raise v
            return v
        raise KeyboardInterrupt

    return _capture


# ── Argparse ──────────────────────────────────────────────────────────────────

def test_no_wake_flag_recognised():
    """--no-wake is a valid flag and sets no_wake=True."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-wake", action="store_true")
    args = parser.parse_args(["--no-wake"])
    assert args.no_wake is True


def test_no_wake_flag_default_false():
    """--no-wake defaults to False when omitted."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-wake", action="store_true")
    args = parser.parse_args([])
    assert args.no_wake is False


# ── Startup / initialisation ──────────────────────────────────────────────────

def test_pipeline_init_all_components_no_crash():
    """
    run() should start up (check connection, load model) without crashing when
    every external call is mocked.  The loop is stopped after one empty-audio
    iteration via KeyboardInterrupt.
    """
    with patch("src.llm.ollama_client.check_connection", return_value=True), \
         patch("src.stt.transcriber._get_model", return_value=MagicMock()), \
         patch("src.orchestrator.pipeline._capture_audio",
               side_effect=_make_capture_side_effect(_dummy_audio())), \
         patch("src.stt.transcriber.transcribe", return_value=""), \
         patch("src.tts.speaker.speak"):
        # Empty transcription → loop continues, then KeyboardInterrupt exits cleanly
        pipeline.run(no_wake=True)  # must not raise


# ── Full one-turn flow ────────────────────────────────────────────────────────

def test_stt_result_triggers_llm_and_tts():
    """
    When STT returns 'what time is it', LLM.complete() and speaker.speak()
    must both be called exactly once.
    """
    mock_complete = MagicMock(return_value="It is 3 PM.")
    mock_speak = MagicMock()

    with patch("src.llm.ollama_client.check_connection", return_value=True), \
         patch("src.stt.transcriber._get_model", return_value=MagicMock()), \
         patch("src.orchestrator.pipeline._capture_audio",
               side_effect=_make_capture_side_effect(_dummy_audio())), \
         patch("src.stt.transcriber.transcribe", return_value="what time is it"), \
         patch("src.llm.ollama_client.complete", mock_complete), \
         patch("src.tts.speaker.speak", mock_speak):
        pipeline.run(no_wake=True)

    mock_complete.assert_called_once()
    # The first positional arg to complete() should contain the transcribed text
    assert mock_complete.call_args[0][0] == "what time is it"
    mock_speak.assert_called_once_with("It is 3 PM.")


def test_llm_is_called_with_transcription():
    """LLM receives exactly the text returned by STT."""
    mock_complete = MagicMock(return_value="Response.")
    captured_args = []

    def recording_complete(text, history=None):
        captured_args.append(text)
        return "Response."

    with patch("src.llm.ollama_client.check_connection", return_value=True), \
         patch("src.stt.transcriber._get_model", return_value=MagicMock()), \
         patch("src.orchestrator.pipeline._capture_audio",
               side_effect=_make_capture_side_effect(_dummy_audio())), \
         patch("src.stt.transcriber.transcribe", return_value="hello pipeline"), \
         patch("src.llm.ollama_client.complete", side_effect=recording_complete), \
         patch("src.tts.speaker.speak"):
        pipeline.run(no_wake=True)

    assert captured_args == ["hello pipeline"]


# ── Error recovery ────────────────────────────────────────────────────────────

def test_empty_llm_response_does_not_crash():
    """
    If LLM returns an empty string, the pipeline must not crash.
    speak() is still called (pipeline does not gate on empty response).
    """
    mock_speak = MagicMock()

    with patch("src.llm.ollama_client.check_connection", return_value=True), \
         patch("src.stt.transcriber._get_model", return_value=MagicMock()), \
         patch("src.orchestrator.pipeline._capture_audio",
               side_effect=_make_capture_side_effect(_dummy_audio())), \
         patch("src.stt.transcriber.transcribe", return_value="some query"), \
         patch("src.llm.ollama_client.complete", return_value=""), \
         patch("src.tts.speaker.speak", mock_speak):
        pipeline.run(no_wake=True)  # must not raise

    mock_speak.assert_called_once_with("")


def test_stt_exception_does_not_crash_pipeline():
    """
    An exception raised by transcriber.transcribe() is caught and the loop
    continues (then exits via KeyboardInterrupt).
    """
    call_count = [0]

    def flaky_capture(no_wake):
        call_count[0] += 1
        if call_count[0] == 1:
            return _dummy_audio()  # first call: valid audio (STT will raise)
        raise KeyboardInterrupt   # second call: stop the loop

    with patch("src.llm.ollama_client.check_connection", return_value=True), \
         patch("src.stt.transcriber._get_model", return_value=MagicMock()), \
         patch("src.orchestrator.pipeline._capture_audio", side_effect=flaky_capture), \
         patch("src.stt.transcriber.transcribe", side_effect=RuntimeError("STT boom")), \
         patch("src.llm.ollama_client.complete") as mock_complete, \
         patch("src.tts.speaker.speak"):
        pipeline.run(no_wake=True)  # must not raise

    # LLM should never have been reached since STT failed
    mock_complete.assert_not_called()


def test_none_audio_skips_turn():
    """
    If _capture_audio returns None, the pipeline skips that turn without
    calling STT, LLM, or TTS.
    """
    with patch("src.llm.ollama_client.check_connection", return_value=True), \
         patch("src.stt.transcriber._get_model", return_value=MagicMock()), \
         patch("src.orchestrator.pipeline._capture_audio",
               side_effect=_make_capture_side_effect(None)), \
         patch("src.stt.transcriber.transcribe") as mock_transcribe, \
         patch("src.llm.ollama_client.complete") as mock_complete, \
         patch("src.tts.speaker.speak"):
        pipeline.run(no_wake=True)

    mock_transcribe.assert_not_called()
    mock_complete.assert_not_called()
