"""Source quality scoring for public evidence results."""

from __future__ import annotations

import math

from .models import SearchResult
from .text import parse_datetime


def _add(condition: bool, score: float, reason: str, reasons: list[str]) -> float:
    if condition:
        reasons.append(reason)
        return score
    return 0.0


def _age_days(value: str | None) -> float | None:
    parsed = parse_datetime(value)
    if not parsed:
        return None
    import datetime as dt

    return max(0.0, (dt.datetime.now(dt.timezone.utc) - parsed).total_seconds() / 86400)


def apply_quality_score(result: SearchResult) -> SearchResult:
    """Attach quality_score, quality_reasons, and risk_flags to a result."""
    metadata = result.metadata
    reasons: list[str] = []
    risks: list[str] = []
    score = 0.0

    if result.source_type == "research":
        citations = metadata.get("citations")
        if isinstance(citations, (int, float)) and citations > 0:
            score += min(3.0, math.log1p(float(citations)))
            reasons.append("citation signal")
        score += _add(bool(metadata.get("doi")), 2.0, "doi present", reasons)
        score += _add(bool(metadata.get("venue")), 1.0, "venue present", reasons)
        score += _add(bool(metadata.get("open_access")), 1.0, "open access", reasons)
        score += _add(result.source in {"crossref", "openalex", "semantic_scholar"}, 1.5, "scholarly index", reasons)
        if result.source == "arxiv" or metadata.get("arxiv_id"):
            risks.append("preprint_or_repository_record")

    elif result.source_type in {"developer", "registry"}:
        stars = metadata.get("stars")
        forks = metadata.get("forks")
        downloads = metadata.get("downloads")
        if isinstance(stars, (int, float)) and stars > 0:
            score += min(3.0, math.log1p(float(stars)) / 2)
            reasons.append("stars")
        if isinstance(forks, (int, float)) and forks > 0:
            score += min(1.5, math.log1p(float(forks)) / 3)
            reasons.append("forks")
        if isinstance(downloads, (int, float)) and downloads > 0:
            score += min(2.5, math.log1p(float(downloads)) / 3)
            reasons.append("downloads")
        score += _add(bool(metadata.get("license")), 1.0, "license present", reasons)
        score += _add(bool(metadata.get("latest_release")), 1.0, "release activity", reasons)
        score += _add(bool(metadata.get("readme_excerpt")), 0.7, "readme available", reasons)
        if metadata.get("archived"):
            risks.append("archived_repository")
            score -= 2.0
        age = _age_days(result.published)
        if age is not None and age <= 180:
            score += 1.0
            reasons.append("recent activity")
        elif age is not None and age > 730:
            risks.append("stale_activity")

    elif result.source_type == "news":
        score += _add(bool(result.published), 1.0, "published date", reasons)
        score += _add(bool(metadata.get("source_country")), 0.7, "source country", reasons)
        score += _add(bool(metadata.get("language")), 0.5, "language", reasons)
        score += _add(result.fetch_verdict == "strong_ok", 1.5, "verified fetch", reasons)
        age = _age_days(result.published)
        if age is not None and age <= 14:
            score += 1.5
            reasons.append("recent coverage")
        if result.source.startswith("google_news"):
            risks.append("aggregated_news_result")

    elif result.source_type == "community":
        comments = metadata.get("comments")
        points = metadata.get("points")
        if isinstance(comments, (int, float)) and comments > 0:
            score += min(2.5, math.log1p(float(comments)))
            reasons.append("discussion volume")
        if isinstance(points, (int, float)) and points > 0:
            score += min(2.0, math.log1p(float(points)) / 2)
            reasons.append("community score")
        age = _age_days(result.published)
        if age is not None and age <= 60:
            score += 1.0
            reasons.append("recent discussion")
        risks.append("community_opinion_not_confirmed_fact")
        if not comments and not points:
            risks.append("low_engagement")

    score = max(0.0, min(10.0, score))
    metadata["quality_score"] = round(score, 2)
    metadata["quality_reasons"] = reasons
    metadata["risk_flags"] = risks
    return result
