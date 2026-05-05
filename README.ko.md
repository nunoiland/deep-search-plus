# Insane Deep Search

Insane Deep Search는 Codex용 공개근거 딥검색 스킬입니다. 뉴스, 해외 커뮤니티, 개발자 플랫폼, 패키지 레지스트리, 논문/도서/위키 소스를 함께 검색하고, 랭킹된 JSON과 사람이 읽기 좋은 Markdown 리포트를 동시에 제공합니다.

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
python3 tools/deep_search.py "현대차 관세 하이브리드" --pack news,community --limit 3 --fetch-top 1 --json --report
```

기본값:

- `--depth deep`
- `--pack news,community,tech,research`
- `--limit 8`
- `--fetch-top 5`
- `--locale ko-KR`
- 리포트와 JSON 동시 출력 가능

탐정 모드로 공개 근거 링크를 더 따라갈 수 있습니다.

```bash
python3 tools/deep_search.py "AI capex power grid" --depth deep --fetch-top 5 --detective --dig-pages 8 --json --report
```

탐정 모드는 상위 원문 페이지에서 공개 링크를 추출하고, 쿼리 관련도 기준으로 강한 후보를 다시 확인합니다. 각 발견 URL에는 부모 페이지가 기록됩니다. 로그인, 유료벽, 캡차, 접근통제, 차단된 시스템은 우회하지 않습니다.

## 소스팩

| Pack | Sources |
| --- | --- |
| `news` | Google News RSS 한국어/영어 |
| `community` | Reddit 공개 JSON 검색, Hacker News Algolia, Lobste.rs, dev.to, V2EX |
| `tech` | GitHub 저장소, GitHub 이슈, Stack Overflow, npm, PyPI exact lookup, Hugging Face 모델/데이터셋 |
| `research` | arXiv, Crossref, Open Library, Wikipedia OpenSearch |

안정적인 공개 API가 없는 한국 커뮤니티는 v1에서 사이트별 스크래퍼로 하드코딩하지 않습니다. 추후 `site:` 후보 발견이나 메타검색 플러그인으로 분리하는 방향이 더 안전합니다.

## 출력 구조

각 결과는 다음 필드를 포함합니다.

- `source`, `source_type`, `pack`
- `title`, `url`, `canonical_url`, `snippet`, `published`
- `query_variant`
- `score`, `rank_score`, `evidence_level`
- `fetched`, `fetch_verdict`, `metadata`
- 탐정 모드에서 원문 확인 URL의 `links`
- 상위 페이지에서 따라간 `discovered_urls`
- `errors`

Markdown 리포트 순서:

1. 핵심 요약
2. 소스별 발견
3. 커뮤니티 반응
4. 기술/논문 근거
5. 원문 확인 결과
6. 빈틈/주의점

## 자연어 트리거

Codex에서 이런 식으로 요청하면 이 스킬을 우선 사용합니다.

- "딥검색으로 넓게 찾아줘"
- "해외 포함해서 커뮤니티 반응까지 봐줘"
- "뉴스, 논문, 깃헙 같이 공개근거로 정리해줘"
- "공개되어 있는데 잘 안 보이는 자료 위주로 찾아줘"
- "탐정 모드로 상위 페이지 안의 관련 링크까지 따라가줘"

단일 URL 읽기는 일반 URL 확인 흐름을 쓰고, 주제 기반 전방위 탐색은 Insane Deep Search를 사용합니다.
