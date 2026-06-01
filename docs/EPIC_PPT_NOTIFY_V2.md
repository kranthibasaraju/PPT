# Epic: PPT Notify V2 — Smart Reminder Intelligence

**Status:** 🔲 Planned — Team Handoff  
**Created:** 2026-05-31  
**Owner:** Team  
**Sponsor:** Rana  

---

## Context for the Team

PPT Notify V1 is a working reminder daemon: it fires at a set time via Telegram,
supports habits, goals, and check-ins, and has a relationship layer that adjusts
message tone as the user engages more.

V2 makes reminders *intelligent*. Instead of firing at a fixed time regardless of
context, they understand *what* the reminder is about, *when* the user is actually
available, and *how* to phrase it given the user's current state.

This epic is owned by the team. Stories are ordered by dependency.
Each story has a clear acceptance criterion — that's what "done" means.

---

## System Context

```
Telegram message
     │
     ▼
TelegramHandler (src/integrations/telegram_handler.py)
     │
     ├──▶ IntentManager (NEW — Story 1)
     │         classifies: what is this reminder about?
     │
     ├──▶ ContextEngine (NEW — Story 2)
     │         answers: what is the user's current state?
     │
     ▼
Scheduler (src/notify/scheduler.py)
     │   uses intent + context to decide WHEN to fire
     ▼
Messenger (src/notify/messenger.py)
     │   uses intent + context to decide HOW to phrase it
     ▼
Telegram → user
```

---

## Stories

---

### 🔲 Story 1 — Intent Manager
**"What is this reminder actually about?"**

Every reminder has an implicit category. "Take meds" is health. "Call mum" is
relationship. "Review PR" is work. Right now PPT treats them all the same.
The intent manager classifies reminders so the scheduler and messenger can
treat them differently.

**WHY:** A work reminder should be suppressed during focus time. A health
reminder (meds) should never be suppressed. A relationship reminder should
fire in the evening, not mid-morning. Intent unlocks all of this.

**Location:** `src/notify/intent_manager.py` (new file)

| Task | Status | Notes |
|---|---|---|
| Define intent taxonomy: `health`, `work`, `relationship`, `personal`, `finance`, `learning` | 🔲 Todo | Start with 6 — can expand |
| `classify_intent(title: str, notes: str) -> Intent` — keyword + pattern matching (no LLM required) | 🔲 Todo | Keep it fast and offline; LLM optional upgrade later |
| Add `intent` column to `reminders` table (nullable, backfilled async) | 🔲 Todo | Migration must not break existing rows |
| `backfill_intents()` — classify all existing reminders on daemon start | 🔲 Todo | Run once at startup, skip already-classified |
| Intent displayed in `/remind list` output | 🔲 Todo | e.g. `[health] 09:00 Take meds` |
| Unit tests: 10+ reminder titles, assert correct intent | 🔲 Todo | `tests/test_intent_manager.py` |

**Acceptance criterion:** `/remind list` shows intent tags. `classify_intent("Take meds", "")` returns `Intent.HEALTH`.

---

### 🔲 Story 2 — Context Engine
**"What is the user's current state right now?"**

Context is the snapshot of what's happening for the user at a given moment.
The scheduler and messenger both need this to make good decisions.

**WHY:** A reminder that fires during focus time, at midnight, or while the
user is already overwhelmed is worse than no reminder. Context lets PPT
know when *not* to fire, and when to adjust tone.

**Location:** `src/notify/context_engine.py` (new file)

| Task | Status | Notes |
|---|---|---|
| Define `UserContext` dataclass: `is_focus_time`, `is_quiet_hours`, `activity_score`, `mood`, `pending_reminder_count` | 🔲 Todo | Snapshot, not a stream |
| `get_context(user_id) -> UserContext` — reads from journal.db + notify.db | 🔲 Todo | Focus time from open work sessions; quiet hours from user profile |
| `is_good_time_to_fire(context, intent) -> bool` — decision function | 🔲 Todo | Health always fires; work suppressed in focus; all suppressed in quiet hours |
| Expose context in `/status` Telegram command: "You're in focus mode until 14:00" | 🔲 Todo | Useful for debugging and user trust |
| Unit tests: `get_context()` with mocked DB rows | 🔲 Todo | `tests/test_context_engine.py` |

**Context definitions to implement:**

| Context field | Source | Rule |
|---|---|---|
| `is_focus_time` | journal.db `work_sessions` — open session with no end time | True if session started < 2h ago |
| `is_quiet_hours` | user_profiles.quiet_hours_start / end | True if current time is in range |
| `activity_score` | pattern_tracker (Story 3) | 0.0–1.0 availability |
| `mood` | notify.db last checkin | Last mood score (1–5), None if > 24h ago |
| `pending_reminder_count` | notify.db reminders fired but not acknowledged in last 30 min | High count → user is overwhelmed |

**Acceptance criterion:** `is_good_time_to_fire(context, Intent.WORK)` returns `False` when `is_focus_time=True`. Health intent always returns `True`.

---

### 🔲 Story 3 — Pattern Analysis
**"When is this user actually available?"**

Learn per-user availability patterns from their journal and reminder history.
Use this to suggest better reminder times and avoid firing into dead zones.

**WHY:** A user who works 10–13 every day should never get a work reminder
in that window. Pattern analysis makes this automatic without asking the user
to configure a schedule.

**Location:** `src/notify/pattern_tracker.py` (new file — referenced in Smart Reminders epic)

| Task | Status | Notes |
|---|---|---|
| `build_activity_profile(user_id) -> dict[str, float]` — hourly availability map from last 30 days of journal data | 🔲 Todo | `{"09": 0.3, "12": 0.8, ...}` — 0 = busy, 1 = free |
| `get_best_fire_time(user_id, after: str, intent: Intent) -> str` — find next high-availability window | 🔲 Todo | Used by scheduler when deciding to defer a reminder |
| Store profile in notify.db, refresh weekly | 🔲 Todo | Don't recalculate on every scheduler tick |
| `suggest_time(user_id, intent) -> str` — called when user creates a new reminder without specifying time | 🔲 Todo | "Based on your patterns, 14:00 looks good for this" |
| Add `suggested_time` to `/remind add` response when intent is known | 🔲 Todo | Opt-in nudge, not forced |

**Acceptance criterion:** `get_best_fire_time(user_id, after="09:00", intent=Intent.WORK)` returns a time outside the user's typical work-session hours.

---

### 🔲 Story 4 — Smart Scheduling (Deferred Firing)
**"Don't fire now — wait for the right moment."**

Connect intent + context + pattern analysis to the scheduler.
Reminders that would fire at a bad time get deferred to the next good window.

**WHY:** Stories 1–3 build the knowledge. Story 4 uses it.
This is the payoff — reminders that feel thoughtful instead of intrusive.

**Location:** `src/notify/scheduler.py` (modify existing)

| Task | Status | Notes |
|---|---|---|
| Before firing a reminder, call `is_good_time_to_fire(context, intent)` | 🔲 Todo | If False → calculate defer time, reschedule |
| Max defer: 2 hours (after that, fire regardless to avoid infinite suppression) | 🔲 Todo | Configurable per intent: health = 0 defer, work = up to 2h |
| Log defer events: `reminder_fires` table — add `deferred_from`, `defer_reason` columns | 🔲 Todo | Audit trail, also feeds pattern analysis |
| `/remind status <id>` — shows if reminder is currently deferred and why | 🔲 Todo | User transparency |
| Regression test: existing reminders still fire correctly with no regressions | 🔲 Todo | Run full test suite |

**Acceptance criterion:** A reminder set for 10:00 during a focus session fires at 12:05 (after focus ends + 5 min buffer), not at 10:00.

---

### 🔲 Story 5 — Richer Message Personalisation
**"Say the right thing, not just the right thing at the right time."**

Use intent + context + relationship level to vary how reminders are phrased.
A health reminder at relationship level "Close Friend" should feel different
from a terse notification.

**Location:** `src/notify/messenger.py` (modify existing)

| Task | Status | Notes |
|---|---|---|
| `build_message(reminder, intent, context, relationship_level) -> str` — replaces flat message lookup | 🔲 Todo | Intent + level together determine template |
| Define message templates per intent × relationship level (6 intents × 5 levels = 30 templates) | 🔲 Todo | Start with health + work + relationship intents |
| Context-aware additions: "You've been in focus for 2h — time to take a break and..." | 🔲 Todo | Append to message when context warrants |
| Acknowledge button in Telegram (inline keyboard): "✓ Done" / "⏰ Snooze 30m" | 🔲 Todo | Feeds acknowledgement rate back to pattern tracker |

**Acceptance criterion:** A health reminder at "Close Friend" level feels warm and personal. Same reminder at "Stranger" level is neutral and professional.

---

## What the Team Does NOT Own

| Area | Owner | Notes |
|---|---|---|
| ppt-board | Rana | Internal dev tool, manual deploy |
| User onboarding flow | Rana | Beta launch epic |
| ppt-journal | Rana | Not part of this epic |
| Infrastructure / CI | Rana | Self-hosted runner already set up |

---

## Build Order

```
Story 1 (Intent Manager) — no dependencies, start here
Story 2 (Context Engine) — parallel with Story 1
  → Story 3 (Pattern Analysis) — needs context + journal data shape
    → Story 4 (Smart Scheduling) — needs all three
      → Story 5 (Message Personalisation) — needs intent + context
```

Stories 1 and 2 can be built in parallel by two developers.

---

## Testing Expectations

Each story ships with tests in `tests/`. The CI workflow runs `pytest tests/` on
every PR — a failing test blocks merge. No exceptions.

Naming convention:
- `tests/test_intent_manager.py`
- `tests/test_context_engine.py`
- `tests/test_pattern_tracker.py`
- `tests/test_scheduler_smart.py`

---

## Questions for Rana Before Starting

| # | Question |
|---|---|
| Q1 | Should `classify_intent` be keyword-only first, or use Ollama from the start? |
| Q2 | Quiet hours default: 23:00–07:00 — correct for beta users, or configurable from day 1? |
| Q3 | Defer max of 2h for work intent — is this right, or should users configure it? |
| Q4 | Acknowledge button (inline keyboard) — is Telegram Bot API mode already set up for callback queries? |

---

## Related Files

- `src/notify/scheduler.py` — modify in Story 4
- `src/notify/messenger.py` — modify in Story 5
- `src/notify/store.py` — schema changes in Stories 1, 3
- `src/notify/pattern_tracker.py` — new, Story 3
- `src/notify/intent_manager.py` — new, Story 1
- `src/notify/context_engine.py` — new, Story 2
- `docs/EPIC_PPT_SMART_REMINDERS.md` — related, Story 3 supersedes SR Story 1
