"""Check distributable archives for bundled UI assets and accidental private files."""

from pathlib import Path
import sys
import tarfile
import zipfile

root = Path(sys.argv[1] if len(sys.argv) > 1 else "dist")
archives = list(root.glob("*.whl")) + list(root.glob("*.tar.gz"))
if not archives:
    raise SystemExit("No distribution archives found")
for archive in archives:
    if archive.suffix == ".whl":
        with zipfile.ZipFile(archive) as z:
            names = z.namelist()
    else:
        with tarfile.open(archive) as t:
            names = t.getnames()
    for name in names:
        path = Path(name)
        if any(
            p
            in (
                "data",
                "exports",
                "imports",
                "datasets",
                "credentials",
                "secrets",
                ".venv",
                ".git",
            )
            for p in path.parts
        ):
            raise SystemExit("Private/runtime directory found in distribution")
        if (
            path.name == ".env"
            or (path.name.startswith(".env.") and path.name != ".env.example")
            or path.suffix in (".sqlite", ".db", ".key", ".pem")
        ):
            raise SystemExit("Private file found in distribution")
    for asset in ("index.html", "style.css", "app.js", "format.js", "scatter.js"):
        if not any(("/" + n).endswith("/abstract_sift/web/" + asset) for n in names):
            raise SystemExit("Missing packaged UI asset: " + asset)
    print(
        "PASS:",
        archive.name,
        "contains required UI assets and no private/runtime paths",
    )
