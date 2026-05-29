"""Claim extraction and evidence ledger helpers."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from .models import SearchResult
from .text import meaningful_tokens, normalize_text


NEGATIVE_SIGNALS = {
    "concern",
    "concerns",
    "criticism",
    "critical",
    "issue",
    "issues",
    "limitation",
    "limitations",
    "problem",
    "problems",
    "risk",
    "risks",
    "debunk",
    "false",
    "not",
    "반박",
    "문제",
    "위험",
    "한계",
}


def normalize_claim(value: str) -> str:
    text = normalize_text(value)
    text = re.sub(r"\s+", " ", text)
    return text[:220].strip(" -:|")


def claim_key(value: str) -> str:
    tokens = [token.lower() for token in meaningful_tokens(value)]
    return " ".join(tokens[:10]) or normalize_claim(value).lower()


def result_claim(result: SearchResult) -> str:
    title = normalize_claim(result.title)
    if title:
        return title
    snippet = normalize_claim(re.split(r"[.!?。]\s*", result.snippet or "")[0])
    return snippet


def confidence_for(items: list[SearchResult], status: str) -> float:
    sources = {item.source for item in items}
    source_types = {item.source_type for item in items}
    quality = sum(float(item.metadata.get("quality_score") or 0.0) for item in items) / max(1, len(items))
    base = min(0.7, 0.15 * len(sources)) + min(0.2, quality / 50)
    if len(source_types) >= 2:
        base += 0.15
    if status == "supported":
        base += 0.1
    if status in {"community_only", "unverified"}:
        base -= 0.15
    if status == "conflicting":
        base -= 0.05
    return round(max(0.05, min(0.98, base)), 2)


def classify_claim(items: list[SearchResult]) -> str:
    source_types = {item.source_type for item in items}
    strong = [item for item in items if item.evidence_level == "strong" or float(item.metadata.get("quality_score") or 0.0) >= 5.0]
    text = " ".join(f"{item.title} {item.snippet}" for item in items).lower()
    has_negative = any(signal in text for signal in NEGATIVE_SIGNALS)
    has_substantive = bool(source_types & {"news", "developer", "registry", "research", "page"})

    if source_types and source_types <= {"community"}:
        return "community_only"
    if has_negative and len(source_types) >= 2:
        return "conflicting"
    if len(source_types) >= 2 and strong:
        return "supported"
    if strong:
        return "weak"
    if has_substantive:
        return "unverified"
    return "weak"


def build_claim_ledger(
    query: str,
    results: list[SearchResult],
    result_groups: list[dict[str, Any]],
    llm_claims: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Build a compact claim ledger from results and optional local LLM claims."""
    grouped: dict[str, list[SearchResult]] = defaultdict(list)
    title_by_key: dict[str, str] = {}
    group_by_url = {str(group.get("representative_url") or ""): group.get("group_id") for group in result_groups}

    for item in results:
        claim = result_claim(item)
        if not claim:
            continue
        key = claim_key(claim)
        grouped[key].append(item)
        title_by_key.setdefault(key, claim)

    for claim in llm_claims or []:
        text = normalize_claim(str(claim.get("claim") or claim.get("text") or ""))
        if not text:
            continue
        key = claim_key(text)
        title_by_key.setdefault(key, text)

    ledger: list[dict[str, Any]] = []
    for key, items in grouped.items():
        status = classify_claim(items)
        supporting_sources = sorted({item.source for item in items})
        source_types = sorted({item.source_type for item in items})
        evidence_groups = []
        for item in items:
            group_id = item.metadata.get("group_id") or group_by_url.get(item.url) or group_by_url.get(item.canonical_url)
            if group_id and group_id not in evidence_groups:
                evidence_groups.append(group_id)
        ledger.append(
            {
                "claim": title_by_key.get(key, key),
                "status": status,
                "confidence": confidence_for(items, status),
                "supporting_sources": supporting_sources,
                "contradicting_sources": supporting_sources if status == "conflicting" else [],
                "source_types": source_types,
                "evidence_groups": evidence_groups,
                "result_count": len(items),
                "query_relevance": bool(set(token.lower() for token in meaningful_tokens(query)) & set(key.split())),
            }
        )

    for claim in llm_claims or []:
        text = normalize_claim(str(claim.get("claim") or claim.get("text") or ""))
        if not text:
            continue
        key = claim_key(text)
        if any(claim_key(str(item["claim"])) == key for item in ledger):
            continue
        ledger.append(
            {
                "claim": text,
                "status": "unverified",
                "confidence": 0.1,
                "supporting_sources": [],
                "contradicting_sources": [],
                "source_types": [],
                "evidence_groups": [],
                "result_count": 0,
                "query_relevance": bool(set(token.lower() for token in meaningful_tokens(query)) & set(key.split())),
            }
        )

    priority = {"supported": 0, "conflicting": 1, "weak": 2, "community_only": 3, "unverified": 4}
    ledger.sort(key=lambda item: (priority.get(str(item["status"]), 9), -float(item["confidence"]), -int(item["result_count"])))
    return ledger[:20]
