import asyncio
from contextlib import redirect_stdout
import io
import json
import unittest
import test_sift
from abstract_sift.cli import parser, execute
from abstract_sift.display import Progress
from abstract_sift.engine import evaluate


class DisplayTests(unittest.TestCase):
    setUp = test_sift.IntegrationTests.setUp
    tearDown = test_sift.IntegrationTests.tearDown
    run_case = test_sift.IntegrationTests.run_case

    def invoke(self, *argv):
        out = io.StringIO()
        with redirect_stdout(out):
            execute(parser().parse_args(list(argv)), self.store)
        return out.getvalue()

    def test_default_tables_and_json_equivalence(self):
        run = self.run_case()
        asyncio.run(evaluate(self.store, run, 1000000000, test_sift.FakeTransport()))
        for command in ("status", "cost", "compare", "results"):
            human = self.invoke(command, run)
            self.assertFalse(human.lstrip().startswith(("{", "[")))
            self.assertEqual(
                json.loads(self.invoke(command, run, "--json")),
                json.loads(self.invoke(command, run, "--format", "json")),
            )
        self.assertIn("Label changes", self.invoke("compare-runs", run, run))
        self.assertEqual(
            json.loads(self.invoke("compare-runs", run, run, "--format", "json"))[
                "providers"
            ]["openai"]["label_changes"],
            0,
        )

    def test_progress_counts_missing_and_failures_without_batch_spam(self):
        run = self.run_case(rows=[test_sift.item("a"), test_sift.item("b", "")])
        stream = io.StringIO()
        progress = Progress(self.store, run, "always", stream)
        progress.draw()
        with self.store.db:
            self.store.db.execute(
                "UPDATE results SET status='failed' WHERE run=? AND id='a' AND provider='openai'",
                (run,),
            )
        progress.notify("openai: request failed (http_429); checkpoint retained")
        progress.draw(final=True)
        text = stream.getvalue()
        self.assertIn("0/1 scored", text)
        self.assertIn("1 missing", text)
        self.assertIn("1 failed", text)
        self.assertIn("\x1b[2A", text)
        self.assertNotIn("finished", text)

    def test_nonterminal_and_disabled_are_quiet(self):
        run = self.run_case()
        stream = io.StringIO()
        p = Progress(self.store, run, "auto", stream)
        p.draw()
        p.notify("openai: finished 2 abstracts")
        p.draw()
        self.assertEqual(stream.getvalue(), "")
        p.draw(final=True)
        self.assertEqual(len(stream.getvalue().splitlines()), 2)
        self.assertNotIn("\x1b", stream.getvalue())
        off = io.StringIO()
        p = Progress(self.store, run, "never", off)
        p.draw(final=True)
        self.assertEqual(off.getvalue(), "")

    def test_export_format_separate_from_report_format(self):
        args = parser().parse_args(
            [
                "export",
                "run_id",
                "--format",
                "tsv",
                "--output-format",
                "json",
                "--output",
                "results.tsv",
            ]
        )
        self.assertEqual(args.format, "tsv")
        self.assertEqual(args.output_format, "json")
