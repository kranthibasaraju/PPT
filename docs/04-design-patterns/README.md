# Chapter 4 — Design Patterns
## How Is the Code Structured?

---

## What Design Patterns Are

A design pattern is a reusable solution to a commonly occurring problem in software design. Patterns are not code — they are templates. They describe how to structure code to solve a recurring challenge in a clean, maintainable way.

Understanding patterns means recognising when you have a familiar problem and knowing which tool to reach for. It also means being able to discuss your code in terms that other engineers immediately understand.

PPT uses several well-known patterns. Each is explained here with the specific PPT context.

---

## 1. The Pipeline Pattern

**Problem:** You have a sequence of transformations to apply to data, where each step produces the input for the next.

**In PPT:** The voice processing chain. Audio goes through four distinct transformations before becoming a spoken response.

```
raw audio
   │
[Wake Detector]     — detects trigger phrase
   │
recorded speech (wav)
   │
[Transcriber]       — audio → text
   │
text string
   │
[Orchestrator/LLM]  — text → response text
   │
response text
   │
[TTS Speaker]       — text → audio
   │
spoken audio
```

Each stage is independent. It takes an input, produces an output, and knows nothing about what came before or after it. This is the pipeline pattern.

**Why this matters:** You can swap any stage without touching the others. If you want to replace Whisper with a different STT engine, you change `transcriber.py` and nothing else. If you want to try a different TTS voice, you change `speaker.py`. The pipeline contract — defined input type, defined output type — enforces this cleanly.

**In code:**
```python
# pipeline.py
while True:
    audio = wake_detector.listen()          # Step 1
    text = transcriber.transcribe(audio)    # Step 2
    response = orchestrator.process(text)   # Step 3
    speaker.speak(response)                 # Step 4
```

Four lines. Each stage is a function call with a clear input and output. The pipeline is readable, testable, and extensible.

---

## 2. The Strategy Pattern

**Problem:** You want to perform an operation, but the specific way it is done should be interchangeable without changing the calling code.

**In PPT:** The LLM backend. PPT currently uses Ollama (local), but the calling code should not care whether the LLM is Ollama, the Claude API, or something else.

```python
# Without strategy pattern
def process(text):
    if config.USE_OLLAMA:
        response = requests.post("http://localhost:11434/api/chat", ...)
    elif config.USE_CLAUDE:
        response = anthropic.messages.create(...)
    return response.text

# With strategy pattern
class OllamaClient:
    def complete(self, prompt): ...

class ClaudeClient:
    def complete(self, prompt): ...

def process(text, llm_client):
    return llm_client.complete(text)
```

The strategy (which LLM to use) is injected from outside. The processing code never changes when the strategy changes.

**Why this matters:** In Phase 0, we use Ollama. In future phases, we might want to optionally use the Claude API for harder questions. The strategy pattern means this is a one-line config change, not a refactor.

---

## 3. The Observer Pattern (Event-Driven)

**Problem:** One component needs to notify others when something happens, without being tightly coupled to them.

**In PPT:** Reminders and notifications. When a reminder fires, multiple things need to happen: speak it out loud, send a Discord notification, update the task status in Plane. The reminder scheduler should not need to know about Discord or Plane directly.

```python
# The scheduler fires an event
scheduler.on_reminder_due(reminder_id)

# Observers react independently
class VoiceSpeaker:
    def on_reminder_due(self, reminder_id): speak(reminder.text)

class DiscordNotifier:
    def on_reminder_due(self, reminder_id): send_discord_message(reminder.text)

class PlaneUpdater:
    def on_reminder_due(self, reminder_id): update_task_status(reminder.task_id, "done")
```

The scheduler doesn't know or care what happens when a reminder fires. It just emits an event. Each observer handles it in its own way.

**Why this matters:** Adding a new notification channel (say, a desktop popup) means adding one new observer. Nothing else changes. Removing Discord means removing one observer. The scheduler remains untouched.

---

## 4. The Repository Pattern

**Problem:** Your application logic should not need to know how data is stored. The storage mechanism should be swappable.

**In PPT:** Task and project data. Currently stored in SQLite (for voice context) and in Plane (via API). The orchestrator should ask "give me open tasks" — not "run this SQL query" or "call this Plane API endpoint".

```python
# Without repository pattern
def get_open_tasks():
    conn = sqlite3.connect("ppt.db")
    rows = conn.execute("SELECT * FROM tasks WHERE status != 'done'").fetchall()
    return rows

# With repository pattern
class TaskRepository:
    def get_open(self): ...      # implementation hidden
    def create(self, task): ...
    def update(self, task): ...

class SQLiteTaskRepository(TaskRepository):
    def get_open(self):
        # SQLite implementation

class PlaneTaskRepository(TaskRepository):
    def get_open(self):
        # Plane API implementation
```

The orchestrator calls `task_repo.get_open()` and doesn't care whether data comes from SQLite or Plane.

**Why this matters:** In Phase 2, tasks are stored in SQLite. In Phase 5, they move to Plane. With the repository pattern, this migration changes one file (the repository implementation) and nothing in the orchestrator.

---

## 5. The Singleton Pattern

**Problem:** Some resources should only be instantiated once (database connections, model instances, API clients).

**In PPT:** The Whisper model and Ollama client. Loading a machine learning model takes several seconds. We want to load it once at startup and reuse it for every request.

```python
# Without singleton — model loaded on every call (slow!)
def transcribe(audio):
    model = WhisperModel("base.en")  # loads model every time
    return model.transcribe(audio)

# With singleton — model loaded once at startup
class Transcriber:
    _instance = None
    _model = None

    @classmethod
    def get(cls):
        if cls._instance is None:
            cls._instance = cls()
            cls._model = WhisperModel("base.en")  # loads once
        return cls._instance

    def transcribe(self, audio):
        return self._model.transcribe(audio)
```

**Why this matters:** Loading Whisper takes 1–3 seconds. If we loaded it on every request, every interaction would add that delay. The singleton ensures we pay the startup cost once.

---

## 6. The Command Pattern

**Problem:** Represent actions as objects, so they can be queued, logged, undone, or retried.

**In PPT:** Voice commands. "Add task X to project Y" is a command. "Mark task X as done" is a command. Representing these as objects (rather than inline code) allows logging, error handling, and potential undo functionality.

```python
class AddTaskCommand:
    def __init__(self, task_name, project_name):
        self.task_name = task_name
        self.project_name = project_name
        self.timestamp = datetime.now()

    def execute(self):
        project = plane.find_project(self.project_name)
        return plane.create_task(project.id, self.task_name)

    def to_log(self):
        return f"[{self.timestamp}] AddTask: '{self.task_name}' → '{self.project_name}'"
```

**Why this matters:** With commands as objects, you can log every action PPT takes. If something goes wrong, you have a full history of what was attempted. You can also replay commands or implement an "undo last action" voice command.

---

## 7. Dependency Injection

**Problem:** Components that create their own dependencies are hard to test and hard to change.

**In PPT:** The orchestrator depends on the LLM client, task repository, and reminder scheduler. Instead of creating these internally, they are passed in from outside.

```python
# Without dependency injection — tightly coupled
class Orchestrator:
    def __init__(self):
        self.llm = OllamaClient()        # hardcoded
        self.tasks = SQLiteTaskRepo()    # hardcoded

# With dependency injection — loosely coupled
class Orchestrator:
    def __init__(self, llm_client, task_repo, reminder_service):
        self.llm = llm_client
        self.tasks = task_repo
        self.reminders = reminder_service

# At startup:
orchestrator = Orchestrator(
    llm_client=OllamaClient(),
    task_repo=PlaneTaskRepository(),
    reminder_service=APSchedulerService()
)
```

**Why this matters:** For testing, you can inject fake/mock implementations. `Orchestrator(llm_client=MockLLM(), ...)` lets you test the orchestrator's logic without actually calling Ollama. This makes tests fast and deterministic.

---

## Summary Table

| Pattern | Problem it solves | Used in PPT for |
|---|---|---|
| Pipeline | Sequential data transformation | Voice processing chain |
| Strategy | Swappable algorithms | LLM backend (Ollama / Claude) |
| Observer | Event-driven notifications | Reminders → Discord + Voice + Plane |
| Repository | Storage abstraction | Tasks (SQLite / Plane API) |
| Singleton | Single instance of expensive resource | Whisper model, Ollama client |
| Command | Actions as objects | Voice commands (add task, set reminder) |
| Dependency Injection | Loose coupling, testability | Orchestrator dependencies |

---

## A Note on Not Over-Engineering

Design patterns are tools, not rules. Using them where they fit makes code better. Using them everywhere, regardless of whether the problem exists, makes code worse.

PPT is a personal project. Some of these patterns are applied fully. Some are applied partially. Some are noted here for educational value even if the Phase 0 implementation is simpler.

The goal is to write code that you can understand six months later and explain clearly in an interview.

---

*Next: [Chapter 5 — Technologies →](../05-technologies/README.md)*
