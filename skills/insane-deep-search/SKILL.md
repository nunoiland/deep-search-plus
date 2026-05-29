---
name: insane-deep-search
description: Codex-native public evidence deep search across news, communities, developer sources, registries, and research indexes. Use when the user asks for broad discovery, overseas coverage, community reaction, public evidence, or mixed sources such as news, GitHub, papers, and forums.
---

# Insane Deep Search

Use this skill when the user asks to search broadly rather than read one known URL.

Prefer this tool for requests such as:

- "딥검색으로 넓게 찾아줘"
- "해외 포함해서 찾아줘"
- "커뮤니티 반응까지 봐줘"
- "공개근거 위주로 정리해줘"
- "뉴스, 논문, 깃헙 같이 봐줘"
- "Find public evidence across news, GitHub, papers, and forums"
- "끝까지 파고들어 공개 근거 링크까지 따라가줘"

Do not use it for private data, login-only content, or access-control bypass. "Hidden" means public material that is easy to miss: public APIs, RSS, registries, communities, metadata, papers, issues, and secondary sources.

## Default Command

Run from this skill directory:

```bash
python3 tools/deep_search.py "query" --json --report
```

The default CLI profile is intentionally heavy: iterative research is on, local Ollama planning is auto-enabled with `gemma4:latest`, top URLs are verified, and public evidence links are recursively followed within bounded limits. Use `--quick` when the user wants a fast low-cost pass.

Useful options:

- `--quick`
- `--depth quick|balanced|deep`
- `--pack news,community,tech,research`
- `--limit N`
- `--fetch-top N`
- `--no-research`
- `--research-depth N`
- `--research-breadth N`
- `--dig-pages N`
- `--crawl-depth N`
- `--max-page-links N`
- `--max-total-fetches N`
- `--local-llm auto|off|required`
- `--local-llm-model MODEL`
- `--cache on|off`
- `--include-offsite`
- `--same-site-only`
- `--locale ko-KR`

## Recursive Discovery

Use recursive discovery when the user wants a more persistent public investigation:

```bash
python3 tools/deep_search.py "query" --dig-pages 16 --crawl-depth 3 --json --report
```

Recursive discovery verifies the top result pages, extracts public links from those pages, filters them by query relevance, and fetches the most relevant discovered links. It records the parent page, parent chain, discovery score, reason, and depth so Codex can explain how a clue was found.

By default, detective mode may follow relevant public offsite links. Use `--same-site-only` when the user wants conservative same-domain discovery.

This mode must stay within public evidence boundaries. It does not bypass login, paywalls, access control, captcha, private systems, or intentionally blocked resources.

## Local LLM

The tool may use local Ollama for planning and claim extraction. It must not call hosted LLM APIs. Default model order is `gemma4:latest`, `qwen2.5:7b`, `llama3.2:3b`, then deterministic heuristics. If the user wants no local model use, pass `--local-llm off`. If they explicitly require the local model, pass `--local-llm required`. Use `DEEP_SEARCH_LOCAL_LLM_TIMEOUT` to adjust the per-model timeout.

## Routing

Use `tools/deep_search.py` first when the user wants broad discovery, source classification, overseas sources, community reaction, public evidence, or mixed source packs.

For a single known URL, use the normal Codex URL reading path instead of this skill.

If the user asks for financial, medical, legal, or other high-stakes interpretation, collect public evidence with this skill first, then clearly separate sourced facts from analysis and uncertainty.

## Report Expectations

When summarizing results for the user:

1. Lead with what the public evidence suggests.
2. Group evidence by source type.
3. Call out community reaction separately from reported facts.
4. Mention coverage, claim status, fetch verification failures, and source gaps.
5. Avoid presenting rumors, comments, or forum posts as confirmed facts.
6. In recursive discovery mode, explain which links were discovered from parent pages.

The CLI already emits a Markdown report and JSON. Use JSON for precise URLs and ranking, and use the report for the human-readable summary.
