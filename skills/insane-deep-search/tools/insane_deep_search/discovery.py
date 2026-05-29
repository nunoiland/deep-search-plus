"""Public link discovery for detective mode."""

from __future__ import annotations

import re
import urllib.parse
from collections import Counter

from .config import DISCOVERY_POLICY, STOPWORDS
from .models import SearchResult, SearchRun
from .results import result
from .text import canonicalize_url, host_for, same_site, tokenize


def discovered_link_analysis(link: dict[str, str], query: str) -> tuple[float, list[str]]:
    tokens = [token.lower() for token in tokenize(query) if token.lower() not in STOPWORDS]
    if not tokens:
        return 0.0, []
    haystack_text = link.get("text", "").lower()
    haystack_url = link.get("url", "").lower()
    score = 0.0
    reasons: list[str] = []
    for token in tokens:
        if token in haystack_text:
            score += DISCOVERY_POLICY.text_hit_score
            reasons.append(f"text:{token}")
        if token in haystack_url:
            score += DISCOVERY_POLICY.url_hit_score
            reasons.append(f"url:{token}")
    path = urllib.parse.urlsplit(link.get("url", "")).path.lower()
    if re.search(r"/(article|news|post|story|report|research|docs?|issues?|pull|release|blog)/", path):
        score += DISCOVERY_POLICY.article_path_bonus
        reasons.append("path:evidence")
    return score, reasons


def discovered_link_score(link: dict[str, str], query: str) -> float:
    score, _reasons = discovered_link_analysis(link, query)
    return score


def build_discovery_results(
    run: SearchRun,
    query: str,
    *,
    dig_pages: int,
    include_offsite: bool,
    current_depth: int = 1,
) -> list[SearchResult]:
    if dig_pages <= 0:
        return []

    parent_by_url: dict[str, str] = {}
    parent_chain_by_url: dict[str, list[str]] = {}
    reason_by_url: dict[str, list[str]] = {}
    candidates: list[tuple[float, dict[str, str]]] = []
    seen: set[str] = {result.canonical_url or canonicalize_url(result.url) for result in run.results}
    seen.update(canonicalize_url(url) for url in run.discovered_urls)
    seen.update(canonicalize_url(check.final_url or check.url) for check in run.fetched_urls)
    domain_counts: Counter[str] = Counter()

    for check in run.fetched_urls:
        check_depth = int(check.metadata.get("discovery_depth") or 0)
        if check_depth != current_depth - 1:
            continue
        parent = check.final_url or check.url
        parent_chain = [str(item) for item in check.metadata.get("parent_chain", []) if item]
        for link in check.links:
            url = canonicalize_url(link.get("url", ""))
            if not url or url in seen:
                continue
            if not include_offsite and not same_site(parent, url):
                continue
            domain = host_for(url)
            if domain and domain_counts[domain] >= DISCOVERY_POLICY.domain_limit:
                continue
            score, reasons = discovered_link_analysis(link, query)
            if score <= 0:
                continue
            seen.add(url)
            domain_counts[domain] += 1
            parent_by_url[url] = parent
            parent_chain_by_url[url] = [*parent_chain, parent]
            reason_by_url[url] = reasons
            candidates.append((score, {"url": url, "text": link.get("text", "")}))
            if len(candidates) >= DISCOVERY_POLICY.candidate_limit:
                break

    candidates.sort(key=lambda item: item[0], reverse=True)
    discovered: list[SearchResult] = []
    for score, link in candidates[:dig_pages]:
        url = link["url"]
        title = link.get("text") or urllib.parse.urlsplit(url).path.rsplit("/", 1)[-1] or url
        discovered.append(
            result(
                source="page_discovery",
                pack="discovery",
                source_type="page",
                query_variant=query,
                title=title,
                url=url,
                snippet=f"Discovered from {parent_by_url.get(url, '')}",
                score=2.0 + score,
                metadata={
                    "parent_url": parent_by_url.get(url, ""),
                    "parent_chain": parent_chain_by_url.get(url, []),
                    "link_text": link.get("text", ""),
                    "trust_weight": DISCOVERY_POLICY.trust_weight,
                    "discovery": "public_page_link",
                    "discovery_score": round(score, 3),
                    "discovery_reason": reason_by_url.get(url, []),
                    "discovery_depth": current_depth,
                },
            )
        )
    return discovered
