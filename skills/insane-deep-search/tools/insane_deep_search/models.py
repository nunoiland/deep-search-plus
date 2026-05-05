"""Shared data models for Insane Deep Search."""

from __future__ import annotations

import dataclasses
from typing import Any, Callable


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


@dataclasses.dataclass(frozen=True)
class SourceSpec:
    name: str
    pack: str
    source_type: str
    trust_weight: float
    endpoints: tuple[str, ...]
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
    include_offsite: bool = True
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
            "include_offsite": self.include_offsite,
            "results": [result.to_dict() for result in self.results],
            "errors": [error.to_dict() for error in self.errors],
            "fetched_urls": [fetch.to_dict() for fetch in self.fetched_urls],
            "discovered_urls": self.discovered_urls,
            "top_evidence_urls": [result.url for result in self.results[:10]],
            "elapsed_ms": self.elapsed_ms,
        }
