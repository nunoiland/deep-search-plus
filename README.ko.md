# Insane Deep Search

Insane Deep Search는 Codex용 공개근거 딥검색 스킬입니다. 뉴스, 해외 커뮤니티, 개발자 플랫폼, 패키지 레지스트리, 논문/도서/위키 소스를 함께 검색하고, 랭킹된 JSON과 사람이 읽기 좋은 Markdown 리포트를 동시에 제공합니다. 기본 CLI 프로필은 반복 검색, 재귀 공개 링크 탐색, claim ledger, 로컬 Ollama planner를 사용하는 heavy 딥서치로 동작합니다.

이런 요청에 맞춰 설계했습니다.

- "해외 포함해서 이 종목 이슈를 넓게 찾아줘."
- "커뮤니티 반응, 뉴스, 깃헙, 논문을 같이 봐줘."
- "일반 검색 상위에 잘 안 뜨는 공개 자료를 모아줘."
- "URL, 출처 유형, 근거 강도, 원문 확인 상태까지 같이 줘."

목표는 비공개 정보, 로그인 전용 자료, 접근 통제 우회가 아닙니다. v1은 공개/API 우선 검색과 열린 URL의 기본 원문 확인에 집중합니다.

## 설치

레포를 클론한 뒤 Codex 스킬 폴더로 복사합니다.

```bash
git clone https://github.com/nunoiland/insane-deep-search.git
mkdir -p ~/.codex/skills
cp -R insane-deep-search/skills/insane-deep-search ~/.codex/skills/insane-deep-search
```

설치 후 Codex를 재시작하세요.

## CLI

스킬 디렉터리에서 바로 실행할 수 있습니다.

```bash
cd ~/.codex/skills/insane-deep-search
python3 tools/deep_search.py "현대차 관세 하이브리드" --json --report
```

기본값은 1분 안쪽의 쓸 만한 결과를 목표로 합니다.

- `--depth balanced`
- `--pack news,community,tech,research`
- `--limit 8`
- `--research` on, `--research-depth 2`, `--research-breadth 4`
- `--verify-mode basic`
- `--fetch-top 3`
- `--dig-pages 4`, `--crawl-depth 1`, `--max-page-links 24`, `--max-total-fetches 12`
- `--local-llm auto --local-llm-model gemma4:latest --local-llm-timeout 5`
- `--max-workers 8`, `--time-budget 60`
- `--cache on`
- `--locale ko-KR`
- 진행 로그는 기본적으로 stderr에 출력하며 `--quiet`으로 끌 수 있음
- 리포트와 JSON 동시 출력 가능

빠른 실행은 `--quick`을 사용합니다. 이 옵션은 반복 검색, 로컬 LLM planner, URL fetch, 재귀 crawl을 끕니다.
기존 98%급 무거운 탐색은 `--ultra`를 사용합니다. 더 깊은 후속 라운드, 더 많은 URL 확인, 렌더링 fallback, crawl depth 3을 사용하므로 몇 분 걸릴 수 있습니다.

재귀 탐색으로 공개 근거 링크를 더 따라갈 수 있습니다. 기본적으로 쿼리 관련도가 높은 공개 offsite 링크까지 후보로 봅니다.

```bash
python3 tools/deep_search.py "AI capex power grid" --dig-pages 16 --crawl-depth 3 --json --report
```

재귀 탐색은 상위 원문 페이지에서 공개 링크를 추출하고, 쿼리 관련도 기준으로 강한 후보를 다시 확인합니다. 각 발견 URL에는 부모 페이지와 parent chain이 기록됩니다. 같은 사이트 안에서만 보수적으로 확인하려면 `--same-site-only`를 사용합니다. 로그인, 유료벽, 캡차, 접근통제, 차단된 시스템은 우회하지 않습니다.

리서치 모드는 제한된 후속 검색을 반복하고, 중복 근거를 묶고, 소스 품질 신호를 추가합니다.

```bash
python3 tools/deep_search.py "OpenAI Codex latest GitHub issues papers news community" --research --research-depth 2 --research-breadth 4 --json --report
```

`--verify-mode auto`를 쓰면 기본 fetch가 차단되거나 약할 때만 선택적으로 렌더링 검증을 시도합니다. `crawl4ai`는 선택 의존성이며 설치되어 있지 않아도 CLI는 동작합니다.

로컬 LLM planner는 Ollama만 사용하며 외부 LLM API를 호출하지 않습니다. 기본 CLI는 `gemma4:latest`를 짧게 한 번 시도한 뒤 휴리스틱으로 fallback합니다. `--ultra`는 `gemma4:latest`, `qwen2.5:7b`, `llama3.2:3b`, 휴리스틱 순서의 넓은 fallback을 복원합니다. 로컬 모델을 끄려면 `--local-llm off`, 반드시 쓰려면 `--local-llm required`를 사용합니다. 모델별 timeout은 `--local-llm-timeout` 또는 `DEEP_SEARCH_LOCAL_LLM_TIMEOUT`으로 조정할 수 있습니다.

## 구조

CLI 진입점은 `tools/deep_search.py`로 유지하고, 실제 구현은 `tools/insane_deep_search/` 패키지에 있습니다.

- 소스 카탈로그와 정책 기본값을 중앙화했습니다.
- HTTP 확인, 링크 발견, 랭킹, 리포트, CLI를 책임별로 분리했습니다.
- 소스 어댑터는 엔드포인트와 trust 설정을 카탈로그에서 읽습니다.

## 소스팩

| Pack | Sources |
| --- | --- |
| `news` | Google News RSS 한국어/영어, GDELT DOC 2.0 |
| `community` | Reddit 공개 JSON 검색, Hacker News Algolia, Lobste.rs, dev.to, V2EX |
| `tech` | GitHub 저장소/이슈와 경량 enrichment, Stack Overflow, npm, PyPI exact lookup, Hugging Face 모델/데이터셋 |
| `research` | arXiv, Crossref, OpenAlex, Semantic Scholar, Open Library, Wikipedia OpenSearch |

안정적인 공개 API가 없는 한국 커뮤니티는 v1에서 사이트별 스크래퍼로 하드코딩하지 않습니다. 추후 `site:` 후보 발견이나 메타검색 플러그인으로 분리하는 방향이 더 안전합니다.

## 출력 구조

각 결과는 다음 필드를 포함합니다.

- `source`, `source_type`, `pack`
- `title`, `url`, `canonical_url`, `snippet`, `published`
- `query_variant`
- `score`, `rank_score`, `evidence_level`
- `fetched`, `fetch_verdict`, `metadata`
- `metadata` 안의 `quality_score`, `quality_reasons`, `risk_flags`
- 같은 근거가 묶인 경우 `group_id`, `duplicate_count`, `supporting_sources`
- 탐정 모드에서 원문 확인 URL의 `links`
- 상위 페이지에서 따라간 `discovered_urls`
- 리서치 모드의 `research_rounds`, `result_groups`
- 발견 링크 metadata: `parent_url`, `parent_chain`, `discovery_score`, `discovery_reason`, `discovery_depth`
- `coverage`, `claims`, `planner_steps`, `crawl_traces`, `local_llm`, `cache_stats`, `retry_stats`
- `errors`

Markdown 리포트 순서:

1. 핵심 요약
2. 검색 커버리지
3. 검증된 주장 / 약한 주장 / 커뮤니티 단독 반응
4. 소스별 발견
5. 커뮤니티 반응
6. 기술/논문 근거
7. 소스 품질/중복 묶음
8. 후속 검색 라운드와 planner trace
9. 원문 확인, crawl trace, local runtime
10. 빈틈/주의점

## 자연어 트리거

Codex에서 이런 식으로 요청하면 이 스킬을 우선 사용합니다.

- "딥검색으로 넓게 찾아줘"
- "해외 포함해서 커뮤니티 반응까지 봐줘"
- "뉴스, 논문, 깃헙 같이 공개근거로 정리해줘"
- "공개되어 있는데 잘 안 보이는 자료 위주로 찾아줘"
- "탐정 모드로 상위 페이지 안의 관련 링크까지 따라가줘"

단일 URL 읽기는 일반 URL 확인 흐름을 쓰고, 주제 기반 전방위 탐색은 Insane Deep Search를 사용합니다.
