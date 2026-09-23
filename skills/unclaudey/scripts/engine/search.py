"""Hybrid semantic photo search.

score = z(visual similarity to the slot brief, blended with the global art direction)
      + keyword relevance (BM25 over captions, keywords, real search terms, collections)
      - "avoid" similarity (only when strongly matched)
      + small popularity prior - cross-project reuse penalty
      + copy-space and color bonuses
then hard filters (orientation, size, tone, people, copy space) and MMR diversity.
"""
from __future__ import annotations

import json
import re
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import config
from .colorutil import hex_to_rgb, rgb_to_oklab
from .imagestats import percentile_rank
from .util import orientation_of, read_json, thumb_path, write_json

# Weights (tuned by eyeballing contact sheets across ~25 briefs; see benchmarks/RESULTS.md)
W_KEYWORD = 1.1
W_AVOID = 0.9
W_POP = 0.25
W_REUSE = 0.9
W_COPY = 2.2
W_COLOR = 0.9
W_ART = 0.25  # share of the global art direction in each slot's query vector
W_HUB = 0.5  # subtract this share of each photo's hubness from its raw similarity
COPY_MIN = 0.6  # requested copy-space side must be calmer than 60% of the library
PEOPLE_NONE_MAX = 0.2  # people: none excludes anything that might contain a person
PEOPLE_REQ_MIN = 0.5
MMR_LAMBDA = 0.72
PER_AUTHOR = 2
POOL = 400

DEFAULT_AVOID = [
    "a photo with a watermark or text overlay",
    "a cheesy staged stock photo of people posing with fake smiles",
]

STOP = set("""a an the of and or with without in on at to for from by into over under near about as is are be
this that these those its it their his her photo photograph image picture shot style very some any one two
""".split())

VALID_ORIENT = {"any", "landscape", "portrait", "square", "wide", "tall"}
SIDE = {"left": "l", "right": "r", "top": "t", "bottom": "b", "center": "c"}


@dataclass
class Slot:
    id: str
    brief: str
    keywords: list[str] = field(default_factory=list)
    avoid: list[str] = field(default_factory=list)
    orientation: str = "any"
    min_width: int = 0
    copy_space: str | None = None
    tone: str = "any"
    people: str = "any"
    color: str | None = None
    k: int = 12

    @classmethod
    def from_dict(cls, d: dict, defaults: dict | None = None) -> "Slot":
        d = {**(defaults or {}), **d}
        orient = (d.get("orientation") or "any").lower()
        if orient not in VALID_ORIENT:
            raise SystemExit(f"slot {d.get('id')}: orientation must be one of {sorted(VALID_ORIENT)}")
        kws = d.get("keywords") or []
        if isinstance(kws, str):
            kws = [k.strip() for k in kws.split(",") if k.strip()]
        avoid = d.get("avoid") or []
        if isinstance(avoid, str):
            avoid = [x.strip() for x in avoid.split(",") if x.strip()]
        return cls(
            id=str(d.get("id") or "slot"),
            brief=str(d.get("brief") or d.get("query") or "").strip(),
            keywords=list(kws),
            avoid=list(avoid),
            orientation=orient,
            min_width=int(d.get("min_width") or 0),
            copy_space=_side(d.get("copy_space")),
            tone=(d.get("tone") or "any").lower(),
            people=(d.get("people") or "any").lower(),
            color=d.get("color") or None,
            k=max(4, min(24, int(d.get("k") or d.get("count") or 12))),
        )


def _side(v) -> str | None:
    if not v or str(v).lower() in ("none", "any", "false"):
        return None
    v = str(v).lower()
    if v not in SIDE:
        raise SystemExit(f"copy_space must be one of {sorted(SIDE)}")
    return v


def tokens(texts: list[str]) -> list[str]:
    out: list[str] = []
    for t in texts:
        for w in re.findall(r"[\w']+", t.lower()):
            w = w.strip("'")
            if len(w) >= 2 and w not in STOP and not w.isdigit():
                out.append(w)
    return list(dict.fromkeys(out))


def fts_query(slot: Slot) -> str:
    parts: list[str] = []
    for kw in slot.keywords:
        kw = kw.strip().lower()
        if " " in kw:
            parts.append('"' + kw.replace('"', '""') + '"')
    for t in tokens(slot.keywords + [slot.brief]):
        parts.append('"' + t.replace('"', '""') + '"')
    return " OR ".join(dict.fromkeys(parts))


class Index:
    """The local Unsplash Lite index, loaded into numpy for fast scoring."""

    def __init__(self):
        meta = read_json(config.index_meta_path(), {}) or {}
        if not config.catalog_path().exists():
            raise SystemExit("No local index yet. Ask the user to accept the Unsplash Dataset terms, then run: setup --accept-unsplash-terms")
        self.meta = meta
        self.model_key = meta.get("model") or config.DEFAULT_MODEL
        self.con = sqlite3.connect(f"file:{config.catalog_path()}?mode=ro", uri=True)
        cols = ["idx", "id", "page_url", "image_url", "width", "height", "aspect", "ai_description", "description",
                "photographer_username", "photographer_name", "downloads", "blur_hash", "colors", "people_kw",
                "ok", "lum", "sat", "warmth", "g_l", "g_r", "g_t", "g_b", "g_c", "l_l", "l_r", "l_t", "l_b", "l_c",
                "fx", "fy", "people_clip"]
        rows = self.con.execute(
            "SELECT p.idx, p.id, p.page_url, p.image_url, p.width, p.height, p.aspect, p.ai_description, p.description,"
            " p.photographer_username, p.photographer_name, p.downloads, p.blur_hash, p.colors, p.people_kw,"
            " s.ok, s.lum, s.sat, s.warmth, s.g_l, s.g_r, s.g_t, s.g_b, s.g_c, s.l_l, s.l_r, s.l_t, s.l_b, s.l_c,"
            " s.fx, s.fy, s.people_clip FROM photos p JOIN stats s USING(idx) ORDER BY p.idx").fetchall()
        self.n = len(rows)
        c = {name: [r[i] for r in rows] for i, name in enumerate(cols)}
        self.ids = c["id"]
        self.page_url, self.image_url = c["page_url"], c["image_url"]
        self.caption = [(a or b or "") for a, b in zip(c["ai_description"], c["description"])]
        self.author = c["photographer_username"]
        self.author_name = c["photographer_name"]
        self.blur_hash = c["blur_hash"]
        self.colors_json = c["colors"]
        f = lambda k: np.array([x if x is not None else np.nan for x in c[k]], dtype=np.float64)  # noqa: E731
        self.width, self.height, self.aspect = f("width"), f("height"), f("aspect")
        self.ok = np.array([bool(x) for x in c["ok"]])
        self.visual = False
        emb_file = config.emb_path(self.model_key)
        if emb_file.exists() and self.ok.any():
            self.E = np.load(emb_file).astype(np.float32)
            self.visual = True
            hp = config.hub_path(self.model_key)
            self.hub = np.load(hp).astype(np.float64) if hp.exists() else np.zeros(self.n)
        else:
            self.E = None
            self.ok = np.ones(self.n, dtype=bool)  # keyword-only mode: everything is searchable
        self.lum, self.sat = f("lum"), f("sat")
        self.fx, self.fy = f("fx"), f("fy")
        self.people_kw = np.array([bool(x) for x in c["people_kw"]])
        self.people_clip = f("people_clip")
        okm = self.ok & ~np.isnan(self.lum) if self.visual else np.zeros(self.n, dtype=bool)
        self.okm = okm
        # dataset-relative ranks (0..1); calm = 1 - rank(gradient energy)
        self.calm, self.region_lum, self.sorted_g = {}, {}, {}
        for r in ("l", "r", "t", "b", "c"):
            g = f(f"g_{r}")
            rank = np.full(self.n, 0.5)
            if okm.any():
                rank[okm] = percentile_rank(g[okm])
                self.sorted_g[r] = np.sort(g[okm])
            self.calm[r] = 1.0 - rank
            self.region_lum[r] = f(f"l_{r}")
        self.lum_rank = np.full(self.n, 0.5)
        if okm.any():
            self.lum_rank[okm] = percentile_rank(self.lum[okm])
            self.sorted_lum = np.sort(self.lum[okm])
        else:
            self.sorted_lum = np.array([])
        dl = np.log1p(f("downloads"))
        self.pop = percentile_rank(np.nan_to_num(dl))
        self._color_lab = None
        self._embedder = None

    # --- model -----------------------------------------------------------------
    def embedder(self):
        if self._embedder is None:
            from .embed import Embedder

            # Text encoding is fast on CPU and avoids GPU warm-up for small batches.
            self._embedder = Embedder(self.model_key, device="cpu")
        return self._embedder

    # --- keyword relevance ---------------------------------------------------------
    def bm25(self, slot: Slot) -> np.ndarray:
        out = np.zeros(self.n)
        q = fts_query(slot)
        if not q:
            return out
        try:
            rows = self.con.execute(
                "SELECT rowid, -bm25(docs, 3.0, 2.0, 1.5, 0.5, 1.0) FROM docs WHERE docs MATCH ? LIMIT 5000", (q,)).fetchall()
        except sqlite3.OperationalError:
            return out
        if rows:
            ids = np.array([r[0] for r in rows])
            sc = np.array([r[1] for r in rows], dtype=np.float64)
            out[ids] = sc / (sc.max() or 1.0)
        return out

    def color_distance(self, target_hex: str) -> np.ndarray:
        if self._color_lab is None:
            labs = []
            for cj in self.colors_json:
                cols = [c for c in (json.loads(cj) if cj else []) if c[1] >= 0.06][:5]
                labs.append(rgb_to_oklab(np.array([hex_to_rgb(c[0]) for c in cols])) if cols else None)
            self._color_lab = labs
        t = rgb_to_oklab(hex_to_rgb(target_hex))
        d = np.full(self.n, 1.0)
        for i, lab in enumerate(self._color_lab):
            if lab is not None:
                d[i] = float(np.min(np.linalg.norm(lab - t, axis=1)))
        return d

    # --- filters -----------------------------------------------------------------
    def mask(self, slot: Slot) -> np.ndarray:
        m = self.ok.copy()
        a = np.nan_to_num(self.aspect, nan=1.0)
        o = slot.orientation
        if o == "landscape":
            m &= a >= 1.2
        elif o == "wide":
            m &= a >= 1.6
        elif o == "portrait":
            m &= a <= 0.83
        elif o == "tall":
            m &= a <= 0.7
        elif o == "square":
            m &= (a > 0.83) & (a < 1.2)
        if slot.min_width:
            m &= np.nan_to_num(self.width) >= slot.min_width
        if self.visual:
            if slot.tone == "dark":
                m &= self.lum_rank <= 0.3
            elif slot.tone == "light":
                m &= self.lum_rank >= 0.7
            elif slot.tone == "mid":
                m &= (self.lum_rank > 0.25) & (self.lum_rank < 0.75)
            if slot.people == "none":
                m &= ~self.people_kw & (np.nan_to_num(self.people_clip, nan=1.0) < PEOPLE_NONE_MAX)
            elif slot.people == "required":
                m &= self.people_kw | (np.nan_to_num(self.people_clip, nan=0.0) >= PEOPLE_REQ_MIN)
            if slot.copy_space:
                m &= self.calm[SIDE[slot.copy_space]] >= COPY_MIN
        else:
            if slot.people == "none":
                m &= ~self.people_kw
            elif slot.people == "required":
                m &= self.people_kw
        return m

    # --- search ------------------------------------------------------------------
    def score(self, slot: Slot, qvec: np.ndarray | None, avoid_vecs: np.ndarray | None,
              reuse: set[str]) -> tuple[np.ndarray, dict[str, np.ndarray]]:
        parts: dict[str, np.ndarray] = {}
        s = np.zeros(self.n)
        zv = None
        if self.visual and qvec is not None:
            raw = self.E @ qvec
            v = raw - W_HUB * self.hub
            mu, sd = v[self.okm].mean(), v[self.okm].std() + 1e-9
            zv = (v - mu) / sd
            parts["visual"] = zv
            s += zv
            self._vstats = (mu, sd)
            self._raw = raw
        bm = self.bm25(slot)
        if zv is not None:
            # keywords only count for photos that also look right ("potter" also matches owls
            # downloaded by people searching "harry potter")
            bm = bm * np.clip((zv - 0.5) / 2.0, 0.0, 1.0)
            parts["keywords"] = bm
            s += W_KEYWORD * bm
        else:
            parts["keywords"] = bm
            s += W_KEYWORD * 4.0 * bm
        if self.visual and avoid_vecs is not None and len(avoid_vecs):
            va = (self.E @ avoid_vecs.T)
            za = (va - va[self.okm].mean(axis=0)) / (va[self.okm].std(axis=0) + 1e-9)
            pen = np.clip(za.max(axis=1) - 1.5, 0, None)
            parts["avoid"] = -W_AVOID * pen
            s += parts["avoid"]
            self._astats = (va[self.okm].mean(axis=0), va[self.okm].std(axis=0) + 1e-9)
        s += W_POP * (self.pop - 0.5)
        if reuse:
            pen = np.array([1.0 if f"unsplash:{pid}" in reuse else 0.0 for pid in self.ids])
            parts["reuse"] = -W_REUSE * pen
            s += parts["reuse"]
        if slot.copy_space and self.visual:
            parts["copy_space"] = W_COPY * (self.calm[SIDE[slot.copy_space]] - 0.5)
            s += parts["copy_space"]
        if slot.color:
            d = self.color_distance(slot.color)
            parts["color"] = W_COLOR * np.exp(-((d / 0.09) ** 2))
            s += parts["color"]
        s = np.where(self.mask(slot), s, -np.inf)
        return s, parts

    def candidate(self, i: int, score: float, parts: dict) -> dict:
        w, h = self.width[i], self.height[i]
        aspect = float(self.aspect[i]) if not np.isnan(self.aspect[i]) else (w / h if w and h else 1.0)
        cols = json.loads(self.colors_json[i]) if self.colors_json[i] else []
        cand = {
            "key": f"unsplash:{self.ids[i]}",
            "source": "unsplash",
            "origin": "index",
            "id": self.ids[i],
            "score": round(float(score), 3),
            "why": {k: round(float(v[i]), 3) for k, v in parts.items() if abs(float(v[i])) > 1e-6},
            "width": int(w) if not np.isnan(w) else None,
            "height": int(h) if not np.isnan(h) else None,
            "aspect": round(aspect, 3),
            "orientation": orientation_of(aspect),
            "description": self.caption[i],
            "photographer": self.author_name[i],
            "photographer_username": self.author[i],
            "page_url": self.page_url[i],
            "image_url": self.image_url[i],
            "thumb": str(thumb_path("unsplash", self.ids[i])),
            "blur_hash": self.blur_hash[i],
            "colors": [c[0] for c in cols[:5]],
            "license": "Unsplash License (resolve via API before publishing)",
        }
        if self.visual and not np.isnan(self.lum[i]):
            cand["lum"] = round(float(self.lum[i]), 3)
            cand["calm"] = {r: round(float(self.calm[r][i]), 2) for r in ("l", "r", "t", "b", "c")}
            cand["region_lum"] = {r: round(float(self.region_lum[r][i]), 2) for r in ("l", "r", "t", "b", "c")}
            cand["focal"] = [float(self.fx[i]), float(self.fy[i])]
            cand["people"] = bool(self.people_kw[i] or (self.people_clip[i] >= PEOPLE_REQ_MIN))
        return cand


def mmr_select(order: list[int], scores: np.ndarray, vecs: np.ndarray | None, authors: list[str], k: int,
               lam: float = MMR_LAMBDA, per_author: int = PER_AUTHOR) -> list[int]:
    """Pick k diverse items from a ranked pool. `order` indexes rows of scores/vecs/authors."""
    if not order:
        return []
    s = np.array([scores[j] for j in order], dtype=np.float64)
    s = (s - s.min()) / (s.max() - s.min() + 1e-9)
    chosen: list[int] = []
    counts: dict[str, int] = {}
    maxsim = np.zeros(len(order))
    V = vecs[order] if vecs is not None else None
    avail = np.ones(len(order), dtype=bool)
    while len(chosen) < k and avail.any():
        val = lam * s - (1 - lam) * maxsim if V is not None else s.copy()
        val[~avail] = -np.inf
        j = int(np.argmax(val))
        if not np.isfinite(val[j]):
            break
        avail[j] = False
        a = authors[order[j]] or "?"
        if counts.get(a, 0) >= per_author:
            continue
        if V is not None and chosen and maxsim[j] > 0.95:
            continue  # near-duplicate of something already chosen
        counts[a] = counts.get(a, 0) + 1
        chosen.append(order[j])
        if V is not None:
            maxsim = np.maximum(maxsim, V @ V[j])
    return chosen


def load_usage() -> dict:
    return read_json(config.usage_path(), {}) or {}


def reuse_set(project: str) -> set[str]:
    out = set()
    for key, rec in load_usage().items():
        projects = rec.get("projects", {})
        if any(p != project for p in projects):
            out.add(key)
    return out


def run_plan(plan: dict, only: list[str] | None = None, expand: list[str] | None = None,
             k_override: int | None = None) -> dict:
    from . import sheets

    t0 = time.time()
    idx = Index()
    ws = config.workspace()
    art = (plan.get("art_direction") or "").strip()
    global_avoid = list(plan.get("avoid") or [])
    if plan.get("use_default_avoid", True):
        global_avoid += DEFAULT_AVOID
    defaults = plan.get("defaults") or {}
    slots = [Slot.from_dict(s, defaults) for s in plan.get("slots") or []]
    if only:
        slots = [s for s in slots if s.id in only]
    if not slots:
        raise SystemExit("The plan has no slots. Each slot needs at least an id and a brief.")
    if k_override:
        for s in slots:
            s.k = max(4, min(24, k_override))

    emb = idx.embedder() if idx.visual else None
    art_vec = emb.prompts([art])[0] if (emb and art) else None
    reuse = reuse_set(str(Path.cwd()))
    out_path = ws / "candidates.json"
    existing = read_json(out_path, {}) or {}
    result = {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "model": idx.model_key if idx.visual else "keywords-only",
              "art_direction": art, "slots": dict(existing.get("slots", {})) if only else {}}

    for slot in slots:
        if not slot.brief:
            raise SystemExit(f"slot {slot.id}: missing brief")
        qvec = avoid_vecs = None
        if emb is not None:
            q = emb.prompts([slot.brief])[0]
            if art_vec is not None:
                q = (1 - W_ART) * q + W_ART * art_vec
            qvec = q / np.linalg.norm(q)
            avoids = slot.avoid + global_avoid
            avoid_vecs = emb.prompts(avoids) if avoids else None
        scores, parts = idx.score(slot, qvec, avoid_vecs, reuse)
        finite = np.isfinite(scores)
        pool = list(np.argsort(-scores)[: min(POOL, int(finite.sum()))])
        live: list[dict] = []
        if expand:
            from .providers import live_candidates

            live = live_candidates(slot, expand, idx, qvec, avoid_vecs, reuse)
        chosen = mmr_select(pool, scores, idx.E if idx.visual else None, idx.author, slot.k)
        cands = [idx.candidate(i, scores[i], parts) for i in chosen]
        if live:
            cands = merge_live(cands, live, slot.k, idx)
        for n, c in enumerate(cands, 1):
            c["n"] = n
        coverage, warn = "n/a", None
        if idx.visual and qvec is not None and finite.any():
            top5 = float(np.sort(idx._raw[finite])[-5:].mean())
            weak, fair = config.COVERAGE.get(idx.model_key, (0.0, 0.0))
            coverage = "weak" if top5 < weak else "fair" if top5 < fair else "good"
            if coverage == "weak" and not expand:
                warn = ("The local library barely covers this subject (coverage: weak). Don't settle: run this slot "
                        "again with --expand unsplash,openverse, or rewrite the brief around what the library has.")
            elif coverage == "fair" and not expand:
                warn = "Coverage is only fair: check the subject closely; --expand unsplash,openverse may find better."
        if not cands:
            warn = "No photos passed the filters. Relax orientation/tone/people/copy_space, or try --expand."
        sheet = ws / "sheets" / f"{slot.id}.jpg"
        sheets.contact_sheet(slot, cands, sheet, coverage=coverage)
        result["slots"][slot.id] = {"slot": slot.__dict__, "sheet": str(sheet), "coverage": coverage, "warning": warn,
                                    "candidates": cands, "pool_size": int(finite.sum())}
    write_json(out_path, result)
    result["_elapsed"] = round(time.time() - t0, 2)
    return result


def merge_live(local: list[dict], live: list[dict], k: int, idx: "Index") -> list[dict]:
    """Merge live results with local ones by score. When the user asked to expand, at least a
    third of the sheet goes to the best live results so they actually get looked at."""
    seen = {c["key"] for c in local}
    live = sorted((c for c in live if c["key"] not in seen), key=lambda c: -c["score"])
    if not live:
        return local[:k]
    n_live = min(len(live), max(k // 3, 1))
    rest = sorted(local + live[n_live:], key=lambda c: -c["score"])
    return sorted(live[:n_live] + rest[: k - n_live], key=lambda c: -c["score"])


def run_cli(a) -> int:
    ws = config.workspace()
    if a.query:
        slot = {"id": "quick", "brief": a.query, "orientation": a.orientation or "any", "copy_space": a.copy_space,
                "tone": a.tone or "any", "people": a.people or "any", "color": a.color, "min_width": a.min_width or 0,
                "avoid": a.avoid or [], "k": a.k or 12}
        plan = {"slots": [slot]}
    else:
        plan_path = Path(a.plan or (ws / "plan.json"))
        plan = read_json(plan_path)
        if plan is None:
            raise SystemExit(f"No plan at {plan_path}. Write one (see SKILL.md 'Image plan') or pass a quick query.")
    only = [s.strip() for s in a.slot.split(",")] if a.slot else None
    expand = [p.strip() for p in a.expand.split(",")] if a.expand else None
    res = run_plan(plan, only=only, expand=expand, k_override=a.k)
    if a.json:
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return 0
    print(f"searched {len(res['slots'])} slot(s) in {res['_elapsed']}s with {res['model']}")
    for sid, s in res["slots"].items():
        if only and sid not in only:
            continue
        print(f"\n[{sid}] {s['slot']['brief']}")
        print(f"  contact sheet: {s['sheet']}   ({len(s['candidates'])} of {s['pool_size']} eligible, coverage: {s.get('coverage')})")
        if s.get("warning"):
            print(f"  ! {s['warning']}")
        for c in s["candidates"][:5]:
            print(f"  #{c['n']:<2} {c['orientation']:<9} {c.get('width')}x{c.get('height')}  {c['source']}/{c['origin']}  {c['description'][:70]}")
    print(f"\nNext: view each contact sheet image, then write {ws / 'selection.json'} (see SKILL.md).")
    return 0
