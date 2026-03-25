# PPT — Personal Project Tracker

> An always-on personal AI voice assistant for project tracking, reminders, and conversational assistance.

## Status: 🟢 Phase 0 — Foundation

**Phase:** Foundation setup
**Started:** 2026-03-23
**Primary Device:** Mac Mini (Apple Silicon)
**LLM:** Offline via Ollama
**Wake Word:** "Hey PPT"

---

## What Is This?

PPT is a personal AI voice assistant designed to run 24/7 on a dedicated home device. You talk to it, it tracks your projects, sets reminders, answers questions, and helps you stay on top of things — without requiring a phone in your hand.

---

## Project Structure

```
PPT/
├── README.md          ← You are here
├── openspec.md        ← Full technical specification
├── src/               ← Source code (Phase 1+)
│   ├── wake/          ← Wake word detection
│   ├── stt/           ← Speech-to-text
│   ├── orchestrator/  ← Intent routing + LLM
│   ├── tts/           ← Text-to-speech
│   └── store/         ← Project/task data layer
├── config/            ← Configuration files
├── scripts/           ← Setup and utility scripts
└── docs/              ← Additional documentation
```

---

## Decisions Locked ✅

| Decision | Choice |
|---|---|
| Primary device | Mac Mini (Apple Silicon) |
| LLM backend | Offline — Ollama |
| Wake word engine | OpenWakeWord |
| Wake word phrase | "Hey PPT" |
| Assistant name | None (for now) |

Remaining open questions tracked in `openspec.md` Section 8.

---

## Target Hardware

| Device | Role |
|---|---|
| Raspberry Pi 4 | Always-on edge node — wake word + mic + speaker |
| Mac Mini (Apple Silicon) | Processing hub — STT, Ollama LLM, TTS |
| Android Phone | Mobile companion — push notifications (Phase 4) |
| Google Nest Hub | Not used (closed ecosystem) |

---

## Quick Links

- [Full Specification →](./openspec.md)

---

## Contact

Personal project — Rana
