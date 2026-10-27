import asyncio
from datetime import datetime, timezone
from email.utils import format_datetime
import io
import json
import sqlite3
import unittest
from unittest.mock import patch
import httpx
import test_sift
from abstract_sift.core import PROVIDERS, money, token_bound, payload
from abstract_sift.engine import Transport, HTTPFailure, evaluate
from abstract_sift.cli import main


class TransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_wire_contract_and_redirects_do_not_forward_key(self):
        seen = []

        def handler(request):
            seen.append(request)
            self.assertEqual(request.headers["authorization"], "Bearer mock-key")
            self.assertEqual(request.url.host, "api.openai.com")
            return httpx.Response(
                302, headers={"location": "https://untrusted.example/"}
            )

        real_client = httpx.AsyncClient
        with patch(
            "httpx.AsyncClient",
            side_effect=lambda **kw: real_client(
                transport=httpx.MockTransport(handler), **kw
            ),
        ):
            async with Transport({"openai": "mock-key"}) as transport:
                with self.assertRaises(HTTPFailure) as caught:
                    await transport.send(PROVIDERS["openai"], {"model": "test"})
                self.assertEqual(caught.exception.status, 302)
                self.assertEqual(len(seen), 1)
                client = transport.clients["openai"]
            self.assertTrue(client.is_closed)

    async def test_success_usage_request_id_and_retry_after(self):
        for provider in PROVIDERS.values():
            async with httpx.AsyncClient(
                transport=httpx.MockTransport(
                    lambda _: httpx.Response(
                        200,
                        json={"usage": {"input_tokens": 42}},
                        headers={"x-request-id": "mock-id"},
                    )
                )
            ) as client:
                transport = Transport({"openai": "mock-key", "jev": "mock-key"})
                transport.clients[provider.name] = client
                result, request_id = await transport.send(
                    provider, {"model": provider.model}
                )
                self.assertEqual(request_id, "mock-id")
                self.assertEqual(result["usage"]["input_tokens"], 42)
        cases = [
            ("600", 600),
            ("-1", 0),
            ("nonsense", 0),
            ("nan", 0),
            ("inf", 0),
            (format_datetime(datetime.fromtimestamp(1600, timezone.utc)), 600),
        ]
        for header, expected in cases:
            async with httpx.AsyncClient(
                transport=httpx.MockTransport(
                    lambda _, header=header: httpx.Response(
                        429, headers={"retry-after": header}
                    )
                )
            ) as client:
                transport = Transport({"openai": "mock-key", "jev": "mock-key"})
                transport.clients["openai"] = client
                with patch("abstract_sift.engine.time.time", return_value=1000):
                    with self.assertRaises(HTTPFailure) as caught:
                        await transport.send(PROVIDERS["openai"], {})
                self.assertEqual(caught.exception.retry_after, expected)

    async def test_invalid_response_object(self):
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json=["bad"]))
        ) as client:
            transport = Transport({"openai": "mock-key", "jev": "mock-key"})
            transport.clients["jev"] = client
            with self.assertRaises(ValueError):
                await transport.send(PROVIDERS["jev"], {})


class ReliabilityTests(unittest.TestCase):
    setUp = test_sift.IntegrationTests.setUp
    tearDown = test_sift.IntegrationTests.tearDown
    run_case = test_sift.IntegrationTests.run_case

    def test_inflight_budget_reservations_wait_for_actual_cost(self):
        rows = [test_sift.item(str(i)) for i in range(4)]
        run = self.run_case(rows, providers=["openai"], batch_size=1, concurrency=4)
        reserve = max(
            token_bound(
                payload(PROVIDERS["openai"], "Find biomarker cancer studies", [r])[0]
            )
            * 100
            for r in rows
        )
        # Enough for all actual costs, but only one conservative reservation at once.
        allowance = reserve + 4 * 100 * 100
        fake = test_sift.FakeTransport()
        self.assertEqual(asyncio.run(evaluate(self.store, run, allowance, fake)), 0)
        self.assertEqual(len(fake.calls), 4)
        self.assertEqual(self.store.cost(run)["unknown_exposure_usd"], "0.000000000")

    def test_malformed_usage_retains_unknown_cost_without_crashing(self):
        for usage in (None, "wrong", [], {"input_tokens": True}, {"input_tokens": -10}):
            run = self.run_case(providers=["openai"], no_cache=True)
            good = test_sift.FakeTransport()

            async def send(p, b, good=good, usage=usage):
                obj, request_id = await good.send(p, b)
                obj["usage"] = usage
                return obj, request_id

            fake = test_sift.FakeTransport()
            fake.send = send
            self.assertEqual(asyncio.run(evaluate(self.store, run, 10000000, fake)), 0)
            cost = self.store.cost(run)
            self.assertEqual(cost["providers"]["openai"]["input_tokens"], 0)
            self.assertGreater(float(cost["unknown_exposure_usd"]), 0)

    def test_retry_accounted_separately(self):
        run = self.run_case(
            [test_sift.item()], providers=["openai"], concurrency=1, retries=1
        )
        good = test_sift.FakeTransport()
        attempts = 0

        async def send(p, b):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise HTTPFailure(429, 0.01)
            return await good.send(p, b)

        fake = test_sift.FakeTransport()
        fake.send = send
        with patch("abstract_sift.engine.random.random", return_value=0):
            self.assertEqual(asyncio.run(evaluate(self.store, run, 10000000, fake)), 0)
        cost = self.store.cost(run)
        self.assertEqual(cost["providers"]["openai"]["attempts"], 2)
        self.assertEqual(cost["providers"]["openai"]["unknown_attempts"], 1)
        self.assertEqual(cost["usage_derived_usd"], "0.000010000")

    def test_request_schema_failure_does_not_lose_usage(self):
        run = self.run_case([test_sift.item()], providers=["openai"])
        fake = test_sift.FakeTransport(
            lambda p, b: (
                {"model": p.model, "usage": {"input_tokens": 123}, "answers": "bad"},
                "id",
            )
        )
        self.assertEqual(asyncio.run(evaluate(self.store, run, 10000000, fake)), 2)
        self.assertEqual(self.store.cost(run)["usage_derived_usd"], "0.000012300")
        self.assertEqual(self.store.results(run)[0]["status"], "failed")

    def test_gateway_errors_retry_but_client_errors_do_not(self):
        retried = (408, 429, 500, 502, 503, 504, 520, 522, 524, 529)
        self.assertTrue(all(HTTPFailure(s).transient for s in retried))
        self.assertFalse(any(HTTPFailure(s).transient for s in (302, 400, 404, 422)))
        # Regression: one Cloudflare 520 left 11 ESMO abstracts failed without a retry.
        for status, calls, code in ((520, 2, 0), (400, 1, 2)):
            run = self.run_case(
                [test_sift.item()],
                providers=["openai"],
                concurrency=1,
                retries=1,
                no_cache=True,
            )
            good = test_sift.FakeTransport()
            seen = []

            async def send(p, b, status=status, good=good, seen=seen):
                seen.append(status)
                if len(seen) == 1:
                    raise HTTPFailure(status)
                return await good.send(p, b)

            fake = test_sift.FakeTransport()
            fake.send = send
            with patch("abstract_sift.engine.random.random", return_value=0):
                result = asyncio.run(evaluate(self.store, run, 10000000, fake))
            self.assertEqual((result, len(seen)), (code, calls))

    def test_auth_failure_halts_provider_without_retry(self):
        run = self.run_case(providers=["jev"], concurrency=1, retries=2)
        calls = []

        async def send(p, b):
            calls.append(p.name)
            raise HTTPFailure(401)

        fake = test_sift.FakeTransport()
        fake.send = send
        self.assertEqual(asyncio.run(evaluate(self.store, run, 10000000, fake)), 2)
        self.assertEqual(calls, ["jev"])
        statuses = sorted(r["status"] for r in self.store.results(run))
        self.assertEqual(statuses, ["failed"] * 2 + ["queued"] * 4)

    def test_provider_cap_limits_only_that_provider(self):
        run = self.run_case(provider_caps={"jev": 1})
        fake = test_sift.FakeTransport()
        self.assertEqual(asyncio.run(evaluate(self.store, run, money("1"), fake)), 2)
        self.assertEqual({name for name, _ in fake.calls}, {"openai"})
        for r in self.store.results(run):
            expected = "ok" if r["provider"] == "openai" else "queued"
            self.assertEqual(r["status"], expected)

    def test_batch_over_tpm_fails_without_request(self):
        run = self.run_case([test_sift.item()], providers=["openai"], tpm=10)
        fake = test_sift.FakeTransport()
        self.assertEqual(asyncio.run(evaluate(self.store, run, 10000000, fake)), 2)
        self.assertEqual(fake.calls, [])
        self.assertEqual(
            self.store.results(run)[0]["error"], "batch_exceeds_configured_tpm"
        )

    def test_changed_rubric_or_model_blocks_resume(self):
        for change in (
            lambda c: c.update(rubric="relevance-v0"),
            lambda c: c["pricing"]["openai"].update(model="older-model"),
        ):
            run = self.run_case([test_sift.item()], providers=["openai"])
            cfg = self.store.run(run)["config"]
            change(cfg)
            with self.store.db:
                self.store.db.execute(
                    "UPDATE runs SET config=? WHERE id=?", (json.dumps(cfg), run)
                )
            fake = test_sift.FakeTransport()
            with self.assertRaises(ValueError):
                asyncio.run(evaluate(self.store, run, 10000000, fake))
            self.assertEqual(fake.calls, [])

    def test_unpinned_returned_model_is_not_cached(self):
        def snapshot_build(p, b):
            answers = [
                dict(name=q["name"], type="predicate", probability=0.9)
                for q in b["questions"]
            ]
            usage = {"input_tokens": 1}
            return dict(model=p.model + "-snapshot", answers=answers, usage=usage), ""

        first = self.run_case([test_sift.item()], providers=["openai"])
        fake = test_sift.FakeTransport(snapshot_build)
        asyncio.run(evaluate(self.store, first, 10000000, fake))
        self.assertEqual(self.store.results(first)[0]["status"], "ok")
        second = self.run_case([test_sift.item()], providers=["openai"])
        fake = test_sift.FakeTransport()
        asyncio.run(evaluate(self.store, second, 10000000, fake))
        self.assertEqual(len(fake.calls), 1)

    def test_database_error_has_no_traceback_or_error_details(self):
        stderr = io.StringIO()
        with (
            patch("sys.argv", ["abstract-sift", "runs"]),
            patch("sys.stderr", stderr),
            patch(
                "abstract_sift.cli.Store",
                side_effect=sqlite3.OperationalError("sensitive details"),
            ),
        ):
            self.assertEqual(main(), 1)
        self.assertEqual(stderr.getvalue(), "Error: OperationalError\n")
