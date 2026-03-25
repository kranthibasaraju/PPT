"""
src/wake/detector.py
Wake word detector using OpenWakeWord + sounddevice.

Usage:
    python src/wake/detector.py              # runs listen_and_record() once
    python src/wake/detector.py --test       # prints detections, no recording, Ctrl+C to stop
    python src/wake/detector.py --list-devices  # lists available input devices

NOTE: OpenWakeWord's built-in "hey_jarvis" model is used as a proxy for "Hey PPT".
      A custom "hey_ppt" model will be trained and swapped in during Phase 1.
"""

import sys
import os

# Allow running as script from project root or directly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import argparse
import time
import logging
import numpy as np
import sounddevice as sd
from openwakeword.model import Model

from config.settings import (
    SAMPLE_RATE,
    MIC_DEVICE_INDEX,
    SILENCE_THRESHOLD,
    MAX_RECORD_SECONDS,
    SILENCE_DURATION,
    LOG_LEVEL,
    WAKE_WORD,
)

logging.basicConfig(level=getattr(logging, LOG_LEVEL))
log = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
CHUNK_SIZE = 1280          # frames per chunk — 80 ms at 16 kHz (required by OWW)
WAKEWORD_MODEL = WAKE_WORD   # driven by config/settings.py
DETECTION_THRESHOLD = 0.5  # confidence score required to trigger


def _load_model() -> Model:
    """Load the OpenWakeWord model (downloads on first run)."""
    log.info("Loading OpenWakeWord model '%s'…", WAKEWORD_MODEL)
    model = Model(wakeword_models=[WAKEWORD_MODEL], inference_framework="onnx")
    log.info("Wake word model ready.")
    return model


def list_devices() -> None:
    """Print all available audio input devices."""
    print("Available audio input devices:")
    devices = sd.query_devices()
    for idx, dev in enumerate(devices):
        if dev["max_input_channels"] > 0:
            print(f"  [{idx}] {dev['name']}  ({dev['max_input_channels']} ch)")


def _rms(chunk: np.ndarray) -> float:
    """Root-mean-square amplitude of a chunk."""
    return float(np.sqrt(np.mean(chunk.astype(np.float32) ** 2)))


def listen_and_record() -> np.ndarray:
    """
    Block until wake word is detected, then record until silence or MAX_RECORD_SECONDS.

    Returns:
        numpy float32 array of the recorded speech at SAMPLE_RATE.
    """
    model = _load_model()
    print("Listening for wake word… (say 'Hey PPT')")

    # Open a continuous mic stream
    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="int16",
        device=MIC_DEVICE_INDEX,
        blocksize=CHUNK_SIZE,
    ) as stream:
        # ── Phase 1: Wait for wake word ────────────────────────────────────────
        while True:
            chunk, _ = stream.read(CHUNK_SIZE)
            chunk_1d = chunk[:, 0]  # mono

            # OWW expects float32 in [-1, 1]
            chunk_f32 = chunk_1d.astype(np.float32) / 32768.0
            prediction = model.predict(chunk_f32)

            score = prediction.get(WAKEWORD_MODEL, 0.0)
            if score >= DETECTION_THRESHOLD:
                print("Wake word detected!")
                log.info("Wake word score=%.3f", score)
                break

        # ── Phase 2: Record speech until silence ───────────────────────────────
        print("Recording… (speak now)")
        recorded_chunks: list[np.ndarray] = []
        silence_samples = 0
        silence_limit = int(SILENCE_DURATION * SAMPLE_RATE / CHUNK_SIZE)  # chunks
        max_chunks = int(MAX_RECORD_SECONDS * SAMPLE_RATE / CHUNK_SIZE)
        total_chunks = 0

        while total_chunks < max_chunks:
            chunk, _ = stream.read(CHUNK_SIZE)
            chunk_1d = chunk[:, 0]
            recorded_chunks.append(chunk_1d.copy())
            total_chunks += 1

            # Detect silence using normalised RMS
            rms = _rms(chunk_1d) / 32768.0
            if rms < SILENCE_THRESHOLD:
                silence_samples += 1
            else:
                silence_samples = 0  # reset on any speech

            if silence_samples >= silence_limit:
                log.info("Silence detected — stopping recording.")
                break

    if not recorded_chunks:
        return np.array([], dtype=np.float32)

    # Concatenate and convert to float32
    audio_int16 = np.concatenate(recorded_chunks)
    audio_f32 = audio_int16.astype(np.float32) / 32768.0
    log.info("Recorded %.1f seconds of audio.", len(audio_f32) / SAMPLE_RATE)
    return audio_f32


def _test_mode() -> None:
    """Just print detections — no recording. Press Ctrl+C to stop."""
    model = _load_model()
    print(f"Test mode — listening for '{WAKEWORD_MODEL}'. Press Ctrl+C to stop.")

    try:
        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="int16",
            device=MIC_DEVICE_INDEX,
            blocksize=CHUNK_SIZE,
        ) as stream:
            while True:
                chunk, _ = stream.read(CHUNK_SIZE)
                chunk_f32 = chunk[:, 0].astype(np.float32) / 32768.0
                prediction = model.predict(chunk_f32)
                score = prediction.get(WAKEWORD_MODEL, 0.0)
                if score >= DETECTION_THRESHOLD:
                    print(f"[{time.strftime('%H:%M:%S')}] Wake word detected! score={score:.3f}")
    except KeyboardInterrupt:
        print("\nTest mode stopped.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PPT wake word detector")
    parser.add_argument("--test", action="store_true", help="Print detections without recording")
    parser.add_argument("--list-devices", action="store_true", help="List audio input devices")
    args = parser.parse_args()

    if args.list_devices:
        list_devices()
    elif args.test:
        try:
            sd.query_devices(kind="input")
        except Exception as e:
            print(f"\n[WARNING] No mic available ({e}).")
            print("Running model load smoke test with synthetic audio…")
            model = _load_model()
            chunk = np.zeros(CHUNK_SIZE, dtype=np.float32)
            prediction = model.predict(chunk)
            score = prediction.get(WAKEWORD_MODEL, 0.0)
            print(f"[Wake word OK] Model loaded, synthetic score={score:.3f}")
            print("[ACTION NEEDED] Grant microphone access to Terminal in:")
            print("  System Settings > Privacy & Security > Microphone")
            sys.exit(0)
        _test_mode()
    else:
        audio = listen_and_record()
        print(f"Captured {len(audio) / SAMPLE_RATE:.1f}s of audio.")
