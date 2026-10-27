"""Offline result selection and terminal presentation, shared with exports."""

import unicodedata
from .compare import joined


def clean(value):
    # Source text must not inject terminal escape sequences or control characters.
    return "".join(
        c if c in "\n\t" or not unicodedata.category(c).startswith("C") else " "
        for c in str(value)
    )


def table(rows, columns):
    """Columns are (key, heading, maximum width). No third-party UI dependencies."""
    cells = [
        [
            (" ".join(clean(r.get(k, "") if r.get(k) is not None else "—").split()))
            for k, _, _ in columns
        ]
        for r in rows
    ]
    widths = [
        min(cap, max([len(title)] + [len(r[i]) for r in cells]))
        for i, (_, title, cap) in enumerate(columns)
    ]

    def line(values):
        return "  ".join(
            (v if len(v) <= w else v[: w - 1] + "…").ljust(w)
            for v, w in zip(values, widths)
        ).rstrip()

    print(line([c[1] for c in columns]))
    print(line(["-" * w for w in widths]))
    for row in cells:
        print(line(row))
    if not rows:
        print("(no matching results)")


def select(store, run, args):
    rows = joined(store, run, args.low, args.high)
    fields = list(rows[0]) if rows else ["id", "title", "authors", "link"]
    items = {r["id"]: r for r in store.items(run)}
    if args.include_text:
        fields.append("full_text")
        for r in rows:
            r["full_text"] = items[r["id"]]["full_text"]
    if args.view == "retained":
        rows = [r for r in rows if r["retain_for_review"]]
    elif args.view != "all":
        rows = [r for r in rows if r["comparison_bucket"] == args.view]
    if args.contains:
        query = args.contains.casefold()
        rows = [
            r for r in rows if query in "\n".join(items[r["id"]].values()).casefold()
        ]
    selected = store.run(run)["config"]["providers"]
    if args.status:
        rows = [
            r for r in rows if any(r[p + "_status"] == args.status for p in selected)
        ]
    sort = args.sort or selected[0]
    if sort in ("openai", "jev") and sort not in selected:
        raise ValueError("Sort provider was not selected for this run")
    if sort == "gap" and len(selected) != 2:
        raise ValueError("Gap sorting requires both providers")
    if sort in ("id", "title"):
        rows.sort(
            key=lambda r: (r[sort].casefold(), r["id"]), reverse=args.ascending is False
        )
    else:
        key = "probability_gap" if sort == "gap" else sort + "_probability"
        rows.sort(
            key=lambda r: (
                r.get(key) is None,
                (r.get(key) or 0) * (1 if args.ascending else -1),
                r["id"],
            )
        )
    return rows, fields


def result_table(rows, providers):
    display = []
    for row in rows:
        r = dict(row)
        for p in providers:
            v = r[p + "_probability"]
            r[p + "_score"] = f"{v:.3f}" if v is not None else "—"
            r[p + "_decision"] = r[p + "_label"] or r[p + "_status"]
        display.append(r)
    cols = [("id", "ID", 18), ("title", "Title", 52)]
    for p in providers:
        cols.extend(
            [(p + "_score", p.upper(), 8), (p + "_decision", "Decision/status", 16)]
        )
    cols.append(("comparison_bucket", "Comparison", 20))
    table(display, cols)
