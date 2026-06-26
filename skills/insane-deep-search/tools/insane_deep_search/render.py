"""Optional rendered-page verification using crawl4ai when installed.

This is a public-page fallback for weak, blocked, or empty basic fetches. It is
not an access-control bypass and must not attempt login, paywall, captcha, or
private-content workarounds.
"""

from __future__ import annotations

import asyncio

from .config import FETCH_POLICY
from .html_tools import extract_links, extract_metadata
from .http import detect_blocked_signals, fetch_verdict
from .models import FetchCheck


def should_render_fallback(check: FetchCheck) -> bool:
    return check.verdict in {"blocked", "fail", "weak_fail", "weak_ok"} or check.body_size < FETCH_POLICY.strong_min_bytes


async def _verify_rendered_async(url: str, timeout: float, link_limit: int) -> FetchCheck:
    try:
        from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig  # type: ignore
    except Exception as exc:
        return FetchCheck(url=url, final_url=url, verdict="fail", error=f"crawl4ai unavailable: {exc}")

    try:
        browser_config = BrowserConfig(headless=True, verbose=False)
        run_config = CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS,
            page_timeout=max(1000, int(timeout * 1000)),
            wait_until="domcontentloaded",
            remove_overlay_elements=True,
            verbose=False,
        )
        start = asyncio.get_running_loop().time()
        async with AsyncWebCrawler(config=browser_config) as crawler:
            result = await crawler.arun(url=url, config=run_config)
        elapsed_ms = int((asyncio.get_running_loop().time() - start) * 1000)
        html = (getattr(result, "html", "") or "").encode("utf-8", errors="replace")
        status = getattr(result, "status_code", None)
        final_url = getattr(result, "redirected_url", None) or url
        text = html[:100_000].decode("utf-8", errors="replace")
        signals = detect_blocked_signals(text, status)
        if not getattr(result, "success", False) and not signals:
            signals.append("render failed")
        metadata = extract_metadata(html, "text/html") if html else {}
        markdown = getattr(result, "markdown", None)
        if markdown:
            raw_markdown = getattr(markdown, "raw_markdown", str(markdown))
            if raw_markdown:
                metadata["rendered_markdown"] = raw_markdown[:4000]
        links = extract_links(html, "text/html", final_url, link_limit) if html else []
        verdict = fetch_verdict(status, len(html), "", signals)
        return FetchCheck(
            url=url,
            final_url=final_url,
            status=status,
            content_type="text/html",
            body_size=len(html),
            verdict=verdict,
            title=str(metadata.get("title", "")),
            description=str(metadata.get("description", "")),
            metadata=metadata,
            links=links,
            blocked_signals=signals,
            elapsed_ms=elapsed_ms,
        )
    except Exception as exc:
        return FetchCheck(url=url, final_url=url, verdict="fail", error=f"render failed: {exc}")


def verify_rendered_url(url: str, timeout: float = 12.0, link_limit: int = 0) -> FetchCheck:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_verify_rendered_async(url, timeout, link_limit))
    return FetchCheck(url=url, final_url=url, verdict="fail", error="rendered verification cannot run inside an active event loop")
