"""Write the image manifest, ready-to-paste markup, and credits.

Modes
  hotlink  (default, websites) responsive Unsplash CDN URLs, as the Unsplash API guidelines require
  inline   (sandboxed artifacts / single-file HTML) compressed WebP data URIs within a size budget
  download (self-hosting) WebP files written to --out; Unsplash photos stay hotlinked
"""
from __future__ import annotations

import base64
import html
import io
import time
from pathlib import Path

import numpy as np
from PIL import Image

from . import config
from .util import add_query, fetch_bytes, http_client, log, read_json, write_json

WIDTHS = [480, 768, 1080, 1440, 1920, 2560]
HERO_WORDS = ("hero", "cover", "banner", "header", "background", "bg", "masthead", "splash")


def is_hero(rec: dict) -> bool:
    """Eager-load only the real hero: an explicit "hero": true on the pick, or a hero-like slot id.
    (On many pages, e.g. an API homepage, the first photo sits mid-page and should stay lazy.)"""
    if rec.get("hero") is not None:
        return bool(rec["hero"])
    s = rec["slot"].lower()
    return any(w in s for w in HERO_WORDS)


def lqip(blur_hash: str | None, aspect: float) -> str | None:
    if not blur_hash:
        return None
    try:
        import blurhash

        w = 32
        h = max(4, int(round(w / max(aspect, 0.2))))
        px = np.array(blurhash.decode(blur_hash, w, h), dtype=np.uint8)
        buf = io.BytesIO()
        Image.fromarray(px, "RGB").save(buf, "PNG", optimize=True)
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return None


def credit(rec: dict) -> dict:
    name = html.escape(rec.get("photographer") or "Unknown")
    if rec["source"] == "unsplash":
        purl = rec.get("photographer_url") or "https://unsplash.com"
        uurl = f"https://unsplash.com/?utm_source={config.app_name()}&utm_medium=referral"
        return {
            "text": f"Photo by {rec.get('photographer')} on Unsplash",
            "html": f'Photo by <a href="{html.escape(purl)}">{name}</a> on <a href="{uurl}">Unsplash</a>',
            "photographer_html": f'<a href="{html.escape(purl)}">{name}</a>',
        }
    lic = html.escape(rec.get("license") or "")
    lurl = html.escape(rec.get("license_url") or "")
    page = html.escape(rec.get("page_url") or "")
    by = f'<a href="{html.escape(rec.get("photographer_url") or page)}">{name}</a>' if rec.get("photographer") else "Unknown creator"
    lic_html = f'<a href="{lurl}">{lic}</a>' if lurl else lic
    return {
        "text": rec.get("attribution") or f"Photo by {rec.get('photographer')} ({rec.get('license')})",
        "html": f'<a href="{page}">Photo</a> by {by}, {lic_html}',
        "photographer_html": by,
    }


def _encode_webp(im: Image.Image, width: int, quality: int) -> bytes:
    im = im.convert("RGB")
    if im.width > width:
        im = im.resize((width, int(im.height * width / im.width)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "WEBP", quality=quality, method=5)
    return buf.getvalue()


def _source_image(client, rec: dict, width: int) -> Image.Image | None:
    url = rec.get("base_url")
    if not url:
        return None
    if rec["source"] == "unsplash":
        url = add_query(url, w=width, q=82, fm="jpg", fit="max")
    data = fetch_bytes(client, url)
    if not data:
        return None
    im = Image.open(io.BytesIO(data))
    im.load()
    return im


def public_url_prefix(out: Path) -> str:
    """public/images -> /images (Next, Vite, Astro serve public/ at the site root)."""
    s = out.as_posix().rstrip("/")
    if s == "public":
        return ""
    if s.startswith("public/"):
        return "/" + s[len("public/"):]
    if "/public/" in s:
        return "/" + s.split("/public/", 1)[1]
    return s


def img_tag(e: dict) -> str:
    attrs = [f'src="{html.escape(e["src"])}"']
    if e.get("srcset"):
        attrs.append(f'srcset="{html.escape(e["srcset"])}"')
        attrs.append(f'sizes="{html.escape(e["sizes"])}"')
    attrs += [f'width="{e["width"]}"', f'height="{e["height"]}"', f'alt="{html.escape(e["alt"])}"']
    if e["hero"]:
        attrs += ['fetchpriority="high"', 'decoding="async"']
    else:
        attrs += ['loading="lazy"', 'decoding="async"']
    style = f"object-fit:cover;object-position:{e['object_position']}"
    if e.get("lqip") and not e["src"].startswith("data:"):
        style += f";background:{e.get('placeholder_color', '#888')} url({e['lqip']}) center/cover no-repeat"
    attrs.append(f'style="{style}"')
    return f"<img {' '.join(attrs)}>"


def export(resolved: dict, mode: str, out_dir: str | None, budget_kb: int, allow_draft: bool) -> dict:
    imgs = resolved.get("images") or []
    problems = []
    for r in imgs:
        if r["status"] == "unavailable":
            problems.append(f"{r['slot']}: photo unavailable, pick another")
        if r["status"] == "draft" and not allow_draft:
            problems.append(f"{r['slot']}: draft (no Unsplash key); resolve with a key, or pass --allow-draft for local previews")
        if not r.get("alt") and not r.get("decorative"):
            problems.append(f"{r['slot']}: missing alt text")
    if problems:
        raise SystemExit("export blocked:\n  " + "\n  ".join(problems))

    client = http_client()
    entries = []
    total = 0
    for r in imgs:
        w, h = int(r.get("width") or 1600), int(r.get("height") or 1067)
        aspect = w / h if h else 1.5
        hero = is_hero(r)
        fx, fy = (r.get("focal") or [0.5, 0.5])
        e = {
            "slot": r["slot"], "key": r["key"], "status": r["status"], "hero": hero,
            "alt": "" if r.get("decorative") else r.get("alt", ""), "decorative": bool(r.get("decorative")),
            "object_position": f"{round(fx * 100)}% {round(fy * 100)}%", "focal": [fx, fy],
            "sizes": r.get("sizes") or ("100vw" if hero else "(min-width: 1024px) 50vw, 100vw"),
            "original_width": w, "original_height": h, "lqip": lqip(r.get("blur_hash"), aspect),
            "credit": credit(r), "license": r.get("license"), "license_url": r.get("license_url"),
            "page_url": r.get("page_url"), "photographer": r.get("photographer"),
            "placeholder_color": (r.get("colors") or ["#8a8a8a"])[0],
        }
        display_w = min(1600 if hero else 1080, w)
        e["width"], e["height"] = display_w, int(round(display_w / aspect))
        use_mode = mode
        if mode == "download" and r["source"] == "unsplash":
            use_mode = "hotlink"  # Unsplash API guidelines: hotlink the returned URLs
            e["note"] = "Unsplash photo kept hotlinked (API guideline)"
        if use_mode == "hotlink":
            if r["source"] == "unsplash":
                ws_ = [x for x in WIDTHS if x <= w] or [w]
                e["src"] = add_query(r["base_url"], w=display_w, q=75, auto="format", fit="max")
                e["srcset"] = ", ".join(f"{add_query(r['base_url'], w=x, q=75, auto='format', fit='max')} {x}w" for x in ws_)
            else:
                e["src"] = r["base_url"]
                e["srcset"] = None
        elif use_mode == "inline":
            target = 1600 if hero else 1000
            im = _source_image(client, r, target)
            if im is None:
                raise SystemExit(f"{r['slot']}: could not download the image for inlining")
            e["_im"] = im
        elif use_mode == "download":
            outp = Path(out_dir or "public/images")
            outp.mkdir(parents=True, exist_ok=True)
            im = _source_image(client, r, max(x for x in WIDTHS if x <= max(w, 480)))
            if im is None:
                raise SystemExit(f"{r['slot']}: could not download the image")
            files = []
            for x in [x for x in (640, 1080, 1600, 2400) if x <= im.width] or [im.width]:
                fname = outp / f"{r['slot']}-{x}.webp"
                fname.write_bytes(_encode_webp(im, x, 78))
                files.append((fname, x))
            prefix = public_url_prefix(outp)
            e["src"] = f"{prefix}/{files[min(1, len(files) - 1)][0].name}"
            e["srcset"] = ", ".join(f"{prefix}/{f.name} {x}w" for f, x in files)
            e["files"] = [str(f) for f, _ in files]
        entries.append(e)

    if mode == "inline":
        quality, scale = 74, 1.0
        for _ in range(8):
            total = 0
            for e in entries:
                if "_im" in e:
                    target = int((1600 if e["hero"] else 1000) * scale)
                    data = _encode_webp(e["_im"], target, quality)
                    e["src"] = "data:image/webp;base64," + base64.b64encode(data).decode()
                    e["srcset"] = None
                    e["bytes"] = len(data)
                    total += len(data) * 4 // 3
            if total <= budget_kb * 1024:
                break
            quality, scale = max(55, quality - 5), scale * 0.85
        for e in entries:
            e.pop("_im", None)
        log(f"inline: {total // 1024} KB of images embedded (budget {budget_kb} KB, q={quality})")
    client.close()
    for e in entries:
        e["html"] = img_tag(e)
    return {
        "generator": f"unclaudey {config.VERSION}", "mode": mode, "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "draft": any(e["status"] == "draft" for e in entries), "images": {e["slot"]: e for e in entries},
        "credits_html": credits_html(entries),
    }


def credits_html(entries: list[dict]) -> str:
    uns = [e for e in entries if e["key"].startswith("unsplash:")]
    other = [e for e in entries if not e["key"].startswith("unsplash:")]
    parts = []
    if uns:
        names = []
        for e in uns:
            ph = e["credit"]["photographer_html"]
            if ph not in names:
                names.append(ph)
        uurl = f"https://unsplash.com/?utm_source={config.app_name()}&utm_medium=referral"
        parts.append(f'Photos by {", ".join(names)} on <a href="{uurl}">Unsplash</a>.')
    for e in other:
        parts.append(e["credit"]["html"] + ".")
    return " ".join(parts)


def record_usage(manifest: dict) -> None:
    usage = read_json(config.usage_path(), {}) or {}
    proj = str(Path.cwd())
    day = time.strftime("%Y-%m-%d")
    for e in manifest["images"].values():
        usage.setdefault(e["key"], {"projects": {}})["projects"][proj] = day
    write_json(config.usage_path(), usage)


def snippets(manifest: dict) -> str:
    out = ["<!-- unclaudey: ready-to-paste markup. Keep the credits line visible (footer is fine). -->"]
    for slot, e in manifest["images"].items():
        out.append(f"\n<!-- {slot}: {html.escape(e['credit']['text'])} -->")
        out.append(e["html"])
    out.append("\n<!-- credits -->")
    out.append(f'<p class="photo-credits">{manifest["credits_html"]}</p>')
    return "\n".join(out) + "\n"


def run_cli(a) -> int:
    ws = config.workspace()
    resolved = read_json(ws / "resolved.json")
    if resolved is None:
        from . import resolve as _resolve

        sel = read_json(a.selection or (ws / "selection.json"))
        if sel is None:
            raise SystemExit("No selection.json yet. Choose photos first (see SKILL.md).")
        resolved = _resolve.resolve(sel)
        write_json(ws / "resolved.json", resolved)
    manifest = export(resolved, a.mode, a.out, a.budget_kb, a.allow_draft)
    mpath = Path(a.manifest) if a.manifest else ws / "images.manifest.json"
    write_json(mpath, manifest)
    (ws / "snippets.html").write_text(snippets(manifest))
    record_usage(manifest)
    print(f"manifest: {mpath}")
    print(f"snippets: {ws / 'snippets.html'}")
    for slot, e in manifest["images"].items():
        src = e["src"] if not e["src"].startswith("data:") else f"data URI ({e.get('bytes', 0) // 1024} KB)"
        print(f"  {slot:<14} {e['width']}x{e['height']}  {src[:90]}")
    print(f"\ncredits: {manifest['credits_html']}")
    if manifest["draft"]:
        print("\n! DRAFT export: resolve with an Unsplash key before publishing.")
    if a.mode == "hotlink" and any(k.startswith("unsplash") for k in (e["key"] for e in manifest["images"].values())):
        print("\nNext.js: add images.unsplash.com to images.remotePatterns (see references/integration.md).")
    print("Use only these URLs. Never type image URLs by hand.")
    return 0
