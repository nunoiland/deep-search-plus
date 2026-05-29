"""Source registry with adapter bindings."""

from __future__ import annotations

from ..models import SourceSpec
from ..source_catalog import SOURCE_DEFINITIONS, validate_source_definitions
from . import adapters


ADAPTERS = {
    "google_news_ko": adapters.google_news_ko,
    "google_news_en": adapters.google_news_en,
    "gdelt_news": adapters.gdelt_news,
    "reddit": adapters.reddit_search,
    "hacker_news": adapters.hacker_news_search,
    "lobsters": adapters.lobsters_search,
    "devto": adapters.devto_search,
    "v2ex": adapters.v2ex_search,
    "github_repositories": adapters.github_repositories,
    "github_issues": adapters.github_issues,
    "stackoverflow": adapters.stackoverflow_search,
    "npm": adapters.npm_search,
    "pypi": adapters.pypi_lookup,
    "huggingface_models": adapters.huggingface_models,
    "huggingface_datasets": adapters.huggingface_datasets,
    "arxiv": adapters.arxiv_search,
    "crossref": adapters.crossref_search,
    "openalex": adapters.openalex_search,
    "semantic_scholar": adapters.semantic_scholar_search,
    "openlibrary": adapters.openlibrary_search,
    "wikipedia": adapters.wikipedia_search,
}


def build_sources() -> list[SourceSpec]:
    errors = validate_source_definitions()
    missing = sorted(source.name for source in SOURCE_DEFINITIONS if source.name not in ADAPTERS)
    if missing:
        errors.append(f"missing adapters: {', '.join(missing)}")
    if errors:
        raise RuntimeError("; ".join(errors))
    return [
        SourceSpec(
            name=source.name,
            pack=source.pack,
            source_type=source.source_type,
            trust_weight=source.trust_weight,
            endpoints=source.endpoints,
            adapter=ADAPTERS[source.name],
        )
        for source in SOURCE_DEFINITIONS
    ]


SOURCES = build_sources()

__all__ = ["ADAPTERS", "SOURCES", "build_sources"]
