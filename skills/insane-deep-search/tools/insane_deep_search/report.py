"""Markdown report formatting."""

from __future__ import annotations

from collections.abc import Iterable

from .models import SearchResult, SearchRun
from .text import compact_url


def group_by(items: Iterable[SearchResult], key: str) -> dict[str, list[SearchResult]]:
    grouped: dict[str, list[SearchResult]] = {}
    for item in items:
        grouped.setdefault(getattr(item, key), []).append(item)
    return grouped


def result_line(item: SearchResult) -> str:
    parts = [f"- [{item.source}] {item.title or '(untitled)'}"]
    if item.published:
        parts.append(f"({item.published[:10]})")
    parts.append(f"- score {item.rank_score:.1f}, evidence {item.evidence_level}")
    quality = item.metadata.get("quality_score")
    if quality is not None:
        parts.append(f", quality {quality}")
    duplicates = item.metadata.get("duplicate_count")
    if isinstance(duplicates, int) and duplicates > 1:
        parts.append(f", sources {duplicates}")
    if item.fetch_verdict:
        parts.append(f", fetch {item.fetch_verdict}")
    parts.append(f"\n  {compact_url(item.url)}")
    if item.snippet:
        parts.append(f"\n  {item.snippet[:220]}")
    return " ".join(parts)


def format_report(run: SearchRun) -> str:
    lines: list[str] = []
    lines.append("# Insane Deep Search Report")
    lines.append("")
    lines.append(f"- Query: `{run.query}`")
    lines.append(f"- Depth: `{run.depth}`")
    lines.append(f"- Packs: `{', '.join(run.packs)}`")
    lines.append(f"- Detective mode: `{'on' if run.detective else 'off'}`")
    lines.append(f"- Offsite discovery: `{'on' if run.include_offsite else 'off'}`")
    lines.append(f"- Research mode: `{'on' if run.research else 'off'}`")
    lines.append(f"- Verify mode: `{run.verify_mode}`")
    lines.append(f"- Results: `{len(run.results)}`")
    lines.append(f"- Result groups: `{len(run.result_groups)}`")
    lines.append(f"- Source errors: `{len(run.errors)}`")
    lines.append("")

    lines.append("## 핵심 요약")
    if run.results:
        for item in run.results[:5]:
            lines.append(result_line(item))
    else:
        lines.append("- 검색 결과가 없습니다. 쿼리를 더 넓게 바꾸거나 소스팩을 추가해 보세요.")
    lines.append("")

    lines.append("## 소스별 발견")
    for pack, items in group_by(run.results, "pack").items():
        lines.append(f"### {pack}")
        for item in items[:8]:
            lines.append(result_line(item))
        lines.append("")

    lines.append("## 커뮤니티 반응")
    community = [item for item in run.results if item.source_type == "community" or item.source == "stackoverflow"]
    if community:
        for item in community[:8]:
            comments = item.metadata.get("comments")
            points = item.metadata.get("points")
            engagement = []
            if comments is not None:
                engagement.append(f"comments {comments}")
            if points is not None:
                engagement.append(f"points {points}")
            suffix = f" ({', '.join(engagement)})" if engagement else ""
            lines.append(f"- [{item.source}] {item.title}{suffix}\n  {compact_url(item.url)}")
    else:
        lines.append("- 커뮤니티 소스에서 의미 있는 결과가 없거나 해당 소스가 실패했습니다.")
    lines.append("- 커뮤니티/질문답변 소스는 사실 확정이 아니라 반응과 단서로 해석해야 합니다.")
    lines.append("")

    lines.append("## 기술/논문 근거")
    technical = [item for item in run.results if item.source_type in {"developer", "registry", "research"}]
    if technical:
        for item in technical[:10]:
            lines.append(result_line(item))
    else:
        lines.append("- 기술/논문/레지스트리 소스에서 의미 있는 결과가 없습니다.")
    lines.append("")

    lines.append("## 소스 품질/중복 묶음")
    if run.result_groups:
        for group in run.result_groups[:10]:
            duplicate_count = int(group.get("duplicate_count") or 0)
            if duplicate_count <= 1 and len(run.result_groups) > 10:
                continue
            sources = ", ".join(group.get("supporting_sources", []))
            lines.append(
                f"- {group.get('representative_title') or '(untitled)'} - duplicates {duplicate_count}, sources `{sources}`\n  {compact_url(str(group.get('representative_url') or ''))}"
            )
    else:
        lines.append("- 중복 그룹 정보가 없습니다.")
    lines.append("")

    lines.append("## 후속 검색 라운드")
    if run.research:
        for round_info in run.research_rounds:
            round_id = round_info.get("round")
            result_count = round_info.get("result_count")
            lines.append(f"- Round {round_id}: results {result_count}")
            queries = round_info.get("queries", [])
            if queries:
                for query in queries[:8]:
                    if isinstance(query, dict):
                        lines.append(f"  - `{query.get('query')}` ({query.get('reason')})")
                    else:
                        lines.append(f"  - `{query}`")
    else:
        lines.append("- 꺼짐. 반복 검색은 `--research`로 켭니다.")
    lines.append("")

    lines.append("## 원문 확인 결과")
    if run.fetched_urls:
        for check in run.fetched_urls:
            status = check.status if check.status is not None else "n/a"
            link_note = f", links {len(check.links)}" if check.links else ""
            lines.append(
                f"- {check.verdict} HTTP {status}, {check.body_size} bytes, {check.elapsed_ms} ms{link_note}\n  {compact_url(check.final_url or check.url)}"
            )
    else:
        lines.append("- `--fetch-top 0`이거나 확인할 상위 URL이 없습니다.")
    lines.append("")

    lines.append("## 탐정 모드 발견 링크")
    if run.discovered_urls:
        discovery_items = [item for item in run.results if item.source == "page_discovery"]
        for item in discovery_items[:10]:
            parent = item.metadata.get("parent_url", "")
            reason = item.metadata.get("discovery_reason", [])
            reason_text = f" ({', '.join(reason[:4])})" if isinstance(reason, list) and reason else ""
            lines.append(f"- {item.title}{reason_text}\n  {compact_url(item.url)}")
            if parent:
                lines.append(f"  from {compact_url(str(parent))}")
    elif run.detective:
        lines.append("- 원문 페이지에서 쿼리와 관련도 높은 공개 링크를 추가로 찾지 못했습니다.")
    else:
        lines.append("- 꺼짐. 공개 페이지 링크 추적은 `--detective` 또는 `--dig-pages N`으로 켭니다.")
    lines.append("")

    lines.append("## 빈틈/주의점")
    lines.append("- 결과는 공개 웹/API/RSS 기반이며, 로그인 전용 자료나 비공개 정보는 포함하지 않습니다.")
    lines.append("- 탐정 모드는 공개 링크를 추적하지만 접근통제, 유료벽, 캡차, 로그인, 비공개 시스템을 우회하지 않습니다.")
    lines.append("- 커뮤니티 글은 사실 확정이 아니라 반응과 단서로 분리해서 해석해야 합니다.")
    lines.append("- 공개 API는 레이트리밋, 지역, 색인 지연 때문에 부분 실패가 날 수 있습니다.")
    if run.errors:
        lines.append("- 소스별 오류:")
        for error in run.errors[:20]:
            lines.append(f"  - {error.pack}/{error.source} `{error.query_variant}`: {error.message[:180]}")

    return "\n".join(lines).rstrip() + "\n"
