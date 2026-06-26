"""Self-contained HTML evidence board output."""

from __future__ import annotations

import html
from pathlib import Path

from .models import SearchRun
from .text import compact_url


def esc(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def badge(label: object) -> str:
    value = esc(label)
    css = value.replace("_", "-")
    return f'<span class="badge {css}">{value}</span>'


def source_link(url: str) -> str:
    label = esc(compact_url(url))
    href = esc(url)
    return f'<a href="{href}" rel="noreferrer" target="_blank">{label}</a>'


def build_html_report(run: SearchRun) -> str:
    contract = run.research_contract or {}
    cards: list[str] = []
    for claim in run.claims[:24]:
        sources = ", ".join(str(item) for item in claim.get("supporting_sources", []))
        cards.append(
            "<article class='card claim'>"
            f"<div>{badge(claim.get('status'))}<strong>{esc(claim.get('claim'))}</strong></div>"
            f"<p>confidence {esc(claim.get('confidence'))} · sources {esc(sources or 'none')}</p>"
            "<div class='actions'>더 검색 · 제외 · 약한 근거로 표시 · 요약에 반영</div>"
            "</article>"
        )

    sources: list[str] = []
    for item in run.results[:40]:
        sources.append(
            "<article class='card source'>"
            f"<div>{badge(item.pack)} {badge(item.source_type)} <strong>{esc(item.title or '(untitled)')}</strong></div>"
            f"<p>{source_link(item.url)}</p>"
            f"<p>{esc((item.snippet or '')[:260])}</p>"
            f"<p>rank {item.rank_score:.1f} · evidence {esc(item.evidence_level)} · quality {esc(item.metadata.get('quality_score', 'n/a'))}</p>"
            "</article>"
        )

    groups: list[str] = []
    for group in run.result_groups[:20]:
        groups.append(
            "<article class='card group'>"
            f"<strong>{esc(group.get('representative_title') or '(untitled)')}</strong>"
            f"<p>duplicates {esc(group.get('duplicate_count'))} · sources {esc(', '.join(group.get('supporting_sources', [])))}</p>"
            f"<p>{source_link(str(group.get('representative_url') or ''))}</p>"
            "</article>"
        )

    followups: list[str] = []
    for round_info in run.research_rounds:
        queries = round_info.get("queries", [])
        if not isinstance(queries, list):
            continue
        for query in queries:
            if isinstance(query, dict):
                followups.append(
                    "<li>"
                    f"<code>{esc(query.get('query'))}</code> "
                    f"<span>{esc(query.get('reason'))}</span>"
                    "</li>"
                )
            else:
                followups.append(f"<li><code>{esc(query)}</code></li>")

    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Deep Search Evidence Board</title>
<style>
:root {{ color-scheme: light; --ink:#172026; --muted:#5f6b72; --line:#dde3e7; --bg:#f7f9fa; --card:#ffffff; --accent:#0f766e; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; color:var(--ink); background:var(--bg); }}
header {{ padding:28px 32px 20px; border-bottom:1px solid var(--line); background:#fff; }}
main {{ padding:24px 32px 40px; max-width:1180px; margin:0 auto; }}
h1 {{ margin:0 0 8px; font-size:24px; }}
h2 {{ margin:28px 0 12px; font-size:18px; }}
.meta {{ color:var(--muted); display:grid; gap:4px; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:12px; }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:8px; padding:14px; min-width:0; }}
.card p {{ margin:8px 0 0; color:var(--muted); overflow-wrap:anywhere; }}
.badge {{ display:inline-block; margin:0 6px 6px 0; padding:2px 7px; border-radius:999px; background:#edf2f4; color:#27343a; font-size:12px; }}
.supported {{ background:#dcfce7; color:#166534; }}
.conflicting {{ background:#fee2e2; color:#991b1b; }}
.weak {{ background:#fef3c7; color:#92400e; }}
.community-only,.unverified {{ background:#e0e7ff; color:#3730a3; }}
.actions {{ margin-top:10px; color:var(--accent); font-size:12px; }}
a {{ color:#0f5f80; text-decoration:none; }}
a:hover {{ text-decoration:underline; }}
code {{ background:#eef2f4; padding:2px 5px; border-radius:5px; overflow-wrap:anywhere; }}
ul {{ padding-left:20px; }}
</style>
</head>
<body>
<header>
  <h1>Deep Search Evidence Board</h1>
  <div class="meta">
    <div>Query: <code>{esc(run.query)}</code></div>
    <div>Decision readiness: <strong>{esc(run.decision_readiness or 'unknown')}</strong></div>
    <div>Goal: {esc(contract.get('goal', ''))}</div>
    <div>Scope: {esc(contract.get('scope', ''))}</div>
    <div>Done evidence: {esc(contract.get('done_evidence', ''))}</div>
  </div>
</header>
<main>
  <h2>Claims</h2>
  <section class="grid">{''.join(cards) or '<p>No claims.</p>'}</section>
  <h2>Sources</h2>
  <section class="grid">{''.join(sources) or '<p>No sources.</p>'}</section>
  <h2>Duplicate Groups</h2>
  <section class="grid">{''.join(groups) or '<p>No duplicate groups.</p>'}</section>
  <h2>Follow-up Queries</h2>
  <ul>{''.join(followups) or '<li>No follow-up queries.</li>'}</ul>
</main>
</body>
</html>
"""


def write_html_report(path: str, run: SearchRun) -> str:
    report_path = Path(path).expanduser()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(build_html_report(run), encoding="utf-8")
    return str(report_path)
