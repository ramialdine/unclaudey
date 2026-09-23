"""Environment and index health check. Never prints secrets."""
from __future__ import annotations

import platform
import sqlite3
import sys
import time

from . import config
from .util import read_json


def _count_files(path, pattern="*.jpg") -> int:
    try:
        return sum(1 for _ in path.rglob(pattern))
    except OSError:
        return 0


def run_cli(a) -> int:
    ok = True
    rows: list[tuple[str, str, str]] = []

    def add(state: str, name: str, detail: str = ""):
        nonlocal ok
        if state == "fail":
            ok = False
        rows.append((state, name, detail))

    add("ok", "python", f"{sys.version.split()[0]} on {platform.system()} {platform.machine()}")
    for mod in ("numpy", "PIL", "httpx", "blurhash"):
        try:
            __import__(mod)
            add("ok", mod)
        except Exception as e:
            add("fail", mod, str(e))
    t0 = time.time()
    try:
        import torch  # noqa: F401
        import open_clip  # noqa: F401

        dev = "mps" if torch.backends.mps.is_available() else "cuda" if torch.cuda.is_available() else "cpu"
        add("ok", "torch + open_clip", f"{torch.__version__}, device {dev}, import {time.time() - t0:.1f}s")
    except Exception as e:
        add("fail", "torch + open_clip", str(e))

    meta = read_json(config.index_meta_path(), {}) or {}
    add("ok", "cache", str(config.cache_dir()))
    if meta.get("terms_accepted_at"):
        add("ok", "Unsplash Dataset terms", f"accepted {meta['terms_accepted_at']}")
    else:
        add("fail", "Unsplash Dataset terms", "not accepted yet; ask the user, then: setup --accept-unsplash-terms")
    if config.catalog_path().exists():
        con = sqlite3.connect(f"file:{config.catalog_path()}?mode=ro", uri=True)
        n = con.execute("SELECT count(*) FROM photos").fetchone()[0]
        n_ok = con.execute("SELECT count(*) FROM stats WHERE ok=1").fetchone()[0]
        try:
            con.execute("SELECT count(*) FROM docs WHERE docs MATCH 'forest'").fetchone()
            add("ok", "catalog + keyword index", f"{n} photos")
        except sqlite3.OperationalError as e:
            add("fail", "keyword index (FTS5)", str(e))
        con.close()
        thumbs = _count_files(config.thumbs_dir())
        add("ok" if thumbs >= 0.95 * n else "warn", "thumbnails", f"{thumbs}/{n}")
        model = meta.get("model")
        emb = config.emb_path(model) if model else None
        if emb and emb.exists():
            add("ok" if n_ok >= 0.95 * n else "warn", "visual index", f"{model}, {n_ok}/{n} photos embedded ({emb.stat().st_size >> 20} MB)")
        else:
            add("fail" if not meta.get("no_visual") else "warn", "visual index", "missing; run: setup (or setup --stage index)")
    else:
        add("fail", "catalog", "missing; run: setup --accept-unsplash-terms")

    if config.unsplash_key():
        add("ok", "UNSPLASH_ACCESS_KEY", f"set (app name: {config.app_name()})")
    else:
        add("warn", "UNSPLASH_ACCESS_KEY", f"not set: searches work, but picks stay DRAFT until resolved with a free key "
                                            f"({config.KEY_HELP_URL}); put it in {config.config_dir() / '.env'}")
    if config.setting("UNSPLASH_API_BASE"):
        add("ok", "UNSPLASH_API_BASE", config.unsplash_api_base())

    if a.network:
        from .util import http_client

        c = http_client(timeout=10)
        for name, url in (("openverse", "https://api.openverse.org/v1/"), ("unsplash cdn", "https://images.unsplash.com/photo-1416138782774-a2149bc6d102?w=10")):
            try:
                r = c.get(url)
                add("ok" if r.status_code < 400 else "warn", f"network: {name}", str(r.status_code))
            except Exception as e:
                add("warn", f"network: {name}", type(e).__name__)
        c.close()

    icon = {"ok": "✓", "warn": "!", "fail": "✗"}
    for state, name, detail in rows:
        print(f" {icon[state]} {name:<26} {detail}")
    print("\nready" if ok else "\nnot ready: fix the ✗ items above")
    return 0 if ok else 1
