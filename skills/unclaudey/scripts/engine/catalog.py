"""Build the local catalog (SQLite + FTS5) from the Unsplash Lite dataset.

The dataset is downloaded by each user from Unsplash under the Unsplash Dataset terms and
stays in the local cache. It is used only as a private search index; photos that end up
in a published design are resolved through the Unsplash API (see resolve.py).
"""
from __future__ import annotations

import collections
import csv
import json
import re
import sqlite3
import sys
import time
import zipfile
from pathlib import Path

from . import config
from .util import log, read_json, write_json

csv.field_size_limit(sys.maxsize)

TABLES = ["photos.tsv000", "keywords.tsv000", "colors.tsv000", "collections.tsv000", "conversions.tsv000"]

# Words that mean a person is in the photo. Deliberately excludes "adult", "male", "female",
# "face" and "hands": in this dataset they tag animals, rock faces, clock faces and close-ups.
PEOPLE_STRICT = {
    "person", "people", "human", "man", "woman", "men", "women", "girl", "boy", "child", "children",
    "kid", "kids", "baby", "crowd", "family", "couple", "selfie", "lady", "guy", "teen", "teenager",
    "toddler", "bride", "groom", "portrait",
}
NO_PEOPLE = re.compile(r"\b(no|without)\s+(people|person|one)\b")


def has_people(keywords: list, caption: str) -> bool:
    cap = (caption or "").lower()
    if NO_PEOPLE.search(cap):
        return False
    if any(k in PEOPLE_STRICT and c >= 0.6 for k, c in keywords):
        return True
    return bool(set(re.findall(r"[a-z]+", cap)) & PEOPLE_STRICT)


SCHEMA = """
CREATE TABLE photos(
  idx INTEGER PRIMARY KEY, id TEXT NOT NULL UNIQUE, page_url TEXT, image_url TEXT,
  width INTEGER, height INTEGER, aspect REAL, description TEXT, ai_description TEXT,
  photographer_username TEXT, photographer_name TEXT, downloads INTEGER, views INTEGER,
  featured INTEGER, blur_hash TEXT, location TEXT, country TEXT, submitted_at TEXT,
  keywords TEXT, searches TEXT, collections TEXT, colors TEXT, people_kw INTEGER
);
CREATE VIRTUAL TABLE docs USING fts5(caption, keywords, searches, collections, place, tokenize='porter unicode61');
CREATE TABLE stats(
  idx INTEGER PRIMARY KEY, ok INTEGER, lum REAL, contrast REAL, sat REAL, warmth REAL,
  g_l REAL, g_r REAL, g_t REAL, g_b REAL, g_c REAL, g_all REAL,
  l_l REAL, l_r REAL, l_t REAL, l_b REAL, l_c REAL, fx REAL, fy REAL, people_clip REAL
);
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);
"""

TERMS_MSG = f"""
unclaudey builds its local photo index from the Unsplash Dataset (Lite).
Downloading it means accepting the Unsplash Dataset Terms:
  {config.TERMS_URL}
In short: you may download and store it and use it internally to build models or
algorithms (this local search index). You may not redistribute or publish any part of the
dataset, or publicly disclose comparisons of it with similar datasets. Photos you ship in a
design are resolved through the Unsplash API instead (free key, see `unclaudey.py doctor`).

If the user agrees, re-run with:  setup --accept-unsplash-terms
"""


def _f(x: str | None) -> float | None:
    try:
        return float(x) if x not in (None, "") else None
    except ValueError:
        return None


def _i(x: str | None) -> int:
    v = _f(x)
    return int(v) if v is not None else 0


def download_dataset(dest: Path) -> dict:
    """Stream the Lite zip from Unsplash into the cache. Returns response metadata."""
    import httpx

    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(".part")
    log(f"Downloading Unsplash Lite dataset from {config.LITE_URL} ...")
    t0 = time.time()
    with httpx.stream("GET", config.LITE_URL, follow_redirects=True, timeout=120,
                      headers={"User-Agent": config.user_agent()}) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length") or 0)
        done = 0
        last = 0.0
        with open(part, "wb") as fh:
            for chunk in r.iter_bytes(1 << 20):
                fh.write(chunk)
                done += len(chunk)
                if time.time() - last > 5:
                    last = time.time()
                    pct = f"{100 * done / total:.0f}%" if total else f"{done >> 20} MB"
                    log(f"  {pct}")
        meta = {"last_modified": r.headers.get("last-modified"), "bytes": done}
    part.rename(dest)
    log(f"  done in {time.time() - t0:.0f}s ({done >> 20} MB)")
    return meta


def ensure_dataset(accept_terms: bool) -> Path:
    meta = read_json(config.index_meta_path(), {}) or {}
    if accept_terms and not meta.get("terms_accepted_at"):
        meta["terms_accepted_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        meta["terms_url"] = config.TERMS_URL
        write_json(config.index_meta_path(), meta)
    if not meta.get("terms_accepted_at"):
        raise SystemExit(TERMS_MSG)
    lite = config.lite_dir()
    if all((lite / name).exists() for name in TABLES):
        return lite
    zpath = config.dataset_dir() / "lite-latest.zip"
    if not zpath.exists():
        meta["dataset_download"] = download_dataset(zpath)
        write_json(config.index_meta_path(), meta)
    log("Extracting dataset ...")
    with zipfile.ZipFile(zpath) as z:
        z.extractall(lite)
    return lite


def _reader(path: Path):
    fh = open(path, newline="", encoding="utf-8", errors="replace")
    return fh, csv.DictReader(fh, delimiter="\t", quoting=csv.QUOTE_NONE)


def build_catalog(lite: Path, db_path: Path) -> int:
    t0 = time.time()
    fh, rd = _reader(lite / "photos.tsv000")
    photos = [r for r in rd if r.get("photo_id")]
    fh.close()
    id2idx = {r["photo_id"]: i for i, r in enumerate(photos)}
    log(f"photos: {len(photos)}")

    # keywords: confidence-weighted, user-suggested keywords count as strong signals
    kw: dict[int, dict[str, float]] = collections.defaultdict(dict)
    fh, rd = _reader(lite / "keywords.tsv000")
    for r in rd:
        i = id2idx.get(r["photo_id"])
        if i is None:
            continue
        k = (r.get("keyword") or "").strip().lower()
        if not k:
            continue
        c = max(_f(r.get("ai_service_1_confidence")) or 0.0, _f(r.get("ai_service_2_confidence")) or 0.0) / 100.0
        if r.get("suggested_by_user") == "t":
            c = max(c, 0.9)
        if r.get("confirmed_by_ai_service_3") == "t":
            c = max(c, 0.8)
        if c >= 0.35 and c > kw[i].get(k, 0.0):
            kw[i][k] = c
    fh.close()
    log(f"keywords: {sum(len(v) for v in kw.values())} pairs")

    # conversions: what real people typed before downloading this photo (multilingual)
    conv: dict[int, collections.Counter] = collections.defaultdict(collections.Counter)
    with open(lite / "conversions.tsv000", encoding="utf-8", errors="replace") as cf:
        header = cf.readline().rstrip("\n").split("\t")
        ki, pi = header.index("keyword"), header.index("photo_id")
        need = max(ki, pi)
        for line in cf:
            parts = line.rstrip("\n").split("\t")
            if len(parts) <= need:
                continue
            i = id2idx.get(parts[pi])
            if i is None:
                continue
            k = parts[ki].strip().lower()
            if 1 < len(k) <= 60:
                conv[i][k] += 1
    log(f"conversions: {sum(len(v) for v in conv.values())} distinct photo/query pairs")

    colls: dict[int, collections.Counter] = collections.defaultdict(collections.Counter)
    fh, rd = _reader(lite / "collections.tsv000")
    for r in rd:
        i = id2idx.get(r["photo_id"])
        if i is None:
            continue
        t = (r.get("collection_title") or "").strip().lower()
        if 2 < len(t) <= 40:
            colls[i][t] += 1
    fh.close()

    cols: dict[int, list] = collections.defaultdict(list)
    fh, rd = _reader(lite / "colors.tsv000")
    for r in rd:
        i = id2idx.get(r["photo_id"])
        if i is None:
            continue
        hx = (r.get("hex") or "").strip().lstrip("#").lower()
        if len(hx) != 6:
            continue
        cols[i].append(["#" + hx, _f(r.get("coverage")) or 0.0, _f(r.get("score")) or 0.0, r.get("keyword") or ""])
    fh.close()

    tmp = db_path.with_suffix(".building")
    if tmp.exists():
        tmp.unlink()
    con = sqlite3.connect(tmp)
    con.executescript(SCHEMA)
    rows, docs = [], []
    for i, r in enumerate(photos):
        w, h = _i(r.get("photo_width")), _i(r.get("photo_height"))
        aspect = _f(r.get("photo_aspect_ratio")) or (w / h if w and h else 1.0)
        kws = sorted(kw.get(i, {}).items(), key=lambda kv: -kv[1])[:48]
        searches = conv.get(i, collections.Counter()).most_common(16)
        ctitles = [t for t, _ in colls.get(i, collections.Counter()).most_common(10)]
        colors = sorted(cols.get(i, []), key=lambda c: -c[1])[:8]
        caption = " . ".join(x for x in [(r.get("ai_description") or "").strip(), (r.get("photo_description") or "").strip()] if x)
        name = " ".join(x for x in [r.get("photographer_first_name", ""), r.get("photographer_last_name", "")] if x).strip()
        place = " ".join(x for x in [r.get("photo_location_name", ""), r.get("photo_location_city", ""), r.get("photo_location_country", "")] if x)
        people = int(has_people(kws, caption))
        rows.append((
            i, r["photo_id"], r.get("photo_url"), r.get("photo_image_url"), w, h, aspect,
            (r.get("photo_description") or "").strip(), (r.get("ai_description") or "").strip(),
            r.get("photographer_username"), name or r.get("photographer_username"),
            _i(r.get("stats_downloads")), _i(r.get("stats_views")), int(r.get("photo_featured") == "t"),
            r.get("blur_hash"), place, r.get("photo_location_country"), r.get("photo_submitted_at"),
            json.dumps([[k, round(c, 3)] for k, c in kws]), json.dumps(searches), json.dumps(ctitles),
            json.dumps(colors), people,
        ))
        docs.append((
            i, caption,
            " ".join(k for k, c in kws if c >= 0.5),
            " ".join(k for k, _ in searches),
            " ".join(ctitles),
            place,
        ))
    con.executemany(f"INSERT INTO photos VALUES ({','.join('?' * 23)})", rows)
    con.executemany("INSERT INTO docs(rowid, caption, keywords, searches, collections, place) VALUES (?,?,?,?,?,?)", docs)
    con.executemany("INSERT INTO stats(idx, ok) VALUES (?, 0)", [(i,) for i in range(len(photos))])
    con.execute("INSERT INTO meta VALUES ('dataset', ?)", (json.dumps({"photos": len(photos), "built": time.time()}),))
    con.commit()
    con.execute("INSERT INTO docs(docs) VALUES ('optimize')")
    con.commit()
    con.close()
    tmp.replace(db_path)
    log(f"catalog built in {time.time() - t0:.0f}s -> {db_path}")
    return len(photos)


def refresh_people_keywords(db_path: Path) -> int:
    con = sqlite3.connect(db_path)
    rows = con.execute("SELECT idx, keywords, ai_description, description FROM photos").fetchall()
    upd = [(int(has_people(json.loads(k or "[]"), " . ".join(x for x in (a, d) if x))), i) for i, k, a, d in rows]
    con.executemany("UPDATE photos SET people_kw=? WHERE idx=?", upd)
    con.commit()
    con.close()
    return sum(u[0] for u in upd)
