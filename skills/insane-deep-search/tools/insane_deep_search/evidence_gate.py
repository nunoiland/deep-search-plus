"""Evidence gate policy for report readiness and summary strength."""

from __future__ import annotations

from typing import Any

from .models import SearchRun


VALID_GATE_MODES = {"strict", "balanced", "loose"}


def allowed_statuses(mode: str) -> set[str]:
    if mode == "strict":
        return {"supported", "conflicting"}
    if mode == "loose":
        return {"supported", "conflicting", "weak", "community_only", "unverified"}
    return {"supported", "conflicting", "weak"}


def evaluate_evidence_gate(run: SearchRun, mode: str = "balanced") -> tuple[dict[str, Any], str]:
    if mode not in VALID_GATE_MODES:
        raise ValueError(f"Unknown evidence_gate mode: {mode}")

    counts: dict[str, int] = {}
    for claim in run.claims:
        status = str(claim.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1

    allowed = allowed_statuses(mode)
    summary_claims = [
        {
            "claim": claim.get("claim"),
            "status": claim.get("status"),
            "confidence": claim.get("confidence"),
            "supporting_sources": claim.get("supporting_sources", []),
        }
        for claim in run.claims
        if str(claim.get("status")) in allowed
    ][:8]

    blocked_claims = [
        {
            "claim": claim.get("claim"),
            "status": claim.get("status"),
            "reason": "not allowed in core summary for this evidence gate",
        }
        for claim in run.claims
        if str(claim.get("status")) not in allowed
    ][:12]

    supported = counts.get("supported", 0)
    conflicting = counts.get("conflicting", 0)
    weak = counts.get("weak", 0)
    community_only = counts.get("community_only", 0)
    unverified = counts.get("unverified", 0)

    if supported >= 2 and not conflicting:
        readiness = "high"
    elif supported or conflicting:
        readiness = "medium"
    elif weak and mode != "strict":
        readiness = "low"
    elif community_only or unverified:
        readiness = "insufficient"
    else:
        readiness = "no_evidence"

    gates = {
        "mode": mode,
        "allowed_summary_statuses": sorted(allowed),
        "status_counts": counts,
        "summary_claims": summary_claims,
        "blocked_claims": blocked_claims,
        "rules": [
            "community_only claims must stay out of the core summary unless evidence gate is loose",
            "unverified claims are always labeled and never presented as confirmed facts",
            "conflicting claims may be shown only with explicit contradiction labeling",
        ],
    }
    return gates, readiness
