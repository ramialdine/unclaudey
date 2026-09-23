"""Read `.unclaudey/selection.json` and join each pick with its candidate record.

selection.json (written by Claude after looking at the contact sheets):
{
  "picks": [
    {"slot": "hero", "pick": 3, "alt": "Hands shaping a wet clay bowl on a wheel", "focal": [0.4, 0.5]},
    {"slot": "studio", "id": "Xy12abc", "alt": "...", "decorative": false}
  ]
}
`pick` is the #number on the slot's contact sheet; `id` (or `key`) works too.
"""
from __future__ import annotations

from . import config
from .util import read_json


def resolve_picks(selection: dict) -> list[dict]:
    ws = config.workspace()
    cands = (read_json(ws / "candidates.json", {}) or {}).get("slots", {})
    out = []
    for p in selection.get("picks") or []:
        slot = p.get("slot")
        pool = (cands.get(slot) or {}).get("candidates", [])
        c = None
        if p.get("pick") is not None:
            c = next((x for x in pool if x["n"] == int(p["pick"])), None)
        elif p.get("key") or p.get("id"):
            want = p.get("key") or p.get("id")
            c = next((x for x in pool if want in (x["key"], x["id"])), None)
            if c is None:  # allow picks from another slot's sheet
                for s in cands.values():
                    c = next((x for x in s.get("candidates", []) if want in (x["key"], x["id"])), None)
                    if c:
                        break
        if c is None:
            raise SystemExit(f"selection: could not find {p} in candidates.json (run search for slot '{slot}' first)")
        rec = dict(p)
        rec["candidate"] = dict(c)
        if p.get("focal"):
            rec["candidate"]["focal"] = [float(v) for v in p["focal"]]
        out.append(rec)
    return out
