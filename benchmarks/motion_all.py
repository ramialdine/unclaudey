# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy>=1.26", "pillow>=10.3", "playwright>=1.45", "httpx>=0.27"]
# ///
"""Run the unclaudey `motion` check on every <runs>/<brief>/<arm>/index.html.

    uv run benchmarks/motion_all.py <runs_dir> <out_dir>   ->  <out_dir>/motion/<brief>-<arm>/{load,scroll,hover}.jpg, report.json
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills" / "unclaudey" / "scripts"))
from engine import motion  # noqa: E402

runs, out = Path(sys.argv[1]), Path(sys.argv[2])
for page in sorted(runs.glob("*/*/index.html")):
    brief, arm = page.parent.parent.name, page.parent.name
    rep = motion.run(str(page), out / "motion" / f"{brief}-{arm}")
    marks = " ".join({"ok": "✓", "warn": "!", "fail": "✗"}[s] for s, _ in rep["findings"])
    print(f"{brief:10s} {arm:15s} cls={rep['cls']:<7} load_motion={'yes' if rep['load_motion']['moving_intervals'] else 'no':3s} {marks}")
