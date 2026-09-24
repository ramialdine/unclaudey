"""`sheet drawings`: look at every code-drawn visual (SVG / canvas) before shipping.

Renders each top-level <svg> and <canvas> on the page as a numbered cell (desktop light,
plus dark and mobile sheets), and flags drawings that are empty, clipped by their viewBox,
off-palette, overflowing on phones, or carrying text too small to read.
"""
from __future__ import annotations

import io
import math
import re
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from . import config
from .browser import browser, new_page, page_url
from .colorutil import delta_e, rgb_to_hex
from .sheets import BG, FG, _badge, font
from .util import read_json, write_json

MIN_SIDE = 40  # smaller drawings are treated as icons: counted, not reviewed
MAX_CELLS = 24

COLLECT = """
() => {
  const els = Array.from(document.querySelectorAll('svg, canvas')).filter(e =>
    !(e.tagName.toLowerCase() === 'svg' && e.parentElement && e.parentElement.closest('svg')));
  return els.map((e, i) => {
    e.dataset.ucDraw = i;
    const r = e.getBoundingClientRect();
    const info = {i, tag: e.tagName.toLowerCase(), w: Math.round(r.width), h: Math.round(r.height),
                  label: e.getAttribute('aria-label') || (e.querySelector && e.querySelector('title') ? e.querySelector('title').textContent : '') || '',
                  hiddenForA11y: e.getAttribute('aria-hidden') === 'true'};
    // is it inside a container that scrolls or clips sideways (an intentional horizontal scroller)?
    for (let n = e.parentElement; n && n !== document.body; n = n.parentElement) {
      const ox = getComputedStyle(n).overflowX; if (['auto', 'scroll', 'hidden', 'clip'].includes(ox)) { info.contained = true; break; } }
    if (info.tag === 'svg') {
      const vb = e.viewBox && e.viewBox.baseVal;
      info.vb = vb && vb.width ? [vb.x, vb.y, vb.width, vb.height] : null;
      try { const b = e.getBBox(); info.bbox = [b.x, b.y, b.width, b.height]; } catch (err) { info.bbox = null; }
      const cols = new Set(); let tiny = 0;
      const scale = info.vb ? r.width / info.vb[2] : 1;
      e.querySelectorAll('path,rect,circle,ellipse,polygon,polyline,line,text,tspan').forEach(n => {
        const cs = getComputedStyle(n);
        if (cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity) === 0) return;
        for (const c of [cs.fill, cs.stroke]) if (c && c !== 'none' && !c.startsWith('url') && !/,\\s*0\\)$/.test(c)) cols.add(c);
        if (n.tagName === 'text' && parseFloat(cs.fontSize) * scale < 10) tiny++;
      });
      info.colors = Array.from(cols).slice(0, 60); info.tinyText = tiny;
    }
    return info;
  });
}
"""


def _hex(css_color: str) -> str | None:
    m = re.match(r"rgba?\(([\d.]+),\s*([\d.]+),\s*([\d.]+)", css_color)
    if not m:
        return None
    return rgb_to_hex([float(v) / 255 for v in m.groups()])


def _palette() -> list[str]:
    ws = config.workspace(create=False)
    pal = read_json(ws / "palette.json") or {}
    cols = list((pal.get("tokens") or {}).values()) + [c["hex"] for c in pal.get("image_colors", [])]
    return [c for c in cols if isinstance(c, str) and c.startswith("#")]


def _shoot(b, url: str, width: int, height: int, scheme: str) -> tuple[list[dict], dict[int, bytes], int]:
    ctx, pg = new_page(b, width=width, height=height, color_scheme=scheme, reduced_motion=True)
    pg.goto(url, wait_until="networkidle", timeout=90_000)
    pg.wait_for_timeout(700)
    info = pg.evaluate(COLLECT)
    vw = pg.evaluate("() => document.documentElement.clientWidth")
    shots: dict[int, bytes] = {}
    big = [d for d in info if d["w"] >= MIN_SIDE and d["h"] >= MIN_SIDE]
    big.sort(key=lambda d: -(d["w"] * d["h"]))
    for d in big[:MAX_CELLS]:
        try:
            loc = pg.locator(f'[data-uc-draw="{d["i"]}"]')
            loc.scroll_into_view_if_needed(timeout=3000)
            pg.wait_for_timeout(150)
            shots[d["i"]] = loc.screenshot(type="png", timeout=5000)
        except Exception:
            pass
    ctx.close()
    return info, shots, vw


def _sheet(cells: list[tuple[str, bytes]], title: str, out: Path) -> None:
    if not cells:
        return
    cols, cell, gap, head = 4, 330, 12, 46
    rows = math.ceil(len(cells) / cols)
    sheet = Image.new("RGB", (cols * cell + (cols + 1) * gap, head + rows * (cell + gap) + gap), BG)
    d = ImageDraw.Draw(sheet)
    d.text((gap, 12), title, font=font(18), fill=FG)
    for k, (lab, png) in enumerate(cells):
        r, c = divmod(k, cols)
        x, y = gap + c * (cell + gap), head + r * (cell + gap)
        d.rectangle([x, y, x + cell, y + cell], fill=(236, 234, 230))
        im = Image.open(io.BytesIO(png)).convert("RGB")
        scale = min((cell - 8) / im.width, (cell - 8) / im.height, 3.0)  # enlarge small drawings, up to 3x
        im = im.resize((max(1, int(im.width * scale)), max(1, int(im.height * scale))), Image.LANCZOS)
        sheet.paste(im, (x + (cell - im.width) // 2, y + (cell - im.height) // 2))
        _badge(d, (x + 6, y + 6), lab, size=15)
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, quality=86)


def run(target: str, out_dir: Path) -> dict:
    url = page_url(target)
    palette = _palette()
    with browser() as b:
        info, light, _ = _shoot(b, url, 1440, 900, "light")
        _, dark, _ = _shoot(b, url, 1440, 900, "dark")
        m_info, mobile, m_vw = _shoot(b, url, 390, 844, "light")
    reviewed = [d for d in info if d["i"] in light]
    icons = sum(1 for d in info if d["w"] < MIN_SIDE or d["h"] < MIN_SIDE)
    findings: list[tuple[str, str]] = []
    by_i_mobile = {d["i"]: d for d in m_info}
    for d in reviewed:
        tag = f"#{d['i']} {d['tag']} {d['w']}×{d['h']}"
        g = np.asarray(Image.open(io.BytesIO(light[d["i"]])).convert("L"), dtype=np.float32)
        if g.std() < 2.0:
            findings.append(("fail", f"{tag}: renders empty or invisible"))
        if d.get("vb") and d.get("bbox"):
            vx, vy, vw_, vh = d["vb"]
            bx, by, bw, bh = d["bbox"]
            over = max(vx - bx, vy - by, (bx + bw) - (vx + vw_), (by + bh) - (vy + vh))
            if over > 0.03 * max(vw_, vh):
                findings.append(("warn", f"{tag}: content extends past its viewBox (clipped by {over:.0f} units)"))
        if palette and d.get("colors"):
            hexes = [h for h in (_hex(c) for c in d["colors"]) if h]
            off = [h for h in hexes if min(delta_e(h, p) for p in palette) > 0.12]
            if hexes and len(off) / len(hexes) > 0.25:
                findings.append(("warn", f"{tag}: {len(off)} of {len(hexes)} colors aren't in the palette (e.g. {', '.join(off[:3])})"))
        md = by_i_mobile.get(d["i"])
        if md:
            if md["w"] > m_vw + 2 and not md.get("contained"):
                findings.append(("warn", f"{tag}: {md['w']}px wide on a {m_vw}px phone, so it overflows"))
            if md.get("tinyText"):
                findings.append(("warn", f"{tag}: {md['tinyText']} text label(s) under 10px on a phone"))
        if not d["label"] and not d["hiddenForA11y"] and d["w"] * d["h"] > 90_000:
            findings.append(("warn", f"{tag}: large drawing with no aria-label/<title> and not aria-hidden"))
    # theme response: does the page redraw its visuals for dark mode?
    dark_changes = sum(1 for i in light if i in dark and _differs(light[i], dark[i]))
    cells = [(f"#{d['i']} {d['tag']}", light[d["i"]]) for d in reviewed]
    _sheet(cells, f"drawings · desktop · {len(reviewed)} shown, {icons} icon(s) skipped", out_dir / "drawings.jpg")
    if dark_changes:
        _sheet([(f"#{i} dark", dark[i]) for i in light if i in dark], "drawings · dark theme", out_dir / "drawings-dark.jpg")
    _sheet([(f"#{i} phone", mobile[i]) for i in mobile], "drawings · phone (390px)", out_dir / "drawings-mobile.jpg")
    if not reviewed:
        findings.append(("ok", "no code-drawn visuals on this page"))
    elif not any(s != "ok" for s, _ in findings):
        findings.append(("ok", f"{len(reviewed)} drawing(s) render cleanly" + (" and stay on-palette" if palette else "")))
    report = {"page": target, "drawings": info, "reviewed": [d["i"] for d in reviewed], "icons": icons,
              "dark_theme_redraws": dark_changes, "palette_checked": bool(palette), "findings": findings}
    write_json(out_dir / "drawings.json", report)
    return report


def _differs(a: bytes, b: bytes) -> bool:
    x = np.asarray(Image.open(io.BytesIO(a)).convert("L"), dtype=np.float32)
    y = np.asarray(Image.open(io.BytesIO(b)).convert("L"), dtype=np.float32)
    if x.shape != y.shape:
        return True
    return float(np.abs(x - y).mean()) > 2.0


def run_cli(page: str) -> int:
    ws = config.workspace()
    out = ws / "drawings" / (Path(page).stem if not page.startswith("http") else "url")
    rep = run(page, out)
    icon = {"ok": "✓", "warn": "!", "fail": "✗"}
    print(f"drawings check: {page}  ({len(rep['reviewed'])} reviewed, {rep['icons']} icons skipped"
          + ("" if rep["palette_checked"] else "; no palette.json, so colors weren't checked") + ")")
    for state, msg in rep["findings"]:
        print(f" {icon[state]} {msg}")
    print(f"\nsheets: {out / 'drawings.jpg'}  {out / 'drawings-mobile.jpg'}"
          + (f"  {out / 'drawings-dark.jpg'}" if rep["dark_theme_redraws"] else ""))
    print("View the sheets: are the drawings specific to this subject, consistent in style, and legible?")
    return 1 if any(s == "fail" for s, _ in rep["findings"]) else 0
