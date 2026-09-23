"""Unsplash API: live search, photo lookup, and download tracking.

API guidelines (https://help.unsplash.com/en/articles/2511245-unsplash-api-guidelines):
hotlink the returned `urls`, call `links.download_location` when a photo is used, and credit
the photographer and Unsplash with utm_source=<app>&utm_medium=referral links.
"""
from __future__ import annotations

from urllib.parse import quote_plus

from .. import config
from ..util import http_client, log

ORIENT = {"landscape": "landscape", "wide": "landscape", "portrait": "portrait", "tall": "portrait", "square": "squarish"}


def headers() -> dict:
    key = config.unsplash_key()
    if not key:
        raise RuntimeError("UNSPLASH_ACCESS_KEY is not set (see `unclaudey.py doctor`)")
    return {"Authorization": f"Client-ID {key}", "Accept-Version": "v1"}


def _item(p: dict) -> dict:
    user = p.get("user") or {}
    return {
        "key": f"unsplash:{p['id']}", "source": "unsplash", "id": p["id"],
        "thumb_url": (p.get("urls") or {}).get("small"),
        "image_url": (p.get("urls") or {}).get("raw"),
        "width": p.get("width"), "height": p.get("height"),
        "description": " . ".join(x for x in [p.get("alt_description"), p.get("description")] if x),
        "tags": [t.get("title") for t in (p.get("tags") or []) if t.get("title")],
        "photographer": user.get("name"), "photographer_username": user.get("username"),
        "photographer_url": (user.get("links") or {}).get("html"),
        "page_url": (p.get("links") or {}).get("html"),
        "download_location": (p.get("links") or {}).get("download_location"),
        "blur_hash": p.get("blur_hash"), "color": p.get("color"),
        "license": "Unsplash License", "license_url": "https://unsplash.com/license",
    }


def search(query: str, slot, per_page: int = 30) -> list[dict]:
    from . import cached_get_json

    if not config.unsplash_key():
        log("unsplash: no UNSPLASH_ACCESS_KEY, skipping live Unsplash search")
        return []
    url = f"{config.unsplash_api_base()}/search/photos?query={quote_plus(query)}&per_page={per_page}&content_filter=high"
    if slot.orientation in ORIENT:
        url += f"&orientation={ORIENT[slot.orientation]}"
    data, info = cached_get_json(url, headers=headers())
    if data is None:
        log(f"unsplash: search failed ({info.get('status')})")
        return []
    if info.get("x-ratelimit-remaining"):
        log(f"unsplash: {info['x-ratelimit-remaining']} requests left this hour")
    return [_item(p) for p in data.get("results", []) if (p.get("urls") or {}).get("small")]


def get_photo(photo_id: str) -> tuple[dict | None, dict]:
    client = http_client(timeout=30)
    try:
        r = client.get(f"{config.unsplash_api_base()}/photos/{photo_id}", headers=headers())
    finally:
        client.close()
    info = {k.lower(): v for k, v in r.headers.items() if "ratelimit" in k.lower()}
    info["status"] = r.status_code
    return (r.json() if r.status_code == 200 else None), info


def track_download(download_location: str) -> bool:
    """Required by the API guidelines whenever a photo is used in a design."""
    client = http_client(timeout=30)
    try:
        r = client.get(download_location, headers=headers())
        return r.status_code == 200
    finally:
        client.close()
