"""Text, query, URL, and date helpers."""

from __future__ import annotations

import datetime as dt
import email.utils
import html
import re
import urllib.parse
from collections.abc import Iterable

from .config import LOW_VALUE_LINK_HINTS, LOW_VALUE_QUERY_PARAMS, SKIP_LINK_EXTENSIONS, STOPWORDS, TRACKING_PARAMS


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()


def unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        normalized = normalize_text(value)
        key = normalized.lower()
        if normalized and key not in seen:
            seen.add(key)
            ordered.append(normalized)
    return ordered


def tokenize(query: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9][A-Za-z0-9_.+-]*|[가-힣]{2,}", query)


def meaningful_tokens(value: str) -> list[str]:
    return [token for token in tokenize(value) if token.lower() not in STOPWORDS]


def generate_query_variants(query: str) -> list[str]:
    base = normalize_text(query)
    tokens = tokenize(base)
    meaningful = [token for token in tokens if token.lower() not in STOPWORDS]
    variants: list[str] = [base]

    if len(tokens) > 1:
        variants.append(f'"{base}"')

    if meaningful:
        variants.append(" ".join(meaningful[:6]))

    latin = [token for token in meaningful if re.search(r"[A-Za-z]", token)]
    korean = [token for token in meaningful if re.search(r"[가-힣]", token)]
    if latin and korean:
        variants.append(" ".join(latin[:6]))
        variants.append(" ".join(korean[:6]))

    if len(meaningful) > 3:
        variants.append(" ".join(meaningful[:3]))

    return unique(variants)


def canonicalize_url(url: str) -> str:
    value = (url or "").strip()
    if not value:
        return ""
    if value.startswith("//"):
        value = "https:" + value
    parsed = urllib.parse.urlsplit(value)
    if not parsed.scheme:
        return value

    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").lower()
    if parsed.port and not ((scheme == "http" and parsed.port == 80) or (scheme == "https" and parsed.port == 443)):
        host = f"{host}:{parsed.port}"
    path = urllib.parse.quote(urllib.parse.unquote(parsed.path or "/"), safe="/:@")
    if path != "/":
        path = path.rstrip("/")

    query_pairs = []
    for key, val in urllib.parse.parse_qsl(parsed.query, keep_blank_values=False):
        lower = key.lower()
        if lower.startswith("utm_") or lower in TRACKING_PARAMS:
            continue
        query_pairs.append((key, val))
    query = urllib.parse.urlencode(sorted(query_pairs), doseq=True)
    return urllib.parse.urlunsplit((scheme, host, path, query, ""))


def host_for(url: str) -> str:
    try:
        return (urllib.parse.urlsplit(url).hostname or "").lower()
    except Exception:
        return ""


def same_site(parent_url: str, child_url: str) -> bool:
    parent = host_for(parent_url)
    child = host_for(child_url)
    if not parent or not child:
        return False
    return child == parent or child.endswith("." + parent)


def is_http_url(url: str) -> bool:
    try:
        return urllib.parse.urlsplit(url).scheme.lower() in {"http", "https"}
    except Exception:
        return False


def has_skipped_extension(url: str) -> bool:
    path = urllib.parse.urlsplit(url).path.lower()
    return any(path.endswith(ext) for ext in SKIP_LINK_EXTENSIONS)


def is_low_value_link(url: str) -> bool:
    parsed = urllib.parse.urlsplit(url)
    path = parsed.path.lower().rstrip("/") or "/"
    if has_skipped_extension(url):
        return True
    if any(path == hint or path.endswith(hint) or f"{hint}/" in path for hint in LOW_VALUE_LINK_HINTS):
        return True
    query_keys = {key.lower().replace("-", "_") for key, _value in urllib.parse.parse_qsl(parsed.query)}
    return bool(query_keys & LOW_VALUE_QUERY_PARAMS)


def build_url(base: str, params: dict[str, object]) -> str:
    return base + "?" + urllib.parse.urlencode(params, doseq=True)


def parse_datetime(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    value = value.strip()
    try:
        parsed = email.utils.parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc)
    except Exception:
        pass
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = dt.datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc)
    except Exception:
        return None


def iso_from_timestamp(value: int | float | None) -> str | None:
    if value is None:
        return None
    try:
        return dt.datetime.fromtimestamp(float(value), tz=dt.timezone.utc).isoformat()
    except Exception:
        return None


def compact_url(url: str, limit: int = 120) -> str:
    return url if len(url) <= limit else url[: limit - 1] + "..."
