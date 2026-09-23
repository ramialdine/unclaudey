"""Live photo providers used by `search --expand`. Results are re-ranked with the same model
and filters as the local index so everything lands on one contact sheet."""
from __future__ import annotations

import json
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from PIL import Image

from .. import config, imagestats
from ..imagestats import rank_against
from ..util import fetch_bytes, http_client, log, orientation_of, thumb_path, write_bytes_atomic

CACHE_TTL = 24 * 3600


def cached_get_json(url: str, headers: dict | None = None, ttl: int = CACHE_TTL) -> tuple[dict | None, dict]:
    """GET JSON with a small on-disk cache so repeated searches don't burn rate limits.
    Returns (json, info) where info has rate-limit headers when a request was made."""
    con = sqlite3.connect(config.http_cache_path())
    con.execute("CREATE TABLE IF NOT EXISTS cache(url TEXT PRIMARY KEY, at REAL, body TEXT)")
    row = con.execute("SELECT at, body FROM cache WHERE url=?", (url,)).fetchone()
    if row and time.time() - row[0] < ttl:
        con.close()
        return json.loads(row[1]), {"cached": True}
    client = http_client(timeout=30)
    try:
        r = client.get(url, headers=headers)
    finally:
        client.close()
    info = {k.lower(): v for k, v in r.headers.items() if "ratelimit" in k.lower()}
    info["status"] = r.status_code
    if r.status_code != 200:
        con.close()
        return None, info
    body = r.text
    con.execute("INSERT OR REPLACE INTO cache VALUES (?,?,?)", (url, time.time(), body))
    con.commit()
    con.close()
    return json.loads(body), info


def provider_query(slot) -> str:
    """Live APIs are keyword engines: send the concrete nouns, not the whole art brief."""
    if slot.keywords:
        return " ".join(slot.keywords[:4])
    words = [w for w in slot.brief.replace(",", " ").split() if len(w) > 2][:6]
    return " ".join(words)


def live_candidates(slot, providers: list[str], idx, qvec, avoid_vecs, reuse: set[str]) -> list[dict]:
    from . import openverse, unsplash

    raw: list[dict] = []
    q = provider_query(slot)
    for name in providers:
        name = name.strip().lower()
        try:
            if name == "unsplash":
                raw += unsplash.search(q, slot)
            elif name == "openverse":
                raw += openverse.search(q, slot)
            else:
                log(f"unknown provider '{name}' (use unsplash, openverse)")
        except Exception as e:  # a provider being down should never break search
            log(f"{name}: search failed: {e}")
    if not raw:
        return []

    client = http_client(max_connections=8)

    def fetch(item):
        p = thumb_path(item["source"], item["id"])
        if not p.exists():
            data = fetch_bytes(client, item["thumb_url"], attempts=2)
            if not data:
                return None
            write_bytes_atomic(p, data)
        try:
            with Image.open(p) as im:
                im.load()
                return item, im.convert("RGB"), p
        except Exception:
            return None

    with ThreadPoolExecutor(8) as ex:
        loaded = [x for x in ex.map(fetch, raw) if x]
    client.close()
    if not loaded:
        return []

    emb = idx.embedder() if idx.visual else None
    feats = emb.images([im for _, im, _ in loaded]) if emb else None
    out = []
    from ..embed import people_probability
    from ..search import PEOPLE_NONE_MAX, PEOPLE_REQ_MIN, SIDE, tokens

    q_tokens = set(tokens(slot.keywords + [slot.brief]))
    pprob = people_probability(emb, feats) if feats is not None else None
    for n, (item, im, p) in enumerate(loaded):
        st = imagestats.compute(im)
        w, h = item.get("width") or im.width, item.get("height") or im.height
        aspect = w / h if w and h else im.width / im.height
        text = " ".join([item.get("description") or "", " ".join(item.get("tags") or [])])
        kw = len(q_tokens & set(tokens([text]))) / max(1, len(q_tokens))
        parts = {"keywords": kw}
        s = 1.1 * kw
        people_clip = float(pprob[n]) if pprob is not None else 0.0
        if feats is not None and qvec is not None:
            mu, sd = idx._vstats
            parts["visual"] = float((feats[n] @ qvec - mu) / sd)
            s += parts["visual"]
            if avoid_vecs is not None and len(avoid_vecs):
                am, asd = idx._astats
                za = ((feats[n] @ avoid_vecs.T) - am) / asd
                pen = max(0.0, float(za.max()) - 1.5)
                if pen:
                    parts["avoid"] = -0.9 * pen
                    s += parts["avoid"]
        calm = {r: 1.0 - rank_against(st[f"g_{r}"], idx.sorted_g.get(r, np.array([]))) for r in ("l", "r", "t", "b", "c")}
        lum_rank = rank_against(st["lum"], idx.sorted_lum)
        side = SIDE.get(slot.copy_space or "")
        if side:
            parts["copy_space"] = 2.2 * (calm[side] - 0.5)
            s += parts["copy_space"]
        if item["key"] in reuse:
            parts["reuse"] = -0.9
            s += parts["reuse"]
        # filters (same semantics as the local index)
        o = slot.orientation
        if (o == "landscape" and aspect < 1.2) or (o == "wide" and aspect < 1.6) or (o == "portrait" and aspect > 0.83) \
                or (o == "tall" and aspect > 0.7) or (o == "square" and not 0.83 < aspect < 1.2):
            continue
        if slot.min_width and w and w < slot.min_width:
            continue
        if slot.tone == "dark" and lum_rank > 0.3 or slot.tone == "light" and lum_rank < 0.7:
            continue
        if slot.people == "none" and people_clip >= PEOPLE_NONE_MAX or slot.people == "required" and people_clip < PEOPLE_REQ_MIN:
            continue
        if side and calm[side] < 0.6:
            continue
        cand = {
            "key": item["key"], "source": item["source"], "origin": "live", "id": item["id"],
            "score": round(s, 3), "why": {k: round(v, 3) for k, v in parts.items() if abs(v) > 1e-6},
            "width": w, "height": h, "aspect": round(aspect, 3), "orientation": orientation_of(aspect),
            "description": (item.get("description") or "")[:200], "photographer": item.get("photographer"),
            "photographer_username": item.get("photographer_username"), "photographer_url": item.get("photographer_url"),
            "page_url": item.get("page_url"), "image_url": item.get("image_url"), "thumb": str(p),
            "blur_hash": item.get("blur_hash"), "colors": [c for c in [item.get("color")] if c],
            "license": item.get("license"), "license_url": item.get("license_url"),
            "attribution": item.get("attribution"), "download_location": item.get("download_location"),
            "lum": round(st["lum"], 3), "calm": {k: round(v, 2) for k, v in calm.items()},
            "region_lum": {r: round(st[f"l_{r}"], 2) for r in ("l", "r", "t", "b", "c")},
            "focal": [st["fx"], st["fy"]], "people": people_clip >= PEOPLE_REQ_MIN,
        }
        out.append(cand)
    log(f"live: {len(out)} of {len(loaded)} results passed filters for [{slot.id}] ({', '.join(providers)})")
    return out
