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

Measured in one user-run ESMO benchmark: 4,284 abstracts per provider in 13.31 seconds of scoring time (15.27 seconds command wall time), $0.8680 usage-derived cost, using concurrency 16 and batch size 32. This is account-specific evidence, not a latency guarantee or clinical accuracy validation.
