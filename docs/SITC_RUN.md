# Screen the SITC 2026 abstracts

The [SITC 2026 release](https://github.com/ValiusSciences/abstract-sift/releases/tag/sitc2026-corpus-v1) contains **1,127 listing records**, including **1,126 with full text**, **19 late-breaking abstracts**, and **one withdrawn entry**. It also includes saved two-provider scores and an offline explorer, so you can review the published results without API calls.

## What the bundle contains

| Asset | Purpose |
| --- | --- |
| `sitc2026-abstracts.jsonl.gz` | Import-ready corpus with string fields `id`, `title`, `authors`, `full_text`, `link` |
| `sitc2026-compilation.csv.gz` | Original 22-field compilation, including categories, keywords, presenters, text and PDF provenance |
| `sitc2026-interest.txt` | Exact criteria used for the published scoring run |
| `sitc2026-scores.csv.gz`, `sitc2026-scores.jsonl.gz` | All 1,127 rows with full text, separate scores, labels, statuses, model IDs and evidence hashes |
| `sitc2026-explorer.html.gz` | Self-contained searchable explorer with scores and full texts |
| `scoring-summary.json` | Run settings, rubric, criteria hash, coverage, label counts, cache reuse and usage-derived costs |
| `manifest.json`, `SHA256SUMS` | Corpus provenance and release-file integrity checks |
| `SCORING_GUIDE.md` | This walkthrough, bundled with the release |

No credentials, SQLite databases, raw request logs or unrelated runs are published. Third-party abstracts retain their original rights; the software's MIT license does not license the corpus.

## 1. Download and verify

From the repository directory:

```bash
mkdir -p data/sitc2026
gh release download sitc2026-corpus-v1 --repo ValiusSciences/abstract-sift --dir data/sitc2026
(cd data/sitc2026 && shasum -a 256 -c SHA256SUMS)
gzip -dk data/sitc2026/sitc2026-abstracts.jsonl.gz
gzip -dk data/sitc2026/sitc2026-explorer.html.gz
open data/sitc2026/sitc2026-explorer.html
```

On Linux, use `xdg-open` instead of `open`. Downloading, checksum verification and using the saved explorer incur no model charges. To read the scored table, decompress `sitc2026-scores.csv.gz` in the same way.

## 2. Use the same scoring criteria

The release criteria are byte-for-byte identical to the repository's ESMO criteria on November 6, 2026. They seek **new human clinical data on ADCs, adoptive cell therapies, bispecifics or T-cell engagers in solid cancers, with explicit patient/tumor biomarkers**. They include negative clinical findings and exclude preclinical-only research, hematologic-only disease, reviews, trials in progress without patient results, unrelated modalities and absent biomarker evidence. Consult the complete criteria rather than relying on this summary.

For reproducibility, use the downloaded `data/sitc2026/sitc2026-interest.txt`, which is the immutable release snapshot. The repository also includes [the same initial SITC criteria](https://github.com/ValiusSciences/abstract-sift/blob/main/examples/sitc2026-interest.txt); later repository edits do not change the release.

The published run used the existing `relevance-v1` rubric and the scorer's configured models: OpenAI Decisions `gpt-6-luna` and TypeSafe `jev-1.14.0`. Requested and returned model IDs are recorded. No SITC-specific scoring logic or threshold changes were introduced.

Scores remain separate:

- At or above **0.7**: relevant.
- At or below **0.3**: not relevant.
- Between those thresholds: review.
- Exclude from the retained view only if **both** selected providers say not relevant.
- Missing or failed results remain visible for review; they are not negative judgments.

Scores are not calibrated clinical probabilities, and provider agreement is not accuracy.

## 3. Set up and import

```bash
uv sync --locked
uv run abstract-sift import data/sitc2026/sitc2026-abstracts.jsonl --corpus sitc2026
uv run abstract-sift estimate --corpus sitc2026 \
  --query-file data/sitc2026/sitc2026-interest.txt --provider both --batch-size 32
```

Expect **1,127 records, 1,126 usable texts, one missing text, and zero oversized texts**. Abstract `1066` is withdrawn. Its blank source title is labeled `Withdrawn abstract 1066` to satisfy the importer, while its full text remains empty.

Before scoring, set `OPENAI_API_KEY` and `JEV_API_KEY` (or `TYPESAFE_API_KEY`) in a local `.env`. Both providers are required for this workflow. Scoring sends the criteria, IDs, titles and full text to each selected provider. Do not commit your keys.

The published preflight estimate was $0.7522 combined, using the application's saved pricing snapshot. Estimates exclude retries and unknown billing modifiers. Re-run the estimate for your environment.

## 4. Run a pilot, then score the full corpus

```bash
uv run abstract-sift score --corpus sitc2026 \
  --query-file data/sitc2026/sitc2026-interest.txt --provider both \
  --limit 50 --concurrency 4 --batch-size 32 --rpm 600 --tpm 10000000 \
  --max-cost-usd 0.25
uv run abstract-sift results PILOT_RUN_ID --sort openai --top 25
uv run abstract-sift compare PILOT_RUN_ID
```

Use the printed pilot ID. The first 50 records are a sequential smoke test, not a representative accuracy study. Inspect source evidence and disagreements before proceeding.

```bash
uv run abstract-sift score --corpus sitc2026 \
  --query-file data/sitc2026/sitc2026-interest.txt --provider both \
  --concurrency 16 --batch-size 32 --rpm 600 --tpm 10000000 \
  --max-cost-usd 2
```

Use those throughput settings only with matching provider quotas; otherwise lower them. The $2 dispatch allowance is split equally between providers and is an application guard, not a provider-enforced billing cap. Matching pilot results can be reused from the local cache. Omitting `--limit` selects the entire corpus.

Replace `RUN_ID` below with your **full run's printed ID**. The release's recorded run ID exists in the publisher's database, not in a fresh installation; downloading scores does not import a run.

## 5. Verify coverage and review candidates

```bash
uv run abstract-sift status RUN_ID
uv run abstract-sift cost RUN_ID
uv run abstract-sift compare RUN_ID
uv run abstract-sift results RUN_ID --view retained --sort openai --top 25
uv run abstract-sift results RUN_ID --view discordant --sort gap
uv run abstract-sift results RUN_ID --view uncertainty
uv run abstract-sift show RUN_ID 1193
```

Expect **1,126 successful scores and one `missing_text` record per provider**, with 1,126 paired scores. Do not accept a completed run without checking these counts.

The November 6 release run completed with no failures or oversized texts. Of the 1,126 scored abstracts, 29 were relevant to both providers, 1,063 were not relevant to both, and 63 were retained for review by at least one provider. Two had opposite relevant/not-relevant labels. The retained view also keeps the withdrawn record visible, making 64 rows including that unavailable entry.

The measured usage-derived cost was **$0.008173358 for the pilot** and **$0.187038008 for new requests in the full run**, or **$0.195211366 combined**. The full run reused 50 pilot results per provider. These are estimates from reported usage and saved pricing, not invoices or guarantees for another run. Re-scoring may change outputs even with the same criteria.

## 6. Recover and export

If interrupted, resume the same run so completed scores are preserved:

```bash
uv run abstract-sift resume RUN_ID --max-additional-cost-usd 1
uv run abstract-sift export RUN_ID --format csv --include-text --output exports/sitc2026-scores.csv
uv run abstract-sift export RUN_ID --format jsonl --include-text --output exports/sitc2026-scores.jsonl
uv run abstract-sift site RUN_ID --output exports/sitc2026.html --title "SITC 2026 Abstract Explorer"
```

The additional allowance permits new spending. Refusals, missing text and oversized records require review rather than automatic retry. Use `--force` only when intentionally replacing an existing HTML export.

## Source coverage and text limitations

The listing was retrieved from [SITC's titles and publications page](https://www.sitcancer.org/2026/abstracts/titles-and-publications) on November 6, 2026. Individual publisher pages required browser verification, so text came from the official [regular supplement](https://info.bmj.com/view/733231857/) and [late-breaking supplement](https://info.bmj.com/view/638855727/).

All 1,126 extracted entries matched the printed abstract number, normalized title (at least 90% similarity) and DOI. The extraction removes repeated headers, footers and watermarks, joins lowercase line-end hyphenation and restores word spacing only when verified against a second layout extraction. References, affiliations and available figure/table text remain part of the scoring evidence. The PDF's abstracts 178 and 531 were absent from the listing snapshot and are not included.

PDF extraction can retain spacing and reading-order artifacts. Image-only chart data was not transcribed. Source PDF page references in the compilation are one-based physical pages. Its relative `Source PDF` and `Text File` paths refer to the original local extraction collection, which is not included in this release; use `Text Source URL` to reach the cited page online.

For additional options, see the [CLI reference](https://github.com/ValiusSciences/abstract-sift/blob/main/docs/CLI.md).
