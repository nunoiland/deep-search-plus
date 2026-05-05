"""Result construction helpers."""

from __future__ import annotations

from typing import Any

from .models import SearchResult
from .text import canonicalize_url, normalize_text


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
