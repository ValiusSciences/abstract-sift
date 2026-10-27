# Release readiness

Local audit completed 2026-10-26. Status: ready for beta use; software licensed under MIT.

## Verified locally

- All 38 Python tests pass on Python 3.11, 3.13 and 3.14 on macOS.
- Coverage with branch measurement: 90% overall; CI requires at least 85%.
- Black formatting checks pass.
- Offline CLI workflow passes with synthetic data and mocked providers: import, estimate, score, reports, comparison, table export and standalone HTML generation.
- Node-based HTML checks pass for loading, full-text modal, scatter plot, filters, safe formatting and operation without network or file-history support.
- Wheel installs in a separate environment and passes the same CLI/HTML smoke check.
- Wheel and source archives contain all five web assets and pass private/runtime path checks.
- Runtime dependency audit using pip-audit reports no known vulnerabilities. This is a point-in-time check, not a security guarantee.
- Git ignores credentials, local databases, private corpora, generated exports and build output. Repository initialized on main; no remote or public release created.

## Reliability fixes

Concurrent requests wait for in-flight budget reservations to reconcile before reporting insufficient allowance. Malformed provider usage is retained as unknown exposure instead of breaking cost reports. Positive finite Retry-After values are honored without a 120-second cap. SQLite errors are presented without tracebacks or SQL contents.

## Automation and remaining checks

GitHub Actions is configured for macOS/Linux with Python 3.11, 3.13 and 3.14, including formatting, coverage, offline workflow, archive inspection and installed-wheel checks. This matrix has not yet run on GitHub.

The software is licensed under MIT; third-party abstracts retain their original rights. Real-browser visual/accessibility validation and clinical relevance validation remain separate from these automated checks. Live provider behavior was mocked during this audit; no paid scoring calls were made and no existing scoring runs were modified.

See [CONTRIBUTING.md](../CONTRIBUTING.md) for reproducible check commands.
