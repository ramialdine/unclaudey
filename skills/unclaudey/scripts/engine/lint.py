"""Check built pages for the image mistakes that make generated sites look generated or broken.

Errors (exit 1): Unsplash URLs that are not in the manifest (almost always invented IDs that
404), the dead source.unsplash.com service, <img> without alt, unpublished draft photos.
Warnings: placeholder services, images without width/height (layout shift), a lazy-loaded
hero, missing photographer credits, and (with --network) any image URL that does not load.
"""
from __future__ import annotations

import html
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

from . import config
from .util import http_client, read_json

URL_RE = re.compile(r"""https?://[^\s"'()<>\\,]+""")
IMG_EXT = re.compile(r"\.(jpe?g|png|webp|avif|gif)(\?|$)", re.I)
PLACEHOLDERS = ("picsum.photos", "placehold.co", "placehold.it", "via.placeholder.com", "dummyimage.com",
                "loremflickr.com", "placekitten.com", "placeimg.com", "fakeimg.pl")
IMAGE_HOSTS = ("images.unsplash.com", "plus.unsplash.com", "source.unsplash.com", "images.pexels.com",
               "cdn.pixabay.com", "live.staticflickr.com", "upload.wikimedia.org", "api.openverse.org") + PLACEHOLDERS
HTML_LIKE = {".html", ".htm", ".vue", ".svelte", ".astro"}
UNSPLASH_PHOTO = re.compile(r"/(photo-[0-9a-z-]+|premium_photo-[0-9a-z-]+)", re.I)


class ImgParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.imgs: list[tuple[int, dict]] = []

    def handle_starttag(self, tag, attrs):
        if tag == "img":
            self.imgs.append((self.getpos()[0], dict(attrs)))


def is_image_url(u: str) -> bool:
    host = urlsplit(u).netloc.lower()
    return any(h in host for h in IMAGE_HOSTS) or bool(IMG_EXT.search(urlsplit(u).path))


def lint(files: list[Path], manifest: dict | None, network: bool, allow_draft: bool) -> tuple[list[str], list[str]]:
    errors, warns = [], []
    allowed_photo_paths, allowed_urls = set(), set()
    if manifest:
        for e in manifest.get("images", {}).values():
            for u in [e.get("src", "")] + [s.strip().split(" ")[0] for s in (e.get("srcset") or "").split(",") if s.strip()]:
                allowed_urls.add(u)
                m = UNSPLASH_PHOTO.search(urlsplit(u).path)
                if m:
                    allowed_photo_paths.add(m.group(1))
        if manifest.get("draft") and not allow_draft:
            errors.append("manifest: DRAFT images (no Unsplash key). Resolve + export with a key before publishing.")
    texts: dict[Path, str] = {}
    for f in files:
        try:
            texts[f] = f.read_text(encoding="utf-8", errors="replace")
        except OSError as ex:
            errors.append(f"{f}: cannot read ({ex})")
    urls_to_check = set()
    for f, text in texts.items():
        for m in URL_RE.finditer(text):
            u = m.group(0).rstrip(".;")
            if not is_image_url(u):
                continue
            host = urlsplit(u).netloc.lower()
            line = text.count("\n", 0, m.start()) + 1
            if "source.unsplash.com" in host:
                errors.append(f"{f}:{line}: source.unsplash.com was shut down, this image will not load: {u[:80]}")
            elif any(p in host for p in PLACEHOLDERS):
                warns.append(f"{f}:{line}: placeholder image service ({host}); use real photography from the manifest")
            elif host in ("images.unsplash.com", "plus.unsplash.com"):
                pm = UNSPLASH_PHOTO.search(urlsplit(u).path)
                if not manifest:
                    warns.append(f"{f}:{line}: Unsplash URL but no manifest to verify it against: {u[:80]}")
                elif not pm or pm.group(1) not in allowed_photo_paths:
                    errors.append(f"{f}:{line}: Unsplash URL not from the manifest (likely an invented photo id): {u[:90]}")
                urls_to_check.add(u)
            elif u not in allowed_urls:
                warns.append(f"{f}:{line}: external image not from the manifest (check it loads and its license): {u[:80]}")
                urls_to_check.add(u)
        # <img> hygiene
        imgs: list[tuple[int, dict]] = []
        if f.suffix.lower() in HTML_LIKE:
            p = ImgParser()
            try:
                p.feed(text)
                imgs = p.imgs
            except Exception:
                pass
        else:
            for m in re.finditer(r"<img\b[^>]*?/?>", text, re.S):
                attrs = dict((k.lower(), v) for k, v in re.findall(r"([\w:-]+)\s*=\s*[\"'{]", m.group(0)))
                imgs.append((text.count("\n", 0, m.start()) + 1, {k: "" for k in attrs}))
        for n, (line, attrs) in enumerate(imgs):
            keys = {k.lower() for k in attrs}
            if "alt" not in keys:
                errors.append(f"{f}:{line}: <img> without alt (use alt=\"\" only for decorative images)")
            if not ({"width", "height"} <= keys) and "fill" not in keys:
                warns.append(f"{f}:{line}: <img> without width/height causes layout shift")
            if n == 0 and (attrs.get("loading") or "").lower() == "lazy":
                warns.append(f"{f}:{line}: first image is lazy-loaded; the hero should load eagerly (fetchpriority=\"high\")")
    # credits
    if manifest and manifest.get("images"):
        alltext = "\n".join(texts.values())
        for e in manifest["images"].values():
            if not _used(e, alltext):
                continue
            name = e.get("photographer")
            if name and name not in alltext and html.escape(name) not in alltext:
                warns.append(f"credits: photographer '{name}' ({e['slot']}) is not credited in the checked files")
        if any(k.startswith("unsplash:") for k in (e["key"] for e in manifest["images"].values())) and "unsplash.com" not in alltext.replace("images.unsplash.com", ""):
            warns.append("credits: no link to Unsplash found (\"Photos by … on Unsplash\" with utm links)")
    if network and urls_to_check:
        client = http_client(timeout=15)
        for u in sorted(urls_to_check):
            try:
                r = client.get(u, headers={"Range": "bytes=0-1023"})
                if r.status_code >= 400:
                    errors.append(f"image does not load ({r.status_code}): {u[:100]}")
            except Exception as ex:
                errors.append(f"image request failed: {u[:100]} ({type(ex).__name__})")
        client.close()
    return errors, warns


def _used(e: dict, alltext: str) -> bool:
    src = e.get("src") or ""
    if src and src in alltext:
        return True
    m = UNSPLASH_PHOTO.search(urlsplit(src).path)
    return bool(m and m.group(1) in alltext)


def run_cli(a) -> int:
    ws = config.workspace(create=False)
    mpath = Path(a.manifest) if a.manifest else ws / "images.manifest.json"
    manifest = read_json(mpath)
    files: list[Path] = []
    for f in a.files:
        p = Path(f)
        if p.is_dir():
            for ext in ("*.html", "*.htm", "*.jsx", "*.tsx", "*.js", "*.ts", "*.vue", "*.svelte", "*.astro", "*.css", "*.mdx"):
                files += [x for x in p.rglob(ext) if "node_modules" not in x.parts and ".unclaudey" not in x.parts]
        else:
            files.append(p)
    errors, warns = lint(files, manifest, a.network, a.allow_draft)
    for e in errors:
        print(f"ERROR  {e}")
    for w in warns:
        print(f"warn   {w}")
    print(f"\n{len(files)} file(s), {len(errors)} error(s), {len(warns)} warning(s)"
          + ("" if manifest else f"  (no manifest at {mpath})"))
    return 1 if errors else 0
