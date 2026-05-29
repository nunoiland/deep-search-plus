"""HTTP fetching and URL verification."""

from __future__ import annotations

import json
import ssl
import time
import urllib.error
import urllib.request
from typing import Any

from .config import BLOCKED_SIGNAL_CHECKS, FETCH_POLICY, USER_AGENT
from .html_tools import extract_links, extract_metadata
from .models import FetchCheck
from .text import unique


def http_headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json,text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    if extra:
        headers.update(extra)
    return headers


def urllib_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    try:
        import certifi  # type: ignore

        context.load_verify_locations(certifi.where())
    except Exception:
        pass
    return context


def fetch_bytes(url: str, timeout: float = 12.0, headers: dict[str, str] | None = None) -> tuple[bytes, int | None, str, str, int, str]:
    start = time.monotonic()
    request_headers = http_headers(headers)
    try:
        try:
            from curl_cffi import requests as curl_requests  # type: ignore

            response = curl_requests.get(
                url,
                headers=request_headers,
                timeout=timeout,
                impersonate="chrome",
                allow_redirects=True,
            )
            elapsed_ms = int((time.monotonic() - start) * 1000)
            return (
                bytes(response.content or b""),
                int(response.status_code),
                response.headers.get("content-type", ""),
                str(response.url),
                elapsed_ms,
                "",
            )
        except ImportError:
            pass

        request = urllib.request.Request(url, headers=request_headers)
        with urllib.request.urlopen(request, timeout=timeout, context=urllib_context()) as response:
            body = response.read()
            elapsed_ms = int((time.monotonic() - start) * 1000)
            return (
                body,
                int(response.status),
                response.headers.get("content-type", ""),
                response.geturl(),
                elapsed_ms,
                "",
            )
    except urllib.error.HTTPError as exc:
        body = exc.read() if hasattr(exc, "read") else b""
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return body, int(exc.code), exc.headers.get("content-type", ""), exc.geturl(), elapsed_ms, str(exc)
    except Exception as exc:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return b"", None, "", url, elapsed_ms, str(exc)


def read_text(url: str, timeout: float = 12.0, headers: dict[str, str] | None = None) -> str:
    body, status, _content_type, _final_url, _elapsed_ms, error = fetch_bytes(url, timeout, headers)
    if error and not body:
        raise RuntimeError(error)
    if status and status >= 400:
        raise RuntimeError(f"HTTP {status}")
    return body.decode("utf-8", errors="replace")


def read_json(url: str, timeout: float = 12.0, headers: dict[str, str] | None = None) -> Any:
    return json.loads(read_text(url, timeout, headers))


def detect_blocked_signals(text: str, status: int | None) -> list[str]:
    haystack = text[:80_000].lower()
    signals = []
    for needle, label in BLOCKED_SIGNAL_CHECKS.items():
        if needle in haystack:
            signals.append(label)
    if status in FETCH_POLICY.blocked_statuses:
        signals.append(f"HTTP {status}")
    return unique(signals)


def fetch_verdict(status: int | None, body_size: int, error: str, signals: list[str]) -> str:
    if error and not body_size:
        return "fail"
    if status in FETCH_POLICY.blocked_statuses or signals:
        return "blocked"
    if status is not None and status >= FETCH_POLICY.weak_failure_min_status:
        return "weak_fail"
    if status is not None and 200 <= status < 300 and body_size >= FETCH_POLICY.strong_min_bytes:
        return "strong_ok"
    if status is not None and 200 <= status < 400 and body_size >= FETCH_POLICY.weak_min_bytes:
        return "weak_ok"
    return "fail"


def verify_url(url: str, timeout: float = 12.0, link_limit: int = 0) -> FetchCheck:
    body, status, content_type, final_url, elapsed_ms, error = fetch_bytes(url, timeout)
    text = body[:100_000].decode("utf-8", errors="replace")
    signals = detect_blocked_signals(text, status)
    metadata = extract_metadata(body, content_type) if body else {}
    links = extract_links(body, content_type, final_url or url, link_limit) if body else []
    verdict = fetch_verdict(status, len(body), error, signals)

    return FetchCheck(
        url=url,
        final_url=final_url,
        status=status,
        content_type=content_type,
        body_size=len(body),
        verdict=verdict,
        title=str(metadata.get("title", "")),
        description=str(metadata.get("description", "")),
        metadata=metadata,
        links=links,
        blocked_signals=signals,
        error=error,
        elapsed_ms=elapsed_ms,
    )
