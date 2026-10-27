# Comparing OpenAI and JEV

Design specification; not yet implemented or benchmarked.

## Pairing and reproducibility

Compare only successful results with identical corpus/abstract version, scientific evidence hash, research-query hash, canonical rubric and task polarity. Provider-specific JSON and batch sizes may differ; record them and test whether batching changes judgments. Retain requested and returned model IDs. A version change starts a distinct report stratum.

For both-mode runs, each eligible abstract has two expected provider results. Failed, refused, missing-text and not-yet-complete items are not negatives. Report selected records, eligible records, successful OpenAI results, successful JEV results, complete pairs, incomplete pairs, and source-missing records. Comparison reports are labeled provisional while the paired set is still growing; high-ranked items evaluated first can bias early agreement.

## Row-level output

Export ID/title/link, both provider statuses and raw probabilities, both labels, thresholds, model IDs, source provenance, `comparison_bucket`, raw probability gap, provider ranks and paired rank difference. Provider fields remain null if unavailable; never replace a missing score with zero.

Three-way label mapping uses versioned low/high thresholds: probability <= low means negative, >= high means positive, and between them means review. Thresholds may differ by provider when fitted to equivalent sensitivity goals on a separate labeled set. Show whether they are provisional or calibrated. Do not tune thresholds merely to maximize agreement.

Buckets: both positive; both negative; OpenAI positive/JEV negative; JEV positive/OpenAI negative; uncertainty in one or both; incomplete pair. Use a separate 3×3 table to distinguish all positive/review/negative combinations.

## Wide-net reading policy

Retain if either label is positive or review. Keep incomplete pairs in a pending/manual-review queue. Prioritize both-positive records for reading; provide a disagreement-first view for opposite confident labels. Make both-negative records inspectable/exportable. Do not discard abstracts merely because one model considers them negative.

This policy increases the opportunities to catch relevant papers but can increase review workload. Test its recall and precision against human labels rather than asserting it outperforms the better single model. Avoid averaging raw scores or multiplying probabilities: model errors are not known to be independent and the two probabilities may be differently calibrated.

## Reported metrics

All metrics include the actual paired denominator, threshold configuration and provider versions. Calculate per query; for multi-query summaries report both micro totals and macro averages rather than hiding difficult queries.

| Metric | Definition and interpretation |
| --- | --- |
| Three-way agreement | Equal positive/review/negative labels divided by all valid pairs; show the entire 3×3 table |
| Binary 2×2 table | Under separately declared binary thresholds: a=both positive, b=OpenAI positive only, c=JEV positive only, d=both negative; N=a+b+c+d |
| Binary agreement | `(a+d)/N`; neither provider is ground truth |
| Discordance rate | `(b+c)/N`; retain both directional counts |
| Cohen's kappa | `(Po-Pe)/(1-Pe)`, where `Po=(a+d)/N` and `Pe=((a+b)(a+c)+(c+d)(b+d))/N²`; report marginals because prevalence affects interpretation |
| Positive agreement | `2a/(2a+b+c)`; useful when negatives dominate |
| Negative agreement | `2d/(2d+b+c)` |
| Ranking concordance | Spearman correlation of paired probabilities using average ranks for ties; measures ordering, not probability calibration |
| Top-k overlap | On the same paired universe, intersection/k and Jaccard intersection/union for k=20, 50, 100 (clamp k to N); deterministic ID tie-break, report ties at cutoff |
| Probability discrepancy | Distribution of `abs(p_openai-p_jev)` and signed mean difference; descriptive only, not an error rate |

Binary thresholds are a reporting projection independent of the review-band workflow. Include uncertain rows in the binary projection when probabilities exist, and label it accordingly. If an additional confident-only table is shown, disclose its excluded count and coverage; never silently drop the review band.

Return null with a reason for no pairs, zero denominators, kappa with Pe=1, and rank correlation with a constant input or fewer than two pairs. No NaN in JSON and no misleading default 0/1. Do not call these sensitivity/specificity metrics without independent truth labels.

When expert labels exist, report precision, recall, false negatives, precision@k, Brier score and reliability bins separately for each provider, plus union/intersection/review-policy performance. Fit any calibration on a training split, evaluate on held-out queries, preserve raw scores and version the calibration. Agreement alone cannot validate scientific screening quality.

For uncertainty estimates, bootstrap paired abstract units within a query; when aggregating profiles, account for query/abstract clustering. Avoid overstating precision from repeated judgments of the same abstracts.

## Acceptance fixtures

Hand-check: identical predictions; all-positive and all-negative degenerate predictions; perfectly reversed labels; scores with equal rankings but different scales; ties and k>N; missing/refused providers; mismatched source/query hashes; version changes; threshold changes without rescoring. A report must explain the paired population and reproduce its metrics from exported rows.
