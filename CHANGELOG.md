# Changelog

## 0.1.0 — initial beta (unreleased)

- OpenAI Decisions and TypeSafe JEV scoring, independently or together.
- Adaptive batching, bounded concurrency, rate limiting, retries and resumable SQLite runs.
- Integer per-request cost accounting, unknown exposure, and runtime settings per invocation.
- Table/JSON CLI reports, provider progress bars, filtering and CSV/TSV/JSONL export.
- Within-run agreement metrics and across-run stability comparisons.
- Self-contained offline HTML explorer with full text, filters and score scatter plot.
- Reliability audit: wait for in-flight budget reservations to reconcile; tolerate malformed usage counters; honor long Retry-After values; sanitize database errors.
- Automated offline CLI, transport, accounting, packaging, and web-interaction checks.
- Retry transient HTTP 408 and all 5xx responses, including CDN gateway errors 520–524; previously a single HTTP 520 left a batch failed without retry.
- Explorer generation reads one SQLite snapshot instead of copying the whole local database into memory, and fails if a bundled UI asset no longer matches its local-file patches.
- CI adds Python 3.12, ruff, warnings-as-errors tests, a 95% coverage floor, tracked-file hygiene checks, a weekly dependency audit and Dependabot.

Measured in one user-run ESMO benchmark: 4,284 abstracts per provider in 13.31 seconds of scoring time (15.27 seconds command wall time), $0.8680 usage-derived cost, using concurrency 16 and batch size 32. This is account-specific evidence, not a latency guarantee or clinical accuracy validation.
