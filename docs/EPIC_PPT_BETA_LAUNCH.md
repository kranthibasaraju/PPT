# Epic: PPT Beta Launch — User Product

**Status:** 🟡 In Progress  
**Created:** 2026-05-31  
**Owner:** Rana  

---

## Why this epic exists

PPT is splitting into two distinct products:

| Product | Audience | Entry point |
|---|---|---|
| **User product** (ppt-notify + ppt-journal) | Beta users (< 10 initially) | Invite link → web onboarding → Telegram bot |
| **Developer tool** (ppt-board) | Rana + team | Manual deploy to Debian, internal only |

This epic covers everything needed to hand the user product to beta testers —
from a working onboarding flow to a simple progress view — while keeping
ppt-board separate and internally deployed.

---

## Epic Goal

> A beta user receives an invite link, completes onboarding in under 5 minutes,
> gets their first personalized reminder via Telegram, and can see their habit
> and goal progress — without ever touching a terminal.

---

## Architecture Split

```
ppt-notify + ppt-journal  →  beta users  →  public-facing, invite-gated
ppt-board                 →  Rana + team →  internal, manual Debian deploy
```

**WHY manual deploy for ppt-board:**
The board is a developer tool. It reads from the same DBs as ppt-notify.
It doesn't need CI/CD — a manual `git pull && systemctl restart ppt-board`
on the Debian server is the right level of control. Automating it creates risk
of breaking the dev tool mid-sprint with no rollback story.

---

## What already exists

- ✅ `src/notify/store.py` — full multi-user schema: `users`, `user_profiles`, invites, per-user habits/reminders/goals
- ✅ `src/web/onboarding_routes.py` — invite creation, Google OAuth flow, Telegram link token
- ✅ Telegram CRUD — `/remind`, `/habit`, `/goal`, `/checkin` all implemented
- ✅ ppt-board — shows projects, tasks, journal, epics (developer-facing)

---

## Stories

---

### 🔲 Story 1 — Onboarding Flow Completion
The invite → Google OAuth → Telegram link chain exists but needs end-to-end validation
with a real beta user account (not just Rana's default user).

**WHY:** The current flow was built for a single user. Multi-user paths
(especially Telegram routing per user_id) need smoke testing before inviting anyone.

| Task | Status | Notes |
|---|---|---|
| Create test invite for a second user, run full onboarding flow | 🔲 Todo | Catch any gaps before real invites |
| Verify Google OAuth callback correctly creates `users` + `user_profiles` row | 🔲 Todo | Check `accept_invite()` in store.py |
| Verify Telegram link token → `/start <token>` correctly sets `telegram_user_id` | 🔲 Todo | Check `ensure_telegram_link_token()` |
| Verify new user gets seeded with default habits on first login | 🔲 Todo | Should happen in onboarding completion handler |
| Add confirmation screen after Telegram link: "You're all set — try /help" | 🔲 Todo | Currently no success page |
| Smoke test: new user receives a timed reminder via Telegram | 🔲 Todo | End-to-end validation |

---

### 🔲 Story 2 — Per-User Telegram Routing
All incoming Telegram messages must be routed to the correct user context.
Currently the bot may assume a single user.

**WHY:** If two beta users message the bot, their reminders must stay isolated.
A message from user A must never read or write user B's data.

| Task | Status | Notes |
|---|---|---|
| Audit `src/integrations/telegram_handler.py` — does every command look up `user_id` by `telegram_user_id`? | 🔲 Todo | Most critical safety check |
| Ensure `get_user_by_telegram_id(telegram_user_id)` is called at start of every handler | 🔲 Todo | If user not found → "Please complete onboarding first" |
| Unlinked user sends a message → friendly error, not a crash | 🔲 Todo | |
| `/help` response is personalised with the user's display name | 🔲 Todo | Small touch, high impact |

---

### 🔲 Story 3 — User Progress View (Web)
Beta users need a lightweight web page to see their reminders, habits, and goals.
**Not** the full ppt-board — that's a developer tool. A clean, read-focused user view.

**WHY separate from ppt-board:**
ppt-board shows epics, projects, tasks, journal — developer context. A beta user
wants to see "my habits today", "my active goals", "my upcoming reminders".
Showing them the dev board adds noise and exposes internal planning.

| Task | Status | Notes |
|---|---|---|
| `/me` route — user-facing dashboard, session-auth gated | 🔲 Todo | Distinct from `/board/` |
| Show: today's habits (done/not done), active goals + progress, next 3 reminders | 🔲 Todo | Read from store using session user_id |
| Show: relationship level + XP (personalised feel) | 🔲 Todo | Already in store, just needs a view |
| Mobile-friendly layout (most users on phone) | 🔲 Todo | Single-column, large tap targets |
| Auth gate: redirect to onboarding if no valid session | 🔲 Todo | |

---

### 🔲 Story 4 — Personalized First Reminders
When a user completes onboarding, PPT should send a welcome reminder and
suggest a first habit — making the product feel alive immediately.

**WHY:** An empty reminder list on day 1 is a dead end. Seeding a few
sensible defaults (morning check-in, evening wind-down) gives users something
to react to, delete, or build on.

| Task | Status | Notes |
|---|---|---|
| On onboarding completion: send Telegram welcome message with quick-start tips | 🔲 Todo | "Hi [name]! You're connected. Try /remind add 09:00 Morning coffee" |
| Seed 2–3 default habits for new users (morning check-in, evening review) | 🔲 Todo | Seeded at user_id scope, not global |
| Seed 1 sample goal ("Complete onboarding", auto-closed) | 🔲 Todo | Shows the goal tracking feature |
| First reminder fires within 15 min of onboarding (timed welcome ping) | 🔲 Todo | Tangible "it works" moment |

---

### 🔲 Story 5 — Beta Ops: Invite Management & Monitoring
Rana needs to manage beta users without logging into the server.

| Task | Status | Notes |
|---|---|---|
| ppt-board `/board/users` admin page shows all users, status, last active | 🔲 Todo | Already partially in `_ADMIN_HTML` in onboarding_routes.py — needs polish |
| Revoke invite (set status = revoked) from admin page | 🔲 Todo | |
| Per-user activity summary: last message, reminder count, habit streak | 🔲 Todo | Quick health signal |
| ppt-board manually deployed to Debian (not CI/CD) | ✅ Decided | `git pull && systemctl restart ppt-board` |

---

### 🔲 Story 6 — Beta Feedback Loop
Light-touch feedback so you know if things are working.

| Task | Status | Notes |
|---|---|---|
| `/feedback <message>` Telegram command → stores in DB, notifies Rana | 🔲 Todo | Lowest-friction feedback path |
| Daily digest to Rana: active user count, reminders fired, habits logged | 🔲 Todo | Morning Telegram message from the bot |
| `reminder_fires` table already exists — add `acknowledged_at` tracking | 🔲 Todo | Was user awake when reminder fired? |

---

## Build Order

```
Story 1 (onboarding end-to-end works)
  → Story 2 (per-user Telegram routing — must be safe before inviting anyone)
    → Story 4 (first-run experience)
    → Story 3 (user progress web view)
      → Story 5 (beta ops / monitoring)
        → Story 6 (feedback loop)
```

Stories 1 + 2 are blockers. Nothing else matters if onboarding breaks or
user data leaks between accounts.

---

## Definition of "Ready to Invite Beta Users"

- [ ] Story 1 complete — full onboarding tested with a real second account
- [ ] Story 2 complete — Telegram routing is user-isolated
- [ ] Story 4 complete — first-run experience is warm, not empty
- [ ] ppt-board deployed to Debian (manual, internal)

---

## Related Epics

- `EPIC_PPT_ONBOARDING.md` — developer onboarding (separate concern)
- `EPIC_PPT_NOTIFY_V2.md` — smart reminder improvements (team handoff)
- `EPIC_PPT_SMART_REMINDERS.md` — pattern-based scheduling
