"""Derive UI color tokens from the chosen photos, so the palette belongs to this site.

k-means in OKLab over the selected photos (the hero counts double), then roles:
bg / surface / line / ink / muted from the dominant tone and hue, accent and accent-2 from the
most characterful chromatic clusters, with lightness pushed until WCAG contrast passes.
"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw

from . import config
from .colorutil import clamp_chroma, cliche_warnings, contrast, lab_hex, oklch, rgb_to_oklab
from .selection import resolve_picks
from .sheets import font, load_thumb
from .util import read_json, write_json


def _kmeans(X: np.ndarray, w: np.ndarray, k: int = 8, iters: int = 14, seed: int = 7) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    centers = [X[rng.choice(len(X), p=w / w.sum())]]
    for _ in range(1, k):
        d = np.min([((X - c) ** 2).sum(1) for c in centers], axis=0) * w
        centers.append(X[rng.choice(len(X), p=d / d.sum())] if d.sum() > 0 else X[rng.integers(len(X))])
    C = np.array(centers)
    for _ in range(iters):
        lab = np.argmin(((X[:, None, :] - C[None]) ** 2).sum(-1), axis=1)
        for j in range(k):
            m = lab == j
            if m.any():
                C[j] = np.average(X[m], axis=0, weights=w[m])
    lab = np.argmin(((X[:, None, :] - C[None]) ** 2).sum(-1), axis=1)
    share = np.array([w[lab == j].sum() for j in range(k)]) / w.sum()
    return C, share


def _with_contrast(L: float, C: float, h: float, against: str, target: float, direction: int) -> tuple[str, float]:
    """Move lightness (direction -1 darker, +1 lighter) until contrast with `against` >= target."""
    for _ in range(60):
        hx = lab_hex(clamp_chroma(L, C, h))
        if contrast(hx, against) >= target or not 0.02 < L < 0.99:
            return hx, contrast(hx, against)
        L += 0.01 * direction
    hx = lab_hex(clamp_chroma(L, C, h))
    return hx, contrast(hx, against)


def derive(picks: list[dict], theme: str = "auto") -> dict:
    pix, wts, means = [], [], []
    for n, p in enumerate(picks):
        im = load_thumb(p["candidate"])
        if im is None:
            continue
        im = im.copy()
        im.thumbnail((72, 72), Image.BILINEAR)
        lab = rgb_to_oklab(np.asarray(im, dtype=np.float64).reshape(-1, 3) / 255.0)
        weight = 2.0 if (n == 0 or p["slot"] in ("hero", "cover", "header")) else 1.0
        pix.append(lab)
        wts.append(np.full(len(lab), weight / len(lab)))
        means.append((float(lab[:, 0].mean()), weight))
    if not pix:
        raise SystemExit("Could not load any selected photo thumbnails.")
    X, w = np.vstack(pix), np.concatenate(wts)
    C, share = _kmeans(X, w)
    clusters = sorted(
        ({"lab": C[j], "share": float(share[j]), **dict(zip(("L", "C", "h"), oklch(C[j])))} for j in range(len(C)) if share[j] > 0.005),
        key=lambda c: -c["share"])
    mean_L = sum(m * wt for m, wt in means) / sum(wt for _, wt in means)
    if theme == "auto":
        theme = "dark" if mean_L < 0.42 else "light"

    # background hue: the dominant cluster in the relevant tonal half, desaturated
    tonal = [c for c in clusters if (c["L"] >= 0.5 if theme == "light" else c["L"] < 0.5)] or clusters
    base = max(tonal, key=lambda c: c["share"])
    h_bg = base["h"]
    tint = min(0.018, base["C"] * 0.3)
    if theme == "light":
        bg = lab_hex(clamp_chroma(0.968, tint, h_bg))
        surface = lab_hex(clamp_chroma(0.935, tint * 1.3, h_bg))
        line = lab_hex(clamp_chroma(0.86, tint * 1.2, h_bg))
        ink, ink_c = _with_contrast(0.30, min(0.03, tint * 1.5), h_bg, bg, 9.0, -1)
        muted, muted_c = _with_contrast(0.55, min(0.03, tint * 1.5), h_bg, bg, 4.6, -1)
    else:
        bg = lab_hex(clamp_chroma(0.165, min(0.025, tint * 1.4), h_bg))
        surface = lab_hex(clamp_chroma(0.215, min(0.03, tint * 1.6), h_bg))
        line = lab_hex(clamp_chroma(0.30, min(0.03, tint * 1.5), h_bg))
        ink, ink_c = _with_contrast(0.88, min(0.02, tint), h_bg, bg, 10.0, +1)
        muted, muted_c = _with_contrast(0.66, min(0.025, tint), h_bg, bg, 4.6, +1)

    chroma = sorted((c for c in clusters if c["C"] >= 0.035), key=lambda c: -(c["C"] * c["share"] ** 0.35))
    derived_accent = bool(chroma)
    if chroma:
        a1 = chroma[0]
        a_h, a_C = a1["h"], max(a1["C"], 0.09)
    else:  # near-neutral photos: pick a hue opposite the background tint, flagged as a choice
        a_h, a_C = (h_bg + 180) % 360, 0.12
    direction = -1 if theme == "light" else +1
    start_L = 0.62 if theme == "light" else 0.72
    accent, _ = _with_contrast(start_L, a_C, a_h, bg, 3.2, direction)
    accent_ink = "#ffffff" if contrast("#ffffff", accent) >= contrast("#111111", accent) else "#111111"
    if contrast(accent_ink, accent) < 4.5:
        accent, _ = _with_contrast(start_L, a_C, a_h, accent_ink, 4.6, -1 if accent_ink == "#ffffff" else +1)
    a2 = next((c for c in chroma[1:] if min(abs(c["h"] - a_h), 360 - abs(c["h"] - a_h)) >= 35), None)
    if a2:
        accent2, _ = _with_contrast(start_L, max(a2["C"], 0.07), a2["h"], bg, 3.0, direction)
    else:
        accent2 = lab_hex(clamp_chroma(0.9 if theme == "light" else 0.3, a_C * 0.35, a_h))  # tinted wash of the accent

    # a light (or deep) tint of the accent hue for section bands, so pages aren't all off-white
    wash = lab_hex(clamp_chroma(0.93 if theme == "light" else 0.24, min(0.045, a_C * 0.4), a_h))
    tokens = {"bg": bg, "surface": surface, "wash": wash, "line": line, "ink": ink, "muted": muted,
              "accent": accent, "accent-ink": accent_ink, "accent-2": accent2}
    checks = {
        "ink/bg": round(ink_c, 2), "muted/bg": round(muted_c, 2), "ink/wash": round(contrast(ink, wash), 2),
        "accent/bg": round(contrast(accent, bg), 2),
        "accent-ink/accent": round(contrast(accent_ink, accent), 2),
    }
    notes = []
    if not derived_accent:
        notes.append("The selected photos are near-neutral; the accent hue is a design choice, not taken from the images.")
    for name in cliche_warnings(bg, accent):
        notes.append(f"This lands on a known generated-looking palette ({name}). Shift hue/lightness or pick a different accent source.")
    return {
        "theme": theme, "tokens": tokens, "contrast": checks, "notes": notes,
        "image_colors": [{"hex": lab_hex(c["lab"]), "share": round(c["share"], 3)} for c in clusters[:8]],
        "sources": [f"{p['slot']}:{p['candidate']['key']}" for p in picks],
    }


def css(result: dict) -> str:
    lines = [f"/* unclaudey palette · theme {result['theme']} · from {', '.join(result['sources'])} */", ":root {"]
    for k, v in result["tokens"].items():
        lines.append(f"  --color-{k}: {v};")
    lines.append("}")
    lines.append("/* contrast: " + ", ".join(f"{k} {v}:1" for k, v in result["contrast"].items()) + " */")
    return "\n".join(lines) + "\n"


def swatch_image(result: dict, out) -> None:
    toks = list(result["tokens"].items())
    sw, gap = 150, 12
    W = gap + len(toks) * (sw + gap)
    H = 300
    im = Image.new("RGB", (W, H), result["tokens"]["bg"])
    d = ImageDraw.Draw(im)
    d.text((gap, 10), f"palette · {result['theme']} theme · from the selected photos", font=font(18), fill=result["tokens"]["ink"])
    for i, (k, v) in enumerate(toks):
        x = gap + i * (sw + gap)
        d.rectangle([x, 44, x + sw, 44 + sw], fill=v, outline=result["tokens"]["line"])
        d.text((x, 44 + sw + 6), f"{k}\n{v}", font=font(14), fill=result["tokens"]["ink"])
    x = gap
    d.text((gap, 250), "photo colors:", font=font(13), fill=result["tokens"]["muted"])
    x = gap + 100
    for c in result["image_colors"]:
        wdt = max(8, int(c["share"] * (W - 140)))
        d.rectangle([x, 250, x + wdt, 280], fill=c["hex"])
        x += wdt
    im.save(out, quality=90)


def run_cli(a) -> int:
    ws = config.workspace()
    sel = read_json(a.selection or (ws / "selection.json"))
    if sel is None:
        raise SystemExit("No selection.json yet. Choose photos first (see SKILL.md).")
    picks = resolve_picks(sel)
    if a.slots:
        want = {s.strip() for s in a.slots.split(",")}
        picks = [p for p in picks if p["slot"] in want]
    result = derive(picks, a.theme)
    write_json(ws / "palette.json", result)
    (ws / "palette.css").write_text(css(result))
    (ws / "sheets").mkdir(exist_ok=True)
    swatch_image(result, ws / "sheets" / "palette.jpg")
    print(css(result))
    for n in result["notes"]:
        print(f"! {n}")
    print(f"swatches: {ws / 'sheets' / 'palette.jpg'}   (tokens also in {ws / 'palette.json'})")
    print("Use these as the starting palette; adjust by eye, but keep the contrast pairs passing.")
    return 0
