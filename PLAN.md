# PPT — Detailed Build Plan

_Last updated: 2026-03-23_

---

## How This Works (Simple Version)

1. RPi4 sits in your room, always powered, always listening through a USB mic
2. You say **"Hey PPT"**
3. RPi4 catches the wake word and streams your voice to the Mac Mini over WiFi
4. Mac Mini turns your speech into text (Whisper), thinks about it (Ollama), speaks back (Piper TTS)
5. Audio response streams back to RPi4's speaker
6. Done — you got your answer, Mac Mini goes back to idle

The Mac Mini does all the heavy work. The RPi4 just listens and passes things along. Low power, always responsive.

---

## What You Need to Buy

| Item | Purpose | Estimated Cost |
|---|---|---|
| USB microphone (e.g. USB desk mic) | Audio input for RPi4 | $10–25 |
| Small USB speaker or 3.5mm speaker | Audio output on RPi4 | $10–20 |
| MicroSD card (32GB+) if not already set up | RPi4 OS | $8–12 |

Everything else you already have.

---

## Phase 0 — Get the Tools Working (Mac Mini only)

**Goal:** Prove each piece works on Mac Mini as a single node. No RPi4, no extra hardware. Use whatever mic input is available on the Mac Mini (3.5mm headset, USB mic, or USB-C adapter with a mic). Once the stack is proven here, the RPi4 gets added in Phase 1 as the dedicated edge node.

### Step 1 — Install Ollama and pick a model
- Install Ollama from ollama.com (one command)
- Pull a model: start with `llama3.2:3b` (fast, fits in 4GB RAM easily)
- Test: type a question in terminal, get an answer
- Try `mistral:7b` if you want better quality (needs more RAM)

### Step 2 — Install and test Whisper
- Install `whisper.cpp` (native Apple Silicon build = very fast)
- Record a 10-second audio clip, run it through Whisper
- Confirm it transcribes correctly

### Step 3 — Install and test Piper TTS
- Install Piper (offline TTS engine)
- Download a voice model (Jenny or lessac-medium are good)
- Test: pipe a sentence in, hear it spoken back

### Step 4 — Test OpenWakeWord on RPi4
- Flash Raspberry Pi OS Lite on the RPi4
- Plug in USB mic
- Install OpenWakeWord (Python)
- Run the default "hey jarvis" demo, rename trigger to "hey ppt"
- Confirm it detects reliably, ignores background noise

**Phase 0 done when:** All 4 tools work independently from the command line.

---

## Phase 1 — Wire the Voice Loop Together

**Goal:** Full end-to-end: say something → hear a response.

### 1a — Single node (Mac Mini only, Phase 0 carry-over)
```
Mac Mini mic → [OpenWakeWord] → [Whisper] → [Ollama] → [Piper] → Mac Mini speaker
```
Wire all 4 services into a single pipeline running locally on Mac Mini.

### 1b — Split node (once RPi4 mic + speaker are available)
```
RPi4 mic → [OpenWakeWord detects] → streams audio → Mac Mini
Mac Mini → [Whisper transcribes] → [Ollama responds] → [Piper speaks]
Mac Mini → streams audio back → RPi4 speaker
```

### Steps (1a)
1. Write `listener.py` — runs OpenWakeWord on Mac Mini mic, records speech after wake
2. Write `processor.py` — Whisper → Ollama → Piper, all local
3. Wire into single runnable pipeline
4. Test: "Hey PPT, what's 2 plus 2" → hear "4" back
5. Measure latency — target under 5 seconds

### Steps (1b — RPi4 migration)
1. Buy USB mic + speaker for RPi4
2. Move `listener.py` to RPi4, update to stream audio to Mac Mini via HTTP/socket
3. Update `processor.py` to receive audio, process, stream response back to RPi4
4. Write `player.py` on RPi4 — receives audio, plays through speaker
5. Test the full split loop

**Phase 1 done when (1a):** Voice loop works on Mac Mini alone.
**Phase 1 done when (1b):** RPi4 listens, Mac Mini processes, RPi4 speaks.

---

## Phase 2 — Project & Task Tracking

**Goal:** PPT actually knows about your projects and tasks.

### Data model (simple)
```
Project: id, name, status (active/paused/done), created_at
Task:    id, project_id, name, status (todo/done), due_date, created_at
```

### Voice commands to support
| You say | What happens |
|---|---|
| "Add task [name] to [project]" | Creates task in DB |
| "What's on my plate?" | Lists active tasks |
| "What's the status of [project]?" | Summarizes project |
| "Mark [task] as done" | Updates task status |
| "Create a new project called [name]" | Creates project |
| "Show all my projects" | Lists all projects |

### Steps
1. Create SQLite database with Project + Task tables
2. Write simple intent parser — regex or LLM-based to extract command + entities
3. Write `ppt_store.py` — CRUD functions for projects and tasks
4. Connect orchestrator to store — when intent is task-related, hit the store
5. Test all 6 voice commands

**Phase 2 done when:** You can manage your projects by voice and data survives restarts.

---

## Phase 3 — Reminders & Always-On Service

**Goal:** PPT runs in the background, reminds you of things, never needs to be manually started.

### Reminder voice commands
| You say | What happens |
|---|---|
| "Remind me to [X] at [time]" | Sets a reminder |
| "What reminders do I have?" | Lists upcoming reminders |
| "Cancel my [X] reminder" | Deletes reminder |

### Always-on setup
- **Mac Mini:** Set up as a `launchd` service — starts on boot, restarts if it crashes
- **RPi4:** Set up as `systemd` service — starts on boot, restarts if it crashes
- Both devices should auto-reconnect if WiFi drops

### Steps
1. Build reminder scheduler using Python APScheduler
2. Implement "remind me" intent + natural language time parsing
3. Trigger audio alert through speaker when reminder fires
4. Package Mac Mini processor as a launchd plist
5. Package RPi4 listener as a systemd service
6. Test reboot on both devices — confirm services restart

**Phase 3 done when:** Both devices boot up and PPT works with no manual intervention. Reminders fire on time.

---

## Phase 4 — Android Phone Companion

**Goal:** Get PPT notifications and updates on your phone. Optional remote voice.

### What the phone does
- Receives push notifications when reminders fire
- Shows daily project summary in the morning
- Access all projects and tasks via the Plane app

### Steps
1. Install the Plane Android app — connects to your Plane workspace, shows all projects and tasks
2. Set up Plane webhooks → Slack for daily summaries
3. Optional: ntfy.sh for additional push notifications from the PPT voice assistant
4. (Optional) WO Mic app on Android — phone becomes a remote mic when away from home

**Phase 4 done when:** Phone gets notified when a reminder fires, and the Plane app shows all projects and tasks.

---

## Phase 5 — Plane Project Dashboard

**Goal:** Use Plane (open source, free) as the project hub — connected to GitHub, phone, and voice.

### What is Plane?
Plane is the open source alternative to Jira/Linear. You can use it free at app.plane.so (cloud, no setup) or self-host via Docker on your Mac Mini. It has a real Android app and deep GitHub integration.

### Setup — Self-hosted on Mac Mini
- Install Docker on Mac Mini
- Run Plane via Docker Compose (official Plane self-host setup — one command)
- Access Plane from any device on your home network via Mac Mini's local IP
- Install the Plane Android app and point it to your self-hosted URL

### GitHub integration
- Connect your GitHub account in Plane settings
- Link each project (Portfolio, mcp-server, qa-agent, PPT) to its repo
- GitHub issues and PRs sync automatically as Plane tasks
- PR merge → closes linked Plane task

### Voice integration
- PPT voice assistant talks to Plane via the Plane REST API
- "What's on my plate?" → fetches open tasks from Plane
- "Add task [X] to [project]" → creates task in Plane
- Morning briefing pulls from Plane + Google Calendar

**Phase 5 done when:** Phone app shows all projects. GitHub linked. Voice can query and update Plane.

---

## Remaining Decisions to Make

| Decision | Why It Matters |
|---|---|
| Which USB mic to buy for RPi4 | Blocks Phase 0 hardware setup |
| Conversation memory — session only or persisted? | Affects how the LLM maintains context |

## Key Decisions Locked

| Decision | Choice |
|---|---|
| Project dashboard tool | Plane (self-hosted via Docker on Mac Mini) |
| Phone notifications & bot | Discord (personal server) |
| Git platform | Personal GitHub |
| Calendar | Personal Google Calendar |
| User | Single user — Rana |

---

## Tech Stack Summary

| Layer | Tool | Where |
|---|---|---|
| Wake word | OpenWakeWord | RPi4 |
| Mic capture | PyAudio / sounddevice | RPi4 |
| Audio transport | HTTP / WebSocket | Local WiFi |
| Speech to text | Whisper.cpp | Mac Mini |
| LLM | Ollama (Llama 3 / Mistral) | Mac Mini |
| Text to speech | Piper TTS | Mac Mini |
| Data store | SQLite (voice) + Plane (projects) | Mac Mini |
| Scheduler | APScheduler | Mac Mini |
| Project dashboard | Plane (self-hosted Docker) | Mac Mini |
| Bot & notifications | Discord bot | Mac Mini → Phone |
| Git integration | GitHub + Plane connector | Cloud |
| Calendar | Google Calendar API | Cloud |
| Container runtime | Docker | Mac Mini |
| Language | Python 3.11+ | Both devices |

---

_This plan is intentionally simple. Each phase has one clear goal. Build, test, move on._
