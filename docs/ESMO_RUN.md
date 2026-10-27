# Run ESMO screening

Run commands from the `abstract-sift` directory. Download the versioned [ESMO corpus release](https://github.com/ValiusSciences/abstract-sift/releases/tag/esmo2026-corpus-v1). The corpus is a separate release asset, not part of Git history or the Python package. While this repository is private, downloading requires repository access and `gh auth login`.

```bash
mkdir -p data/esmo2026
gh release download esmo2026-corpus-v1 --repo ValiusSciences/abstract-sift --dir data/esmo2026
(cd data/esmo2026 && shasum -a 256 -c SHA256SUMS)
gzip -dk data/esmo2026/esmo2026-abstracts.jsonl.gz
```

The release includes the compressed JSONL, `esmo2026-interest.txt`, a provenance/coverage manifest, and SHA-256 checksums. The criteria also live in [examples/esmo2026-interest.txt](../examples/esmo2026-interest.txt). They are the actual research-interest text used for this workflow: new clinical data on ADCs, CAR-T therapies, bispecific antibodies and T-cell engagers in solid tumors with explicit biomarkers. Third-party abstracts retain their original rights; this release does not assign them a new license.

## Readiness and coverage

Validated on 2026-10-26:

- Both live providers scored the two fictional demo records successfully. Their combined reported-usage estimate was $0.000075776; the scoring invocation lasted about 1.45 seconds. This is an integration check, not an accuracy or corpus-throughput benchmark.
- The current ESMO import has 4,418 unique records, 4,284 with nonempty full text, and 134 missing full text. All 4,284 fit the app's conservative context checks with the demo query. Re-estimate with your actual query.
- The automated regression suite passes, including interruption/resume, budgets, cost accounting, missing results, paired metrics, exploration, and filtered exports.

The app is ready to attempt a full run of the available texts. It cannot score the 134 records without text. The archive's size does not by itself prove that every abstract on the conference website has been captured. A subsequent user-run benchmark scored all 4,284 available texts with both providers in 13.31 seconds ($0.8680 usage-derived cost) at concurrency 16, batch size 32, 600 RPM and 10 million TPM per provider. This does not establish another account’s quota or accuracy.

## 1. Choose the screening criteria

Use the shared `examples/esmo2026-interest.txt` to reproduce our screening criteria, or create your own private query file (`data/` is gitignored). Describe the disease, treatment or mechanism, population, study types, endpoints, and exclusions that matter. State whether negative results, preclinical work, or indirect evidence should count. The demo query in `examples/interest.txt` is only an example and must not silently become your research criteria.

Do not change this file midway through comparing runs. Each run snapshots its query. Revising criteria creates a new scoring task; exact caching only reuses matching criteria and evidence.

## 2. Import and estimate (no API calls)

```bash
uv sync
uv run abstract-sift import data/esmo2026/esmo2026-abstracts.jsonl --corpus esmo2026
uv run abstract-sift estimate --corpus esmo2026 --query-file examples/esmo2026-interest.txt --provider both
```

With the short demo query, the conservative byte-based estimates are $2.3481 for OpenAI and $0.9586 for JEV, about $3.31 combined before retries. These are not measured token counts or guaranteed billing caps. Your actual query and provider responses change usage. Both mode allocates half the dispatch allowance to each provider; a $5 allowance therefore provides $2.50 per provider, not a pooled $5. Downloading, importing and estimating do not make paid API calls.

## 3. Optional small real-data check

```bash
uv run abstract-sift score --corpus esmo2026 --query-file examples/esmo2026-interest.txt --provider both --limit 50 --max-cost-usd 0.25
```

This selects the first 50 imported records, not a representative random sample. Review the scores against your criteria, especially negatives and disagreements. Record the printed run ID. A full run with unchanged criteria can reuse exact successful scores from this pilot; cached scores retain their origin run. Pilot cost remains in the pilot's ledger, so use `cost --all` to see all spending.

## 4. Score all available abstracts

After reviewing the estimate, choose your allowance explicitly. This example allows $5 of estimated dispatch exposure:

```bash
uv run abstract-sift score --corpus esmo2026 --query-file examples/esmo2026-interest.txt --provider both --max-cost-usd 5
```

Omit `--limit` for full coverage. Defaults are four concurrent requests per provider, up to 120 requests/minute and 600,000 estimated input tokens/minute per provider, with two retries. Those are application controls, not verified account quotas. Reduce `--rpm`, `--tpm`, or `--concurrency` if your account needs lower limits. A concurrency increase alone does not increase quota.

The original byte-based throttle imposed roughly 40 minutes of local rate-limit delay. The updated engine releases excess token reservations as responses arrive and learns input-token estimates from usage reported by the same provider in this run, retaining 25% headroom. Subsequent batches can contain more abstracts. Dollar reservations remain byte-based. Actual speed still depends on API latency and account quotas; the user’s updated full-corpus benchmark took 13.31 seconds; other accounts and data can differ. Keep the machine awake and the terminal running.

The app prints a run ID before making requests. Keep it for all commands below. Replace `RUN_ID` literally with that value.

## 5. Monitor, explore, and export

In a second terminal, from the same app directory:

```bash
uv run abstract-sift runs
uv run abstract-sift status RUN_ID
uv run abstract-sift cost RUN_ID
uv run abstract-sift results RUN_ID --view retained --top 25 --page 1
uv run abstract-sift results RUN_ID --view discordant --sort gap
uv run abstract-sift results RUN_ID --contains "lung cancer" --sort jev
uv run abstract-sift show RUN_ID ABSTRACT_ID
uv run abstract-sift compare RUN_ID
uv run abstract-sift site RUN_ID --output exports/esmo2026.html
uv run abstract-sift export RUN_ID --include-text --output exports/esmo-all.csv
uv run abstract-sift export RUN_ID --view retained --include-text --output exports/esmo-retained.csv
uv run abstract-sift export RUN_ID --view discordant --sort gap --format tsv --output exports/esmo-disagreements.tsv
```

`compare` uses successful pairs only and reports coverage. Metrics during a running/partial job are provisional. Even completed-run metrics do not include missing texts. Agreement is not validation of relevance. Exporting while scoring produces a snapshot of the results available at that moment; export again at the end for the final table. The [CLI reference](CLI.md) explains every filter and export column.

## 6. Finish or recover

Check `status RUN_ID`, `cost RUN_ID`, and the paired count in `compare RUN_ID`. For this archive, the expected result with no scoring failures is 4,284 `ok` and 134 `missing_text` **per provider**, with 4,284 successful pairs. A run can be `complete` while containing `missing_text` records; this does not mean all 4,418 were scored.

If interrupted or stopped by its allowance:

```bash
uv run abstract-sift resume RUN_ID --max-additional-cost-usd 1
```

Resume uses the original criteria, settings, and data snapshot and skips completed results. Its allowance is additional, not a replacement for previous spending. Timeouts can leave unknown billed usage; the ledger preserves estimated exposure rather than treating these as free. Refused and oversized records remain flagged rather than being retried automatically. To speed up an existing run, stop it with Ctrl-C and wait for exit, then resume with `--concurrency 16 --batch-size 32`. You can also override `--rpm` and `--tpm` to match known account limits. Completed results remain in the same run; runtime settings are recorded per invocation. The additional allowance still applies.

For missing source texts, repair the input archive, re-import, and start a new run. Re-importing does not modify an existing run's snapshot. Unchanged records can reuse exact cached results.

An authentication error (`http_401`/`http_403`) requires fixing the relevant key or account access before resume. A quota/payment issue (`http_402`) needs account attention. Repeated `http_429` errors indicate rate pressure; stop and resume with lower `--rpm` or `--tpm`. A `batch_exceeds_configured_tpm` error requires a larger TPM allowance or smaller batch size. Never interpret any of these as a negative relevance judgment.
