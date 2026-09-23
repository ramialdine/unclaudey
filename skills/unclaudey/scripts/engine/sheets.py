"""Contact sheets and review boards that Claude looks at before choosing photos.

- contact sheet: numbered grid of a slot's candidates at their true aspect ratio
- finalists: each pick shown whole plus cropped to the layout's aspect ratios, with the
  copy-space region and a sample headline drawn in, so crop and legibility can be judged
- set: all chosen photos side by side to judge whether they belong to one visual voice
"""
from __future__ import annotations

import math
import textwrap
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from . import config
from .colorutil import contrast, rgb_to_hex
from .util import add_query, fetch_bytes, http_client, large_path, read_json, thumb_path, write_bytes_atomic

BG = (24, 24, 24)
CELL_BG = (40, 40, 40)
FG = (235, 235, 235)
MUTED = (160, 160, 160)


def font(size: int):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # very old Pillow
        return ImageFont.load_default()


def _open(path: str | Path) -> Image.Image | None:
    try:
        with Image.open(path) as im:
            im.load()
            return im.convert("RGB")
    except Exception:
        return None


def load_thumb(c: dict) -> Image.Image | None:
    p = Path(c.get("thumb") or thumb_path(c["source"], c["id"]))
    im = _open(p) if p.exists() else None
    if im is None and c.get("image_url"):
        client = http_client()
        data = fetch_bytes(client, add_query(c["image_url"], w=400, h=400, fit="max", q=70, fm="jpg") if c["source"] == "unsplash" else c["image_url"])
        client.close()
        if data:
            write_bytes_atomic(p, data)
            im = _open(p)
    return im


def load_large(c: dict, width: int = 1100) -> Image.Image | None:
    """A bigger version for finalist review (cached)."""
    p = large_path(c["source"], c["id"], width)
    if p.exists():
        return _open(p)
    url = None
    if c["source"] == "unsplash" and c.get("image_url"):
        url = add_query(c["image_url"], w=width, q=75, fm="jpg", fit="max")
    elif c.get("thumb_url"):
        url = c["thumb_url"]
    if url:
        client = http_client()
        data = fetch_bytes(client, url)
        client.close()
        if data:
            write_bytes_atomic(p, data)
            return _open(p)
    return load_thumb(c)


def _fit(im: Image.Image, box_w: int, box_h: int) -> Image.Image:
    im = im.copy()
    im.thumbnail((box_w, box_h), Image.LANCZOS)
    return im


def _badge(draw: ImageDraw.ImageDraw, xy, text: str, size: int = 22):
    f = font(size)
    x, y = xy
    tw = draw.textlength(text, font=f)
    draw.rounded_rectangle([x, y, x + tw + 14, y + size + 10], radius=6, fill=(0, 0, 0))
    draw.text((x + 7, y + 4), text, font=f, fill=(255, 255, 255))


def _region_box(w: int, h: int, side: str) -> tuple[int, int, int, int]:
    return {
        "left": (0, 0, int(w * 0.45), h),
        "right": (int(w * 0.55), 0, w, h),
        "top": (0, 0, w, int(h * 0.42)),
        "bottom": (0, int(h * 0.58), w, h),
        "center": (int(w * 0.25), int(h * 0.3), int(w * 0.75), int(h * 0.7)),
    }[side]


def _dashed_rect(draw, box, fill=(255, 255, 255), dash=8, width=2):
    x0, y0, x1, y1 = box
    for x in range(x0, x1, dash * 2):
        draw.line([(x, y0), (min(x + dash, x1), y0)], fill=fill, width=width)
        draw.line([(x, y1 - 1), (min(x + dash, x1), y1 - 1)], fill=fill, width=width)
    for y in range(y0, y1, dash * 2):
        draw.line([(x0, y), (x0, min(y + dash, y1))], fill=fill, width=width)
        draw.line([(x1 - 1, y), (x1 - 1, min(y + dash, y1))], fill=fill, width=width)


def contact_sheet(slot, cands: list[dict], out: Path, coverage: str | None = None) -> Path:
    n = len(cands)
    cols = 4 if n <= 12 else 6
    cell = 300 if cols == 4 else 230
    # cell height follows the slot's orientation so landscape sheets don't waste space
    ratio = {"landscape": 1.5, "wide": 1.75, "portrait": 0.75, "tall": 0.66}.get(slot.orientation, 1.0)
    cell_h = int(cell / ratio) if ratio >= 1 else cell
    cell_w = cell if ratio >= 1 else int(cell * ratio / 0.75 * 0.8)
    gap, label_h, head_h = 12, 30, 78
    rows = max(1, math.ceil(n / cols))
    W = cols * cell_w + (cols + 1) * gap
    H = head_h + rows * (cell_h + label_h + gap) + gap
    sheet = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(sheet)
    title = f"[{slot.id}]  {slot.brief}"
    d.text((gap, 10), textwrap.shorten(title, 120), font=font(22), fill=FG)
    filt = [f"orientation={slot.orientation}"]
    for k in ("tone", "people"):
        if getattr(slot, k) not in (None, "any"):
            filt.append(f"{k}={getattr(slot, k)}")
    if slot.copy_space:
        filt.append(f"copy_space={slot.copy_space} (dashed box)")
    if slot.min_width:
        filt.append(f"min_width={slot.min_width}")
    if slot.color:
        filt.append(f"color~{slot.color}")
    cov = f"   ·   library coverage: {coverage}" if coverage and coverage != "n/a" else ""
    d.text((gap, 42), "   ".join(filt) + f"   ·   {n} candidates{cov}", font=font(16), fill=MUTED)
    if not cands:
        d.text((gap, head_h + 20), "No candidates passed the filters.", font=font(22), fill=FG)
    for i, c in enumerate(cands):
        r, col = divmod(i, cols)
        x = gap + col * (cell_w + gap)
        y = head_h + r * (cell_h + label_h + gap)
        d.rectangle([x, y, x + cell_w, y + cell_h], fill=CELL_BG)
        im = load_thumb(c)
        if im is not None:
            t = _fit(im, cell_w, cell_h)
            ox, oy = x + (cell_w - t.width) // 2, y + (cell_h - t.height) // 2
            sheet.paste(t, (ox, oy))
            if slot.copy_space:
                bx0, by0, bx1, by1 = _region_box(t.width, t.height, slot.copy_space)
                _dashed_rect(d, (ox + bx0, oy + by0, ox + bx1, oy + by1))
        _badge(d, (x + 6, y + 6), f"#{c['n']}")
        origin = "" if c.get("origin") == "index" else f" · {c['source']} live"
        lab = f"{c.get('width')}x{c.get('height')}{origin}"
        if c.get("source") == "openverse" and c.get("license"):
            lab += f" · {c['license']}"
        d.text((x + 2, y + cell_h + 6), textwrap.shorten(lab, int(cell_w / 7)), font=font(15), fill=MUTED)
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, quality=88)
    return out


def crop_box(w: int, h: int, ratio: float, fx: float, fy: float) -> tuple[int, int, int, int]:
    if w / h > ratio:
        cw, ch = h * ratio, h
    else:
        cw, ch = w, w / ratio
    x0 = min(max(fx * w - cw / 2, 0), w - cw)
    y0 = min(max(fy * h - ch / 2, 0), h - ch)
    return int(x0), int(y0), int(x0 + cw), int(y0 + ch)


def parse_ratio(s: str) -> float:
    if ":" in s:
        a, b = s.split(":", 1)
        return float(a) / float(b)
    return float(s)


def _headline_overlay(img: Image.Image, side: str, headline: str) -> tuple[Image.Image, str]:
    """Draw a sample headline in the copy-space region; report the text contrast."""
    im = img.copy()
    w, h = im.size
    box = _region_box(w, h, side)
    region = np.asarray(im.crop(box), dtype=np.float64) / 255.0
    mean = region.reshape(-1, 3).mean(axis=0)
    bg_hex = rgb_to_hex(mean)
    white, ink = contrast("#ffffff", bg_hex), contrast("#111111", bg_hex)
    color, ratio = ("#ffffff", white) if white >= ink else ("#111111", ink)
    d = ImageDraw.Draw(im)
    bw = box[2] - box[0]
    size = max(14, int(min(bw, h) * 0.11))
    f = font(size)
    lines = textwrap.wrap(headline, width=max(8, int(bw / (size * 0.55))))[:3]
    tx = box[0] + int(bw * 0.08)
    ty = box[1] + int((box[3] - box[1]) * 0.3)
    for ln in lines:
        d.text((tx, ty), ln, font=f, fill=color)
        ty += int(size * 1.15)
    _dashed_rect(d, box)
    busy = float(region.std(axis=(0, 1)).mean())
    note = f"text {color} ~ {ratio:.1f}:1 on region avg {bg_hex}; busyness {busy:.2f}"
    return im, note


def finalists(slot_id: str, picks: list[int], crops: list[str], copy_space: str | None, headline: str | None,
              out: Path) -> Path:
    ws = config.workspace()
    data = read_json(ws / "candidates.json", {}) or {}
    s = (data.get("slots") or {}).get(slot_id)
    if not s:
        raise SystemExit(f"No candidates for slot '{slot_id}'. Run search first.")
    by_n = {c["n"]: c for c in s["candidates"]}
    copy_space = copy_space or s["slot"].get("copy_space")
    headline = headline or "A headline that sits here"
    ratios = [parse_ratio(r) for r in crops]
    row_h, gap, label_h = 300, 14, 26
    rows = []
    for n in picks:
        c = by_n.get(n)
        if not c:
            raise SystemExit(f"slot {slot_id} has no candidate #{n}")
        im = load_large(c)
        if im is None:
            continue
        fx, fy = (c.get("focal") or [0.5, 0.5])
        tiles = [("full", _fit(im, 10_000, row_h), "")]
        for label, ratio in zip(crops, ratios):
            box = crop_box(im.width, im.height, ratio, fx, fy)
            cr = im.crop(box)
            note = ""
            if copy_space:
                cr, note = _headline_overlay(cr, copy_space, headline)
            tiles.append((label, cr.resize((int(row_h * ratio), row_h), Image.LANCZOS), note))
        rows.append((c, tiles))
    if not rows:
        raise SystemExit("Could not load any finalist images.")
    W = max(sum(t.width for _, t, _ in tiles) + gap * (len(tiles) + 1) for _, tiles in rows)
    H = gap + len(rows) * (row_h + label_h * 2 + gap) + 40
    sheet = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(sheet)
    d.text((gap, 10), f"[{slot_id}] finalists · crops {', '.join(crops)} · focal point from image detail", font=font(18), fill=FG)
    y = 40
    for c, tiles in rows:
        x = gap
        for label, t, note in tiles:
            sheet.paste(t, (x, y))
            _badge(d, (x + 6, y + 6), f"#{c['n']} {label}", size=18)
            if note:
                d.text((x, y + row_h + 4), textwrap.shorten(note, int(t.width / 7.5)), font=font(13), fill=MUTED)
            x += t.width + gap
        d.text((gap, y + row_h + label_h), textwrap.shorten(f"#{c['n']}: {c.get('description', '')}", 150), font=font(14), fill=MUTED)
        y += row_h + label_h * 2 + gap
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, quality=88)
    return out


def set_view(selection: dict, out: Path) -> Path:
    from .selection import resolve_picks

    picks = resolve_picks(selection)
    if not picks:
        raise SystemExit("selection.json has no picks")
    row_h, gap, max_w = 260, 12, 1500
    tiles = []
    for p in picks:
        im = load_thumb(p["candidate"])
        if im is not None:
            t = im.copy()
            t.thumbnail((10_000, row_h), Image.LANCZOS)
            tiles.append((p, t))
    rows, cur, cur_w = [], [], gap
    for p, t in tiles:
        if cur and cur_w + t.width + gap > max_w:
            rows.append(cur)
            cur, cur_w = [], gap
        cur.append((p, t))
        cur_w += t.width + gap
    if cur:
        rows.append(cur)
    W = max(sum(t.width for _, t in r) + gap * (len(r) + 1) for r in rows)
    H = 44 + len(rows) * (row_h + 30 + gap)
    sheet = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(sheet)
    d.text((gap, 10), "Selected set — do these read as one photographic voice (light, grade, contrast, subject distance)?", font=font(18), fill=FG)
    y = 44
    for r in rows:
        x = gap
        for p, t in r:
            sheet.paste(t, (x, y))
            _badge(d, (x + 6, y + 6), p["slot"], size=16)
            d.text((x, y + row_h + 6), textwrap.shorten(p["candidate"].get("description", ""), int(t.width / 7)), font=font(13), fill=MUTED)
            x += t.width + gap
        y += row_h + 30 + gap
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, quality=88)
    return out


def run_cli(a) -> int:
    ws = config.workspace()
    if a.view == "finalists":
        if not a.slot or not a.picks:
            raise SystemExit("finalists needs --slot and --picks (numbers from the contact sheet)")
        picks = [int(x) for x in a.picks.replace(" ", "").split(",") if x]
        out = ws / "sheets" / f"{a.slot}-finalists.jpg"
        finalists(a.slot, picks, [c.strip() for c in a.crops.split(",") if c.strip()], a.copy_space, a.headline, out)
        print(out)
    elif a.view == "set":
        sel = read_json(a.selection or (ws / "selection.json"))
        if sel is None:
            raise SystemExit("No selection.json yet (see SKILL.md)")
        out = set_view(sel, ws / "sheets" / "set.jpg")
        print(out)
    elif a.view == "slot":
        from .search import Slot

        data = read_json(ws / "candidates.json", {}) or {}
        s = (data.get("slots") or {}).get(a.slot or "")
        if not s:
            raise SystemExit("unknown slot")
        out = contact_sheet(Slot.from_dict(s["slot"]), s["candidates"], ws / "sheets" / f"{a.slot}.jpg")
        print(out)
    return 0
