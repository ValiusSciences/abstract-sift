# Per-run usage and cost accounting

Every score, benchmark, and resume operation produces a durable usage ledger. Status, comparison, threshold changes, and exports do not make paid model calls.

## What the user sees

At start: estimated tokens, requests, price assumptions/date, provider-specific costs, combined cost, total budget and optional provider sub-budgets. Unknown provider pricing blocks a dollar-capped run until a rate assumption is explicitly supplied; do not represent unknown price as free.

During the run: estimated usage-based spend so far, in-flight reservations, cache hits, retries and remaining budget. Track both provider pipelines independently and aggregate them atomically.

At completion, cancellation or failure: save a run summary even if incomplete. Show newly incurred cost this invocation and lifetime cost for the run across resumes. Failed/no-result requests and refused answers may still consume billable input; accounting must not depend on a successful classification.

Example output (illustrative values only):

```text
Run: run_123   Invocation: attempt_2
Provider  Input tokens  Usage-derived cost  Unknown-usage attempts
OpenAI    1,000,000     $0.1000             1
JEV       1,000,000     $0.0420             0
New usage-derived total: $0.1420
Unknown-usage exposure: estimated separately; not confirmed billing
Prior invocation costs: shown separately
Lifetime run cost: prior + current, with uncertainty explicitly reported
```

Do not label this a settled invoice. Provider usage counters plus published rates produce a usage-derived estimate. Actual billing can differ because of account discounts, cache writes, regional modifiers, price changes, rounding or requests processed after a client timeout. If a provider supplies an authoritative per-request charge, retain it with its currency/source and prefer it over the calculation for that request. Later reconciliation must preserve the original estimate and audit trail.

## Ledger structure

- Run: run ID, corpus/query/rubric hashes, selected providers/models, created/finished timestamps, state, total budget and currency.
- Invocation: invocation ID, parent run ID, start/end, resume reason, allowed additional budget, and newly incurred totals.
- Request attempt: unique local attempt ID, logical batch ID, provider/request ID if available, requested/returned model, timestamps, outcome/status, retry ordinal, item IDs, estimated input tokens, reserved cost, returned usage, elapsed time, and billing certainty.
- Pricing snapshot: provider/model, currency, effective/check date, source URL, uncached input rate, cache-read/write rates where applicable, output rate, known modifiers, and explicit user overrides.
- Derived cost: provider-reported charge if available; otherwise rate × matching usage categories. Keep raw usage separately for future recalculation.

Use decimal arithmetic or integer sub-cent units, not binary floating-point money. Preserve at least six decimal places in internal USD estimates; do not round each tiny request to cents before summing. Unsupported or missing usage categories remain unknown instead of zero. Avoid double-counting cached tokens already included in total input: partition input into mutually exclusive billable categories according to that provider's documented semantics.

## Retries, cache and interruption

A logical batch may have multiple paid attempts. Persist an attempt record before dispatch, update after response, and count each actual attempt once. Do not count duplicate local completion events twice. Capture retries in one layer: either disable opaque SDK retries and implement them in the scheduler, or instrument every SDK attempt.

A timeout or connection loss can occur after the provider processes a request. Record it as `usage_unknown`, retain a conservative estimated charge/exposure, and never assume retrying is free. On a process crash, dispatched-but-unreconciled attempts become unknown rather than disappearing. Canceling an HTTP request is not evidence that billing stopped.

Local result-cache hits make no request and incur zero NEW provider cost. Retain the originating result/run ID and its historical cost; do not charge it again. Provider prompt-cache hits are requests and follow the provider's billing categories. Show local-cache reuse separately from prompt-cache discounts.

Input usage and costs belong naturally to a request/batch. An optional per-abstract allocation is only a proportional accounting estimate, explicitly labeled; never imply the provider billed a specific amount for each abstract.

## Budget enforcement

Reserve conservative estimated costs atomically against both total and provider-specific budgets before each dispatch. Include already spent amounts and unresolved/in-flight reservations. Set aside capacity for both providers so the faster pool cannot consume the entire both-mode budget before paired results arrive. Reconcile returned usage after every attempt. Retries need a new reservation. Do not automatically borrow a provider's reserved share or switch providers after a failure.

Stop new work when the budget is exhausted, checkpoint, and report partial coverage. Resume uses an explicit additional allowance; accounting never resets to zero. Budgets constrain app scheduling, not absolute provider invoices: estimates and in-flight/unknown requests limit guarantees. Report this plainly in help and run summaries.

## Outputs and tests

Proposed commands: `abstract-sift cost RUN_ID --json` and `abstract-sift cost --all`. Export `run-summary.json` plus `request-usage.jsonl` without secrets or source content. Reports retain per-provider and combined costs and price snapshots. Comparison reports reference the same run ledger and show cost per successfully evaluated item and per complete pair, with denominator and incomplete work visible.

Tests cover two-provider concurrent reservations, tiny-cost precision, retry charges, no-usage errors/timeouts, prompt-cache categories, duplicate events, crash/resume, local-cache reuse, price revisions, currency mismatch and unchanged accounting when thresholds change. Compare totals with provider usage/billing views when available; no admin credentials are required for the basic local ledger.
