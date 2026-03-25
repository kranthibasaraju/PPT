"""
tests/test_ollama.py
Basic tests for the Ollama LLM client.

Run with:
    python -m pytest tests/test_ollama.py -v
    # or directly:
    python tests/test_ollama.py
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.llm import ollama_client


def test_connection():
    """Ollama should be reachable on localhost."""
    assert ollama_client.check_connection(), (
        "Ollama is not running. Start it with: ollama serve"
    )


def test_complete_returns_nonempty():
    """A simple prompt should return a non-empty string."""
    if not ollama_client.check_connection():
        pytest.skip("Ollama not running — skipping LLM test.")

    response = ollama_client.complete("Say hello in exactly one word.")
    assert isinstance(response, str), "Response should be a string."
    assert len(response.strip()) > 0, "Response should not be empty."


def test_complete_with_history():
    """Conversation history should be appended correctly."""
    if not ollama_client.check_connection():
        pytest.skip("Ollama not running — skipping LLM test.")

    history: list[dict] = []
    r1 = ollama_client.complete("My name is Rana.", history)
    assert len(r1) > 0

    # History should now contain 2 entries (user + assistant)
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[1]["role"] == "assistant"

    r2 = ollama_client.complete("What is my name?", history)
    assert len(r2) > 0
    # History should have grown to 4 entries
    assert len(history) == 4


if __name__ == "__main__":
    # Simple runner without pytest
    print("Testing Ollama connection…")
    ok = ollama_client.check_connection()
    print(f"  Connection: {'OK' if ok else 'FAILED'}")

    if ok:
        print("\nSending test prompt…")
        resp = ollama_client.complete("What is today's date and what can you help me with?")
        print(f"  Response: {resp}")
        assert resp, "Response was empty!"
        print("\nAll tests passed.")
    else:
        print("Skipping prompt test — Ollama not running.")
