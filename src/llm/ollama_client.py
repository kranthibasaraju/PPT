"""
src/llm/ollama_client.py
Ollama LLM client using the REST API.

Usage:
    python src/llm/ollama_client.py              # import and call complete()
    python src/llm/ollama_client.py --test       # checks connection and sends a test prompt
"""

from __future__ import annotations  # enables X | Y union syntax on Python 3.9

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import argparse
import logging
import requests

from config.settings import OLLAMA_HOST, OLLAMA_MODEL, LOG_LEVEL

logging.basicConfig(level=getattr(logging, LOG_LEVEL))
log = logging.getLogger(__name__)

# ── System prompt ─────────────────────────────────────────────────────────────
_SYSTEM_PROMPT = (
    "You are PPT, a personal AI assistant for Rana. "
    "Keep responses concise and direct — you will be spoken aloud, so avoid markdown, "
    "bullet points, and long explanations. "
    "Answer in 1-3 sentences unless asked for more detail."
)


def check_connection() -> bool:
    """
    Ping the Ollama health endpoint.

    Returns:
        True if Ollama is reachable and running, False otherwise.
    """
    try:
        resp = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=3)
        if resp.ok:
            log.info("Ollama is reachable at %s", OLLAMA_HOST)
            return True
        log.warning("Ollama responded with status %d", resp.status_code)
        return False
    except requests.exceptions.ConnectionError:
        log.error("Cannot reach Ollama at %s — is it running?", OLLAMA_HOST)
        return False
    except requests.exceptions.Timeout:
        log.error("Ollama connection timed out.")
        return False


def complete(
    user_message: str,
    conversation_history: list[dict] | None = None,
) -> str:
    """
    Send a message to Ollama and return the assistant's response.

    Args:
        user_message:         The user's text.
        conversation_history: Optional list of prior turns as
                              [{"role": "user"|"assistant", "content": "..."}].
                              Pass the same list across calls to maintain context.

    Returns:
        The assistant's response string.
    """
    if conversation_history is None:
        conversation_history = []

    # Build the messages array: system prompt + history + new user message
    messages = [{"role": "system", "content": _SYSTEM_PROMPT}]
    messages.extend(conversation_history)
    messages.append({"role": "user", "content": user_message})

    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
    }

    log.debug("Sending to Ollama: %r", user_message)

    try:
        resp = requests.post(
            f"{OLLAMA_HOST}/api/chat",
            json=payload,
            timeout=60,   # LLM can be slow on first run
        )
        resp.raise_for_status()
    except requests.exceptions.ConnectionError:
        raise RuntimeError(
            f"Cannot reach Ollama at {OLLAMA_HOST}. "
            "Make sure Ollama is running: `ollama serve`"
        )
    except requests.exceptions.Timeout:
        raise RuntimeError("Ollama request timed out — the model may be loading.")

    data = resp.json()
    reply = data["message"]["content"].strip()
    log.debug("Ollama reply: %r", reply)

    # Append this turn to conversation history so the caller can pass it back
    conversation_history.append({"role": "user", "content": user_message})
    conversation_history.append({"role": "assistant", "content": reply})

    return reply


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PPT Ollama LLM client")
    parser.add_argument("--test", action="store_true", help="Check connection and send a test prompt")
    args = parser.parse_args()

    if args.test:
        print(f"Checking Ollama connection at {OLLAMA_HOST}…")
        if not check_connection():
            print("ERROR: Ollama is not reachable. Start it with: ollama serve")
            sys.exit(1)
        print("Connected.\n")

        prompt = "What is today's date and what can you help me with?"
        print(f"Sending: {prompt!r}\n")
        response = complete(prompt)
        print(f"PPT: {response}")
    else:
        print("Import this module and call complete(user_message).")
        print("Run with --test to check connection and send a test prompt.")
