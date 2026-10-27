import argparse
import asyncio
from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest.mock import patch
import test_sift
from abstract_sift.cli import execute, main, parser
from abstract_sift.engine import evaluate, run_lock

ROOT = Path(__file__).resolve().parents[1]


class OfflineCLITests(unittest.TestCase):
    setUp = test_sift.IntegrationTests.setUp
    tearDown = test_sift.IntegrationTests.tearDown
    run_case = test_sift.IntegrationTests.run_case

    def invoke(self, *argv):
        out = io.StringIO()
        with redirect_stdout(out):
            execute(parser().parse_args(list(argv)), self.store)
        return out.getvalue()

    def write(self, name, text):
        path = Path(self.tmp.name) / name
        path.write_text(text)
        return str(path)

    def import_corpus(self):
        rows = [
            test_sift.item("lung", "Lung cancer biomarker trial"),
            test_sift.item("heart", "Cardiology registry"),
            test_sift.item("blank", ""),
        ]
        path = self.write("corpus.jsonl", "".join(json.dumps(r) + "\n" for r in rows))
        return self.invoke("import", path, "--corpus", "c")

    def test_import_estimate_and_search_reports(self):
        self.assertIn("usable", self.import_corpus())
        query = self.write("query.txt", "lung biomarker")
        scoring = ["--corpus", "c", "--query-file", query]
        self.assertIn(
            "Cost bound (USD)*",
            self.invoke("estimate", *scoring, "--provider", "both"),
        )
        estimate = json.loads(
            self.invoke("estimate", *scoring, "--provider", "openai", "--json")
        )["providers"]
        self.assertEqual(list(estimate), ["openai"])
        self.assertEqual(estimate["openai"]["eligible"], 2)
        self.assertEqual(estimate["openai"]["missing_text"], 1)
        preview = json.loads(self.invoke("search", *scoring, "--top", "1", "--json"))
        self.assertEqual(preview["kind"], "lexical_preview_not_model_scores")
        self.assertEqual([r["id"] for r in preview["results"]], ["lung"])
        self.assertIn("Lexical preview", self.invoke("search", *scoring))

    def test_invalid_arguments_fail_before_any_run_is_created(self):
        self.import_corpus()
        query = self.write("query.txt", "lung")
        empty = self.write("empty.txt", "  \n")
        absent = str(Path(self.tmp.name) / "absent.env")
        score = ["score", "--corpus", "c", "--provider", "openai"]
        score += ["--max-cost-usd", "1"]
        for argv in (
            score + ["--query-file", empty],
            score + ["--query-file", query, "--batch-size", "0"],
            score + ["--query-file", query, "--limit", "-1"],
            score + ["--query-file", query, "--concurrency", "17"],
            score + ["--query-file", query, "--retries", "6"],
            score + ["--query-file", query, "--rpm", "0"],
            ["search", "--corpus", "c", "--query-file", query, "--top", "0"],
            ["cost"],
            ["compare-runs", "a", "b", "--top", "-1"],
            ["results", "run_x", "--low", "0.8", "--high", "0.2"],
            ["compare", "run_x", "--threshold", "2"],
        ):
            with self.subTest(argv=argv), self.assertRaises(ValueError):
                self.invoke(*argv)
        with (
            patch.dict(os.environ, {}, clear=True),
            self.assertRaises(ValueError) as caught,
        ):
            self.invoke("--env-file", absent, *score, "--query-file", query)
        self.assertIn("Missing credential for openai", str(caught.exception))
        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": "fake"}, clear=True),
            self.assertRaises(ValueError),
        ):
            self.invoke("--env-file", absent, *score[:-1], "0", "--query-file", query)
        runs = self.store.db.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        self.assertEqual(runs, 0)

    def test_text_sort_and_provider_specific_sorts(self):
        run = self.run_case(providers=["openai"])
        asyncio.run(evaluate(self.store, run, 10**9, test_sift.FakeTransport()))
        rows = json.loads(self.invoke("results", run, "--sort", "title", "--json"))
        titles = [r["title"] for r in rows]
        self.assertEqual(titles, sorted(titles, key=str.casefold))
        for sort in ("jev", "gap"):
            with self.subTest(sort=sort), self.assertRaises(ValueError):
                self.invoke("results", run, "--sort", sort)

    def test_site_command_reports_and_refuses_overwrite(self):
        run = self.run_case()
        asyncio.run(evaluate(self.store, run, 10**9, test_sift.FakeTransport()))
        output = str(Path(self.tmp.name) / "explorer.html")
        text = self.invoke("site", run, "--output", output)
        self.assertIn("HTML explorer:", text)
        self.assertIn("6 abstracts | 6 scored pairs", text)
        with self.assertRaises(ValueError):
            self.invoke("site", run, "--output", output)

    def test_resume_refuses_an_active_run(self):
        run = self.run_case([test_sift.item()], providers=["openai"])
        absent = str(Path(self.tmp.name) / "absent.env")
        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": "fake"}, clear=True),
            run_lock(self.store, run),
            self.assertRaises(ValueError) as caught,
        ):
            self.invoke(
                "--env-file", absent, "resume", run, "--max-additional-cost-usd", "1"
            )
        self.assertIn("already active", str(caught.exception))

    def test_every_command_and_option_is_documented(self):
        doc = (ROOT / "docs" / "CLI.md").read_text()
        ap = parser()
        commands = next(
            a for a in ap._actions if isinstance(a, argparse._SubParsersAction)
        ).choices
        for name, sub in [("global", ap)] + list(commands.items()):
            if name != "global":
                self.assertIn(f"## {name}\n", doc)
            for action in sub._actions:
                for option in action.option_strings:
                    if option.startswith("--") and option != "--help":
                        self.assertIn(option, doc, f"{name} {option}")


class EntryPointTests(unittest.TestCase):
    def test_exit_codes_and_sanitized_messages(self):
        with tempfile.TemporaryDirectory() as d:
            base = ["abstract-sift", "--data-dir", d]
            missing = str(Path(d) / "missing.txt")
            for argv, code, message in (
                (["status", "run_missing"], 1, "Error: Unknown run ID\n"),
                (
                    ["search", "--corpus", "c", "--query-file", missing],
                    1,
                    "Error: FileNotFoundError\n",
                ),
            ):
                stderr = io.StringIO()
                with patch("sys.argv", base + argv), redirect_stderr(stderr):
                    self.assertEqual(main(), code)
                self.assertEqual(stderr.getvalue(), message)
            stderr = io.StringIO()
            with (
                patch("sys.argv", base + ["runs"]),
                patch("abstract_sift.cli.execute", side_effect=KeyboardInterrupt),
                redirect_stderr(stderr),
            ):
                self.assertEqual(main(), 130)
            self.assertIn("Use resume", stderr.getvalue())

    def test_python_module_entry_point(self):
        with tempfile.TemporaryDirectory() as d:
            out = io.StringIO()
            with (
                patch("sys.argv", ["abstract-sift", "--data-dir", d, "runs", "--json"]),
                redirect_stdout(out),
                self.assertRaises(SystemExit) as caught,
            ):
                runpy.run_module("abstract_sift", run_name="__main__")
        self.assertEqual(caught.exception.code, 0)
        self.assertEqual(json.loads(out.getvalue()), [])


if __name__ == "__main__":
    unittest.main()
