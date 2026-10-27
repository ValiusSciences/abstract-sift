# Abstract Sift

A local CLI for screening research abstracts against a research-interest text with **OpenAI Decisions**, **TypeSafe JEV**, or both. Both mode preserves independent scores and reports agreement and disagreement.

Version 0.1 implements concurrent, resumable scoring, per-request cost accounting, CSV/JSONL exports, and comparison metrics. Both live API integrations passed a two-abstract smoke test; a full ESMO run subsequently completed in 13.31 seconds of scoring time (15.27 seconds wall time) on the user’s account. Treat this as an initial beta, not a guarantee of throughput or screening accuracy. Python 3.11–3.14 on macOS/Linux is the test target; use WSL on Windows.

For detailed usage, see the [CLI reference](docs/CLI.md) and [ESMO full-corpus run guide](docs/ESMO_RUN.md), including coverage checks, budget examples, monitoring, and recovery.

## Terminal output and progress

Commands default to readable tables. Add `--format json` (or `--json`) to retain the complete machine-readable schema. `--output-format table|json` is also available on every command. `show` includes readable full text after its score table.

```bash
uv run abstract-sift status RUN_ID
uv run abstract-sift cost RUN_ID --format json
uv run abstract-sift compare-runs BEFORE_RUN_ID AFTER_RUN_ID --format table
uv run abstract-sift compare-runs BEFORE_RUN_ID AFTER_RUN_ID --format json > comparison.json
```

Scoring and resume display one progress bar per selected provider on stderr, updating in place at most four times per second. Bars count successful scores (including local cache reuse) against records with text; missing text and failures are shown separately. A partial run does not falsely show 100% successful scoring. In redirected/nonterminal output, auto mode prints only the final provider snapshot. Use `--progress never` to suppress it, or `--progress always` to force terminal animation. Progress never contaminates JSON on stdout. Engine batch-completion messages and the large preflight JSON dump are no longer printed during scoring; `estimate` remains available separately.

For `export`, `--format csv|tsv|jsonl` still selects the **file format**. Use `--output-format json` or `--json` for the export confirmation on stdout. Summary tables prioritize key fields; JSON includes the full details and original numeric precision.

## Quick start

From this directory, with [uv](https://docs.astral.sh/uv/) installed:

```bash
uv sync
uv run abstract-sift import examples/abstracts.jsonl --corpus demo
uv run abstract-sift estimate --corpus demo --query-file examples/interest.txt --provider both
uv run abstract-sift score --corpus demo --query-file examples/interest.txt --provider both --max-cost-usd 0.05
```

Store `OPENAI_API_KEY` and `TYPESAFE_API_KEY` (or `JEV_API_KEY`) in `.env` here or in your environment. Existing environment values take precedence. The application reads literal values without executing shell expressions. Keys are never saved in the run database or reports. Do not commit `.env`. Scoring sends the research interest, abstract IDs, titles, and full texts to each selected provider.

On macOS, double-click **Run Demo.command** to install dependencies and score the two fictional abstracts with both providers, using a $0.05 dispatch budget. It reads your existing `.env`. It does not start the conference corpus.

## Your corpus

Import CSV or JSONL with string fields `id`, `title`, `authors`, `full_text`, `link`. IDs must be unique. Extra fields are ignored. Empty full texts remain visible as `missing_text`; oversized texts are flagged, never silently truncated.

```bash
uv run abstract-sift import /path/to/abstracts.jsonl --corpus conference
# Write your inclusion/exclusion criteria in interest.txt.
uv run abstract-sift estimate --corpus conference --query-file interest.txt --provider both
uv run abstract-sift score --corpus conference --query-file interest.txt --provider both --max-cost-usd 5
```

Choose `--provider openai`, `jev`, or `both`. All eligible records are scored unless you explicitly set `--limit`. `--batch-size` defaults to 16; conservative context limits may split batches further. `--concurrency 4` is per provider. Adjust `--rpm` and `--tpm` to your account limits; token throttling starts with conservative byte estimates, then reconciles to reported input usage and adapts future estimates with 25% headroom. Batching adapts to the same observed usage; per-question size checks remain conservative. This is empirical estimation, not an exact tokenizer. Instantaneous scoring of thousands of abstracts is not guaranteed. `search` provides an immediate local lexical preview, not model relevance scores.

A run ID is printed before dispatch. Use it to inspect or resume:

```bash
uv run abstract-sift status RUN_ID
uv run abstract-sift results RUN_ID --view retained
uv run abstract-sift results RUN_ID --view discordant --sort gap
uv run abstract-sift compare RUN_ID
uv run abstract-sift cost RUN_ID
uv run abstract-sift export RUN_ID --format csv --output exports/results.csv
uv run abstract-sift resume RUN_ID --max-additional-cost-usd 1
uv run abstract-sift cost --all
```

To accelerate an existing run, press Ctrl-C, wait for it to exit, then use `resume RUN_ID --max-additional-cost-usd 1 --concurrency 16 --batch-size 32`. The allowance is additional spending exposure; choose it deliberately. Resume also accepts `--rpm` and `--tpm` for known account limits. Each invocation records its runtime settings, while the query, evidence, models, and scoring rubric remain unchanged.

Ctrl-C preserves completed results and attempts. Resume retries unfinished failures, keeping successful results. Refusals, missing texts, and oversized records require review rather than automatic retry. Exact successful results can be reused across runs with the same evidence, research interest, requested model, and rubric. Returned model IDs are retained; caching requires a matching pinned model ID.

## Explore and export results

`results` now defaults to a readable terminal table. Add `--json` for the original machine-readable array. Exploration is offline and incurs no model charges.

```bash
uv run abstract-sift runs
uv run abstract-sift results RUN_ID --top 25 --page 1
uv run abstract-sift results RUN_ID --top 25 --page 2
uv run abstract-sift results RUN_ID --contains "lung cancer" --sort jev
uv run abstract-sift results RUN_ID --view discordant --sort gap
uv run abstract-sift results RUN_ID --view uncertainty
uv run abstract-sift results RUN_ID --status failed
uv run abstract-sift show RUN_ID ABSTRACT_ID
```

`show` displays the title, authors, source link, both scores/statuses, and complete abstract text. Text search matches a case-insensitive substring across the original record. Score sorting defaults high to low; use `--ascending` for low to high. `--sort id` and `--sort title` use alphabetical order. Missing scores stay last. `--view retained` includes all records except those labeled not relevant by every selected provider. `discordant` means opposite relevant/not-relevant labels; `uncertainty` covers differing labels involving review.

Export a spreadsheet-compatible table with scores, labels, statuses, errors, model IDs, evidence hashes, links, and comparison columns:

```bash
uv run abstract-sift export RUN_ID --format csv --include-text --output exports/results.csv
uv run abstract-sift export RUN_ID --format tsv --view discordant --sort gap --output exports/disagreements.tsv
uv run abstract-sift export RUN_ID --format jsonl --view retained --output exports/retained.jsonl
```

Exports accept the same `--view`, `--contains`, `--status`, `--sort`, `--ascending`, `--low`, and `--high` settings as results. They contain **all matching rows**, irrespective of terminal pagination. `--include-text` includes the complete abstract text. Empty selections produce a table with headers. CSV/TSV text that could execute as a spreadsheet formula is escaped; JSONL preserves original text. Terminal scores are rounded to three decimals; exports retain full numeric precision.

## Repeat a live speed test

A completed run does no work on resume, and an identical new run normally reuses cached scores. Add `score --no-cache` to force new API evaluations and measure live throughput. It creates a new run and incurs new costs; the old run remains available. Resuming that new run still skips its own completed results.

The first full ESMO run took 47 minutes 27.5 seconds, with approximately 6.3 million reported input tokens per provider. At 600,000 tokens/minute, even accurate accounting implies roughly ten minutes of token throughput. Under a minute requires substantially higher provider quotas and low enough request latency; it is not guaranteed by the concurrency setting.

For an account whose quotas allow the following ceilings, a fresh benchmark command is:

```bash
time uv run abstract-sift score --corpus esmo2026 --query-file data/interest.txt \
  --provider both --no-cache --concurrency 16 --batch-size 32 \
  --rpm 600 --tpm 10000000 --max-cost-usd 5
```

These are application ceilings per provider, not evidence of available account quotas. Match them to your accounts' limits, including per-second limits where applicable. Watch for `http_429` responses; retries can dominate elapsed time when the service throttles requests. A rolling per-minute limiter can burst and does not enforce a provider's separate per-second quota. Record the new run ID and inspect `status`, `cost`, and coverage after completion. `--no-cache` bypasses this application's saved scores, not any provider-side caching. This benchmark's higher limits do not change the dollar allowance or scoring criteria.

## Compare screening stability across runs

```bash
uv run abstract-sift compare-runs BEFORE_RUN_ID AFTER_RUN_ID
# Save a full report with up to 50 largest score changes:
uv run abstract-sift compare-runs BEFORE_RUN_ID AFTER_RUN_ID --top 50 --format json > comparison.json
```

This is distinct from `compare RUN_ID`, which compares OpenAI with JEV within a run. `compare-runs` compares each provider with itself across two runs and reports label agreement, score changes, rank correlation, transition matrices, and IDs newly excluded or retained. Inspect `retained.newly_excluded` first for candidates that the faster run dropped. Use `show` with either run ID to review the source and scores. Matching query, evidence, rubric and provider/model configuration are required; incomplete or changed-returned-model pairs are explicitly excluded. Cached reuse is counted so it does not masquerade as independent stability evidence.

Keep thresholds identical. Missing texts are excluded from retained-set stability metrics. Differences cannot be attributed to batch size alone without controlled repeated runs; a stable result does not establish accuracy.

## Interpretation and costs

Defaults label scores at or above 0.7 relevant, at or below 0.3 not relevant, and the middle review. Only records judged not relevant by every selected provider are excluded from the retained view. Failed/missing results remain for review. Scores are not calibrated clinical probabilities. Agreement is not correctness.

Comparison uses only successful paired records from the same run and includes a three-way label matrix, binary agreement, Cohen's kappa, positive/negative agreement, Spearman rank correlation, top-k overlap, and raw score gaps. Mixed returned model builds are rejected for comparison. Scores are never averaged. Binary comparison defaults to 0.5 independently of review thresholds. Undefined metrics are null.

Costs use reported input usage and versioned pricing snapshots, in USD, with integer arithmetic. They are **usage-derived estimates, not invoices**. Retries have separate ledger entries; timeouts or absent usage retain an unreconciled exposure estimate. Cached local results incur no new request cost. Every resume has an additional allowance, and cumulative costs remain visible.

The dispatch budget reserves a conservative byte-based token estimate before each request. Both mode splits the allowance equally; optional `--openai-budget-usd` and `--jev-budget-usd` can reduce those shares. Unused shares are not transferred. This is an application guard, not a provider-enforced billing cap: pricing changes or unexpected billed usage can exceed estimates. OpenAI prompt caching is disabled in this release to avoid unpriced cache writes. Review the [API notes](docs/API_NOTES.md) before large runs.

## Local state and development

Default state: `~/.local/share/abstract-sift`, including SQLite snapshots and `runs/RUN_ID/{run-summary.json,cost-summary.json,request-usage.jsonl}`. Use global `--data-dir PATH` and `--env-file PATH` **before** the subcommand to override. Imported abstracts and queries stay in this private local state; exporting is explicit. Exit codes: 0 complete, 2 partial, 130 canceled, 1 configuration/error. A complete run may still contain missing-text records; always inspect counts.

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the complete test, coverage, offline HTML, and package-validation commands.

Tests use fictional abstracts and mock transports; no keys or paid calls are required. The earlier [plan](docs/PLAN.md), [comparison specification](docs/COMPARISON.md), and [cost design](docs/COST_TRACKING.md) include future work beyond this release. No browser UI, OAuth, benchmark claims, settled-invoice reconciliation, or automatic threshold calibration is included.

This folder is portable and independent of conference downloader scripts. Conference content and credentials are excluded from version control. A code license has not yet been selected; select one before publishing as open source. A code license does not grant redistribution rights to imported abstracts.

## Generate the explorer as a local HTML file

```bash
# From this repository:
uv run abstract-sift site RUN_ID --output exports/explorer.html
# Or from its parent folder:
uv run --project abstract-sift abstract-sift site RUN_ID --output abstract-sift/exports/explorer.html
```

Open the generated HTML directly in a browser. It is one self-contained file with the same purple Valius Sciences interface as the ChatGPT Site: all abstracts, percentage score bars, search and score filters, sticky table headers, scatter tab, CSV export, and full-text modals with expandable author/affiliation details. It needs no server, internet, API keys, or paid model calls. Source links still require internet when clicked.

The generator takes a coherent snapshot of the selected run, includes every record and its full text, and retains missing/failed/not-selected statuses. A running run exports its current progress, not future results. Generate a new file to refresh it. Single-provider runs show the other provider as not selected and have no paired scatter points.

`--title`, `--brand`, and `--description` customize the heading, organization name, and introduction. Defaults use the corpus name and saved research-interest text, so another run never silently inherits the ESMO demo criteria. `--force` permits overwriting an existing HTML file; otherwise the command refuses to overwrite. Global `--data-dir` selects another local database. Use `--format json` for the generation report in scripts.

A local file does **not** inherit ChatGPT workspace authentication. The access badge says “Local snapshot”; anyone given the file can read the embedded abstracts. Only this run's content is embedded—no credentials, request logs, or unrelated runs. The ESMO snapshot is approximately 23 MB.

UI assets are packaged under `src/abstract_sift/web/`, based on hosted Site source commit `2af81de753a9fccbe7dfd97abdd584086a85513b`. The local generator adapts data loading and local-file history handling without changing scoring. It does not require the original Sites project folder or publishing credentials. After intentional hosted UI changes, copy the five UI assets (index.html, style.css, app.js, format.js, scatter.js) into that directory and rerun the standalone checks before releasing.

```bash
node tests/check_site.cjs exports/explorer.html
```
