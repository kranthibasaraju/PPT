#!/usr/bin/env python3
"""Run the full PPT test suite."""
import subprocess, sys
result = subprocess.run(
    [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=short"],
    cwd=str(__import__('pathlib').Path(__file__).parent.parent)
)
sys.exit(result.returncode)
