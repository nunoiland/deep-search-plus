"""HTML metadata and link extraction helpers."""

from __future__ import annotations

import json
import re
import urllib.parse
from html.parser import HTMLParser
from typing import Any

from .config import DISCOVERY_POLICY
from .text import canonicalize_url, is_http_url, is_low_value_link, normalize_text


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


def extract_metadata(body: bytes, content_type: str) -> dict[str, Any]:
    text = body[: DISCOVERY_POLICY.body_parse_limit].decode("utf-8", errors="replace")
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


def extract_links(body: bytes, content_type: str, base_url: str, limit: int = 25) -> list[dict[str, str]]:
    if limit <= 0:
        return []
    text = body[: DISCOVERY_POLICY.body_parse_limit].decode("utf-8", errors="replace")
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
        links.append({"url": canonical, "text": normalize_text(raw.get("text", ""))[: DISCOVERY_POLICY.link_text_limit]})
        if len(links) >= limit:
            break
    return links
