"""Command line interface."""

from __future__ import annotations

import argparse
import json
import sys

from .config import DEFAULT_LOCAL_LLM_MODEL, DISCOVERY_POLICY
from .html_report import write_html_report
from .report import format_report
from .runner import parse_packs, run_search
from .workflow import load_checkpoint, write_checkpoint


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be zero or greater")
    return parsed


def non_negative_float(value: str) -> float:
    parsed = float(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be zero or greater")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Codex-native public evidence deep search.")
    parser.add_argument("query", help="Search query")
    parser.add_argument("--quick", action="store_true", help="Use a fast low-cost profile")
    parser.add_argument("--ultra", action="store_true", help="Use the slower maximum-depth research profile")
    parser.add_argument("--depth", choices=["quick", "balanced", "deep"], default="balanced")
    parser.add_argument("--pack", default="news,community,tech,research", help="Comma-separated source packs")
    parser.add_argument("--limit", type=positive_int, default=8, help="Per-source result limit")
    parser.add_argument("--fetch-top", type=positive_int, default=3, help="Verify the top N result URLs")
    parser.add_argument("--detective", action="store_true", help="Extract public links from fetched pages and follow the most relevant ones")
    parser.add_argument("--dig-pages", type=positive_int, default=4, help="Fetch up to N discovered public links from top pages")
    parser.add_argument("--max-page-links", type=positive_int, default=DISCOVERY_POLICY.default_max_page_links, help="Maximum links to extract from each fetched page")
    parser.add_argument("--crawl-depth", type=positive_int, default=1, help="Recursive public link discovery depth")
    parser.add_argument("--max-total-fetches", type=positive_int, default=12, help="Maximum URL fetches per run")
    parser.add_argument("--include-offsite", action="store_true", help="Compatibility flag; offsite discovery is on by default in detective mode")
    parser.add_argument("--same-site-only", action="store_true", help="Limit detective mode to links on the same site")
    parser.add_argument("--locale", default="ko-KR")
    parser.add_argument("--timeout", type=float, default=6.0)
    parser.add_argument("--research", dest="research", action="store_true", default=True, help="Run iterative follow-up searches and evidence grouping")
    parser.add_argument("--no-research", dest="research", action="store_false", help="Disable iterative follow-up searches")
    parser.add_argument("--research-depth", type=positive_int, default=2, help="Total research rounds including the initial round")
    parser.add_argument("--research-breadth", type=positive_int, default=4, help="Follow-up queries per research round")
    parser.add_argument("--verify-mode", choices=["basic", "auto", "rendered"], default="basic", help="URL verification backend")
    parser.add_argument("--local-llm", choices=["auto", "off", "required"], default="auto", help="Local Ollama planner mode")
    parser.add_argument("--local-llm-model", default=DEFAULT_LOCAL_LLM_MODEL, help="Local Ollama model name")
    parser.add_argument("--local-llm-timeout", type=non_negative_float, default=5.0, help="Local Ollama planner timeout per model")
    parser.add_argument("--max-workers", type=positive_int, default=8, help="Parallel source calls")
    parser.add_argument("--time-budget", type=non_negative_float, default=60.0, help="Overall runtime budget in seconds")
    parser.add_argument("--quiet", action="store_true", help="Disable progress logs on stderr")
    parser.add_argument("--cache", choices=["on", "off"], default="on", help="Use local HTTP response cache")
    parser.add_argument("--research-contract", choices=["basic", "strict", "off"], default="basic", help="Research contract mode")
    parser.add_argument("--goal", default=None, help="Decision goal for this research run")
    parser.add_argument("--scope", default=None, help="In/out scope for this research run")
    parser.add_argument("--done-evidence", default=None, help="Evidence needed before the run is considered done")
    parser.add_argument("--checkpoint", default=None, help="Write resumable handoff checkpoint JSON to this path")
    parser.add_argument("--resume", default=None, help="Resume from a prior checkpoint JSON and skip duplicate queries/URLs")
    parser.add_argument("--html-report", default=None, help="Write a self-contained HTML evidence board to this path")
    parser.add_argument("--evidence-gate", choices=["strict", "balanced", "loose"], default="balanced", help="Evidence gate policy for core summary strength")
    parser.add_argument("--json", action="store_true", help="Print JSON output")
    parser.add_argument("--report", action="store_true", help="Print Markdown report")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        packs = parse_packs(args.pack)
    except ValueError as exc:
        parser.error(str(exc))

    if args.ultra:
        args.depth = "deep"
        args.fetch_top = 10
        args.dig_pages = DISCOVERY_POLICY.default_dig_pages
        args.crawl_depth = DISCOVERY_POLICY.max_depth
        args.max_total_fetches = DISCOVERY_POLICY.max_total_fetches
        args.research = True
        args.research_depth = 4
        args.research_breadth = 8
        args.verify_mode = "auto"
        args.local_llm = "auto"
        args.local_llm_timeout = 20.0
        args.time_budget = 0.0

    if args.quick:
        args.depth = "quick"
        args.limit = min(args.limit, 4)
        args.fetch_top = 0
        args.dig_pages = 0
        args.crawl_depth = 1
        args.max_total_fetches = 0
        args.research = False
        args.research_depth = 1
        args.research_breadth = 0
        args.verify_mode = "basic"
        args.local_llm = "off"
        args.local_llm_timeout = 0.0

    progress = None if args.quiet else (lambda message: print(message, file=sys.stderr, flush=True))
    resume_state = load_checkpoint(args.resume) if args.resume else None

    run = run_search(
        args.query,
        depth=args.depth,
        packs=packs,
        limit=args.limit,
        fetch_top=args.fetch_top,
        detective=args.detective or args.dig_pages > 0,
        dig_pages=args.dig_pages,
        max_page_links=args.max_page_links,
        crawl_depth=args.crawl_depth,
        max_total_fetches=args.max_total_fetches,
        include_offsite=not args.same_site_only,
        locale=args.locale,
        timeout=args.timeout,
        research=args.research,
        research_depth=args.research_depth,
        research_breadth=args.research_breadth,
        verify_mode=args.verify_mode,
        local_llm_mode=args.local_llm,
        local_llm_model=args.local_llm_model,
        local_llm_timeout=args.local_llm_timeout,
        local_llm_fallback=args.ultra,
        cache=args.cache,
        max_workers=args.max_workers,
        time_budget=args.time_budget,
        progress=progress,
        research_contract=args.research_contract,
        goal=args.goal,
        scope=args.scope,
        done_evidence=args.done_evidence,
        evidence_gate=args.evidence_gate,
        resume_state=resume_state,
    )

    if args.html_report:
        path = write_html_report(args.html_report, run)
        run.html_report = {"path": path, "format": "self-contained-html", "saved": True}

    if args.checkpoint:
        run.run_checkpoint = dict(run.run_checkpoint)
        run.run_checkpoint["saved"] = True
        path = write_checkpoint(args.checkpoint, run.run_checkpoint)
        run.run_checkpoint["path"] = path

    print_report = args.report or not args.json
    if print_report:
        print(format_report(run))
    if args.json:
        print(json.dumps(run.to_dict(), ensure_ascii=False, indent=2))
    return 0
