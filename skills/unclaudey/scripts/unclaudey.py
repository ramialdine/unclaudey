#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "numpy>=1.26",
#   "pillow>=10.3",
#   "httpx>=0.27",
#   "blurhash>=1.1.4",
#   "torch>=2.2",
#   "open_clip_torch>=3.2",
#   "timm>=1.0.17",
#   "transformers>=4.45",
#   "sentencepiece>=0.2",
# ]
# [tool.uv.sources]
# torch = [{ index = "pytorch-cpu", marker = "sys_platform == 'linux' or sys_platform == 'win32'" }]
# [[tool.uv.index]]
# name = "pytorch-cpu"
# url = "https://download.pytorch.org/whl/cpu"
# explicit = true
# ///
"""unclaudey: art-directed, real photography for Claude-built designs.

Run with uv (it provisions Python and dependencies on first use):

    uv run scripts/unclaudey.py doctor
    uv run scripts/unclaudey.py setup --accept-unsplash-terms     # one time, ~10-15 min
    uv run scripts/unclaudey.py search --plan .unclaudey/plan.json
    uv run scripts/unclaudey.py sheet finalists --slot hero --picks 2,5,7 --crops 16:9,4:5 --copy-space left
    uv run scripts/unclaudey.py palette
    uv run scripts/unclaudey.py resolve
    uv run scripts/unclaudey.py export --mode hotlink
    uv run scripts/unclaudey.py lint index.html

See SKILL.md next to this folder for the full workflow.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from engine import config  # noqa: E402


def cmd_setup(a: argparse.Namespace) -> int:
    from engine import catalog, thumbs
    from engine.util import read_json, write_json, log

    stages = [s.strip() for s in a.stage.split(",")] if a.stage else ["catalog", "thumbs", "index"]
    if a.no_visual:
        stages = [s for s in stages if s not in ("thumbs", "index")]
    if "catalog" in stages:
        if config.catalog_path().exists() and not a.rebuild:
            log(f"catalog: exists ({config.catalog_path()}), skipping (use --rebuild to redo)")
        else:
            lite = catalog.ensure_dataset(a.accept_unsplash_terms)
            catalog.build_catalog(lite, config.catalog_path())
    if not config.catalog_path().exists():
        raise SystemExit("No catalog yet. Run: setup --accept-unsplash-terms")
    if "thumbs" in stages:
        have, failed = thumbs.download_all(workers=a.workers, limit=a.limit)
        log(f"thumbnails ready: {have} (failed {failed})")
    if "index" in stages:
        from engine import indexer

        indexer.build_index(model_key=a.model, batch=a.batch, limit=a.limit)
    if "people" in stages:  # refresh people signals without re-embedding
        from engine import indexer

        n = catalog.refresh_people_keywords(config.catalog_path())
        log(f"people keywords: {n} photos")
        indexer.recompute_people()
    if "hub" in stages:  # refresh hubness scores without re-embedding
        from engine import indexer

        indexer.recompute_hubness()
    meta = read_json(config.index_meta_path(), {}) or {}
    meta["no_visual"] = bool(a.no_visual) and not config.emb_path(meta.get("model", a.model)).exists()
    write_json(config.index_meta_path(), meta)
    log("setup complete. Try: search \"hands shaping clay on a pottery wheel\"")
    return 0


def cmd_search(a: argparse.Namespace) -> int:
    from engine import search

    return search.run_cli(a)


def cmd_sheet(a: argparse.Namespace) -> int:
    from engine import sheets

    return sheets.run_cli(a)


def cmd_palette(a: argparse.Namespace) -> int:
    from engine import palette

    return palette.run_cli(a)


def cmd_resolve(a: argparse.Namespace) -> int:
    from engine import resolve

    return resolve.run_cli(a)


def cmd_export(a: argparse.Namespace) -> int:
    from engine import export

    return export.run_cli(a)


def cmd_lint(a: argparse.Namespace) -> int:
    from engine import lint

    return lint.run_cli(a)


def cmd_doctor(a: argparse.Namespace) -> int:
    from engine import doctor

    return doctor.run_cli(a)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="unclaudey", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--workspace", default=None, help="project root that holds .unclaudey/ (default: cwd)")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("setup", help="download the Unsplash Lite dataset and build the local index")
    s.add_argument("--accept-unsplash-terms", action="store_true", help="the user agreed to the Unsplash Dataset Terms")
    s.add_argument("--stage", default=None, help="comma list of catalog,thumbs,index,people,hub (default: catalog,thumbs,index)")
    s.add_argument("--no-visual", action="store_true", help="keyword-only index (no thumbnails or embeddings)")
    s.add_argument("--model", default=config.DEFAULT_MODEL, choices=sorted(config.MODELS))
    s.add_argument("--workers", type=int, default=16)
    s.add_argument("--batch", type=int, default=128)
    s.add_argument("--limit", type=int, default=None, help="only process the first N photos (testing)")
    s.add_argument("--rebuild", action="store_true")
    s.set_defaults(fn=cmd_setup)

    s = sub.add_parser("search", help="find candidate photos for an image plan (or a single query)")
    s.add_argument("query", nargs="?", help="quick single query instead of --plan")
    s.add_argument("--plan", default=None, help="image plan JSON (default: .unclaudey/plan.json)")
    s.add_argument("--slot", default=None, help="only run these slot ids (comma list)")
    s.add_argument("--k", type=int, default=None, help="candidates per slot (default 12, max 24)")
    s.add_argument("--expand", default=None, help="also search live providers: unsplash,openverse")
    s.add_argument("--orientation", default=None, choices=["landscape", "portrait", "square", "wide", "tall", "any"])
    s.add_argument("--copy-space", default=None, choices=["left", "right", "top", "bottom", "center"])
    s.add_argument("--tone", default=None, choices=["light", "dark", "mid", "any"])
    s.add_argument("--people", default=None, choices=["any", "none", "required"])
    s.add_argument("--color", default=None, help="target hex, e.g. #8a5a3c")
    s.add_argument("--min-width", type=int, default=None)
    s.add_argument("--avoid", default=None, help="comma list of things to steer away from")
    s.add_argument("--json", action="store_true", help="print candidates JSON to stdout")
    s.set_defaults(fn=cmd_search)

    s = sub.add_parser("sheet", help="render finalist crops or the full selected set for visual review")
    s.add_argument("view", choices=["finalists", "set", "slot"])
    s.add_argument("--slot", default=None)
    s.add_argument("--picks", default=None, help="candidate numbers from the slot's contact sheet, e.g. 2,5,7")
    s.add_argument("--crops", default="16:9,4:5", help="aspect ratios to preview")
    s.add_argument("--copy-space", default=None, choices=["left", "right", "top", "bottom", "center"])
    s.add_argument("--headline", default=None, help="sample headline drawn in the copy space")
    s.add_argument("--selection", default=None)
    s.set_defaults(fn=cmd_sheet)

    s = sub.add_parser("palette", help="derive color tokens from the selected photos")
    s.add_argument("--selection", default=None)
    s.add_argument("--theme", default="auto", choices=["auto", "light", "dark"])
    s.add_argument("--slots", default=None, help="only use these slots (comma list)")
    s.set_defaults(fn=cmd_palette)

    s = sub.add_parser("resolve", help="resolve picks through the Unsplash API (download tracking + credits)")
    s.add_argument("--selection", default=None)
    s.set_defaults(fn=cmd_resolve)

    s = sub.add_parser("export", help="write the image manifest, snippets and credits for the build")
    s.add_argument("--selection", default=None)
    s.add_argument("--mode", default="hotlink", choices=["hotlink", "inline", "download"])
    s.add_argument("--out", default=None, help="download mode: folder for image files (e.g. public/images)")
    s.add_argument("--manifest", default=None, help="where to write images.manifest.json (default .unclaudey/)")
    s.add_argument("--budget-kb", type=int, default=3000, help="inline mode: total size budget")
    s.add_argument("--allow-draft", action="store_true", help="export unresolved (draft) photos for local previews")
    s.set_defaults(fn=cmd_export)

    s = sub.add_parser("lint", help="check pages for invented image URLs, missing alt/size/credits")
    s.add_argument("files", nargs="+")
    s.add_argument("--manifest", default=None)
    s.add_argument("--network", action="store_true", help="also HEAD-check every external image")
    s.add_argument("--allow-draft", action="store_true")
    s.set_defaults(fn=cmd_lint)

    s = sub.add_parser("doctor", help="check environment, index and keys")
    s.add_argument("--network", action="store_true")
    s.set_defaults(fn=cmd_doctor)

    a = p.parse_args(argv)
    if a.workspace:
        os.chdir(a.workspace)
    return int(a.fn(a) or 0)


if __name__ == "__main__":
    sys.exit(main())
