import asyncio
import csv
import io
import json
import math
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from abstract_sift import core
from abstract_sift.store import Store
from abstract_sift.engine import evaluate, run_lock, HTTPFailure
from abstract_sift.compare import report, correlation, ranks
from abstract_sift.cli import parser, execute, load_env


def item(i="a", text="A fictional trial of biomarker-guided cancer treatment."):
    return dict(
        id=i,
        title="Synthetic study " + i,
        authors="Example Author",
        full_text=text,
        link="https://example.org/" + i,
    )


class FakeTransport:
    def __init__(self, behavior=None):
        self.calls = []
        self.active = 0
        self.peak = 0
        self.behavior = behavior

    async def send(self, provider, body):
        self.calls.append((provider.name, body))
        self.active += 1
        self.peak = max(self.peak, self.active)
        await asyncio.sleep(0.001)
        self.active -= 1
        if self.behavior:
            return self.behavior(provider, body)
        names = (
            [q["name"] for q in body["questions"]]
            if provider.name == "openai"
            else list(body["questions"])
        )
        vals = [0.9 if i % 2 == 0 else 0.1 for i in range(len(names))]
        answers = (
            [dict(name=n, type="predicate", probability=v) for n, v in zip(names, vals)]
            if provider.name == "openai"
            else {n: dict(type="noul", noul=v) for n, v in zip(names, vals)}
        )
        return (
            dict(
                model=provider.model,
                answers=answers,
                usage=dict(input_tokens=100, output_tokens=0),
            ),
            "fake-request",
        )


class CoreTests(unittest.TestCase):
    def test_packing_and_semantic_parity(self):
        items = [item(str(i)) for i in range(7)]
        a, n = core.payload(core.PROVIDERS["openai"], "interest", items)
        j, _ = core.payload(core.PROVIDERS["jev"], "interest", items)
        self.assertEqual(a["input"], j["state"])
        for q in a["questions"]:
            self.assertEqual(
                q["instructions"], j["questions"][q["name"]]["instructions"]
            )
        batches, large = core.pack(
            core.PROVIDERS["jev"], "interest", items + [item("large", "x" * 100000)], 3
        )
        self.assertEqual([len(x) for x in batches], [3, 3, 1])
        self.assertEqual(len(large), 1)

    def test_partial_answers_and_invalid_numbers(self):
        p = core.PROVIDERS["openai"]
        _, names = core.payload(p, "q", [item("a"), item("b"), item("c")])
        obj = dict(
            model=p.model,
            answers=[
                dict(name="q_0", type="predicate", probability=0.8),
                dict(name="q_1", type="refusal"),
            ],
        )
        rs = core.parse_answers(p, obj, names)
        self.assertEqual([r["status"] for r in rs], ["ok", "refused", "failed"])
        for val in (float("nan"), True, 1.1, -0.2, "0.8"):
            obj["answers"][0]["probability"] = val
            self.assertEqual(core.parse_answers(p, obj, names)[0]["status"], "failed")
        obj["answers"].append(dict(name="wrong", type="refusal"))
        with self.assertRaises(ValueError):
            core.parse_answers(p, obj, names)

    def test_answer_contract_rejections(self):
        p, j = core.PROVIDERS["openai"], core.PROVIDERS["jev"]
        _, names = core.payload(p, "q", [item("a")])
        for provider, response in [
            (p, dict(answers=[])),
            (j, dict(model=j.model, answers={"q_9": {}})),
            (j, dict(model=j.model, answers=[])),
        ]:
            with self.assertRaises(ValueError):
                core.parse_answers(provider, response, names)
        twice = dict(name="q_0", type="predicate", probability=0.5)
        rs = core.parse_answers(p, dict(model=p.model, answers=[twice, twice]), names)
        self.assertEqual(rs[0]["error"], "missing_or_duplicate_answer")
        wrong = {"q_0": dict(type="predicate", noul=0.5)}
        rs = core.parse_answers(j, dict(model=j.model, answers=wrong), names)
        self.assertEqual(rs[0]["error"], "invalid_answer_type")

    def test_label_boundaries_are_inclusive(self):
        self.assertEqual(core.label(0.7), "relevant")
        self.assertEqual(core.label(0.3), "not_relevant")
        self.assertEqual(core.label(0.5), "review")
        self.assertEqual(core.label(0.5, 0.2, 0.5), "relevant")

    def test_spearman_uses_average_ranks_for_ties(self):
        self.assertEqual(ranks([3, 1, 2]), [3, 1, 2])
        self.assertEqual(ranks([1, 2, 2, 3]), [1, 2.5, 2.5, 4])
        # Hand-calculated Pearson correlation of [1,2.5,2.5,4] and [1,3,2,4].
        rho = correlation(ranks([1, 2, 2, 3]), ranks([1, 3, 2, 4]))
        self.assertAlmostEqual(rho, math.sqrt(0.9))
        self.assertIsNone(correlation([1], [1]))

    def test_cost_precision_and_unknown_usage(self):
        self.assertEqual(core.money("0.25"), 250_000_000)
        self.assertEqual(core.money(".0000001"), 100)
        self.assertEqual(core.dollars(14200), "0.000014200")
        self.assertEqual(
            core.usage_cost(core.PROVIDERS["jev"], {"usage": {"input_tokens": 100}}),
            4200,
        )
        self.assertIsNone(
            core.usage_cost(
                core.PROVIDERS["openai"],
                {
                    "usage": {
                        "input_tokens": 100,
                        "input_tokens_details": {"cached_tokens": 10},
                    }
                },
            )
        )
        for details in ("wrong", {"cache_write_tokens": 5}):
            usage = {"input_tokens": 100, "input_tokens_details": details}
            self.assertIsNone(
                core.usage_cost(core.PROVIDERS["openai"], {"usage": usage})
            )
        for val in ("nan", "Infinity", "0", "-1", "abc"):
            with self.assertRaises(ValueError):
                core.money(val)

    def test_env_does_not_execute_or_override(self):
        with (
            tempfile.TemporaryDirectory() as d,
            patch.dict(os.environ, {"OPENAI_API_KEY": "existing"}, clear=True),
        ):
            p = Path(d) / ".env"
            p.write_text(
                'OPENAI_API_KEY=other\nJEV_API_KEY="$(touch nope)"\nUNRELATED=secret\n'
            )
            load_env(p)
            self.assertEqual(os.environ["OPENAI_API_KEY"], "existing")
            self.assertEqual(os.environ["JEV_API_KEY"], "$(touch nope)")
            self.assertNotIn("UNRELATED", os.environ)

    def test_env_export_prefix_quotes_and_comments(self):
        with (
            tempfile.TemporaryDirectory() as d,
            patch.dict(os.environ, {}, clear=True),
        ):
            p = Path(d) / ".env"
            p.write_text(
                "# comment\n\nexport OPENAI_API_KEY='single'\n"
                "TYPESAFE_API_KEY = plain\nJEV_API_KEY\n"
            )
            load_env(p)
            load_env(Path(d) / "absent.env")
            self.assertEqual(os.environ["OPENAI_API_KEY"], "single")
            self.assertEqual(os.environ["TYPESAFE_API_KEY"], "plain")
            self.assertNotIn("JEV_API_KEY", os.environ)


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(self.tmp.name)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def run_case(self, rows=None, providers=None, **extra):
        cfg = dict(
            providers=providers or ["openai", "jev"],
            batch_size=2,
            concurrency=2,
            rpm=10000,
            tpm=10000000,
            retries=0,
            provider_caps={},
        )
        cfg.update(extra)
        return self.store.create_run(
            "test",
            "Find biomarker cancer studies",
            cfg,
            rows if rows is not None else [item(str(i)) for i in range(6)],
        )

    def test_both_parallel_and_cost(self):
        run = self.run_case()
        fake = FakeTransport()
        code = asyncio.run(evaluate(self.store, run, core.money("1"), fake))
        self.assertEqual(code, 0)
        self.assertGreater(fake.peak, 1)
        self.assertLessEqual(fake.peak, 4)
        self.assertEqual(len(fake.calls), 6)
        cost = self.store.cost(run)
        self.assertEqual(cost["usage_derived_usd"], "0.000042600")
        self.assertEqual(cost["unknown_exposure_usd"], "0.000000000")
        r = report(self.store, run)
        self.assertEqual(r["paired"], 6)
        self.assertEqual(r["kappa"], 1)
        self.assertEqual(r["spearman"], 1)
        self.assertTrue(
            (Path(self.tmp.name) / "runs" / run / "request-usage.jsonl").exists()
        )

    def test_cached_second_run_zero_new_cost(self):
        first = self.run_case()
        asyncio.run(evaluate(self.store, first, core.money("1"), FakeTransport()))
        second = self.run_case()
        fake = FakeTransport()
        asyncio.run(evaluate(self.store, second, core.money("1"), fake))
        self.assertEqual(fake.calls, [])
        self.assertEqual(self.store.cost(second)["usage_derived_usd"], "0.000000000")
        self.assertTrue(
            all(r["cache_origin"] == first for r in self.store.results(second))
        )

    def test_budget_stops_dispatch(self):
        run = self.run_case()
        fake = FakeTransport()
        code = asyncio.run(evaluate(self.store, run, 1, fake))
        self.assertEqual(code, 2)
        self.assertEqual(fake.calls, [])
        self.assertTrue(all(r["status"] == "queued" for r in self.store.results(run)))

    def test_failure_other_provider_and_resume(self):
        run = self.run_case()
        good = FakeTransport()

        async def send(p, b):
            if p.name == "jev":
                raise HTTPFailure(401)
            return await good.send(p, b)

        failed = FakeTransport()
        failed.send = send
        self.assertEqual(
            asyncio.run(evaluate(self.store, run, core.money("1"), failed)), 2
        )
        self.assertGreater(float(self.store.cost(run)["unknown_exposure_usd"]), 0)
        second = FakeTransport()
        self.assertEqual(
            asyncio.run(evaluate(self.store, run, core.money("1"), second)), 0
        )
        self.assertTrue(all(p == "jev" for p, b in second.calls))
        self.assertEqual(len(self.store.cost(run)["invocations"]), 2)

    def test_missing_and_oversized_not_negatives(self):
        run = self.run_case([item("missing", ""), item("big", "x" * 100000)])
        fake = FakeTransport()
        asyncio.run(evaluate(self.store, run, core.money("1"), fake))
        self.assertEqual(fake.calls, [])
        r = report(self.store, run)
        self.assertEqual(r["paired"], 0)
        self.assertIsNone(r["kappa"])

    def test_immutable_snapshot_and_run_lock(self):
        run = self.run_case([item()])
        with run_lock(self.store, run):
            with self.assertRaises(ValueError):
                with run_lock(self.store, run):
                    pass
        self.assertEqual(self.store.items(run), [item()])

    def test_import_transaction_and_cli_export(self):
        p = Path(self.tmp.name) / "corpus.jsonl"
        p.write_text(json.dumps(item()) + "\n" + json.dumps(item("missing", "")) + "\n")
        self.assertEqual(self.store.read_corpus(p, "c")["usable"], 1)
        p.write_text(json.dumps(item()) + "\n" + json.dumps(item()) + "\n")
        with self.assertRaises(ValueError):
            self.store.read_corpus(p, "c")
        self.assertEqual(len(self.store.corpus("c")), 2)
        run = self.run_case(
            [dict(item(), title='=HYPERLINK("bad")')], providers=["openai"]
        )
        asyncio.run(evaluate(self.store, run, core.money("1"), FakeTransport()))
        output = Path(self.tmp.name) / "result.csv"
        args = parser().parse_args(["export", run, "--output", str(output)])
        with patch("sys.stdout", new=io.StringIO()):
            execute(args, self.store)
        with output.open() as f:
            self.assertTrue(next(csv.DictReader(f))["title"].startswith("'="))

    def test_hand_calculated_comparison_and_degeneracy(self):
        run = self.run_case([item(str(i)) for i in range(4)])
        with self.store.db:
            for i, (a, b) in enumerate([(1, 1), (1, 0), (0, 1), (0, 0)]):
                for p, v in [("openai", a), ("jev", b)]:
                    self.store.db.execute(
                        "UPDATE results SET status='ok',probability=?,model=? WHERE run=? AND id=? AND provider=?",
                        (v, core.PROVIDERS[p].model, run, str(i), p),
                    )
        r = report(self.store, run)
        self.assertEqual(r["binary_agreement"], 0.5)
        self.assertEqual(r["kappa"], 0)
        self.assertEqual(r["positive_agreement"], 0.5)
        with self.store.db:
            self.store.db.execute(
                "UPDATE results SET probability=1 WHERE run=?", (run,)
            )
        r = report(self.store, run)
        self.assertIsNone(r["kappa"])
        self.assertIsNone(r["spearman"])

    def test_kappa_and_agreement_match_hand_calculation(self):
        cells = [(0.9, 0.9)] * 20 + [(0.9, 0.1)] * 5 + [(0.1, 0.9)] * 10
        cells += [(0.1, 0.1)] * 15
        run = self.run_case([item(f"{i:02d}") for i in range(len(cells))])
        with self.store.db:
            for i, pair in enumerate(cells):
                for p, v in zip(("openai", "jev"), pair):
                    self.store.db.execute(
                        "UPDATE results SET status='ok',probability=?,model=? WHERE run=? AND id=? AND provider=?",
                        (v, core.PROVIDERS[p].model, run, f"{i:02d}", p),
                    )
        r = report(self.store, run)
        # po = 35/50; pe = (25*30 + 25*20)/50^2 = 0.5; kappa = (0.7-0.5)/0.5.
        self.assertAlmostEqual(r["binary_agreement"], 0.7)
        self.assertAlmostEqual(r["kappa"], 0.4)
        self.assertAlmostEqual(r["positive_agreement"], 40 / 55)
        self.assertAlmostEqual(r["negative_agreement"], 30 / 45)
        self.assertEqual(r["three_way_matrix"]["relevant"]["not_relevant"], 5)
        self.assertEqual(
            r["top_k"]["20"], dict(k=20, overlap=1, jaccard=1, tie_break="abstract_id")
        )
        with self.store.db:
            self.store.db.execute(
                "UPDATE results SET model='another-build' WHERE run=? AND id='00' AND provider='jev'",
                (run,),
            )
        with self.assertRaises(ValueError):
            report(self.store, run)
        with self.assertRaises(ValueError):
            report(self.store, self.run_case(providers=["openai"]))

    def test_csv_import_and_record_validation(self):
        p = Path(self.tmp.name) / "corpus.csv"
        p.write_text(
            "﻿id,title,authors,full_text,link,extra\n"
            'x1,Title,Author,"Text, with comma",https://example.org,ignored\n',
            encoding="utf-8",
        )
        self.assertEqual(self.store.read_corpus(p, "csv")["records"], 1)
        self.assertEqual(
            self.store.corpus("csv"),
            [
                dict(
                    id="x1",
                    title="Title",
                    authors="Author",
                    full_text="Text, with comma",
                    link="https://example.org",
                )
            ],
        )
        bad = Path(self.tmp.name) / "bad.jsonl"
        for record in (
            json.dumps(dict(id="a", title="t")),
            json.dumps(dict(item(), authors=["not", "a", "string"])),
            json.dumps(dict(item(), id=" ")),
            json.dumps(dict(item(), full_text="x" * 2_000_001)),
            "",
        ):
            bad.write_text(record + "\n")
            with self.assertRaises(ValueError):
                self.store.read_corpus(bad, "bad")
        with self.assertRaises(ValueError):
            self.store.corpus("bad")
        with self.assertRaises(ValueError):
            self.store.run("run_missing")

    def test_cancellation_records_unknown_and_resumes(self):
        run = self.run_case(providers=["openai"], concurrency=1)

        async def stalled(p, b):
            await asyncio.sleep(10)

        fake = FakeTransport()
        fake.send = stalled

        async def cancel():
            task = asyncio.create_task(evaluate(self.store, run, core.money("1"), fake))
            await asyncio.sleep(0.02)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task

        asyncio.run(cancel())
        self.assertEqual(self.store.run(run)["status"], "canceled")
        self.assertGreater(float(self.store.cost(run)["unknown_exposure_usd"]), 0)
        self.assertEqual(
            asyncio.run(evaluate(self.store, run, core.money("1"), FakeTransport())), 0
        )


if __name__ == "__main__":
    unittest.main()
