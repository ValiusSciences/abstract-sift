"""Paired descriptive agreement. Neither model is treated as ground truth."""

import math
from .core import label, digest


def ratio(a, b):
    return a / b if b else None


def ranks(values):
    result = [0.0] * len(values)
    order = sorted(range(len(values)), key=lambda i: values[i])
    i = 0
    while i < len(order):
        j = i + 1
        while j < len(order) and values[order[j]] == values[order[i]]:
            j += 1
        for k in order[i:j]:
            result[k] = (i + j - 1) / 2 + 1
        i = j
    return result


def correlation(x, y):
    if len(x) < 2:
        return None
    mx, my = sum(x) / len(x), sum(y) / len(y)
    a = [v - mx for v in x]
    b = [v - my for v in y]
    den = math.sqrt(sum(v * v for v in a) * sum(v * v for v in b))
    return sum(u * v for u, v in zip(a, b)) / den if den else None


def joined(store, run, low=0.3, high=0.7):
    items = {r["id"]: r for r in store.items(run)}
    selected = store.run(run)["config"]["providers"]
    output = {
        i: dict(
            id=i,
            title=r["title"],
            authors=r["authors"],
            link=r["link"],
            evidence_hash=digest(r),
        )
        for i, r in items.items()
    }
    for r in store.results(run):
        row = output[r["id"]]
        p = r["provider"]
        row[p + "_status"] = r["status"]
        row[p + "_probability"] = r["probability"]
        row[p + "_error"] = r["error"]
        row[p + "_model"] = r["model"]
        row[p + "_cache_origin"] = r["cache_origin"]
        row[p + "_label"] = (
            label(r["probability"], low, high) if r["status"] == "ok" else None
        )
    for row in output.values():
        labels = [row.get(p + "_label") for p in selected]
        row["retain_for_review"] = not all(v == "not_relevant" for v in labels)
        if len(selected) == 1:
            bucket = "single_provider"
        elif None in labels:
            bucket = "incomplete_pair"
        elif labels[0] == labels[1]:
            bucket = "both_" + labels[0]
        elif "review" in labels:
            bucket = "uncertainty"
        else:
            bucket = "discordant"
        row["comparison_bucket"] = bucket
        a, b = row.get("openai_probability"), row.get("jev_probability")
        row["probability_gap"] = abs(a - b) if a is not None and b is not None else None
    return list(output.values())


def report(store, run, low=0.3, high=0.7, threshold=0.5):
    cfg = store.run(run)["config"]
    if set(cfg["providers"]) != {"openai", "jev"}:
        raise ValueError("Comparison requires a both-provider run")
    rows = joined(store, run, low, high)
    pairs = [r for r in rows if r["openai_status"] == "ok" and r["jev_status"] == "ok"]
    n = len(pairs)
    a = b = c = d = 0
    labels = ("relevant", "review", "not_relevant")
    matrix = {x: {y: 0 for y in labels} for x in labels}
    for r in pairs:
        matrix[r["openai_label"]][r["jev_label"]] += 1
        x, y = r["openai_probability"] >= threshold, r["jev_probability"] >= threshold
        if x and y:
            a += 1
        elif x:
            b += 1
        elif y:
            c += 1
        else:
            d += 1
    po = ratio(a + d, n)
    pe = ((a + b) * (a + c) + (c + d) * (b + d)) / n**2 if n else None
    kappa = (po - pe) / (1 - pe) if pe is not None and pe != 1 else None
    overlaps = {}
    for requested in (20, 50, 100):
        k = min(requested, n)
        sets = [
            {
                r["id"]
                for r in sorted(pairs, key=lambda r: (-r[p + "_probability"], r["id"]))[
                    :k
                ]
            }
            for p in ("openai", "jev")
        ]
        overlaps[str(requested)] = dict(
            k=k,
            overlap=ratio(len(sets[0] & sets[1]), k),
            jaccard=ratio(len(sets[0] & sets[1]), len(sets[0] | sets[1])),
            tie_break="abstract_id",
        )
    x = [r["openai_probability"] for r in pairs]
    y = [r["jev_probability"] for r in pairs]
    builds = {p: sorted({r[p + "_model"] for r in pairs}) for p in ("openai", "jev")}
    if any(len(v) > 1 for v in builds.values()):
        raise ValueError("Mixed model versions; compare version-homogeneous runs")
    return dict(
        run=run,
        provisional=store.run(run)["status"] != "complete",
        selected=len(rows),
        paired=n,
        incomplete_pairs=len(rows) - n,
        coverage=store.summary(run)["providers"],
        thresholds=dict(
            low=low, high=high, binary=threshold, calibration="uncalibrated"
        ),
        models=builds,
        three_way_matrix=matrix,
        three_way_agreement=ratio(sum(matrix[z][z] for z in labels), n),
        binary_table=dict(
            both_positive=a,
            openai_positive_only=b,
            jev_positive_only=c,
            both_negative=d,
        ),
        binary_agreement=po,
        discordance=ratio(b + c, n),
        kappa=kappa,
        positive_agreement=ratio(2 * a, 2 * a + b + c),
        negative_agreement=ratio(2 * d, 2 * d + b + c),
        spearman=correlation(ranks(x), ranks(y)),
        top_k=overlaps,
        mean_absolute_probability_gap=ratio(sum(abs(u - v) for u, v in zip(x, y)), n),
        mean_signed_probability_gap=ratio(sum(u - v for u, v in zip(x, y)), n),
        undefined_note="Null metrics have insufficient pairs, a zero denominator, or constant ranks. Agreement is not accuracy.",
        cost=store.cost(run),
    )


def compare_runs(store, before, after, low=0.3, high=0.7, top=20):
    """Compare identical screening tasks; no model is treated as ground truth."""
    old, new = store.run(before), store.run(after)
    for key in ("rubric", "corpus_hash", "pricing"):
        if old["config"][key] != new["config"][key]:
            raise ValueError(
                "Run comparison requires matching rubric, corpus and model/pricing snapshots"
            )
    if old["query"] != new["query"] or set(old["config"]["providers"]) != set(
        new["config"]["providers"]
    ):
        raise ValueError(
            "Run comparison requires identical criteria and selected providers"
        )
    left = {r["id"]: r for r in joined(store, before, low, high)}
    right = {r["id"]: r for r in joined(store, after, low, high)}
    if set(left) != set(right) or any(
        left[i]["evidence_hash"] != right[i]["evidence_hash"] for i in left
    ):
        raise ValueError("Run comparison requires identical abstract evidence")
    providers = old["config"]["providers"]
    metrics = {}
    changes = []
    complete = []
    for i in left:
        a, b = left[i], right[i]
        if all(
            a[p + "_status"] == b[p + "_status"] == "ok"
            and a[p + "_model"] == b[p + "_model"]
            for p in providers
        ):
            complete.append(i)
    for p in providers:
        pairs = [
            i
            for i in left
            if left[i][p + "_status"] == right[i][p + "_status"] == "ok"
            and left[i][p + "_model"] == right[i][p + "_model"]
        ]
        x = [left[i][p + "_probability"] for i in pairs]
        y = [right[i][p + "_probability"] for i in pairs]
        deltas = [abs(b - a) for a, b in zip(x, y)]
        n = len(pairs)
        flips = sum(left[i][p + "_label"] != right[i][p + "_label"] for i in pairs)
        matrix = {
            a: {b: 0 for b in ("relevant", "review", "not_relevant")}
            for a in ("relevant", "review", "not_relevant")
        }
        for i in pairs:
            a, b = left[i], right[i]
            matrix[a[p + "_label"]][b[p + "_label"]] += 1
            delta = b[p + "_probability"] - a[p + "_probability"]
            if delta:
                changes.append(
                    dict(
                        id=i,
                        title=b["title"],
                        provider=p,
                        before=a[p + "_probability"],
                        after=b[p + "_probability"],
                        delta=delta,
                        before_label=a[p + "_label"],
                        after_label=b[p + "_label"],
                    )
                )
        metrics[p] = dict(
            paired=n,
            excluded=len(left) - n,
            label_changes=flips,
            label_agreement=ratio(n - flips, n),
            mean_absolute_score_change=ratio(sum(deltas), n),
            max_absolute_score_change=max(deltas, default=None),
            spearman=correlation(ranks(x), ranks(y)),
            label_transitions=matrix,
            reused_scores_after=sum(bool(right[i][p + "_cache_origin"]) for i in pairs),
        )
    removed = [
        i
        for i in complete
        if left[i]["retain_for_review"] and not right[i]["retain_for_review"]
    ]
    added = [
        i
        for i in complete
        if not left[i]["retain_for_review"] and right[i]["retain_for_review"]
    ]
    changes.sort(key=lambda r: (-abs(r["delta"]), r["id"], r["provider"]))
    return dict(
        before=before,
        after=after,
        provisional=old["status"] != "complete" or new["status"] != "complete",
        thresholds=dict(low=low, high=high),
        providers=metrics,
        retained=dict(
            fully_scored_same_model_pairs=len(complete),
            excluded=len(left) - len(complete),
            before=sum(left[i]["retain_for_review"] for i in complete),
            after=sum(right[i]["retain_for_review"] for i in complete),
            newly_excluded=removed,
            newly_retained=added,
        ),
        largest_score_changes=changes[:top],
        total_changed_provider_scores=len(changes),
        note="Missing/failed scores and changed returned models are excluded. Transitions are before → after. Changes may reflect run-to-run variability as well as batching; this is stability analysis, not accuracy validation.",
    )
