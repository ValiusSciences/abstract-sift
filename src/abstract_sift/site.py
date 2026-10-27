"""Build the Sites explorer as one self-contained, offline HTML file."""

import html
from importlib.resources import files
import json
from pathlib import Path
import re
import sqlite3
import tempfile
import os


def script_json(obj):
    # A JSON script element still ends at a literal </script>; escape all '<'.
    return (
        json.dumps(obj, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def patched(text, old, new):
    # Hosted UI updates must fail here rather than publish a silently broken page.
    if old not in text:
        raise ValueError("Bundled UI changed; update site.py patch for: " + old[:60])
    return text.replace(old, new)


def substituted(pattern, replacement, text):
    text, count = re.subn(pattern, lambda _: replacement, text, count=1)
    if not count:
        raise ValueError("Bundled UI changed; update site.py patch for: " + pattern)
    return text


def build_site(
    store,
    run_id,
    output,
    title=None,
    brand="Valius Sciences",
    description=None,
    force=False,
):
    output = Path(output).expanduser().resolve()
    if output.suffix.lower() not in (".html", ".htm"):
        raise ValueError("Output must be an .html or .htm file")
    if output.exists() and not force:
        raise ValueError("Output exists; choose another path or use --force")
    # One WAL read transaction is a coherent snapshot even while scoring continues,
    # without copying every corpus and run into memory.
    db = sqlite3.connect(store.path, timeout=30)
    db.row_factory = sqlite3.Row
    try:
        db.execute("BEGIN")
        run = db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        if run is None:
            raise ValueError("Unknown run ID")
        config = json.loads(run["config"])
        records = []
        details = {}
        results = {
            (r["id"], r["provider"]): r
            for r in db.execute("SELECT * FROM results WHERE run=?", (run_id,))
        }
        for n, item in enumerate(
            db.execute("SELECT payload FROM items WHERE run=? ORDER BY id", (run_id,))
        ):
            row = json.loads(item[0])
            chunk = str(n // 100)
            details.setdefault(chunk, {})[row["id"]] = row["full_text"]
            meta = {k: row[k] for k in ("id", "title", "authors", "link")}
            meta["chunk"] = n // 100
            for provider in ("openai", "jev"):
                result = results.get((row["id"], provider))
                meta[provider] = (
                    result["probability"]
                    if result and result["status"] == "ok"
                    else None
                )
                meta[provider + "_status"] = (
                    result["status"] if result else "not_selected"
                )
                meta[provider + "_model"] = result["model"] if result else ""
            records.append(meta)
        corpus = run["corpus"]
        corpus_label = (
            "ESMO " + corpus[4:] if re.fullmatch(r"esmo\d{4}", corpus, re.I) else corpus
        )
        title = title or corpus_label + " Abstract Explorer"
        description = (
            description if description is not None else run["query"].split("\n\n")[0]
        )
        data = dict(
            run=run_id,
            query=run["query"],
            status=run["status"],
            created=run["created"],
            providers=config["providers"],
            corpus=corpus_label,
            records=records,
        )
    finally:
        db.close()
    assets = files("abstract_sift").joinpath("web")
    template = assets.joinpath("index.html").read_text(encoding="utf-8")
    template = substituted(
        r"<title>.*?</title>", "<title>" + html.escape(title) + "</title>", template
    )
    template = substituted(
        r"<h1>.*?</h1>", "<h1>" + html.escape(title) + "</h1>", template
    )
    template = patched(template, "Valius Sciences", html.escape(brand))
    template = patched(
        template,
        "CONFERENCE LIBRARY / ESMO 2026",
        "CONFERENCE LIBRARY / " + html.escape(corpus_label),
    )
    template = patched(template, "● Workspace access", "Local snapshot")
    template = substituted(
        r'<p class="intro">.*?</p>',
        '<p class="intro">' + html.escape(description) + "</p>",
        template,
    )
    css = assets.joinpath("style.css").read_text(encoding="utf-8")
    template = patched(
        template,
        '<link rel="stylesheet" href="style.css">',
        "<style>" + css + "</style>",
    )
    payload = (
        '<script id="explorer-data" type="application/json">'
        + script_json(dict(metadata=data, details=details))
        + "</script>"
    )
    bootstrap = """const LOCAL_SNAPSHOT=JSON.parse(document.getElementById('explorer-data').textContent);
function loadExplorerJSON(url){
 if(url==='data.json')return Promise.resolve(LOCAL_SNAPSHOT.metadata);
 const match=/^details\\/(\\d+)\\.json$/.exec(url);
 if(match&&LOCAL_SNAPSHOT.details[match[1]])return Promise.resolve(LOCAL_SNAPSHOT.details[match[1]]);
 return Promise.reject(new Error('Unknown snapshot asset'));
}
"""
    scripts = []
    for name in ("format.js", "scatter.js", "app.js"):
        code = assets.joinpath(name).read_text(encoding="utf-8")
        if name == "app.js":
            code = patched(
                code,
                "fetch('data.json').then(r=>{if(!r.ok)throw Error('load');return r.json();})",
                "loadExplorerJSON('data.json')",
            )
            code = patched(
                code,
                "const res=await fetch(`details/${r.chunk}.json`);if(!res.ok)throw Error('load');cache.set(r.chunk,await res.json());",
                "cache.set(r.chunk,await loadExplorerJSON(`details/${r.chunk}.json`));",
            )
            code = patched(
                code,
                "ESMO 2026 · ${d.run} · Frozen scoring snapshot",
                "${d.corpus} · ${d.run} · ${d.status} snapshot",
            )
            code = patched(
                code,
                "new URL(r.link,location.origin)",
                "(()=>{try{return new URL(r.link,location.href)}catch{return new URL('about:blank')}})()",
            )
            # file:// history replacement is not supported consistently across browsers.
            code = patched(code, "history.replaceState(null,", "safeReplaceState(null,")
            code = (
                "function safeReplaceState(...args){try{history.replaceState(...args);}catch{}}\n"
                + code
            )
            # Modal race check also works where file:// history is unavailable.
            code = patched(
                code,
                "async function openAbstract(id){",
                "let activeAbstractId=null;\nasync function openAbstract(id){activeAbstractId=id;",
            )
            code = patched(
                code,
                "location.hash===`#${encodeURIComponent(id)}`",
                "activeAbstractId===id&&$('detail').open",
            )
            code = patched(
                code,
                "$('detail').addEventListener('close',()=>safeReplaceState(null,'',location.pathname));",
                "$('detail').addEventListener('close',()=>{activeAbstractId=null;safeReplaceState(null,'',location.pathname);});",
            )
        scripts.append(code)
        template = patched(template, f'<script src="{name}" defer></script>', "")
    template = patched(
        template,
        "</body>",
        payload + "<script>" + bootstrap + "\n".join(scripts) + "</script></body>",
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=output.parent,
            prefix=".explorer-",
            suffix=".tmp",
            delete=False,
        ) as f:
            temporary = Path(f.name)
            f.write(template)
        if force:
            os.replace(temporary, output)
        else:
            os.link(temporary, output)  # Atomic no-clobber publication.
            temporary.unlink()
    finally:
        if temporary and temporary.exists():
            temporary.unlink()
    return dict(
        run=run_id,
        output=str(output),
        records=len(records),
        paired=sum(r["openai"] is not None and r["jev"] is not None for r in records),
        bytes=output.stat().st_size,
        open=output.as_uri(),
        access="Local file: no ChatGPT workspace authentication; contains full abstract texts",
    )
