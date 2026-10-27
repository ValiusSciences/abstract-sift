import asyncio
from contextlib import redirect_stdout
import csv
import io
import json
from pathlib import Path
import tempfile
import unittest
from abstract_sift.cli import parser, execute
from abstract_sift.store import Store
from abstract_sift.engine import evaluate
from abstract_sift.explore import clean
from test_sift import FakeTransport, item


class ExploreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(self.tmp.name)
        cfg = dict(
            providers=["openai", "jev"],
            batch_size=2,
            concurrency=2,
            rpm=10000,
            tpm=10000000,
            retries=0,
            provider_caps={},
        )
        self.run = self.store.create_run(
            "test",
            "interest",
            cfg,
            [item("a", "Lung cancer evidence"), item("b", "Breast cancer evidence")],
        )
        asyncio.run(evaluate(self.store, self.run, 100000000, FakeTransport()))

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def command(self, *argv):
        out = io.StringIO()
        with redirect_stdout(out):
            execute(parser().parse_args(list(argv)), self.store)
        return out.getvalue()

    def test_table_paging_json_and_show(self):
        output = self.command("results", self.run, "--top", "1")
        self.assertIn("OPENAI", output)
        self.assertIn("2 matching abstracts", output)
        page = json.loads(
            self.command("results", self.run, "--top", "1", "--page", "2", "--json")
        )
        self.assertEqual([r["id"] for r in page], ["b"])
        detail = json.loads(self.command("show", self.run, "a", "--json"))
        self.assertEqual(detail["full_text"], "Lung cancer evidence")
        self.assertIn(self.run, self.command("runs"))
        with self.assertRaises(ValueError):
            self.command("results", self.run, "--page", "0")
        self.assertNotIn("\x1b", clean("\x1b[2Jhello"))

    def test_filtered_export_matches_results_and_empty_has_headers(self):
        filters = ["--view", "retained", "--contains", "lung", "--include-text"]
        expected = json.loads(self.command("results", self.run, *filters, "--json"))
        path = Path(self.tmp.name) / "table.tsv"
        self.command(
            "export", self.run, *filters, "--format", "tsv", "--output", str(path)
        )
        with path.open() as f:
            rows = list(csv.DictReader(f, delimiter="\t"))
        self.assertEqual([r["id"] for r in rows], [r["id"] for r in expected])
        self.assertEqual(rows[0]["full_text"], "Lung cancer evidence")
        self.command(
            "export", self.run, "--contains", "no such text", "--output", str(path)
        )
        with path.open() as f:
            reader = csv.DictReader(f)
            self.assertIn("openai_probability", reader.fieldnames)
            self.assertEqual(list(reader), [])

    def test_status_and_numeric_sort(self):
        rows = json.loads(self.command("results", self.run, "--ascending", "--json"))
        self.assertEqual(rows[0]["id"], "b")
        with self.store.db:
            self.store.db.execute(
                "UPDATE results SET status='failed',probability=NULL WHERE run=? AND id='b' AND provider='jev'",
                (self.run,),
            )
        rows = json.loads(
            self.command(
                "results",
                self.run,
                "--status",
                "failed",
                "--view",
                "incomplete_pair",
                "--json",
            )
        )
        self.assertEqual([r["id"] for r in rows], ["b"])
