#!/usr/bin/env python3
"""Environment check for Insane Deep Search."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "deep_search.py"


def module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def main() -> int:
    errors: list[str] = []

    if sys.version_info < (3, 10):
        errors.append("Python 3.10 or newer is recommended.")

    if not TOOL.exists():
        errors.append(f"Missing tool: {TOOL}")

    optional = {
        "curl_cffi": "optional browser-like HTTP client",
        "certifi": "optional CA bundle for urllib TLS verification",
    }

    print("Insane Deep Search environment")
    print(f"- skill root: {ROOT}")
    print(f"- python: {sys.version.split()[0]}")
    print(f"- deep_search.py: {'OK' if TOOL.exists() else 'MISSING'}")

    for module, label in optional.items():
        status = "available" if module_available(module) else "not installed"
        print(f"- {module}: {status} ({label})")

    if errors:
        print("\nProblems:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("\nReady.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
