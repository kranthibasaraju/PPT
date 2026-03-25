# Chapter 1 — Product
## What Are We Building, and Why?

---

## The Problem

Most people who work on personal projects have the same problem: things fall through the cracks.

You start a project with energy and momentum. Then life happens. You context-switch. A week later you can't remember where you left off. You have tasks scattered across sticky notes, Notion pages, GitHub issues, and your own memory. You set a reminder but miss it because your phone was across the room.

What's missing is something that *just knows* — something always present, always listening, that can tell you where you are, what you need to do next, and remind you when something is due. Not an app you have to open. Not a service that stores your thoughts on someone else's server. Something that lives in your home, runs on your hardware, and speaks to you like a colleague.

That is PPT.

---

## The Vision

PPT is a personal AI voice assistant designed for one person: its owner.

It lives on a small device in your home — a Raspberry Pi sitting on your desk, plugged in and always on. It listens for its wake word. When you speak to it, it responds out loud. It knows your projects. It remembers your tasks. It tells you what's on your calendar. It reminds you when something is due.

It is not Siri. It is not Alexa. It is not Google Assistant. Those are cloud products built for millions of people and optimised for the lowest common denominator. PPT is built for *you*, runs on *your* hardware, and keeps your data *on your network*.

---

## What PPT Does

### Core capabilities

**Voice interface.** PPT listens for the wake word "Hey PPT". When triggered, it records your speech, converts it to text, sends it to a local language model, and speaks the response back. No cloud. No latency from round-trips to a server thousands of miles away.

**Project tracking.** PPT knows about your projects. You can ask "what's on my plate today?" and get a summary of your open tasks. You can say "add task write the README to the portfolio project" and it will create that task. All project data is managed through Plane, an open-source project management tool running on your Mac Mini.

**Reminders.** Say "remind me to call the bank at 3pm" and PPT sets a reminder. When 3pm arrives, it speaks the reminder out loud wherever you are in the room. No need to pick up your phone.

**Conversational AI.** Beyond tasks and reminders, PPT is a general-purpose AI assistant. Ask it anything — explain a concept, help you draft something, think through a problem. It uses a local language model (Llama 3 via Ollama) so the conversation stays private.

**Discord integration.** Everything PPT knows is also available through Discord. Your daily morning summary arrives in a Discord channel. Reminders send Discord notifications. You can query your tasks from your phone by typing in Discord even when you're not home.

**GitHub integration.** PPT connects to your GitHub repos through Plane. New issues and pull requests automatically appear as tasks. When a PR is merged, the linked task closes. Your code activity and your project tracker stay in sync.

---

## Who Is the User?

PPT is built for one specific user: Rana.

This is intentional. The strongest products are built for a real, specific person with real, specific needs — not for a hypothetical average user. When you know exactly who you're building for, every decision becomes clearer.

Rana is a developer who works on multiple personal projects simultaneously. Rana works from home. Rana wants hands-free access to project information. Rana values privacy and prefers not to depend on cloud services for personal data. Rana has a Mac Mini, a Raspberry Pi 4, and an Android phone.

Every design decision in PPT flows from this profile.

---

## How It Should Feel

Good products have a feeling. Before writing a line of code, it is worth articulating what that feeling should be.

PPT should feel like a **knowledgeable colleague who is always in the room**. When you ask it something, it answers promptly and concisely. It doesn't waste your time. It doesn't need to be reminded of context from five minutes ago. It feels present without being intrusive.

Specific qualities:
- **Fast.** Response within 5 seconds of finishing your sentence.
- **Reliable.** Works every time. Doesn't need to be restarted. Doesn't forget state between sessions.
- **Honest.** If it doesn't know something, it says so. It doesn't make things up.
- **Minimal.** It doesn't speak unless spoken to. It doesn't interrupt. It doesn't add unnecessary filler.

---

## What PPT Is Not

Defining what a product is *not* is just as important as defining what it is.

PPT is not a smart home hub. It won't control your lights or your thermostat (though that could be added later).

PPT is not a team tool. It is built for one person and doesn't need access control, permissions, or multi-user support.

PPT is not a replacement for your calendar app. It reads your calendar and speaks events, but you still manage your calendar in Google Calendar.

PPT is not a mobile app. It runs on home hardware. When you leave the house, Discord carries the notifications.

---

## Phases of the Product

PPT is built in phases. Each phase adds capability without breaking what came before.

**Phase 0 — Foundation:** Get all the tools working. Prove the stack.

**Phase 1 — Voice Loop:** Full end-to-end voice: wake word → hear → think → speak.

**Phase 2 — Project Tracking:** Voice commands that create, update, and query tasks.

**Phase 3 — Always-On Service:** Runs in the background, restarts automatically, survives reboots.

**Phase 4 — Phone Companion:** Plane app on Android, Discord notifications on the go.

**Phase 5 — Plane Dashboard:** Self-hosted Plane with GitHub integration and phone access.

**Phase 6 — Full Integrations:** Google Calendar, Discord bot commands, extended voice skills.

Each phase has a clear exit gate: a thing you can do or say that proves the phase is complete. This prevents scope creep and keeps progress measurable.

---

## The Deeper Purpose

This project is also a learning exercise. Every technology choice, every architectural decision, every design pattern is an opportunity to understand something deeply rather than just use it.

Building PPT will teach you:
- How voice recognition actually works
- How large language models run locally on consumer hardware
- How to design distributed systems even at small scale
- How to build software that runs reliably in the background
- How to integrate third-party tools (GitHub, Discord, Google Calendar) via APIs
- How to think about privacy and data ownership in software design

These are real skills that transfer directly to professional engineering work.

---

*Next: [Chapter 2 — Architecture →](../02-architecture/README.md)*
