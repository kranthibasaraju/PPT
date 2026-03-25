# Chapter 5 — Technologies
## What Tools Are We Using and Why?

---

## How to Read This Chapter

Every technology in PPT was chosen deliberately. For each tool, this chapter explains:
- What it is and what problem it solves
- How it works (at a level that builds real understanding)
- Why we chose it over alternatives
- What you should know about it

This is not just a list of tools. It is an explanation of the technology landscape around voice AI, so you can make your own informed decisions on future projects.

---

## 1. OpenWakeWord

**What it is:** A Python library for detecting custom wake words in audio streams. It listens to a microphone continuously and fires an event when it hears a specific phrase.

**How it works:** OpenWakeWord runs a small neural network trained to distinguish a specific phrase (like "Hey PPT") from all other sounds. The network takes short windows of audio (a few hundred milliseconds) and outputs a confidence score. When the score exceeds a threshold, the wake word is declared detected.

The key insight is that this model is *much smaller* than a full speech recognition model. It doesn't need to understand what you're saying — it just needs to recognise one specific sound pattern. This makes it efficient enough to run continuously on a Raspberry Pi.

**Why we chose it:**
- Completely offline — no audio ever leaves the device
- Open source and free
- Supports custom wake words (you can train your own model for "Hey PPT")
- Efficient enough for always-on use on RPi4
- Python API is simple and clean

**Alternatives considered:**
- *Porcupine (Picovoice):* More polished, better accuracy, but requires a paid licence for custom wake words. Free tier limited.
- *Snowboy:* Discontinued. Not a serious option.
- *VAD + Whisper (no wake word):* Record everything and transcribe it all. Bad for privacy and efficiency.

**Default vs custom model:** OpenWakeWord ships with pre-trained models for common phrases ("hey jarvis", "alexa", etc.). For "hey ppt" specifically, we use the closest available model initially and train a custom model in a later phase when we need better accuracy.

---

## 2. Whisper (via faster-whisper)

**What it is:** A speech-to-text model developed by OpenAI. Given an audio recording, it outputs accurate transcribed text.

**How it works:** Whisper is a transformer-based neural network trained on 680,000 hours of labelled audio data from the internet. It uses an encoder-decoder architecture: the encoder converts the audio spectrogram into a rich representation, and the decoder generates text tokens from that representation — essentially "reading" what was said.

`faster-whisper` is a reimplementation of Whisper using the CTranslate2 inference engine, which is significantly faster than the original, especially on Apple Silicon.

**Model sizes:** Whisper comes in multiple sizes:

| Model | Parameters | VRAM | Speed | Accuracy |
|---|---|---|---|---|
| tiny | 39M | ~1GB | Fastest | Basic |
| base | 74M | ~1GB | Fast | Good |
| small | 244M | ~2GB | Medium | Better |
| medium | 769M | ~5GB | Slow | High |
| large | 1.5B | ~10GB | Slowest | Best |

We use `base.en` (English-only base model) in Phase 0. It is fast enough on Mac Mini (real-time or faster) and accurate enough for clear speech.

**Why we chose it:**
- Best open-source STT quality available
- Runs entirely offline
- Apple Silicon acceleration via Metal Performance Shaders
- Well-maintained, widely used, strong community

**Alternatives considered:**
- *Deepgram:* Cloud-based, excellent quality, but sends audio to their servers. Violates offline requirement.
- *Google Speech-to-Text:* Same issue — cloud-based.
- *Vosk:* Offline, lightweight, but noticeably worse accuracy than Whisper for English.

---

## 3. Ollama + Llama 3

**What Ollama is:** A tool for running large language models (LLMs) locally on your computer. It downloads model files, manages memory, and exposes a REST API that looks almost identical to the OpenAI API.

**What Llama 3 is:** An open-weights large language model developed by Meta. "Open-weights" means the model parameters are publicly available for download — you can run it on your own hardware without any API fees or cloud dependency.

**How LLMs work (simplified):** A large language model is trained on enormous amounts of text. Through this training, it learns the statistical patterns of language — which words tend to follow which other words, in what contexts. Given a prompt ("Hey PPT, what's on my plate today?"), it generates the most statistically likely continuation — a response.

Modern LLMs (like Llama 3) are transformer models. The key mechanism is *attention*: the model learns which parts of the input are most relevant to predicting each part of the output. This allows it to "understand" context across long texts.

**Quantisation:** A full Llama 3 7B model requires ~14GB of RAM. On a Mac Mini with 8GB RAM, this doesn't fit. *Quantisation* reduces model precision (from 16-bit floats to 4-bit integers) at a modest quality cost. A 4-bit quantised Llama 3 3B model fits in ~2GB and runs quickly on Apple Silicon.

**Why we chose Ollama + Llama 3:**
- Completely offline — no data leaves the device
- Zero API costs
- Apple Silicon GPU acceleration via Metal (Ollama supports this automatically)
- Simple REST API (drop-in replacement for OpenAI API)
- Llama 3 is among the best open-weights models available

**Alternatives considered:**
- *Claude API (Anthropic):* Best quality, but requires internet and has per-token costs. Reserved as an optional upgrade path.
- *LM Studio:* Similar to Ollama but GUI-focused. Less suitable for headless server use.
- *GPT4All:* Another local LLM runner, but less actively maintained than Ollama.

---

## 4. Piper TTS

**What it is:** A fast, offline text-to-speech system that produces natural-sounding voices. Given text, it outputs an audio file.

**How it works:** Piper uses a neural network architecture (VITS — Variational Inference with adversarial learning for end-to-end Text-to-Speech) to directly synthesise audio from text. Unlike older TTS systems that concatenated recorded phonemes, Piper generates audio end-to-end through a neural network, producing much more natural speech.

**Voice models:** Piper comes with many pre-trained voice models in multiple languages. For English, `en_US-lessac-medium` is a good balance of quality and speed. Voices vary in naturalness — the "medium" and "high" quality variants produce noticeably more natural speech than "low".

**Why we chose it:**
- Fully offline — no cloud
- Runs well on Apple Silicon
- Natural-sounding voices (not robotic)
- Simple command-line interface (pipe text in, get audio out)
- Free and open source (MIT licence)

**Alternatives considered:**
- *ElevenLabs:* Exceptionally natural voices, but cloud-based and has usage costs.
- *macOS `say` command:* Available on macOS, no install needed, but voice quality is noticeably robotic.
- *Coqui TTS:* Good quality, but the project is no longer actively maintained.

---

## 5. Python

**Why Python?** Python is the lingua franca of AI and machine learning. Every library in this stack — OpenWakeWord, faster-whisper, Ollama clients — has a first-class Python API. Python also has excellent audio libraries (PyAudio, sounddevice) and is easy to read and modify.

**Version:** Python 3.11+. f-strings, pattern matching, and type hints make code significantly cleaner than older versions.

**Virtual environment:** We use a `.venv/` virtual environment to isolate project dependencies. This prevents version conflicts with other Python projects on the same machine.

**Key libraries:**
- `sounddevice` — cross-platform audio I/O without needing PortAudio configuration
- `numpy` — audio data is handled as numpy arrays
- `requests` — HTTP calls to Ollama and Plane APIs
- `apscheduler` — reminder scheduling
- `faster-whisper` — Whisper STT
- `openwakeword` — wake word detection

---

## 6. Plane

**What it is:** An open-source project management tool — the self-hosted alternative to Jira or Linear. It provides projects, issues (tasks), cycles (sprints), modules, and analytics.

**Why it matters for PPT:** PPT's task management needs a backend. Rather than building a custom task database, we use Plane. It gives us a web UI (accessible from desktop and phone), a REST API (so PPT's voice interface can read and write tasks), and GitHub integration (so code activity connects to project tasks).

**Self-hosting:** Plane runs as a Docker Compose stack on the Mac Mini. It includes a Next.js frontend, a Django backend, PostgreSQL database, Redis cache, and a few background workers. Plane's official setup script handles all of this.

**REST API:** Plane's API uses standard REST conventions. Creating a task is a POST to `/api/v1/workspaces/{slug}/projects/{id}/issues/`. PPT's orchestrator calls this API when you say "add task X to project Y".

**Why we chose it over alternatives:**
- Full GitHub integration (issues sync, PR linking)
- Native Android app
- Self-hosted → data stays on your network
- Active development (backed by a YC-funded company)
- REST API for voice integration

---

## 7. Discord Bot

**What it is:** A bot (automated account) in Discord that can send messages, respond to slash commands, and post scheduled summaries.

**How Discord bots work:** You register a bot application on the Discord Developer Portal, add it to your server, and receive a token. Your code uses this token to authenticate with the Discord API. The bot can post messages, listen for commands, and react to events.

**Discord.py:** The Python library for building Discord bots. You define command handlers with simple decorators:

```python
@bot.slash_command(name="tasks")
async def tasks(ctx):
    open_tasks = plane.get_open_tasks()
    await ctx.respond("\n".join(t.name for t in open_tasks))
```

**Why Discord (not Slack, Telegram, or WhatsApp):**
- Already installed and used daily
- Free — no costs for bot usage
- Personal server → no company data policy concerns
- Slash commands are well-designed and easy to use
- Discord's API is robust and well-documented

---

## 8. Docker

**What it is:** A platform for building and running applications in containers. A container bundles an application with all its dependencies so it runs identically everywhere.

**Why Plane uses Docker:** Plane consists of multiple services (frontend, backend, database, workers). Coordinating these manually would be complex. Docker Compose defines all services in a single file (`docker-compose.yml`) and starts them all with one command.

**Key concepts:**
- *Image:* A template for a container. Immutable.
- *Container:* A running instance of an image. Has its own filesystem, network, and processes.
- *Docker Compose:* A tool for defining and running multi-container applications via a YAML file.
- *Volume:* Persistent storage that survives container restarts. Used for the database.

**Basic Docker commands:**
```bash
docker compose up -d      # start all services in background
docker compose down       # stop all services
docker compose ps         # show running services
docker compose logs -f    # stream logs from all services
```

---

## 9. GitHub (REST API and Webhooks)

**REST API:** GitHub exposes every action through a REST API. Listing repos, fetching issues, closing PRs — all available programmatically. Plane uses this to sync your issues and PRs.

**Webhooks:** Rather than polling the API continuously, GitHub pushes events to you. When a PR is opened, GitHub sends an HTTP POST to a URL you configure. Plane listens for these webhooks to update tasks in real time.

**GitHub → Plane integration:** When you link a Plane project to a GitHub repo, Plane registers webhooks with GitHub. New issues appear as Plane tasks. Closing a PR with "Closes #123" in the description automatically closes the linked Plane task.

---

## 10. Google Calendar API

**What it is:** Google's REST API for reading and writing calendar data.

**How it works:** You register an app in Google Cloud Console and request the `calendar.readonly` OAuth scope. Users authenticate once and grant your app permission to read their calendar. After that, your app can fetch events programmatically.

**In PPT:** The voice assistant calls the Calendar API to answer "what's on my calendar today?" and to include events in the morning briefing. This is read-only access — PPT reads events but doesn't create them (calendar management stays in Google Calendar itself).

---

## Technology Decisions Summary

| Layer | Tool | Key reason for choice |
|---|---|---|
| Wake word | OpenWakeWord | Free, offline, customisable |
| STT | faster-whisper (Whisper base.en) | Best open-source accuracy, Apple Silicon fast |
| LLM | Ollama + Llama 3 3B | Offline, no cost, Apple Silicon optimised |
| TTS | Piper TTS | Offline, natural voice, lightweight |
| Language | Python 3.11 | Ecosystem fit for AI/audio |
| Project management | Plane (self-hosted) | GitHub integration, Android app, open source |
| Notifications/bot | Discord | Already used, free, good API |
| Container runtime | Docker | Required for Plane, industry standard |
| Git | GitHub | Personal repos already there |
| Calendar | Google Calendar API | Already used |

---

*Next: [Chapter 6 — Testing →](../06-testing/README.md)*
