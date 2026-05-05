"""Search orchestration."""

from __future__ import annotations

import time

from .config import DEFAULT_PACKS
from .discovery import build_discovery_results
from .http import verify_url
from .models import SearchContext, SearchError, SearchResult, SearchRun, SourceSpec
from .ranking import rank_result
from .sources import SOURCES
from .text import canonicalize_url, generate_query_variants, unique


def variants_for_depth(query: str, depth: str) -> list[str]:
    variants = generate_query_variants(query)
    if depth == "quick":
        return variants[:1]
    if depth == "balanced":
        return variants[:3]
    return variants


def parse_packs(value: str, sources: list[SourceSpec] | None = None) -> list[str]:
    packs = [item.strip() for item in value.split(",") if item.strip()]
    valid = {source.pack for source in (sources or SOURCES)}
    unknown = sorted(set(packs) - valid)
    if unknown:
        raise ValueError(f"Unknown pack: {', '.join(unknown)}")
    return unique(packs)


def dedupe_and_rank(results: list[SearchResult], query: str) -> list[SearchResult]:
    best: dict[str, SearchResult] = {}
    for item in results:
        if not item.url:
            continue
        item.canonical_url = canonicalize_url(item.url)
        rank_result(item, query)
        key = item.canonical_url or item.url
        previous = best.get(key)
        if previous is None or item.rank_score > previous.rank_score:
            best[key] = item
    return sorted(best.values(), key=lambda item: item.rank_score, reverse=True)


def run_search(
    query: str,
    *,
    depth: str = "deep",
    packs: list[str] | None = None,
    limit: int = 8,
    fetch_top: int = 5,
    detective: bool = False,
    dig_pages: int = 0,
    max_page_links: int = 12,
    include_offsite: bool = True,
    locale: str = "ko-KR",
    timeout: float = 12.0,
    sources: list[SourceSpec] | None = None,
) -> SearchRun:
    started = time.monotonic()
    selected_packs = packs or list(DEFAULT_PACKS)
    variants = variants_for_depth(query, depth)
    context = SearchContext(original_query=query, depth=depth, locale=locale, limit=limit, timeout=timeout)
    run = SearchRun(
        query=query,
        depth=depth,
        packs=selected_packs,
        locale=locale,
        query_variants=variants,
        detective=detective,
        dig_pages=dig_pages,
        include_offsite=include_offsite,
    )

    selected_sources = [source for source in (sources or SOURCES) if source.pack in selected_packs]
    collected: list[SearchResult] = []
    for source in selected_sources:
        for variant in variants:
            try:
                source_results = source.adapter(variant, context)
                for item in source_results[:limit]:
                    item.source = source.name
                    item.pack = source.pack
                    item.source_type = source.source_type
                    item.metadata.setdefault("trust_weight", source.trust_weight)
                    rank_result(item, query, source.trust_weight)
                collected.extend(source_results[:limit])
            except Exception as exc:
                run.errors.append(SearchError(source=source.name, pack=source.pack, query_variant=variant, message=str(exc)))

    run.results = dedupe_and_rank(collected, query)

    for item in run.results[: max(0, fetch_top)]:
        check = verify_url(item.url, timeout=timeout, link_limit=max_page_links if detective or dig_pages else 0)
        run.fetched_urls.append(check)
        item.fetched = True
        item.fetch_verdict = check.verdict
        item.metadata["fetch_status"] = check.status
        item.metadata["fetch_body_size"] = check.body_size
        if check.title and not item.title:
            item.title = check.title
        if check.description and not item.snippet:
            item.snippet = check.description
        if check.metadata.get("canonical"):
            item.canonical_url = canonicalize_url(str(check.metadata["canonical"]))
        rank_result(item, query)

    discovery_results = build_discovery_results(
        run,
        query,
        dig_pages=dig_pages,
        include_offsite=include_offsite,
    )
    for item in discovery_results:
        check = verify_url(item.url, timeout=timeout)
        run.fetched_urls.append(check)
        run.discovered_urls.append(item.url)
        item.fetched = True
        item.fetch_verdict = check.verdict
        item.metadata["fetch_status"] = check.status
        item.metadata["fetch_body_size"] = check.body_size
        if check.title:
            item.title = check.title
        if check.description:
            item.snippet = check.description
        if check.metadata.get("canonical"):
            item.canonical_url = canonicalize_url(str(check.metadata["canonical"]))
        rank_result(item, query)
    if discovery_results:
        run.results = dedupe_and_rank(run.results + discovery_results, query)

    run.results = dedupe_and_rank(run.results, query)
    run.elapsed_ms = int((time.monotonic() - started) * 1000)
    return run
