# Release readiness

Local audit updated 2026-10-26. Status: ready for beta use; software licensed under MIT.

## Verified locally

- All 60 Python tests pass on Python 3.11, 3.12, 3.13 and 3.14 on macOS with warnings treated as errors.
- Coverage with branch measurement: 97% overall; CI requires at least 95%.
- Black formatting, ruff correctness checks and tracked-file hygiene checks pass.
- Offline CLI workflow passes with synthetic data and mocked providers: import, estimate, score, reports, comparison, table export and standalone HTML generation.
- Node-based HTML checks pass for loading, full-text modal, scatter plot, filters, safe formatting and operation without network or file-history support.
- The full ESMO explorer (4,418 records) loads in headless Chromium with no console errors or warnings; the modal, filters and scatter plot work, and its discordant count matches the CLI.
- Wheel installs in a separate environment and passes the same CLI/HTML smoke check.
- Wheel and source archives contain all five web assets and pass private/runtime path checks.
- pip-audit reports no known vulnerabilities in the locked runtime and development dependencies. CI repeats this on every push and weekly; it is not a security guarantee.
- Git ignores credentials, local databases, private corpora, generated exports and build output.

## Live runs

Full ESMO runs scored 4,284 abstracts per provider (134 missing texts) in 13.0–15.1 seconds of invocation time at concurrency 16 and batch size 32, for about $0.87 in usage-derived cost. One run ended partial after a single HTTP 520 failed an 11-abstract OpenAI batch; 520–524 and other 5xx responses are now retried.

## Reliability fixes

Concurrent requests wait for in-flight budget reservations to reconcile before reporting insufficient allowance. Malformed provider usage is retained as unknown exposure instead of breaking cost reports. Positive finite Retry-After values are honored without a 120-second cap. Transient 408 and 5xx responses are retried. SQLite errors are presented without tracebacks or SQL contents.

## Automation and remaining checks

GitHub Actions runs on macOS and Linux with Python 3.11–3.14, covering formatting, linting, repository hygiene, dependency audit, coverage, the offline workflow, archive inspection and installed-wheel checks. Dependabot proposes weekly action and dependency updates.

The software is licensed under MIT; third-party abstracts retain their original rights. Automated real-browser and accessibility checks, and clinical relevance validation, remain outside CI.

See [CONTRIBUTING.md](../CONTRIBUTING.md) for reproducible check commands.
