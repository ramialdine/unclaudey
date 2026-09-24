"""Turn picks into publishable image records.

Unsplash photos found in the local index are looked up through the Unsplash API (official
URLs, current photographer name) and their download is tracked, as the API guidelines
require. Without a key the picks stay in *draft* mode: fine for local previews, not for
shipping. Openverse picks carry their license and attribution through unchanged.
"""
from __future__ import annotations

import time

from . import config
from .selection import resolve_picks
from .util import read_json, write_json


def utm(url: str | None) -> str | None:
    if not url:
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}utm_source={config.app_name()}&utm_medium=referral"


def resolve(selection: dict) -> dict:
    from .providers import unsplash

    picks = resolve_picks(selection)
    key = config.unsplash_key()
    out = []
    remaining = None
    for p in picks:
        c = p["candidate"]
        rec = {
            "slot": p["slot"], "key": c["key"], "source": c["source"], "id": c["id"],
            "alt": (p.get("alt") or "").strip(), "decorative": bool(p.get("decorative")),
            "focal": c.get("focal") or [0.5, 0.5], "sizes": p.get("sizes"), "role": p.get("role"),
            "hero": p.get("hero"),
            "width": c.get("width"), "height": c.get("height"), "blur_hash": c.get("blur_hash"),
            "description": c.get("description"), "colors": c.get("colors") or [],
        }
        if c["source"] == "unsplash":
            if key:
                data, info = unsplash.get_photo(c["id"])
                remaining = info.get("x-ratelimit-remaining", remaining)
                if data is None:
                    rec.update(status="unavailable", error=f"Unsplash API returned {info.get('status')}; pick another photo")
                    out.append(rec)
                    continue
                user = data.get("user") or {}
                tracked = unsplash.track_download((data.get("links") or {}).get("download_location", ""))
                rec.update(
                    status="resolved", base_url=(data.get("urls") or {}).get("raw"),
                    width=data.get("width") or rec["width"], height=data.get("height") or rec["height"],
                    blur_hash=data.get("blur_hash") or rec["blur_hash"],
                    photographer=user.get("name"), photographer_url=utm((user.get("links") or {}).get("html")),
                    page_url=utm((data.get("links") or {}).get("html")), download_tracked=tracked,
                    license="Unsplash License", license_url="https://unsplash.com/license",
                    credit_html=None,
                )
            else:
                rec.update(
                    status="draft", base_url=c.get("image_url"),
                    photographer=c.get("photographer"),
                    photographer_url=utm(f"https://unsplash.com/@{c.get('photographer_username')}") if c.get("photographer_username") else None,
                    page_url=utm(c.get("page_url")), download_tracked=False,
                    license="Unsplash License (unresolved draft)", license_url="https://unsplash.com/license",
                )
        else:  # openverse and other openly licensed sources
            rec.update(
                status="resolved", base_url=c.get("image_url"), photographer=c.get("photographer"),
                photographer_url=c.get("photographer_url"), page_url=c.get("page_url"),
                license=c.get("license"), license_url=c.get("license_url"), attribution=c.get("attribution"),
                download_tracked=None,
            )
        out.append(rec)
    result = {"resolved_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "app": config.app_name(),
              "has_key": bool(key), "images": out}
    if remaining is not None:
        result["unsplash_requests_left_this_hour"] = remaining
    return result


def run_cli(a) -> int:
    ws = config.workspace()
    sel = read_json(a.selection or (ws / "selection.json"))
    if sel is None:
        raise SystemExit("No selection.json yet. Choose photos first (see SKILL.md).")
    res = resolve(sel)
    write_json(ws / "resolved.json", res)
    missing_alt = [i["slot"] for i in res["images"] if not i["alt"] and not i["decorative"]]
    w = max((len(i["slot"]) for i in res["images"]), default=10) + 2
    for i in res["images"]:
        print(f"{i['slot']:<{w}} {i['status']:<11} {i['key']:<32} {i.get('photographer') or ''}")
    if not res["has_key"]:
        print("\n! No UNSPLASH_ACCESS_KEY: Unsplash picks are DRAFT (fine for local previews, not for publishing).")
        print(f"  Get a free key at {config.KEY_HELP_URL} and put it in ~/.config/unclaudey/.env (see README).")
    if any(i["status"] == "unavailable" for i in res["images"]):
        print("\n! Some photos are no longer available on Unsplash. Pick replacements from the contact sheet.")
    if missing_alt:
        print(f"\n! Missing alt text for: {', '.join(missing_alt)} (add \"alt\" in selection.json, or \"decorative\": true)")
    if res.get("unsplash_requests_left_this_hour"):
        print(f"\nUnsplash API: {res['unsplash_requests_left_this_hour']} requests left this hour")
    print(f"\nwrote {ws / 'resolved.json'}. Next: export --mode hotlink (websites) or --mode inline (artifacts)")
    return 0
