# /// script
# requires-python = ">=3.10"
# dependencies = ["playwright>=1.45"]
# ///
"""Screenshot built pages at desktop and mobile sizes (first screen + full page).

Uses the installed Google Chrome through Playwright (no browser download). Reduced motion is
emulated and the page is scrolled once so scroll-triggered reveals are captured in their
final state.

    uv run benchmarks/screenshot.py <page.html> <out_dir> <name>
"""
from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

SIZES = (("desktop", 1440, 900, 1), ("mobile", 390, 844, 2))

SCROLL_THROUGH = """
async () => {
  const step = Math.max(200, Math.floor(window.innerHeight * 0.8));
  for (let y = 0; y < document.body.scrollHeight; y += step) {
    window.scrollTo(0, y);
    await new Promise(r => setTimeout(r, 120));
  }
  window.scrollTo(0, 0);
  await new Promise(r => setTimeout(r, 300));
}
"""


def shoot(page_path: str, out_dir: str, name: str) -> list[Path]:
    url = Path(page_path).resolve().as_uri()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        for label, w, h, scale in SIZES:
            ctx = browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=scale,
                                      reduced_motion="reduce")
            page = ctx.new_page()
            page.goto(url, wait_until="networkidle", timeout=90_000)
            page.evaluate(SCROLL_THROUGH)
            page.wait_for_timeout(800)
            for kind, full in (("fold", False), ("full", True)):
                path = out / f"{name}-{label}-{kind}.jpg"
                page.screenshot(path=str(path), full_page=full, type="jpeg", quality=82)
                written.append(path)
            ctx.close()
        browser.close()
    return written


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    for f in shoot(*sys.argv[1:]):
        print(f)
