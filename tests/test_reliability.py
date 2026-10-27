import asyncio
from datetime import datetime, timezone
from email.utils import format_datetime
import io
import json
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch
import httpx
import test_sift
from abstract_sift.core import PROVIDERS, token_bound, payload
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
                    lambda _: httpx.Response(429, headers={"retry-after": header})
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

            async def send(p, b):
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
