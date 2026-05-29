"""Search orchestration."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from typing import Callable

from .claims import build_claim_ledger
from .config import DEFAULT_LOCAL_LLM_MODEL, DEFAULT_PACKS, DISCOVERY_POLICY
from .dedupe import group_results
from .discovery import build_discovery_results
from .http import reset_transport_stats, set_transport_options, transport_stats, verify_url
from .models import SearchContext, SearchError, SearchResult, SearchRun, SourceSpec
from .quality import apply_quality_score
from .ranking import rank_result
from .render import should_render_fallback, verify_rendered_url
from .research import build_follow_up_plan, follow_up_queries, source_coverage
from .sources import SOURCES
from .text import canonicalize_url, generate_query_variants, unique

ProgressFn = Callable[[str], None] | None


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


def elapsed_seconds(started: float) -> float:
    return time.monotonic() - started


def time_budget_exhausted(started: float, time_budget: float | None) -> bool:
    return time_budget is not None and time_budget > 0 and elapsed_seconds(started) >= time_budget


def emit_progress(progress: ProgressFn, started: float, message: str) -> None:
    if progress:
        progress(f"[deep-search {elapsed_seconds(started):.1f}s] {message}")


def suppressible_source_error(message: str) -> bool:
    value = message.lower()
    return "http 403" in value or "http 429" in value or "timed out" in value or "timeout" in value


def update_suppressed_sources(run: SearchRun, start_index: int, suppressed: set[str]) -> None:
    for error in run.errors[start_index:]:
        if suppressible_source_error(error.message):
            suppressed.add(error.source)


def target_packs_for_followup(item: dict[str, str], selected_packs: list[str]) -> list[str]:
    haystack = " ".join(str(item.get(key, "")) for key in ("query", "reason", "type")).lower()
    if "cover page gap" in haystack:
        return []
    targets: list[str] = []
    if "news" in haystack or "report" in haystack or "latest" in haystack:
        targets.append("news")
    if "community" in haystack or "reaction" in haystack or "discussion" in haystack:
        targets.append("community")
    if any(token in haystack for token in ("github", "issue", "release", "changelog", "implementation", "package", "registry")):
        targets.append("tech")
    if any(token in haystack for token in ("paper", "doi", "citation", "citations", "research", "arxiv", "semantic scholar")):
        targets.append("research")
    filtered = [pack for pack in unique(targets) if pack in selected_packs]
    return filtered or selected_packs


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
    max_workers: int = 1,
    progress: ProgressFn = None,
    started: float | None = None,
) -> list[SearchResult]:
    def call_source(source: SourceSpec, variant: str) -> tuple[list[SearchResult], SearchError | None]:
        try:
            source_results = source.adapter(variant, context)
            prepared: list[SearchResult] = []
            for item in source_results[:limit]:
                item.source = source.name
                item.pack = source.pack
                item.source_type = source.source_type
                item.metadata.setdefault("trust_weight", source.trust_weight)
                apply_quality_score(item)
                rank_result(item, query, source.trust_weight)
                prepared.append(item)
            return prepared, None
        except Exception as exc:
            return [], SearchError(source=source.name, pack=source.pack, query_variant=variant, message=str(exc))

    tasks = [(source, variant) for source in selected_sources for variant in variants]
    collected: list[SearchResult] = []
    if not tasks:
        return collected

    workers = max(1, min(max_workers, len(tasks)))
    if workers == 1:
        for source, variant in tasks:
            results, error = call_source(source, variant)
            collected.extend(results)
            if error:
                run.errors.append(error)
        if started is not None:
            emit_progress(progress, started, f"sources done: {len(collected)} results, {len(tasks)} calls")
        return collected

    completed = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(call_source, source, variant) for source, variant in tasks]
        for future in as_completed(futures):
            completed += 1
            results, error = future.result()
            collected.extend(results)
            if error:
                run.errors.append(error)
    if started is not None:
        emit_progress(progress, started, f"sources done: {len(collected)} results, {completed} calls, workers {workers}")
    return collected


def update_local_llm_status(run: SearchRun, status: dict[str, object]) -> None:
    if not status:
        return
    if not run.local_llm:
        run.local_llm = dict(status)
        return
    attempted = list(run.local_llm.get("attempted_models", []))
    for item in status.get("attempted_models", []) if isinstance(status.get("attempted_models"), list) else []:
        if item not in attempted:
            attempted.append(item)
    run.local_llm.update(status)
    run.local_llm["attempted_models"] = attempted


def fetch_result(
    item: SearchResult,
    run: SearchRun,
    *,
    timeout: float,
    link_limit: int,
    verify_mode: str,
    query: str,
    discovery_depth: int,
    append_discovered: bool = False,
) -> None:
    check = verify_for_mode(item.url, timeout=timeout, link_limit=link_limit, verify_mode=verify_mode)
    check.metadata.setdefault("discovery_depth", discovery_depth)
    check.metadata.setdefault("parent_chain", item.metadata.get("parent_chain", []))
    run.fetched_urls.append(check)
    if append_discovered:
        run.discovered_urls.append(item.url)
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
    crawl_depth: int = 1,
    max_total_fetches: int = 0,
    include_offsite: bool = True,
    locale: str = "ko-KR",
    timeout: float = 12.0,
    sources: list[SourceSpec] | None = None,
    research: bool = False,
    research_depth: int = 2,
    research_breadth: int = 4,
    verify_mode: str = "basic",
    local_llm_mode: str = "off",
    local_llm_model: str = DEFAULT_LOCAL_LLM_MODEL,
    local_llm_timeout: float | None = None,
    local_llm_fallback: bool = True,
    cache: str = "off",
    cache_dir: str | None = None,
    max_workers: int = 1,
    time_budget: float | None = None,
    progress: ProgressFn = None,
) -> SearchRun:
    if verify_mode not in {"basic", "auto", "rendered"}:
        raise ValueError(f"Unknown verify_mode: {verify_mode}")
    if local_llm_mode not in {"auto", "off", "required"}:
        raise ValueError(f"Unknown local_llm mode: {local_llm_mode}")
    if cache not in {"on", "off"}:
        raise ValueError(f"Unknown cache mode: {cache}")
    set_transport_options(cache_enabled=cache == "on", cache_dir=cache_dir)
    reset_transport_stats()
    started = time.monotonic()
    emit_progress(progress, started, f"start query={query!r} depth={depth} research={research}")
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
        crawl_depth=crawl_depth,
        max_total_fetches=max_total_fetches,
        research=research,
        research_depth=research_depth if research else 0,
        research_breadth=research_breadth if research else 0,
        verify_mode=verify_mode,
        local_llm_mode=local_llm_mode,
        local_llm_model=local_llm_model,
        local_llm_timeout=local_llm_timeout,
        cache=cache,
        max_workers=max(1, max_workers),
        time_budget=time_budget,
        local_llm={"provider": "ollama", "mode": local_llm_mode, "requested_model": local_llm_model, "available": False, "fallback": local_llm_mode == "off"},
    )
    run.local_llm["timeout"] = local_llm_timeout

    selected_sources = [source for source in (sources or SOURCES) if source.pack in selected_packs]
    suppressed_sources: set[str] = set()
    llm_claim_candidates: list[dict[str, object]] = []
    emit_progress(progress, started, f"round 0 sources={len(selected_sources)} variants={len(variants)}")
    error_start = len(run.errors)
    collected = collect_from_sources(
        variants=variants,
        selected_sources=selected_sources,
        context=context,
        run=run,
        limit=limit,
        query=query,
        max_workers=max_workers,
        progress=progress,
        started=started,
    )
    update_suppressed_sources(run, error_start, suppressed_sources)
    if research:
        run.research_rounds.append({"round": 0, "queries": variants, "result_count": len(collected), "reason": "initial variants"})

    run.results, run.result_groups = dedupe_rank_and_group(collected, query)
    run.coverage = source_coverage(run.results)

    if research:
        seen_queries = {variant.lower() for variant in variants}
        total_rounds = max(1, research_depth)
        for round_index in range(1, total_rounds):
            if time_budget_exhausted(started, time_budget):
                emit_progress(progress, started, f"round {round_index} skipped: time budget exhausted")
                run.research_rounds.append({"round": round_index, "queries": [], "result_count": 0, "reason": "time budget exhausted"})
                break
            emit_progress(progress, started, f"round {round_index} planning")
            followups, planner_step, claim_candidates = build_follow_up_plan(
                query,
                run.results,
                research_breadth,
                coverage=run.coverage,
                local_llm_mode=local_llm_mode,
                local_llm_model=local_llm_model,
                local_llm_timeout=local_llm_timeout,
                local_llm_fallback=local_llm_fallback,
            )
            planner_step["round"] = round_index
            run.planner_steps.append(planner_step)
            update_local_llm_status(run, planner_step.get("local_llm", {}) if isinstance(planner_step.get("local_llm"), dict) else {})
            if local_llm_mode == "required" and run.local_llm.get("fallback"):
                raise RuntimeError(f"local LLM required but unavailable: {run.local_llm.get('error') or 'unknown error'}")
            llm_claim_candidates.extend(claim_candidates)
            followups = [item for item in followups if item["query"].lower() not in seen_queries]
            if not followups:
                run.research_rounds.append({"round": round_index, "queries": [], "result_count": 0, "reason": "no novel follow-up queries"})
                break
            for item in followups:
                item["target_packs"] = target_packs_for_followup(item, selected_packs)  # type: ignore[assignment]
            followup_queries = [item["query"] for item in followups]
            seen_queries.update(item.lower() for item in followup_queries)
            round_results: list[SearchResult] = []
            for item in followups:
                if time_budget_exhausted(started, time_budget):
                    emit_progress(progress, started, f"round {round_index} stopped: time budget exhausted")
                    break
                target_packs = item.get("target_packs", selected_packs)
                target_sources = [
                    source
                    for source in selected_sources
                    if source.pack in target_packs and source.name not in suppressed_sources
                ]
                if not target_sources:
                    continue
                error_start = len(run.errors)
                round_results.extend(
                    collect_from_sources(
                        variants=[item["query"]],
                        selected_sources=target_sources,
                        context=context,
                        run=run,
                        limit=limit,
                        query=query,
                        max_workers=max_workers,
                        progress=progress,
                        started=started,
                    )
                )
                update_suppressed_sources(run, error_start, suppressed_sources)
            collected.extend(round_results)
            run.research_rounds.append({"round": round_index, "queries": followups, "result_count": len(round_results), "reason": "follow-up expansion"})
            run.results, run.result_groups = dedupe_rank_and_group(collected, query)
            run.coverage = source_coverage(run.results)

    effective_max_fetches = max_total_fetches if max_total_fetches > 0 else fetch_top + dig_pages
    for item in run.results[: max(0, min(fetch_top, effective_max_fetches))]:
        if time_budget_exhausted(started, time_budget):
            emit_progress(progress, started, "top URL verification stopped: time budget exhausted")
            break
        emit_progress(progress, started, f"fetch {len(run.fetched_urls) + 1}/{effective_max_fetches}: {item.url}")
        fetch_result(
            item,
            run,
            timeout=timeout,
            link_limit=max_page_links if detective or dig_pages else 0,
            verify_mode=verify_mode,
            query=query,
            discovery_depth=0,
        )

    if dig_pages > 0 and effective_max_fetches > len(run.fetched_urls):
        for depth_level in range(1, max(1, crawl_depth) + 1):
            if time_budget_exhausted(started, time_budget):
                emit_progress(progress, started, f"crawl depth {depth_level} skipped: time budget exhausted")
                break
            remaining_discoveries = max(0, dig_pages - len(run.discovered_urls))
            remaining_fetches = max(0, effective_max_fetches - len(run.fetched_urls))
            if remaining_discoveries <= 0 or remaining_fetches <= 0:
                break
            discovery_results = build_discovery_results(
                run,
                query,
                dig_pages=min(remaining_discoveries, remaining_fetches),
                include_offsite=include_offsite,
                current_depth=depth_level,
            )
            if not discovery_results:
                break
            for item in discovery_results:
                if time_budget_exhausted(started, time_budget):
                    emit_progress(progress, started, f"crawl depth {depth_level} stopped: time budget exhausted")
                    break
                link_limit = max_page_links if depth_level < crawl_depth else 0
                emit_progress(progress, started, f"crawl fetch depth {depth_level}: {item.url}")
                fetch_result(
                    item,
                    run,
                    timeout=timeout,
                    link_limit=link_limit,
                    verify_mode=verify_mode,
                    query=query,
                    discovery_depth=depth_level,
                    append_discovered=True,
                )
                run.crawl_traces.append(
                    {
                        "url": item.url,
                        "parent_url": item.metadata.get("parent_url", ""),
                        "parent_chain": item.metadata.get("parent_chain", []),
                        "depth": depth_level,
                        "reason": item.metadata.get("discovery_reason", []),
                        "fetch_verdict": item.fetch_verdict,
                    }
                )
            collected.extend(discovery_results)
            run.results, run.result_groups = dedupe_rank_and_group(collected, query)
            run.coverage = source_coverage(run.results)

    run.results, run.result_groups = dedupe_rank_and_group(collected if collected else run.results, query)
    run.coverage = source_coverage(run.results)
    run.claims = build_claim_ledger(query, run.results, run.result_groups, llm_claim_candidates)
    run.cache_stats, run.retry_stats = transport_stats()
    run.elapsed_ms = int((time.monotonic() - started) * 1000)
    emit_progress(progress, started, f"done results={len(run.results)} errors={len(run.errors)} elapsed_ms={run.elapsed_ms}")
    return run
