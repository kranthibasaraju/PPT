# Chapter 7 — Interview Guide
## What Would You Say in an Interview?

---

## How to Use This Chapter

This chapter prepares you to talk about PPT in technical interviews. It covers:
- The key decisions made and how to explain your reasoning
- Common system design questions this project answers
- How to frame a personal project as evidence of engineering skill

The best interview answers are grounded in real decisions you actually made, with real tradeoffs you actually considered. PPT gives you exactly that.

---

## How to Introduce the Project

A good project introduction answers three questions in 60 seconds: what it does, why you built it, and what you learned.

**Example:**

> "PPT is a personal AI voice assistant I built to run offline on home hardware — a Raspberry Pi for always-on listening and a Mac Mini for processing. Say 'Hey PPT' and it hears you, transcribes your speech using Whisper, routes the intent through a local LLM running on Ollama, and speaks back using Piper TTS. The whole pipeline runs without any cloud services.

> I built it because I wanted to understand how voice assistants actually work under the hood — not just call an API, but own the full stack. It also integrates with a self-hosted project management tool (Plane), Discord for notifications, and GitHub for linking code activity to project tasks.

> What I learned most was how to split a system across two devices based on different resource requirements, and how to design each layer for independent testability."

---

## Key Decisions and How to Defend Them

### "Why did you split the system across two devices?"

**Answer:** The two main jobs have fundamentally different resource profiles. Always-on wake word detection needs to run at ~3 watts with near-zero CPU, 24/7 without ever sleeping. STT, LLM, and TTS processing needs RAM, compute, and takes several seconds — but only triggers occasionally. Putting both on the same device forces a tradeoff: either you run a powerful device at idle most of the time (wasting power), or you run a low-power device that can't handle the ML workload. The split-node architecture matches each job to the right hardware. The Pi handles listening. The Mac Mini handles processing. They communicate over the local network via HTTP.

**Follow-up: "How do they communicate?"**
HTTP POST. The Pi detects the wake word, records the speech, and sends the audio as a multipart file upload to the Mac Mini's processing server. The Mac Mini processes, generates audio, and returns it in the response. Simple, debuggable, reliable.

### "Why offline? Why not use the OpenAI API?"

**Answer:** Three reasons. First, privacy — every interaction with a cloud API sends your speech to a third-party server. For a personal assistant that hears everything you say at home, this is unacceptable. Second, reliability — the assistant works during internet outages, which is when you most want it to work. Third, cost — API calls add up, especially for a system that might handle dozens of interactions per day. The tradeoff is model quality: a local 3B parameter model is good but not as capable as GPT-4. For personal task management and reminders, 3B is more than sufficient.

### "Why Plane instead of building your own task database?"

**Answer:** Build vs. buy is one of the most important engineering decisions. Building a task management system from scratch would take weeks, and the result would be a simple CRUD app — not a good use of time. Plane gives us a full-featured project management system with a polished UI, GitHub integration, an Android app, and a REST API — all self-hosted and free. The PPT voice layer sits on top of Plane's API. This lets us focus on the novel part of the project (the voice pipeline) rather than reimplementing solved problems.

### "Why Discord for notifications?"

**Answer:** I evaluated Slack, Telegram, and WhatsApp. Slack has good APIs but is designed for teams, not personal use. WhatsApp requires a business API account with associated costs. Telegram is excellent, but the deciding factor was simpler: I use Discord every day. The best notification system is one you already have open. Discord's bot API is well-documented, free, and supports slash commands, which gives a text-based interface to PPT when away from home.

### "How would you scale this?"

**Answer (framing):** This is a personal system deliberately designed not to scale — it's for one user on home hardware. But if I were designing it to scale:

- The wake word detector stays on the edge, but the processing hub moves to a cloud service with auto-scaling
- The Ollama instance becomes a load-balanced LLM inference cluster
- SQLite becomes PostgreSQL with connection pooling
- The Discord bot moves to a hosted service with webhook handling
- Plane's self-hosted instance moves to managed cloud infrastructure

The key insight is that the architecture is already designed for this: the processing hub is already a separate service that receives audio via HTTP. Making it a cloud endpoint is a deployment change, not an architecture change.

---

## Common System Design Questions This Project Answers

### "Design a voice assistant"

PPT is exactly this. Key points to hit:
- Wake word detection (low-power, always-on, edge)
- STT pipeline
- Intent classification and routing
- Skill system (extensible handlers for different intents)
- TTS synthesis
- Latency budget (< 5 seconds end-to-end)
- Offline vs. cloud tradeoffs

### "How would you design a system that runs on limited hardware?"

The RPi4 constraint is a real hardware limitation you solved. Key points:
- Offload heavy computation to a more powerful node
- Keep edge responsibilities minimal (wake word only)
- Design communication between nodes as simple HTTP
- Consider power draw as a first-class metric

### "How do you test a system that involves ML models?"

From Chapter 6:
- Test each layer independently with a `--test` mode
- Use pre-recorded audio fixtures for E2E tests
- Measure latency at each stage
- Accept that ML output quality is subjective — evaluate manually
- Focus automated tests on routing logic, API integration, and config

### "Walk me through an integration you built"

The Plane + GitHub + voice integration:
- PPT voice command → orchestrator → Plane REST API → task created
- GitHub webhook → Plane → task updated automatically
- Discord bot → Plane API → summary posted
- This is a web of integrations, all coordinated through Plane as the data hub

### "How do you handle failure in a distributed system?"

From PPT:
- Each service restarts automatically (launchd / systemd with KeepAlive)
- Pipeline has try/except at each stage — failure loops back to listening, not crash
- Network timeouts are handled with retries
- Logs capture failures with timestamps for debugging
- Graceful degradation: if Plane API is down, the LLM still responds conversationally

---

## Learnings Worth Mentioning

**On choosing the right tool:**
> "My first instinct was to build a custom task database. But recognising that Plane solves this problem better than I could in the time available — and exposes a clean API for the voice layer — was the right call. Knowing when to use a tool vs. build from scratch is a skill."

**On hardware constraints as design input:**
> "The RPi4's 3-watt power draw seems like a limitation, but it became a design driver. It forced a split that makes the system cleaner: the Pi is only responsible for one thing, and the Mac Mini is only responsible for one thing."

**On offline AI:**
> "Running a 3B parameter LLM locally on consumer hardware in 2026 produces responses that are genuinely useful for personal assistant tasks. The gap between local and cloud models has narrowed significantly. For well-defined tasks with short contexts, local models are often good enough."

**On latency:**
> "Breaking down the 5-second latency budget into per-stage targets — 1.5s for STT, 2s for LLM, 0.5s for TTS — made it clear where to optimise. Replacing the Whisper medium model with base.en saved 1.5 seconds. Quantising the LLM saved another second. Profiling first, optimising second."

---

## A Note on Authenticity

The most important thing in an interview is to talk about something you actually built, with decisions you actually made, for reasons you actually thought through. The details of PPT — why the Pi vs. the Mac Mini, why Plane vs. a custom DB, why offline vs. cloud — are real decisions with real tradeoffs.

Memorising answers is less useful than understanding the reasoning. If you understand why each decision was made, you can answer any follow-up question naturally.

The project documents that reasoning. When you re-read the openspec, the plan, and these chapters, you are not memorising — you are remembering something you genuinely worked through.

---

*End of The Book.*

---

**[← Back to Table of Contents](../README.md)**
