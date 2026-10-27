import asyncio
import unittest
import test_sift
from abstract_sift.compare import compare_runs
from abstract_sift.engine import evaluate


class RunComparisonTests(unittest.TestCase):
    setUp = test_sift.IntegrationTests.setUp
    tearDown = test_sift.IntegrationTests.tearDown
    run_case = test_sift.IntegrationTests.run_case

    def test_changes_and_missing_coverage(self):
        old = self.run_case(
            rows=[
                test_sift.item("a"),
                test_sift.item("b"),
                test_sift.item("missing", ""),
            ]
        )
        new = self.run_case(
            rows=[
                test_sift.item("a"),
                test_sift.item("b"),
                test_sift.item("missing", ""),
            ],
            no_cache=True,
        )
        for run in (old, new):
            asyncio.run(
                evaluate(self.store, run, 1000000000, test_sift.FakeTransport())
            )
        with self.store.db:
            self.store.db.execute(
                "UPDATE results SET probability=.2 WHERE run=? AND id='a'", (new,)
            )
        r = compare_runs(self.store, old, new)
        self.assertEqual(r["retained"]["newly_excluded"], ["a"])
        self.assertEqual(r["retained"]["excluded"], 1)
        self.assertEqual(r["providers"]["openai"]["label_agreement"], 0.5)
        self.assertAlmostEqual(
            r["providers"]["openai"]["mean_absolute_score_change"], 0.35
        )
        self.assertAlmostEqual(r["largest_score_changes"][0]["delta"], -0.7)
        self.assertEqual(
            len(compare_runs(self.store, old, new, top=1)["largest_score_changes"]), 1
        )

    def test_reject_different_query_and_exclude_changed_model(self):
        old = self.run_case()
        new = self.run_case(no_cache=True)
        for run in (old, new):
            asyncio.run(
                evaluate(self.store, run, 1000000000, test_sift.FakeTransport())
            )
        with self.store.db:
            self.store.db.execute(
                "UPDATE results SET model='another-build' WHERE run=? AND provider='jev'",
                (new,),
            )
        r = compare_runs(self.store, old, new)
        self.assertEqual(r["providers"]["jev"]["paired"], 0)
        self.assertIsNone(r["providers"]["jev"]["label_agreement"])
        self.assertEqual(r["retained"]["fully_scored_same_model_pairs"], 0)
        with self.store.db:
            self.store.db.execute(
                "UPDATE runs SET query='different criteria' WHERE id=?", (new,)
            )
        with self.assertRaises(ValueError):
            compare_runs(self.store, old, new)
