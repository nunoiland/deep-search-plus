"""Trace public-source access attempts without bypassing access controls."""

from __future__ import annotations

from typing import Any

from .models import FetchCheck, SearchError
from .text import compact_url


def classify_failure(*, status: int | None = None, verdict: str = "", message: str = "") -> str:
    text = f"{verdict} {message}".lower()
    if status in {401, 403} or "403" in text or "forbidden" in text:
        return "blocked"
    if status == 429 or "429" in text or "rate limit" in text:
        return "rate_limited"
    if "timeout" in text or "timed out" in text:
        return "timeout"
    if verdict in {"fail", "weak_fail"}:
        return "fetch_failed"
    if verdict == "weak_ok":
        return "weak_body"
    if not verdict and message:
        return "source_error"
    return "ok"


def error_ladder_trace(error: SearchError) -> dict[str, Any]:
    return {
        "phase": "source",
        "source": error.source,
        "pack": error.pack,
        "query_variant": error.query_variant,
        "failure_type": classify_failure(message=error.message),
        "steps": [
            {
                "step": "official_api_or_rss",
                "outcome": "failed",
                "message": error.message[:240],
            }
        ],
    }


def fetch_ladder_trace(
    *,
    url: str,
    verify_mode: str,
    basic: FetchCheck | None = None,
    rendered: FetchCheck | None = None,
    selected: FetchCheck | None = None,
) -> dict[str, Any]:
    selected_check = selected or rendered or basic
    steps: list[dict[str, Any]] = []
    if basic is not None:
        steps.append(
            {
                "step": "metadata_probe",
                "outcome": "ok" if basic.title or basic.description or basic.metadata.get("canonical") else "empty",
                "status": basic.status,
                "verdict": basic.verdict,
            }
        )
        steps.append(
            {
                "step": "archive_cache_candidate",
                "outcome": "recorded_not_fetched",
                "reason": "cache/archive candidates are informational only and do not bypass access controls",
            }
        )
        steps.append(
            {
                "step": "general_fetch",
                "outcome": basic.verdict,
                "status": basic.status,
                "body_size": basic.body_size,
                "blocked_signals": basic.blocked_signals,
            }
        )
    if verify_mode in {"auto", "rendered"}:
        steps.append(
            {
                "step": "render_fallback",
                "outcome": rendered.verdict if rendered else "skipped",
                "status": rendered.status if rendered else None,
                "body_size": rendered.body_size if rendered else 0,
                "error": rendered.error if rendered else "",
            }
        )
    return {
        "phase": "fetch",
        "url": url,
        "display_url": compact_url(url),
        "verify_mode": verify_mode,
        "failure_type": classify_failure(
            status=selected_check.status if selected_check else None,
            verdict=selected_check.verdict if selected_check else "",
            message=selected_check.error if selected_check else "",
        ),
        "selected_verdict": selected_check.verdict if selected_check else "not_checked",
        "steps": steps,
    }
