"""
src/orchestrator/pipeline.py
Main pipeline — wires wake → STT → LLM → TTS into a continuous voice loop.

Usage:
    python src/orchestrator/pipeline.py           # full voice loop with wake word
    python src/orchestrator/pipeline.py --no-wake # press Enter to record, no wake word needed
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import argparse
import logging
import time

from config.settings import SAMPLE_RATE, LOG_LEVEL

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger(__name__)


def _timestamp() -> str:
    return time.strftime("%H:%M:%S")


def run(no_wake: bool = False) -> None:
    """
    Start the PPT voice assistant loop.

    Args:
        no_wake: If True, skip wake word detection and instead record 5s on Enter.
                 Useful for testing individual pipeline stages.
    """
    # ── Startup checks ─────────────────────────────────────────────────────────
    from src.llm import ollama_client
    from src.stt import transcriber

    print(f"[{_timestamp()}] Checking Ollama connection…")
    if not ollama_client.check_connection():
        print(
            "ERROR: Ollama is not running. Start it with:\n"
            "  ollama serve\n"
            "Then re-run this script."
        )
        sys.exit(1)

    print(f"[{_timestamp()}] Loading Whisper model…")
    transcriber._get_model()  # warm up — avoids first-call latency in the loop

    print(f"\n[{_timestamp()}] PPT is ready. Say 'Hey PPT' to begin.\n")
    if no_wake:
        print("  (--no-wake mode: press Enter to start recording, speak for 5s)\n")

    # Maintain conversation history across turns so the LLM has context
    conversation_history: list[dict] = []

    # ── Main loop ──────────────────────────────────────────────────────────────
    while True:
        try:
            # ── Step 1: Capture audio ─────────────────────────────────────────
            audio = _capture_audio(no_wake)
            if audio is None or len(audio) == 0:
                log.warning("No audio captured — retrying.")
                continue

            t_heard = time.perf_counter()
            log.info("[%s] Audio captured: %.1fs", _timestamp(), len(audio) / SAMPLE_RATE)

            # ── Step 2: Speech → Text ─────────────────────────────────────────
            try:
                from src.stt import transcriber
                text = transcriber.transcribe(audio, SAMPLE_RATE)
            except Exception as exc:
                log.error("STT error: %s", exc)
                continue

            t_stt = time.perf_counter()

            if not text.strip():
                log.info("Empty transcription — nothing to respond to.")
                continue

            print(f"\nYou said: {text}")
            log.info("[%s] STT took %.2fs", _timestamp(), t_stt - t_heard)

            # ── Step 3: Text → LLM response ───────────────────────────────────
            try:
                from src.llm import ollama_client
                response = ollama_client.complete(text, conversation_history)
            except Exception as exc:
                log.error("LLM error: %s", exc)
                # Don't update history on error
                continue

            t_llm = time.perf_counter()
            print(f"PPT: {response}")
            log.info("[%s] LLM took %.2fs", _timestamp(), t_llm - t_stt)

            # ── Step 4: Response → Speech ─────────────────────────────────────
            try:
                from src.tts import speaker
                speaker.speak(response)
            except Exception as exc:
                log.error("TTS error: %s", exc)
                # TTS failure isn't fatal — we already printed the response

            t_tts = time.perf_counter()
            log.info(
                "[%s] TTS took %.2fs | Total end-to-end: %.2fs",
                _timestamp(),
                t_tts - t_llm,
                t_tts - t_heard,
            )

        except KeyboardInterrupt:
            print(f"\n[{_timestamp()}] Goodbye.")
            break
        except Exception as exc:
            # Catch-all: log and keep the loop alive
            log.error("Unexpected error in pipeline loop: %s", exc, exc_info=True)
            time.sleep(1)


def _capture_audio(no_wake: bool):
    """
    Capture audio either via wake word detection or manual Enter-key trigger.

    Returns:
        numpy float32 array, or None on failure.
    """
    import numpy as np

    if no_wake:
        input("Press Enter to speak…")
        import sounddevice as sd
        from config.settings import MIC_DEVICE_INDEX

        record_seconds = 5
        print(f"Recording {record_seconds}s — speak now…")
        raw = sd.rec(
            int(record_seconds * SAMPLE_RATE),
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            device=MIC_DEVICE_INDEX,
        )
        sd.wait()
        return raw[:, 0]  # mono
    else:
        from src.wake import detector
        return detector.listen_and_record()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PPT voice assistant pipeline")
    parser.add_argument(
        "--no-wake",
        action="store_true",
        help="Skip wake word — record 5s on Enter key press (useful for testing)",
    )
    args = parser.parse_args()
    run(no_wake=args.no_wake)
