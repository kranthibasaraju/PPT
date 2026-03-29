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

This is the **root monorepo**. Sub-applications graduate to their own repos as they grow — see [CONTRIBUTING.md](./CONTRIBUTING.md) for the graduation rules.

```
PPT/                        ← root monorepo
├── src/
│   ├── wake/               ← wake word detection       → will become: ppt-voice
│   ├── stt/                ← speech-to-text            → will become: ppt-voice
│   ├── tts/                ← text-to-speech            → will become: ppt-voice
│   ├── llm/                ← LLM client (Ollama)       → will become: ppt-llm
│   ├── orchestrator/       ← intent routing + pipeline ← stays in core
│   ├── projects/           ← project/task data layer   → will become: ppt-store
│   ├── integrations/       ← external API adapters
│   └── web/                ← local web dashboard       → will become: ppt-board
├── config/                 ← configuration files
├── scripts/                ← setup and utility scripts
├── tests/                  ← test suite (mirrors src/)
└── docs/                   ← architecture docs and ADRs
```

### Sub-App Repos

| Repo | Contents | Status |
|---|---|---|
| [`ppt-voice`](https://github.com/kranthibasaraju/ppt-voice) | wake + stt + tts | 🟢 Graduated |
| [`ppt-llm`](https://github.com/kranthibasaraju/ppt-llm) | Ollama client | 🟢 Graduated |
| [`ppt-board`](https://github.com/kranthibasaraju/ppt-board) | web dashboard | 🟢 Graduated |
| [`ppt-store`](https://github.com/kranthibasaraju/ppt-store) | project/task data layer | 🟢 Graduated |
| [`ppt-integrations`](https://github.com/kranthibasaraju/ppt-integrations) | Telegram bot + commands | 🟢 Graduated |
| `ppt-panels` | UI components | 🔵 Future |

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
- [File Organizing Rules & Repo Graduation →](./CONTRIBUTING.md)
- [Task Tracker →](./TODO.md)
- [Build Plan →](./PLAN.md)

---

## Contact

Personal project — Rana
