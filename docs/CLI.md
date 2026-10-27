# CLI reference

Global options go before the subcommand. Output options go after it. Tables are the default.

## Global options

```text
usage: - [-h] [--data-dir DATA_DIR] [--env-file ENV_FILE]
         {compare-runs,runs,show,import,search,estimate,score,resume,status,results,export,compare,cost} ...

Local abstract screening with OpenAI Decisions and TypeSafe JEV.

positional arguments:
  {compare-runs,runs,show,import,search,estimate,score,resume,status,results,export,compare,cost}

options:
  -h, --help            show this help message and exit
  --data-dir DATA_DIR
  --env-file ENV_FILE   Literal key file; default .env in the current
                        directory
```

## compare-runs

```text
usage: - compare-runs [-h] [--low LOW] [--high HIGH] [--top TOP]
                      [--format {table,json} | --json]
                      before after

positional arguments:
  before
  after

options:
  -h, --help            show this help message and exit
  --low LOW
  --high HIGH
  --top TOP             Number of largest score changes to display
  --format, --output-format {table,json}
                        Terminal output format (default: table)
  --json                Alias for JSON terminal output
```

## runs

```text
usage: - runs [-h] [--format {table,json} | --json]

options:
  -h, --help            show this help message and exit
  --format, --output-format {table,json}
                        Terminal output format (default: table)
  --json                Alias for JSON terminal output
```

## show

```text
usage: - show [-h] [--format {table,json} | --json] run id

positional arguments:
  run
  id

options:
  -h, --help            show this help message and exit
  --format, --output-format {table,json}
                        Terminal output format (default: table)
  --json                Alias for JSON terminal output
```

## import

```text
usage: - import [-h] --corpus CORPUS [--format {table,json} | --json] path

positional arguments:
  path

options:
  -h, --help            show this help message and exit
  --corpus CORPUS
  --format, --output-format {table,json}
                        Terminal output format (default: table)
  --json                Alias for JSON terminal output
```

## search

```text
usage: - search [-h] --corpus CORPUS --query-file QUERY_FILE [--top TOP]
                [--format {table,json} | --json]

options:
  -h, --help            show this help message and exit
  --corpus CORPUS
  --query-file QUERY_FILE
  --top TOP
  --format, --output-format {table,json}
                        Terminal output format (default: table)
  --json                Alias for JSON terminal output
```

## estimate

```text
usage: - estimate [-h] --corpus CORPUS --query-file QUERY_FILE
                  --provider {openai,jev,both} [--batch-size BATCH_SIZE]
                  [--limit LIMIT] [--format {table,json} | --json]

options:
  -h, --help            show this help message and exit
  --corpus CORPUS
  --query-file QUERY_FILE
  --provider {openai,jev,both}
  --batch-size BATCH_SIZE
  --limit LIMIT         Optional explicit subset; 0 means all
  --format, --output-format {table,json}
                        Terminal output format (default: table)
  --json                Alias for JSON terminal output
```

## score

```text
usage: - score [-h] --corpus CORPUS --query-file QUERY_FILE
               --provider {openai,jev,both} [--batch-size BATCH_SIZE]
               [--limit LIMIT] --max-cost-usd MAX_COST_USD
               [--concurrency CONCURRENCY] [--rpm RPM] [--tpm TPM]
               [--retries RETRIES] [--openai-budget-usd OPENAI_BUDGET_USD]
               [--jev-budget-usd JEV_BUDGET_USD] [--no-cache]
               [--format {table,json} | --json]
               [--progress {auto,always,never}]

options:
  -h, --help            show this help message and exit
  --corpus CORPUS
  --query-file QUERY_FILE
  --provider {openai,jev,both}
  --batch-size BATCH_SIZE
  --limit LIMIT         Optional explicit subset; 0 means all
  --max-cost-usd MAX_COST_USD
  --concurrency CONCURRENCY
                        Concurrent requests per provider, 1–16
  --rpm RPM             Conservative request budget per minute per provider
  --tpm TPM             Conservative token budget per minute per provider
  --retries RETRIES
  --openai-budget-usd OPENAI_BUDGET_USD
  --jev-budget-usd JEV_BUDGET_USD
  --no-cache            Score every eligible item again; bypass local score
                        reuse (incurs new API costs)
  --format, --output-format {table,json}
                        Terminal output format (default: table)
  --json                Alias for JSON terminal output
  --progress {auto,always,never}
                        Progress on stderr; auto animates only in a terminal
```

## resume

```text
usage: - resume [-h] --max-additional-cost-usd MAX_ADDITIONAL_COST_USD
                [--concurrency CONCURRENCY] [--batch-size BATCH_SIZE]
                [--rpm RPM] [--tpm TPM] [--format {table,json} | --json]
                [--progress {auto,always,never}]
                run

positional arguments:
  run

options:
  -h, --help            show this help message and exit
  --max-additional-cost-usd MAX_ADDITIONAL_COST_USD
  --concurrency CONCURRENCY
  --batch-size BATCH_SIZE
  --rpm RPM
  --tpm TPM
  --format, --output-format {table,json}
                        Terminal output format (default: table)
  --json                Alias for JSON terminal output
  --progress {auto,always,never}
                        Progress on stderr; auto animates only in a terminal
```

## status

```text
usage: - status [-h] [--format {table,json} | --json] run

positional arguments:
  run

options:
  -h, --help            show this help message and exit
  --format, --output-format {table,json}
                        Terminal output format (default: table)
  --json                Alias for JSON terminal output
```

## results

```text
usage: - results [-h] [--low LOW] [--high HIGH]
                 [--view {all,retained,discordant,uncertainty,incomplete_pair,both_relevant,both_not_relevant,both_review}]
                 [--sort {openai,jev,gap,id,title}] [--ascending]
                 [--contains CONTAINS]
                 [--status {ok,queued,failed,missing_text,oversized,refused}]
                 [--include-text] [--top TOP] [--page PAGE]
                 [--format {table,json} | --json]
                 run

positional arguments:
  run

options:
  -h, --help            show this help message and exit
  --low LOW
  --high HIGH
  --view {all,retained,discordant,uncertainty,incomplete_pair,both_relevant,both_not_relevant,both_review}
  --sort {openai,jev,gap,id,title}
  --ascending           Sort scores low to high (text defaults A–Z)
  --contains CONTAINS   Case-insensitive substring in ID, title, authors, full
                        text or link
  --status {ok,queued,failed,missing_text,oversized,refused}
                        Match this status in any selected provider
  --include-text        Include full abstract text in JSON or exported table
  --top TOP             Rows per page
  --page PAGE
  --format, --output-format {table,json}
                        Terminal output format (default: table)
  --json                Alias for JSON terminal output
```

## export

```text
usage: - export [-h] [--low LOW] [--high HIGH]
                [--view {all,retained,discordant,uncertainty,incomplete_pair,both_relevant,both_not_relevant,both_review}]
                [--sort {openai,jev,gap,id,title}] [--ascending]
                [--contains CONTAINS]
                [--status {ok,queued,failed,missing_text,oversized,refused}]
                [--include-text] [--format {csv,tsv,jsonl}] --output OUTPUT
                [--output-format {table,json} | --json]
                run

positional arguments:
  run

options:
  -h, --help            show this help message and exit
  --low LOW
  --high HIGH
  --view {all,retained,discordant,uncertainty,incomplete_pair,both_relevant,both_not_relevant,both_review}
  --sort {openai,jev,gap,id,title}
  --ascending           Sort scores low to high (text defaults A–Z)
  --contains CONTAINS   Case-insensitive substring in ID, title, authors, full
                        text or link
  --status {ok,queued,failed,missing_text,oversized,refused}
                        Match this status in any selected provider
  --include-text        Include full abstract text in JSON or exported table
  --format {csv,tsv,jsonl}
  --output OUTPUT
  --output-format {table,json}
                        Terminal output format (default: table)
  --json                Alias for JSON terminal output
```

## compare

```text
usage: - compare [-h] [--low LOW] [--high HIGH] [--threshold THRESHOLD]
                 [--format {table,json} | --json]
                 run

positional arguments:
  run

options:
  -h, --help            show this help message and exit
  --low LOW
  --high HIGH
  --threshold THRESHOLD
  --format, --output-format {table,json}
                        Terminal output format (default: table)
  --json                Alias for JSON terminal output
```

## cost

```text
usage: - cost [-h] [--all] [--format {table,json} | --json] [run]

positional arguments:
  run

options:
  -h, --help            show this help message and exit
  --all
  --format, --output-format {table,json}
                        Terminal output format (default: table)
  --json                Alias for JSON terminal output
```

## Selection and output behavior

- `runs` lists saved runs, newest first. `results` defaults to a terminal table; `show` displays one complete abstract. Every command defaults to readable output; use `--format json` or `--json` for machine-readable output. For export, use `--output-format json` because `--format` selects the file format.
- `results --top 25 --page 2` shows matches 26–50 **after** filtering and sorting. Export uses all matching rows, with no page limit.
- `--contains` is one case-insensitive substring, not a semantic search or Boolean query. It searches ID, title, authors, full text, and link.
- `--status failed` matches a failure from either selected provider. It does not treat missing text or queued work as a failed request.
- `--sort` defaults to the first selected provider. Scores and gaps sort descending; `--ascending` reverses numeric order. IDs and titles sort alphabetically. Missing scores sort last and tied scores use abstract ID.
- `--view retained` keeps a record unless every selected provider labels it not relevant. It includes incomplete pairs. `discordant` means opposite relevant/not-relevant labels; `uncertainty` means differing labels with one in review. `incomplete_pair` means at least one provider has no valid score.
- `both_relevant`, `both_review`, and `both_not_relevant` are exact paired label filters. Pair-specific views are intended for both-provider runs.
- `--low` and `--high` change displayed/exported labels without new API calls. Specify the same values for results, export, and compare. `show` uses the default 0.3/0.7 labels. `compare --threshold` independently controls its binary metrics.
- `--include-text` adds the full abstract to JSON results or exports; terminal tables remain compact. Use `show` to read text in the terminal.
- CSV/TSV are spreadsheet-compatible text tables, not `.xlsx` workbooks. Numeric probabilities retain precision; text is quoted and formula-like strings are escaped. JSONL preserves source text.
- Run `cost RUN_ID` for cumulative usage-derived cost and unknown exposure, or `cost --all` for every run. These are estimates, not settled invoices.
- Exploration and export do not call either model. Use a second terminal to inspect a running job; individual batches become visible as they finish.

## Export column guide

| Column | Meaning |
| --- | --- |
| `id`, `title`, `authors`, `link` | Original abstract metadata |
| `evidence_hash` | SHA-256 fingerprint of the imported five-field record |
| `openai_probability`, `jev_probability` | Raw relevance score, blank if unavailable |
| `*_status` | `ok`, `queued`, `failed`, `missing_text`, `oversized`, or `refused` |
| `*_error` | Sanitized failure reason, when available |
| `*_model` | Model ID returned by the service |
| `*_cache_origin` | Prior run that supplied a reused score, otherwise empty |
| `*_label` | Relevant, review, or not relevant at the selected thresholds; blank without a valid score |
| `retain_for_review` | False only if every selected provider labels the record not relevant |
| `comparison_bucket` | Paired label relationship, incomplete pair, or single-provider result |
| `probability_gap` | Absolute difference between successful provider scores; not a calibrated uncertainty measure |
| `full_text` | Present only with `--include-text` |

Only selected providers have columns. Keep the run ID, query, and run reports alongside exported tables for provenance.


## Progress and scripting

`score` and `resume` use one stderr progress bar per provider. Auto mode animates only in terminals; redirected output gets a final snapshot, not per-batch messages. Use `--progress never` for no progress output. Use `--format json` to keep stdout machine-readable. Resume can override concurrency, batch size, RPM, and TPM; stop the active process first.

`compare-runs` requires matching screening criteria and evidence. Its default table highlights label stability, retention changes, and the largest score differences. Use `--format json` for full transition matrices and metrics. Both modes are offline.

## site

```text
usage: - site [-h] --output OUTPUT [--title TITLE] [--brand BRAND]
              [--description DESCRIPTION] [--force] [--format {table,json} |
              --json]
              run

positional arguments:
  run

options:
  -h, --help            show this help message and exit
  --output OUTPUT
  --title TITLE
  --brand BRAND
  --description DESCRIPTION
  --force               Replace an existing HTML output
  --format, --output-format {table,json}
                        Terminal output format (default: table)
  --json                Alias for JSON terminal output
```

Creates one self-contained HTML explorer from a coherent snapshot of RUN_ID. Open the file directly in a browser; no server or API calls are needed. Every record and full abstract text is included. The UI matches the hosted explorer, with the saved run criteria and a local-file access badge. Defaults derive the title from the corpus and the introduction from the research-interest text. Existing outputs require `--force` to replace. Files do not inherit ChatGPT workspace restrictions. See the README for examples and packaging details.
