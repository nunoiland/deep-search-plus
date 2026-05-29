"""Identity-based grouping and deduplication."""

from __future__ import annotations

import hashlib
import re
import urllib.parse

from .models import SearchResult
from .text import canonicalize_url, host_for, normalize_text


def normalize_doi(value: object) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"^https?://(dx\.)?doi\.org/", "", text)
    text = text.removeprefix("doi:")
    return text.strip()


def github_repo_key(url: str, metadata: dict[str, object]) -> str:
    repo = str(metadata.get("repository") or metadata.get("full_name") or "").strip().lower()
    if repo and "/" in repo:
        return repo
    parsed = urllib.parse.urlsplit(url)
    if (parsed.hostname or "").lower() != "github.com":
        return ""
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(parts) >= 2:
        return f"{parts[0].lower()}/{parts[1].lower()}"
    return ""


def arxiv_key(result: SearchResult) -> str:
    metadata_id = str(result.metadata.get("arxiv_id") or "").strip().lower()
    if metadata_id:
        return metadata_id
    parsed = urllib.parse.urlsplit(result.url)
    if "arxiv.org" not in (parsed.hostname or ""):
        return ""
    match = re.search(r"/(?:abs|pdf)/([0-9.]+(?:v\d+)?)", parsed.path)
    if not match:
        return ""
    return re.sub(r"v\d+$", "", match.group(1).lower())


def normalized_title(value: str) -> str:
    text = normalize_text(value).lower()
    text = re.sub(r"[^a-z0-9가-힣]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def identity_key(result: SearchResult) -> str:
    doi = normalize_doi(result.metadata.get("doi"))
    if doi:
        return f"doi:{doi}"

    arxiv = arxiv_key(result)
    if arxiv:
        return f"arxiv:{arxiv}"

    paper_id = str(result.metadata.get("paper_id") or result.metadata.get("semantic_scholar_id") or "").strip()
    if paper_id:
        return f"semantic_scholar:{paper_id}"

    repo = github_repo_key(result.url, result.metadata)
    if repo:
        return f"github:{repo}"

    canonical = canonicalize_url(result.url)
    if canonical:
        return f"url:{canonical}"

    title = normalized_title(result.title)
    host = host_for(result.url)
    if title and host:
        return f"title_domain:{host}:{title}"
    return f"title:{title or result.title.lower()}"


def group_id_for(key: str) -> str:
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]
    return f"grp_{digest}"


def _duplicate_summary(item: SearchResult) -> dict[str, object]:
    return {
        "source": item.source,
        "title": item.title,
        "url": item.url,
        "rank_score": round(float(item.rank_score), 3),
        "quality_score": item.metadata.get("quality_score"),
    }


def group_results(results: list[SearchResult]) -> tuple[list[SearchResult], list[dict[str, object]]]:
    grouped: dict[str, list[SearchResult]] = {}
    for item in results:
        grouped.setdefault(identity_key(item), []).append(item)

    representatives: list[SearchResult] = []
    group_summaries: list[dict[str, object]] = []
    for key, items in grouped.items():
        items.sort(key=lambda item: item.rank_score, reverse=True)
        representative = items[0]
        group_id = group_id_for(key)
        supporting_sources = sorted({item.source for item in items})
        representative.metadata["group_id"] = group_id
        representative.metadata["identity_key"] = key
        representative.metadata["duplicate_count"] = len(items)
        representative.metadata["supporting_sources"] = supporting_sources
        if len(items) > 1:
            representative.metadata["duplicates"] = [_duplicate_summary(item) for item in items[1:]]
        representatives.append(representative)
        group_summaries.append(
            {
                "group_id": group_id,
                "identity_key": key,
                "representative_url": representative.url,
                "representative_title": representative.title,
                "duplicate_count": len(items),
                "supporting_sources": supporting_sources,
                "urls": [item.url for item in items],
            }
        )

    representatives.sort(key=lambda item: item.rank_score, reverse=True)
    group_summaries.sort(key=lambda item: int(item["duplicate_count"]), reverse=True)
    return representatives, group_summaries
