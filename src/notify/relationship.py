"""
src/notify/relationship.py — the "relationship layer" for ppt-notify.

WHY this exists:
  A dumb reminder app says: "Time to drink water."
  PPT says something that changes based on how long you've been using it,
  your streak, your mood yesterday, and your name.

HOW the relationship level works:
  XP is earned by:
    - Logging a habit done     → +10 XP
    - Completing a goal        → +100 XP
    - Daily mood check-in      → +5 XP

  Levels (thresholds are deliberately gentle so you reach them quickly):
    0     Stranger      PPT just met you.  Polite, encouraging.
    50    Acquaintance  PPT knows your name.  Starts being warmer.
    200   Friend        PPT references your streaks.  Jokes a little.
    500   Companion     PPT knows your patterns.  Notices if you skip.
    1000  Partner       PPT speaks like it genuinely cares.  Deep trust.

USAGE:
    from src.notify import relationship
    msg = relationship.habit_reminder("Drink water", streak=5)
    greeting = relationship.morning_greeting()
"""
from __future__ import annotations
import random
from src.notify.store import get_profile

# ── Level definitions ─────────────────────────────────────────────────────────

LEVELS = [
    (1000, "Partner"),
    (500,  "Companion"),
    (200,  "Friend"),
    (50,   "Acquaintance"),
    (0,    "Stranger"),
]


def get_level(xp: int) -> str:
    for threshold, label in LEVELS:
        if xp >= threshold:
            return label
    return "Stranger"


def get_level_progress(xp: int) -> dict:
    """Return current level, XP to next level, and 0–100 percent."""
    thresholds = [0, 50, 200, 500, 1000]
    labels = ["Stranger", "Acquaintance", "Friend", "Companion", "Partner"]
    for i, t in enumerate(thresholds):
        if xp < t:
            prev = thresholds[i - 1]
            nxt  = t
            label = labels[i - 1]
            pct = int((xp - prev) / (nxt - prev) * 100)
            return {"level": label, "xp": xp, "next_at": nxt, "pct": pct,
                    "next_level": labels[i]}
    return {"level": "Partner", "xp": xp, "next_at": None, "pct": 100,
            "next_level": None}


# ── Message banks (keyed by level) ───────────────────────────────────────────

_HABIT_MESSAGES = {
    "Stranger": [
        "⏰ Reminder: {habit}",
        "🔔 Time for: {habit}",
        "📌 Don't forget — {habit}",
    ],
    "Acquaintance": [
        "Hey {name} — time for {habit}! 🙌",
        "Quick nudge, {name}: {habit} 📌",
        "Reminder for you, {name}: {habit} ⏰",
    ],
    "Friend": [
        "Hey {name}! {habit} time — you're on a {streak}-day streak! 🔥",
        "{name}, {habit} is calling. {streak} days strong! 💪",
        "Don't break that streak, {name}! {streak} days of {habit} 🏆",
    ],
    "Companion": [
        "I know you're busy, {name}, but {habit} keeps you sharp. Day {streak} ✨",
        "{streak} days in a row — you've built something real, {name}. Time for {habit} 🌱",
        "{name}, your {habit} streak is at {streak}. That's not luck — that's discipline 💪",
    ],
    "Partner": [
        "Hey {name} 💙 — {streak} days of {habit}. I've watched this habit become part of who you are.",
        "{name}, {habit}. You know why. Day {streak} — I'm proud of you.",
        "{streak} consecutive days, {name}. {habit} isn't something you do anymore — it's something you *are* 🌟",
    ],
}

_GOAL_MESSAGES = {
    "Stranger": [
        "📍 Goal check: {goal} — {progress}% complete",
        "🎯 Progress update: {goal} ({progress}%)",
    ],
    "Acquaintance": [
        "Hey {name} — your goal '{goal}' is at {progress}%. Keep going!",
        "{name}, checking in on '{goal}': {progress}% there 🎯",
    ],
    "Friend": [
        "{name}, '{goal}' is {progress}% done. {deadline_msg} You've got this! 🙌",
        "Progress check, {name}! '{goal}' — {progress}% complete. {deadline_msg}",
    ],
    "Companion": [
        "{name}, I've been thinking about '{goal}'. At {progress}% you're really close. {deadline_msg} Push through 🔥",
        "'{goal}' at {progress}%, {name}. {deadline_msg} I believe in what you're building here.",
    ],
    "Partner": [
        "{name} 💙 — '{goal}' is {progress}% done. {deadline_msg} This matters to you. I know it.",
        "Hey {name} — '{goal}' — {progress}%. {deadline_msg} You started this for a reason. Don't stop now.",
    ],
}

_CHECKIN_PROMPTS = {
    "Stranger": [
        "📝 Daily check-in time! How are you feeling? (1–5)",
        "🌤 Time for your daily reflection. Rate your day 1–5.",
    ],
    "Acquaintance": [
        "Hey {name} — how's your day going? Share a quick mood (1–5) 🌤",
        "Check-in time, {name}! How are you feeling today? (1–5)",
    ],
    "Friend": [
        "{name}, how are you doing today, really? Mood 1–5 + a note 🌱",
        "Daily check-in, {name}! Yesterday you were {prev_mood_msg}. How about today? (1–5)",
    ],
    "Companion": [
        "{name}, I notice you've been consistent with check-ins. How are you today? (1–5) 💙",
        "Hey {name} — mood check. No judgment, just honest: 1–5. {prev_mood_msg}",
    ],
    "Partner": [
        "{name} 💙 — daily check-in. I care about how you're actually doing, not just the numbers. How are you?",
        "Hey {name} — just me checking in. {prev_mood_msg} How are you feeling today?",
    ],
}

_MORNING_GREETINGS = {
    "Stranger": [
        "🌅 Good morning! Ready to start the day?",
        "☀️ Morning! Here's your daily summary.",
    ],
    "Acquaintance": [
        "Good morning, {name}! Let's see what today holds 🌅",
        "☀️ Morning, {name}! Your day is ready when you are.",
    ],
    "Friend": [
        "Good morning, {name}! ☀️ You've got {habit_count} habit{s} lined up today.",
        "Rise and shine, {name}! 🌅 {habit_count} habit{s} to keep that streak alive.",
    ],
    "Companion": [
        "Morning, {name} ☀️ — {habit_count} habit{s} today. You've been on a roll lately.",
        "Hey {name}, good morning! {habit_count} habit{s} on the list. Let's have a good one. 🌱",
    ],
    "Partner": [
        "Good morning, {name} 💙 — {habit_count} habit{s} today. I'm here when you need me.",
        "Hey {name} ☀️ — another day. {habit_count} habit{s} lined up. You know the drill — and you're good at it.",
    ],
}

_STREAK_MILESTONES = {
    3:   "🔥 3-day streak on {habit}! You're building momentum, {name}.",
    7:   "🏅 One full week of {habit}! That's real commitment, {name}.",
    14:  "💪 Two weeks straight! {habit} is becoming a genuine habit for you, {name}.",
    21:  "🌟 21 days of {habit}, {name} — science says it takes 21 days to form a habit. You did it.",
    30:  "🏆 30-day streak on {habit}! {name}, this is extraordinary. Seriously.",
    60:  "💎 60 days of {habit}. {name}, you are a different person than when you started.",
    100: "👑 100-day streak, {name}. {habit} is no longer a habit — it's who you are.",
}


# ── Public message generators ─────────────────────────────────────────────────

def _pick(bank: dict, level: str, **kwargs) -> str:
    """Pick a random message from the right level bank and format it."""
    template = random.choice(bank.get(level, bank["Stranger"]))
    return template.format(**kwargs)


def _ctx(user_id: int | None = None) -> dict:
    """Fetch shared context from the profile."""
    p = get_profile(user_id=user_id)
    xp   = p.get("relationship_xp", 0)
    name = p.get("name", "Rana")
    level = get_level(xp)
    return {"name": name, "level": level, "xp": xp}


def habit_reminder(habit_name: str, streak: int = 0, user_id: int | None = None) -> str:
    ctx = _ctx(user_id=user_id)
    # Check for milestone
    if streak in _STREAK_MILESTONES:
        return _STREAK_MILESTONES[streak].format(habit=habit_name, name=ctx["name"])
    return _pick(_HABIT_MESSAGES, ctx["level"],
                 name=ctx["name"], habit=habit_name, streak=streak)


def goal_reminder(
    goal_title: str,
    progress: int = 0,
    deadline: str | None = None,
    user_id: int | None = None,
) -> str:
    ctx = _ctx(user_id=user_id)
    if deadline:
        from datetime import date
        try:
            d = date.fromisoformat(deadline)
            days_left = (d - date.today()).days
            if days_left < 0:
                deadline_msg = "⚠️ Past deadline!"
            elif days_left == 0:
                deadline_msg = "🚨 Due today!"
            elif days_left <= 3:
                deadline_msg = f"⏳ {days_left} days left."
            else:
                deadline_msg = f"📅 {days_left} days to go."
        except ValueError:
            deadline_msg = ""
    else:
        deadline_msg = ""
    return _pick(_GOAL_MESSAGES, ctx["level"],
                 name=ctx["name"], goal=goal_title,
                 progress=progress, deadline_msg=deadline_msg)


def checkin_prompt(prev_mood: int | None = None, user_id: int | None = None) -> str:
    ctx = _ctx(user_id=user_id)
    mood_words = {1: "rough", 2: "tough", 3: "okay", 4: "good", 5: "great"}
    if prev_mood:
        prev_mood_msg = f"Yesterday was {mood_words.get(prev_mood, 'okay')}."
    else:
        prev_mood_msg = ""
    return _pick(_CHECKIN_PROMPTS, ctx["level"],
                 name=ctx["name"], prev_mood_msg=prev_mood_msg)


def morning_greeting(habit_count: int = 0, user_id: int | None = None) -> str:
    ctx = _ctx(user_id=user_id)
    s = "s" if habit_count != 1 else ""
    return _pick(_MORNING_GREETINGS, ctx["level"],
                 name=ctx["name"], habit_count=habit_count, s=s)


def goal_completed_message(goal_title: str, user_id: int | None = None) -> str:
    ctx = _ctx(user_id=user_id)
    msgs = [
        f"🏆 Goal complete: '{goal_title}'! {ctx['name']}, you said you would and you did.",
        f"🎉 '{goal_title}' — DONE! Amazing work, {ctx['name']}.",
        f"✅ '{goal_title}' is finished, {ctx['name']}! That took focus and follow-through. Well done.",
    ]
    return random.choice(msgs)
