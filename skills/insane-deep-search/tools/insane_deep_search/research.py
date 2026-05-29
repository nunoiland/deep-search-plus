"""Heuristic follow-up query generation for research mode."""

from __future__ import annotations

from .models import SearchResult
from .text import meaningful_tokens, normalize_text, unique


SOURCE_TYPE_TERMS = {
    "news": "latest reporting",
    "community": "community reaction discussion",
    "developer": "github issues implementation",
    "registry": "package release changelog",
    "research": "paper citations DOI",
}


def compact_query(value: str, limit: int = 180) -> str:
    text = normalize_text(value)
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0]


def follow_up_queries(query: str, results: list[SearchResult], breadth: int) -> list[dict[str, str]]:
    """Generate bounded, deterministic follow-up queries from top evidence."""
    if breadth <= 0:
        return []
    original_tokens = {token.lower() for token in meaningful_tokens(query)}
    candidates: list[str] = []
    reasons: dict[str, str] = {}

    for source_type, suffix in SOURCE_TYPE_TERMS.items():
        candidate = compact_query(f"{query} {suffix}")
        candidates.append(candidate)
        reasons[candidate] = f"cover {source_type} evidence"

    for item in results[: max(8, breadth * 2)]:
        tokens = []
        for token in meaningful_tokens(f"{item.title} {item.snippet}"):
            lower = token.lower()
            if lower not in original_tokens and lower not in tokens:
                tokens.append(lower)
            if len(tokens) >= 3:
                break
        if not tokens:
            continue
        candidate = compact_query(f"{query} {' '.join(tokens)}")
        candidates.append(candidate)
        reasons[candidate] = f"expand from {item.source}"

    ordered = unique(candidates)
    return [{"query": item, "reason": reasons.get(item, "follow-up")} for item in ordered[:breadth]]
