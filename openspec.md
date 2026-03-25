# PPT — Personal Project Tracker
## Open Specification Document (OpenSpec)

**Version:** 0.2
**Date:** 2026-03-23
**Status:** Phase 0 — Foundation
**Author:** Rana

---

## 1. Project Overview

**Project Name:** PPT — Personal Project Tracker
**Codename:** `ppt`
**Goal:** Build a personal AI voice assistant that runs always-on on one of the user's dedicated devices, serving as a persistent intelligent companion for project tracking, reminders, and conversational assistance.

### Vision Statement
> An ambient, always-listening AI assistant that knows your projects, understands your context, and responds naturally by voice — running locally or hybrid-cloud on hardware you already own.

---

## 2. Problem Statement

- Personal projects lack a single intelligent tracking layer
- Existing voice assistants (Siri, Google Assistant) are cloud-locked, privacy-invasive, and not customizable
- There is no persistent, context-aware AI available across devices without re-establishing context each time
- Task tracking tools require manual input; a voice-first interface eliminates friction

---

## 3. Device Options & Evaluation

| Criterion | Pixel Phone (old) | G Hub | Raspberry Pi 4 | Mac Mini |
|---|---|---|---|---|
| Always-on power draw | High (battery cycles) | Low | Low (~3-5W) | Medium (~20W idle) |
| Processing power | Medium | Low | Medium (4GB/8GB RAM) | High (Apple Silicon) |
| Microphone quality | Good (built-in) | Built-in | Requires USB mic | Requires USB mic |
| Speaker output | Good (built-in) | Built-in | Requires USB speaker | 3.5mm / USB |
| OS flexibility | Android (limited) | Proprietary | Linux (full) | macOS (full) |
| Local LLM capable | Limited | No | Yes (small models) | Yes (large models) |
| Cost to run 24/7 | Low-medium | Low | Very low | Medium |
| Developer access | Moderate | Limited | Full | Full |
| **Recommendation** | Backup / mobile UI | Not recommended | ✅ Primary option | ✅ Best performance |

### Recommendation ✅ Decided
**Architecture: Split node model**
- **RPi4** — always-on edge node: wake word detection + mic input (low power, ~3W, never sleeps)
- **Mac Mini** — processing hub: STT + LLM (Ollama) + TTS (only active when triggered)
- **Android phone** — mobile companion: push notifications + remote voice query (Phase 4)
- **Google Nest Hub** — closed ecosystem, excluded from architecture

---

## 4. Architecture

### High-Level System Diagram

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  RASPBERRY PI 4 (always-on edge node, ~3W)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  [USB Microphone]
       │
       ▼
  [OpenWakeWord]  ──── listens 24/7 for "Hey PPT"
       │
       │  (wake detected — stream audio over local network)
       ▼
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  MAC MINI (processing hub — wakes on trigger)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  [Audio Stream Receiver]
       │
       ▼
  [Whisper.cpp — STT]   converts speech to text
       │
       ▼
  [Orchestrator]        intent routing + context
       │
       ├──► [Ollama LLM]          offline, local model
       │
       ├──► [Skill Router]
       │         ├── Reminders & Scheduler
       │         ├── Project Tracker (PPT store)
       │         └── General Q&A
       │
       ▼
  [Piper TTS]           text → speech audio
       │
       ▼
  [Audio → RPi4]        streams response back
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  RASPBERRY PI 4 (plays response)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  [Speaker Output]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ANDROID PHONE (Phase 4)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  [Push notifications + remote voice query]
```

### Core Services

| Service | Role | Language |
|---|---|---|
| `wake_detector` | Always-on wake word listener | Python |
| `stt_service` | Convert audio to text | Python |
| `orchestrator` | Route intent, call LLM | Python |
| `ppt_store` | Project & task data layer | SQLite / JSON |
| `tts_service` | Convert response to audio | Python |
| `web_ui` | Optional browser dashboard | Next.js or plain HTML |

---

## 5. Core Capabilities

### 5.1 Voice Interface (SHALL)
- SHALL detect a configurable wake word without cloud dependency
- SHALL transcribe speech to text within 2 seconds on target hardware
- SHALL synthesize and play back responses within 3 seconds of transcription
- SHALL support push-to-talk as a fallback to wake word

### 5.2 Project Tracking (SHALL)
- SHALL maintain a persistent list of projects and tasks
- SHALL allow voice commands to create, update, and query tasks
- SHALL support project status (active, paused, completed)
- SHALL store all data locally

### 5.3 Reminders & Scheduling (SHALL)
- SHALL set time-based reminders by voice
- SHALL announce reminders when due
- SHALL integrate with macOS Calendar or a local calendar store

### 5.4 Conversational AI (SHOULD)
- SHOULD retain short-term conversation context (last N turns)
- SHOULD summarize project status on request
- SHOULD answer general questions via LLM

### 5.5 Extensibility (COULD)
- COULD support custom skill plugins
- COULD integrate with smart home (HomeKit, Home Assistant)
- COULD sync state to mobile (Pixel companion app)

---

## 6. Technology Stack

### 6.1 Wake Word Detection

| Option | Offline | Custom Wake Word | Ease |
|---|---|---|---|
| **Porcupine (Picovoice)** | ✅ | ✅ (paid) | High |
| **OpenWakeWord** | ✅ | ✅ (free) | Medium |
| **Snowboy** (deprecated) | ✅ | ✅ | Low |

**Recommendation:** OpenWakeWord (free, open-source, customizable)

### 6.2 Speech-to-Text

| Option | Offline | Quality | Speed | Cost |
|---|---|---|---|---|
| **Whisper (local)** | ✅ | High | Medium | Free |
| **Whisper.cpp** | ✅ | High | Fast (ARM) | Free |
| **Deepgram** | ❌ | Very High | Very Fast | ~$0.0043/min |
| **Google STT** | ❌ | Very High | Fast | ~$0.006/min |

**Recommendation:** Whisper.cpp for offline (RPi4), Deepgram for Mac Mini (quality)

### 6.3 LLM Backend

| Option | Offline | Quality | Cost | Notes |
|---|---|---|---|---|
| **Claude API** | ❌ | Best | Per token | Best for reasoning |
| **Ollama (local)** | ✅ | Good | Free | Llama 3 / Mistral |
| **LM Studio** | ✅ | Good | Free | GUI-friendly |

**Recommendation:** Claude API primary, Ollama fallback for offline mode

### 6.4 Text-to-Speech

| Option | Offline | Natural | Latency |
|---|---|---|---|
| **Piper TTS** | ✅ | Good | Low |
| **macOS `say`** | ✅ | Medium | Very Low |
| **ElevenLabs** | ❌ | Excellent | Medium |
| **Coqui TTS** | ✅ | Good | Medium |

**Recommendation:** Piper TTS (offline, fast, good quality), ElevenLabs for premium voices

### 6.5 Data Store

| Option | Use Case |
|---|---|
| **SQLite** | Projects, tasks, reminders |
| **JSON flat files** | Config, skill definitions |
| **Chroma / FAISS** | Long-term memory / embeddings (future) |

---

## 7. Development Phases

### Phase 0 — Foundation (Device & Stack Decision)
**Goal:** Lock in hardware and software stack
**Exit Criteria:**
- [ ] Primary device selected (Mac Mini vs RPi4)
- [ ] Wake word engine tested and working
- [ ] STT producing accurate transcription from mic
- [ ] LLM responding to text input via CLI

**Estimated Duration:** 1-2 weeks

---

### Phase 1 — Voice Loop MVP
**Goal:** End-to-end wake → hear → think → speak
**Exit Criteria:**
- [ ] Wake word activates recording
- [ ] STT transcribes correctly
- [ ] LLM generates response
- [ ] TTS speaks response
- [ ] Full loop < 5 seconds end-to-end

**Estimated Duration:** 2-3 weeks

---

### Phase 2 — Project Tracker Integration
**Goal:** Voice-driven project and task management
**Exit Criteria:**
- [ ] "Add task [name] to [project]" works by voice
- [ ] "What's on my plate today?" returns current tasks
- [ ] Data persists across restarts
- [ ] Basic CRUD by voice for projects and tasks

**Estimated Duration:** 2-3 weeks

---

### Phase 3 — Reminders & Always-On
**Goal:** Persistent background service with scheduled reminders
**Exit Criteria:**
- [ ] Runs as a background daemon / launchd service
- [ ] Reminders trigger audio alerts at correct time
- [ ] Survives sleep/wake cycles on Mac Mini
- [ ] Deployed and stable on RPi4

**Estimated Duration:** 2-3 weeks

---

### Phase 4 — Polish & Mobile Companion
**Goal:** Reliability, UI, and mobile access
**Exit Criteria:**
- [ ] Web dashboard showing project status
- [ ] Push notifications to Pixel phone
- [ ] Custom wake word trained
- [ ] Logging and error recovery

**Estimated Duration:** 3-4 weeks

---

## 8. Open Questions

| ID | Question | Priority | Status |
|---|---|---|---|
| OQ-1 | Which device is Phase 1 primary: Mac Mini or RPi4? | 🔴 Critical | ✅ **Mac Mini** |
| OQ-2 | Offline-only vs hybrid-cloud (Claude API)? | 🔴 Critical | ✅ **Offline (Ollama)** |
| OQ-3 | Which wake word engine: OpenWakeWord or Porcupine? | 🔴 Critical | ✅ **OpenWakeWord** |
| OQ-4 | What is the primary wake word phrase? | 🟡 High | ✅ **"Hey PPT"** |
| OQ-5 | Should the assistant have a name/persona? | 🟡 High | ✅ **No name for now** |
| OQ-6 | Calendar integration: macOS Calendar, Google Cal, or local? | 🟡 High | Open |
| OQ-7 | Data sync between Mac Mini and RPi4? | 🟠 Medium | ✅ **RPi4 = edge/mic node, Mac Mini = processor. No full sync needed.** |
| OQ-11 | USB mic for RPi4 — which one to buy? | 🔴 Critical | Open |
| OQ-8 | Voice profile: single user or multi-user? | 🟠 Medium | Open |
| OQ-9 | Should conversation history be persisted? If so, how long? | 🟠 Medium | Open |
| OQ-10 | Mobile companion: native app or PWA? | 🟢 Low | Open |

---

## 9. Non-Goals (v1)

- Not a smart home hub (integration is a stretch goal)
- Not a multi-user system in v1
- Not a replacement for a full calendar app
- No cloud data storage of personal content

---

## 10. Success Metrics

| Metric | Target |
|---|---|
| Wake word false positive rate | < 1 per hour |
| End-to-end response latency | < 5 seconds |
| STT word error rate | < 10% |
| Uptime (always-on device) | > 99% daily |
| Task retrieval accuracy | > 95% |

---

## 11. References

- [OpenWakeWord](https://github.com/dscripka/openWakeWord)
- [Whisper.cpp](https://github.com/ggerganov/whisper.cpp)
- [Piper TTS](https://github.com/rhasspy/piper)
- [Ollama](https://ollama.com)
- [Picovoice Porcupine](https://picovoice.ai/platform/porcupine/)
- [Claude API Docs](https://docs.anthropic.com)

---

*This document is a living spec. Update version and date with each significant revision.*
