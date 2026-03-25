#!/usr/bin/env python3
"""
tests/run_all.py
Run every test file in the tests/ directory with pytest and print a summary.

Usage:
    python tests/run_all.py           # normal run
    python tests/run_all.py -v        # verbose output
    python tests/run_all.py --fast    # skip slow integration tests (needs_ollama)
"""

import subprocess
import sys
import os


def main() -> None:
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # Forward any extra CLI args (e.g. -v, -k, --fast) to pytest
    extra_args = sys.argv[1:]

    cmd = [
        sys.executable, "-m", "pytest",
        "tests/",
        "-v",
        "--tb=short",
        "--color=yes",
    ] + extra_args

    print("=" * 60)
    print("PPT test suite")
    print(f"Project root: {project_root}")
    print("=" * 60)

    result = subprocess.run(cmd, cwd=project_root)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
