# Contributing

Python 3.11–3.14 on macOS or Linux and Node.js 22+ are the development targets. Native Windows is not supported because run locking uses `fcntl`; use WSL instead.

```bash
uv sync --locked
uv run black --check src tests scripts
uv run ruff check src tests scripts
uv run python scripts/check_repo.py
PYTHONWARNINGS=error uv run coverage run --branch --source=abstract_sift -m unittest discover -s tests -v
uv run coverage report --fail-under=95
uv run python scripts/check_release.py
uv build
uv run python scripts/check_artifacts.py
```

All automated checks use synthetic fixtures and mocked HTTP/model responses. Never add conference content, API keys, `.env`, local state, or generated HTML exports to the repository; `scripts/check_repo.py` fails CI if tracked files include private paths, OpenAI-style keys or files over 1 MB. CI also audits the locked dependencies with pip-audit on every push and weekly, and Dependabot proposes action and dependency updates. Do not use real provider credentials in CI. Testing a live provider is a separate, explicitly costed smoke test.

Use `uv run black src tests scripts` to format Python changes. Add regression coverage for meaningful behavioral changes, especially request accounting, retries, concurrency, resume, score pairing, and export safety. Keep scoring evidence and criteria immutable within a run. Missing or refused answers must not become negative scores. Preserve integer cost arithmetic and distinguish usage-derived costs from unknown exposure.

HTML templates live in `src/abstract_sift/web/`. The standalone smoke check uses the packaged templates and opens the generated app in a simulated DOM without network access. It does not replace visual/accessibility checks in a real browser. A generated file contains all exported abstract text and is not protected by ChatGPT workspace authentication.

Use `docs/CLI.md` for implemented commands; `docs/PLAN.md` is historical design intent, not a claim that every feature is shipped. Update documentation when CLI behavior or output changes. Site publication is separate from releasing this CLI.

Before a public release, retain the MIT license notice, inspect both wheel and source archives, and run the installed-wheel smoke check documented in CI. Do not publish release artifacts until these checks pass.
