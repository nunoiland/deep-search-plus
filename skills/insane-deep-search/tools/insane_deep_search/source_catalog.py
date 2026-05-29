"""Search source catalog and validation."""

from __future__ import annotations

import dataclasses

from .config import VALID_PACKS, VALID_SOURCE_TYPES


@dataclasses.dataclass(frozen=True)
class SourceDefinition:
    name: str
    pack: str
    source_type: str
    trust_weight: float
    endpoints: tuple[str, ...]
    base_url: str = ""


SOURCE_DEFINITIONS: tuple[SourceDefinition, ...] = (
    SourceDefinition(
        "google_news_ko",
        "news",
        "news",
        4.0,
        ("https://news.google.com/rss/search",),
    ),
    SourceDefinition(
        "google_news_en",
        "news",
        "news",
        4.0,
        ("https://news.google.com/rss/search",),
    ),
    SourceDefinition(
        "gdelt_news",
        "news",
        "news",
        3.5,
        ("https://api.gdeltproject.org/api/v2/doc/doc",),
    ),
    SourceDefinition(
        "reddit",
        "community",
        "community",
        1.5,
        ("https://www.reddit.com/search.json",),
        "https://www.reddit.com",
    ),
    SourceDefinition(
        "hacker_news",
        "community",
        "community",
        2.0,
        ("https://hn.algolia.com/api/v1/search",),
        "https://news.ycombinator.com",
    ),
    SourceDefinition(
        "lobsters",
        "community",
        "community",
        1.5,
        ("https://lobste.rs/search.json",),
    ),
    SourceDefinition(
        "devto",
        "community",
        "community",
        1.2,
        ("https://dev.to/api/articles",),
    ),
    SourceDefinition(
        "v2ex",
        "community",
        "community",
        1.0,
        ("https://www.v2ex.com/api/topics/hot.json", "https://www.v2ex.com/api/topics/latest.json"),
    ),
    SourceDefinition(
        "github_repositories",
        "tech",
        "developer",
        3.0,
        ("https://api.github.com/search/repositories",),
    ),
    SourceDefinition(
        "github_issues",
        "tech",
        "developer",
        2.5,
        ("https://api.github.com/search/issues",),
    ),
    SourceDefinition(
        "stackoverflow",
        "tech",
        "developer",
        2.5,
        ("https://api.stackexchange.com/2.3/search/advanced",),
    ),
    SourceDefinition(
        "npm",
        "tech",
        "registry",
        3.0,
        ("https://registry.npmjs.org/-/v1/search",),
        "https://www.npmjs.com/package",
    ),
    SourceDefinition(
        "pypi",
        "tech",
        "registry",
        3.0,
        ("https://pypi.org/pypi/{name}/json",),
        "https://pypi.org/project",
    ),
    SourceDefinition(
        "huggingface_models",
        "tech",
        "developer",
        2.5,
        ("https://huggingface.co/api/models",),
        "https://huggingface.co",
    ),
    SourceDefinition(
        "huggingface_datasets",
        "tech",
        "developer",
        2.5,
        ("https://huggingface.co/api/datasets",),
        "https://huggingface.co/datasets",
    ),
    SourceDefinition(
        "arxiv",
        "research",
        "research",
        4.0,
        ("https://export.arxiv.org/api/query",),
    ),
    SourceDefinition(
        "crossref",
        "research",
        "research",
        4.0,
        ("https://api.crossref.org/works",),
    ),
    SourceDefinition(
        "openalex",
        "research",
        "research",
        4.0,
        ("https://api.openalex.org/works",),
    ),
    SourceDefinition(
        "semantic_scholar",
        "research",
        "research",
        4.0,
        ("https://api.semanticscholar.org/graph/v1/paper/search",),
        "https://www.semanticscholar.org/paper",
    ),
    SourceDefinition(
        "openlibrary",
        "research",
        "research",
        2.0,
        ("https://openlibrary.org/search.json",),
        "https://openlibrary.org",
    ),
    SourceDefinition(
        "wikipedia",
        "research",
        "research",
        2.5,
        ("https://{lang}.wikipedia.org/w/api.php",),
    ),
)

SOURCE_BY_NAME = {source.name: source for source in SOURCE_DEFINITIONS}


def source_definition(name: str) -> SourceDefinition:
    return SOURCE_BY_NAME[name]


def endpoints_for(name: str) -> tuple[str, ...]:
    return source_definition(name).endpoints


def endpoint_for(name: str, index: int = 0) -> str:
    return endpoints_for(name)[index]


def validate_source_definitions() -> list[str]:
    errors: list[str] = []
    names: set[str] = set()
    for source in SOURCE_DEFINITIONS:
        if source.name in names:
            errors.append(f"duplicate source name: {source.name}")
        names.add(source.name)
        if source.pack not in VALID_PACKS:
            errors.append(f"{source.name}: invalid pack {source.pack}")
        if source.source_type not in VALID_SOURCE_TYPES:
            errors.append(f"{source.name}: invalid source_type {source.source_type}")
        if source.trust_weight <= 0:
            errors.append(f"{source.name}: trust_weight must be positive")
        if not source.endpoints:
            errors.append(f"{source.name}: missing endpoint")
        for endpoint in source.endpoints:
            if not endpoint.startswith("https://"):
                errors.append(f"{source.name}: endpoint must use https")
    return errors
