# Deep Search plus

Deep Search plus is a Codex-native public evidence research skill. It searches across news, communities, developer platforms, package registries, and research indexes, then returns both a ranked JSON payload and a readable Markdown report. The default CLI profile now runs a heavy local deep-search flow with iterative planning, recursive public-link crawling, claim grouping, and optional local Ollama planning.

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
python3 tools/deep_search.py "openai agents sdk" --json --report
```

Default behavior:

- `--depth deep`
- `--pack news,community,tech,research`
- `--limit 8` per source
- `--research` on, `--research-depth 4`, `--research-breadth 8`
- `--verify-mode auto`
- `--fetch-top 10`
- `--dig-pages 16`, `--crawl-depth 3`, `--max-page-links 24`, `--max-total-fetches 60`
- `--local-llm auto --local-llm-model gemma4:latest`
- `--cache on`
- `--locale ko-KR`
- report and JSON can be printed together

Use `--quick` for a fast profile that disables iterative research, local LLM planning, URL fetching, and recursive crawling.

Recursive discovery follows public evidence trails from top pages, including relevant public offsite links by default:

```bash
python3 tools/deep_search.py "AI capex power grid" --dig-pages 16 --crawl-depth 3 --json --report
```

The crawler extracts public links from fetched pages, filters them by query relevance, records the parent chain, and verifies the strongest discovered URLs. Use `--same-site-only` when you want conservative same-domain discovery. It does not bypass login, paywalls, captcha, access controls, or blocked systems.

Research mode runs bounded follow-up searches, groups duplicates, and adds source quality signals:

```bash
python3 tools/deep_search.py "OpenAI Codex latest GitHub issues papers news community" --research --research-depth 2 --research-breadth 4 --json --report
```

Use `--verify-mode auto` to try optional rendered verification only when the basic fetch is blocked or weak. `crawl4ai` is optional; the CLI still works when it is not installed.

Local LLM planning uses Ollama only and never calls hosted LLM APIs. The preferred model is `gemma4:latest`, falling back to `qwen2.5:7b`, `llama3.2:3b`, then deterministic heuristics. Use `--local-llm off` to disable local model planning or `--local-llm required` to fail clearly when Ollama is unavailable. `DEEP_SEARCH_LOCAL_LLM_TIMEOUT` controls the per-model timeout.

## Structure

The CLI entrypoint stays stable at `tools/deep_search.py`, while the implementation lives in `tools/insane_deep_search/`:

- source catalog and policy defaults are centralized
- HTTP verification, discovery, ranking, reporting, and CLI are separated
- source adapters read endpoint and trust settings from the catalog instead of scattering them through the search logic

## Source Packs

| Pack | Sources |
| --- | --- |
| `news` | Google News RSS in Korean and English, GDELT DOC 2.0 |
| `community` | Reddit public JSON search, Hacker News Algolia, Lobste.rs, dev.to, V2EX |
| `tech` | GitHub repositories and issues with lightweight enrichment, Stack Overflow, npm, PyPI exact lookup, Hugging Face models and datasets |
| `research` | arXiv, Crossref, OpenAlex, Semantic Scholar, Open Library, Wikipedia OpenSearch |

Korean community sites without stable public APIs are intentionally not hardcoded in v1. Use broader web search or a future pluggable metasearch source for `site:`-based discovery.

## Output

Each result includes:

- `source`, `source_type`, `pack`
- `title`, `url`, `canonical_url`, `snippet`, `published`
- `query_variant`
- `score`, `rank_score`, `evidence_level`
- `fetched`, `fetch_verdict`, `metadata`
- `quality_score`, `quality_reasons`, `risk_flags` inside `metadata`
- `group_id`, `duplicate_count`, and `supporting_sources` when equivalent evidence is grouped
- `links` on fetched URL checks when detective mode is enabled
- `discovered_urls` for public links followed from top pages
- `research_rounds` and `result_groups` when research mode is enabled
- discovery metadata such as `parent_url`, `parent_chain`, `discovery_score`, `discovery_reason`, and `discovery_depth`
- `coverage`, `claims`, `planner_steps`, `crawl_traces`, `local_llm`, `cache_stats`, and `retry_stats`
- `errors`

The Markdown report is ordered as:

1. Key summary
2. Search coverage
3. Verified, weak, and community-only claims
4. Source findings
5. Community reaction
6. Technical and research evidence
7. Source quality and duplicate groups
8. Follow-up search rounds and planner trace
9. Fetch verification, crawl trace, local runtime
10. Gaps and cautions

## Examples

```bash
python3 tools/deep_search.py "Hyundai tariffs hybrid sales" --pack news,community --limit 4 --fetch-top 2 --json
python3 tools/deep_search.py "openai agents sdk" --pack tech,research --depth quick --limit 2 --fetch-top 0 --report
python3 tools/deep_search.py "Kia HEV EV margin buyback" --pack news,community,research --depth balanced
python3 tools/deep_search.py "AI capex power grid" --same-site-only --dig-pages 4 --crawl-depth 2 --report
python3 tools/deep_search.py "OpenAI Codex GitHub papers community" --local-llm auto --json --report
python3 tools/deep_search.py "OpenAI Codex GitHub papers community" --quick --json --report
```

## Codex Triggers

Use natural Korean or English requests inside Codex:

- "딥검색으로 넓게 찾아줘"
- "해외 포함해서 커뮤니티 반응까지 봐줘"
- "뉴스, 논문, 깃헙 같이 공개근거로 정리해줘"
- "숨은 정보 말고 공개되어 있는데 잘 안 보이는 자료 위주로 찾아줘"
- "탐정 모드로 상위 페이지 안의 관련 링크까지 따라가줘"

Single URL reading should stay with ordinary URL-fetching workflows. Broad topic discovery should use Insane Deep Search.
