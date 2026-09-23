"""Compute image statistics and embeddings for every cached thumbnail."""
from __future__ import annotations

import sqlite3
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from PIL import Image

from . import config, imagestats
from .embed import Embedder, people_probability
from .util import index_thumb_path, log, read_json, write_json

STAT_COLS = ["lum", "contrast", "sat", "warmth", "g_l", "g_r", "g_t", "g_b", "g_c", "g_all",
             "l_l", "l_r", "l_t", "l_b", "l_c", "fx", "fy"]


def build_index(model_key: str = config.DEFAULT_MODEL, batch: int = 128, limit: int | None = None) -> None:
    t0 = time.time()
    con = sqlite3.connect(config.catalog_path())
    rows = con.execute("SELECT idx, id FROM photos ORDER BY idx").fetchall()
    n_total = len(rows)
    if limit:
        rows = rows[:limit]
    emb = Embedder(model_key)

    def load(row):
        idx, pid = row
        path = index_thumb_path(pid)
        try:
            with Image.open(path) as im:
                im.load()
                im = im.convert("RGB")
            st = imagestats.compute(im)
            return idx, st, emb.preprocess(im)
        except Exception:
            return idx, None, None

    dim = None
    vecs: dict[int, np.ndarray] = {}
    stats_rows = []
    done = 0
    last = time.time()
    starts = iter(range(0, len(rows), batch))
    with ThreadPoolExecutor(8) as ex:
        # keep two batches decoding while the model embeds the current one
        pending = deque()
        for _ in range(2):
            s = next(starts, None)
            if s is not None:
                pending.append([ex.submit(load, r) for r in rows[s:s + batch]])
        while pending:
            futs = pending.popleft()
            s = next(starts, None)
            if s is not None:
                pending.append([ex.submit(load, r) for r in rows[s:s + batch]])
            chunk = [f.result() for f in futs]
            good = [(i, st, t) for i, st, t in chunk if st is not None]
            if good:
                f = emb.images(tensors=[t for _, _, t in good])
                dim = f.shape[1]
                people = people_probability(emb, f)
                for (i, st, _), v, pc in zip(good, f, people):
                    vecs[i] = v
                    stats_rows.append((1, *[st[c] for c in STAT_COLS], float(pc), i))
            done += len(chunk)
            if time.time() - last > 10 or done == len(rows):
                last = time.time()
                log(f"  indexed {done}/{len(rows)}  ({done / max(1e-6, last - t0):.0f} img/s)")

    if dim is None:
        raise SystemExit("No thumbnails found. Run: setup --stage thumbs")
    mat = np.zeros((n_total, dim), dtype=np.float16)
    for i, v in vecs.items():
        mat[i] = v.astype(np.float16)
    np.save(config.emb_path(model_key), mat)

    compute_hubness(model_key, emb, mat.astype(np.float32), con)

    sets = ", ".join(f"{c}=?" for c in ["ok", *STAT_COLS, "people_clip"])
    con.executemany(f"UPDATE stats SET {sets} WHERE idx=?", stats_rows)
    con.commit()
    con.close()

    meta = read_json(config.index_meta_path(), {}) or {}
    meta.update({
        "model": model_key,
        "dim": int(dim),
        "indexed": len(vecs),
        "photos": n_total,
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })
    write_json(config.index_meta_path(), meta)
    log(f"index built: {len(vecs)}/{n_total} photos, dim {dim}, {time.time() - t0:.0f}s -> {config.emb_path(model_key)}")


def recompute_people(model_key: str | None = None) -> None:
    """Refresh the people probability from stored embeddings (no image work)."""
    meta = read_json(config.index_meta_path(), {}) or {}
    model_key = model_key or meta.get("model") or config.DEFAULT_MODEL
    E = np.load(config.emb_path(model_key)).astype(np.float32)
    emb = Embedder(model_key, device="cpu")
    prob = people_probability(emb, E)
    con = sqlite3.connect(config.catalog_path())
    con.executemany("UPDATE stats SET people_clip=? WHERE idx=? AND ok=1", [(float(p), i) for i, p in enumerate(prob)])
    con.commit()
    con.close()
    log(f"people probability refreshed for {len(prob)} photos")


def compute_hubness(model_key: str, emb: Embedder, E: np.ndarray, con: sqlite3.Connection, bank: int = 800) -> None:
    """Some photos sit close to almost every query in embedding space ("hubs") and would show
    up everywhere. Score each photo by its mean top-10 similarity to a bank of real captions;
    search subtracts part of it."""
    rows = con.execute("SELECT ai_description FROM photos WHERE ai_description != '' ORDER BY random() LIMIT ?", (bank,)).fetchall()
    texts = [r[0] for r in rows]
    B = np.vstack([emb.prompts(texts[i:i + 128]) for i in range(0, len(texts), 128)]).astype(np.float32)
    S = E @ B.T
    k = min(10, S.shape[1])
    hub = np.sort(S, axis=1)[:, -k:].mean(axis=1)
    hub[np.abs(E).sum(axis=1) == 0] = 0.0
    np.save(config.hub_path(model_key), hub.astype(np.float32))
    log(f"hubness scores: mean {hub.mean():.3f}, p99 {np.percentile(hub, 99):.3f}")


def recompute_hubness(model_key: str | None = None) -> None:
    meta = read_json(config.index_meta_path(), {}) or {}
    model_key = model_key or meta.get("model") or config.DEFAULT_MODEL
    E = np.load(config.emb_path(model_key)).astype(np.float32)
    con = sqlite3.connect(config.catalog_path())
    compute_hubness(model_key, Embedder(model_key, device="cpu"), E, con)
    con.close()
