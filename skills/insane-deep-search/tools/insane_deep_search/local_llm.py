"""Local Ollama-backed planning helpers.

This module intentionally uses only localhost Ollama. It never calls hosted
LLM APIs and it never requires an API key.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from .config import DEFAULT_LOCAL_LLM_MODEL, DEFAULT_OLLAMA_HOST, LOCAL_LLM_FALLBACK_MODELS


def configured_model(model: str | None = None) -> str:
    return model or os.getenv("DEEP_SEARCH_LOCAL_LLM_MODEL") or DEFAULT_LOCAL_LLM_MODEL


def ollama_host() -> str:
    return (os.getenv("DEEP_SEARCH_OLLAMA_HOST") or DEFAULT_OLLAMA_HOST).rstrip("/")


def local_llm_timeout(default: float = 20.0) -> float:
    try:
        return float(os.getenv("DEEP_SEARCH_LOCAL_LLM_TIMEOUT") or default)
    except ValueError:
        return default


def model_candidates(model: str | None = None) -> list[str]:
    preferred = configured_model(model)
    ordered = [preferred, *LOCAL_LLM_FALLBACK_MODELS]
    seen: set[str] = set()
    result: list[str] = []
    for item in ordered:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def extract_json_object(text: str) -> dict[str, Any]:
    """Parse a JSON object from a model response."""
    value = (text or "").strip()
    if not value:
        raise ValueError("empty local LLM response")
    try:
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    start = value.find("{")
    end = value.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("local LLM response did not contain a JSON object")
    parsed = json.loads(value[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("local LLM response JSON was not an object")
    return parsed


def ollama_generate(prompt: str, *, model: str, timeout: float = 20.0) -> str:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.1, "top_p": 0.9},
    }
    request = urllib.request.Request(
        ollama_host() + "/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = json.loads(response.read().decode("utf-8", errors="replace"))
    return str(data.get("response") or "")


def generate_json(
    prompt: str,
    *,
    mode: str = "auto",
    model: str | None = None,
    timeout: float | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Return parsed JSON and local LLM status metadata."""
    status: dict[str, Any] = {
        "provider": "ollama",
        "mode": mode,
        "requested_model": configured_model(model),
        "used_model": "",
        "attempted_models": [],
        "available": False,
        "fallback": False,
        "error": "",
    }
    if mode == "off":
        status["fallback"] = True
        status["error"] = "local LLM disabled"
        return None, status
    if mode not in {"auto", "required"}:
        raise ValueError(f"Unknown local_llm mode: {mode}")

    last_error = ""
    effective_timeout = local_llm_timeout() if timeout is None else timeout
    for candidate in model_candidates(model):
        status["attempted_models"].append(candidate)
        try:
            parsed = extract_json_object(ollama_generate(prompt, model=candidate, timeout=effective_timeout))
            status["used_model"] = candidate
            status["available"] = True
            return parsed, status
        except (OSError, urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            last_error = str(exc)
            continue
    status["fallback"] = True
    status["error"] = last_error or "local LLM unavailable"
    return None, status
