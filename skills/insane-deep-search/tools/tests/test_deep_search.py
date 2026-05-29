#!/usr/bin/env python3
"""Unit tests for Insane Deep Search."""

from __future__ import annotations

import sys
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path


TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import deep_search  # noqa: E402
from insane_deep_search import cli as cli_module  # noqa: E402
from insane_deep_search import http as http_module  # noqa: E402
from insane_deep_search import research as research_module  # noqa: E402
from insane_deep_search import runner as runner_module  # noqa: E402
from insane_deep_search.source_catalog import validate_source_definitions  # noqa: E402


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

    def test_reexported_compatibility_entrypoint(self) -> None:
        self.assertTrue(callable(deep_search.run_search))
        self.assertTrue(callable(deep_search.main))
        self.assertEqual(deep_search.SourceSpec.__name__, "SourceSpec")

    def test_source_catalog_validates_cleanly(self) -> None:
        self.assertEqual(validate_source_definitions(), [])
        names = [source.name for source in deep_search.SOURCES]
        self.assertEqual(len(names), len(set(names)))

    def test_source_urls_and_trust_weights_live_outside_adapters(self) -> None:
        adapters = TOOLS / "insane_deep_search" / "sources" / "adapters.py"
        text = adapters.read_text()
        self.assertNotIn("https://", text)
        self.assertNotIn("trust_weight", text)

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
        self.assertEqual(results[0].metadata["duplicate_count"], 2)
        self.assertIn("one", results[0].metadata["supporting_sources"])

    def test_identity_dedupe_uses_doi_arxiv_github_and_title_domain(self) -> None:
        doi = deep_search.result(
            source="crossref",
            pack="research",
            source_type="research",
            query_variant="x",
            title="Paper",
            url="https://publisher.example/paper",
            metadata={"doi": "https://doi.org/10.123/ABC"},
        )
        self.assertEqual(deep_search.identity_key(doi), "doi:10.123/abc")

        arxiv = deep_search.result(
            source="arxiv",
            pack="research",
            source_type="research",
            query_variant="x",
            title="Paper",
            url="https://arxiv.org/abs/2401.12345v2",
        )
        self.assertEqual(deep_search.identity_key(arxiv), "arxiv:2401.12345")

        github = deep_search.result(
            source="github_issues",
            pack="tech",
            source_type="developer",
            query_variant="x",
            title="Issue",
            url="https://github.com/OpenAI/codex/issues/1",
        )
        self.assertEqual(deep_search.identity_key(github), "github:openai/codex")

    def test_quality_score_flags_source_specific_risk(self) -> None:
        community = deep_search.result(
            source="reddit",
            pack="community",
            source_type="community",
            query_variant="x",
            title="Rumor",
            url="https://reddit.com/r/test/comments/1",
            metadata={"comments": 10, "points": 5},
        )
        deep_search.apply_quality_score(community)
        self.assertGreater(community.metadata["quality_score"], 0)
        self.assertIn("community_opinion_not_confirmed_fact", community.metadata["risk_flags"])

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

        sources = [
            deep_search.SourceSpec("ok", "news", "news", 4, ("https://example.com/ok",), ok_adapter),
            deep_search.SourceSpec("bad", "news", "news", 4, ("https://example.com/bad",), bad_adapter),
        ]
        run = deep_search.run_search("openai", packs=["news"], limit=2, fetch_top=0, sources=sources)
        self.assertEqual(len(run.results), 1)
        self.assertEqual(len(run.errors), 1)
        self.assertEqual(run.errors[0].source, "bad")

    def test_research_mode_generates_bounded_novel_followups(self) -> None:
        calls = []

        def ok_adapter(variant: str, context: deep_search.SearchContext) -> list[deep_search.SearchResult]:
            calls.append(variant)
            return [
                deep_search.result(
                    source="ok",
                    pack="news",
                    source_type="news",
                    query_variant=variant,
                    title=f"OpenAI Codex evidence {variant}",
                    url=f"https://example.com/{len(calls)}",
                    score=3,
                )
            ]

        sources = [deep_search.SourceSpec("ok", "news", "news", 4, ("https://example.com/ok",), ok_adapter)]
        run = deep_search.run_search(
            "OpenAI Codex",
            packs=["news"],
            depth="quick",
            limit=1,
            fetch_top=0,
            research=True,
            research_depth=2,
            research_breadth=2,
            sources=sources,
        )
        self.assertEqual(len(run.research_rounds), 2)
        self.assertLessEqual(len(run.research_rounds[1]["queries"]), 2)
        self.assertEqual(len(calls), len(set(calls)))

    def test_fetch_verdict_strong_ok(self) -> None:
        original_fetch = http_module.fetch_bytes

        def fake_fetch(url: str, timeout: float = 12.0):
            body = b"<html><head><title>Example</title><meta name='description' content='Desc'></head><body>" + b"x" * 2000 + b"</body></html>"
            return body, 200, "text/html", url, 15, ""

        try:
            http_module.fetch_bytes = fake_fetch  # type: ignore[assignment]
            check = deep_search.verify_url("https://example.com")
            self.assertEqual(check.verdict, "strong_ok")
            self.assertEqual(check.title, "Example")
            self.assertEqual(check.description, "Desc")
        finally:
            http_module.fetch_bytes = original_fetch  # type: ignore[assignment]

    def test_verify_mode_auto_uses_render_fallback_for_weak_basic_result(self) -> None:
        original_verify = runner_module.verify_url
        original_render = runner_module.verify_rendered_url

        def fake_verify(url: str, timeout: float = 12.0, link_limit: int = 0):
            return deep_search.FetchCheck(url=url, final_url=url, status=200, body_size=20, verdict="weak_ok")

        def fake_render(url: str, timeout: float = 12.0, link_limit: int = 0):
            return deep_search.FetchCheck(url=url, final_url=url, status=200, body_size=2000, verdict="strong_ok")

        try:
            runner_module.verify_url = fake_verify  # type: ignore[assignment]
            runner_module.verify_rendered_url = fake_render  # type: ignore[assignment]
            check = deep_search.verify_for_mode("https://example.com", timeout=12, link_limit=0, verify_mode="auto")
            self.assertEqual(check.verdict, "strong_ok")
            self.assertEqual(check.metadata["basic_verdict"], "weak_ok")
        finally:
            runner_module.verify_url = original_verify  # type: ignore[assignment]
            runner_module.verify_rendered_url = original_render  # type: ignore[assignment]

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
          <a href="/readme?activeTab=code">tab</a>
        </body></html>
        """
        links = deep_search.extract_links(html, "text/html", "https://example.com/root", limit=5)
        self.assertEqual(links, [{"url": "https://example.com/news/openai-update", "text": "OpenAI update"}])

    def test_detective_mode_follows_relevant_public_offsite_links_by_default(self) -> None:
        original_fetch = http_module.fetch_bytes

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
                  <a href="https://evidence.example.org/research/openai-codex-evidence">OpenAI Codex evidence</a>
                  <a href="/privacy">Privacy</a>
                </body></html>
                """
                return body, 200, "text/html", url, 10, ""
            body = b"<html><head><title>Deep Evidence</title><meta name='description' content='OpenAI Codex evidence page'></head><body>ok</body></html>"
            return body, 200, "text/html", url, 12, ""

        try:
            http_module.fetch_bytes = fake_fetch  # type: ignore[assignment]
            sources = [deep_search.SourceSpec("ok", "news", "news", 4, ("https://example.com/search",), ok_adapter)]
            run = deep_search.run_search(
                "OpenAI Codex",
                packs=["news"],
                limit=1,
                fetch_top=1,
                detective=True,
                dig_pages=1,
                max_page_links=5,
                sources=sources,
            )
            self.assertIn("https://evidence.example.org/research/openai-codex-evidence", run.discovered_urls)
            discovery = [item for item in run.results if item.source == "page_discovery"]
            self.assertEqual(len(discovery), 1)
            self.assertEqual(discovery[0].metadata["parent_url"], "https://example.com/news/openai")
            self.assertEqual(discovery[0].metadata["discovery_depth"], 1)
            self.assertIn("url:openai", discovery[0].metadata["discovery_reason"])
        finally:
            http_module.fetch_bytes = original_fetch  # type: ignore[assignment]

    def test_same_site_only_blocks_offsite_discovery(self) -> None:
        original_verify = runner_module.verify_url

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

        def fake_verify(url: str, timeout: float = 12.0, link_limit: int = 0):
            return deep_search.FetchCheck(
                url=url,
                final_url=url,
                status=200,
                content_type="text/html",
                body_size=2000,
                verdict="strong_ok",
                links=[{"url": "https://offsite.example.org/research/openai-codex", "text": "OpenAI Codex research"}],
            )

        try:
            runner_module.verify_url = fake_verify  # type: ignore[assignment]
            sources = [deep_search.SourceSpec("ok", "news", "news", 4, ("https://example.com/search",), ok_adapter)]
            run = deep_search.run_search(
                "OpenAI Codex",
                packs=["news"],
                limit=1,
                fetch_top=1,
                detective=True,
                dig_pages=1,
                include_offsite=False,
                sources=sources,
            )
            self.assertEqual(run.discovered_urls, [])
        finally:
            runner_module.verify_url = original_verify  # type: ignore[assignment]

    def test_cli_defaults_use_heavy_deep_profile(self) -> None:
        parser = deep_search.build_parser()
        args = parser.parse_args(["OpenAI Codex"])
        self.assertTrue(args.research)
        self.assertEqual(args.research_depth, 4)
        self.assertEqual(args.research_breadth, 8)
        self.assertEqual(args.verify_mode, "auto")
        self.assertEqual(args.fetch_top, 10)
        self.assertEqual(args.dig_pages, 16)
        self.assertEqual(args.crawl_depth, 3)
        self.assertEqual(args.max_total_fetches, 60)
        self.assertEqual(args.local_llm, "auto")
        self.assertEqual(args.local_llm_model, "gemma4:latest")

    def test_quick_profile_lowers_runtime_work(self) -> None:
        original_run_search = cli_module.run_search
        captured = {}

        def fake_run_search(query: str, **kwargs):
            captured.update(kwargs)
            return deep_search.SearchRun(query=query, depth=kwargs["depth"], packs=kwargs["packs"], locale="ko-KR", query_variants=[query])

        try:
            cli_module.run_search = fake_run_search  # type: ignore[assignment]
            with redirect_stdout(StringIO()):
                self.assertEqual(cli_module.main(["OpenAI Codex", "--quick", "--json"]), 0)
        finally:
            cli_module.run_search = original_run_search  # type: ignore[assignment]

        self.assertEqual(captured["depth"], "quick")
        self.assertFalse(captured["research"])
        self.assertEqual(captured["fetch_top"], 0)
        self.assertEqual(captured["dig_pages"], 0)
        self.assertEqual(captured["verify_mode"], "basic")
        self.assertEqual(captured["local_llm_mode"], "off")

    def test_local_llm_unavailable_falls_back_to_heuristic_planner(self) -> None:
        original_generate_json = research_module.generate_json

        def fake_generate_json(prompt: str, *, mode: str = "auto", model: str | None = None, timeout: float = 45.0):
            return None, {"mode": mode, "requested_model": model, "available": False, "fallback": True, "error": "offline"}

        def ok_adapter(variant: str, context: deep_search.SearchContext) -> list[deep_search.SearchResult]:
            return [
                deep_search.result(
                    source="ok",
                    pack="community",
                    source_type="community",
                    query_variant=variant,
                    title="OpenAI Codex community issue",
                    url=f"https://example.com/{variant.replace(' ', '-')}",
                    score=3,
                )
            ]

        try:
            research_module.generate_json = fake_generate_json  # type: ignore[assignment]
            run = deep_search.run_search(
                "OpenAI Codex",
                packs=["community"],
                limit=1,
                fetch_top=0,
                research=True,
                research_depth=2,
                research_breadth=3,
                local_llm_mode="auto",
                sources=[deep_search.SourceSpec("ok", "community", "community", 1, ("https://example.com",), ok_adapter)],
            )
        finally:
            research_module.generate_json = original_generate_json  # type: ignore[assignment]

        self.assertEqual(len(run.research_rounds), 2)
        self.assertEqual(run.planner_steps[0]["planner"], "heuristic")
        self.assertTrue(run.local_llm["fallback"])

    def test_local_llm_required_failure_raises_clear_error(self) -> None:
        original_generate_json = research_module.generate_json

        def fake_generate_json(prompt: str, *, mode: str = "auto", model: str | None = None, timeout: float = 45.0):
            return None, {"mode": mode, "requested_model": model, "available": False, "fallback": True, "error": "offline"}

        def ok_adapter(variant: str, context: deep_search.SearchContext) -> list[deep_search.SearchResult]:
            return [
                deep_search.result(source="ok", pack="news", source_type="news", query_variant=variant, title="OpenAI", url="https://example.com/openai", score=3)
            ]

        try:
            research_module.generate_json = fake_generate_json  # type: ignore[assignment]
            with self.assertRaisesRegex(RuntimeError, "local LLM required"):
                deep_search.run_search(
                    "OpenAI Codex",
                    packs=["news"],
                    limit=1,
                    fetch_top=0,
                    research=True,
                    research_depth=2,
                    local_llm_mode="required",
                    sources=[deep_search.SourceSpec("ok", "news", "news", 1, ("https://example.com",), ok_adapter)],
                )
        finally:
            research_module.generate_json = original_generate_json  # type: ignore[assignment]

    def test_planner_prioritizes_source_and_contradiction_gaps(self) -> None:
        item = deep_search.result(
            source="reddit",
            pack="community",
            source_type="community",
            query_variant="x",
            title="OpenAI Codex issue",
            url="https://example.com/community",
            snippet="community discussion",
        )
        deep_search.apply_quality_score(item)
        plan = deep_search.heuristic_follow_up_queries("OpenAI Codex", [item], 8)
        queries = " ".join(entry["query"] for entry in plan)
        self.assertIn("paper citations DOI", queries)
        self.assertIn("criticism", queries)

    def test_recursive_crawler_respects_depth_and_fetch_budget(self) -> None:
        original_fetch = http_module.fetch_bytes

        def ok_adapter(variant: str, context: deep_search.SearchContext) -> list[deep_search.SearchResult]:
            return [
                deep_search.result(source="ok", pack="news", source_type="news", query_variant=variant, title="OpenAI root", url="https://example.com/root", score=5)
            ]

        def fake_fetch(url: str, timeout: float = 12.0):
            if url.endswith("/root"):
                body = b"<html><body><a href='https://example.com/research/openai-b'>OpenAI research b</a></body></html>"
            elif url.endswith("/openai-b"):
                body = b"<html><body><a href='https://example.com/research/openai-c'>OpenAI research c</a></body></html>"
            else:
                body = b"<html><body>final</body></html>"
            return body, 200, "text/html", url, 10, ""

        try:
            http_module.fetch_bytes = fake_fetch  # type: ignore[assignment]
            run = deep_search.run_search(
                "OpenAI research",
                packs=["news"],
                limit=1,
                fetch_top=1,
                detective=True,
                dig_pages=2,
                crawl_depth=2,
                max_total_fetches=3,
                max_page_links=4,
                sources=[deep_search.SourceSpec("ok", "news", "news", 4, ("https://example.com",), ok_adapter)],
            )
        finally:
            http_module.fetch_bytes = original_fetch  # type: ignore[assignment]

        self.assertEqual(len(run.discovered_urls), 2)
        self.assertEqual([trace["depth"] for trace in run.crawl_traces], [1, 2])
        self.assertEqual(len(run.fetched_urls), 3)

    def test_claim_ledger_separates_supported_and_community_only_claims(self) -> None:
        news = deep_search.result(source="news", pack="news", source_type="news", query_variant="x", title="OpenAI Codex launches research mode", url="https://example.com/news")
        paper = deep_search.result(source="paper", pack="research", source_type="research", query_variant="x", title="OpenAI Codex launches research mode", url="https://example.com/paper", metadata={"doi": "10.1/test"})
        community = deep_search.result(source="reddit", pack="community", source_type="community", query_variant="x", title="OpenAI Codex rumor", url="https://example.com/reddit")
        for item in [news, paper, community]:
            item.evidence_level = "strong" if item is not community else "medium"
            deep_search.apply_quality_score(item)
        ledger = deep_search.build_claim_ledger("OpenAI Codex", [news, paper, community], [])
        statuses = {item["claim"]: item["status"] for item in ledger}
        self.assertEqual(statuses["OpenAI Codex launches research mode"], "supported")
        self.assertEqual(statuses["OpenAI Codex rumor"], "community_only")

    def test_fetch_retry_stats_track_retryable_statuses(self) -> None:
        original_fetch_once = http_module.fetch_bytes_once
        calls = []

        def fake_fetch_once(url: str, timeout: float, headers: dict[str, str]):
            calls.append(url)
            if len(calls) == 1:
                return b"", 429, "text/plain", url, 1, ""
            return b"ok", 200, "text/plain", url, 2, ""

        try:
            http_module.fetch_bytes_once = fake_fetch_once  # type: ignore[assignment]
            http_module.set_transport_options(cache_enabled=False)
            http_module.reset_transport_stats()
            body, status, _content_type, _final_url, _elapsed_ms, _error = http_module.fetch_bytes("https://example.com/retry")
            _cache, retry = http_module.transport_stats()
        finally:
            http_module.fetch_bytes_once = original_fetch_once  # type: ignore[assignment]

        self.assertEqual(body, b"ok")
        self.assertEqual(status, 200)
        self.assertEqual(retry["retries"], 1)
        self.assertEqual(retry["retry_statuses"]["429"], 1)

    def test_extract_json_object_recovers_embedded_model_json(self) -> None:
        parsed = deep_search.extract_json_object('planner output {"queries": [], "claims": []} done')
        self.assertEqual(parsed["queries"], [])


if __name__ == "__main__":
    unittest.main()
