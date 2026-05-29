"""Codex-native public evidence deep search package."""

from __future__ import annotations

from .cli import build_parser, main, non_negative_float, positive_int
from .claims import build_claim_ledger, claim_key, classify_claim, normalize_claim, result_claim
from .config import (
    DEFAULT_LOCAL_LLM_MODEL,
    DEFAULT_OLLAMA_HOST,
    DISCOVERY_POLICY,
    FETCH_POLICY,
    LOCAL_LLM_FALLBACK_MODELS,
    LOW_VALUE_LINK_HINTS,
    LOW_VALUE_QUERY_PARAMS,
    RANKING_POLICY,
    SKIP_LINK_EXTENSIONS,
    STOPWORDS,
    TRACKING_PARAMS,
    USER_AGENT,
)
from .dedupe import arxiv_key, github_repo_key, group_results, identity_key, normalize_doi, normalized_title
from .discovery import build_discovery_results, discovered_link_analysis, discovered_link_score
from .html_tools import LinkParser, MetadataParser, extract_links, extract_metadata
from .http import detect_blocked_signals, fetch_bytes, fetch_verdict, http_headers, read_json, read_text, reset_transport_stats, set_transport_options, transport_stats, urllib_context, verify_url
from .local_llm import configured_model, extract_json_object, generate_json, local_llm_timeout, model_candidates, ollama_generate, ollama_host
from .models import FetchCheck, SearchContext, SearchError, SearchResult, SearchRun, SourceSpec
from .quality import apply_quality_score
from .ranking import query_match_score, rank_result, recency_score
from .render import should_render_fallback, verify_rendered_url
from .report import format_report, group_by, result_line
from .research import build_follow_up_plan, follow_up_queries, heuristic_follow_up_queries, local_llm_follow_up_plan, source_coverage
from .results import result
from .runner import dedupe_and_rank, dedupe_rank_and_group, parse_packs, run_search, variants_for_depth, verify_for_mode
from .source_catalog import (
    SOURCE_BY_NAME,
    SOURCE_DEFINITIONS,
    SourceDefinition,
    endpoint_for,
    endpoints_for,
    source_definition,
    validate_source_definitions,
)
from .sources import SOURCES
from .sources.adapters import (
    arxiv_search,
    crossref_search,
    devto_search,
    first_tag_candidate,
    gdelt_news,
    github_issues,
    github_repositories,
    google_news_en,
    google_news_ko,
    hacker_news_search,
    huggingface_datasets,
    huggingface_models,
    lobsters_search,
    npm_search,
    openalex_search,
    openlibrary_search,
    package_candidates,
    parse_rss,
    pypi_lookup,
    reddit_search,
    semantic_scholar_search,
    stackoverflow_search,
    v2ex_search,
    wikipedia_search,
)
from .text import (
    build_url,
    canonicalize_url,
    compact_url,
    generate_query_variants,
    has_skipped_extension,
    host_for,
    is_http_url,
    is_low_value_link,
    iso_from_timestamp,
    meaningful_tokens,
    normalize_text,
    parse_datetime,
    same_site,
    tokenize,
    unique,
)

__all__ = [name for name in globals() if not name.startswith("_")]
