"""
scripts/setup_phase0.py
One-shot setup script for PPT Phase 0 on macOS (Apple Silicon / Mac Mini).

Checks dependencies, installs system packages via Homebrew, creates a Python
virtual environment, installs Python packages, downloads Piper TTS binary and
voice models, and verifies Ollama is installed.

Usage:
    python3 scripts/setup_phase0.py
"""

import os
import sys
import shutil
import subprocess
import tarfile
import urllib.request
import platform
from pathlib import Path
from typing import Optional, List

# ── Colours ───────────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

OK   = f"{GREEN}✓{RESET}"
WARN = f"{YELLOW}⚠{RESET}"
FAIL = f"{RED}✗{RESET}"

# Track any blocking issues found during setup
_issues: List[str] = []


def info(msg: str) -> None:  print(f"  {msg}")
def ok(msg: str)   -> None:  print(f"  {OK}  {msg}")
def warn(msg: str) -> None:  print(f"  {WARN}  {YELLOW}{msg}{RESET}")
def fail(msg: str) -> None:
    print(f"  {FAIL}  {RED}{msg}{RESET}")
    _issues.append(msg)

def header(msg: str) -> None:
    print(f"\n{BOLD}── {msg} {'─' * max(0, 60 - len(msg))}{RESET}")

def run(cmd: list[str], check: bool = True, capture: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=check, capture_output=capture, text=True)


# ── Project root ──────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent


# ─────────────────────────────────────────────────────────────────────────────
# 1. Python version check — warn only, don't exit
#    The *setup script itself* can run on 3.9; the venv needs 3.11+.
# ─────────────────────────────────────────────────────────────────────────────
def check_python() -> bool:
    """Returns True if the running Python is 3.9+ (minimum viable for PPT packages)."""
    header("Python version")
    major, minor, patch = sys.version_info[:3]
    version_str = f"{major}.{minor}.{patch}"
    if (major, minor) >= (3, 9):
        ok(f"Python {version_str} — OK")
        return True

    fail(f"Python {version_str} detected — PPT requires 3.9+.")
    print(
        "\n  Install Python 3.9+ from https://www.python.org/downloads/\n"
        "  or via Homebrew:  brew install python@3.11\n"
    )
    return False


# ─────────────────────────────────────────────────────────────────────────────
# 2. Homebrew — also check /opt/homebrew (Apple Silicon) and /usr/local (Intel)
# ─────────────────────────────────────────────────────────────────────────────
def find_brew() -> Optional[str]:
    """Return path to brew binary, or None if not found."""
    candidates = [
        shutil.which("brew"),
        "/opt/homebrew/bin/brew",   # Apple Silicon default
        "/usr/local/bin/brew",      # Intel Mac default
    ]
    for path in candidates:
        if path and Path(path).is_file():
            return path
    return None


def check_homebrew() -> Optional[str]:
    """Returns brew path if found, None otherwise."""
    header("Homebrew")
    brew = find_brew()
    if brew is None:
        warn("Homebrew not found.")
        print(
            "\n  Install Homebrew:\n"
            '    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"\n'
            "\n  Then re-run this script.\n"
        )
        return None

    result = run([brew, "--version"], capture=True)
    ok(f"{result.stdout.splitlines()[0].strip()} at {brew}")
    return brew


# ─────────────────────────────────────────────────────────────────────────────
# 3. System packages
# ─────────────────────────────────────────────────────────────────────────────
def install_brew_packages(brew: Optional[str]) -> None:
    header("System packages (portaudio, ffmpeg)")
    if not brew:
        warn("Skipping — Homebrew not available.")
        return

    for pkg in ["portaudio", "ffmpeg"]:
        result = run([brew, "list", "--formula", pkg], check=False, capture=True)
        if result.returncode == 0:
            ok(f"{pkg} already installed.")
        else:
            info(f"Installing {pkg}…")
            try:
                run([brew, "install", pkg])
                ok(f"{pkg} installed.")
            except subprocess.CalledProcessError:
                fail(f"brew install {pkg} failed — try manually.")


# ─────────────────────────────────────────────────────────────────────────────
# 4. Find the best available Python 3.11+
# ─────────────────────────────────────────────────────────────────────────────
def find_python311(brew: Optional[str]) -> Optional[str]:
    """
    Return a path to a Python 3.11+ binary, preferring the highest version.
    Checks PATH, Homebrew Cellar, and python.org installer locations.
    """
    # Derive Homebrew prefix from brew binary
    brew_prefix = str(Path(brew).parent.parent) if brew else ""

    candidates = [
        # Homebrew-managed pythons
        f"{brew_prefix}/bin/python3.13",
        f"{brew_prefix}/bin/python3.12",
        f"{brew_prefix}/bin/python3.11",
        # python.org installers on macOS
        "/Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13",
        "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12",
        "/Library/Frameworks/Python.framework/Versions/3.11/bin/python3.11",
        # PATH-accessible shims (pyenv, asdf, etc.)
        shutil.which("python3.13"),
        shutil.which("python3.12"),
        shutil.which("python3.11"),
    ]

    for path in candidates:
        if path and Path(path).is_file():
            return path
    return None


# ─────────────────────────────────────────────────────────────────────────────
# 5. Virtual environment
# ─────────────────────────────────────────────────────────────────────────────
def setup_venv(brew: Optional[str]) -> Optional[Path]:
    header("Python virtual environment (.venv)")
    venv_path = PROJECT_ROOT / ".venv"

    # Decide which Python binary to use — prefer 3.11+ but accept 3.9+
    if (sys.version_info[0], sys.version_info[1]) >= (3, 9):
        python_bin = sys.executable
    else:
        python_bin = find_python311(brew)
        if python_bin is None:
            fail(
                "No Python 3.9+ found — cannot create venv. "
                "Install Python 3.11 (brew install python@3.11) and re-run."
            )
            return None

    result = run([python_bin, "--version"], capture=True)
    info(f"Using: {python_bin}  ({result.stdout.strip() or result.stderr.strip()})")

    if venv_path.exists():
        ok(f".venv already exists at {venv_path}")
    else:
        info("Creating .venv…")
        run([python_bin, "-m", "venv", str(venv_path)])
        ok(f".venv created at {venv_path}")

    return venv_path


# ─────────────────────────────────────────────────────────────────────────────
# 6. Python packages
# ─────────────────────────────────────────────────────────────────────────────
def install_python_packages(venv_path: Optional[Path]) -> None:
    header("Python packages")
    if venv_path is None:
        warn("Skipping — no venv available.")
        return

    pip = venv_path / "bin" / "pip"
    requirements = PROJECT_ROOT / "requirements.txt"

    if not requirements.exists():
        fail(f"requirements.txt not found at {requirements}")
        return

    info("Upgrading pip…")
    run([str(pip), "install", "--upgrade", "pip"], capture=True)

    info("Installing packages from requirements.txt…")
    try:
        run([str(pip), "install", "-r", str(requirements)])
        ok("All Python packages installed.")
    except subprocess.CalledProcessError:
        fail("Package installation failed — see output above.")


# ─────────────────────────────────────────────────────────────────────────────
# 7. Directories
# ─────────────────────────────────────────────────────────────────────────────
def create_directories() -> None:
    header("Directory structure")
    for d in [PROJECT_ROOT / "bin", PROJECT_ROOT / "models" / "piper"]:
        d.mkdir(parents=True, exist_ok=True)
        ok(f"{d.relative_to(PROJECT_ROOT)}/")


# ─────────────────────────────────────────────────────────────────────────────
# 8. Piper TTS binary (macOS ARM64)
#
# The tarball unpacks as:
#   piper/
#     piper           ← the binary
#     espeak-ng-data/ ← required data (must stay alongside the binary)
#     libpiper_phonemize.1.dylib
#     libonnxruntime.1.14.1.dylib
#     ...
#
# We extract the whole piper/ directory to bin/, giving:
#   bin/piper/piper          ← PIPER_BIN in config/settings.py
#   bin/piper/espeak-ng-data/
# ─────────────────────────────────────────────────────────────────────────────
PIPER_VERSION     = "2023.11.14-2"
PIPER_ARCHIVE     = "piper_macos_aarch64.tar.gz"
PIPER_DOWNLOAD_URL = (
    f"https://github.com/rhasspy/piper/releases/download/{PIPER_VERSION}/{PIPER_ARCHIVE}"
)
PIPER_DIR         = PROJECT_ROOT / "bin" / "piper"      # extracted directory
PIPER_BIN_DEST    = PIPER_DIR / "piper"                 # actual binary


def download_piper_binary() -> None:
    header("Piper TTS binary")

    if PIPER_BIN_DEST.exists():
        ok(f"Piper binary already at {PIPER_BIN_DEST.relative_to(PROJECT_ROOT)}")
        return

    machine = platform.machine()
    if machine != "arm64":
        warn(
            f"Architecture is '{machine}' — this script downloads the ARM64 build. "
            "For Intel, grab the correct release manually:\n"
            "  https://github.com/rhasspy/piper/releases"
        )

    archive_path = PROJECT_ROOT / "bin" / PIPER_ARCHIVE
    info(f"Downloading Piper {PIPER_VERSION} (macOS ARM64)…")
    info(f"  {PIPER_DOWNLOAD_URL}")

    try:
        _download_with_progress(PIPER_DOWNLOAD_URL, archive_path)
    except Exception as exc:
        fail(f"Download failed: {exc}")
        info(
            "Download manually from:\n"
            "  https://github.com/rhasspy/piper/releases\n"
            f"  Extract so that the binary is at: {PIPER_BIN_DEST}"
        )
        return

    info("Extracting…")
    try:
        # Extract to bin/ — creates bin/piper/ with binary + shared libs + data
        with tarfile.open(archive_path, "r:gz") as tar:
            tar.extractall(path=PROJECT_ROOT / "bin")
    except Exception as exc:
        fail(f"Extraction failed: {exc}")
        archive_path.unlink(missing_ok=True)
        return

    archive_path.unlink(missing_ok=True)

    if PIPER_BIN_DEST.exists():
        PIPER_BIN_DEST.chmod(0o755)
        ok(f"Piper binary ready at {PIPER_BIN_DEST.relative_to(PROJECT_ROOT)}")
    else:
        # List what was actually extracted so the user can debug
        extracted = list((PROJECT_ROOT / "bin").iterdir())
        fail(
            f"Binary not found at expected path: {PIPER_BIN_DEST.relative_to(PROJECT_ROOT)}\n"
            f"  Extracted contents of bin/: {[p.name for p in extracted]}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 9. Piper voice model (en_US-lessac-medium)
# ─────────────────────────────────────────────────────────────────────────────
VOICE_NAME     = "en_US-lessac-medium"
VOICE_BASE_URL = (
    "https://huggingface.co/rhasspy/piper-voices/resolve/main"
    "/en/en_US/lessac/medium"
)
VOICE_FILES = [
    (f"{VOICE_BASE_URL}/en_US-lessac-medium.onnx",      f"{VOICE_NAME}.onnx"),
    (f"{VOICE_BASE_URL}/en_US-lessac-medium.onnx.json", f"{VOICE_NAME}.onnx.json"),
]
VOICE_DIR = PROJECT_ROOT / "models" / "piper"


def download_piper_voice() -> None:
    header("Piper voice model (en_US-lessac-medium)")

    if all((VOICE_DIR / fname).exists() for _, fname in VOICE_FILES):
        ok("Voice model files already present.")
        return

    for url, filename in VOICE_FILES:
        dest = VOICE_DIR / filename
        if dest.exists():
            ok(f"{filename} already present.")
            continue
        info(f"Downloading {filename}…")
        try:
            _download_with_progress(url, dest)
            ok(f"{filename} downloaded.")
        except Exception as exc:
            fail(f"Failed to download {filename}: {exc}")
            info(
                "Download manually from:\n"
                "  https://huggingface.co/rhasspy/piper-voices\n"
                f"  Place files in: {VOICE_DIR}"
            )


# ─────────────────────────────────────────────────────────────────────────────
# 10. Ollama
# ─────────────────────────────────────────────────────────────────────────────
def check_ollama(brew: Optional[str]) -> None:
    header("Ollama")
    brew_prefix = str(Path(brew).parent.parent) if brew else ""
    ollama = (
        shutil.which("ollama")
        or (Path(brew_prefix) / "bin" / "ollama" if brew_prefix else None)
        or Path("/usr/local/bin/ollama")
    )
    # Resolve to actual path string and verify it exists
    ollama_path = str(ollama) if ollama and Path(str(ollama)).is_file() else None

    if ollama_path:
        result = run([ollama_path, "--version"], capture=True, check=False)
        version = (result.stdout + result.stderr).strip()
        ok(f"Ollama found ({version})")
        info("To pull the default model:  ollama pull llama3.2:3b")
    else:
        warn("Ollama not found.")
        print(
            "\n  Install Ollama from: https://ollama.com\n"
            "  Then:\n"
            "    ollama pull llama3.2:3b\n"
            "    ollama serve\n"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Helper: download with progress bar
# ─────────────────────────────────────────────────────────────────────────────
def _download_with_progress(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url) as resp:
        total = int(resp.headers.get("Content-Length", 0))
        downloaded = 0
        with open(dest, "wb") as f:
            while chunk := resp.read(256 * 1024):
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = downloaded / total * 100
                    mb = downloaded / 1024 / 1024
                    print(f"\r    {pct:5.1f}%  {mb:.1f} MB", end="", flush=True)
        print()


# ─────────────────────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────────────────────
def print_summary(venv_path: Optional[Path]) -> None:
    venv_python = str(venv_path / "bin" / "python") if venv_path else "python3.11"

    if _issues:
        print(f"\n{BOLD}{YELLOW}── Issues to resolve before running PPT {'─' * 18}{RESET}")
        for i, issue in enumerate(_issues, 1):
            print(f"  {YELLOW}{i}. {issue}{RESET}")

    print(f"""
{BOLD}{'─' * 64}
  Phase 0 setup — next steps
{'─' * 64}{RESET}

  1. Activate the virtual environment:
       source .venv/bin/activate

  2. Start Ollama (if not already running):
       ollama serve
     Pull the model if you haven't yet (new terminal):
       ollama pull llama3.2:3b

  3. Test each layer:
       python start.py test wake
       python start.py test stt
       python start.py test llm
       python start.py test tts

  4. Run the full pipeline:
       python start.py run

{BOLD}{'─' * 64}{RESET}
""")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
def main() -> None:
    print(f"\n{BOLD}PPT Phase 0 — Setup Script{RESET}")
    print(f"Project root: {PROJECT_ROOT}\n")

    check_python()                          # warn only — don't exit
    brew       = check_homebrew()
    install_brew_packages(brew)
    create_directories()
    venv       = setup_venv(brew)
    install_python_packages(venv)
    download_piper_binary()
    download_piper_voice()
    check_ollama(brew)
    print_summary(venv)


if __name__ == "__main__":
    main()
