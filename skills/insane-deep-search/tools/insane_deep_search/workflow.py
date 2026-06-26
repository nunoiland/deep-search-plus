"""Research workflow contracts and resumable checkpoints."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import SearchRun


VALID_CONTRACT_MODES = {"basic", "strict", "off"}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def build_research_contract(
    *,
    query: str,
    mode: str = "basic",
    goal: str | None = None,
    scope: str | None = None,
    done_evidence: str | None = None,
) -> dict[str, Any]:
    """Create a lightweight research contract used by reports and gates."""
    if mode not in VALID_CONTRACT_MODES:
        raise ValueError(f"Unknown research_contract mode: {mode}")
    if mode == "off":
        return {"mode": "off", "enabled": False}

    strict = mode == "strict"
    return {
        "mode": mode,
        "enabled": True,
        "query": query,
        "goal": goal
        or "Answer the query with public evidence, separated by verified facts, weak evidence, and community reactions.",
        "scope": scope
        or "Use public APIs, RSS feeds, indexed pages, and fetched public URLs only. Do not bypass access controls.",
        "done_evidence": done_evidence
        or (
            "Strict mode: core conclusions require supported or conflicting claims from multiple substantive sources."
            if strict
            else "Balanced mode: label every conclusion as supported, weak, community-only, or unverified."
        ),
        "created_at": utc_now_iso(),
    }


def load_checkpoint(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    checkpoint_path = Path(path).expanduser()
    if not checkpoint_path.exists():
        raise FileNotFoundError(f"checkpoint not found: {checkpoint_path}")
    data = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("checkpoint must contain a JSON object")
    return data


def checkpoint_seen_queries(checkpoint: dict[str, Any] | None) -> set[str]:
    if not checkpoint:
        return set()
    values = checkpoint.get("seen_queries") or checkpoint.get("query_variants") or []
    if not isinstance(values, list):
        return set()
    return {str(item).strip().lower() for item in values if str(item).strip()}


def checkpoint_seen_urls(checkpoint: dict[str, Any] | None) -> set[str]:
    if not checkpoint:
        return set()
    values = checkpoint.get("seen_urls") or checkpoint.get("top_evidence_urls") or []
    if not isinstance(values, list):
        return set()
    return {str(item).strip() for item in values if str(item).strip()}


def checkpoint_contract(checkpoint: dict[str, Any] | None) -> dict[str, Any]:
    if not checkpoint:
        return {}
    value = checkpoint.get("research_contract")
    return value if isinstance(value, dict) else {}


def build_checkpoint_payload(run: SearchRun) -> dict[str, Any]:
    seen_queries: list[str] = []
    for value in run.query_variants:
        if value not in seen_queries:
            seen_queries.append(value)
    for round_info in run.research_rounds:
        queries = round_info.get("queries", [])
        if not isinstance(queries, list):
            continue
        for item in queries:
            query = item.get("query") if isinstance(item, dict) else item
            if isinstance(query, str) and query and query not in seen_queries:
                seen_queries.append(query)

    seen_urls: list[str] = []
    for result in run.results:
        if result.url and result.url not in seen_urls:
            seen_urls.append(result.url)
    for fetch in run.fetched_urls:
        url = fetch.final_url or fetch.url
        if url and url not in seen_urls:
            seen_urls.append(url)

    return {
        "version": 1,
        "created_at": utc_now_iso(),
        "query": run.query,
        "depth": run.depth,
        "packs": run.packs,
        "research_contract": run.research_contract,
        "evidence_gates": run.evidence_gates,
        "decision_readiness": run.decision_readiness,
        "seen_queries": seen_queries,
        "seen_urls": seen_urls,
        "claims": run.claims,
        "research_rounds": run.research_rounds,
        "result_groups": run.result_groups,
        "top_evidence_urls": [result.url for result in run.results[:10]],
        "errors": [error.to_dict() for error in run.errors],
    }


def write_checkpoint(path: str, payload: dict[str, Any]) -> str:
    checkpoint_path = Path(path).expanduser()
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(checkpoint_path)
