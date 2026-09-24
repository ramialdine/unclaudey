"""Shared headless-browser helper (Playwright driving the installed Google Chrome).

Using the system Chrome avoids a ~150 MB browser download. If Chrome isn't installed,
Playwright's own Chromium is used, which needs a one-time `playwright install chromium`.
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

SCROLL_THROUGH = """
async () => {
  const step = Math.max(200, Math.floor(window.innerHeight * 0.8));
  for (let y = 0; y < document.documentElement.scrollHeight; y += step) {
    window.scrollTo(0, y);
    await new Promise(r => setTimeout(r, 120));
  }
  window.scrollTo(0, 0);
  await new Promise(r => setTimeout(r, 300));
}
"""


def page_url(target: str) -> str:
    if target.startswith(("http://", "https://", "file://")):
        return target
    p = Path(target).resolve()
    if not p.exists():
        raise SystemExit(f"No such page: {target}")
    return p.as_uri()


@contextmanager
def browser():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:  # pragma: no cover
        raise SystemExit("playwright is missing; run the CLI through `uv run` so dependencies install") from e
    with sync_playwright() as p:
        try:
            b = p.chromium.launch(channel="chrome")
        except Exception:
            try:
                b = p.chromium.launch()
            except Exception as e:
                raise SystemExit("No Chrome found. Install Google Chrome, or run once: "
                                 "uv run --with playwright playwright install chromium") from e
        try:
            yield b
        finally:
            b.close()


def new_page(b, width: int = 1440, height: int = 900, scale: float = 1, reduced_motion: bool = False,
             javascript: bool = True, color_scheme: str = "light", video_dir: str | None = None):
    ctx = b.new_context(
        viewport={"width": width, "height": height}, device_scale_factor=scale,
        reduced_motion="reduce" if reduced_motion else "no-preference",
        java_script_enabled=javascript, color_scheme=color_scheme,
        record_video_dir=video_dir, record_video_size={"width": width, "height": height} if video_dir else None,
    )
    return ctx, ctx.new_page()
