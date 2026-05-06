# Deep Search plus

Deep Search plus is a Codex-native public evidence research skill. It searches across news, communities, developer platforms, package registries, and research indexes, then returns both a ranked JSON payload and a readable Markdown report.

It is built for questions such as:

- "Find overseas coverage and community reaction for this company."
- "Search news, GitHub, package registries, and papers together."
- "Collect public evidence that is easy to miss in normal search results."
- "Give me the URLs, source type, confidence, and verification status."

The goal is not private data, login-only content, or bypassing access controls. The product focuses on public/API-first discovery and lightweight verification of open URLs.

## Install

Clone the repository and copy the skill into Codex:

```bash
git clone https://github.com/nunoiland/deep-search-plus.git
mkdir -p ~/.codex/skills
cp -R insane-deep-search/skills/insane-deep-search ~/.codex/skills/deep-search-plus
```

Restart Codex after installing the skill.

## CLI

Run the tool directly from the skill directory:

```bash
cd ~/.codex/skills/deep-search-plus
python3 tools/deep_search.py "openai agents sdk" --depth quick --pack tech,research --limit 3 --fetch-top 1 --json --report
```

Default behavior:

- `--depth deep`
- `--pack news,community,tech,research`
- `--limit 8` per source
- `--fetch-top 5`
- `--locale ko-KR`
- report and JSON can be printed together

Detective mode follows public evidence trails from top pages, including relevant public offsite links by default:

```bash
python3 tools/deep_search.py "AI capex power grid" --depth deep --fetch-top 5 --detective --dig-pages 8 --json --report
```

Detective mode extracts public links from fetched pages, filters them by query relevance, records the parent page, and verifies the strongest discovered URLs. Use `--same-site-only` when you want conservative same-domain discovery. It does not bypass login, paywalls, captcha, access controls, or blocked systems.

## Structure

The CLI entrypoint stays stable at `tools/deep_search.py`, while the implementation lives in `tools/insane_deep_search/`:

- source catalog and policy defaults are centralized
- HTTP verification, discovery, ranking, reporting, and CLI are separated
- source adapters read endpoint and trust settings from the catalog instead of scattering them through the search logic

## Source Packs

| Pack | Sources |
| --- | --- |
| `news` | Google News RSS in Korean and English |
| `community` | Reddit public JSON search, Hacker News Algolia, Lobste.rs, dev.to, V2EX |
| `tech` | GitHub repositories, GitHub issues, Stack Overflow, npm, PyPI exact lookup, Hugging Face models and datasets |
| `research` | arXiv, Crossref, Open Library, Wikipedia OpenSearch |

Korean community sites without stable public APIs are intentionally not hardcoded in v1. Use broader web search or a future pluggable metasearch source for `site:`-based discovery.

## Output

Each result includes:

- `source`, `source_type`, `pack`
- `title`, `url`, `canonical_url`, `snippet`, `published`
- `query_variant`
- `score`, `rank_score`, `evidence_level`
- `fetched`, `fetch_verdict`, `metadata`
- `links` on fetched URL checks when detective mode is enabled
- `discovered_urls` for public links followed from top pages
- discovery metadata such as `parent_url`, `discovery_score`, `discovery_reason`, and `discovery_depth`
- `errors`

The Markdown report is ordered as:

1. Key summary
2. Source findings
3. Community reaction
4. Technical and research evidence
5. Fetch verification
6. Gaps and cautions

## Examples

```bash
python3 tools/deep_search.py "Hyundai tariffs hybrid sales" --pack news,community --limit 4 --fetch-top 2 --json
python3 tools/deep_search.py "openai agents sdk" --pack tech,research --depth quick --limit 2 --fetch-top 0 --report
python3 tools/deep_search.py "Kia HEV EV margin buyback" --pack news,community,research --depth balanced
python3 tools/deep_search.py "AI capex power grid" --detective --same-site-only --dig-pages 4 --report
```

## Codex Triggers

Use natural Korean or English requests inside Codex:

- "딥검색으로 넓게 찾아줘"
- "해외 포함해서 커뮤니티 반응까지 봐줘"
- "뉴스, 논문, 깃헙 같이 공개근거로 정리해줘"
- "숨은 정보 말고 공개되어 있는데 잘 안 보이는 자료 위주로 찾아줘"
- "탐정 모드로 상위 페이지 안의 관련 링크까지 따라가줘"

Single URL reading should stay with ordinary URL-fetching workflows. Broad topic discovery should use Insane Deep Search.
