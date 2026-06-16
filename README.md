# Deep Search plus

## 한국어 핵심 요약

Deep Search Plus는 Codex 안에서 뉴스, 커뮤니티, GitHub, 패키지, 논문 근거를 한 번에 따라가는 공개근거 딥서치 스킬입니다.

- 검색 결과를 많이 나열하는 데서 끝나지 않고, 같은 근거를 묶고 소스 품질과 검증 상태를 함께 보여줍니다.
- 기본 실행은 약 1분 안쪽의 쓸 만한 결과를 목표로 하며, 더 깊은 탐색은 `--ultra`로 켭니다.
- Ollama 로컬 모델이 있으면 후속 검색 계획에 활용하고, 없어도 휴리스틱으로 안전하게 동작합니다.
- 자세한 한국어 설명은 아래 [한국어 소개](#한국어-소개) 섹션을 보세요.

## English Overview

Deep Search plus is a Codex-native public evidence research skill. It searches across news, communities, developer platforms, package registries, and research indexes, then returns both a ranked JSON payload and a readable Markdown report. The default CLI profile targets a fast deep-search flow with iterative planning, public-link crawling, claim grouping, and optional local Ollama planning.

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
cp -R deep-search-plus/skills/insane-deep-search ~/.codex/skills/deep-search-plus
```

Restart Codex after installing the skill.

## CLI

Run the tool directly from the skill directory:

```bash
cd ~/.codex/skills/deep-search-plus
python3 tools/deep_search.py "openai agents sdk" --json --report
```

Default behavior targets a useful result in about a minute:

- `--depth balanced`
- `--pack news,community,tech,research`
- `--limit 8` per source
- `--research` on, `--research-depth 2`, `--research-breadth 4`
- `--verify-mode basic`
- `--fetch-top 3`
- `--dig-pages 4`, `--crawl-depth 1`, `--max-page-links 24`, `--max-total-fetches 12`
- `--local-llm auto --local-llm-model gemma4:latest --local-llm-timeout 5`
- `--max-workers 8`, `--time-budget 60`
- `--cache on`
- `--locale ko-KR`
- progress logs print to stderr unless `--quiet` is used
- report and JSON can be printed together

Use `--quick` for a fast profile that disables iterative research, local LLM planning, URL fetching, and recursive crawling.
Use `--ultra` for the older maximum-depth profile: deeper follow-up rounds, more URL verification, rendered fallback, and recursive crawl depth 3. It can take several minutes.

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

Local LLM planning uses Ollama only and never calls hosted LLM APIs. The default CLI tries `gemma4:latest` once with a short timeout, then falls back to deterministic heuristics. `--ultra` restores the broader fallback order: `gemma4:latest`, `qwen2.5:7b`, `llama3.2:3b`, then heuristics. Use `--local-llm off` to disable local model planning or `--local-llm required` to fail clearly when Ollama is unavailable. `--local-llm-timeout` or `DEEP_SEARCH_LOCAL_LLM_TIMEOUT` controls the per-model timeout.

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

## 한국어 소개

### 검색 결과를 더 많이 모으는 도구가 아니라, 근거를 놓치지 않는 딥서치 엔진

Deep Search Plus는 Codex 안에서 공개 근거를 넓고 깊게 따라가는 리서치 스킬입니다. 한 번의 질문으로 뉴스, 커뮤니티, GitHub, 패키지 레지스트리, 논문/인용 데이터베이스를 함께 훑고, 중복된 근거를 묶고, 소스 품질과 검증 상태까지 리포트로 정리합니다.

일반 검색이 "상위 링크 몇 개"를 보여준다면, Deep Search Plus는 "어떤 출처들이 같은 주장을 뒷받침하는지", "커뮤니티 반응은 사실 근거와 어떻게 다른지", "아직 빈틈이 어디에 남아 있는지"까지 보여주는 것을 목표로 합니다.

### 이런 상황에 좋습니다

- 특정 기업, 종목, 제품, 기술 이슈를 뉴스와 커뮤니티 반응까지 함께 보고 싶을 때
- GitHub 이슈, 릴리스, 패키지, 논문 근거를 한 번에 모아야 할 때
- 영어권 자료와 한국어 자료를 같이 훑고 싶은데 매번 검색어를 바꾸기 귀찮을 때
- 단순 요약보다 URL, 출처, 신뢰도, 중복 여부, 원문 확인 상태가 필요할 때
- Codex 대화방 안에서 바로 근거 중심 리서치를 반복하고 싶을 때

### 핵심 차별점

- **멀티소스 검색**: 뉴스, Reddit, Hacker News, Lobste.rs, dev.to, V2EX, GitHub, Stack Overflow, npm, PyPI, Hugging Face, arXiv, Crossref, OpenAlex, Semantic Scholar, Wikipedia를 함께 탐색합니다.
- **근거 그룹화**: 같은 이슈를 다루는 URL을 버리지 않고 `group_id`, `duplicate_count`, `supporting_sources`로 묶어 보여줍니다.
- **소스 품질 점수**: GitHub stars/release activity, 논문 DOI/citation/year, 뉴스 발행일/원출처성, 커뮤니티 반응량 같은 신호를 품질 점수와 risk flag로 표시합니다.
- **후속 검색 라운드**: 부족한 출처, 약한 주장, 커뮤니티 단독 반응을 기준으로 추가 검색어를 만들고 제한된 라운드 안에서 다시 확인합니다.
- **로컬 LLM planner**: Ollama의 `gemma4:latest`가 있으면 후속 검색 계획에 활용하고, 없거나 실패하면 휴리스틱으로 안전하게 fallback합니다.
- **재귀 공개 링크 탐색**: 상위 페이지 안의 관련 공개 링크를 따라가며 parent chain과 발견 이유를 기록합니다.
- **빠른 기본값과 ultra 모드**: 기본 실행은 약 1분 안쪽의 쓸 만한 결과를 목표로 하고, 더 깊은 탐색은 `--ultra`로 명시적으로 켭니다.

### 빠른 시작

```bash
git clone https://github.com/nunoiland/deep-search-plus.git
mkdir -p ~/.codex/skills
cp -R deep-search-plus/skills/insane-deep-search ~/.codex/skills/deep-search-plus
```

Codex를 재시작한 뒤, 스킬 폴더에서 바로 실행합니다.

```bash
cd ~/.codex/skills/deep-search-plus
python3 tools/deep_search.py "OpenAI Codex 최신 이슈 논문 뉴스 커뮤니티 반응" --json --report
```

빠르게 확인하려면:

```bash
python3 tools/deep_search.py "KCC 주식 이슈 뉴스 커뮤니티 반응" --quick --report
```

깊게 파고들려면:

```bash
python3 tools/deep_search.py "AI capex power grid 논문 뉴스 GitHub 커뮤니티" --ultra --json --report
```

### Codex에서 이렇게 요청하세요

- "딥검색으로 해외 뉴스, 논문, GitHub, 커뮤니티 반응까지 같이 찾아줘"
- "이 이슈를 공개근거 기준으로 중복 묶고 소스 품질까지 평가해줘"
- "커뮤니티 반응과 검증된 사실을 분리해서 정리해줘"
- "상위 원문 안의 관련 링크까지 따라가서 근거를 더 찾아줘"
- "빠르게 보고 싶으니 quick으로, 깊게 보고 싶으면 ultra로 돌려줘"

### 지켜야 할 선

Deep Search Plus는 공개된 자료를 더 잘 찾고 정리하는 도구입니다. 로그인 전용 콘텐츠, 유료벽, 캡차, 접근통제, 비공개 데이터는 우회하지 않습니다. 리포트의 claim ledger와 quality score는 의사결정을 돕는 보조 신호이며, 법률/투자/의료 같은 고위험 판단은 원문 확인과 전문가 검토가 필요합니다.
