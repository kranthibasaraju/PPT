# PPT — The Book
### Building a Personal AI Voice Assistant from Scratch

> This documentation tells the full story of PPT — a real project built by one person, documented as a learning resource for anyone who wants to understand how modern AI systems are designed, built, and deployed.

---

## Who This Is For

- Developers who want to build something real with AI
- Anyone preparing for system design or architecture interviews
- Curious people who want to understand how voice assistants actually work under the hood
- Engineers moving into AI/ML product development

You do not need to be an expert. Every concept is explained from first principles.

---

## How to Read This

Read it like a book — start to finish — or jump to the chapter most relevant to you.

Each chapter stands alone, but they build on each other. The first time you encounter a concept, it is explained. Later chapters assume that foundation.

---

## Table of Contents

### [Chapter 1 — Product](./01-product/README.md)
*What are we building? Why? Who is it for?*
The product thinking behind PPT. What problem it solves, what it does, and how it should feel to use.

### [Chapter 2 — Architecture](./02-architecture/README.md)
*How does the system fit together?*
The big picture. How the parts connect, why we split the system across two devices, and how data flows from your voice to a spoken response.

### [Chapter 3 — Infrastructure](./03-infrastructure/README.md)
*Where does it all run?*
Hardware choices, self-hosting with Docker, networking on a local home network, and running services that never sleep.

### [Chapter 4 — Design Patterns](./04-design-patterns/README.md)
*How is the code structured?*
The software patterns that make this project clean and extensible. Pipeline, observer, strategy, and more — explained with real PPT examples.

### [Chapter 5 — Technologies](./05-technologies/README.md)
*What tools are we using and why?*
A deep dive into every technology in the stack. OpenWakeWord, Whisper, Ollama, Piper TTS, Plane, Discord — what each one is, how it works, and why we chose it over alternatives.

### [Chapter 6 — Testing](./06-testing/README.md)
*How do we know it works?*
Testing strategy for a voice assistant. How to test each layer independently, how to measure latency, and what "good enough" means for a personal project.

### [Chapter 7 — Interview Guide](./07-interview/README.md)
*What would you say in an interview?*
Key decisions made in this project, the reasoning behind them, and how to talk about them in a technical interview. Includes common system design questions and sample answers drawn from PPT.

---

## The Project at a Glance

**PPT** (Personal Project Tracker) is a personal AI voice assistant that runs 24/7 on your home hardware. Say *"Hey PPT"* and it hears you, understands you, responds out loud, and helps you manage your projects and tasks — all without sending your data to the cloud.

```
You speak → RPi4 hears → Mac Mini thinks → RPi4 speaks back
```

**Stack in one line:** OpenWakeWord + Whisper + Ollama (Llama 3) + Piper TTS + Plane + Discord bot

**Hardware:** Raspberry Pi 4 (always-on listener) + Mac Mini Apple Silicon (processing)

**Philosophy:** Own your data. Use open source. Keep it simple. Build it to learn.

---

*Started: March 2026 | Author: Rana | License: Personal / Educational*
