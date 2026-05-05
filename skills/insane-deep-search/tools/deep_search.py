#!/usr/bin/env python3
"""Compatibility entrypoint for Insane Deep Search."""

from __future__ import annotations

from insane_deep_search import *  # noqa: F401,F403
from insane_deep_search.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
