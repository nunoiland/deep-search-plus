#!/usr/bin/env python3
"""Codex-native public evidence deep search."""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import email.utils
import html
import json
import math
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from typing import Any, Callable, Iterable


USER_AGENT = "insane-deep-search/0.1 (+https://github.com/nunoiland/insane-deep-search)"
TRACKING_PARAMS = {
    "fbclid",
    "gclid",
    "igshid",
    "mc_cid",
    "mc_eid",
    "msclkid",
    "ref_src",
}
SKIP_LINK_EXTENSIONS = {
    ".7z",
    ".avi",
    ".css",
    ".gif",
    ".ico",
    ".jpeg",
    ".jpg",
    ".js",
    ".m4a",
    ".m4v",
    ".mov",
    ".mp3",
    ".mp4",
    ".ogg",
    ".png",
    ".rar",
    ".svg",
    ".tar",
    ".webm",
    ".webp",
    ".woff",
    ".woff2",
    ".zip",
}
LOW_VALUE_LINK_HINTS = {
    "/about",
    "/account",
    "/advertise",
    "/contact",
    "/cookie",
    "/help",
    "/login",
    "/privacy",
    "/register",
    "/search",
    "/share",
    "/signin",
    "/signup",
    "/subscribe",
    "/terms",
}
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "by",
    "for",
    "from",
    "how",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
    "관련",
    "검색",
    "뉴스",
    "정보",
    "확인",
    "찾아줘",
    "해외",
    "포함",
}


@dataclasses.dataclass
class SearchContext:
    original_query: str
    depth: str
    locale: str
    limit: int
    timeout: float


@dataclasses.dataclass
class SearchError:
    source: str
    pack: str
    query_variant: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass
class FetchCheck:
    url: str
    final_url: str = ""
    status: int | None = None
    content_type: str = ""
    body_size: int = 0
    verdict: str = "not_checked"
    title: str = ""
    description: str = ""
    metadata: dict[str, Any] = dataclasses.field(default_factory=dict)
    links: list[dict[str, str]] = dataclasses.field(default_factory=list)
    blocked_signals: list[str] = dataclasses.field(default_factory=list)
    error: str = ""
    elapsed_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass
class SearchResult:
    source: str
    title: str
    url: str
    snippet: str = ""
    published: str | None = None
    score: float = 0.0
    pack: str = ""
    source_type: str = ""
    query_variant: str = ""
    canonical_url: str = ""
    rank_score: float = 0.0
    evidence_level: str = "weak"
    fetched: bool = False
    fetch_verdict: str | None = None
    metadata: dict[str, Any] = dataclasses.field(default_factory=dict)
    errors: list[str] = dataclasses.field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = dataclasses.asdict(self)
        data["score"] = round(float(self.score), 3)
        data["rank_score"] = round(float(self.rank_score), 3)
        return data


@dataclasses.dataclass
class SourceSpec:
    name: str
    pack: str
    source_type: str
    trust_weight: float
    adapter: Callable[[str, SearchContext], list[SearchResult]]


@dataclasses.dataclass
class SearchRun:
    query: str
    depth: str
    packs: list[str]
    locale: str
    query_variants: list[str]
    detective: bool = False
    dig_pages: int = 0
    results: list[SearchResult] = dataclasses.field(default_factory=list)
    errors: list[SearchError] = dataclasses.field(default_factory=list)
    fetched_urls: list[FetchCheck] = dataclasses.field(default_factory=list)
    discovered_urls: list[str] = dataclasses.field(default_factory=list)
    elapsed_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "depth": self.depth,
            "packs": self.packs,
            "locale": self.locale,
            "query_variants": self.query_variants,
            "detective": self.detective,
            "dig_pages": self.dig_pages,
            "results": [result.to_dict() for result in self.results],
            "errors": [error.to_dict() for error in self.errors],
            "fetched_urls": [fetch.to_dict() for fetch in self.fetched_urls],
            "discovered_urls": self.discovered_urls,
            "top_evidence_urls": [result.url for result in self.results[:10]],
            "elapsed_ms": self.elapsed_ms,
        }


class MetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_title = False
        self.title_parts: list[str] = []
        self.meta: dict[str, str] = {}
        self.canonical = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {key.lower(): value or "" for key, value in attrs}
        if tag.lower() == "title":
            self.in_title = True
        elif tag.lower() == "meta":
            key = (attrs_dict.get("name") or attrs_dict.get("property") or "").lower()
            content = attrs_dict.get("content", "")
            if key and content and key not in self.meta:
                self.meta[key] = content.strip()
        elif tag.lower() == "link":
            rel = attrs_dict.get("rel", "").lower()
            href = attrs_dict.get("href", "")
            if "canonical" in rel and href:
                self.canonical = href.strip()

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self.in_title = False

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title_parts.append(data)

    @property
    def title(self) -> str:
        return normalize_text(" ".join(self.title_parts))

    @property
    def description(self) -> str:
        return normalize_text(
            self.meta.get("description")
            or self.meta.get("og:description")
            or self.meta.get("twitter:description")
            or ""
        )


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[dict[str, str]] = []
        self._active: dict[str, str] | None = None
        self._text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        attrs_dict = {key.lower(): value or "" for key, value in attrs}
        href = attrs_dict.get("href", "").strip()
        if not href:
            return
        self._active = {
            "url": href,
            "text": normalize_text(attrs_dict.get("aria-label") or attrs_dict.get("title") or ""),
        }
        self._text_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or self._active is None:
            return
        text = normalize_text(" ".join(self._text_parts))
        if text:
            self._active["text"] = text
        self.links.append(self._active)
        self._active = None
        self._text_parts = []

    def handle_data(self, data: str) -> None:
        if self._active is not None:
            self._text_parts.append(data)


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
    return any(path == hint or path.endswith(hint) for hint in LOW_VALUE_LINK_HINTS)


def extract_links(body: bytes, content_type: str, base_url: str, limit: int = 25) -> list[dict[str, str]]:
    if limit <= 0:
        return []
    text = body[:500_000].decode("utf-8", errors="replace")
    if "html" not in content_type.lower() and "<a " not in text.lower():
        return []

    parser = LinkParser()
    try:
        parser.feed(text)
    except Exception:
        pass

    links: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in parser.links:
        href = raw.get("url", "").strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:", "data:")):
            continue
        absolute = urllib.parse.urljoin(base_url, href)
        canonical = canonicalize_url(absolute)
        if not canonical or not is_http_url(canonical) or is_low_value_link(canonical):
            continue
        if canonical in seen:
            continue
        seen.add(canonical)
        links.append({"url": canonical, "text": normalize_text(raw.get("text", ""))[:240]})
        if len(links) >= limit:
            break
    return links


def discovered_link_score(link: dict[str, str], query: str) -> float:
    tokens = [token.lower() for token in tokenize(query) if token.lower() not in STOPWORDS]
    if not tokens:
        return 0.0
    haystack_text = link.get("text", "").lower()
    haystack_url = link.get("url", "").lower()
    score = 0.0
    for token in tokens:
        if token in haystack_text:
            score += 2.5
        if token in haystack_url:
            score += 1.0
    path = urllib.parse.urlsplit(link.get("url", "")).path.lower()
    if re.search(r"/(article|news|post|story|report|research|docs?|issues?|pull|release|blog)/", path):
        score += 1.0
    return score


def build_url(base: str, params: dict[str, Any]) -> str:
    return base + "?" + urllib.parse.urlencode(params, doseq=True)


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


def fetch_bytes(url: str, timeout: float = 12.0) -> tuple[bytes, int | None, str, str, int, str]:
    start = time.monotonic()
    try:
        try:
            from curl_cffi import requests as curl_requests  # type: ignore

            response = curl_requests.get(
                url,
                headers=http_headers(),
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

        request = urllib.request.Request(url, headers=http_headers())
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


def read_text(url: str, timeout: float = 12.0) -> str:
    body, status, _content_type, _final_url, _elapsed_ms, error = fetch_bytes(url, timeout)
    if error and not body:
        raise RuntimeError(error)
    if status and status >= 400:
        raise RuntimeError(f"HTTP {status}")
    return body.decode("utf-8", errors="replace")


def read_json(url: str, timeout: float = 12.0) -> Any:
    return json.loads(read_text(url, timeout))


def extract_metadata(body: bytes, content_type: str) -> dict[str, Any]:
    text = body[:500_000].decode("utf-8", errors="replace")
    metadata: dict[str, Any] = {}

    if "html" in content_type.lower() or "<html" in text[:2000].lower():
        parser = MetadataParser()
        try:
            parser.feed(text)
        except Exception:
            pass
        metadata["title"] = parser.title
        metadata["description"] = parser.description
        metadata["canonical"] = parser.canonical
        metadata["og_title"] = normalize_text(parser.meta.get("og:title", ""))
        metadata["json_ld_count"] = len(re.findall(r'type=["\']application/ld\+json["\']', text, flags=re.I))
    elif "json" in content_type.lower():
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                metadata["json_keys"] = sorted(list(parsed.keys()))[:20]
            elif isinstance(parsed, list):
                metadata["json_items"] = len(parsed)
        except Exception:
            metadata["json_parse_error"] = True

    return {key: value for key, value in metadata.items() if value not in ("", [], None)}


def detect_blocked_signals(text: str, status: int | None) -> list[str]:
    haystack = text[:80_000].lower()
    signals = []
    checks = {
        "captcha": "captcha",
        "access denied": "access denied",
        "checking your browser": "browser challenge",
        "verify you are human": "human verification",
        "unusual traffic": "unusual traffic",
        "temporarily blocked": "temporary block",
        "rate limit": "rate limit",
    }
    for needle, label in checks.items():
        if needle in haystack:
            signals.append(label)
    if status in {401, 403, 429}:
        signals.append(f"HTTP {status}")
    return unique(signals)


def verify_url(url: str, timeout: float = 12.0, link_limit: int = 0) -> FetchCheck:
    body, status, content_type, final_url, elapsed_ms, error = fetch_bytes(url, timeout)
    text = body[:100_000].decode("utf-8", errors="replace")
    signals = detect_blocked_signals(text, status)
    metadata = extract_metadata(body, content_type) if body else {}
    links = extract_links(body, content_type, final_url or url, link_limit) if body else []

    if error and not body:
        verdict = "fail"
    elif status in {401, 403, 429} or signals:
        verdict = "blocked"
    elif status is not None and status >= 500:
        verdict = "weak_fail"
    elif status is not None and 200 <= status < 300 and len(body) >= 1200:
        verdict = "strong_ok"
    elif status is not None and 200 <= status < 400 and len(body) >= 200:
        verdict = "weak_ok"
    else:
        verdict = "fail"

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


def recency_score(published: str | None) -> float:
    parsed = parse_datetime(published)
    if not parsed:
        return 0.0
    age_days = max(0.0, (dt.datetime.now(dt.timezone.utc) - parsed).total_seconds() / 86400)
    if age_days <= 2:
        return 8.0
    if age_days <= 14:
        return 6.0
    if age_days <= 60:
        return 4.0
    if age_days <= 365:
        return 2.0
    return 0.5


def query_match_score(result: SearchResult, query: str) -> float:
    tokens = [token.lower() for token in tokenize(query) if token.lower() not in STOPWORDS]
    if not tokens:
        return 0.0
    title = result.title.lower()
    snippet = result.snippet.lower()
    title_hits = sum(1 for token in tokens if token in title)
    snippet_hits = sum(1 for token in tokens if token in snippet)
    return min(12.0, title_hits * 3.0 + snippet_hits * 1.2)


def rank_result(result: SearchResult, query: str, trust_weight: float | None = None) -> SearchResult:
    engagement = 0.0
    for key in ("points", "score", "comments", "stars", "downloads", "citations"):
        raw = result.metadata.get(key)
        if isinstance(raw, (int, float)) and raw > 0:
            engagement += math.log1p(raw)
    fetch_bonus = {"strong_ok": 5.0, "weak_ok": 2.0, "blocked": -1.0, "fail": -2.0, "weak_fail": -1.0}.get(
        result.fetch_verdict or "",
        0.0,
    )
    trust = trust_weight if trust_weight is not None else float(result.metadata.get("trust_weight", 1.0))
    result.rank_score = (
        result.score
        + trust
        + query_match_score(result, query)
        + recency_score(result.published)
        + min(8.0, engagement)
        + fetch_bonus
    )
    if result.source_type in {"research", "registry", "developer"} and result.rank_score >= 13:
        result.evidence_level = "strong"
    elif result.source_type == "news" and result.rank_score >= 12:
        result.evidence_level = "strong"
    elif result.source_type == "community":
        result.evidence_level = "medium" if result.rank_score >= 12 else "weak"
    else:
        result.evidence_level = "medium" if result.rank_score >= 9 else "weak"
    return result


def result(
    *,
    source: str,
    pack: str,
    source_type: str,
    query_variant: str,
    title: str,
    url: str,
    snippet: str = "",
    published: str | None = None,
    score: float = 0.0,
    metadata: dict[str, Any] | None = None,
) -> SearchResult:
    return SearchResult(
        source=source,
        pack=pack,
        source_type=source_type,
        query_variant=query_variant,
        title=normalize_text(title)[:500],
        url=url,
        canonical_url=canonicalize_url(url),
        snippet=normalize_text(snippet)[:1200],
        published=published,
        score=float(score),
        metadata=metadata or {},
    )


def parse_rss(text: str, source: str, variant: str, limit: int) -> list[SearchResult]:
    root = ET.fromstring(text)
    items = []
    for item in root.findall(".//item")[:limit]:
        title = item.findtext("title") or ""
        link = item.findtext("link") or ""
        description = item.findtext("description") or ""
        published = item.findtext("pubDate") or item.findtext("published")
        items.append(
            result(
                source=source,
                pack="news",
                source_type="news",
                query_variant=variant,
                title=title,
                url=link,
                snippet=re.sub(r"<[^>]+>", " ", description),
                published=published,
                score=5.0,
                metadata={"trust_weight": 4.0},
            )
        )
    return items


def google_news_ko(variant: str, context: SearchContext) -> list[SearchResult]:
    url = build_url(
        "https://news.google.com/rss/search",
        {"q": variant, "hl": "ko", "gl": "KR", "ceid": "KR:ko"},
    )
    return parse_rss(read_text(url, context.timeout), "google_news_ko", variant, context.limit)


def google_news_en(variant: str, context: SearchContext) -> list[SearchResult]:
    url = build_url(
        "https://news.google.com/rss/search",
        {"q": variant, "hl": "en-US", "gl": "US", "ceid": "US:en"},
    )
    return parse_rss(read_text(url, context.timeout), "google_news_en", variant, context.limit)


def reddit_search(variant: str, context: SearchContext) -> list[SearchResult]:
    data = read_json(
        build_url("https://www.reddit.com/search.json", {"q": variant, "sort": "relevance", "limit": context.limit, "raw_json": 1}),
        context.timeout,
    )
    items = []
    for child in data.get("data", {}).get("children", []):
        post = child.get("data", {})
        permalink = post.get("permalink") or ""
        url = "https://www.reddit.com" + permalink if permalink.startswith("/") else post.get("url", "")
        comments = int(post.get("num_comments") or 0)
        points = int(post.get("score") or 0)
        items.append(
            result(
                source="reddit",
                pack="community",
                source_type="community",
                query_variant=variant,
                title=post.get("title", ""),
                url=url,
                snippet=post.get("selftext", "")[:700],
                published=iso_from_timestamp(post.get("created_utc")),
                score=3.0,
                metadata={"subreddit": post.get("subreddit"), "comments": comments, "points": points, "trust_weight": 1.5},
            )
        )
    return items


def hacker_news_search(variant: str, context: SearchContext) -> list[SearchResult]:
    data = read_json(
        build_url("https://hn.algolia.com/api/v1/search", {"query": variant, "tags": "story", "hitsPerPage": context.limit}),
        context.timeout,
    )
    items = []
    for hit in data.get("hits", []):
        object_id = hit.get("objectID")
        url = hit.get("url") or f"https://news.ycombinator.com/item?id={object_id}"
        comments = int(hit.get("num_comments") or 0)
        points = int(hit.get("points") or 0)
        items.append(
            result(
                source="hacker_news",
                pack="community",
                source_type="community",
                query_variant=variant,
                title=hit.get("title") or hit.get("story_title") or "",
                url=url,
                snippet=hit.get("_highlightResult", {}).get("title", {}).get("value", ""),
                published=hit.get("created_at"),
                score=3.5,
                metadata={"comments": comments, "points": points, "discussion": f"https://news.ycombinator.com/item?id={object_id}", "trust_weight": 2.0},
            )
        )
    return items


def lobsters_search(variant: str, context: SearchContext) -> list[SearchResult]:
    if not re.search(r"[A-Za-z0-9]", variant):
        return []
    data = read_json(
        build_url("https://lobste.rs/search.json", {"q": variant, "what": "stories", "order": "relevance"}),
        context.timeout,
    )
    items = []
    for story in (data if isinstance(data, list) else [])[: context.limit]:
        comments = int(story.get("comment_count") or story.get("comments_count") or 0)
        score = int(story.get("score") or 0)
        items.append(
            result(
                source="lobsters",
                pack="community",
                source_type="community",
                query_variant=variant,
                title=story.get("title", ""),
                url=story.get("url") or story.get("comments_url", ""),
                snippet=" ".join(story.get("tags", []) if isinstance(story.get("tags"), list) else []),
                published=story.get("created_at"),
                score=2.5,
                metadata={"comments": comments, "points": score, "trust_weight": 1.5},
            )
        )
    return items


def first_tag_candidate(variant: str) -> str:
    for token in tokenize(variant):
        cleaned = re.sub(r"[^A-Za-z0-9]", "", token).lower()
        if len(cleaned) >= 2:
            return cleaned[:30]
    return ""


def devto_search(variant: str, context: SearchContext) -> list[SearchResult]:
    tag = first_tag_candidate(variant)
    if not tag:
        return []
    data = read_json(build_url("https://dev.to/api/articles", {"tag": tag, "per_page": context.limit}), context.timeout)
    items = []
    for article in data if isinstance(data, list) else []:
        items.append(
            result(
                source="devto",
                pack="community",
                source_type="community",
                query_variant=variant,
                title=article.get("title", ""),
                url=article.get("url", ""),
                snippet=article.get("description", ""),
                published=article.get("published_at"),
                score=2.0,
                metadata={
                    "tag": tag,
                    "comments": int(article.get("comments_count") or 0),
                    "points": int(article.get("public_reactions_count") or 0),
                    "trust_weight": 1.2,
                },
            )
        )
    return items


def v2ex_search(variant: str, context: SearchContext) -> list[SearchResult]:
    endpoints = ["https://www.v2ex.com/api/topics/hot.json", "https://www.v2ex.com/api/topics/latest.json"]
    tokens = [token.lower() for token in tokenize(variant)]
    items = []
    for endpoint in endpoints:
        data = read_json(endpoint, context.timeout)
        for topic in data if isinstance(data, list) else []:
            title = topic.get("title", "")
            content = topic.get("content", "")
            haystack = f"{title} {content}".lower()
            if tokens and not any(token in haystack for token in tokens):
                continue
            items.append(
                result(
                    source="v2ex",
                    pack="community",
                    source_type="community",
                    query_variant=variant,
                    title=title,
                    url=topic.get("url", ""),
                    snippet=content,
                    published=iso_from_timestamp(topic.get("created")),
                    score=2.0,
                    metadata={"comments": int(topic.get("replies") or 0), "trust_weight": 1.0},
                )
            )
            if len(items) >= context.limit:
                return items
    return items


def github_repositories(variant: str, context: SearchContext) -> list[SearchResult]:
    data = read_json(
        build_url("https://api.github.com/search/repositories", {"q": variant, "sort": "updated", "order": "desc", "per_page": context.limit}),
        context.timeout,
    )
    items = []
    for repo in data.get("items", []):
        items.append(
            result(
                source="github_repositories",
                pack="tech",
                source_type="developer",
                query_variant=variant,
                title=repo.get("full_name", ""),
                url=repo.get("html_url", ""),
                snippet=repo.get("description", ""),
                published=repo.get("updated_at"),
                score=4.0,
                metadata={
                    "stars": int(repo.get("stargazers_count") or 0),
                    "forks": int(repo.get("forks_count") or 0),
                    "language": repo.get("language"),
                    "trust_weight": 3.0,
                },
            )
        )
    return items


def github_issues(variant: str, context: SearchContext) -> list[SearchResult]:
    data = read_json(
        build_url("https://api.github.com/search/issues", {"q": variant, "sort": "updated", "order": "desc", "per_page": context.limit}),
        context.timeout,
    )
    items = []
    for issue in data.get("items", []):
        items.append(
            result(
                source="github_issues",
                pack="tech",
                source_type="developer",
                query_variant=variant,
                title=issue.get("title", ""),
                url=issue.get("html_url", ""),
                snippet=issue.get("body", "") or "",
                published=issue.get("updated_at"),
                score=3.5,
                metadata={
                    "comments": int(issue.get("comments") or 0),
                    "state": issue.get("state"),
                    "is_pull_request": "pull_request" in issue,
                    "trust_weight": 2.5,
                },
            )
        )
    return items


def stackoverflow_search(variant: str, context: SearchContext) -> list[SearchResult]:
    data = read_json(
        build_url(
            "https://api.stackexchange.com/2.3/search/advanced",
            {"order": "desc", "sort": "relevance", "q": variant, "site": "stackoverflow", "pagesize": context.limit},
        ),
        context.timeout,
    )
    items = []
    for question in data.get("items", []):
        items.append(
            result(
                source="stackoverflow",
                pack="tech",
                source_type="developer",
                query_variant=variant,
                title=question.get("title", ""),
                url=question.get("link", ""),
                snippet="; ".join(question.get("tags", [])),
                published=iso_from_timestamp(question.get("creation_date")),
                score=3.0,
                metadata={
                    "comments": int(question.get("answer_count") or 0),
                    "points": int(question.get("score") or 0),
                    "accepted_answer_id": question.get("accepted_answer_id"),
                    "trust_weight": 2.5,
                },
            )
        )
    return items


def npm_search(variant: str, context: SearchContext) -> list[SearchResult]:
    data = read_json(build_url("https://registry.npmjs.org/-/v1/search", {"text": variant, "size": context.limit}), context.timeout)
    items = []
    for package in data.get("objects", []):
        pkg = package.get("package", {})
        links = pkg.get("links", {})
        score_detail = package.get("score", {})
        items.append(
            result(
                source="npm",
                pack="tech",
                source_type="registry",
                query_variant=variant,
                title=pkg.get("name", ""),
                url=links.get("npm") or f"https://www.npmjs.com/package/{pkg.get('name', '')}",
                snippet=pkg.get("description", ""),
                published=pkg.get("date"),
                score=3.0 + float(score_detail.get("final") or 0),
                metadata={"version": pkg.get("version"), "publisher": (pkg.get("publisher") or {}).get("username"), "trust_weight": 3.0},
            )
        )
    return items


def package_candidates(variant: str) -> list[str]:
    candidates = []
    for token in tokenize(variant):
        cleaned = re.sub(r"[^A-Za-z0-9_.-]", "", token).strip("._-").lower()
        if 2 <= len(cleaned) <= 80:
            candidates.append(cleaned)
    return unique(candidates)[:4]


def pypi_lookup(variant: str, context: SearchContext) -> list[SearchResult]:
    items = []
    for name in package_candidates(variant):
        try:
            data = read_json(f"https://pypi.org/pypi/{urllib.parse.quote(name)}/json", context.timeout)
        except Exception:
            continue
        info = data.get("info", {})
        items.append(
            result(
                source="pypi",
                pack="tech",
                source_type="registry",
                query_variant=variant,
                title=info.get("name", name),
                url=info.get("package_url") or f"https://pypi.org/project/{name}/",
                snippet=info.get("summary", ""),
                published=info.get("release_url"),
                score=3.0,
                metadata={"version": info.get("version"), "license": info.get("license"), "trust_weight": 3.0},
            )
        )
        if len(items) >= context.limit:
            break
    return items


def huggingface_models(variant: str, context: SearchContext) -> list[SearchResult]:
    data = read_json(build_url("https://huggingface.co/api/models", {"search": variant, "limit": context.limit}), context.timeout)
    items = []
    for model in data if isinstance(data, list) else []:
        model_id = model.get("modelId") or model.get("id", "")
        items.append(
            result(
                source="huggingface_models",
                pack="tech",
                source_type="developer",
                query_variant=variant,
                title=model_id,
                url=f"https://huggingface.co/{model_id}",
                snippet=", ".join(model.get("tags", [])[:8]) if isinstance(model.get("tags"), list) else "",
                published=model.get("lastModified"),
                score=3.0,
                metadata={"downloads": int(model.get("downloads") or 0), "likes": int(model.get("likes") or 0), "trust_weight": 2.5},
            )
        )
    return items


def huggingface_datasets(variant: str, context: SearchContext) -> list[SearchResult]:
    data = read_json(build_url("https://huggingface.co/api/datasets", {"search": variant, "limit": context.limit}), context.timeout)
    items = []
    for dataset in data if isinstance(data, list) else []:
        dataset_id = dataset.get("id", "")
        items.append(
            result(
                source="huggingface_datasets",
                pack="tech",
                source_type="developer",
                query_variant=variant,
                title=dataset_id,
                url=f"https://huggingface.co/datasets/{dataset_id}",
                snippet=", ".join(dataset.get("tags", [])[:8]) if isinstance(dataset.get("tags"), list) else "",
                published=dataset.get("lastModified"),
                score=3.0,
                metadata={"downloads": int(dataset.get("downloads") or 0), "likes": int(dataset.get("likes") or 0), "trust_weight": 2.5},
            )
        )
    return items


def arxiv_search(variant: str, context: SearchContext) -> list[SearchResult]:
    text = read_text(
        build_url(
            "https://export.arxiv.org/api/query",
            {"search_query": f"all:{variant}", "start": 0, "max_results": context.limit, "sortBy": "relevance", "sortOrder": "descending"},
        ),
        context.timeout,
    )
    root = ET.fromstring(text)
    ns = {"a": "http://www.w3.org/2005/Atom"}
    items = []
    for entry in root.findall("a:entry", ns):
        title = entry.findtext("a:title", default="", namespaces=ns)
        link = ""
        for node in entry.findall("a:link", ns):
            if node.attrib.get("rel") == "alternate":
                link = node.attrib.get("href", "")
                break
        authors = [node.findtext("a:name", default="", namespaces=ns) for node in entry.findall("a:author", ns)]
        items.append(
            result(
                source="arxiv",
                pack="research",
                source_type="research",
                query_variant=variant,
                title=title,
                url=link,
                snippet=entry.findtext("a:summary", default="", namespaces=ns),
                published=entry.findtext("a:published", default="", namespaces=ns),
                score=4.0,
                metadata={"authors": [author for author in authors if author], "trust_weight": 4.0},
            )
        )
    return items


def crossref_search(variant: str, context: SearchContext) -> list[SearchResult]:
    data = read_json(build_url("https://api.crossref.org/works", {"query": variant, "rows": context.limit}), context.timeout)
    items = []
    for work in data.get("message", {}).get("items", []):
        title = " ".join(work.get("title", [])[:1])
        url = work.get("URL", "")
        published = None
        date_parts = (work.get("published-print") or work.get("published-online") or work.get("created") or {}).get("date-parts")
        if date_parts and date_parts[0]:
            parts = [int(part) for part in date_parts[0]]
            while len(parts) < 3:
                parts.append(1)
            published = dt.date(parts[0], parts[1], parts[2]).isoformat()
        items.append(
            result(
                source="crossref",
                pack="research",
                source_type="research",
                query_variant=variant,
                title=title,
                url=url,
                snippet="; ".join(work.get("subject", [])[:5]),
                published=published,
                score=4.0,
                metadata={
                    "doi": work.get("DOI"),
                    "citations": int(work.get("is-referenced-by-count") or 0),
                    "publisher": work.get("publisher"),
                    "trust_weight": 4.0,
                },
            )
        )
    return items


def openlibrary_search(variant: str, context: SearchContext) -> list[SearchResult]:
    data = read_json(build_url("https://openlibrary.org/search.json", {"q": variant, "limit": context.limit}), context.timeout)
    items = []
    for doc in data.get("docs", []):
        key = doc.get("key", "")
        year = doc.get("first_publish_year")
        published = f"{year}-01-01" if year else None
        items.append(
            result(
                source="openlibrary",
                pack="research",
                source_type="research",
                query_variant=variant,
                title=doc.get("title", ""),
                url=f"https://openlibrary.org{key}",
                snippet=", ".join(doc.get("author_name", [])[:4]) if isinstance(doc.get("author_name"), list) else "",
                published=published,
                score=2.5,
                metadata={"edition_count": doc.get("edition_count"), "trust_weight": 2.0},
            )
        )
    return items


def wikipedia_search(variant: str, context: SearchContext) -> list[SearchResult]:
    lang = "ko" if context.locale.lower().startswith("ko") else "en"
    data = read_json(
        build_url(
            f"https://{lang}.wikipedia.org/w/api.php",
            {"action": "opensearch", "search": variant, "limit": context.limit, "namespace": 0, "format": "json"},
        ),
        context.timeout,
    )
    titles = data[1] if len(data) > 1 else []
    descriptions = data[2] if len(data) > 2 else []
    urls = data[3] if len(data) > 3 else []
    items = []
    for title, description, url in zip(titles, descriptions, urls):
        items.append(
            result(
                source="wikipedia",
                pack="research",
                source_type="research",
                query_variant=variant,
                title=title,
                url=url,
                snippet=description,
                score=2.5,
                metadata={"language": lang, "trust_weight": 2.5},
            )
        )
    return items


SOURCES: list[SourceSpec] = [
    SourceSpec("google_news_ko", "news", "news", 4.0, google_news_ko),
    SourceSpec("google_news_en", "news", "news", 4.0, google_news_en),
    SourceSpec("reddit", "community", "community", 1.5, reddit_search),
    SourceSpec("hacker_news", "community", "community", 2.0, hacker_news_search),
    SourceSpec("lobsters", "community", "community", 1.5, lobsters_search),
    SourceSpec("devto", "community", "community", 1.2, devto_search),
    SourceSpec("v2ex", "community", "community", 1.0, v2ex_search),
    SourceSpec("github_repositories", "tech", "developer", 3.0, github_repositories),
    SourceSpec("github_issues", "tech", "developer", 2.5, github_issues),
    SourceSpec("stackoverflow", "tech", "developer", 2.5, stackoverflow_search),
    SourceSpec("npm", "tech", "registry", 3.0, npm_search),
    SourceSpec("pypi", "tech", "registry", 3.0, pypi_lookup),
    SourceSpec("huggingface_models", "tech", "developer", 2.5, huggingface_models),
    SourceSpec("huggingface_datasets", "tech", "developer", 2.5, huggingface_datasets),
    SourceSpec("arxiv", "research", "research", 4.0, arxiv_search),
    SourceSpec("crossref", "research", "research", 4.0, crossref_search),
    SourceSpec("openlibrary", "research", "research", 2.0, openlibrary_search),
    SourceSpec("wikipedia", "research", "research", 2.5, wikipedia_search),
]


def variants_for_depth(query: str, depth: str) -> list[str]:
    variants = generate_query_variants(query)
    if depth == "quick":
        return variants[:1]
    if depth == "balanced":
        return variants[:3]
    return variants


def parse_packs(value: str) -> list[str]:
    packs = [item.strip() for item in value.split(",") if item.strip()]
    valid = {source.pack for source in SOURCES}
    unknown = sorted(set(packs) - valid)
    if unknown:
        raise ValueError(f"Unknown pack: {', '.join(unknown)}")
    return unique(packs)


def dedupe_and_rank(results: list[SearchResult], query: str) -> list[SearchResult]:
    best: dict[str, SearchResult] = {}
    for item in results:
        if not item.url:
            continue
        item.canonical_url = canonicalize_url(item.url)
        rank_result(item, query)
        key = item.canonical_url or item.url
        previous = best.get(key)
        if previous is None or item.rank_score > previous.rank_score:
            best[key] = item
    return sorted(best.values(), key=lambda item: item.rank_score, reverse=True)


def build_discovery_results(
    run: SearchRun,
    query: str,
    *,
    dig_pages: int,
    include_offsite: bool,
) -> list[SearchResult]:
    if dig_pages <= 0:
        return []

    parent_by_url: dict[str, str] = {}
    candidates: list[tuple[float, dict[str, str]]] = []
    seen: set[str] = {result.canonical_url or canonicalize_url(result.url) for result in run.results}
    for check in run.fetched_urls:
        parent = check.final_url or check.url
        for link in check.links:
            url = canonicalize_url(link.get("url", ""))
            if not url or url in seen:
                continue
            if not include_offsite and not same_site(parent, url):
                continue
            score = discovered_link_score(link, query)
            if score <= 0:
                continue
            seen.add(url)
            parent_by_url[url] = parent
            candidates.append((score, {"url": url, "text": link.get("text", "")}))

    candidates.sort(key=lambda item: item[0], reverse=True)
    discovered: list[SearchResult] = []
    for score, link in candidates[:dig_pages]:
        url = link["url"]
        title = link.get("text") or urllib.parse.urlsplit(url).path.rsplit("/", 1)[-1] or url
        discovered.append(
            result(
                source="page_discovery",
                pack="discovery",
                source_type="page",
                query_variant=query,
                title=title,
                url=url,
                snippet=f"Discovered from {parent_by_url.get(url, '')}",
                score=2.0 + score,
                metadata={
                    "parent_url": parent_by_url.get(url, ""),
                    "link_text": link.get("text", ""),
                    "trust_weight": 1.8,
                    "discovery": "public_page_link",
                },
            )
        )
    return discovered


def run_search(
    query: str,
    *,
    depth: str = "deep",
    packs: list[str] | None = None,
    limit: int = 8,
    fetch_top: int = 5,
    detective: bool = False,
    dig_pages: int = 0,
    max_page_links: int = 12,
    include_offsite: bool = False,
    locale: str = "ko-KR",
    timeout: float = 12.0,
) -> SearchRun:
    started = time.monotonic()
    selected_packs = packs or ["news", "community", "tech", "research"]
    variants = variants_for_depth(query, depth)
    context = SearchContext(original_query=query, depth=depth, locale=locale, limit=limit, timeout=timeout)
    run = SearchRun(
        query=query,
        depth=depth,
        packs=selected_packs,
        locale=locale,
        query_variants=variants,
        detective=detective,
        dig_pages=dig_pages,
    )

    selected_sources = [source for source in SOURCES if source.pack in selected_packs]
    collected: list[SearchResult] = []
    for source in selected_sources:
        for variant in variants:
            try:
                source_results = source.adapter(variant, context)
                for item in source_results[:limit]:
                    item.source = source.name
                    item.pack = source.pack
                    item.source_type = source.source_type
                    item.metadata.setdefault("trust_weight", source.trust_weight)
                    rank_result(item, query, source.trust_weight)
                collected.extend(source_results[:limit])
            except Exception as exc:
                run.errors.append(SearchError(source=source.name, pack=source.pack, query_variant=variant, message=str(exc)))

    run.results = dedupe_and_rank(collected, query)

    for item in run.results[: max(0, fetch_top)]:
        check = verify_url(item.url, timeout=timeout, link_limit=max_page_links if detective or dig_pages else 0)
        run.fetched_urls.append(check)
        item.fetched = True
        item.fetch_verdict = check.verdict
        item.metadata["fetch_status"] = check.status
        item.metadata["fetch_body_size"] = check.body_size
        if check.title and not item.title:
            item.title = check.title
        if check.description and not item.snippet:
            item.snippet = check.description
        if check.metadata.get("canonical"):
            item.canonical_url = canonicalize_url(str(check.metadata["canonical"]))
        rank_result(item, query)

    discovery_results = build_discovery_results(
        run,
        query,
        dig_pages=dig_pages,
        include_offsite=include_offsite,
    )
    for item in discovery_results:
        check = verify_url(item.url, timeout=timeout)
        run.fetched_urls.append(check)
        run.discovered_urls.append(item.url)
        item.fetched = True
        item.fetch_verdict = check.verdict
        item.metadata["fetch_status"] = check.status
        item.metadata["fetch_body_size"] = check.body_size
        if check.title:
            item.title = check.title
        if check.description:
            item.snippet = check.description
        if check.metadata.get("canonical"):
            item.canonical_url = canonicalize_url(str(check.metadata["canonical"]))
        rank_result(item, query)
    if discovery_results:
        run.results = dedupe_and_rank(run.results + discovery_results, query)

    run.results = dedupe_and_rank(run.results, query)
    run.elapsed_ms = int((time.monotonic() - started) * 1000)
    return run


def group_by(items: Iterable[SearchResult], key: str) -> dict[str, list[SearchResult]]:
    grouped: dict[str, list[SearchResult]] = {}
    for item in items:
        grouped.setdefault(getattr(item, key), []).append(item)
    return grouped


def compact_url(url: str, limit: int = 120) -> str:
    return url if len(url) <= limit else url[: limit - 1] + "..."


def result_line(item: SearchResult) -> str:
    parts = [f"- [{item.source}] {item.title or '(untitled)'}"]
    if item.published:
        parts.append(f"({item.published[:10]})")
    parts.append(f"- score {item.rank_score:.1f}, evidence {item.evidence_level}")
    if item.fetch_verdict:
        parts.append(f", fetch {item.fetch_verdict}")
    parts.append(f"\n  {compact_url(item.url)}")
    if item.snippet:
        parts.append(f"\n  {item.snippet[:220]}")
    return " ".join(parts)


def format_report(run: SearchRun) -> str:
    lines: list[str] = []
    lines.append("# Insane Deep Search Report")
    lines.append("")
    lines.append(f"- Query: `{run.query}`")
    lines.append(f"- Depth: `{run.depth}`")
    lines.append(f"- Packs: `{', '.join(run.packs)}`")
    lines.append(f"- Detective mode: `{'on' if run.detective else 'off'}`")
    lines.append(f"- Results: `{len(run.results)}`")
    lines.append(f"- Source errors: `{len(run.errors)}`")
    lines.append("")

    lines.append("## 핵심 요약")
    if run.results:
        for item in run.results[:5]:
            lines.append(result_line(item))
    else:
        lines.append("- 검색 결과가 없습니다. 쿼리를 더 넓게 바꾸거나 소스팩을 추가해 보세요.")
    lines.append("")

    lines.append("## 소스별 발견")
    for pack, items in group_by(run.results, "pack").items():
        lines.append(f"### {pack}")
        for item in items[:8]:
            lines.append(result_line(item))
        lines.append("")

    lines.append("## 커뮤니티 반응")
    community = [item for item in run.results if item.source_type == "community"]
    if community:
        for item in community[:8]:
            comments = item.metadata.get("comments")
            points = item.metadata.get("points")
            engagement = []
            if comments is not None:
                engagement.append(f"comments {comments}")
            if points is not None:
                engagement.append(f"points {points}")
            suffix = f" ({', '.join(engagement)})" if engagement else ""
            lines.append(f"- [{item.source}] {item.title}{suffix}\n  {compact_url(item.url)}")
    else:
        lines.append("- 커뮤니티 소스에서 의미 있는 결과가 없거나 해당 소스가 실패했습니다.")
    lines.append("")

    lines.append("## 기술/논문 근거")
    technical = [item for item in run.results if item.source_type in {"developer", "registry", "research"}]
    if technical:
        for item in technical[:10]:
            lines.append(result_line(item))
    else:
        lines.append("- 기술/논문/레지스트리 소스에서 의미 있는 결과가 없습니다.")
    lines.append("")

    lines.append("## 원문 확인 결과")
    if run.fetched_urls:
        for check in run.fetched_urls:
            status = check.status if check.status is not None else "n/a"
            link_note = f", links {len(check.links)}" if check.links else ""
            lines.append(
                f"- {check.verdict} HTTP {status}, {check.body_size} bytes, {check.elapsed_ms} ms{link_note}\n  {compact_url(check.final_url or check.url)}"
            )
    else:
        lines.append("- `--fetch-top 0`이거나 확인할 상위 URL이 없습니다.")
    lines.append("")

    lines.append("## 탐정 모드 발견 링크")
    if run.discovered_urls:
        discovery_items = [item for item in run.results if item.source == "page_discovery"]
        for item in discovery_items[:10]:
            parent = item.metadata.get("parent_url", "")
            lines.append(f"- {item.title}\n  {compact_url(item.url)}")
            if parent:
                lines.append(f"  from {compact_url(str(parent))}")
    elif run.detective:
        lines.append("- 원문 페이지에서 쿼리와 관련도 높은 공개 링크를 추가로 찾지 못했습니다.")
    else:
        lines.append("- 꺼짐. 공개 페이지 링크 추적은 `--detective` 또는 `--dig-pages N`으로 켭니다.")
    lines.append("")

    lines.append("## 빈틈/주의점")
    lines.append("- 결과는 공개 웹/API/RSS 기반이며, 로그인 전용 자료나 비공개 정보는 포함하지 않습니다.")
    lines.append("- 탐정 모드는 공개 링크를 추적하지만 접근통제, 유료벽, 캡차, 로그인, 비공개 시스템을 우회하지 않습니다.")
    lines.append("- 커뮤니티 글은 사실 확정이 아니라 반응과 단서로 분리해서 해석해야 합니다.")
    lines.append("- 공개 API는 레이트리밋, 지역, 색인 지연 때문에 부분 실패가 날 수 있습니다.")
    if run.errors:
        lines.append("- 소스별 오류:")
        for error in run.errors[:20]:
            lines.append(f"  - {error.pack}/{error.source} `{error.query_variant}`: {error.message[:180]}")

    return "\n".join(lines).rstrip() + "\n"


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be zero or greater")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Codex-native public evidence deep search.")
    parser.add_argument("query", help="Search query")
    parser.add_argument("--depth", choices=["quick", "balanced", "deep"], default="deep")
    parser.add_argument("--pack", default="news,community,tech,research", help="Comma-separated source packs")
    parser.add_argument("--limit", type=positive_int, default=8, help="Per-source result limit")
    parser.add_argument("--fetch-top", type=positive_int, default=5, help="Verify the top N result URLs")
    parser.add_argument("--detective", action="store_true", help="Extract public links from fetched pages and follow the most relevant ones")
    parser.add_argument("--dig-pages", type=positive_int, default=0, help="Fetch up to N discovered public links from top pages")
    parser.add_argument("--max-page-links", type=positive_int, default=12, help="Maximum links to extract from each fetched page")
    parser.add_argument("--include-offsite", action="store_true", help="Allow detective mode to follow relevant offsite links")
    parser.add_argument("--locale", default="ko-KR")
    parser.add_argument("--timeout", type=float, default=12.0)
    parser.add_argument("--json", action="store_true", help="Print JSON output")
    parser.add_argument("--report", action="store_true", help="Print Markdown report")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        packs = parse_packs(args.pack)
    except ValueError as exc:
        parser.error(str(exc))

    run = run_search(
        args.query,
        depth=args.depth,
        packs=packs,
        limit=args.limit,
        fetch_top=args.fetch_top,
        detective=args.detective or args.dig_pages > 0,
        dig_pages=args.dig_pages or (8 if args.detective else 0),
        max_page_links=args.max_page_links,
        include_offsite=args.include_offsite,
        locale=args.locale,
        timeout=args.timeout,
    )

    print_report = args.report or not args.json
    if print_report:
        print(format_report(run))
    if args.json:
        print(json.dumps(run.to_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
