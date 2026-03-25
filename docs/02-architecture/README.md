# Chapter 2 — Architecture
## How Does the System Fit Together?

---

## What Architecture Means

Architecture is the set of decisions that are hard to change later. It is the skeleton of your system — the big choices about how components are divided, how they communicate, and where they run.

Good architecture makes it easy to build, test, change, and scale individual parts without touching everything else. Bad architecture means changing one thing breaks five others.

Before writing code, it is worth spending time on architecture. The cost of a bad architecture decision compounds over time. The cost of a good one disappears into the background.

---

## The Core Insight: One Problem, Two Devices

The central architectural decision in PPT is to split the system across two devices.

**Why two devices?** Because the two main jobs of PPT have completely different requirements.

The first job is **always-on listening**: sitting quietly, consuming almost no power, waiting for a wake word. This needs to run 24/7, never sleeping, never restarting. It doesn't need to be fast or powerful — it just needs to be always there.

The second job is **processing**: when the wake word fires, transcribe speech, run a language model, synthesise a voice response. This needs power and RAM. It takes a few seconds. But it only happens when triggered.

If you put both jobs on the same device, you have a conflict: a powerful device sitting idle 99% of the time (wasting power), or a low-power device struggling to run a language model.

The solution is to separate them:

- **Raspberry Pi 4** handles the always-on listening. It draws ~3 watts, runs cool and quiet, and never needs to sleep.
- **Mac Mini** handles the processing. It only activates when the Pi wakes it. It has the RAM and CPU to run Ollama and Whisper quickly.

This is the **split-node** architecture.

---

## System Diagram

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  EDGE NODE — Raspberry Pi 4 (~3W)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  USB Mic  →  [OpenWakeWord]
                    │
            wake detected
                    │
              stream audio
                    │
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  PROCESSING HUB — Mac Mini
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  receive audio
       │
  [Whisper STT]  →  text
       │
  [Orchestrator]
       │
  ┌────┴────────────────┐
  │                     │
[Ollama LLM]    [Skill Router]
                     │
              ┌──────┴──────┐
          [Tasks]      [Reminders]

  response text
       │
  [Piper TTS]  →  audio
       │
  stream audio back
       │
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  EDGE NODE — Raspberry Pi 4
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  receive audio  →  USB Speaker
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  MOBILE — Android Phone
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Plane app + Discord notifications
```

---

## The Four Layers

The audio pipeline has four distinct layers. Each is a separate concern, independently testable, and swappable.

### Layer 1 — Wake Word Detection

**What it does:** Listens to the microphone continuously and detects the phrase "Hey PPT". Everything else it hears, it ignores.

**Technology:** OpenWakeWord — an open-source library that runs a small neural network on short windows of audio. It does not record or transcribe anything until the wake word fires.

**Why this matters:** Wake word detection must be extremely efficient. It runs 24/7 on the Pi, so it must consume almost no CPU. OpenWakeWord is specifically designed for this — it's fast, lightweight, and runs entirely offline.

### Layer 2 — Speech-to-Text (STT)

**What it does:** After the wake word fires, record the following speech and convert it to text.

**Technology:** Whisper (via `faster-whisper`) — OpenAI's speech recognition model, running locally. The `base.en` model is fast and accurate for English.

**Why this matters:** Transcription quality directly determines how well PPT understands you. Whisper is among the best open-source STT models available, and it runs on Apple Silicon very quickly.

### Layer 3 — Language Model (LLM)

**What it does:** Takes the transcribed text, understands the intent, generates a response.

**Technology:** Ollama running Llama 3 (3B parameter model). Ollama is a tool for running large language models locally. It exposes a REST API that looks just like the OpenAI API.

**Why this matters:** The LLM is the "brain" of PPT. It decides whether your input is a question, a task command, a reminder request, or something else. It generates natural language responses. Running it locally means no API costs, no latency from network round-trips, and complete privacy.

### Layer 4 — Text-to-Speech (TTS)

**What it does:** Converts the LLM's text response into audio and plays it through the speaker.

**Technology:** Piper TTS — a fast, offline text-to-speech engine with natural-sounding voices.

**Why this matters:** The voice is the personality. A robotic voice makes the assistant feel mechanical. Piper produces voices that are natural enough that you don't notice the synthesis. It runs entirely offline and is very fast on Apple Silicon.

---

## The Orchestrator

Between STT and TTS sits the orchestrator — the decision-making layer.

The orchestrator's job is to take transcribed text and decide what to do with it. Not everything you say to PPT is a question for the LLM. Some things are commands: "add task X to project Y". Some things are requests to a skill: "remind me at 3pm". Some things are general questions that the LLM handles directly.

The orchestrator routes your request to the right handler:

```
transcribed text
       │
   [orchestrator]
       │
   ┌───┴─────────────────────┐
   │            │            │
[LLM chat]  [Task skill]  [Reminder skill]
   │            │            │
   └────────────┴────────────┘
                │
          response text
```

This pattern — called the **skill router** — is how most voice assistants work internally. Siri routes "set a timer" differently from "what is the capital of France." PPT does the same thing at a smaller scale.

---

## Data Flow: A Complete Example

Here is what happens when you say "Hey PPT, add task write tests to the mcp-server project":

1. RPi4's mic captures audio continuously
2. OpenWakeWord detects "Hey PPT" (takes ~50ms)
3. RPi4 starts recording your voice
4. You say "add task write tests to the mcp-server project"
5. After silence is detected, recording stops
6. Audio is sent to Mac Mini via HTTP (local network, ~1ms latency)
7. Whisper transcribes the audio → "add task write tests to the mcp-server project"
8. Orchestrator receives the text
9. Orchestrator identifies this as a task command (pattern: "add task X to project Y")
10. Task skill extracts: task="write tests", project="mcp-server"
11. Plane API is called: POST /api/v1/issues/ with task details
12. Plane confirms: task created
13. Orchestrator generates response: "Done. Task 'write tests' added to mcp-server."
14. Piper TTS converts response to audio
15. Audio is streamed back to RPi4
16. Speaker plays: "Done. Task 'write tests' added to mcp-server."

Total time from wake word to spoken response: under 5 seconds.

---

## Phase 0 Architecture (Single Node)

During Phase 0, we run everything on the Mac Mini. There is no RPi4 in the loop. The Mac Mini is both the edge node and the processing hub.

```
Mac Mini mic → [all 4 layers] → Mac Mini speaker
```

This simplifies development enormously. We can test and iterate on the Mac Mini without dealing with network communication between two devices. Once the full pipeline works on a single machine, we split it.

---

## Component Boundaries

Good architecture has clear boundaries between components. Each component:
- Has one job
- Receives a well-defined input
- Produces a well-defined output
- Can be tested independently
- Can be replaced without changing others

In PPT:

| Component | Input | Output |
|---|---|---|
| Wake word detector | raw audio (continuous) | wake event + recorded speech |
| Transcriber | audio (wav) | text string |
| Orchestrator | text string | response text + action |
| LLM client | prompt text | response text |
| TTS speaker | text string | audio (plays via speaker) |
| Task skill | parsed intent | Plane API call + confirmation |

---

## Integrations (Phases 5–6)

Beyond the voice pipeline, PPT integrates with external systems:

**Plane** — open-source project management. PPT's task commands read and write to Plane via its REST API. Plane also connects to GitHub, so issues and PRs appear as tasks automatically.

**Discord** — notification and bot channel. A Discord bot (running on Mac Mini) posts daily summaries, reminder alerts, and receives slash commands. This gives phone access to PPT's data without building a mobile app.

**Google Calendar** — read-only integration. PPT reads calendar events and includes them in morning briefings and voice queries.

These integrations are loosely coupled — they connect via APIs and can be added or removed independently.

---

## What Makes This Architecture Good

**Separation of concerns.** Each layer does one thing. Changing the LLM model doesn't touch the wake word detector. Changing the TTS voice doesn't touch the task skill.

**Testability.** Because inputs and outputs are well-defined, every component can be tested with a simple test mode flag.

**Resilience.** If the LLM is slow, only Layer 3 is slow. If Discord is down, the voice interface still works.

**Privacy by design.** No data ever leaves the local network. The only external calls are to Plane (self-hosted), Discord (notifications only), and Google Calendar (read-only).

**Extensibility.** Adding a new skill — say, a weather query — means adding one handler in the orchestrator and routing one new intent pattern. Nothing else changes.

---

*Next: [Chapter 3 — Infrastructure →](../03-infrastructure/README.md)*
