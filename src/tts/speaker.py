"""
src/tts/speaker.py
Text-to-speech using macOS `say` command (confirmed working).

Piper TTS backend is kept as commented-out code below for future reference.

Usage:
    python src/tts/speaker.py              # import and call speak()
    python src/tts/speaker.py --test       # speaks a test sentence
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from config.settings import LOG_LEVEL

logging.basicConfig(level=getattr(logging, LOG_LEVEL))
log = logging.getLogger(__name__)


def speak(text: str, backend: str = "auto") -> None:
    """
    Synthesise `text` and play it through the system speakers via macOS `say`.

    Args:
        text:    The sentence(s) to speak aloud.
        backend: Ignored — always uses macOS `say`. Kept for API compatibility.
    """
    subprocess.run(['say', text], check=True)


# ── Piper TTS (future use) ─────────────────────────────────────────────────────
# Piper generates higher-quality neural TTS but requires sounddevice playback.
# All the pieces work (piper model at models/piper/en_US-lessac-medium.onnx,
# sounddevice default device = Mac mini Speakers @ 48kHz, piper outputs 22050 Hz
# mono PCM). Re-enable by replacing speak() above with the implementation below.
#
# import numpy as np
# import sounddevice as sd
# from config.settings import PIPER_MODEL_DIR, PIPER_VOICE
#
# _PIPER_MODEL_PATH = os.path.join(PIPER_MODEL_DIR, f"{PIPER_VOICE}.onnx")
# _PIPER_SAMPLE_RATE = 22050
#
# def speak(text: str, backend: str = "auto") -> None:
#     if not text.strip():
#         return
#     log.info("Speaking: %r", text[:80])
#     piper_cmd = [sys.executable, "-m", "piper",
#                  "--model", _PIPER_MODEL_PATH, "--output_raw", "--quiet"]
#     try:
#         proc = subprocess.Popen(piper_cmd,
#                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE,
#                                 stderr=subprocess.DEVNULL)
#         raw, _ = proc.communicate(input=text.encode("utf-8"))
#         if not raw:
#             log.error("Piper produced no audio output.")
#             return
#         audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
#         sd.play(audio, samplerate=_PIPER_SAMPLE_RATE)
#         sd.wait()
#     except Exception as exc:
#         log.error("TTS playback error: %s", exc)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="PPT TTS speaker")
    parser.add_argument("--test", action="store_true", help="Speak a test sentence")
    args = parser.parse_args()

    if args.test:
        speak("Hello, I am PPT, your personal assistant. How can I help you today?")
    else:
        print("Import this module and call speak(text).")
        print("Run with --test to hear a sample sentence.")
