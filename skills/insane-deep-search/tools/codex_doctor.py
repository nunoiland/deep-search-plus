#!/usr/bin/env python3
"""Environment and structure check for Insane Deep Search."""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
REPO_ROOT = ROOT.parents[1]
TOOL = TOOLS / "deep_search.py"
PACKAGE = TOOLS / "insane_deep_search"
FORBIDDEN_BRANDING_TERMS = (
    "Cla" + "ude",
    "cla" + "ude",
    "클" + "로드",
    "five" + "taku",
    "gp" + "taku",
    "insane" + "-search",
    "." + "cla" + "ude-plugin",
)
FORBIDDEN_BRANDING = re.compile("|".join(re.escape(term) for term in FORBIDDEN_BRANDING_TERMS))


def module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def tracked_text_files() -> list[Path]:
    ignored_parts = {".git", "__pycache__"}
    files: list[Path] = []
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file() or any(part in ignored_parts for part in path.parts):
            continue
        if path.suffix in {".pyc", ".png", ".jpg", ".jpeg", ".gif"}:
            continue
        files.append(path)
    return files


def branding_errors() -> list[str]:
    errors: list[str] = []
    for path in tracked_text_files():
        try:
            text = path.read_text(errors="ignore")
        except Exception:
            continue
        if FORBIDDEN_BRANDING.search(text):
            errors.append(f"forbidden branding in {path.relative_to(REPO_ROOT)}")
    return errors


def package_errors() -> list[str]:
    required = [
        PACKAGE / "__init__.py",
        PACKAGE / "cli.py",
        PACKAGE / "config.py",
        PACKAGE / "discovery.py",
        PACKAGE / "http.py",
        PACKAGE / "models.py",
        PACKAGE / "ranking.py",
        PACKAGE / "report.py",
        PACKAGE / "runner.py",
        PACKAGE / "source_catalog.py",
        PACKAGE / "sources" / "adapters.py",
    ]
    return [f"missing package file: {path.relative_to(ROOT)}" for path in required if not path.exists()]


def catalog_errors() -> list[str]:
    sys.path.insert(0, str(TOOLS))
    try:
        from insane_deep_search.source_catalog import validate_source_definitions
        from insane_deep_search.sources import SOURCES
    except Exception as exc:
        return [f"cannot import source catalog: {exc}"]

    errors = validate_source_definitions()
    names = [source.name for source in SOURCES]
    if len(names) != len(set(names)):
        errors.append("source registry has duplicate bound names")
    if not SOURCES:
        errors.append("source registry is empty")
    return errors


def main() -> int:
    errors: list[str] = []

    if sys.version_info < (3, 10):
        errors.append("Python 3.10 or newer is recommended.")

    if not TOOL.exists():
        errors.append(f"Missing tool: {TOOL}")

    errors.extend(package_errors())
    errors.extend(catalog_errors())
    errors.extend(branding_errors())

    optional = {
        "curl_cffi": "optional browser-like HTTP client",
        "certifi": "optional CA bundle for urllib TLS verification",
    }

    print("Insane Deep Search environment")
    print(f"- skill root: {ROOT}")
    print(f"- python: {sys.version.split()[0]}")
    print(f"- deep_search.py: {'OK' if TOOL.exists() else 'MISSING'}")
    print(f"- package: {'OK' if PACKAGE.exists() else 'MISSING'}")

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
