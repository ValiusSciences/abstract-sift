# Conference abstracts: collection to scientist review

Maintainer playbook, recorded 2026-11-06 (America/New_York). Based on the completed ESMO 2026 and SITC 2026 workflows. Start here for the next conference, then read its source-specific guide and the currently installed Sites skill. This document describes orchestration around abstract-sift; **TRACE tagging and hosted voting are not built-in CLI commands**.

## Deliverables and ownership

Keep three independently versioned layers:

1. **Evidence bundle:** source metadata, full text, provenance, five-field import corpus, criteria, independent model scores, offline explorer, manifest and checksums.
2. **TRACE annotations:** catalog snapshot hashes, matcher version, canonical entities, evidence snippets and uncertain candidates. These add information without changing scoring evidence or scores.
3. **Hosted review:** authenticated Site with filters, full text, annotations and persistent per-scientist votes. Votes are separate from model scores and must survive redeployments.

Use `conferences/<conference-year>/` for extraction, private catalogs, outputs and Site checkouts. Keep portable software and generic documentation in abstract-sift. Release artifacts belong in a versioned release, not the Python package. Do not put credentials, raw provider logs, scoring databases, private catalogs or scientist votes in a public release. Authorization to publish the abstract bundle does not automatically authorize publishing TRACE-derived data publicly; the current annotated Sites are workspace-only.

## 1. Collect and reconcile the source

- Establish the official listing and a dated coverage boundary. Discover the actual JSON/search endpoint when a page loads dynamically; paginate through all results and reconcile total count and unique IDs.
- Preserve string IDs (including suffixes such as `LBA` and `O`), titles, authors, categories, types, keywords and source links. Save original responses and extraction reports locally.
- Follow abstract links to HTML/PDF. Prefer structured HTML when accessible. For an official supplement fallback, retain PDF hashes and one-based physical pages, and match extracted text to the listing by number, title and DOI where available.
- Preserve missing/withdrawn entries with empty full text and an explicit reason. Do not silently drop them, invent text, truncate oversized text, or equate missing text with irrelevance.
- Reconcile duplicate IDs, listing-only entries, supplement-only entries, late-breaking coverage and text counts. Sample titles, section boundaries, tables and difficult PDF layouts. Record limits such as figures not transcribed.

SITC precedent: the public listing used Algolia pagination; official BMJ regular and LBA supplements supplied text when individual HTML pages were challenged. `pdftotext -raw` plus a layout extraction restored spacing only when character content agreed. Repeated page furniture was removed and lowercase line-end hyphenation joined. 1,126 texts matched the 1,127-row listing; withdrawn 1066 remained empty. PDF entries 178 and 531 were absent from that listing and were excluded. These are source-specific choices, not assumptions for future meetings.

## 2. Create an abstract-sift bundle

Each UTF-8 JSONL record must contain five string fields:

```json
{"id":"1000O","title":"Abstract title","authors":"A. Author; B. Author","full_text":"Complete source text","link":"https://official-source.example/abstract"}
```

IDs must be unique. The importer ignores extra fields, so retain richer metadata and extraction provenance in a separate compilation CSV/JSON. A withdrawn entry with a blank title can receive a documented label such as `Withdrawn abstract 1066`; keep its text empty.

Suggested release assets, using a conference-specific prefix:

| Asset | Contents |
| --- | --- |
| `<conference>-abstracts.jsonl.gz` | Five-field import corpus |
| `<conference>-abstracts.tsv` and `.tsv.gz` | Same five fields, without scores; UTF-8, quoted multiline fields, IDs preserved as strings |
| `<conference>-compilation.csv.gz` | Rich metadata, full text and source provenance |
| `<conference>-interest.txt` | Exact scoring criteria, immutable within this release |
| `<conference>-scores.csv.gz` and `.jsonl.gz` | Separate scores/statuses/models, evidence hashes and text |
| `<conference>-explorer.html.gz` | Offline scoring snapshot; no authentication or voting backend |
| `scoring-summary.json` | Run ID, rubric, criteria hash, requested/returned models, settings, coverage, cache reuse and costs |
| `manifest.json` | Version, source URLs/dates/hashes, counts, transformations, exceptions, rights and artifact hashes |
| `SHA256SUMS` | Checksums for finalized published files; do not self-hash this file |
| `SCORING_GUIDE.md` | Conference-specific download, verification, scoring and recovery instructions |

For a lossless TSV addition to an existing release, preserve the existing corpus/manifests and add a `TSV_GUIDE.md` and `TSV_SHA256SUMS` covering the new files. Validate TSV-to-JSONL round-trip equality for every field; physical line counts are not record counts when abstracts contain newlines.

Use a new release version when evidence or scores change. Record both uncompressed corpus integrity and compressed release-file integrity. Finalize documents and assets before checksums; validate them by downloading the published release when publishing is in scope. Source abstract rights remain with their holders; the software license does not license the corpus.

## 3. Score, inspect and export

Use the current CLI help and [CLI reference](CLI.md). A typical sequence is:

```bash
uv sync --locked
uv run abstract-sift import data/CONFERENCE/abstracts.jsonl --corpus CONFERENCE
uv run abstract-sift estimate --corpus CONFERENCE --query-file data/CONFERENCE/interest.txt --provider both
uv run abstract-sift score --corpus CONFERENCE --query-file data/CONFERENCE/interest.txt --provider both --limit 50 --max-cost-usd 0.25
uv run abstract-sift status PILOT_RUN_ID
uv run abstract-sift compare PILOT_RUN_ID
uv run abstract-sift score --corpus CONFERENCE --query-file data/CONFERENCE/interest.txt --provider both --max-cost-usd 2
uv run abstract-sift status RUN_ID
uv run abstract-sift cost RUN_ID
uv run abstract-sift compare RUN_ID
uv run abstract-sift export RUN_ID --format csv --include-text --output exports/CONFERENCE-scores.csv
uv run abstract-sift export RUN_ID --format jsonl --include-text --output exports/CONFERENCE-scores.jsonl
uv run abstract-sift site RUN_ID --output exports/CONFERENCE.html --title "Conference Abstract Explorer"
```

Replace uppercase placeholders. Budgets are examples, not standing spending authorization or provider billing caps. Choose budgets and throughput for the task and account quotas. SITC used batch size 32, concurrency 16, RPM 600 and TPM 10,000,000 after a pilot; do not assume those quotas elsewhere. Use existing credentials through supported configuration, never print them. On interrupted runs, resume the same run with an explicitly chosen additional budget rather than scoring again blindly.

For comparable screening, snapshot the agreed criteria rather than paraphrasing them. The 2026 examples used `relevance-v1`, OpenAI Decisions `gpt-6-luna` and JEV `jev-1.14.0`; verify configured/current model support before a future run. Keep requested and returned models and evidence hashes. Model scores stay separate, never averaged. Default labels: relevant >=0.7, not relevant <=0.3, otherwise review. Failed/missing scores remain visible.

Reconcile successful/missing/failed/oversized counts per provider; completion alone is insufficient. Record paired coverage, disagreements, retained counts, pilot cache reuse and usage-derived costs. A sequential pilot is a smoke test, not an accuracy study. Release run IDs are references to the originating database; downloading scores does not create those runs in a fresh installation.

Optional prioritization: `openai > 0.5 OR jev > 0.5`, treating null as unavailable. The explorer slider uses >=, so explicitly check boundary records when someone asks for strictly >. SITC had 51 qualifying records and no maximum score exactly 0.5 at the recorded snapshot. Do not silently discard other abstracts or change screening labels to implement a review filter.

## 4. Update documentation with the bundle

Update `examples/<conference>-interest.txt`, add `docs/<CONFERENCE>_RUN.md`, and link it from README. Follow [SITC_RUN.md](SITC_RUN.md) for a scored bundle and [ESMO_RUN.md](ESMO_RUN.md) for corpus setup. Copy the finalized conference guide into its release as `SCORING_GUIDE.md`.

Include actual coverage and exceptions, source provenance, exact criteria/model/rubric choices, download/checksum instructions, import/estimate/pilot/full/resume/export commands, run interpretation, observed costs with caveats, and rights. Distinguish immutable release artifacts from a mutable hosted Site. Do not claim the public release contains internal tags or votes unless it actually does and publication is authorized.

After later tagging or Site changes, record the deployment separately; do not rewrite old scoring results to imply a new scoring run. Link back to this playbook from each guide. Verify relative documentation links, changed-file whitespace and repository status. Documentation-only edits need no paid scoring or broad test run.

## 5. Read TRACE through omnivalius

Code lives in `~/Projects/valius/kandinsky/omnivalius`. Read the applicable repository instructions and current TRACE API contract before use. Relevant modules are `src/omnivalius/clients/trace.py` and `src/omnivalius/config.py`; service documentation is in `../trace/API.md`.

Use the established `settings()` / `trace_client(...)` configuration and authenticate with `whoami()` before collection. Existing environment values take precedence; the recorded config supports `OMNIVALIUS_ENV_FILE`, project `.env` discovery, and `~/.config/omnivalius/env`. Inspect current code rather than assuming this never changes. Never print tokens or save them in source. Use the supported login flow only if authentication is absent.

Useful read-only endpoints under the configured TRACE base URL:

| Endpoint | Purpose |
| --- | --- |
| `/gene-names` | Canonical gene symbols, display names and aliases |
| `/therapeutics` | All therapy identities, including unlinked therapies: ID, name, INN, brand, sponsor codes and aliases |
| `/gene-names/{name}` | Alias resolution when further investigation is needed |

The recorded client used its `_get` helper for the first two catalog endpoints because they were not exposed as dedicated methods. Treat this as an internal implementation detail; inspect current client/API support before reusing it. The CLI also exposes `trace targets`, `trace target SYMBOL`, and `trace therapies SYMBOL` with JSON output. A per-target therapy fetch alone can miss unlinked therapies.

Save private catalog snapshots with restrictive permissions, retrieval time and SHA-256 hashes. The Nov 6 snapshot had 313 targets and 3,813 therapy records. Reuse the same snapshot for comparable conference annotations, or record a new snapshot/version explicitly. Tagging does not require creating or changing TRACE records.

## 6. Match targets and therapies conservatively

The implemented method is deterministic lexical entity matching, **not trial registration, intervention classification or evidence of efficacy**. An abstract can mention a target as a biomarker or a therapy as background/comparator. Do not infer targets from a drug mechanism or identify a specific drug from a class description.

- Search title and scientific body, excluding authors/affiliations and reference-only mentions where section boundaries permit. ESMO additionally cuts disclosure, funding, editorial acknowledgements and legal-entity sections. If no recognized body heading exists, the current matcher searches title only; record this coverage limit.
- Match canonical symbols, display names and aliases; therapies use names, INNs, brands and aliases. Normalize case and typography while respecting alphanumeric boundaries. Prefer a longer overlapping therapy name over its nested parent-drug alias, without suppressing separate mentions elsewhere.
- Treat alias collisions and ambiguous short names as review candidates, excluded from confident tags. Examples include MET/KIT/RET and common-word symbols. Keep candidate evidence for adjudication.
- **Do not blindly trust sponsor-code fields.** TRACE contained `anti-PD-1` attached to MEDI8500, numeric fragments `20`/`70` attached to other drugs, `AML`, and institutional names. These produced false matches. The implemented filter accepts only sponsor codes resembling a specific letter-number identifier; generic descriptions and numeric fragments are excluded.
- The initial matcher supplements missing target aliases with PD-1 → PDCD1, PD-L2 → PDCD1LG2, CD39 → ENTPD1, CD73 → NT5E and LAG-3 → LAG3, only when the canonical entity exists. Keep additions explicit and versioned; do not silently mutate TRACE.
- Record abstract ID, entity kind, canonical ID/name, normalized alias, actual matched text, searched section, offsets, status and evidence snippet. Current deduplication keeps the first occurrence per entity/alias/status/section. Offsets refer to the searched section, not the entire source document.

Outputs: canonical target genes/names, therapy names/TRACE IDs, review candidates, tag status/method, structured evidence JSON, evidence CSV, method guide and validation summary with catalog hashes. Preserve every original record/score/text and verify equality before and after enrichment. No catalog match is not evidence of absence. This first pass is not manually curated; unknown therapies, missing aliases, OCR variants and unstructured abstracts can be missed.

Validate difficult negatives (generic anti-PD-1, numbers, institutional names, common-word MET), known positives (named drugs, HER2/PD-1), collisions and nested therapies. Inspect top matches for implausible enrichment. Do not claim these checks establish clinical accuracy.

## 7. Publish an annotated ChatGPT Site

Read the **currently installed Sites skill**, including storage and identity references. Plugin versions and supported publishing APIs can change. Use its source helper and native publishing tools, not a remembered credential workaround.

For an existing Site, read `.openai/hosting.json`, reuse its exact project ID, call `get_site`, preserve its audience, obtain a source write credential, and open the source using `site-workflow.mjs` before editing. Credentials belong in session memory and helper stdin only. Retain the complete opening result for packaging. Never create a second Site to update an existing one.

Retain the conference's own metadata, query, scores, original links and full-text chunks. Add target/therapy filters, searchable tags, per-abstract chips, evidence/review candidates, tagged CSV downloads and a method/limitations link. Clearly label tags as mentions, not confirmed study interventions. Keep thresholds and scores unchanged.

Two proven source layouts exist: SITC has an embedded `explorer-data` snapshot; ESMO uses `data.json`, `details/<chunk>.json`, and separate JS/CSS. Adapt data loading to the actual layout. Avoid replacing an existing conference's data or branding with a copied template. The generic offline CLI exporter remains network-free: do not copy hosted voting fetches into it without separating the hosted feature.

### Persistent scientist review

Use hosted D1, not localStorage. The Site migration declares `d1: "DB"` and uses a server Worker; remove the static-only declaration when converting. Sites provisions the database and applies schema migrations. The implemented schema is:

```sql
CREATE TABLE scientist_votes (
  abstract_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  vote INTEGER NOT NULL CHECK (vote IN (-1, 1)),
  updated_at TEXT NOT NULL,
  PRIMARY KEY (abstract_id, user_id)
);
```

Use the platform-supplied `oai-authenticated-user-id` on the server. Never accept the voter ID from the browser. It is stable within a Site, not across Sites. Keep workspace restrictions in the Site access policy. API routes must reject absent identity even when service access exists; service tokens are not scientist identities.

The current API is GET/PUT `/api/votes`. GET returns aggregate up/down counts and the current scientist's own vote. PUT validates same-origin Origin, JSON content type, bounded input, known abstract ID and vote in {-1,0,1}. Upsert ±1 on the composite key; 0 deletes only that scientist's vote. The browser never writes raw SQL. Do not expose other scientists' identities when only totals are needed.

Use `SUM(CASE WHEN user_id=? THEN vote ELSE 0 END)` for the current vote. A tested pitfall: adding MAX and MIN gives -2 when the only vote is the current user's downvote. Repeated votes must not inflate totals. Test two scientists, reversal, deletion, authentication and malformed input against real SQLite semantics.

Place buttons in table rows and full-text dialogs; selected thumbs use `aria-pressed`. Clicking the selected thumb clears it. Disable controls during loading/saving; show local save/error feedback, refresh totals and never report a failed save as successful. Votes do not modify AI scores. Show one-vote-per-scientist guidance and a refresh control.

Store schema changes in append-only migrations (`drizzle/*.sql` plus the journal for these Worker implementations). Do not create tables during requests. Never rewrite applied migrations, drop review data, or replace the project's DB binding on a later update. Future schema changes require a new migration.

### Build, verify and deploy

A server-backed Site exports a Worker `fetch` handler at `dist/server/index.js`. The current custom builders embed gzipped assets and decompress them for responses, and package the source manifest plus migrations. No provider credentials or TRACE catalog are embedded. For larger corpora, avoid embedding duplicate full-text CSVs: ESMO streams downloads from metadata/text chunks. Its initial duplicated bundle compressed to ~14.9 MB; streaming reduced the Worker to ~7.7 MB and it deployed successfully. Check current platform limits rather than treating this historical size as a universal threshold.

Checks before publication:

- All original metadata, scores, criteria and full texts are unchanged; row counts reconcile.
- Tag filters/search/reset, evidence, modal loading, score filters, scatter view and CSV export work.
- Voting passes authentication/origin/input checks, repeat/change/clear tests and per-scientist isolation.
- Built Worker serves HTML, scripts, CSS, metadata, text chunks and downloads; anonymous voting fails.
- Run supported browser preview/visual QA when available. Report the limit if unavailable; the initial SITC/ESMO updates had automated interaction checks but no browser visual verification.

Package/push the exact source state using the current source helper, the complete opening result, remaining check/build commands, and an absolute archive path. Use its returned project ID, full commit SHA and archive unchanged. Save the version, then deploy the exact returned version ID using the operation appropriate to the existing audience. For these workspace-wide Sites, use the shared deployment operation. Do not request another conversational approval when publication is already authorized.

Poll only nonterminal deployment states. After adding storage, use the database overview tool to confirm `DB` and `scientist_votes` exist. Deployment success plus schema presence does not itself prove a signed-in browser vote succeeded; distinguish this from local integration tests. Report the exact live URL, counts, preserved audience/scores and verification limits.

## Reference implementations and recorded deployments

Local paths are navigation aids, not portable dependencies:

- `~/Projects/valius/conferences/sitc2026/`: `export_abstracts.py`, `extract_abstract_text.py`, `tag_abstracts.py`, `update_tagged_site.py`, `extend_esmo.py`, private TRACE snapshots, validation outputs and workbook builders.
- SITC Site: `conferences/sitc2026/sites/sitc2026-explorer/`; `worker/api.mjs`, `build-worker.mjs`, `drizzle/`, `test-votes.mjs`, `test-ui.cjs`.
- ESMO Site: `conferences/esmo2026/sites/esmo-abstract-explorer/`; adapted chunked-data builder, same voting API/migration, tests and `tagging-validation.json`.
- These adaptation scripts are one-off orchestration, not idempotent public APIs. Some modify files by string replacement. Start from the opened Site source, inspect it, and port changes deliberately; do not blindly rerun them against already enriched files.

| Snapshot | SITC 2026 | ESMO 2026 |
| --- | --- | --- |
| Records | 1,127 | 4,418 |
| Target-tagged | 857 | 1,972 |
| Therapy-tagged | 299 | 1,581 |
| Either tag | 905 | 2,573 |
| Records with review candidates | 129 | 356 |
| Site project | `appgprj_6aee5ce95c4481918ac71b728c28ebdc` | `appgprj_6adfcaff042881918fdff80a6e9e134d` |
| Tagged/voting version | 3 | 11 |
| Published source commit | `0d8c034d9162def65d808c193fbee2ea01fae30f` | `de0a2bc4783421bc007bc439875f52cd0bd7066b` |
| Audience | Workspace all | Workspace all |

Live references: [SITC explorer](https://sitc2026-abstract-explorer.valius-scien-8271.chatgpt.site) and [ESMO explorer](https://esmo-2026-abstract-explorer.valius-scien-8271.chatgpt.site). These are mutable; read current Site state before changing them. Catalog hashes and per-run validation files are the source of reproducibility, not the counts in this table alone.
