# Changelog

## 0.2.0

- Split the monolithic CLI into a package with dedicated modules for models, policy, source catalog, HTTP verification, discovery, ranking, reports, and CLI.
- Centralized source endpoints, trust weights, ranking thresholds, fetch verdict rules, and link filters.
- Made detective mode follow relevant public offsite links by default, with `--same-site-only` for conservative discovery.
- Added discovery metadata for parent URL, score, reason, and depth.
- Expanded doctor and unit tests for catalog validity, compatibility exports, offsite discovery, same-site filtering, and low-value link filtering.

## 0.1.0

- Initial Codex-native release of Insane Deep Search.
- Added public/API-first deep search across news, communities, developer sources, registries, and research indexes.
- Added ranked JSON output, Markdown reports, URL normalization, deduplication, and lightweight source verification.
- Added Codex skill routing for broad evidence searches, overseas coverage, community reaction checks, and mixed source research.
- Added detective mode for following relevant public links from fetched pages while preserving public evidence boundaries.
