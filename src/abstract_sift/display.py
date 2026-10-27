"""Human-readable reports and bounded, stderr-only progress rendering."""

import asyncio
import shutil
import sys
import time
from .explore import table, clean


def value(v):
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.4f}"
    return str(v)


def grid(rows, columns):
    table(
        [{k: value(v) for k, v in r.items()} for r in rows],
        [(k, title, width) for k, title, width in columns],
    )


def stats(obj):
    grid(
        [{"metric": k.replace("_", " "), "value": v} for k, v in obj.items()],
        [("metric", "Metric", 40), ("value", "Value", 65)],
    )


def cost_table(obj):
    print("Run: " + clean(obj["run"]))
    grid(
        [dict(provider=p, **r) for p, r in obj["providers"].items()],
        [
            ("provider", "Provider", 10),
            ("attempts", "Requests", 10),
            ("input_tokens", "Input tokens", 14),
            ("known_usd", "Cost (USD)", 15),
            ("unknown_usd", "Unknown exposure", 18),
        ],
    )
    print(
        f"Usage-derived total: ${obj['usage_derived_usd']} | Unknown exposure: ${obj['unknown_exposure_usd']} | In flight: ${obj['inflight_reserved_usd']}"
    )
    print("Estimated from reported usage; not a settled invoice.")


def present(obj, command):
    if command == "site":
        print("HTML explorer: " + clean(obj["output"]))
        print(
            f"{obj['records']:,} abstracts | {obj['paired']:,} scored pairs | {obj['bytes']/1_000_000:.1f} MB"
        )
        print("Open this file directly in your browser. " + obj["access"])
        return
    if command in ("score", "resume"):
        present(obj["summary"], "status")
        print()
        cost_table(obj["cost"])
        return
    if command == "status":
        print("Run: " + clean(obj["run"]) + " | " + clean(obj["status"]))
        keys = ("ok", "queued", "failed", "missing_text", "oversized", "refused")
        grid(
            [
                dict(provider=p, **{k: r.get(k, 0) for k in keys})
                for p, r in obj["providers"].items()
            ],
            [("provider", "Provider", 10)]
            + [(k, k.replace("_", " ").title(), 14) for k in keys],
        )
        return
    if command == "cost":
        if isinstance(obj, list):
            grid(
                [
                    dict(
                        run=r["run"],
                        cost=r["usage_derived_usd"],
                        unknown=r["unknown_exposure_usd"],
                    )
                    for r in obj
                ],
                [
                    ("run", "Run", 24),
                    ("cost", "Cost (USD)", 15),
                    ("unknown", "Unknown exposure", 18),
                ],
            )
        else:
            cost_table(obj)
        return
    if command == "estimate":
        grid(
            [dict(provider=p, **r) for p, r in obj["providers"].items()],
            [
                ("provider", "Provider", 10),
                ("requests", "Requests*", 10),
                ("eligible", "Eligible", 10),
                ("missing_text", "Missing text", 14),
                ("oversized", "Oversized", 10),
                ("uncached_cost_upper_estimate_usd", "Cost bound (USD)*", 20),
            ],
        )
        print(
            "* Conservative preflight estimate. Adaptive batching may use fewer requests; retries excluded."
        )
        return
    if command == "import":
        stats({k: obj[k] for k in ("corpus", "records", "usable")})
        return
    if command == "export":
        stats(obj)
        return
    if command == "search":
        print("Lexical preview — not model relevance scores")
        grid(
            obj["results"],
            [
                ("id", "ID", 18),
                ("title", "Title", 65),
                ("search_matches", "Matches", 10),
            ],
        )
        return
    if command == "compare-runs":
        print(clean(obj["before"]) + " → " + clean(obj["after"]))
        print(
            f"Thresholds: {obj['thresholds']['low']} / {obj['thresholds']['high']} | Provisional: {obj['provisional']}"
        )
        grid(
            [dict(provider=p, **r) for p, r in obj["providers"].items()],
            [
                ("provider", "Provider", 10),
                ("paired", "Paired", 8),
                ("excluded", "Excluded", 10),
                ("label_changes", "Label changes", 14),
                ("label_agreement", "Agreement", 12),
                ("mean_absolute_score_change", "Mean |Δ|", 12),
                ("spearman", "Spearman", 12),
                ("reused_scores_after", "Reused", 8),
            ],
        )
        r = obj["retained"]
        print(
            f"\nRetained: {r['before']} → {r['after']} | Excluded from comparison: {r['excluded']}"
        )
        print(
            "Newly excluded: " + (", ".join(map(clean, r["newly_excluded"])) or "none")
        )
        print(
            "Newly retained: " + (", ".join(map(clean, r["newly_retained"])) or "none")
        )
        print("\nLargest score changes")
        grid(
            obj["largest_score_changes"],
            [
                ("id", "ID", 16),
                ("provider", "Provider", 10),
                ("before", "Before", 10),
                ("after", "After", 10),
                ("delta", "Change", 10),
                ("title", "Title", 55),
            ],
        )
        print("\n" + obj["note"])
        return
    if command == "compare":
        print("Run: " + clean(obj["run"]))
        stats(
            {
                k: obj[k]
                for k in (
                    "provisional",
                    "selected",
                    "paired",
                    "incomplete_pairs",
                    "binary_agreement",
                    "kappa",
                    "spearman",
                    "mean_absolute_probability_gap",
                )
            }
        )
        print("\nLabels: OpenAI rows, JEV columns")
        grid(
            [dict(openai=k, **v) for k, v in obj["three_way_matrix"].items()],
            [
                ("openai", "OpenAI / JEV", 16),
                ("relevant", "Relevant", 12),
                ("review", "Review", 12),
                ("not_relevant", "Not relevant", 14),
            ],
        )
        print(
            f"Thresholds: {obj['thresholds']['low']} / {obj['thresholds']['high']}; binary {obj['thresholds']['binary']}"
        )
        print("Agreement is not accuracy. Use --format json for the complete metrics.")
        return
    stats(obj)


class Progress:
    """At most four refreshes/second; no per-batch logs or stdout writes."""

    def __init__(self, store, run, mode="auto", stream=None):
        self.store, self.run = store, run
        self.stream = stream if stream is not None else sys.stderr
        self.enabled = mode != "never"
        self.animate = mode == "always" or (mode == "auto" and self.stream.isatty())
        self.providers = store.run(run)["config"]["providers"]
        self.messages = {}
        self.drawn = False
        self.started = time.monotonic()

    def notify(self, message):
        # Engine failures remain visible without interrupting the progress display.
        if "request failed" in message or "budget share exhausted" in message:
            name = message.split(":", 1)[0]
            self.messages[name] = message.split(":", 1)[-1].strip()

    def draw(self, final=False):
        if not self.enabled or (not self.animate and not final):
            return
        counts = {p: {} for p in self.providers}
        for r in self.store.db.execute(
            "SELECT provider,status,COUNT(*) AS n FROM results WHERE run=? GROUP BY provider,status",
            (self.run,),
        ):
            counts[r["provider"]][r["status"]] = r["n"]
        if self.drawn and self.animate:
            self.stream.write(f"\x1b[{len(self.providers)}A")
        width = max(30, shutil.get_terminal_size((120, 24)).columns - 1)
        for p in self.providers:
            c = counts[p]
            eligible = sum(c.values()) - c.get("missing_text", 0)
            ok = c.get("ok", 0)
            proportion = ok / eligible if eligible else 0
            bars = int(20 * proportion)
            state = self.messages.get(p, "")
            line = f'{p.upper():6} [{"#"*bars}{"-"*(20-bars)}] {ok}/{eligible} scored'
            if c.get("missing_text"):
                line += f" | {c['missing_text']} missing"
            for k in ("failed", "refused", "oversized"):
                if c.get(k):
                    line += f" | {c[k]} {k}"
            line += f" | {time.monotonic()-self.started:.1f}s"
            if state:
                line += " | " + state
            if self.animate:
                self.stream.write("\r\x1b[2K")
            self.stream.write(clean(line)[:width] + "\n")
        self.stream.flush()
        self.drawn = True

    async def poll(self):
        while True:
            self.draw()
            await asyncio.sleep(0.25)
