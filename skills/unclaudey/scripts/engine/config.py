"""Paths, settings and secrets for unclaudey.

Everything heavy (dataset, thumbnails, embeddings) lives in a per-user cache so it is
shared across projects and never lands in a repo. Per-project working files live in
`.unclaudey/` inside the project the user is building.
"""
from __future__ import annotations

import os
from pathlib import Path

APP = "unclaudey"
VERSION = "0.1.0"

LITE_URL = "https://unsplash.com/data/lite/latest"
TERMS_URL = "https://github.com/unsplash/datasets/blob/master/TERMS.md"
KEY_HELP_URL = "https://unsplash.com/oauth/applications"

# Text-image models (open_clip names). Only permissively licensed weights: designs made with
# this tool are commercial work, so research-only weights (e.g. Apple's MobileCLIP2, AMLR
# license) are deliberately not offered.
MODELS = {
    "siglip2-b16-256": ("ViT-B-16-SigLIP2-256", "webli"),  # Apache-2.0, ~1.5 GB, best retrieval
    "clip-b32-laion": ("ViT-B-32", "laion2b_s34b_b79k"),  # MIT, ~0.6 GB, lighter and weaker
}
DEFAULT_MODEL = "siglip2-b16-256"

# Mean raw cosine of the top-5 results below which the library doesn't really cover a brief
# (calibrated by eye on 25 spot-check briefs; see benchmarks/RESULTS.md). (weak, fair) per model.
COVERAGE = {
    "siglip2-b16-256": (0.085, 0.11),
    "clip-b32-laion": (0.24, 0.28),
}

THUMB_SIZE = 400  # long edge of cached thumbnails, px


def cache_dir() -> Path:
    base = os.environ.get("UNCLAUDEY_CACHE")
    if not base:
        xdg = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
        base = os.path.join(xdg, APP)
    p = Path(base)
    p.mkdir(parents=True, exist_ok=True)
    return p


def config_dir() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return Path(xdg) / APP


def dataset_dir() -> Path:
    return cache_dir() / "dataset"


def lite_dir() -> Path:
    return dataset_dir() / "lite"


def catalog_path() -> Path:
    return cache_dir() / "catalog.sqlite"


def thumbs_dir() -> Path:
    return cache_dir() / "thumbs"


def live_dir() -> Path:
    return cache_dir() / "live"


def large_dir() -> Path:
    return cache_dir() / "large"


def emb_path(model_key: str) -> Path:
    return cache_dir() / f"emb-{model_key}.f16.npy"


def hub_path(model_key: str) -> Path:
    return cache_dir() / f"hub-{model_key}.npy"


def index_meta_path() -> Path:
    return cache_dir() / "index.json"


def usage_path() -> Path:
    return cache_dir() / "usage.json"


def http_cache_path() -> Path:
    return cache_dir() / "http-cache.sqlite"


def workspace(root: str | os.PathLike | None = None, create: bool = True) -> Path:
    p = Path(root or os.getcwd()) / f".{APP}"
    if create:
        p.mkdir(parents=True, exist_ok=True)
        gi = p / ".gitignore"
        if not gi.exists():
            gi.write_text("# unclaudey working files (contact sheets, candidates). Safe to delete.\n*\n")
    return p


def _dotenv() -> dict[str, str]:
    """Read ~/.config/unclaudey/.env (KEY=VALUE lines). Env vars always win."""
    path = config_dir() / ".env"
    out: dict[str, str] = {}
    try:
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            out[k.strip().removeprefix("export ").strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return out


def setting(name: str, default: str | None = None) -> str | None:
    val = os.environ.get(name)
    if val is None or not val.strip():
        val = _dotenv().get(name)
    return val.strip() if val and val.strip() else default


def unsplash_key() -> str | None:
    return setting("UNSPLASH_ACCESS_KEY")


def unsplash_api_base() -> str:
    return (setting("UNSPLASH_API_BASE") or "https://api.unsplash.com").rstrip("/")


def app_name() -> str:
    return setting("UNSPLASH_APP_NAME") or APP


def user_agent() -> str:
    return f"{APP}/{VERSION} (+https://github.com/ramialdine/unclaudey)"
