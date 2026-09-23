"""Download small previews of indexed photos (resumable, polite concurrency)."""
from __future__ import annotations

import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from . import config
from .util import fetch_bytes, http_client, index_thumb_path, log, write_bytes_atomic, add_query


def thumb_url(image_url: str, size: int = config.THUMB_SIZE) -> str:
    return add_query(image_url, w=size, h=size, fit="max", q=70, fm="jpg")


def download_all(db_path=None, workers: int = 16, limit: int | None = None) -> tuple[int, int]:
    con = sqlite3.connect(db_path or config.catalog_path())
    rows = con.execute("SELECT idx, id, image_url FROM photos ORDER BY idx").fetchall()
    con.close()
    if limit:
        rows = rows[:limit]
    todo = [r for r in rows if not index_thumb_path(r[1]).exists()]
    have = len(rows) - len(todo)
    log(f"thumbnails: {have} cached, {len(todo)} to download ({workers} workers)")
    if not todo:
        return len(rows), 0
    client = http_client(max_connections=workers)
    ok = failed = 0
    t0 = last = time.time()

    def one(row):
        _, pid, url = row
        data = fetch_bytes(client, thumb_url(url))
        if data:
            write_bytes_atomic(index_thumb_path(pid), data)
            return True
        return False

    with ThreadPoolExecutor(workers) as ex:
        futs = [ex.submit(one, r) for r in todo]
        for n, fut in enumerate(as_completed(futs), 1):
            if fut.result():
                ok += 1
            else:
                failed += 1
            if time.time() - last > 10 or n == len(todo):
                last = time.time()
                rate = n / max(1e-6, last - t0)
                eta = (len(todo) - n) / max(rate, 1e-6)
                log(f"  {n}/{len(todo)}  ok={ok} failed={failed}  {rate:.0f}/s  eta {eta / 60:.1f} min")
    client.close()
    return have + ok, failed
