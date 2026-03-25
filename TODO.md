# PPT — Todo & Task Tracker

_Last updated: 2026-03-24 (v3 — Telegram, project planner, web UI added)_

---

## 🌐 Web UI — Project Planner

- [ ] **Use AI skill (stitch/image-gen) to redesign the web UI** — generate a proper visual design for the project planner dashboard, replace the hand-coded HTML with a polished output
- [ ] Make web server auto-start on Mac Mini boot (launchd plist)
- [ ] Add project status toggle (active → done) from the UI
- [ ] Add task due dates to the UI
- [ ] Show voice command history in the UI
- [ ] Send Telegram notification when a task is tapped done on mobile

---

## 🔴 Open Questions (Resolve First)

- [ ] OQ-8: Voice profile — single user (confirmed: Rana only)
- [ ] OQ-9: Persist conversation history? If yes, how long / how much?
- [ ] OQ-11: Which USB mic to buy for RPi4? (blocks hardware setup)

**Resolved from context:**
- ✅ OQ-6: Calendar — Personal Google Calendar
- ✅ OQ-10: Dashboard = Plane (self-hosted via Docker on Mac Mini)
- ✅ OQ-12: Notifications/Bot — Discord (personal server)
- ✅ OQ-13: Git — Personal GitHub account

## 🛒 Hardware to Buy (Phase 1+ only — not needed for Phase 0)

- [ ] USB microphone for RPi4 (~$10–25)
- [ ] Small USB or 3.5mm speaker for RPi4 (~$10–20)

---

## 📦 Phase 0 — Foundation (Mac Mini only, no RPi4 needed yet)

> Testing on Mac Mini as a single node — mic input and processing all on Mac Mini.
> RPi4 split comes in Phase 1 once the stack is proven.

- [ ] Confirm mic input available on Mac Mini (3.5mm headset or USB mic/headset)
- [ ] Install and test OpenWakeWord on Mac Mini
- [ ] Train / configure "Hey PPT" wake word model
- [ ] Install Whisper.cpp (Apple Silicon native build) and test with mic input
- [ ] Install Ollama on Mac Mini
- [ ] Pull and benchmark a suitable offline LLM (start with `llama3.2:3b`)
- [ ] Test full text prompt → Ollama response via CLI
- [ ] Install and test Piper TTS — confirm audio output through Mac Mini speakers
- [ ] Run all 4 layers (wake → STT → LLM → TTS) end to end on Mac Mini
- [ ] Document final stack decisions in openspec.md

**Exit gate:** All 4 layers working on Mac Mini alone. No RPi4 required yet.

---

## 🎙️ Phase 1 — Voice Loop MVP

- [ ] Build `wake_detector.py` — listens for "Hey PPT", triggers recording
- [ ] Build `stt_service.py` — records audio, transcribes with Whisper
- [ ] Build `orchestrator.py` — receives text, calls Ollama, returns response
- [ ] Build `tts_service.py` — converts LLM response to audio and plays it
- [ ] Wire all 4 services into a single runnable pipeline
- [ ] Measure end-to-end latency (target: < 5 seconds)
- [ ] Handle edge cases: silence, background noise, partial wake word
- [ ] Basic logging to file

**Exit gate:** Full voice loop working end-to-end, latency < 5s

---

## 📋 Phase 2 — Project Tracker Integration

- [ ] Design SQLite schema for projects and tasks
- [ ] Build `ppt_store.py` — CRUD for projects and tasks
- [ ] Implement intent parsing for task commands (add, update, query, delete)
- [ ] "Add task [name] to [project]" works by voice
- [ ] "What's on my plate today?" returns current tasks by voice
- [ ] "Mark [task] as done" works by voice
- [ ] Data persists across restarts
- [ ] Write basic tests for store and intent parser

**Exit gate:** Full voice-driven project/task CRUD working

---

## ⏰ Phase 3 — Reminders & Always-On

- [ ] Build reminder scheduler (cron-based or APScheduler)
- [ ] "Remind me to [X] at [time]" works by voice
- [ ] Reminder triggers audio alert at correct time
- [ ] Set up as launchd / systemd background service
- [ ] Confirm it survives Mac Mini sleep/wake cycles
- [ ] Deploy and test on Raspberry Pi 4
- [ ] Monitor uptime over 48 hours

**Exit gate:** Running as daemon, reminders firing, stable on RPi4

---

## ✨ Phase 4 — Dashboard & Polish

- [ ] Train custom "Hey PPT" wake word (improve accuracy)
- [ ] Add error recovery and auto-restart on crash
- [ ] Structured logging + log viewer
- [ ] Write user guide / usage docs

**Exit gate:** Stable, reliable, running hands-free

---

## 📱 Phase 5 — Project Dashboard (Plane)

**Tool:** Plane (open source, free — cloud at app.plane.so or self-hosted via Docker)
**Goal:** One place for all projects, accessible from phone and desktop, integrated with GitHub.

### Setup (Self-hosted on Mac Mini)
- [ ] Install Docker on Mac Mini
- [ ] Pull and run Plane via Docker Compose
- [ ] Confirm Plane is accessible on local network (Mac Mini IP)
- [ ] Install Plane Android app on phone, point to self-hosted instance
- [ ] Create workspaces for: PPT, Portfolio, mcp-server, qa-agent
- [ ] Set up project views — list, board, and spreadsheet as needed

### GitHub Integration
- [ ] Connect Plane to personal GitHub account
- [ ] Link each project to its GitHub repo
- [ ] Confirm GitHub issues sync to Plane tasks
- [ ] Confirm PR merges can close Plane tasks automatically
- [ ] Test: open issue on GitHub → appears in Plane

### Discord Integration
- [ ] Create a personal Discord server (if not already have one)
- [ ] Create a Discord bot via Discord Developer Portal
- [ ] Add bot to personal server with message + webhook permissions
- [ ] Connect Plane webhooks → Discord channel for task updates
- [ ] Build PPT Discord bot commands: `/tasks`, `/add`, `/status`, `/remind`
- [ ] Daily morning summary posted to Discord by bot
- [ ] Reminder alerts posted to Discord when due
- [ ] Set up Google Calendar integration in Plane (deadlines → calendar events)

### Voice Integration (connects back to PPT voice assistant)
- [ ] Expose Plane API to PPT orchestrator
- [ ] "What's on my plate?" pulls open tasks from Plane via API
- [ ] "Add task [X] to [project]" creates task in Plane via API
- [ ] Morning briefing includes Plane task summary

**Exit gate:** Phone app shows all projects. GitHub PRs/issues linked. Slack gets daily summary.

---

## 🔗 Phase 6 — Extended Integrations

### Calendar (Google Calendar)
- [ ] Read upcoming events by voice ("what's on my calendar today?")
- [ ] Create calendar events from PPT reminders
- [ ] Morning briefing: calendar + open tasks + reminders combined
- [ ] Plane deadlines sync to Google Calendar

### Discord Deep Integration
- [ ] `/ppt` slash command in Discord — query tasks by voice or text
- [ ] Daily standup summary posted automatically each morning
- [ ] Reminder alerts posted to Discord channel when due
- [ ] Two-way: Discord message / command creates task in Plane
- [ ] "Hey PPT" voice → response also mirrored to Discord log channel

**Exit gate:** Full daily briefing — calendar, tasks, reminders — accessible by voice, Slack, and phone.

---

## ✅ Completed

- [x] Project created and onboarded (2026-03-23)
- [x] OpenSpec written (2026-03-23)
- [x] PLAN.md written with full phase-by-phase build plan (2026-03-23)
- [x] OQ-1 resolved: Mac Mini as processing hub (2026-03-23)
- [x] OQ-2 resolved: Offline LLM via Ollama (2026-03-23)
- [x] OQ-3 resolved: OpenWakeWord (2026-03-23)
- [x] OQ-4 resolved: Wake word = "Hey PPT" (2026-03-23)
- [x] OQ-5 resolved: No assistant name for now (2026-03-23)
- [x] OQ-7 resolved: RPi4 = edge/mic node, Mac Mini = processor (2026-03-23)
- [x] Architecture decided: split node — RPi4 listens, Mac Mini processes (2026-03-23)
- [x] OQ-10 resolved: Dashboard = PWA, mobile-first, free (2026-03-23)
- [x] Phase 5 (Dashboard) and Phase 6 (Integrations: Slack, Git, Calendar) added to plan (2026-03-23)
- [x] OQ-6 resolved: Personal Google Calendar (2026-03-23)
- [x] OQ-8 resolved: Single user — Rana only (2026-03-23)
- [x] OQ-12 resolved: Personal Slack workspace (2026-03-23)
- [x] OQ-13 resolved: Personal GitHub account (2026-03-23)
- [x] Dashboard tool decided: Plane (self-hosted via Docker on Mac Mini) (2026-03-23)
- [x] Notification/bot channel decided: Discord personal server (2026-03-23)
