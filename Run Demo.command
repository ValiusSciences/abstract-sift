#!/bin/bash
set -euo pipefail
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
cd -- "$(dirname -- "$0")"
finish() { printf '\nPress Return to close this window. '; read -r _ || true; }
trap finish EXIT
uv sync
uv run abstract-sift import examples/abstracts.jsonl --corpus demo
uv run abstract-sift score --corpus demo --query-file examples/interest.txt --provider both --max-cost-usd 0.05 --retries 0
