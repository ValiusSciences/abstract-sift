"""Bounded concurrent provider workers with durable attempts and budget reservations."""

import asyncio
from collections import deque
import math
from contextlib import contextmanager
from email.utils import parsedate_to_datetime
import json
import os
from pathlib import Path
import random
import time
import uuid
from .core import (
    PROVIDERS,
    RUBRIC_VERSION,
    digest,
    dollars,
    encoded,
    pack,
    payload,
    parse_answers,
    token_bound,
    usage_cost,
)


class HTTPFailure(Exception):
    def __init__(self, status, retry_after=0):
        super().__init__(f"HTTP {status}")
        self.status, self.retry_after = status, retry_after


class Transport:
    def __init__(self, keys):
        self.keys = keys
        self.clients = {}

    async def __aenter__(self):
        import httpx

        self.clients = {
            p: httpx.AsyncClient(
                timeout=90,
                follow_redirects=False,
                limits=httpx.Limits(max_connections=16, max_keepalive_connections=16),
            )
            for p in self.keys
        }
        return self

    async def __aexit__(self, *args):
        await asyncio.gather(*(c.aclose() for c in self.clients.values()))

    async def send(self, provider, body):
        response = await self.clients[provider.name].post(
            provider.url,
            headers={"Authorization": "Bearer " + self.keys[provider.name]},
            json=body,
        )
        if response.status_code != 200:
            raw = response.headers.get("retry-after", "0")
            try:
                delay = float(raw)
            except ValueError:
                try:
                    delay = max(0, parsedate_to_datetime(raw).timestamp() - time.time())
                except (ValueError, TypeError):
                    delay = 0
            raise HTTPFailure(
                response.status_code, max(0, delay) if math.isfinite(delay) else 0
            )
        obj = response.json()
        if not isinstance(obj, dict):
            raise ValueError("Invalid response object")
        return obj, response.headers.get(
            "x-request-id", response.headers.get("x-typesafe-request-id", "")
        )


@contextmanager
def run_lock(store, run):
    import fcntl

    path = store.directory / (run + ".lock")
    with path.open("a") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("This run is already active") from None
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


class UsageEstimator:
    """Use observed provider usage with headroom; byte bounds still reserve dollars."""

    def __init__(self, store, run, provider):
        self.ratios = []
        for row in store.db.execute(
            "SELECT reservation,usage FROM attempts WHERE run=? AND provider=? AND usage IS NOT NULL ORDER BY started DESC LIMIT 100",
            (run, provider.name),
        ):
            try:
                usage = json.loads(row["usage"])
                self.observe(
                    row["reservation"] // provider.nano_per_token,
                    usage.get("input_tokens"),
                )
            except (TypeError, ValueError, AttributeError):
                pass

    def observe(self, bound, actual):
        if (
            isinstance(actual, int)
            and not isinstance(actual, bool)
            and actual > 0
            and bound > 0
        ):
            self.ratios.append(actual / bound)
            self.ratios = self.ratios[-100:]

    def estimate(self, bound):
        # Never pretend a tokenizer is available. Start conservatively, then adapt.
        ratio = max(1.25 * max(self.ratios), 0.25) if self.ratios else 1
        return max(1, math.ceil(bound * ratio))


class Limiter:
    def __init__(self, rpm, tpm, clock=time.monotonic):
        self.rpm, self.tpm = rpm, tpm
        self.events = []
        self.condition = asyncio.Condition()
        self.cooldown = 0
        self.clock = clock

    async def acquire(self, tokens):
        if tokens > self.tpm:
            raise ValueError("Batch exceeds configured token-per-minute budget")
        async with self.condition:
            while True:
                now = self.clock()
                self.events = [e for e in self.events if now - e[0] < 60]
                capacity = (
                    len(self.events) < self.rpm
                    and sum(e[1] for e in self.events) + tokens <= self.tpm
                )
                if now >= self.cooldown and capacity:
                    event = [now, tokens]
                    self.events.append(event)
                    return event
                waits = []
                if now < self.cooldown:
                    waits.append(self.cooldown - now)
                if not capacity and self.events:
                    waits.append(60 - (now - self.events[0][0]))
                delay = max(0.01, max(waits, default=0.05))
                try:
                    await asyncio.wait_for(self.condition.wait(), delay)
                except asyncio.TimeoutError:
                    pass

    async def reconcile(self, event, actual):
        if isinstance(actual, int) and not isinstance(actual, bool) and actual >= 0:
            async with self.condition:
                event[1] = actual
                self.condition.notify_all()

    async def backoff(self, seconds):
        async with self.condition:
            self.cooldown = max(self.cooldown, self.clock() + seconds)
            self.condition.notify_all()


def write_result(
    store, run, provider, item, status, error="", probability=None, model="", origin=""
):
    store.db.execute(
        "UPDATE results SET status=?,probability=?,model=?,error=?,cache_origin=? WHERE run=? AND id=? AND provider=?",
        (status, probability, model, error, origin, run, item["id"], provider),
    )


def save_reports(store, run):
    directory = store.directory / "runs" / run
    directory.mkdir(parents=True, exist_ok=True)
    for name, obj in [
        ("run-summary.json", store.summary(run)),
        ("cost-summary.json", store.cost(run)),
    ]:
        temp = directory / (name + ".part")
        temp.write_text(json.dumps(obj, indent=2) + "\n")
        temp.replace(directory / name)
    temp = directory / "request-usage.jsonl.part"
    with temp.open("w") as f:
        for r in store.db.execute(
            "SELECT * FROM attempts WHERE run=? ORDER BY started", (run,)
        ):
            f.write(json.dumps(dict(r)) + "\n")
    temp.replace(directory / "request-usage.jsonl")


async def evaluate(store, run_id, allowance, transport, progress=lambda x: None):
    """Caller holds run_lock. All DB and reservation changes occur on this event loop."""
    run = store.run(run_id)
    cfg = run["config"]
    if cfg["rubric"] != RUBRIC_VERSION:
        raise ValueError("Rubric changed; start a new run")
    for p in cfg["providers"]:
        if (
            cfg["pricing"][p]["model"] != PROVIDERS[p].model
            or cfg["pricing"][p]["nano_per_input_token"] != PROVIDERS[p].nano_per_token
        ):
            raise ValueError(
                "Model/pricing changed; start a new run to preserve provenance"
            )
    invocation = "inv_" + uuid.uuid4().hex
    with store.db:
        store.db.execute(
            "UPDATE attempts SET state='unknown',error='interrupted_before_reconciliation' WHERE run=? AND state='pending'",
            (run_id,),
        )
        store.db.execute(
            "INSERT INTO invocations VALUES (?,?,?,?,?)",
            (invocation, run_id, time.time(), None, allowance),
        )
        store.db.execute("UPDATE runs SET status='running' WHERE id=?", (run_id,))
        store.db.execute(
            "CREATE TABLE IF NOT EXISTS invocation_settings (invocation TEXT PRIMARY KEY, settings TEXT)"
        )
        store.db.execute(
            "INSERT INTO invocation_settings VALUES (?,?)",
            (
                invocation,
                encoded(
                    {
                        k: cfg[k]
                        for k in ("concurrency", "batch_size", "rpm", "tpm", "retries")
                    }
                ),
            ),
        )
    # Equal shares protect paired coverage; explicit caps may reduce a provider's share.
    caps = {
        p: min(
            allowance // len(cfg["providers"]),
            cfg.get("provider_caps", {}).get(p, allowance),
        )
        for p in cfg["providers"]
    }
    held = {p: 0 for p in cfg["providers"]}
    halted = {p: False for p in cfg["providers"]}
    in_flight = {p: 0 for p in cfg["providers"]}
    budget_changed = asyncio.Condition()
    items = store.items(run_id)
    existing = {(r["provider"], r["id"]): r for r in store.results(run_id)}

    async def pipeline(name):
        provider = PROVIDERS[name]
        pending = []
        with store.db:
            for item in items:
                prev = existing[(name, item["id"])]
                if prev["status"] in ("ok", "missing_text", "refused", "oversized"):
                    continue
                ck = store.cache_key(run, name, item)
                cached = store.db.execute(
                    "SELECT * FROM cache WHERE key=?", (ck,)
                ).fetchone()
                if cached and not cfg.get("no_cache", False):
                    write_result(
                        store,
                        run_id,
                        name,
                        item,
                        "ok",
                        probability=cached["probability"],
                        model=cached["model"],
                        origin=cached["run"],
                    )
                else:
                    write_result(store, run_id, name, item, "queued")
                    pending.append(item)
        estimator = UsageEstimator(store, run_id, provider)
        _, oversized = pack(provider, run["query"], pending, cfg["batch_size"])
        oversized_ids = {i["id"] for i in oversized}
        with store.db:
            for item in oversized:
                write_result(
                    store,
                    run_id,
                    name,
                    item,
                    "oversized",
                    "conservative_context_bound_exceeded",
                )
        queue = deque(i for i in pending if i["id"] not in oversized_ids)

        def next_batch():
            batch = []
            while queue and len(batch) < min(cfg["batch_size"], provider.max_questions):
                trial = batch + [queue[0]]
                bound = token_bound(payload(provider, run["query"], trial)[0])
                if batch and estimator.estimate(bound) > min(
                    provider.request_tokens, cfg["tpm"]
                ):
                    break
                batch.append(queue.popleft())
            return batch

        limiter = Limiter(cfg["rpm"], cfg["tpm"])

        async def worker():
            while not halted[name]:
                batch = next_batch()
                if not batch:
                    return
                body, names = payload(provider, run["query"], batch)
                bound = token_bound(body)
                tokens = estimator.estimate(bound)
                reservation = bound * provider.nano_per_token
                if tokens > cfg["tpm"]:
                    with store.db:
                        for item in batch:
                            write_result(
                                store,
                                run_id,
                                name,
                                item,
                                "failed",
                                "batch_exceeds_configured_tpm",
                            )
                    continue
                for ordinal in range(cfg["retries"] + 1):
                    async with budget_changed:
                        while (
                            held[name] + reservation > caps[name]
                            and in_flight[name]
                            and not halted[name]
                        ):
                            await budget_changed.wait()
                        if halted[name]:
                            return
                        if held[name] + reservation > caps[name]:
                            halted[name] = True
                            progress(
                                f"{name}: budget share exhausted; unfinished items saved"
                            )
                            budget_changed.notify_all()
                            return
                        held[name] += reservation
                        in_flight[name] += 1
                    attempt = None
                    response = None
                    try:
                        ticket = await limiter.acquire(tokens)
                        if halted[name]:
                            held[name] -= reservation
                            return
                        attempt = "att_" + uuid.uuid4().hex
                        with store.db:
                            store.db.execute(
                                "INSERT INTO attempts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                                (
                                    attempt,
                                    run_id,
                                    invocation,
                                    name,
                                    digest(body),
                                    ordinal,
                                    time.time(),
                                    None,
                                    "pending",
                                    reservation,
                                    None,
                                    None,
                                    "",
                                    "",
                                ),
                            )
                        response, request_id = await transport.send(provider, body)
                        usage = response.get("usage")
                        if not isinstance(usage, dict):
                            usage = {}
                        actual = (
                            usage.get("input_tokens")
                            if isinstance(usage, dict)
                            else None
                        )
                        estimator.observe(bound, actual)
                        await limiter.reconcile(ticket, actual)
                        cost = usage_cost(provider, response)
                        with store.db:
                            store.db.execute(
                                "UPDATE attempts SET finished=?,state=?,cost=?,usage=?,request_id=? WHERE id=?",
                                (
                                    time.time(),
                                    "accounted" if cost is not None else "unknown",
                                    cost,
                                    encoded(usage),
                                    request_id,
                                    attempt,
                                ),
                            )
                        if cost is not None:
                            held[name] += cost - reservation
                        parsed = parse_answers(provider, response, names)
                        with store.db:
                            for r in parsed:
                                item = next(i for i in batch if i["id"] == r["id"])
                                write_result(
                                    store,
                                    run_id,
                                    name,
                                    item,
                                    r["status"],
                                    r["error"],
                                    r["probability"],
                                    r["model"],
                                )
                                if r["status"] == "ok" and r["model"] == provider.model:
                                    store.db.execute(
                                        "INSERT OR REPLACE INTO cache VALUES (?,?,?,?)",
                                        (
                                            store.cache_key(run, name, item),
                                            run_id,
                                            r["probability"],
                                            r["model"],
                                        ),
                                    )
                        progress(
                            f"{name}: finished {len(batch)} abstracts; invocation exposure ${dollars(held[name])}"
                        )
                        break
                    except asyncio.CancelledError:
                        if attempt is None:
                            held[name] -= reservation
                        with store.db:
                            store.db.execute(
                                "UPDATE attempts SET state=CASE WHEN state='pending' THEN 'unknown' ELSE state END,error='canceled' WHERE id=?",
                                (attempt,),
                            )
                        raise
                    except Exception as exc:
                        if attempt is None:
                            held[name] -= reservation
                        # Never retain exception text or HTTP bodies (may contain credentials/source).
                        error = (
                            f"http_{exc.status}"
                            if isinstance(exc, HTTPFailure)
                            else type(exc).__name__
                        )
                        with store.db:
                            store.db.execute(
                                "UPDATE attempts SET state=CASE WHEN state='pending' THEN 'unknown' ELSE state END,finished=?,error=? WHERE id=?",
                                (time.time(), error, attempt),
                            )
                            for item in batch:
                                write_result(store, run_id, name, item, "failed", error)
                        fatal = isinstance(exc, HTTPFailure) and exc.status in (
                            401,
                            402,
                            403,
                        )
                        if fatal:
                            halted[name] = True
                        retryable = response is None and (
                            not isinstance(exc, HTTPFailure)
                            or exc.status in (429, 500, 502, 503, 504, 529)
                        )
                        if fatal or not retryable or ordinal == cfg["retries"]:
                            progress(
                                f"{name}: request failed ({error}); checkpoint retained"
                            )
                            break
                        delay = max(
                            2**ordinal + random.random(),
                            exc.retry_after if isinstance(exc, HTTPFailure) else 0,
                        )
                        await limiter.backoff(delay)
                        await asyncio.sleep(delay)
                    finally:
                        async with budget_changed:
                            in_flight[name] -= 1
                            budget_changed.notify_all()
                save_reports(store, run_id)

        await asyncio.gather(*(worker() for _ in range(cfg["concurrency"])))

    tasks = [asyncio.create_task(pipeline(p)) for p in cfg["providers"]]
    interrupted = False
    try:
        await asyncio.gather(*tasks)
    except BaseException:
        interrupted = True
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise
    finally:
        rs = store.results(run_id)
        complete = all(r["status"] in ("ok", "missing_text") for r in rs)
        with store.db:
            store.db.execute(
                "UPDATE invocations SET finished=? WHERE id=?",
                (time.time(), invocation),
            )
            store.db.execute(
                "UPDATE runs SET status=? WHERE id=?",
                (
                    (
                        "canceled"
                        if interrupted
                        else "complete" if complete else "partial"
                    ),
                    run_id,
                ),
            )
        save_reports(store, run_id)
    return 0 if complete else 2
