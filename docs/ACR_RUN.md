# ACR Convergence 2026: unscored abstract corpus

This corpus is prepared for a future rheumatology-specific abstract-sift workflow. No import, estimate, scoring, TRACE annotation, or Site publication was run. Do not reuse the ESMO/SITC solid-tumor criteria for this conference.

## Collection and coverage

Source: https://acrabstracts.org/meetings/acr-convergence-2026/ . The collector follows every numbered meeting-listing page and fetches each linked abstract. The finalized manifest and validation report record counts, retrieval dates, missing content, title comparisons, and SHA-256 hashes.

IDs are strings: preserve leading zeros and late-breaking prefixes such as `LB16` and patient-perspective IDs such as `PP01`. The corpus contains the complete listing regardless of disease, modality, or anticipated relevance. It is a dated snapshot; subsequent additions or corrections require a new bundle version.

## Bundle files

- `acr2026-abstracts.jsonl.gz`: import-ready UTF-8 JSONL with exactly `id`, `title`, `authors`, `full_text`, and `link`, all strings.
- `acr2026-compilation.json.gz`: richer metadata, affiliations, keywords, session title/type/date/time, disclosures, citation, figure URLs/captions, extraction status, and source hashes.
- `validation.json`, `manifest.json`, and `SHA256SUMS`: coverage and integrity evidence.
- `CORPUS_GUIDE.md`: this guide.

Original HTML responses are cached under the conference workspace's `sources/` directory, separately from the portable bundle. The collector is `scripts/collect.py`; it resumes from successfully cached pages and retries transient errors. Cached responses must be explicitly removed or collected into a new workspace to refresh evidence.

Scientific text includes available HTML tables and figure captions. Image-only tables and figures are not OCR-transcribed; follow the retained image/source URLs to inspect them. Site navigation, favorite controls, session furniture, disclosures, and citation instructions are excluded from `full_text`; metadata and disclosures remain in the rich compilation. Superscript affiliation markers are removed from the authors field, with the original combined authors/affiliations text retained separately. Mathematical symbols in scientific content are preserved. Withdrawn records remain in the corpus with empty scientific text and explicit status in the compilation; missing authors on withdrawal pages are not invented. No model-generated summaries or invented missing text are included.

## Verify and import later

The local bundle is at `~/Projects/valius/conferences/acr2026/outputs/acr2026-corpus-v1/`. The portable bundle is published as [acr2026-corpus-v1](https://github.com/ValiusSciences/abstract-sift/releases/tag/acr2026-corpus-v1). Run from the abstract-sift repository when you choose to use it:

```bash
mkdir -p data/acr2026
gh release download acr2026-corpus-v1 --repo ValiusSciences/abstract-sift --dir data/acr2026
(cd data/acr2026 && shasum -a 256 -c SHA256SUMS)
gzip -dk data/acr2026/acr2026-abstracts.jsonl.gz
uv sync --locked
uv run abstract-sift import data/acr2026/acr2026-abstracts.jsonl --corpus acr2026
```

These are instructions only; the preparation task did not execute abstract-sift. Verification and import do not call a model API.

## Define a rheumatology research question before scoring

Write your own `data/acr2026/interest.txt`. Specify the diseases/populations of interest, interventions or biological questions, human versus preclinical evidence, outcomes, study types, exclusions, and what should receive high versus low relevance. Distinguish clinical efficacy from mechanistic findings and biomarker associations. Explicitly decide whether diagnostic, pediatric, rehabilitation, implementation, and health-services research is in scope. There is no default oncology filter or predetermined relevance threshold in this bundle.

Only after the question is agreed and a budget authorized, follow the current CLI reference for a small pilot and human review before a full run. For example:

```bash
uv run abstract-sift estimate --corpus acr2026 --query-file data/acr2026/interest.txt --provider both
uv run abstract-sift score --corpus acr2026 --query-file data/acr2026/interest.txt --provider both --limit 50 --max-cost-usd 0.25
uv run abstract-sift results PILOT_RUN_ID --sort openai --top 25
```

The budget is illustrative, not spending authorization or a provider billing cap. The first 50 records are not a random validation sample. Review a disease- and study-type-diverse sample and revise the criteria before scoring the full corpus. Record the exact query hash, requested/returned models, run ID, coverage and costs; keep the two model scores separate. A score represents relevance to the selected question, not clinical quality or probability of efficacy. Existing run IDs from other conferences do not apply.

## Rights and provenance

Abstract rights remain with the American College of Rheumatology and/or their respective rights holders. The abstract-sift software license does not license these abstracts. Publication of this research corpus does not change the rights in the underlying abstracts. Source URLs and source HTML hashes are retained for audit.

For maintainers, see abstract-sift's [conference workflow](CONFERENCE_WORKFLOW.md); CLI details are in [CLI reference](CLI.md). The corpus-only workflow deliberately stops before scoring and hosted Site publication.

## Validated snapshot

Collected 2,995 unique abstracts from 200 listing pages, including 22 late-breaking and 17 patient-perspective IDs; 2,988 have nonempty scientific text; 7 withdrawn records are retained with empty text. 0 fetch/parse errors; 7 missing author fields; 0 listing/title differences. 2,580 records contain linked images. Retrieval completed 2026-11-08T02:13:13.306043+00:00. See `validation.json` for exceptions.
