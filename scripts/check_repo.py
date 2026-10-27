"""Fail if version control tracks credentials, local state, corpora or large exports."""

from pathlib import Path
import re
import subprocess
from check_artifacts import private

ROOT = Path(__file__).resolve().parents[1]
# Source files are small; an explorer export or corpus is megabytes.
MAX_BYTES = 1_000_000
OPENAI_KEY = re.compile(rb"\bsk-(?:proj-|svcacct-|admin-)?[A-Za-z0-9_-]{20,}")

output = subprocess.run(
    ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True
).stdout
tracked = [n.decode() for n in output.split(b"\0") if n]
problems = []
for name in tracked:
    path = ROOT / name
    if private(name):
        problems.append(f"{name}: {private(name)}")
    elif path.is_file() and path.stat().st_size > MAX_BYTES:
        problems.append(f"{name}: larger than {MAX_BYTES:,} bytes")
    elif path.is_file() and OPENAI_KEY.search(path.read_bytes()):
        problems.append(f"{name}: looks like an API key")
if problems:
    raise SystemExit("Tracked files must stay local:\n" + "\n".join(problems))
print(f"PASS: {len(tracked)} tracked files contain no private paths or API keys.")
