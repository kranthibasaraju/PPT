"""
start.py — PPT launcher

Usage:
    python start.py                  # show this menu
    python start.py setup            # run Phase 0 setup
    python start.py board            # start web dashboard only (localhost:5000)
    python start.py check            # quick health check — board + Ollama
    python start.py ecosystem        # start everything: board → check → voice pipeline
    python start.py test wake        # test wake word detector
    python start.py test stt         # test speech-to-text
    python start.py test llm         # test Ollama LLM
    python start.py test tts         # test Piper TTS
    python start.py test all         # run all 4 tests in sequence
    python start.py run              # start full pipeline (with wake word)
    python start.py run --no-wake    # start pipeline without wake word
"""

import os
import sys
import subprocess
import time
import urllib.request
import urllib.error
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
VENV_PYTHON  = PROJECT_ROOT / ".venv" / "bin" / "python"


# ── Auto-activate venv ────────────────────────────────────────────────────────
def _relaunch_in_venv() -> None:
    """
    If a .venv exists and we're not already running inside it, re-exec this
    script using the venv's Python so all packages are available.
    """
    if not VENV_PYTHON.exists():
        return  # no venv yet — that's fine, setup will create it

    # sys.prefix points to the venv root when inside one
    already_in_venv = Path(sys.prefix) == PROJECT_ROOT / ".venv"
    if already_in_venv:
        return

    # Re-exec with venv Python; os.execv replaces this process entirely
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON)] + sys.argv)


_relaunch_in_venv()


# ── Helpers ───────────────────────────────────────────────────────────────────
BOLD   = "\033[1m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
RESET  = "\033[0m"


def _run(cmd: list) -> int:
    """Run a command in a subprocess, streaming output to the terminal."""
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
    return result.returncode


def _python() -> str:
    """Return the Python executable to use for sub-commands."""
    return str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable


# ── Menu ──────────────────────────────────────────────────────────────────────
MENU = f"""
{BOLD}PPT — Personal AI Voice Assistant{RESET}
{CYAN}{'─' * 50}{RESET}

  {BOLD}python start.py ecosystem{RESET}
      Start everything: board → health check → voice

  {BOLD}python start.py board{RESET}
      Start web dashboard only  →  localhost:5000

  {BOLD}python start.py check{RESET}
      Quick health check (board + Ollama)

  {BOLD}python start.py setup{RESET}
      Install dependencies, download Piper TTS

  {BOLD}python start.py test wake{RESET}
      Test wake word detector (say "Hey PPT")

  {BOLD}python start.py test stt{RESET}
      Test speech-to-text (records 8s from mic)

  {BOLD}python start.py test llm{RESET}
      Test Ollama LLM connection + response

  {BOLD}python start.py test tts{RESET}
      Test Piper TTS (plays a sample sentence)

  {BOLD}python start.py test all{RESET}
      Run all 4 tests in sequence

  {BOLD}python start.py run{RESET}
      Start full voice pipeline (say "Hey PPT")

  {BOLD}python start.py run --no-wake{RESET}
      Start pipeline without wake word
      (press Enter to speak)

{CYAN}{'─' * 50}{RESET}
"""


# ── Commands ──────────────────────────────────────────────────────────────────
def cmd_setup() -> None:
    _run([sys.executable, "scripts/setup_phase0.py"])


def cmd_test_wake() -> None:
    print(f"\n{BOLD}Testing wake word detector…{RESET}")
    print("Say 'Hey PPT' (or 'Hey Jarvis' — custom model coming in Phase 1).")
    print("Press Ctrl+C to stop.\n")
    _run([_python(), "src/wake/detector.py", "--test"])


def cmd_test_stt() -> None:
    print(f"\n{BOLD}Testing speech-to-text…{RESET}\n")
    _run([_python(), "src/stt/transcriber.py", "--test"])


def cmd_test_llm() -> None:
    print(f"\n{BOLD}Testing Ollama LLM…{RESET}\n")
    _run([_python(), "src/llm/ollama_client.py", "--test"])


def cmd_test_tts() -> None:
    print(f"\n{BOLD}Testing Piper TTS…{RESET}\n")
    _run([_python(), "src/tts/speaker.py", "--test"])


def cmd_test_all() -> None:
    tests = [
        ("LLM (Ollama)",       cmd_test_llm),
        ("STT (Whisper)",      cmd_test_stt),
        ("TTS (Piper)",        cmd_test_tts),
        ("Wake word detector", cmd_test_wake),
    ]
    for name, fn in tests:
        print(f"\n{BOLD}{CYAN}{'─' * 40}{RESET}")
        print(f"{BOLD}  {name}{RESET}")
        print(f"{BOLD}{CYAN}{'─' * 40}{RESET}")
        fn()
        try:
            input(f"\n  Press Enter to continue to the next test…")
        except EOFError:
            pass  # non-interactive (piped) — just continue


def _ping(url: str, timeout: int = 3) -> bool:
    """Return True if the URL responds with HTTP 200."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def cmd_board() -> None:
    """Start the web dashboard in the foreground."""
    print(f"\n{BOLD}Starting ppt-board at http://localhost:5000{RESET}\n")
    _run([_python(), "src/web/app.py"])


def cmd_check() -> None:
    """Quick health check — board and Ollama."""
    checks = [
        ("ppt-board  ", "http://localhost:5000"),
        ("Ollama     ", "http://localhost:11434"),
    ]
    print(f"\n{BOLD}PPT health check{RESET}")
    print(f"{CYAN}{'─' * 36}{RESET}")
    all_ok = True
    for name, url in checks:
        ok = _ping(url)
        icon = f"{GREEN}✓{RESET}" if ok else f"{YELLOW}✗{RESET}"
        status = "up" if ok else "down"
        print(f"  {icon}  {name}  {status}  ({url})")
        if not ok:
            all_ok = False
    print(f"{CYAN}{'─' * 36}{RESET}")
    if all_ok:
        print(f"  {GREEN}{BOLD}All services up.{RESET}\n")
    else:
        print(f"  {YELLOW}Some services are down — check above.{RESET}\n")
    return all_ok


def cmd_ecosystem(no_wake: bool = False) -> None:
    """
    Start the full PPT ecosystem:
      1. Launch ppt-board in background
      2. Wait for board to be ready
      3. Run quick health check
      4. Start the voice pipeline in foreground
    """
    print(f"\n{BOLD}{CYAN}PPT Ecosystem Starting…{RESET}")
    print(f"{CYAN}{'─' * 50}{RESET}\n")

    # ── Step 1: start ppt-board in background ─────────────────────────────────
    board_already_up = _ping("http://localhost:5000")
    if board_already_up:
        print(f"  {GREEN}✓{RESET}  ppt-board already running at localhost:5000")
        board_proc = None
    else:
        print(f"  →  Starting ppt-board…")
        board_proc = subprocess.Popen(
            [_python(), "src/web/app.py"],
            cwd=str(PROJECT_ROOT),
            stdout=open(PROJECT_ROOT / "logs" / "board.log", "a"),
            stderr=subprocess.STDOUT,
        )
        # Wait up to 8 seconds for board to come up
        for _ in range(16):
            time.sleep(0.5)
            if _ping("http://localhost:5000"):
                print(f"  {GREEN}✓{RESET}  ppt-board ready at http://localhost:5000")
                break
        else:
            print(f"  {YELLOW}⚠{RESET}  ppt-board slow to start — check logs/board.log")

    # ── Step 2: health check ──────────────────────────────────────────────────
    print()
    cmd_check()

    # ── Step 3: start voice pipeline in foreground ────────────────────────────
    print(f"{BOLD}Starting voice pipeline…{RESET}\n")
    try:
        extra = ["--no-wake"] if no_wake else []
        _run([_python(), "src/orchestrator/pipeline.py"] + extra)
    finally:
        # Clean up board process if we started it
        if board_proc and board_proc.poll() is None:
            board_proc.terminate()


def cmd_run(no_wake: bool = False) -> None:
    extra = ["--no-wake"] if no_wake else []
    _run([_python(), "src/orchestrator/pipeline.py"] + extra)


# ── Argument parsing (no external dependencies) ───────────────────────────────
def main() -> None:
    args = sys.argv[1:]

    if not args:
        print(MENU)
        return

    command = args[0].lower()

    if command == "ecosystem":
        no_wake = "--no-wake" in args
        cmd_ecosystem(no_wake=no_wake)

    elif command == "board":
        cmd_board()

    elif command == "check":
        cmd_check()

    elif command == "setup":
        cmd_setup()

    elif command == "test":
        if len(args) < 2:
            print("Usage: python start.py test <wake|stt|llm|tts|all>")
            sys.exit(1)
        target = args[1].lower()
        dispatch = {
            "wake": cmd_test_wake,
            "stt":  cmd_test_stt,
            "llm":  cmd_test_llm,
            "tts":  cmd_test_tts,
            "all":  cmd_test_all,
        }
        if target not in dispatch:
            print(f"Unknown test target '{target}'. Choose from: wake, stt, llm, tts, all")
            sys.exit(1)
        dispatch[target]()

    elif command == "run":
        no_wake = "--no-wake" in args
        cmd_run(no_wake=no_wake)

    else:
        print(f"Unknown command '{command}'.\n")
        print(MENU)
        sys.exit(1)


if __name__ == "__main__":
    main()
