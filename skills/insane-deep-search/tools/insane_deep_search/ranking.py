"""Ranking and evidence scoring."""

from __future__ import annotations

import datetime as dt
import math

from .config import FETCH_VERDICT_BONUS, RANKING_POLICY
from .models import SearchResult
from .text import parse_datetime, tokenize
from .config import STOPWORDS


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
    return min(RANKING_POLICY.max_query_match_score, title_hits * 3.0 + snippet_hits * 1.2)


def rank_result(result: SearchResult, query: str, trust_weight: float | None = None) -> SearchResult:
    engagement = 0.0
    for key in ("points", "score", "comments", "stars", "downloads", "citations"):
        raw = result.metadata.get(key)
        if isinstance(raw, (int, float)) and raw > 0:
            engagement += math.log1p(raw)
    fetch_bonus = FETCH_VERDICT_BONUS.get(result.fetch_verdict or "", 0.0)
    trust = trust_weight if trust_weight is not None else float(result.metadata.get("trust_weight", RANKING_POLICY.default_trust_weight))
    result.rank_score = (
        result.score
        + trust
        + query_match_score(result, query)
        + recency_score(result.published)
        + min(RANKING_POLICY.max_engagement_score, engagement)
        + fetch_bonus
    )
    if result.source_type in {"research", "registry", "developer"} and result.rank_score >= RANKING_POLICY.strong_research_threshold:
        result.evidence_level = "strong"
    elif result.source_type == "news" and result.rank_score >= RANKING_POLICY.strong_news_threshold:
        result.evidence_level = "strong"
    elif result.source_type == "community":
        result.evidence_level = "medium" if result.rank_score >= RANKING_POLICY.medium_community_threshold else "weak"
    else:
        result.evidence_level = "medium" if result.rank_score >= RANKING_POLICY.medium_default_threshold else "weak"
    return result
