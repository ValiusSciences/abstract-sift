# Screen the ESMO 2026 abstracts

Run these commands from the repository directory after `uv sync`. Put your `OPENAI_API_KEY` and `TYPESAFE_API_KEY` (or `JEV_API_KEY`) in `.env`.

The shared [research criteria](../examples/esmo2026-interest.txt) look for new clinical data on ADCs, adoptive cell therapies (including CAR-T, TCR-T, NK, gamma-delta T cells and TILs), bispecifics and T-cell engagers in solid cancers with explicit biomarkers. Use the current criteria file from the repository; the release's bundled interest file records the criteria at release time.

## 1. Import the corpus

Download the [corpus release](https://github.com/ValiusSciences/abstract-sift/releases/tag/esmo2026-corpus-v2), verify it, and import it. While the repository is private, `gh auth login` and repository access are required.

```bash
mkdir -p data/esmo2026
gh release download esmo2026-corpus-v2 --repo ValiusSciences/abstract-sift --dir data/esmo2026
(cd data/esmo2026 && shasum -a 256 -c SHA256SUMS)
gzip -dk data/esmo2026/esmo2026-abstracts.jsonl.gz
uv run abstract-sift import data/esmo2026/esmo2026-abstracts.jsonl --corpus esmo2026
```

Expected: **4,418 records**, with **4,375 full texts** and **43 missing texts**. Download and import make no model API calls.

## 2. Small real-data check

Score the first 50 abstracts with both providers using a $0.25 dispatch allowance:

```bash
uv run abstract-sift score --corpus esmo2026 \
  --query-file examples/esmo2026-interest.txt --provider both \
  --limit 50 --max-cost-usd 0.25
uv run abstract-sift results PILOT_RUN_ID --sort openai --top 25
```

Replace `PILOT_RUN_ID` with the printed run ID. Review the results before continuing; these first 50 records are not a random sample.

## 3. Full run

```bash
uv run abstract-sift score --corpus esmo2026 \
  --query-file examples/esmo2026-interest.txt --provider both \
  --concurrency 16 --batch-size 32 --rpm 600 --tpm 10000000 \
  --max-cost-usd 5
```

These speed settings require matching provider quotas; lower them if needed. One full run took **13.31 seconds** and cost approximately **$0.87** in reported usage. Speed and cost vary. The $5 dispatch allowance is an application estimate, not a provider billing cap. Matching successful pilot scores can be reused automatically.

Use the **full run's printed ID** as `RUN_ID` below. With no scoring failures, expect 4,375 successful scores and 43 missing-text records per provider.

## 4. List the top 25 by OpenAI score

```bash
uv run abstract-sift results RUN_ID --sort openai --top 25
```

## 5. Create and open the HTML explorer

```bash
uv run abstract-sift site RUN_ID --output exports/esmo2026.html
open exports/esmo2026.html
```

`open` is for macOS; on Linux use `xdg-open exports/esmo2026.html`, or open the file directly in your browser. The self-contained page includes all abstracts, filters, score bars, a scatter plot and full-text details. Anyone given the file can read its contents.

See the [CLI reference](CLI.md) for filtering, exports, cost reports, comparisons and resume options.
