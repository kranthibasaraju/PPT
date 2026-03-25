# PPT — Session Progress Log

---

## Session 1 — 2026-03-23

### What We Did
First planning session for PPT (Personal Project Tracker). Went from zero to a fully documented project with a clear 6-phase build plan.

### Decisions Made (in order)

| Decision | Choice | Reason |
|---|---|---|
| Primary device | Mac Mini | Powerful, already owned, fast to iterate |
| LLM backend | Offline (Ollama) | Privacy, no API costs, works without internet |
| Wake word engine | OpenWakeWord | Free, open source, customizable |
| Wake word phrase | "Hey PPT" | Simple, project-specific |
| Assistant name | None for now | Can add later |
| Edge node (mic/listen) | RPi4 | Always-on, low power (~3W) |
| Processing hub | Mac Mini | Handles STT, LLM, TTS |
| Phase 0 testing | Mac Mini only | No extra hardware needed to start |
| Project dashboard | Plane (self-hosted Docker) | Open source, GitHub integration, Android app |
| Notifications/bot | Discord | Already installed, free, personal server |
| Git integration | Personal GitHub | Single user |
| Calendar | Personal Google Calendar | Already used |
| Users | Single — Rana only | Personal project |

### Architecture Decided
**Split node model:**
- RPi4 → always-on, listens for wake word, captures voice, plays response
- Mac Mini → processes: Whisper (STT) → Ollama (LLM) → Piper (TTS)
- Phase 0: test entire stack on Mac Mini only (no RPi4 needed yet)

### Files Created
- `README.md` — project onboarding
- `openspec.md` — full technical specification (v0.2)
- `PLAN.md` — phase-by-phase build plan (6 phases)
- `TODO.md` — all tasks by phase, resolved open questions

### Phase 0 Started (Not Completed)
- Code session started but not approved (user not present)
- Goal: install OpenWakeWord, Whisper.cpp, Ollama, Piper TTS on Mac Mini
- All 4 layers need to work independently from CLI before moving to Phase 1

### Open Questions Remaining
- OQ-9: Persist conversation history? (not blocking Phase 0)
- OQ-11: Which USB mic to buy for RPi4? (not needed until Phase 1b)

### Next Steps
1. Approve Phase 0 code session → install all tools on Mac Mini
2. Plug in a headset or mic to Mac Mini for testing
3. Run setup script, test each layer individually
4. Wire into pipeline and test full "Hey PPT" → response loop
5. When working: buy USB mic + speaker for RPi4

---

_Add new sessions below as work continues._
