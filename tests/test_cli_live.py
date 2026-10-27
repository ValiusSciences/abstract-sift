import io
import json
import os
from pathlib import Path
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch
import test_sift
from abstract_sift.cli import execute, parser


class MockContextTransport(test_sift.FakeTransport):
    def __init__(self, keys):
        super().__init__()
        self.keys = keys

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None


class CLILiveTests(unittest.TestCase):
    setUp = test_sift.IntegrationTests.setUp
    tearDown = test_sift.IntegrationTests.tearDown

    def test_score_resume_json_and_quiet_progress(self):
        corpus = Path(self.tmp.name) / "input.jsonl"
        corpus.write_text(json.dumps(test_sift.item()) + "\n")
        self.store.read_corpus(corpus, "test")
        query = Path(self.tmp.name) / "query.txt"
        query.write_text("Test relevance")
        stdout, stderr = io.StringIO(), io.StringIO()
        args = parser().parse_args(
            [
                "--env-file",
                str(Path(self.tmp.name) / "absent.env"),
                "score",
                "--corpus",
                "test",
                "--query-file",
                str(query),
                "--provider",
                "both",
                "--max-cost-usd",
                "1",
                "--json",
            ]
        )
        with (
            patch.dict(
                os.environ,
                {"OPENAI_API_KEY": "fake", "JEV_API_KEY": "fake"},
                clear=True,
            ),
            patch("abstract_sift.cli.Transport", MockContextTransport),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            self.assertEqual(execute(args, self.store), 0)
            result = json.loads(stdout.getvalue())
            run = result["summary"]["run"]
            self.assertEqual(result["summary"]["status"], "complete")
            self.assertNotIn("finished", stderr.getvalue())
            stdout.seek(0)
            stdout.truncate(0)
            args = parser().parse_args(
                [
                    "--env-file",
                    str(Path(self.tmp.name) / "absent.env"),
                    "resume",
                    run,
                    "--max-additional-cost-usd",
                    "1",
                    "--concurrency",
                    "3",
                    "--progress",
                    "never",
                    "--json",
                ]
            )
            self.assertEqual(execute(args, self.store), 0)
            result = json.loads(stdout.getvalue())
            self.assertEqual(len(result["cost"]["invocations"]), 2)
            self.assertEqual(self.store.run(run)["config"]["concurrency"], 3)
        self.assertEqual(len(list(self.store.db.execute("SELECT * FROM attempts"))), 2)
