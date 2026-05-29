"""Adaptive follow-up query generation for research mode."""

from __future__ import annotations

import json
from typing import Any

from .local_llm import generate_json
from .models import SearchResult
from .text import meaningful_tokens, normalize_text, unique


SOURCE_TYPE_TERMS = {
    "news": "latest reporting",
    "community": "community reaction discussion",
    "developer": "github issues implementation",
    "registry": "package release changelog",
    "research": "paper citations DOI",
}

CONTRADICTION_TERMS = ("criticism", "limitations", "issues", "benchmark", "security risk", "release notes")
BLOCKED_QUERY_TERMS = ("captcha", "paywall bypass", "login bypass", "sign in bypass", "cookie bypass")


def compact_query(value: str, limit: int = 180) -> str:
    text = normalize_text(value)
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0]


def source_coverage(results: list[SearchResult]) -> dict[str, dict[str, Any]]:
    axes = {
        "news": {"source_types": {"news"}},
        "community": {"source_types": {"community"}},
        "developer": {"source_types": {"developer", "registry"}},
        "research": {"source_types": {"research"}},
        "page": {"source_types": {"page"}},
    }
    coverage: dict[str, dict[str, Any]] = {}
    for axis, spec in axes.items():
        items = [item for item in results if item.source_type in spec["source_types"]]
        strong = [item for item in items if item.evidence_level == "strong"]
        quality = sum(float(item.metadata.get("quality_score") or 0.0) for item in items) / max(1, len(items))
        status = "missing"
        if len(strong) >= 2 or (items and quality >= 5.0):
            status = "covered"
        elif items:
            status = "weak"
        coverage[axis] = {
            "count": len(items),
            "strong_count": len(strong),
            "average_quality": round(quality, 2),
            "status": status,
            "sources": sorted({item.source for item in items}),
        }
    return coverage


def sanitize_query(value: str) -> str:
    return compact_query(value.replace("\n", " ").replace("\t", " "))


def safe_query(value: str) -> bool:
    lowered = value.lower()
    return bool(value.strip()) and not any(term in lowered for term in BLOCKED_QUERY_TERMS)


def top_result_summaries(results: list[SearchResult], limit: int = 12) -> list[dict[str, Any]]:
    summaries = []
    for item in results[:limit]:
        summaries.append(
            {
                "source": item.source,
                "source_type": item.source_type,
                "title": item.title[:180],
                "snippet": item.snippet[:260],
                "evidence": item.evidence_level,
                "quality": item.metadata.get("quality_score"),
                "risk_flags": item.metadata.get("risk_flags", []),
            }
        )
    return summaries


def llm_prompt(query: str, results: list[SearchResult], coverage: dict[str, Any], breadth: int) -> str:
    payload = {
        "query": query,
        "coverage": coverage,
        "top_results": top_result_summaries(results),
        "max_queries": breadth,
        "allowed_output": {
            "queries": [{"query": "string", "reason": "string", "type": "source_gap|contradiction|implementation|paper_trail|release|community|language_split"}],
            "claims": [{"claim": "string", "reason": "string"}],
            "gaps": ["string"],
            "stop_reason": "string",
        },
    }
    return (
        "You are the local planner for a public-evidence deep search tool. "
        "Return strict JSON only. Generate follow-up search queries that deepen verification, "
        "find missing source classes, check contradictions, and separate community reactions from facts. "
        "Do not suggest login, paywall, captcha, or private-data bypass.\n\n"
        + json.dumps(payload, ensure_ascii=False)
    )


def heuristic_follow_up_queries(
    query: str,
    results: list[SearchResult],
    breadth: int,
    coverage: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    if breadth <= 0:
        return []
    coverage = coverage or source_coverage(results)
    original_tokens = {token.lower() for token in meaningful_tokens(query)}
    candidates: list[str] = []
    reasons: dict[str, str] = {}

    for axis, details in coverage.items():
        if details.get("status") in {"missing", "weak"}:
            suffix = SOURCE_TYPE_TERMS.get("developer" if axis == "developer" else axis, axis)
            candidate = sanitize_query(f"{query} {suffix}")
            candidates.append(candidate)
            reasons[candidate] = f"cover {axis} gap"

    if any(item.source_type == "community" for item in results):
        for suffix in CONTRADICTION_TERMS[:3]:
            candidate = sanitize_query(f"{query} {suffix}")
            candidates.append(candidate)
            reasons[candidate] = "verify community-only or weak claim"

    for source_type, suffix in SOURCE_TYPE_TERMS.items():
        candidate = sanitize_query(f"{query} {suffix}")
        candidates.append(candidate)
        reasons.setdefault(candidate, f"cover {source_type} evidence")

    for item in results[: max(10, breadth * 2)]:
        tokens = []
        for token in meaningful_tokens(f"{item.title} {item.snippet}"):
            lower = token.lower()
            if lower not in original_tokens and lower not in tokens:
                tokens.append(lower)
            if len(tokens) >= 3:
                break
        if not tokens:
            continue
        candidate = sanitize_query(f"{query} {' '.join(tokens)}")
        candidates.append(candidate)
        reasons[candidate] = f"expand from {item.source}"

    ordered = [item for item in unique(candidates) if safe_query(item)]
    return [{"query": item, "reason": reasons.get(item, "follow-up"), "type": "heuristic"} for item in ordered[:breadth]]


def local_llm_follow_up_plan(
    query: str,
    results: list[SearchResult],
    breadth: int,
    coverage: dict[str, Any],
    *,
    local_llm_mode: str,
    local_llm_model: str,
    local_llm_timeout: float | None = None,
    local_llm_fallback: bool = True,
) -> tuple[list[dict[str, str]], list[dict[str, Any]], dict[str, Any]]:
    parsed, status = generate_json(
        llm_prompt(query, results, coverage, breadth),
        mode=local_llm_mode,
        model=local_llm_model,
        timeout=local_llm_timeout,
        fallback_models=local_llm_fallback,
    )
    if not parsed:
        return [], [], status

    queries: list[dict[str, str]] = []
    for item in parsed.get("queries", []) if isinstance(parsed.get("queries"), list) else []:
        if not isinstance(item, dict):
            continue
        value = sanitize_query(str(item.get("query") or ""))
        if safe_query(value):
            queries.append(
                {
                    "query": value,
                    "reason": str(item.get("reason") or "local LLM planner"),
                    "type": str(item.get("type") or "local_llm"),
                }
            )
        if len(queries) >= breadth:
            break

    claims = [item for item in parsed.get("claims", []) if isinstance(item, dict)] if isinstance(parsed.get("claims"), list) else []
    status["gaps"] = parsed.get("gaps", [])
    status["stop_reason"] = parsed.get("stop_reason", "")
    return queries, claims, status


def build_follow_up_plan(
    query: str,
    results: list[SearchResult],
    breadth: int,
    *,
    coverage: dict[str, dict[str, Any]] | None = None,
    local_llm_mode: str = "off",
    local_llm_model: str = "",
    local_llm_timeout: float | None = None,
    local_llm_fallback: bool = True,
) -> tuple[list[dict[str, str]], dict[str, Any], list[dict[str, Any]]]:
    coverage = coverage or source_coverage(results)
    llm_queries: list[dict[str, str]] = []
    llm_claims: list[dict[str, Any]] = []
    llm_status: dict[str, Any] = {"mode": local_llm_mode, "available": False, "fallback": local_llm_mode != "off"}
    if local_llm_mode != "off":
        llm_queries, llm_claims, llm_status = local_llm_follow_up_plan(
            query,
            results,
            breadth,
            coverage,
            local_llm_mode=local_llm_mode,
            local_llm_model=local_llm_model,
            local_llm_timeout=local_llm_timeout,
            local_llm_fallback=local_llm_fallback,
        )

    heuristic = heuristic_follow_up_queries(query, results, breadth, coverage)
    merged: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in [*llm_queries, *heuristic]:
        key = item["query"].lower()
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
        if len(merged) >= breadth:
            break
    step = {
        "planner": "local_llm" if llm_queries else "heuristic",
        "local_llm": llm_status,
        "coverage": coverage,
        "generated": merged,
        "claim_candidates": llm_claims,
    }
    return merged, step, llm_claims


def follow_up_queries(query: str, results: list[SearchResult], breadth: int) -> list[dict[str, str]]:
    """Generate bounded, deterministic follow-up queries from top evidence."""
    return heuristic_follow_up_queries(query, results, breadth)
