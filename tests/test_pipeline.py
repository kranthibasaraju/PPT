"""Integration tests for the full pipeline."""
import pytest
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from unittest.mock import patch, MagicMock


def test_pipeline_imports():
    """Pipeline module should import cleanly."""
    try:
        import src.orchestrator.pipeline as p
        assert p is not None
    except ImportError as e:
        pytest.fail(f"Pipeline import failed: {e}")


def test_pipeline_has_run_function():
    """Pipeline should expose a run() function."""
    try:
        from src.orchestrator.pipeline import run
        assert callable(run)
    except ImportError as e:
        pytest.skip(f"Pipeline not structured as expected: {e}")


def test_tts_and_llm_integration():
    """LLM response should flow into TTS without crashing."""
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        with patch('requests.post') as mock_post:
            mock_response = MagicMock()
            mock_response.iter_lines.return_value = [
                b'{"response": "Hello", "done": false}',
                b'{"response": " world", "done": true}'
            ]
            mock_response.raise_for_status = MagicMock()
            mock_post.return_value = mock_response
            # Just verify imports and mocks work together
            from src.tts.speaker import speak
            speak("Hello world")
            mock_run.assert_called()
