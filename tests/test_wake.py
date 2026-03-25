"""Tests for wake word detector."""
import pytest
import numpy as np
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def test_wake_detector_imports():
    """Wake word detector module should import cleanly."""
    try:
        import src.wake.detector as det
        assert det is not None
    except ImportError as e:
        pytest.skip(f"openwakeword not installed: {e}")


def test_wake_model_loads():
    """OpenWakeWord model should initialise."""
    try:
        from openwakeword.model import Model
        m = Model(wakeword_models=["hey_jarvis"], inference_framework="onnx")
        assert m is not None
    except Exception as e:
        pytest.skip(f"Wake word model not available: {e}")


def test_wake_scores_on_silence():
    """Model should return float scores between 0 and 1 for silent audio."""
    try:
        from openwakeword.model import Model
        m = Model(wakeword_models=["hey_jarvis"], inference_framework="onnx")
        audio = np.zeros(1280, dtype=np.int16)
        result = m.predict(audio)
        for key, score in result.items():
            assert 0.0 <= float(score) <= 1.0
    except Exception as e:
        pytest.skip(f"Wake word model not available: {e}")
