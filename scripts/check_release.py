"""Offline CLI + installed-package + HTML smoke check; synthetic data only."""

import asyncio
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from abstract_sift.engine import evaluate
from abstract_sift.store import Store

ROOT = Path(__file__).resolve().parents[1]


class MockTransport:
    async def send(self, provider, body):
        questions = body["questions"]
        names = (
            [q["name"] for q in questions]
            if provider.name == "openai"
            else list(questions)
        )
        answers = (
            [dict(name=n, type="predicate", probability=0.85) for n in names]
            if provider.name == "openai"
            else {n: dict(type="noul", noul=0.75) for n in names}
        )
        return (
            dict(model=provider.model, answers=answers, usage={"input_tokens": 100}),
            "synthetic-request",
        )


with tempfile.TemporaryDirectory(prefix="abstract-sift-release-") as directory:
    state = Path(directory)

    def cli(*args):
        result = subprocess.run(
            [sys.executable, "-m", "abstract_sift", "--data-dir", directory, *args],
            text=True,
            capture_output=True,
            check=True,
        )
        return json.loads(result.stdout)

    result = cli(
        "import",
        str(ROOT / "examples/abstracts.jsonl"),
        "--corpus",
        "synthetic",
        "--json",
    )
    assert result["records"] == 2
    result = cli(
        "estimate",
        "--corpus",
        "synthetic",
        "--query-file",
        str(ROOT / "examples/interest.txt"),
        "--provider",
        "both",
        "--json",
    )
    assert result["providers"]["openai"]["eligible"] == 2
    store = Store(state)
    cfg = dict(
        providers=["openai", "jev"],
        batch_size=16,
        concurrency=4,
        rpm=120,
        tpm=600000,
        retries=0,
        provider_caps={},
    )
    run = store.create_run(
        "synthetic", "Synthetic interest only", cfg, store.corpus("synthetic")
    )
    assert asyncio.run(evaluate(store, run, 10000000, MockTransport())) == 0
    store.close()
    assert cli("status", run, "--json")["status"] == "complete"
    assert len(cli("results", run, "--json")) == 2
    assert cli("compare", run, "--json")["paired"] == 2
    assert (
        cli("compare-runs", run, run, "--json")["providers"]["openai"]["label_changes"]
        == 0
    )
    assert (
        cli("export", run, "--output", str(state / "scores.csv"), "--json")["rows"] == 2
    )
    page = state / "explorer.html"
    assert cli("site", run, "--output", str(page), "--json")["records"] == 2
    subprocess.run(["node", str(ROOT / "tests/check_site.cjs"), str(page)], check=True)
    subprocess.run(["node", str(ROOT / "tests/web_unit.cjs")], check=True)
print("PASS: offline CLI workflow and bundled HTML assets. No API calls made.")
