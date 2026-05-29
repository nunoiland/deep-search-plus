"""Search orchestration."""

from __future__ import annotations

import time

from .config import DEFAULT_PACKS
from .dedupe import group_results
from .discovery import build_discovery_results
from .http import verify_url
from .models import SearchContext, SearchError, SearchResult, SearchRun, SourceSpec
from .quality import apply_quality_score
from .ranking import rank_result
from .render import should_render_fallback, verify_rendered_url
from .research import follow_up_queries
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
    ranked = []
    for item in results:
        if not item.url:
            continue
        item.canonical_url = canonicalize_url(item.url)
        apply_quality_score(item)
        rank_result(item, query)
        ranked.append(item)
    representatives, _groups = group_results(ranked)
    return representatives


def dedupe_rank_and_group(results: list[SearchResult], query: str) -> tuple[list[SearchResult], list[dict[str, object]]]:
    ranked = []
    for item in results:
        if not item.url:
            continue
        item.canonical_url = canonicalize_url(item.url)
        apply_quality_score(item)
        rank_result(item, query)
        ranked.append(item)
    return group_results(ranked)


def verify_for_mode(url: str, *, timeout: float, link_limit: int, verify_mode: str):
    if verify_mode == "rendered":
        return verify_rendered_url(url, timeout=timeout, link_limit=link_limit)
    check = verify_url(url, timeout=timeout, link_limit=link_limit)
    if verify_mode == "auto" and should_render_fallback(check):
        rendered = verify_rendered_url(url, timeout=timeout, link_limit=link_limit)
        if rendered.verdict != "fail" or rendered.body_size > check.body_size:
            rendered.metadata["basic_verdict"] = check.verdict
            rendered.metadata["basic_status"] = check.status
            return rendered
        check.metadata["render_error"] = rendered.error
    return check


def collect_from_sources(
    *,
    variants: list[str],
    selected_sources: list[SourceSpec],
    context: SearchContext,
    run: SearchRun,
    limit: int,
    query: str,
) -> list[SearchResult]:
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
                    apply_quality_score(item)
                    rank_result(item, query, source.trust_weight)
                collected.extend(source_results[:limit])
            except Exception as exc:
                run.errors.append(SearchError(source=source.name, pack=source.pack, query_variant=variant, message=str(exc)))
    return collected


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
    research: bool = False,
    research_depth: int = 2,
    research_breadth: int = 4,
    verify_mode: str = "basic",
) -> SearchRun:
    if verify_mode not in {"basic", "auto", "rendered"}:
        raise ValueError(f"Unknown verify_mode: {verify_mode}")
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
        research=research,
        research_depth=research_depth if research else 0,
        research_breadth=research_breadth if research else 0,
        verify_mode=verify_mode,
    )

    selected_sources = [source for source in (sources or SOURCES) if source.pack in selected_packs]
    collected = collect_from_sources(
        variants=variants,
        selected_sources=selected_sources,
        context=context,
        run=run,
        limit=limit,
        query=query,
    )
    if research:
        run.research_rounds.append({"round": 0, "queries": variants, "result_count": len(collected), "reason": "initial variants"})

    run.results, run.result_groups = dedupe_rank_and_group(collected, query)

    if research:
        seen_queries = {variant.lower() for variant in variants}
        total_rounds = max(1, research_depth)
        for round_index in range(1, total_rounds):
            followups = [item for item in follow_up_queries(query, run.results, research_breadth) if item["query"].lower() not in seen_queries]
            if not followups:
                run.research_rounds.append({"round": round_index, "queries": [], "result_count": 0, "reason": "no novel follow-up queries"})
                break
            followup_queries = [item["query"] for item in followups]
            seen_queries.update(item.lower() for item in followup_queries)
            round_results = collect_from_sources(
                variants=followup_queries,
                selected_sources=selected_sources,
                context=context,
                run=run,
                limit=limit,
                query=query,
            )
            collected.extend(round_results)
            run.research_rounds.append({"round": round_index, "queries": followups, "result_count": len(round_results), "reason": "follow-up expansion"})
            run.results, run.result_groups = dedupe_rank_and_group(collected, query)

    for item in run.results[: max(0, fetch_top)]:
        check = verify_for_mode(
            item.url,
            timeout=timeout,
            link_limit=max_page_links if detective or dig_pages else 0,
            verify_mode=verify_mode,
        )
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
        apply_quality_score(item)
        rank_result(item, query)

    discovery_results = build_discovery_results(
        run,
        query,
        dig_pages=dig_pages,
        include_offsite=include_offsite,
    )
    for item in discovery_results:
        check = verify_for_mode(item.url, timeout=timeout, link_limit=0, verify_mode=verify_mode)
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
        apply_quality_score(item)
        rank_result(item, query)
    if discovery_results:
        collected.extend(discovery_results)
        run.results, run.result_groups = dedupe_rank_and_group(collected, query)

    run.results, run.result_groups = dedupe_rank_and_group(collected if collected else run.results, query)
    run.elapsed_ms = int((time.monotonic() - started) * 1000)
    return run
