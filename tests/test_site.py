import asyncio
import json
from pathlib import Path
import re
import unittest
import test_sift
from abstract_sift.engine import evaluate
from abstract_sift.site import build_site


class SiteTests(unittest.TestCase):
    setUp = test_sift.IntegrationTests.setUp
    tearDown = test_sift.IntegrationTests.tearDown
    run_case = test_sift.IntegrationTests.run_case

    def test_single_file_snapshot_and_safe_embedding(self):
        malicious = "</script><script>alert(1)</script> & <b>body</b>"
        run = self.run_case(
            rows=[test_sift.item("a", malicious), test_sift.item("missing", "")]
        )
        other = self.run_case(rows=[test_sift.item("other", "PRIVATE OTHER RUN")])
        asyncio.run(evaluate(self.store, run, 10000000, test_sift.FakeTransport()))
        path = Path(self.tmp.name) / "export.html"
        result = build_site(
            self.store, run, path, title="<b>Title</b>", brand="Example & Co"
        )
        text = path.read_text()
        self.assertEqual(result["records"], 2)
        self.assertEqual(result["paired"], 1)
        self.assertNotIn("PRIVATE OTHER RUN", text)
        self.assertNotIn(malicious, text)
        self.assertIn("&lt;b&gt;Title&lt;/b&gt;", text)
        self.assertIn("Example &amp; Co", text)
        self.assertNotIn("<script src=", text)
        self.assertNotIn('<link rel="stylesheet"', text)
        self.assertNotIn("fetch('data.json')", text)
        self.assertNotIn("await fetch(`details/", text)
        self.assertNotIn("● Workspace access", text)
        self.assertIn("Scatter plot", text)
        self.assertIn("scoretrack", text)
        payload = re.search(
            r'<script id="explorer-data" type="application/json">(.*?)</script>',
            text,
            re.S,
        ).group(1)
        data = json.loads(payload)
        self.assertEqual(data["details"]["0"]["a"], malicious)
        self.assertEqual(data["metadata"]["run"], run)
        self.assertEqual(data["metadata"]["query"], "Find biomarker cancer studies")
        with self.assertRaises(ValueError):
            build_site(self.store, run, path)
        build_site(self.store, run, path, force=True)

    def test_single_provider_and_unknown_run(self):
        run = self.run_case(providers=["jev"])
        asyncio.run(evaluate(self.store, run, 10000000, test_sift.FakeTransport()))
        path = Path(self.tmp.name) / "one.html"
        build_site(self.store, run, path)
        text = path.read_text()
        data = json.loads(
            re.search(
                r'<script id="explorer-data" type="application/json">(.*?)</script>',
                text,
                re.S,
            ).group(1)
        )
        self.assertEqual(
            data["metadata"]["records"][0]["openai_status"], "not_selected"
        )
        with self.assertRaises(ValueError):
            build_site(self.store, "missing", Path(self.tmp.name) / "bad.html")
        self.assertFalse((Path(self.tmp.name) / "bad.html").exists())
        with self.assertRaises(ValueError):
            build_site(self.store, run, Path(self.tmp.name) / "db.sqlite")
