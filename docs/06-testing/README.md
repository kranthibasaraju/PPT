# Chapter 6 — Testing
## How Do We Know It Works?

---

## Testing a Voice Assistant

Testing software that listens, thinks, and speaks is different from testing a web API or a database. You cannot just send an HTTP request and check the status code. You are dealing with audio input, ML model output, and spoken responses.

This chapter covers the testing strategy for PPT: how to test each layer independently, how to measure what matters, and what "good enough" means for a personal project.

---

## The Testing Pyramid

The testing pyramid is a model for how to allocate testing effort.

```
        ▲
       /E2E\          End-to-end tests: few, slow, but most realistic
      /─────\
     /Integra-\       Integration tests: some, test multiple layers together
    /──────────\
   /  Unit Tests \    Unit tests: many, fast, test individual components
  /──────────────\
```

At the base: many fast unit tests. In the middle: integration tests. At the top: a small number of full end-to-end tests.

For PPT, this translates to:
- **Unit tests** — each layer in isolation (transcriber, LLM client, TTS)
- **Integration tests** — pairs of layers together (STT → LLM)
- **End-to-end tests** — full voice loop from mic to speaker

---

## Testing Each Layer

### Layer 1 — Wake Word Detector

**What to test:**
- Does it detect the wake word when spoken clearly?
- Does it *not* fire on similar words or random speech?
- Does it handle background noise?

**How to test:**
```bash
# Built-in test mode: listens and prints detections
python src/wake/detector.py --test
```

**Metrics:**
- *True positive rate:* How often does it detect "Hey PPT" when actually spoken? Target: > 95%
- *False positive rate:* How often does it fire when you didn't say it? Target: < 1 per hour in normal home noise
- *Latency:* How quickly after the phrase ends does detection fire? Target: < 500ms

**Manual test procedure:**
1. Start the detector in test mode
2. Say "Hey PPT" 20 times from varying distances (1m, 2m, 3m)
3. Record how many times it detects correctly
4. Leave it running for 30 minutes in a room with normal background noise
5. Count false positives

### Layer 2 — Transcriber (STT)

**What to test:**
- Does it correctly transcribe clear speech?
- Does it handle different speeds of speech?
- Does it handle domain-specific vocabulary ("mcp-server", "Ollama", "Piper")?

**How to test:**
```bash
# Records 10 seconds from mic and prints transcription
python src/stt/transcriber.py --test
```

**Metrics:**
- *Word Error Rate (WER):* Percentage of words incorrectly transcribed. Target: < 10% for clear speech.
- *Latency:* How long does transcription take? Target: < 2 seconds for a 10-second clip on Mac Mini.

**Manual test procedure:**
1. Prepare a list of 20 test phrases covering: simple questions, task commands, project names, reminder requests
2. Record each phrase and transcribe it
3. Compare output to expected, count errors
4. Calculate WER

**Example test phrases:**
- "What's on my plate today"
- "Add task write unit tests to the mcp-server project"
- "Remind me to check the deployment at three PM"
- "What did I commit last week in the portfolio project"

### Layer 3 — LLM (Ollama)

**What to test:**
- Does it respond to general questions coherently?
- Does it stay concise (voice responses should be short)?
- Does it correctly interpret task command language?

**How to test:**
```bash
# Sends a test prompt and prints response
python src/llm/ollama_client.py --test
```

**Things to evaluate (no numerical metric — manual review):**
- Response makes sense given the prompt
- Response is appropriately brief (under 3 sentences for conversational answers)
- System prompt is being respected (PPT persona)

**Sample test prompts:**
- "What is the capital of France?" → expect: "Paris."
- "Explain what a REST API is in one sentence." → expect: brief accurate answer
- "Add task fix the login bug to the qa-agent project." → expect: parsed intent, not a conversational response

### Layer 4 — TTS Speaker

**What to test:**
- Does it speak the text out loud?
- Is the audio quality acceptable?
- Does it handle punctuation and numbers naturally?

**How to test:**
```bash
# Speaks a test phrase through the system speakers
python src/tts/speaker.py --test
```

**Manual evaluation:**
- Listen to the output. Does it sound natural?
- Test with: numbers ("three fifty PM"), abbreviations, long sentences, short sentences.
- Check latency: how long between calling `speak()` and hearing audio? Target: < 1 second.

---

## Integration Tests

### STT → LLM

After transcription, does the LLM receive the right text and respond sensibly?

```python
def test_stt_to_llm():
    # Simulate a transcription result
    transcribed = "what projects am I working on"
    response = orchestrator.process(transcribed)
    assert len(response) > 0
    assert "project" in response.lower() or "portfolio" in response.lower()
```

### Orchestrator Routing

Does the orchestrator correctly route different intents?

```python
def test_routing_add_task():
    result = orchestrator.process("add task write tests to mcp-server")
    assert result.intent == "add_task"
    assert result.task_name == "write tests"
    assert result.project == "mcp-server"

def test_routing_general_question():
    result = orchestrator.process("what time is it")
    assert result.intent == "general_llm"
```

### Plane API

Does creating a task via the Plane API actually work?

```python
def test_plane_create_task():
    task = plane_repo.create(name="test task", project="mcp-server")
    assert task.id is not None
    assert task.name == "test task"

    # Clean up
    plane_repo.delete(task.id)
```

---

## End-to-End Tests

The full pipeline test. Automated end-to-end testing of a voice assistant requires a synthetic audio input.

**Approach:** Use a pre-recorded audio file instead of a live microphone. Feed it into the pipeline and verify the response.

```python
def test_full_pipeline():
    # Load pre-recorded audio of someone saying "Hey PPT, what time is it"
    audio = load_audio("tests/fixtures/hey_ppt_what_time.wav")

    # Inject into pipeline (bypassing live mic)
    response_text = pipeline.process_audio(audio)

    assert "time" in response_text.lower() or any(
        digit in response_text for digit in "0123456789"
    )
```

For Phase 0, full E2E tests are manual: you say something, you listen to the response, you evaluate whether it was correct.

---

## Measuring What Matters: Latency

The single most important metric for a voice assistant is end-to-end latency — the time between when you finish speaking and when you hear the response.

**Target: under 5 seconds.**

Breaking it down:

| Stage | Expected duration |
|---|---|
| Wake word detection fires | ~100ms |
| Audio recorded | ~1–3s (depends on your speech length) |
| Audio sent to Mac Mini | ~10ms (local network) |
| Whisper transcription | ~500ms–1.5s |
| Orchestrator routing | ~50ms |
| Ollama LLM response | ~1–3s |
| Piper TTS synthesis | ~200–500ms |
| Audio sent back + playback starts | ~50ms |
| **Total (excluding speaking time)** | **~2–5s** |

Logging timestamps at each stage lets you identify bottlenecks. If total latency is too high, the biggest wins are usually in the LLM (try a smaller model) or in STT (try a smaller Whisper model).

---

## Testing Philosophy for Personal Projects

Not everything needs a test. Over-testing a personal project is a real failure mode — it adds maintenance burden without proportional value.

**What is worth testing formally:**
- Orchestrator intent routing (high value, easy to automate)
- Plane API integration (catches API changes)
- Config loading and settings (prevents silent misconfiguration)

**What is fine to test manually:**
- Wake word detection (subjective, hardware-dependent)
- TTS audio quality (subjective)
- LLM response quality (subjective, changes with model updates)

**What matters most is: does it work reliably in daily use?**

Test that. Use it every day. Notice when it fails. Fix those failures.

---

*Next: [Chapter 7 — Interview Guide →](../07-interview/README.md)*
