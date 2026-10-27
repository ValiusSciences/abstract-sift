"""Durable, private local state. No credentials stored."""

import csv
import json
from pathlib import Path
import sqlite3
import time
import uuid
from .core import digest, encoded, dollars, PROVIDERS, RUBRIC_VERSION

SCHEMA = """
CREATE TABLE IF NOT EXISTS corpora (name TEXT PRIMARY KEY, hash TEXT, rows_json TEXT);
CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, created REAL, corpus TEXT, query TEXT, config TEXT, status TEXT);
CREATE TABLE IF NOT EXISTS items (run TEXT, id TEXT, payload TEXT, PRIMARY KEY(run,id));
CREATE TABLE IF NOT EXISTS results (run TEXT, id TEXT, provider TEXT, status TEXT, probability REAL, model TEXT, error TEXT, cache_origin TEXT, PRIMARY KEY(run,id,provider));
CREATE TABLE IF NOT EXISTS invocations (id TEXT PRIMARY KEY, run TEXT, started REAL, finished REAL, allowance INTEGER);
CREATE TABLE IF NOT EXISTS attempts (id TEXT PRIMARY KEY, run TEXT, invocation TEXT, provider TEXT, batch_hash TEXT, ordinal INTEGER, started REAL, finished REAL, state TEXT, reservation INTEGER, cost INTEGER, usage TEXT, request_id TEXT, error TEXT);
CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, run TEXT, probability REAL, model TEXT);
"""


class Store:
    def __init__(self, directory):
        self.directory = Path(directory).expanduser().resolve()
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.directory / "sift.sqlite"
        self.db = sqlite3.connect(self.path, timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(SCHEMA)

    def close(self):
        self.db.close()

    def read_corpus(self, path, name):
        path = Path(path)
        with path.open(encoding="utf-8-sig", newline="") as f:
            source = (
                csv.DictReader(f)
                if path.suffix.lower() == ".csv"
                else (json.loads(line) for line in f if line.strip())
            )
            rows, seen = [], set()
            for record in source:
                if not isinstance(record, dict) or not all(
                    k in record for k in ("id", "title", "authors", "full_text", "link")
                ):
                    raise ValueError(
                        "Every record requires id, title, authors, full_text and link"
                    )
                row = {
                    k: record[k]
                    for k in ("id", "title", "authors", "full_text", "link")
                }
                if not all(isinstance(v, str) for v in row.values()):
                    raise ValueError("All five input fields must be strings")
                if (
                    not row["id"].strip()
                    or not row["title"].strip()
                    or row["id"] in seen
                ):
                    raise ValueError("Empty ID/title or duplicate ID")
                if len(encoded(row).encode()) > 2_000_000:
                    raise ValueError("Record exceeds 2 MB; inspect source")
                seen.add(row["id"])
                rows.append(row)
        if not rows:
            raise ValueError("Corpus is empty")
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO corpora VALUES (?,?,?)",
                (name, digest(rows), encoded(rows)),
            )
        return dict(
            corpus=name,
            records=len(rows),
            usable=sum(bool(r["full_text"].strip()) for r in rows),
            hash=digest(rows),
        )

    def corpus(self, name):
        row = self.db.execute("SELECT * FROM corpora WHERE name=?", (name,)).fetchone()
        if not row:
            raise ValueError("Unknown corpus")
        return json.loads(row["rows_json"])

    def create_run(self, corpus, query, config, rows):
        run = "run_" + uuid.uuid4().hex[:16]
        config = dict(
            config,
            rubric=RUBRIC_VERSION,
            corpus_hash=digest(rows),
            pricing={
                n: dict(
                    model=PROVIDERS[n].model,
                    nano_per_input_token=PROVIDERS[n].nano_per_token,
                    currency="USD",
                    checked="2026-10-26",
                    source=(
                        "https://developers.openai.com/api/docs/guides/decisions"
                        if n == "openai"
                        else "https://docs.typesafe.ai/models"
                    ),
                )
                for n in config["providers"]
            },
        )
        with self.db:
            self.db.execute(
                "INSERT INTO runs VALUES (?,?,?,?,?,?)",
                (run, time.time(), corpus, query, encoded(config), "created"),
            )
            self.db.executemany(
                "INSERT INTO items VALUES (?,?,?)",
                [(run, r["id"], encoded(r)) for r in rows],
            )
            self.db.executemany(
                "INSERT INTO results VALUES (?,?,?,?,?,?,?,?)",
                [
                    (
                        run,
                        r["id"],
                        p,
                        "queued" if r["full_text"].strip() else "missing_text",
                        None,
                        "",
                        "",
                        "",
                    )
                    for r in rows
                    for p in config["providers"]
                ],
            )
        return run

    def run(self, run):
        r = self.db.execute("SELECT * FROM runs WHERE id=?", (run,)).fetchone()
        if not r:
            raise ValueError("Unknown run ID")
        obj = dict(r)
        obj["config"] = json.loads(obj["config"])
        return obj

    def items(self, run):
        return [
            json.loads(r[0])
            for r in self.db.execute(
                "SELECT payload FROM items WHERE run=? ORDER BY id", (run,)
            )
        ]

    def results(self, run):
        return [
            dict(r)
            for r in self.db.execute(
                "SELECT * FROM results WHERE run=? ORDER BY id,provider", (run,)
            )
        ]

    def cache_key(self, run, provider, item):
        return digest(
            [
                provider,
                run["config"]["pricing"][provider]["model"],
                run["config"]["rubric"],
                run["query"],
                item,
            ]
        )

    def summary(self, run):
        r = self.run(run)
        counts = {}
        for x in self.results(run):
            p = counts.setdefault(x["provider"], {})
            p[x["status"]] = p.get(x["status"], 0) + 1
        return dict(run=run, status=r["status"], providers=counts)

    def cost(self, run):
        self.run(run)
        groups = {}
        for r in self.db.execute("SELECT * FROM attempts WHERE run=?", (run,)):
            g = groups.setdefault(
                r["provider"],
                dict(
                    attempts=0,
                    known_nano=0,
                    unknown_nano=0,
                    pending_nano=0,
                    input_tokens=0,
                    unknown_attempts=0,
                ),
            )
            g["attempts"] += 1
            if r["cost"] is not None:
                g["known_nano"] += r["cost"]
            elif r["state"] == "pending":
                g["pending_nano"] += r["reservation"]
            else:
                g["unknown_nano"] += r["reservation"]
                g["unknown_attempts"] += 1
            u = json.loads(r["usage"]) if r["usage"] else {}
            tokens = u.get("input_tokens") if isinstance(u, dict) else None
            if isinstance(tokens, int) and not isinstance(tokens, bool) and tokens >= 0:
                g["input_tokens"] += tokens
        for g in groups.values():
            for k in ("known", "unknown", "pending"):
                g[k + "_usd"] = dollars(g.pop(k + "_nano"))
        totals = {
            k: dollars(sum(int(DecimalMoney(g[k + "_usd"])) for g in groups.values()))
            for k in ("known", "unknown", "pending")
        }
        invocations = []
        for inv in self.db.execute(
            "SELECT * FROM invocations WHERE run=? ORDER BY started", (run,)
        ):
            row = dict(inv)
            if self.db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='invocation_settings'"
            ).fetchone():
                settings = self.db.execute(
                    "SELECT settings FROM invocation_settings WHERE invocation=?",
                    (inv["id"],),
                ).fetchone()
                if settings:
                    row["runtime_settings"] = json.loads(settings[0])
            row["allowance_usd"] = dollars(row.pop("allowance"))
            amounts = self.db.execute(
                "SELECT COALESCE(SUM(cost),0),COALESCE(SUM(CASE WHEN cost IS NULL THEN reservation ELSE 0 END),0) FROM attempts WHERE invocation=?",
                (inv["id"],),
            ).fetchone()
            row["known_usd"] = dollars(amounts[0])
            row["unreconciled_exposure_usd"] = dollars(amounts[1])
            invocations.append(row)
        return dict(
            run=run,
            currency="USD",
            providers=groups,
            usage_derived_usd=totals["known"],
            unknown_exposure_usd=totals["unknown"],
            inflight_reserved_usd=totals["pending"],
            invocations=invocations,
            pricing=self.run(run)["config"]["pricing"],
            billing_note="Usage-derived estimates, not a settled invoice. Unknown attempts retain estimated exposure.",
        )


def DecimalMoney(value):
    from decimal import Decimal

    return Decimal(value) * 1_000_000_000
