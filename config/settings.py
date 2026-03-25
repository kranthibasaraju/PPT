# config/settings.py
# Central configuration for PPT — Personal AI Voice Assistant
# Edit these values to match your hardware and preferences.

# ── Wake Word ──────────────────────────────────────────────────────────────────
WAKE_WORD = "hey_jarvis"   # closest available openwakeword built-in; swap for custom in Phase 1

# ── Audio / Microphone ────────────────────────────────────────────────────────
MIC_DEVICE_INDEX = None      # None = system default; set to int index to pin a device
SAMPLE_RATE = 16000          # Hz — Whisper and OpenWakeWord both expect 16 kHz
SILENCE_THRESHOLD = 0.01     # RMS amplitude below which audio is considered silence
MAX_RECORD_SECONDS = 30      # Hard cap on recording length after wake word
SILENCE_DURATION = 2.0       # Seconds of silence that ends a recording

# ── Speech-to-Text (Whisper via faster-whisper) ────────────────────────────────
WHISPER_MODEL = "base.en"    # Options: tiny.en, base.en, small.en, medium.en

# ── LLM (Ollama) ──────────────────────────────────────────────────────────────
OLLAMA_MODEL = "llama3.2:3b"
OLLAMA_HOST = "http://localhost:11434"

# ── Text-to-Speech (Piper) ────────────────────────────────────────────────────
PIPER_VOICE = "en_US-lessac-medium"
PIPER_BIN = "piper"   # unused fallback; speaker.py invokes via sys.executable -m piper
PIPER_MODEL_DIR = "./models/piper"

# ── Telegram Bot ──────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = "8618744531:AAEbP7H0eRLqCC2hLPPxajjnsFFQfjKNvU0"
TELEGRAM_CHAT_ID = "5330253249"  # Run scripts/setup_telegram.py to set this automatically

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_LEVEL = "INFO"           # DEBUG | INFO | WARNING | ERROR
