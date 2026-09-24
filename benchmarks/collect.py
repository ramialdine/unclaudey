# /// script
# requires-python = ">=3.10"
# dependencies = ["playwright>=1.45", "pillow>=10.3"]
# ///
"""Screenshot every A/B run and collect simple, checkable facts about each page.

    uv run benchmarks/collect.py <runs_dir> <out_dir>

<runs_dir>/<brief>/<arm>/index.html  ->  <out_dir>/img/<brief>-<arm>-{desktop,mobile}-{fold,full}.jpg
                                        <out_dir>/facts.json
"""
from __future__ import annotations

import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from screenshot import shoot  # noqa: E402

IMG_URL = re.compile(r"""https?://[^\s"'()<>\\,]+""")


class Imgs(HTMLParser):
    def __init__(self):
        super().__init__()
        self.imgs = []

    def handle_starttag(self, tag, attrs):
        if tag == "img":
            self.imgs.append(dict(attrs))


def facts(page: Path) -> dict:
    html = page.read_text(encoding="utf-8", errors="replace")
    p = Imgs()
    p.feed(html)
    hosts = {}
    for m in IMG_URL.finditer(html):
        u = m.group(0)
        host = urlsplit(u).netloc.lower()
        if any(h in host for h in ("unsplash", "pexels", "pixabay", "picsum", "placehold", "openverse", "staticflickr", "wikimedia")):
            hosts[host] = hosts.get(host, 0) + 1
    fonts = sorted(set(re.findall(r"family=([A-Za-z0-9+]+)", html)))
    return {
        "bytes": len(html.encode()),
        "img_tags": len(p.imgs),
        "img_with_alt": sum(1 for i in p.imgs if "alt" in i),
        "data_uri_imgs": sum(1 for i in p.imgs if (i.get("src") or "").startswith("data:")),
        "svg_elements": html.count("<svg"),
        "image_hosts": hosts,
        "google_fonts": [f.replace("+", " ") for f in fonts],
        "has_credits": bool(re.search(r"on\s*<a[^>]*unsplash\.com|\bCC[ -](BY|0)\b|Public Domain|Photos? by", html, re.I)),
    }


def main(runs: str, out: str) -> None:
    runs_p, out_p = Path(runs), Path(out)
    (out_p / "img").mkdir(parents=True, exist_ok=True)
    result = {}
    for page in sorted(runs_p.glob("*/*/index.html")):
        brief, arm = page.parent.parent.name, page.parent.name
        name = f"{brief}-{arm}"
        print(f"shooting {name}")
        shots = shoot(str(page), str(out_p / "img"), name)
        for s in shots:  # keep the repo light: cap widths
            im = Image.open(s)
            cap = 1200 if "desktop" in s.name else 390
            if im.width > cap:
                im = im.resize((cap, int(im.height * cap / im.width)), Image.LANCZOS)
            if im.height > 9000:
                im = im.crop((0, 0, im.width, 9000))
            im.convert("RGB").save(s, quality=80, optimize=True)
        result.setdefault(brief, {})[arm] = {"facts": facts(page), "shots": [s.name for s in shots]}
    (out_p / "facts.json").write_text(json.dumps(result, indent=2))
    print(out_p / "facts.json")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2])
