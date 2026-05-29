"""HTTP fetching and URL verification."""

from __future__ import annotations

import json
import base64
import hashlib
import os
import pathlib
import ssl
import time
import urllib.error
import urllib.request
from typing import Any

from .config import BLOCKED_SIGNAL_CHECKS, FETCH_POLICY, USER_AGENT
from .html_tools import extract_links, extract_metadata
from .models import FetchCheck
from .text import unique


_CACHE_ENABLED = False
_CACHE_DIR = ""
_CACHE_STATS = {"enabled": False, "hits": 0, "misses": 0, "writes": 0, "errors": 0}
_RETRY_STATS = {"attempts": 0, "retries": 0, "retry_statuses": {}, "errors": 0}


def default_cache_dir() -> str:
    return os.getenv("DEEP_SEARCH_CACHE_DIR") or os.path.expanduser("~/.cache/insane-deep-search")


def set_transport_options(*, cache_enabled: bool = False, cache_dir: str | None = None) -> None:
    global _CACHE_ENABLED, _CACHE_DIR
    _CACHE_ENABLED = cache_enabled
    _CACHE_DIR = cache_dir or default_cache_dir()
    _CACHE_STATS["enabled"] = cache_enabled


def reset_transport_stats() -> None:
    _CACHE_STATS.update({"enabled": _CACHE_ENABLED, "hits": 0, "misses": 0, "writes": 0, "errors": 0})
    _RETRY_STATS.update({"attempts": 0, "retries": 0, "retry_statuses": {}, "errors": 0})


def transport_stats() -> tuple[dict[str, object], dict[str, object]]:
    return dict(_CACHE_STATS), {"attempts": _RETRY_STATS["attempts"], "retries": _RETRY_STATS["retries"], "retry_statuses": dict(_RETRY_STATS["retry_statuses"]), "errors": _RETRY_STATS["errors"]}


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


def cache_headers(headers: dict[str, str]) -> dict[str, str]:
    return {key.lower(): value for key, value in headers.items() if key.lower() not in {"authorization", "x-api-key", "cookie"}}


def cache_key(url: str, headers: dict[str, str]) -> str:
    payload = json.dumps({"url": url, "headers": cache_headers(headers)}, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def cache_path(url: str, headers: dict[str, str]) -> pathlib.Path:
    return pathlib.Path(_CACHE_DIR or default_cache_dir()) / (cache_key(url, headers) + ".json")


def read_cache(url: str, headers: dict[str, str]) -> tuple[bytes, int | None, str, str, int, str] | None:
    if not _CACHE_ENABLED:
        return None
    path = cache_path(url, headers)
    if not path.exists():
        _CACHE_STATS["misses"] += 1
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        age = time.time() - float(data.get("created_at") or 0)
        raw_status = data.get("status")
        status = int(raw_status) if raw_status is not None else None
        ttl = FETCH_POLICY.success_cache_ttl_seconds if status and status < 400 and not data.get("error") else FETCH_POLICY.failure_cache_ttl_seconds
        if age > ttl:
            _CACHE_STATS["misses"] += 1
            return None
        _CACHE_STATS["hits"] += 1
        body = base64.b64decode(str(data.get("body") or ""))
        return body, status, str(data.get("content_type") or ""), str(data.get("final_url") or url), 0, str(data.get("error") or "")
    except Exception:
        _CACHE_STATS["errors"] += 1
        return None


def write_cache(url: str, headers: dict[str, str], response: tuple[bytes, int | None, str, str, int, str]) -> None:
    if not _CACHE_ENABLED:
        return
    body, status, content_type, final_url, _elapsed_ms, error = response
    try:
        path = cache_path(url, headers)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "created_at": time.time(),
            "status": status,
            "content_type": content_type,
            "final_url": final_url,
            "error": error,
            "body": base64.b64encode(body).decode("ascii"),
        }
        path.write_text(json.dumps(payload), encoding="utf-8")
        _CACHE_STATS["writes"] += 1
    except Exception:
        _CACHE_STATS["errors"] += 1


def fetch_bytes_once(url: str, timeout: float, headers: dict[str, str]) -> tuple[bytes, int | None, str, str, int, str]:
    start = time.monotonic()
    try:
        try:
            from curl_cffi import requests as curl_requests  # type: ignore

            response = curl_requests.get(
                url,
                headers=headers,
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

        request = urllib.request.Request(url, headers=headers)
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


def fetch_bytes(url: str, timeout: float = 12.0, headers: dict[str, str] | None = None) -> tuple[bytes, int | None, str, str, int, str]:
    request_headers = http_headers(headers)
    cached = read_cache(url, request_headers)
    if cached is not None:
        return cached

    response: tuple[bytes, int | None, str, str, int, str] = (b"", None, "", url, 0, "")
    for attempt in range(FETCH_POLICY.max_retries + 1):
        _RETRY_STATS["attempts"] += 1
        response = fetch_bytes_once(url, timeout, request_headers)
        _body, status, _content_type, _final_url, _elapsed_ms, error = response
        retryable = status in FETCH_POLICY.retry_statuses or (error and attempt == 0)
        if not retryable or attempt >= FETCH_POLICY.max_retries:
            break
        _RETRY_STATS["retries"] += 1
        label = str(status) if status is not None else "error"
        retry_statuses = _RETRY_STATS["retry_statuses"]
        retry_statuses[label] = int(retry_statuses.get(label, 0)) + 1
        time.sleep(FETCH_POLICY.retry_backoff_seconds * (attempt + 1))
    if response[5]:
        _RETRY_STATS["errors"] += 1
    write_cache(url, request_headers, response)
    return response


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
