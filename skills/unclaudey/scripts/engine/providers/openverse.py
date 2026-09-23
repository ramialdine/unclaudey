"""Openverse (openverse.org): keyless search over openly licensed images.

Only licenses that allow commercial use *and* modification are requested (no NC, no ND),
because designs crop and recolor photos. Most results still require attribution, which
export writes into the credits.
"""
from __future__ import annotations

from urllib.parse import quote_plus

from ..util import log

API = "https://api.openverse.org/v1/images/"
ASPECT = {"landscape": "wide", "wide": "wide", "portrait": "tall", "tall": "tall", "square": "square"}


def search(query: str, slot, page_size: int = 20) -> list[dict]:  # anonymous max is 20
    from . import cached_get_json

    url = (f"{API}?q={quote_plus(query)}&license_type=commercial,modification&category=photograph"
           f"&page_size={page_size}&mature=false")
    if slot.orientation in ASPECT:
        url += f"&aspect_ratio={ASPECT[slot.orientation]}"
    if slot.min_width and slot.min_width >= 1200:
        url += "&size=large"
    data, info = cached_get_json(url)
    if data is None:
        st = info.get("status")
        why = {401: "request not allowed anonymously", 429: "rate limited (anonymous: 20/min, 200/day); try again shortly",
               403: "blocked by Openverse's bot protection; try again later"}.get(st, "")
        log(f"openverse: search failed ({st}) {why}")
        return []
    out = []
    for r in data.get("results", []):
        lic = (r.get("license") or "").lower()
        if lic.startswith("by-nc") or "nd" in lic.split("-"):
            continue
        out.append({
            "key": f"openverse:{r['id']}", "source": "openverse", "id": r["id"],
            "thumb_url": r.get("thumbnail") or r.get("url"), "image_url": r.get("url"),
            "width": r.get("width"), "height": r.get("height"),
            "description": r.get("title") or "",
            "tags": [t.get("name") for t in (r.get("tags") or []) if t.get("name")][:20],
            "photographer": r.get("creator"), "photographer_url": r.get("creator_url"),
            "page_url": r.get("foreign_landing_url"),
            "license": f"{(r.get('license') or '').upper()} {r.get('license_version') or ''}".strip(),
            "license_url": r.get("license_url"), "attribution": r.get("attribution"),
            "provider": r.get("source"),
        })
    return out
