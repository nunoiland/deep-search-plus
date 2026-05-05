#!/usr/bin/env python3
"""Unit tests for Insane Deep Search."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import deep_search  # noqa: E402


class DeepSearchTests(unittest.TestCase):
    def test_query_variants_keep_original_and_split_mixed_query(self) -> None:
        variants = deep_search.generate_query_variants("현대차 tariffs hybrid")
        self.assertEqual(variants[0], "현대차 tariffs hybrid")
        self.assertIn('"현대차 tariffs hybrid"', variants)
        self.assertIn("tariffs hybrid", variants)
        self.assertIn("현대차", variants)

    def test_canonicalize_url_removes_tracking_and_normalizes_host(self) -> None:
        url = "https://Example.com:443/path/?utm_source=x&b=2&a=1#section"
        self.assertEqual(deep_search.canonicalize_url(url), "https://example.com/path?a=1&b=2")

    def test_dedupe_keeps_highest_ranked_result(self) -> None:
        first = deep_search.result(
            source="one",
            pack="news",
            source_type="news",
            query_variant="openai",
            title="OpenAI old",
            url="https://example.com/a?utm_source=x",
            score=1,
            metadata={"trust_weight": 1},
        )
        second = deep_search.result(
            source="two",
            pack="news",
            source_type="news",
            query_variant="openai",
            title="OpenAI important update",
            url="https://example.com/a",
            score=10,
            metadata={"trust_weight": 5},
        )
        results = deep_search.dedupe_and_rank([first, second], "openai update")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].source, "two")

    def test_report_contains_expected_sections(self) -> None:
        item = deep_search.result(
            source="github_repositories",
            pack="tech",
            source_type="developer",
            query_variant="agents sdk",
            title="agents sdk",
            url="https://example.com/repo",
            snippet="developer evidence",
            score=5,
        )
        run = deep_search.SearchRun(
            query="agents sdk",
            depth="quick",
            packs=["tech"],
            locale="ko-KR",
            query_variants=["agents sdk"],
            results=[item],
        )
        report = deep_search.format_report(run)
        self.assertIn("## 핵심 요약", report)
        self.assertIn("## 원문 확인 결과", report)
        self.assertIn("github_repositories", report)

    def test_source_failure_keeps_partial_success(self) -> None:
        original_sources = deep_search.SOURCES

        def ok_adapter(variant: str, context: deep_search.SearchContext) -> list[deep_search.SearchResult]:
            return [
                deep_search.result(
                    source="ok",
                    pack="news",
                    source_type="news",
                    query_variant=variant,
                    title="OpenAI result",
                    url="https://example.com/openai",
                    score=3,
                )
            ]

        def bad_adapter(variant: str, context: deep_search.SearchContext) -> list[deep_search.SearchResult]:
            raise RuntimeError("source unavailable")

        try:
            deep_search.SOURCES = [
                deep_search.SourceSpec("ok", "news", "news", 4, ok_adapter),
                deep_search.SourceSpec("bad", "news", "news", 4, bad_adapter),
            ]
            run = deep_search.run_search("openai", packs=["news"], limit=2, fetch_top=0)
            self.assertEqual(len(run.results), 1)
            self.assertEqual(len(run.errors), 1)
            self.assertEqual(run.errors[0].source, "bad")
        finally:
            deep_search.SOURCES = original_sources

    def test_fetch_verdict_strong_ok(self) -> None:
        original_fetch = deep_search.fetch_bytes

        def fake_fetch(url: str, timeout: float = 12.0):
            body = b"<html><head><title>Example</title><meta name='description' content='Desc'></head><body>" + b"x" * 2000 + b"</body></html>"
            return body, 200, "text/html", url, 15, ""

        try:
            deep_search.fetch_bytes = fake_fetch  # type: ignore[assignment]
            check = deep_search.verify_url("https://example.com")
            self.assertEqual(check.verdict, "strong_ok")
            self.assertEqual(check.title, "Example")
            self.assertEqual(check.description, "Desc")
        finally:
            deep_search.fetch_bytes = original_fetch  # type: ignore[assignment]

    def test_google_news_rss_parsing(self) -> None:
        rss = """<?xml version="1.0" encoding="UTF-8" ?>
        <rss><channel><item>
          <title>Market update</title>
          <link>https://example.com/news?utm_source=x</link>
          <description><![CDATA[<p>Short text</p>]]></description>
          <pubDate>Tue, 05 May 2026 00:00:00 GMT</pubDate>
        </item></channel></rss>"""
        items = deep_search.parse_rss(rss, "google_news_ko", "market", 2)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "Market update")
        self.assertEqual(items[0].canonical_url, "https://example.com/news")

    def test_extract_links_normalizes_and_filters_public_links(self) -> None:
        html = b"""
        <html><body>
          <a href="/news/openai-update?utm_source=x">OpenAI update</a>
          <a href="mailto:test@example.com">mail</a>
          <a href="/image.png">image</a>
          <a href="/login">login</a>
        </body></html>
        """
        links = deep_search.extract_links(html, "text/html", "https://example.com/root", limit=5)
        self.assertEqual(links, [{"url": "https://example.com/news/openai-update", "text": "OpenAI update"}])

    def test_detective_mode_follows_relevant_public_links(self) -> None:
        original_sources = deep_search.SOURCES
        original_fetch = deep_search.fetch_bytes

        def ok_adapter(variant: str, context: deep_search.SearchContext) -> list[deep_search.SearchResult]:
            return [
                deep_search.result(
                    source="ok",
                    pack="news",
                    source_type="news",
                    query_variant=variant,
                    title="OpenAI article",
                    url="https://example.com/news/openai",
                    score=6,
                )
            ]

        def fake_fetch(url: str, timeout: float = 12.0):
            if url.endswith("/news/openai"):
                body = b"""
                <html><head><title>OpenAI article</title></head><body>
                  <a href="/research/openai-codex-evidence">OpenAI Codex evidence</a>
                  <a href="/privacy">Privacy</a>
                </body></html>
                """
                return body, 200, "text/html", url, 10, ""
            body = b"<html><head><title>Deep Evidence</title><meta name='description' content='OpenAI Codex evidence page'></head><body>ok</body></html>"
            return body, 200, "text/html", url, 12, ""

        try:
            deep_search.SOURCES = [deep_search.SourceSpec("ok", "news", "news", 4, ok_adapter)]
            deep_search.fetch_bytes = fake_fetch  # type: ignore[assignment]
            run = deep_search.run_search(
                "OpenAI Codex",
                packs=["news"],
                limit=1,
                fetch_top=1,
                detective=True,
                dig_pages=1,
                max_page_links=5,
            )
            self.assertIn("https://example.com/research/openai-codex-evidence", run.discovered_urls)
            discovery = [item for item in run.results if item.source == "page_discovery"]
            self.assertEqual(len(discovery), 1)
            self.assertEqual(discovery[0].title, "Deep Evidence")
            self.assertEqual(discovery[0].metadata["parent_url"], "https://example.com/news/openai")
        finally:
            deep_search.SOURCES = original_sources
            deep_search.fetch_bytes = original_fetch  # type: ignore[assignment]


if __name__ == "__main__":
    unittest.main()
