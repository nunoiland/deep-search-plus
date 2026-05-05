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

Do not use it for private data, login-only content, or access-control bypass. "Hidden" means public material that is easy to miss: public APIs, RSS, registries, communities, metadata, papers, issues, and secondary sources.

## Default Command

Run from this skill directory:

```bash
python3 tools/deep_search.py "query" --json --report
```

Useful options:

- `--depth quick|balanced|deep`
- `--pack news,community,tech,research`
- `--limit N`
- `--fetch-top N`
- `--locale ko-KR`

## Routing

Use `tools/deep_search.py` first when the user wants broad discovery, source classification, overseas sources, community reaction, public evidence, or mixed source packs.

For a single known URL, use the normal Codex URL reading path instead of this skill.

If the user asks for financial, medical, legal, or other high-stakes interpretation, collect public evidence with this skill first, then clearly separate sourced facts from analysis and uncertainty.

## Report Expectations

When summarizing results for the user:

1. Lead with what the public evidence suggests.
2. Group evidence by source type.
3. Call out community reaction separately from reported facts.
4. Mention fetch verification failures and source gaps.
5. Avoid presenting rumors, comments, or forum posts as confirmed facts.

The CLI already emits a Markdown report and JSON. Use JSON for precise URLs and ranking, and use the report for the human-readable summary.
