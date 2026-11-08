# ASH 2026 abstract bundle and scoring guide

This bundle contains **6,376 numbered submitted abstracts, all with full text**, from the official [ASH 2026 program](https://onlineprogram.hematology.org/). It includes 6,370 oral/poster abstracts plus six plenary abstracts. All 413 oral/poster sessions were paginated and reconciled; the remaining program categories were checked to find plenary coverage. Unnumbered invited presentations are excluded. Two decimal source IDs (`1155.1` and `4445.1`) are preserved exactly.

The [ASH abstract schedule](https://www.hematology.org/meetings/annual-meeting/abstracts) lists regular abstract availability on November 4, 2026 and late-breaking availability on December 7. **Late-breaking abstracts are not included yet.** This snapshot predates their scheduled December 7, 2026 availability.

## Inspect the saved results

Download the [ash2026-corpus-v1 release](https://github.com/ValiusSciences/abstract-sift/releases/tag/ash2026-corpus-v1). It includes the corpus, metadata, saved scores, criteria, offline explorer, provenance and checksums.

```bash
mkdir -p data/ash2026
gh release download ash2026-corpus-v1 --repo ValiusSciences/abstract-sift --dir data/ash2026
cd data/ash2026
shasum -a 256 -c SHA256SUMS
gzip -dk ash2026-explorer.html.gz
open ash2026-explorer.html
```

Use `xdg-open` on Linux. The offline explorer requires no model calls and has no workspace authentication. Share its content only with the intended audience. It contains saved scores and text; TRACE tags and persistent voting belong to the separate hosted review Site.

## Criteria and interpretation

The user explicitly chose the **existing solid-tumor criteria unchanged**, despite ASH's hematology focus. The exact `ash2026-interest.txt` snapshot seeks new human clinical results for ADCs, adoptive cell therapies, bispecific antibodies or T-cell engagers in solid cancers with explicit patient/tumor biomarkers. Hematologic-only studies remain excluded. Do not silently adapt the criteria to hematologic cancers.

The run used rubric `relevance-v1`, OpenAI Decisions `gpt-6-luna` and TypeSafe JEV `jev-1.14.0`. Scores stay separate. Relevant: >=0.7; not relevant: <=0.3; otherwise review. Missing or failed scores are not negative judgments. Scores are not calibrated clinical probabilities.

All 6,376 records were successfully scored by both providers. There is one both-relevant result, six opposite-label disagreements, eleven uncertainty cases, and 6,358 both-not-relevant results. **13 abstracts have either score strictly above 0.5.** These are model screening outcomes, not adjudicated clinical relevance; check source evidence, especially disagreements and hematologic-only candidates that a model may have rated too highly.

## Reproduce with abstract-sift

From the abstract-sift repository, point the commands at the decompressed bundle and its criteria:

```bash
gzip -dk /path/to/ash2026-corpus-v1/ash2026-abstracts.jsonl.gz
uv sync --locked
uv run abstract-sift import /path/to/ash2026-corpus-v1/ash2026-abstracts.jsonl --corpus ash2026
uv run abstract-sift estimate --corpus ash2026 --query-file /path/to/ash2026-corpus-v1/ash2026-interest.txt --provider both --batch-size 32
uv run abstract-sift score --corpus ash2026 --query-file /path/to/ash2026-corpus-v1/ash2026-interest.txt --provider both --limit 50 --max-cost-usd 0.25
uv run abstract-sift score --corpus ash2026 --query-file /path/to/ash2026-corpus-v1/ash2026-interest.txt --provider both --batch-size 32 --concurrency 16 --rpm 600 --tpm 10000000 --max-cost-usd 7 --openai-budget-usd 3.5 --jev-budget-usd 2
uv run abstract-sift status RUN_ID
uv run abstract-sift compare RUN_ID
uv run abstract-sift cost RUN_ID
uv run abstract-sift export RUN_ID --format csv --include-text --output ash2026-scores.csv
uv run abstract-sift site RUN_ID --output ash2026-explorer.html --title "ASH 2026 Abstract Explorer"
```

Configure both provider credentials locally before scoring. Use throughput settings compatible with your provider quotas. These are example application budgets, not provider-enforced billing caps. Resume an interrupted run using `resume RUN_ID --max-additional-cost-usd AMOUNT`, preserving completed scores.

The published-to-local-bundle run ID is `run_ea52fa427dba43b4`; pilot: `run_ecee02ef52b044c1`. These IDs belong to the originating local database, not a fresh installation. The pilot cost $0.009104272 and new requests in the full run cost $1.096087894, totaling **$1.105192166**, based on reported usage and saved pricing. The full run reused 50 pilot results per provider. Costs are estimates, not invoices; re-scoring can differ.

## Provenance and limitations

The corpus extracts the publisher's scientific `ABSTRACT` HTML block. Authors, affiliations, session information, session keywords and disclosures are retained separately in the compilation. The source HTML path and SHA-256 hash are included for audit, but source HTML files are not part of this compact bundle. Use each record's official link to inspect the original. Session keywords are session-level metadata, not necessarily abstract-specific. Image-only figures were not transcribed. Abstract rights remain with their original holders; the software license does not license this corpus.

The workspace contains reproducible collection, cross-program discovery, extraction, TRACE tagging, Site-build and bundle-packaging scripts. TRACE uses the same private November 6 catalog snapshot as SITC and ESMO. Tags identify mentions, not confirmed study interventions; uncertain aliases remain review candidates. No TRACE data or scientist votes are included in this public-safe evidence bundle.

For future conference preparation, see the [conference workflow playbook](CONFERENCE_WORKFLOW.md).
