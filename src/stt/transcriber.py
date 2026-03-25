"""
src/stt/transcriber.py
Speech-to-text using faster-whisper.

Usage:
    python src/stt/transcriber.py           # transcribe from module (import transcribe)
    python src/stt/transcriber.py --test    # records 8s from mic and prints transcription
"""

from __future__ import annotations  # enables X | Y union syntax on Python 3.9

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import argparse
import logging
import tempfile
import time
import wave

import numpy as np
from faster_whisper import WhisperModel

from config.settings import (
    WHISPER_MODEL,
    SAMPLE_RATE,
    MIC_DEVICE_INDEX,
    LOG_LEVEL,
)

logging.basicConfig(level=getattr(logging, LOG_LEVEL))
log = logging.getLogger(__name__)

# ── Singleton model ────────────────────────────────────────────────────────────
_model: WhisperModel | None = None


def _get_model() -> WhisperModel:
    """Load the Whisper model once and reuse it across calls."""
    global _model
    if _model is None:
        log.info("Loading Whisper model '%s'…", WHISPER_MODEL)
        _model = WhisperModel(WHISPER_MODEL, device="auto", compute_type="auto")
        log.info("Whisper model loaded.")
    return _model


def transcribe(audio: np.ndarray, sample_rate: int = SAMPLE_RATE) -> str:
    """
    Transcribe a numpy float32 audio array to text.

    Args:
        audio:       Float32 array, values in [-1.0, 1.0], mono.
        sample_rate: Hz of the audio (default: SAMPLE_RATE from config).

    Returns:
        Transcribed text string (stripped of leading/trailing whitespace).
    """
    model = _get_model()

    # Write audio to a temporary WAV file — faster-whisper accepts file paths
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        _save_wav(audio, sample_rate, tmp_path)

        log.info("Transcribing %.1f seconds of audio…", len(audio) / sample_rate)
        t0 = time.perf_counter()

        segments, info = model.transcribe(
            tmp_path,
            language="en",
            beam_size=5,
            vad_filter=True,       # skip silent regions
            vad_parameters={"min_silence_duration_ms": 500},
        )

        # Consume the generator and join all segment texts
        text = " ".join(seg.text for seg in segments).strip()

        elapsed = time.perf_counter() - t0
        log.info("Transcription done in %.2fs: %r", elapsed, text)

    finally:
        os.unlink(tmp_path)

    return text


def _save_wav(audio: np.ndarray, sample_rate: int, path: str) -> None:
    """Write a float32 numpy array to a 16-bit WAV file."""
    # Clip to [-1, 1] before converting to int16
    clipped = np.clip(audio, -1.0, 1.0)
    pcm = (clipped * 32767).astype(np.int16)

    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)          # 16-bit = 2 bytes
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())


def _record_test_audio(seconds: int = 8) -> np.ndarray:
    """Record `seconds` of audio from the default mic for testing."""
    import sounddevice as sd

    print(f"Recording {seconds}s from mic — speak now…")
    raw = sd.rec(
        int(seconds * SAMPLE_RATE),
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="float32",
        device=MIC_DEVICE_INDEX,
    )
    sd.wait()
    print("Recording complete.")
    return raw[:, 0]  # flatten to mono


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PPT STT transcriber")
    parser.add_argument("--test", action="store_true", help="Record 8s from mic and transcribe")
    parser.add_argument("--file", help="Transcribe a WAV file instead of recording from mic")
    args = parser.parse_args()

    if args.file:
        import wave
        with wave.open(args.file, "rb") as wf:
            sr = wf.getframerate()
            raw = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
        audio = raw.astype(np.float32) / 32768.0
        result = transcribe(audio, sr)
        print(f"\nTranscription: {result!r}")
    elif args.test:
        import sounddevice as sd
        try:
            sd.query_devices(kind="input")
            audio = _record_test_audio(seconds=8)
        except Exception as e:
            print(f"\n[WARNING] No mic available ({e}).")
            print("Generating synthetic audio to verify Whisper model loads correctly…")
            # 3s of silence — Whisper should return empty string, proving the pipeline works
            audio = np.zeros(3 * SAMPLE_RATE, dtype=np.float32)
        result = transcribe(audio, SAMPLE_RATE)
        print(f"\nTranscription: {result!r}")
        if audio.max() == 0.0:
            print("[STT OK] Whisper model loaded and ran on synthetic audio.")
            print("[ACTION NEEDED] Grant microphone access to Terminal in:")
            print("  System Settings > Privacy & Security > Microphone")
    else:
        print("Import this module and call transcribe(audio, sample_rate).")
        print("Run with --test to record from mic and print transcription.")
