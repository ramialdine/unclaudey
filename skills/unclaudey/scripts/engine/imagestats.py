"""Cheap per-image statistics used for filtering and for copy-space ("room for a headline").

Everything is computed on a small grayscale/OKLab version of the thumbnail with numpy.
Gradient energy per region is stored raw; search converts it to dataset percentiles so a
"calm left third" means calm relative to the whole library, not an absolute threshold.
"""
from __future__ import annotations

import numpy as np
from PIL import Image

from .colorutil import rgb_to_oklab

REGIONS = ("l", "r", "t", "b", "c")


def _regions(h: int, w: int) -> dict[str, tuple[slice, slice]]:
    return {
        "l": (slice(0, h), slice(0, int(w * 0.42))),
        "r": (slice(0, h), slice(int(w * 0.58), w)),
        "t": (slice(0, int(h * 0.40)), slice(0, w)),
        "b": (slice(int(h * 0.60), h), slice(0, w)),
        "c": (slice(int(h * 0.30), int(h * 0.70)), slice(int(w * 0.30), int(w * 0.70))),
    }


def compute(img: Image.Image, size: int = 160) -> dict[str, float]:
    im = img.convert("RGB")
    im.thumbnail((size, size), Image.BILINEAR)
    rgb = np.asarray(im, dtype=np.float64) / 255.0
    lab = rgb_to_oklab(rgb)
    L = lab[..., 0]
    a, b = lab[..., 1], lab[..., 2]
    chroma = np.hypot(a, b)

    # Sobel gradient magnitude on lightness
    p = np.pad(L, 1, mode="edge")
    gx = (p[:-2, 2:] + 2 * p[1:-1, 2:] + p[2:, 2:]) - (p[:-2, :-2] + 2 * p[1:-1, :-2] + p[2:, :-2])
    gy = (p[2:, :-2] + 2 * p[2:, 1:-1] + p[2:, 2:]) - (p[:-2, :-2] + 2 * p[:-2, 1:-1] + p[:-2, 2:])
    g = np.hypot(gx, gy)

    h, w = L.shape
    out: dict[str, float] = {
        "lum": float(L.mean()),
        "contrast": float(L.std()),
        "sat": float(chroma.mean()),
        "warmth": float(b.mean() + 0.5 * a.mean()),
        "g_all": float(g.mean()),
    }
    for k, (ys, xs) in _regions(h, w).items():
        out[f"g_{k}"] = float(g[ys, xs].mean())
        out[f"l_{k}"] = float(L[ys, xs].mean())

    # Focal point: where the detail is, pulled gently toward the center.
    wts = g ** 2
    tot = wts.sum()
    if tot > 1e-9:
        yy, xx = np.mgrid[0:h, 0:w]
        fx = float((wts * xx).sum() / tot) / max(1, w - 1)
        fy = float((wts * yy).sum() / tot) / max(1, h - 1)
    else:
        fx = fy = 0.5
    out["fx"] = round(0.75 * fx + 0.25 * 0.5, 3)
    out["fy"] = round(0.75 * fy + 0.25 * 0.5, 3)
    return out


def percentile_rank(values: np.ndarray) -> np.ndarray:
    """0 = lowest value in the library, 1 = highest."""
    order = values.argsort(kind="stable")
    ranks = np.empty(len(values), dtype=np.float64)
    ranks[order] = np.arange(len(values))
    return ranks / max(1, len(values) - 1)


def rank_against(value: float, sorted_ref: np.ndarray) -> float:
    """Percentile of one value against a sorted reference distribution."""
    if len(sorted_ref) == 0:
        return 0.5
    return float(np.searchsorted(sorted_ref, value) / len(sorted_ref))
