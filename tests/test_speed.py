import asyncio
import json
import unittest
from abstract_sift.engine import Limiter, UsageEstimator, evaluate
from abstract_sift.cli import update_runtime
import test_sift
from test_sift import FakeTransport, item
from abstract_sift.core import PROVIDERS


class LimiterTests(unittest.IsolatedAsyncioTestCase):
    async def test_reconciliation_wakes_waiters(self):
        limiter = Limiter(10, 100)
        ticket = await limiter.acquire(90)
        pending = asyncio.create_task(limiter.acquire(50))
        await asyncio.sleep(0.001)
        self.assertFalse(pending.done())
        await limiter.reconcile(ticket, 10)
        await asyncio.wait_for(pending, 0.2)
        self.assertEqual(sum(e[1] for e in limiter.events), 60)

    async def test_cooldown_does_not_sleep_until_minute_boundary(self):
        limiter = Limiter(10, 100)
        await limiter.acquire(10)
        await limiter.backoff(0.01)
        await asyncio.wait_for(limiter.acquire(10), 0.2)

    async def test_requests_still_limited_when_tokens_released(self):
        limiter = Limiter(1, 100)
        ticket = await limiter.acquire(50)
        await limiter.reconcile(ticket, 1)
        with self.assertRaises(asyncio.TimeoutError):
            await asyncio.wait_for(limiter.acquire(1), 0.01)
        # Reported usage can exceed estimates: keep it, do not clip it.
        await limiter.reconcile(ticket, 200)
        self.assertEqual(ticket[1], 200)


class SpeedTests(unittest.TestCase):
    setUp = test_sift.IntegrationTests.setUp
    tearDown = test_sift.IntegrationTests.tearDown
    run_case = test_sift.IntegrationTests.run_case

    def test_adaptive_batches_and_runtime_provenance(self):
        run = self.run_case(
            rows=[item(str(i), "clinical evidence " * 300) for i in range(32)],
            batch_size=16,
            concurrency=1,
        )
        original = self.store.run(run)
        update_runtime(self.store, run, {"concurrency": 1, "batch_size": 16})
        fake = FakeTransport()
        asyncio.run(evaluate(self.store, run, 1000000000, fake))
        openai = [
            len(body["questions"]) for name, body in fake.calls if name == "openai"
        ]
        self.assertGreater(max(openai[1:]), openai[0])
        current = self.store.run(run)
        self.assertEqual(current["query"], original["query"])
        self.assertEqual(current["config"]["pricing"], original["config"]["pricing"])
        self.assertEqual(
            current["config"]["corpus_hash"], original["config"]["corpus_hash"]
        )
        records = self.store.db.execute(
            "SELECT settings FROM invocation_settings"
        ).fetchall()
        self.assertEqual(json.loads(records[0][0])["batch_size"], 16)
        with self.assertRaises(ValueError):
            update_runtime(self.store, run, {"concurrency": 0})
        self.assertEqual(self.store.run(run)["config"]["concurrency"], 1)
        # Resume learns from recorded usage without sending completed items again.
        estimate = UsageEstimator(self.store, run, PROVIDERS["openai"])
        self.assertLess(estimate.estimate(10000), 10000)
        again = FakeTransport()
        asyncio.run(evaluate(self.store, run, 1000000000, again))
        self.assertEqual(again.calls, [])

    def test_no_cache_forces_new_requests_but_resume_skips_completed(self):
        first = self.run_case()
        asyncio.run(evaluate(self.store, first, 1000000000, FakeTransport()))
        second = self.run_case(no_cache=True)
        fake = FakeTransport()
        asyncio.run(evaluate(self.store, second, 1000000000, fake))
        self.assertGreater(len(fake.calls), 0)
        self.assertTrue(all(not r["cache_origin"] for r in self.store.results(second)))
        again = FakeTransport()
        asyncio.run(evaluate(self.store, second, 1000000000, again))
        self.assertEqual(again.calls, [])
