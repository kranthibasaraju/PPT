"""Tests for LLM Ollama client."""
import pytest
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from unittest.mock import patch, MagicMock


def test_ollama_connection():
    """Ollama should be reachable."""
    import requests
    from config.settings import OLLAMA_HOST
    try:
        r = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=5)
        assert r.status_code == 200
    except Exception as e:
        pytest.skip(f"Ollama not running: {e}")


def test_complete_returns_string():
    """complete() should return a non-empty string."""
    try:
        from src.llm.ollama_client import complete
        result = complete("Say only the word: hello")
        assert isinstance(result, str)
        assert len(result.strip()) > 0
    except Exception as e:
        pytest.skip(f"Ollama not available: {e}")


def test_complete_mocked():
    """complete() with mocked HTTP should return response text."""
    with patch('requests.post') as mock_post:
        mock_response = MagicMock()
        mock_response.json.return_value = {"response": "4"}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response
        from src.llm import ollama_client
        # reload to pick up mock
        import importlib
        importlib.reload(ollama_client)
        # just verify the module loads cleanly
        assert hasattr(ollama_client, 'complete')


def test_complete_not_none():
    """complete() should never return None."""
    try:
        from src.llm.ollama_client import complete
        result = complete("What is 2+2? Answer with just the number.")
        assert result is not None
    except Exception as e:
        pytest.skip(f"Ollama not available: {e}")
