# PPT — File Organizing Rules & Contribution Guide

_Last updated: 2026-03-29_

This document defines how the PPT project is structured, how to decide where new code lives, and when a sub-application is ready to graduate into its own git repository.

---

## Folder Structure Conventions

```
PPT/                        ← root monorepo (this repo)
├── src/                    ← all Python source code
│   ├── wake/               ← wake word detection (OpenWakeWord)
│   ├── stt/                ← speech-to-text (Whisper)
│   ├── tts/                ← text-to-speech (Piper)
│   ├── llm/                ← LLM client (Ollama)
│   ├── orchestrator/       ← intent routing + pipeline coordination
│   ├── projects/           ← project/task data layer (SQLite)
│   ├── integrations/       ← external API adapters (Telegram, Discord, etc.)
│   └── web/                ← local web dashboard (Flask app)
├── config/                 ← environment configs (do not commit secrets)
├── scripts/                ← setup, install, and utility scripts
├── data/                   ← local runtime data (SQLite files, logs)
├── models/                 ← downloaded model files (gitignored)
├── logs/                   ← runtime logs (gitignored)
├── tests/                  ← test suite (mirrors src/ structure)
├── docs/                   ← architecture docs, ADRs, diagrams
├── bin/                    ← executable entry points
├── PLAN.md                 ← phase-by-phase build plan
├── TODO.md                 ← task tracker (source of truth for what's next)
├── PROGRESS.md             ← session-by-session log of what was done
├── README.md               ← project overview and onboarding
└── CONTRIBUTING.md         ← you are here
```

---

## Rules for New Code

### Where does a new feature go?

| If it... | Put it in... |
|---|---|
| Is a new capability within an existing layer | Add a file inside the matching `src/` subfolder |
| Spans two layers (e.g. a new command that uses LLM + DB) | Lives in `orchestrator/` — it's the glue layer |
| Is an adapter to a new external service | `src/integrations/<service_name>/` |
| Is a standalone utility or script | `scripts/` if runnable, `src/` if imported |
| Is a config value | `config/` — never hardcode paths or secrets |
| Is a test | `tests/` mirroring the `src/` path (e.g. `tests/llm/test_ollama_client.py`) |

### Naming rules

- Python files: `snake_case.py`
- Folders / modules: `snake_case`
- Sub-repos (when graduated): `ppt-<name>` (e.g. `ppt-voice`, `ppt-llm`)
- Classes: `PascalCase`
- Constants: `UPPER_SNAKE_CASE`

### What goes in `docs/`

- Architecture Decision Records (ADRs) — one file per decision, named `adr-001-<title>.md`
- Diagrams (embed as ASCII or link to images)
- Per-phase technical write-ups

---

## When to Spin a Sub-App Into Its Own Repo

**The rule: a sub-application earns its own git repository when it meets 3 or more of the following signals.**

This is called **repo graduation**.

| Signal | What it means |
|---|---|
| 📦 Independent deployability | It can be started, stopped, and updated without touching the rest of PPT |
| 🔄 Its own release cycle | It gets updated on a different cadence than the main repo |
| 📐 Its own config / env | It needs its own `.env`, `requirements.txt`, or `Dockerfile` |
| 🌳 Deep file tree | It has grown to 5+ files or 2+ subfolders of its own |
| 🔌 Reusable by other projects | Another project (not PPT) could use it as a standalone library or service |
| 🐛 Its bugs are isolated | When it breaks, it doesn't take down everything else |
| 👤 Could have a separate contributor | You could hand it to someone else to maintain independently |

**When in doubt, keep it in the monorepo.** Only graduate when it's genuinely painful to keep co-located.

### How to graduate a sub-app

1. **Create the new repo** on GitHub: `ppt-<name>` (e.g. `github.com/rana/ppt-voice`)
2. **Copy the subfolder** into the new repo root — `git subtree split` or manual copy
3. **Add its own README**, `requirements.txt`, and `Dockerfile` (if needed)
4. **Tag v0.1.0** as the starting point
5. **Replace the subfolder** in the main PPT repo with a git submodule or a pip-installable reference
6. **Update PLAN.md and TODO.md** to track the migration
7. **Set up CI** (GitHub Actions) on the new repo — at minimum: lint + test on push

---

## Sub-Applications — Current Status & Migration Plan

These are the sub-apps that have been identified for eventual repo graduation:

| Sub-App | Current Location | New Repo | Graduation Status |
|---|---|---|---|
| `ppt-voice` | `src/wake/` + `src/stt/` + `src/tts/` | [ppt-voice](https://github.com/kranthibasaraju/ppt-voice) | 🟢 Done — v0.1.0 |
| `ppt-llm` | `src/llm/` | [ppt-llm](https://github.com/kranthibasaraju/ppt-llm) | 🟢 Done — v0.1.0 |
| `ppt-board` | `src/web/` | [ppt-board](https://github.com/kranthibasaraju/ppt-board) | 🟢 Done — v0.1.0 |
| `ppt-store` | `src/projects/` | [ppt-store](https://github.com/kranthibasaraju/ppt-store) | 🟢 Done — v0.1.0 |
| `ppt-integrations` | `src/integrations/` | [ppt-integrations](https://github.com/kranthibasaraju/ppt-integrations) | 🟢 Done — v0.1.0 |
| `ppt-panels` | part of `src/web/` (UI components) | `ppt-panels` | 🔵 Future |

**Legend:**
- 🟢 Done — graduated, main repo references it as submodule/package
- 🟡 Planned — actively being prepared for migration
- 🔵 Future — will graduate once it grows enough
- ⬜ Staying — intentionally kept in monorepo

---

## Commit Message Format

```
<type>(<scope>): <short description>

[optional body — explain the why, not the what]
```

Types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `perf`
Scopes: `voice`, `llm`, `board`, `store`, `orchestrator`, `infra`, `ci`

Examples:
```
feat(voice): add streaming TTS playback
fix(llm): handle Ollama timeout on slow hardware
docs(contributing): add repo graduation rules
chore(infra): add launchd plist for Mac Mini autostart
```

---

## When a New Project Starts

Any new project that grows beyond a proof-of-concept should follow this progression:

```
Phase 1 — Scratch (folder in an existing repo, no git history of its own)
  ↓ when it has real files and works end-to-end
Phase 2 — Module (its own subfolder with __init__.py and tests)
  ↓ when it meets 3+ graduation signals above
Phase 3 — Own Repo (git repo on GitHub, independent CI, semantic versioning)
  ↓ when it has multiple dependents or contributors
Phase 4 — Package (published to PyPI or internal registry, versioned API)
```

**Start in Phase 1. Graduate deliberately. Don't over-engineer early.**

---

_This file is the source of truth for how the PPT project is organized. Update it when rules change — don't let it drift._
