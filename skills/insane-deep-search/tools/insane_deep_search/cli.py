"""Command line interface."""

from __future__ import annotations

import argparse
import json

from .config import DISCOVERY_POLICY
from .report import format_report
from .runner import parse_packs, run_search


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be zero or greater")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Codex-native public evidence deep search.")
    parser.add_argument("query", help="Search query")
    parser.add_argument("--depth", choices=["quick", "balanced", "deep"], default="deep")
    parser.add_argument("--pack", default="news,community,tech,research", help="Comma-separated source packs")
    parser.add_argument("--limit", type=positive_int, default=8, help="Per-source result limit")
    parser.add_argument("--fetch-top", type=positive_int, default=5, help="Verify the top N result URLs")
    parser.add_argument("--detective", action="store_true", help="Extract public links from fetched pages and follow the most relevant ones")
    parser.add_argument("--dig-pages", type=positive_int, default=0, help="Fetch up to N discovered public links from top pages")
    parser.add_argument("--max-page-links", type=positive_int, default=DISCOVERY_POLICY.default_max_page_links, help="Maximum links to extract from each fetched page")
    parser.add_argument("--include-offsite", action="store_true", help="Compatibility flag; offsite discovery is on by default in detective mode")
    parser.add_argument("--same-site-only", action="store_true", help="Limit detective mode to links on the same site")
    parser.add_argument("--locale", default="ko-KR")
    parser.add_argument("--timeout", type=float, default=12.0)
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

    run = run_search(
        args.query,
        depth=args.depth,
        packs=packs,
        limit=args.limit,
        fetch_top=args.fetch_top,
        detective=args.detective or args.dig_pages > 0,
        dig_pages=args.dig_pages or (DISCOVERY_POLICY.default_dig_pages if args.detective else 0),
        max_page_links=args.max_page_links,
        include_offsite=not args.same_site_only,
        locale=args.locale,
        timeout=args.timeout,
    )

    print_report = args.report or not args.json
    if print_report:
        print(format_report(run))
    if args.json:
        print(json.dumps(run.to_dict(), ensure_ascii=False, indent=2))
    return 0
