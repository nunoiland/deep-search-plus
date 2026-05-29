"""Public source adapters."""

from __future__ import annotations

import datetime as dt
import base64
import os
import re
import urllib.parse
import xml.etree.ElementTree as ET

from ..http import read_json, read_text
from ..models import SearchContext, SearchResult
from ..results import result
from ..source_catalog import endpoint_for, endpoints_for, source_definition
from ..text import build_url, iso_from_timestamp, tokenize, unique


def parse_rss(text: str, source: str, variant: str, limit: int) -> list[SearchResult]:
    root = ET.fromstring(text)
    items = []
    for item in root.findall(".//item")[:limit]:
        title = item.findtext("title") or ""
        link = item.findtext("link") or ""
        description = item.findtext("description") or ""
        published = item.findtext("pubDate") or item.findtext("published")
        items.append(
            result(
                source=source,
                pack="news",
                source_type="news",
                query_variant=variant,
                title=title,
                url=link,
                snippet=re.sub(r"<[^>]+>", " ", description),
                published=published,
                score=5.0,
            )
        )
    return items


def google_news_ko(variant: str, context: SearchContext) -> list[SearchResult]:
    url = build_url(
        endpoint_for("google_news_ko"),
        {"q": variant, "hl": "ko", "gl": "KR", "ceid": "KR:ko"},
    )
    return parse_rss(read_text(url, context.timeout), "google_news_ko", variant, context.limit)


def google_news_en(variant: str, context: SearchContext) -> list[SearchResult]:
    url = build_url(
        endpoint_for("google_news_en"),
        {"q": variant, "hl": "en-US", "gl": "US", "ceid": "US:en"},
    )
    return parse_rss(read_text(url, context.timeout), "google_news_en", variant, context.limit)


def gdelt_news(variant: str, context: SearchContext) -> list[SearchResult]:
    data = read_json(
        build_url(
            endpoint_for("gdelt_news"),
            {"query": variant, "mode": "artlist", "format": "json", "maxrecords": min(50, context.limit), "sort": "datedesc"},
        ),
        context.timeout,
    )
    items = []
    for article in data.get("articles", []) if isinstance(data, dict) else []:
        items.append(
            result(
                source="gdelt_news",
                pack="news",
                source_type="news",
                query_variant=variant,
                title=article.get("title", ""),
                url=article.get("url", ""),
                snippet=article.get("snippet") or article.get("domain", ""),
                published=article.get("seendate"),
                score=4.0,
                metadata={
                    "domain": article.get("domain"),
                    "language": article.get("language"),
                    "source_country": article.get("sourcecountry"),
                    "tone": article.get("tone"),
                },
            )
        )
    return items


def reddit_search(variant: str, context: SearchContext) -> list[SearchResult]:
    definition = source_definition("reddit")
    data = read_json(
        build_url(endpoint_for("reddit"), {"q": variant, "sort": "relevance", "limit": context.limit, "raw_json": 1}),
        context.timeout,
    )
    items = []
    for child in data.get("data", {}).get("children", []):
        post = child.get("data", {})
        permalink = post.get("permalink") or ""
        url = definition.base_url + permalink if permalink.startswith("/") else post.get("url", "")
        comments = int(post.get("num_comments") or 0)
        points = int(post.get("score") or 0)
        items.append(
            result(
                source="reddit",
                pack="community",
                source_type="community",
                query_variant=variant,
                title=post.get("title", ""),
                url=url,
                snippet=post.get("selftext", "")[:700],
                published=iso_from_timestamp(post.get("created_utc")),
                score=3.0,
                metadata={"subreddit": post.get("subreddit"), "comments": comments, "points": points},
            )
        )
    return items


def hacker_news_search(variant: str, context: SearchContext) -> list[SearchResult]:
    definition = source_definition("hacker_news")
    data = read_json(
        build_url(endpoint_for("hacker_news"), {"query": variant, "tags": "story", "hitsPerPage": context.limit}),
        context.timeout,
    )
    items = []
    for hit in data.get("hits", []):
        object_id = hit.get("objectID")
        discussion = build_url(definition.base_url + "/item", {"id": object_id})
        url = hit.get("url") or discussion
        comments = int(hit.get("num_comments") or 0)
        points = int(hit.get("points") or 0)
        items.append(
            result(
                source="hacker_news",
                pack="community",
                source_type="community",
                query_variant=variant,
                title=hit.get("title") or hit.get("story_title") or "",
                url=url,
                snippet=hit.get("_highlightResult", {}).get("title", {}).get("value", ""),
                published=hit.get("created_at"),
                score=3.5,
                metadata={"comments": comments, "points": points, "discussion": discussion},
            )
        )
    return items


def lobsters_search(variant: str, context: SearchContext) -> list[SearchResult]:
    if not re.search(r"[A-Za-z0-9]", variant):
        return []
    data = read_json(
        build_url(endpoint_for("lobsters"), {"q": variant, "what": "stories", "order": "relevance"}),
        context.timeout,
    )
    items = []
    for story in (data if isinstance(data, list) else [])[: context.limit]:
        comments = int(story.get("comment_count") or story.get("comments_count") or 0)
        score = int(story.get("score") or 0)
        items.append(
            result(
                source="lobsters",
                pack="community",
                source_type="community",
                query_variant=variant,
                title=story.get("title", ""),
                url=story.get("url") or story.get("comments_url", ""),
                snippet=" ".join(story.get("tags", []) if isinstance(story.get("tags"), list) else []),
                published=story.get("created_at"),
                score=2.5,
                metadata={"comments": comments, "points": score},
            )
        )
    return items


def first_tag_candidate(variant: str) -> str:
    for token in tokenize(variant):
        cleaned = re.sub(r"[^A-Za-z0-9]", "", token).lower()
        if len(cleaned) >= 2:
            return cleaned[:30]
    return ""


def devto_search(variant: str, context: SearchContext) -> list[SearchResult]:
    tag = first_tag_candidate(variant)
    if not tag:
        return []
    data = read_json(build_url(endpoint_for("devto"), {"tag": tag, "per_page": context.limit}), context.timeout)
    items = []
    for article in data if isinstance(data, list) else []:
        items.append(
            result(
                source="devto",
                pack="community",
                source_type="community",
                query_variant=variant,
                title=article.get("title", ""),
                url=article.get("url", ""),
                snippet=article.get("description", ""),
                published=article.get("published_at"),
                score=2.0,
                metadata={
                    "tag": tag,
                    "comments": int(article.get("comments_count") or 0),
                    "points": int(article.get("public_reactions_count") or 0),
                },
            )
        )
    return items


def v2ex_search(variant: str, context: SearchContext) -> list[SearchResult]:
    tokens = [token.lower() for token in tokenize(variant)]
    items = []
    for endpoint in endpoints_for("v2ex"):
        data = read_json(endpoint, context.timeout)
        for topic in data if isinstance(data, list) else []:
            title = topic.get("title", "")
            content = topic.get("content", "")
            haystack = f"{title} {content}".lower()
            if tokens and not any(token in haystack for token in tokens):
                continue
            items.append(
                result(
                    source="v2ex",
                    pack="community",
                    source_type="community",
                    query_variant=variant,
                    title=title,
                    url=topic.get("url", ""),
                    snippet=content,
                    published=iso_from_timestamp(topic.get("created")),
                    score=2.0,
                    metadata={"comments": int(topic.get("replies") or 0)},
                )
            )
            if len(items) >= context.limit:
                return items
    return items


def github_headers(extra_accept: str | None = None) -> dict[str, str]:
    headers = {"Accept": extra_accept or "application/vnd.github+json"}
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def enrich_github_repo(repo: dict, context: SearchContext) -> dict[str, object]:
    metadata: dict[str, object] = {}
    api_url = repo.get("url") or ""
    if not api_url:
        return metadata

    try:
        readme = read_json(api_url + "/readme", context.timeout, github_headers())
        content = readme.get("content", "")
        if content:
            decoded = base64.b64decode(content.encode("ascii"), validate=False).decode("utf-8", errors="replace")
            metadata["readme_excerpt"] = decoded[:700]
        metadata["readme_url"] = readme.get("html_url")
    except Exception:
        pass

    try:
        license_info = read_json(api_url + "/license", context.timeout, github_headers())
        metadata["license"] = (license_info.get("license") or {}).get("spdx_id") or (license_info.get("license") or {}).get("key")
    except Exception:
        license_value = repo.get("license")
        if isinstance(license_value, dict):
            metadata["license"] = license_value.get("spdx_id") or license_value.get("key")

    try:
        release = read_json(api_url + "/releases/latest", context.timeout, github_headers())
        metadata["latest_release"] = release.get("tag_name") or release.get("name")
        metadata["latest_release_published"] = release.get("published_at")
    except Exception:
        pass

    return metadata


def github_repositories(variant: str, context: SearchContext) -> list[SearchResult]:
    data = read_json(
        build_url(endpoint_for("github_repositories"), {"q": variant, "sort": "updated", "order": "desc", "per_page": context.limit}),
        context.timeout,
        github_headers(),
    )
    items = []
    for index, repo in enumerate(data.get("items", [])):
        license_value = repo.get("license")
        metadata = {
            "stars": int(repo.get("stargazers_count") or 0),
            "forks": int(repo.get("forks_count") or 0),
            "language": repo.get("language"),
            "repository": repo.get("full_name"),
            "archived": bool(repo.get("archived")),
            "license": (license_value or {}).get("spdx_id") if isinstance(license_value, dict) else None,
        }
        if index < min(context.limit, 3):
            metadata.update(enrich_github_repo(repo, context))
        items.append(
            result(
                source="github_repositories",
                pack="tech",
                source_type="developer",
                query_variant=variant,
                title=repo.get("full_name", ""),
                url=repo.get("html_url", ""),
                snippet=repo.get("description", ""),
                published=repo.get("updated_at"),
                score=4.0,
                metadata=metadata,
            )
        )
    return items


def github_issues(variant: str, context: SearchContext) -> list[SearchResult]:
    data = read_json(
        build_url(endpoint_for("github_issues"), {"q": variant, "sort": "updated", "order": "desc", "per_page": context.limit}),
        context.timeout,
        github_headers("application/vnd.github.text-match+json"),
    )
    items = []
    for issue in data.get("items", []):
        repository_url = issue.get("repository_url", "")
        repository = repository_url.rsplit("/", 2)[-2:]
        text_matches = issue.get("text_matches") or []
        text_fragment = ""
        if text_matches and isinstance(text_matches, list):
            text_fragment = text_matches[0].get("fragment", "")
        items.append(
            result(
                source="github_issues",
                pack="tech",
                source_type="developer",
                query_variant=variant,
                title=issue.get("title", ""),
                url=issue.get("html_url", ""),
                snippet=text_fragment or issue.get("body", "") or "",
                published=issue.get("updated_at"),
                score=3.5,
                metadata={
                    "comments": int(issue.get("comments") or 0),
                    "state": issue.get("state"),
                    "is_pull_request": "pull_request" in issue,
                    "repository": "/".join(repository) if len(repository) == 2 else "",
                },
            )
        )
    return items


def stackoverflow_search(variant: str, context: SearchContext) -> list[SearchResult]:
    data = read_json(
        build_url(
            endpoint_for("stackoverflow"),
            {"order": "desc", "sort": "relevance", "q": variant, "site": "stackoverflow", "pagesize": context.limit},
        ),
        context.timeout,
    )
    items = []
    for question in data.get("items", []):
        items.append(
            result(
                source="stackoverflow",
                pack="tech",
                source_type="developer",
                query_variant=variant,
                title=question.get("title", ""),
                url=question.get("link", ""),
                snippet="; ".join(question.get("tags", [])),
                published=iso_from_timestamp(question.get("creation_date")),
                score=3.0,
                metadata={
                    "comments": int(question.get("answer_count") or 0),
                    "points": int(question.get("score") or 0),
                    "accepted_answer_id": question.get("accepted_answer_id"),
                },
            )
        )
    return items


def npm_search(variant: str, context: SearchContext) -> list[SearchResult]:
    definition = source_definition("npm")
    data = read_json(build_url(endpoint_for("npm"), {"text": variant, "size": context.limit}), context.timeout)
    items = []
    for package in data.get("objects", []):
        pkg = package.get("package", {})
        links = pkg.get("links", {})
        score_detail = package.get("score", {})
        name = pkg.get("name", "")
        items.append(
            result(
                source="npm",
                pack="tech",
                source_type="registry",
                query_variant=variant,
                title=name,
                url=links.get("npm") or f"{definition.base_url}/{name}",
                snippet=pkg.get("description", ""),
                published=pkg.get("date"),
                score=3.0 + float(score_detail.get("final") or 0),
                metadata={"version": pkg.get("version"), "publisher": (pkg.get("publisher") or {}).get("username")},
            )
        )
    return items


def package_candidates(variant: str) -> list[str]:
    candidates = []
    for token in tokenize(variant):
        cleaned = re.sub(r"[^A-Za-z0-9_.-]", "", token).strip("._-").lower()
        if 2 <= len(cleaned) <= 80:
            candidates.append(cleaned)
    return unique(candidates)[:4]


def pypi_lookup(variant: str, context: SearchContext) -> list[SearchResult]:
    definition = source_definition("pypi")
    items = []
    for name in package_candidates(variant):
        try:
            url = endpoint_for("pypi").format(name=urllib.parse.quote(name))
            data = read_json(url, context.timeout)
        except Exception:
            continue
        info = data.get("info", {})
        items.append(
            result(
                source="pypi",
                pack="tech",
                source_type="registry",
                query_variant=variant,
                title=info.get("name", name),
                url=info.get("package_url") or f"{definition.base_url}/{name}/",
                snippet=info.get("summary", ""),
                published=info.get("release_url"),
                score=3.0,
                metadata={"version": info.get("version"), "license": info.get("license")},
            )
        )
        if len(items) >= context.limit:
            break
    return items


def huggingface_models(variant: str, context: SearchContext) -> list[SearchResult]:
    definition = source_definition("huggingface_models")
    data = read_json(build_url(endpoint_for("huggingface_models"), {"search": variant, "limit": context.limit}), context.timeout)
    items = []
    for model in data if isinstance(data, list) else []:
        model_id = model.get("modelId") or model.get("id", "")
        items.append(
            result(
                source="huggingface_models",
                pack="tech",
                source_type="developer",
                query_variant=variant,
                title=model_id,
                url=f"{definition.base_url}/{model_id}",
                snippet=", ".join(model.get("tags", [])[:8]) if isinstance(model.get("tags"), list) else "",
                published=model.get("lastModified"),
                score=3.0,
                metadata={"downloads": int(model.get("downloads") or 0), "likes": int(model.get("likes") or 0)},
            )
        )
    return items


def huggingface_datasets(variant: str, context: SearchContext) -> list[SearchResult]:
    definition = source_definition("huggingface_datasets")
    data = read_json(build_url(endpoint_for("huggingface_datasets"), {"search": variant, "limit": context.limit}), context.timeout)
    items = []
    for dataset in data if isinstance(data, list) else []:
        dataset_id = dataset.get("id", "")
        items.append(
            result(
                source="huggingface_datasets",
                pack="tech",
                source_type="developer",
                query_variant=variant,
                title=dataset_id,
                url=f"{definition.base_url}/{dataset_id}",
                snippet=", ".join(dataset.get("tags", [])[:8]) if isinstance(dataset.get("tags"), list) else "",
                published=dataset.get("lastModified"),
                score=3.0,
                metadata={"downloads": int(dataset.get("downloads") or 0), "likes": int(dataset.get("likes") or 0)},
            )
        )
    return items


def arxiv_search(variant: str, context: SearchContext) -> list[SearchResult]:
    text = read_text(
        build_url(
            endpoint_for("arxiv"),
            {"search_query": f"all:{variant}", "start": 0, "max_results": context.limit, "sortBy": "relevance", "sortOrder": "descending"},
        ),
        context.timeout,
    )
    root = ET.fromstring(text)
    ns = {"a": "http://www.w3.org/2005/Atom"}
    items = []
    for entry in root.findall("a:entry", ns):
        title = entry.findtext("a:title", default="", namespaces=ns)
        link = ""
        for node in entry.findall("a:link", ns):
            if node.attrib.get("rel") == "alternate":
                link = node.attrib.get("href", "")
                break
        authors = [node.findtext("a:name", default="", namespaces=ns) for node in entry.findall("a:author", ns)]
        items.append(
            result(
                source="arxiv",
                pack="research",
                source_type="research",
                query_variant=variant,
                title=title,
                url=link,
                snippet=entry.findtext("a:summary", default="", namespaces=ns),
                published=entry.findtext("a:published", default="", namespaces=ns),
                score=4.0,
                metadata={"authors": [author for author in authors if author]},
            )
        )
    return items


def crossref_search(variant: str, context: SearchContext) -> list[SearchResult]:
    data = read_json(build_url(endpoint_for("crossref"), {"query": variant, "rows": context.limit}), context.timeout)
    items = []
    for work in data.get("message", {}).get("items", []):
        title = " ".join(work.get("title", [])[:1])
        url = work.get("URL", "")
        published = None
        date_parts = (work.get("published-print") or work.get("published-online") or work.get("created") or {}).get("date-parts")
        if date_parts and date_parts[0]:
            parts = [int(part) for part in date_parts[0]]
            while len(parts) < 3:
                parts.append(1)
            published = dt.date(parts[0], parts[1], parts[2]).isoformat()
        items.append(
            result(
                source="crossref",
                pack="research",
                source_type="research",
                query_variant=variant,
                title=title,
                url=url,
                snippet="; ".join(work.get("subject", [])[:5]),
                published=published,
                score=4.0,
                metadata={
                    "doi": work.get("DOI"),
                    "citations": int(work.get("is-referenced-by-count") or 0),
                    "publisher": work.get("publisher"),
                },
            )
        )
    return items


def openalex_search(variant: str, context: SearchContext) -> list[SearchResult]:
    data = read_json(
        build_url(endpoint_for("openalex"), {"search": variant, "per_page": context.limit}),
        context.timeout,
    )
    items = []
    for work in data.get("results", []) if isinstance(data, dict) else []:
        primary = work.get("primary_location") or {}
        source = primary.get("source") or {}
        open_access = work.get("open_access") or {}
        url = primary.get("landing_page_url") or work.get("doi") or work.get("id", "")
        year = work.get("publication_year")
        items.append(
            result(
                source="openalex",
                pack="research",
                source_type="research",
                query_variant=variant,
                title=work.get("title", ""),
                url=url,
                snippet=source.get("display_name", ""),
                published=f"{year}-01-01" if year else None,
                score=4.0,
                metadata={
                    "doi": work.get("doi"),
                    "citations": int(work.get("cited_by_count") or 0),
                    "venue": source.get("display_name"),
                    "open_access": bool(open_access.get("is_oa")),
                    "openalex_id": work.get("id"),
                    "year": year,
                },
            )
        )
    return items


def semantic_scholar_headers() -> dict[str, str]:
    headers = {"Accept": "application/json"}
    token = os.getenv("SEMANTIC_SCHOLAR_API_KEY")
    if token:
        headers["x-api-key"] = token
    return headers


def semantic_scholar_search(variant: str, context: SearchContext) -> list[SearchResult]:
    definition = source_definition("semantic_scholar")
    data = read_json(
        build_url(
            endpoint_for("semantic_scholar"),
            {
                "query": variant,
                "limit": context.limit,
                "fields": "title,url,abstract,year,publicationDate,citationCount,externalIds,venue,isOpenAccess,authors",
            },
        ),
        context.timeout,
        semantic_scholar_headers(),
    )
    items = []
    for paper in data.get("data", []) if isinstance(data, dict) else []:
        external = paper.get("externalIds") or {}
        paper_id = paper.get("paperId", "")
        authors = paper.get("authors") or []
        items.append(
            result(
                source="semantic_scholar",
                pack="research",
                source_type="research",
                query_variant=variant,
                title=paper.get("title", ""),
                url=paper.get("url") or f"{definition.base_url}/{paper_id}",
                snippet=paper.get("abstract", "") or paper.get("venue", ""),
                published=paper.get("publicationDate") or (f"{paper.get('year')}-01-01" if paper.get("year") else None),
                score=4.0,
                metadata={
                    "paper_id": paper_id,
                    "doi": external.get("DOI"),
                    "arxiv_id": external.get("ArXiv"),
                    "citations": int(paper.get("citationCount") or 0),
                    "venue": paper.get("venue"),
                    "open_access": bool(paper.get("isOpenAccess")),
                    "year": paper.get("year"),
                    "authors": [author.get("name") for author in authors[:5] if isinstance(author, dict) and author.get("name")],
                },
            )
        )
    return items


def openlibrary_search(variant: str, context: SearchContext) -> list[SearchResult]:
    definition = source_definition("openlibrary")
    data = read_json(build_url(endpoint_for("openlibrary"), {"q": variant, "limit": context.limit}), context.timeout)
    items = []
    for doc in data.get("docs", []):
        key = doc.get("key", "")
        year = doc.get("first_publish_year")
        published = f"{year}-01-01" if year else None
        items.append(
            result(
                source="openlibrary",
                pack="research",
                source_type="research",
                query_variant=variant,
                title=doc.get("title", ""),
                url=f"{definition.base_url}{key}",
                snippet=", ".join(doc.get("author_name", [])[:4]) if isinstance(doc.get("author_name"), list) else "",
                published=published,
                score=2.5,
                metadata={"edition_count": doc.get("edition_count")},
            )
        )
    return items


def wikipedia_search(variant: str, context: SearchContext) -> list[SearchResult]:
    lang = "ko" if context.locale.lower().startswith("ko") else "en"
    data = read_json(
        build_url(
            endpoint_for("wikipedia").format(lang=lang),
            {"action": "opensearch", "search": variant, "limit": context.limit, "namespace": 0, "format": "json"},
        ),
        context.timeout,
    )
    titles = data[1] if len(data) > 1 else []
    descriptions = data[2] if len(data) > 2 else []
    urls = data[3] if len(data) > 3 else []
    items = []
    for title, description, url in zip(titles, descriptions, urls):
        items.append(
            result(
                source="wikipedia",
                pack="research",
                source_type="research",
                query_variant=variant,
                title=title,
                url=url,
                snippet=description,
                score=2.5,
                metadata={"language": lang},
            )
        )
    return items
