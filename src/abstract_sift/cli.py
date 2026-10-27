"""CLI. Offline operations never construct an API client."""

import argparse
import asyncio
import csv
import json
import os
from pathlib import Path
import re
import sys
import sqlite3
from .core import PROVIDERS, dollars, money, pack, payload, token_bound
from .store import Store
from .engine import Transport, evaluate, run_lock
from .compare import joined, report, compare_runs
from .explore import select, result_table, table, clean
from .display import present, Progress
from .site import build_site


def load_env(path):
    """Minimal literal dotenv loader; never executes shell substitutions or prints values."""
    if not path.exists():
        return
    allowed = {"OPENAI_API_KEY", "TYPESAFE_API_KEY", "JEV_API_KEY"}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:]
        key, sep, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if sep and key in allowed:
            if len(value) > 1 and value[0] == value[-1] and value[0] in ('"', "'"):
                value = value[1:-1]
            os.environ.setdefault(key, value)


def keys_for(providers, env_file):
    load_env(env_file)
    keys = {}
    for p in providers:
        value = (
            os.environ.get("OPENAI_API_KEY")
            if p == "openai"
            else os.environ.get("TYPESAFE_API_KEY") or os.environ.get("JEV_API_KEY")
        )
        if not value:
            raise ValueError(
                "Missing credential for "
                + p
                + "; set its API key in the environment or --env-file"
            )
        keys[p] = value
    return keys


def emit(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False))


def estimate(query, items, providers, batch_size):
    out = {}
    for p in providers:
        cfg = PROVIDERS[p]
        usable = [r for r in items if r["full_text"].strip()]
        batches, oversized = pack(cfg, query, usable, batch_size)
        bounds = sum(token_bound(payload(cfg, query, b)[0]) for b in batches)
        out[p] = dict(
            requests=len(batches),
            eligible=len(usable) - len(oversized),
            oversized=len(oversized),
            missing_text=len(items) - len(usable),
            conservative_input_token_bound=bounds,
            uncached_cost_upper_estimate_usd=dollars(bounds * cfg.nano_per_token),
            model=cfg.model,
        )
    return dict(
        providers=out,
        note="UTF-8 byte bound, not actual tokenization. Excludes retries and unknown billing modifiers; no requests sent.",
    )


def add_scoring(p):
    p.add_argument("--corpus", required=True)
    p.add_argument("--query-file", type=Path, required=True)
    p.add_argument("--provider", choices=["openai", "jev", "both"], required=True)
    p.add_argument("--batch-size", type=int, default=16)
    p.add_argument(
        "--limit", type=int, default=0, help="Optional explicit subset; 0 means all"
    )


def add_exploration(p):
    p.add_argument(
        "--view",
        choices=[
            "all",
            "retained",
            "discordant",
            "uncertainty",
            "incomplete_pair",
            "both_relevant",
            "both_not_relevant",
            "both_review",
        ],
        default="all",
    )
    p.add_argument(
        "--sort", choices=["openai", "jev", "gap", "id", "title"], default=None
    )
    p.add_argument(
        "--ascending",
        action="store_true",
        default=None,
        help="Sort scores low to high (text defaults A–Z)",
    )
    p.add_argument(
        "--contains",
        help="Case-insensitive substring in ID, title, authors, full text or link",
    )
    p.add_argument(
        "--status",
        choices=["ok", "queued", "failed", "missing_text", "oversized", "refused"],
        help="Match this status in any selected provider",
    )
    p.add_argument(
        "--include-text",
        action="store_true",
        help="Include full abstract text in JSON or exported table",
    )


def parser():
    ap = argparse.ArgumentParser(
        description="Local abstract screening with OpenAI Decisions and TypeSafe JEV."
    )
    ap.add_argument(
        "--data-dir",
        type=Path,
        default=Path(
            os.environ.get(
                "ABSTRACT_SIFT_HOME", Path.home() / ".local/share/abstract-sift"
            )
        ),
    )
    ap.add_argument(
        "--env-file",
        type=Path,
        default=Path(".env"),
        help="Literal key file; default .env in the current directory",
    )
    sub = ap.add_subparsers(dest="command", required=True)
    p = sub.add_parser("compare-runs")
    p.add_argument("before")
    p.add_argument("after")
    p.add_argument("--low", type=float, default=0.3)
    p.add_argument("--high", type=float, default=0.7)
    p.add_argument(
        "--top", type=int, default=20, help="Number of largest score changes to display"
    )
    p = sub.add_parser(
        "site", help="Generate a self-contained local HTML explorer for one run"
    )
    p.add_argument("run")
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--title")
    p.add_argument("--brand", default="Valius Sciences")
    p.add_argument("--description")
    p.add_argument(
        "--force", action="store_true", help="Replace an existing HTML output"
    )
    p = sub.add_parser("runs")
    p = sub.add_parser("show")
    p.add_argument("run")
    p.add_argument("id")
    p = sub.add_parser("import")
    p.add_argument("path", type=Path)
    p.add_argument("--corpus", required=True)
    p = sub.add_parser("search")
    p.add_argument("--corpus", required=True)
    p.add_argument("--query-file", type=Path, required=True)
    p.add_argument("--top", type=int, default=30)
    p = sub.add_parser("estimate")
    add_scoring(p)
    p = sub.add_parser("score")
    add_scoring(p)
    p.add_argument("--max-cost-usd", required=True)
    p.add_argument(
        "--concurrency",
        type=int,
        default=4,
        help="Concurrent requests per provider, 1–16",
    )
    p.add_argument(
        "--rpm",
        type=int,
        default=120,
        help="Conservative request budget per minute per provider",
    )
    p.add_argument(
        "--tpm",
        type=int,
        default=600000,
        help="Conservative token budget per minute per provider",
    )
    p.add_argument("--retries", type=int, default=2)
    p.add_argument("--openai-budget-usd")
    p.add_argument("--jev-budget-usd")
    p.add_argument(
        "--no-cache",
        action="store_true",
        help="Score every eligible item again; bypass local score reuse (incurs new API costs)",
    )
    p = sub.add_parser("resume")
    p.add_argument("run")
    p.add_argument("--max-additional-cost-usd", required=True)
    p.add_argument("--concurrency", type=int)
    p.add_argument("--batch-size", type=int)
    p.add_argument("--rpm", type=int)
    p.add_argument("--tpm", type=int)
    for cmd in ("status", "results", "export", "compare", "cost"):
        p = sub.add_parser(cmd)
        p.add_argument("run", nargs="?" if cmd == "cost" else None)
        if cmd == "cost":
            p.add_argument("--all", action="store_true")
        if cmd in ("results", "export", "compare"):
            p.add_argument("--low", type=float, default=0.3)
            p.add_argument("--high", type=float, default=0.7)
        if cmd == "compare":
            p.add_argument("--threshold", type=float, default=0.5)
        if cmd in ("results", "export"):
            add_exploration(p)
        if cmd == "results":
            p.add_argument("--top", type=int, default=50, help="Rows per page")
            p.add_argument("--page", type=int, default=1)
        if cmd == "export":
            p.add_argument("--format", choices=["csv", "tsv", "jsonl"], default="csv")
            p.add_argument("--output", type=Path, required=True)
    for name, p in sub.choices.items():
        output = p.add_mutually_exclusive_group()
        flags = (
            ["--output-format"] if name == "export" else ["--format", "--output-format"]
        )
        output.add_argument(
            *flags,
            dest="output_format",
            choices=["table", "json"],
            default="table",
            help="Terminal output format (default: table)",
        )
        output.add_argument(
            "--json", action="store_true", help="Alias for JSON terminal output"
        )
        if name in ("score", "resume"):
            p.add_argument(
                "--progress",
                choices=["auto", "always", "never"],
                default="auto",
                help="Progress on stderr; auto animates only in a terminal",
            )
    return ap


def update_runtime(store, run, overrides):
    cfg = store.run(run)["config"]
    cfg.update(overrides)
    if (
        not 1 <= cfg["concurrency"] <= 16
        or not 1 <= cfg["batch_size"] <= 400
        or cfg["rpm"] < 1
        or cfg["tpm"] < 1
    ):
        raise ValueError("Invalid concurrency, batch size, or rate limits")
    with store.db:
        store.db.execute("UPDATE runs SET config=? WHERE id=?", (json.dumps(cfg), run))


async def live(store, run, budget, keys, mode="auto"):
    progress = Progress(store, run, mode)
    async with Transport(keys) as transport:
        task = asyncio.create_task(progress.poll())
        try:
            return await evaluate(store, run, budget, transport, progress.notify)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            progress.draw(final=True)


def execute(args, store):
    args.json = args.json or args.output_format == "json"

    def output(obj):
        if args.json:
            emit(obj)
        else:
            present(obj, args.command)

    if hasattr(args, "low") and not 0 <= args.low < args.high <= 1:
        raise ValueError("Require 0 <= low < high <= 1")
    if hasattr(args, "threshold") and not 0 <= args.threshold <= 1:
        raise ValueError("Threshold must be in [0,1]")
    if args.command == "site":
        output(
            build_site(
                store,
                args.run,
                args.output,
                args.title,
                args.brand,
                args.description,
                args.force,
            )
        )
        return 0
    if args.command == "compare-runs":
        if args.top < 0:
            raise ValueError("Top must be nonnegative")
        output(
            compare_runs(store, args.before, args.after, args.low, args.high, args.top)
        )
        return 0
    if args.command == "runs":
        rows = [
            dict(r)
            for r in store.db.execute(
                "SELECT id AS run,created,corpus,status FROM runs ORDER BY created DESC"
            )
        ]
        if args.json:
            output(rows)
        else:
            from datetime import datetime

            for r in rows:
                r["created"] = (
                    datetime.fromtimestamp(r["created"])
                    .astimezone()
                    .isoformat(timespec="seconds")
                )
            table(
                rows,
                [
                    ("run", "Run", 24),
                    ("created", "Created", 25),
                    ("corpus", "Corpus", 24),
                    ("status", "Status", 12),
                ],
            )
        return 0
    if args.command == "show":
        rows = joined(store, args.run)
        row = next((r for r in rows if r["id"] == args.id), None)
        if row is None:
            raise ValueError("Unknown abstract ID in this run")
        row["full_text"] = next(
            r["full_text"] for r in store.items(args.run) if r["id"] == args.id
        )
        if args.json:
            output(row)
        else:
            print(clean(row["id"] + " — " + row["title"]))
            print(clean(row["authors"]) + "\n" + clean(row["link"]) + "\n")
            result_table([row], store.run(args.run)["config"]["providers"])
            print("\n" + clean(row["full_text"]))
        return 0
    if args.command == "import":
        output(store.read_corpus(args.path, args.corpus))
        return 0
    if args.command == "search":
        if args.top < 1:
            raise ValueError("Top must be a positive integer")
        words = set(re.findall(r"\w+", args.query_file.read_text().lower()))
        rows = store.corpus(args.corpus)
        for r in rows:
            r["search_matches"] = sum(
                3 * r["title"].lower().count(w) + r["full_text"].lower().count(w)
                for w in words
            )
        output(
            dict(
                kind="lexical_preview_not_model_scores",
                results=sorted(rows, key=lambda r: (-r["search_matches"], r["id"]))[
                    : args.top
                ],
            )
        )
        return 0
    if args.command in ("estimate", "score"):
        if args.limit < 0 or not 1 <= args.batch_size <= 400:
            raise ValueError("Invalid limit or batch size")
        query = args.query_file.read_text().strip()
        if not query:
            raise ValueError("Query file is empty")
        rows = store.corpus(args.corpus)
        if args.limit:
            rows = rows[: args.limit]
        providers = ["openai", "jev"] if args.provider == "both" else [args.provider]
        summary = estimate(query, rows, providers, args.batch_size)
        if args.command == "estimate":
            output(summary)
            return 0
        if (
            not 1 <= args.concurrency <= 16
            or args.rpm < 1
            or args.tpm < 1
            or not 0 <= args.retries <= 5
        ):
            raise ValueError("Invalid concurrency, rate limits or retry count")
        keys = keys_for(providers, args.env_file)
        budget = money(args.max_cost_usd)
        caps = {
            p: money(getattr(args, p + "_budget_usd"))
            for p in providers
            if getattr(args, p + "_budget_usd")
        }
        config = dict(
            providers=providers,
            batch_size=args.batch_size,
            concurrency=args.concurrency,
            rpm=args.rpm,
            tpm=args.tpm,
            retries=args.retries,
            provider_caps=caps,
            selection_limit=args.limit,
            no_cache=args.no_cache,
        )
        run = store.create_run(args.corpus, query, config, rows)
        print("Run: " + run, file=sys.stderr, flush=True)
        with run_lock(store, run):
            code = asyncio.run(live(store, run, budget, keys, args.progress))
        output(dict(summary=store.summary(run), cost=store.cost(run)))
        return code
    if args.command == "resume":
        r = store.run(args.run)
        keys = keys_for(r["config"]["providers"], args.env_file)
        budget = money(args.max_additional_cost_usd)
        with run_lock(store, args.run):
            overrides = {
                k: getattr(args, k)
                for k in ("concurrency", "batch_size", "rpm", "tpm")
                if getattr(args, k) is not None
            }
            update_runtime(store, args.run, overrides)
            code = asyncio.run(live(store, args.run, budget, keys, args.progress))
        output(dict(summary=store.summary(args.run), cost=store.cost(args.run)))
        return code
    if args.command == "cost":
        if args.all:
            output(
                [
                    store.cost(r[0])
                    for r in store.db.execute("SELECT id FROM runs ORDER BY created")
                ]
            )
        elif args.run:
            output(store.cost(args.run))
        else:
            raise ValueError("Specify RUN_ID or --all")
        return 0
    store.run(args.run)
    if args.command == "status":
        output(store.summary(args.run))
        return 0
    if args.command == "compare":
        output(report(store, args.run, args.low, args.high, args.threshold))
        return 0
    rows, fields = select(store, args.run, args)
    if args.command == "results":
        if args.top < 1 or args.page < 1:
            raise ValueError("Page and top must be positive integers")
        start = (args.page - 1) * args.top
        page = rows[start : start + args.top]
        if args.json:
            output(page)
        else:
            result_table(page, store.run(args.run)["config"]["providers"])
            print(
                f"\n{len(rows)} matching abstracts; page {args.page}; showing {len(page)}. Use --page to browse, show RUN_ID ID for full text."
            )
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temp = args.output.with_suffix(args.output.suffix + ".part")
    with temp.open("w", encoding="utf-8", newline="") as f:
        if args.format == "jsonl":
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        else:
            writer = csv.DictWriter(
                f,
                fieldnames=fields,
                quoting=csv.QUOTE_ALL,
                delimiter="\t" if args.format == "tsv" else ",",
            )
            writer.writeheader()
            for r in rows:
                writer.writerow(
                    {
                        k: (
                            "'" + v
                            if isinstance(v, str)
                            and (
                                v.lstrip().startswith(("=", "+", "-", "@"))
                                or v.startswith(("\t", "\r", "\n"))
                            )
                            else v
                        )
                        for k, v in r.items()
                    }
                )
    temp.replace(args.output)
    output(dict(output=str(args.output), rows=len(rows)))
    return 0


def main():
    os.umask(0o077)
    args = parser().parse_args()
    store = None
    try:
        store = Store(args.data_dir)
        return execute(args, store)
    except KeyboardInterrupt:
        print(
            "Canceled; completed results and request costs are checkpointed. Use resume.",
            file=sys.stderr,
        )
        return 130
    except (ValueError, OSError, ImportError, sqlite3.Error) as exc:
        # Data or HTTP exception text must never leak secrets or entire source documents.
        message = str(exc) if type(exc) is ValueError else type(exc).__name__
        print("Error: " + message, file=sys.stderr)
        return 1
    finally:
        if store:
            store.close()


if __name__ == "__main__":
    raise SystemExit(main())
