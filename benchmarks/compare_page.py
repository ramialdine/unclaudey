# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow>=10.3"]
# ///
"""Build a single self-contained comparison page (screenshots embedded as data URIs).

    uv run benchmarks/compare_page.py <collect_out_dir> <notes.json> <out.html>

notes.json: {"summary": "...", "briefs": {"<id>": {"title": "...", "brief": "...",
             "baseline": "...", "unclaudey": "...", "verdict": "..."}}}
"""
from __future__ import annotations

import base64
import html
import io
import json
import sys
from pathlib import Path

from PIL import Image

DEFAULT_ARMS = [["baseline", "frontend-design only"], ["unclaudey", "unclaudey"]]


def data_uri(path: Path, width: int, max_h: int | None = None, q: int = 72) -> str:
    im = Image.open(path).convert("RGB")
    if im.width > width:
        im = im.resize((width, int(im.height * width / im.width)), Image.LANCZOS)
    if max_h and im.height > max_h:
        im = im.crop((0, 0, im.width, max_h))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=q, optimize=True, progressive=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


CSS = """
:root{--ground:#e9e7e3;--sheet:#f7f6f3;--ink:#1f1d1b;--muted:#5d5853;--rule:#cfcac3;--pencil:#b3261e;--pencil-ink:#fff;
--display:"Archivo",system-ui,sans-serif;--body:"Archivo",system-ui,sans-serif;--edge:"IBM Plex Mono",ui-monospace,monospace}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--ground:#221f1d;--sheet:#2b2825;--ink:#efebe6;--muted:#aaa39b;--rule:#443f3a;--pencil:#e0574d;--pencil-ink:#1b1918;color-scheme:dark}}
:root[data-theme="dark"]{--ground:#221f1d;--sheet:#2b2825;--ink:#efebe6;--muted:#aaa39b;--rule:#443f3a;--pencil:#e0574d;--pencil-ink:#1b1918;color-scheme:dark}
[hidden]{display:none!important}
body{background:var(--ground);color:var(--ink);font:16px/1.55 var(--body);padding-inline:clamp(16px,4vw,48px);padding-block:40px 64px}
.wrap{max-width:1320px;margin:0 auto;display:grid;gap:56px}
header{display:grid;gap:14px;max-width:72ch}
h1{font:800 clamp(34px,5vw,58px)/1.02 var(--display);letter-spacing:-.02em;margin:0;text-wrap:balance}
h1 .circle{display:inline-block;padding:0 .18em;border:3px solid var(--pencil);border-radius:48% 52% 45% 55%/55% 45% 55% 45%;transform:rotate(-2deg)}
.lede{font-size:18px;color:var(--muted);margin:0}
.summary{background:var(--sheet);border-left:4px solid var(--pencil);padding:18px 22px;max-width:80ch}
.summary p{margin:.4em 0}
section.brief{display:grid;gap:18px}
.brief h2{font:700 clamp(22px,2.6vw,30px)/1.15 var(--display);margin:0}
.brief .ask{color:var(--muted);max-width:90ch;margin:0}
.pair{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,400px),1fr));gap:18px}
figure{margin:0;background:var(--sheet);padding:12px 12px 14px;display:grid;gap:10px;align-content:start}
.edge{font:500 12px/1 var(--edge);letter-spacing:.08em;color:var(--muted);display:flex;justify-content:space-between;gap:12px;text-transform:uppercase}
.edge b{color:var(--pencil);font-weight:600}
.frame{overflow:auto;max-height:720px;border:1px solid var(--rule);background:var(--ground)}
.frame img{display:block;width:100%;height:auto}
.frame.mobile{display:flex;justify-content:center;padding:12px}
.frame.mobile img{width:min(100%,360px)}
.views{display:flex;gap:6px;flex-wrap:wrap}
.views button{font:600 13px/1 var(--body);padding:8px 12px;border:1px solid var(--rule);background:transparent;color:var(--ink);cursor:pointer}
.views button[aria-pressed="true"]{background:var(--pencil);border-color:var(--pencil);color:var(--pencil-ink)}
.views button:focus-visible{outline:2px solid var(--pencil);outline-offset:2px}
dl{display:grid;grid-template-columns:max-content 1fr;gap:4px 14px;margin:0;font-size:14px}
dt{color:var(--muted)}dd{margin:0;font-variant-numeric:tabular-nums}
.note{font-size:15px;margin:0}
.verdict{margin:0;padding:12px 16px;border:2px solid var(--pencil);border-radius:14px 18px 12px 20px/18px 12px 20px 14px;max-width:90ch}
footer{color:var(--muted);font-size:14px;max-width:90ch}
@media (prefers-reduced-motion:no-preference){.views button{transition:background .15s,color .15s}}
"""

JS = """
document.querySelectorAll('figure[data-arm]').forEach(fig=>{
  const buttons=fig.querySelectorAll('.views button');
  buttons.forEach(b=>b.addEventListener('click',()=>{
    buttons.forEach(x=>x.setAttribute('aria-pressed',String(x===b)));
    fig.querySelectorAll('.frame').forEach(f=>{f.hidden=f.dataset.view!==b.dataset.view;});
  }));
});
"""


def facts_dl(f: dict, m: dict | None = None) -> str:
    hosts = ", ".join(f"{h} ×{n}" for h, n in f["image_hosts"].items()) or "none"
    rows = [
        ("<img> tags", f["img_tags"]),
        ("photo sources", hosts),
        ("inline SVGs", f["svg_elements"]),
        ("fonts", ", ".join(f["google_fonts"]) or "system"),
        ("photo credits", "yes" if f["has_credits"] else "no"),
    ]
    if m:
        rows += [
            ("load motion", "yes" if m["load_motion"]["moving_intervals"] else "none"),
            ("scroll reveals", f'{m["entrances"]["revealed_elements"]} in {m["entrances"]["sections_with_reveals"]} sections'),
            ("layout shift", m["cls"]),
            ("hidden, JS off", m["no_js"]["hidden_text"]["hidden"]),
            ("hidden, reduced motion", m["reduced_motion"]["hidden_text"]["hidden"]),
            ("motion checks", " ".join({"ok": "✓", "warn": "!", "fail": "✗"}[st] for st, _ in m["findings"])),
        ]
    return "<dl>" + "".join(f"<dt>{html.escape(k)}</dt><dd>{html.escape(str(v))}</dd>" for k, v in rows) + "</dl>"


def build(collect_dir: str, notes_path: str, out: str) -> None:
    cdir = Path(collect_dir)
    facts = json.loads((cdir / "facts.json").read_text())
    notes = json.loads(Path(notes_path).read_text())
    parts = [
        '<title>unclaudey A/B</title>',
        '<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>',
        '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@400;600;700;800&family=IBM+Plex+Mono:wght@500;600&display=swap">',
        f"<style>{CSS}</style>",
        '<div class="wrap">',
        f'<header><h1>{notes.get("headline", "Same brief, same model. One of them <span class=\"circle\">looked</span> at photos first.")}</h1>',
        f'<p class="lede">{notes.get("lede", "")}</p></header>',
        f'<div class="summary">{notes["summary"]}</div>',
    ]
    frame_no = 1
    arm_list = notes.get("arms") or DEFAULT_ARMS
    for bid, arms in facts.items():
        n = notes["briefs"].get(bid, {})
        parts.append(f'<section class="brief" id="{html.escape(bid)}"><h2>{html.escape(n.get("title", bid))}</h2>')
        parts.append(f'<p class="ask">{html.escape(n.get("brief", ""))}</p><div class="pair">')
        for arm, label in arm_list:
            if arm not in arms:
                continue
            a = arms[arm]
            mdir = cdir / "motion" / f"{bid}-{arm}"
            motion = json.loads((mdir / "report.json").read_text()) if (mdir / "report.json").exists() else None
            strips = "".join(f'<img src="{data_uri(mdir / n, 1000, q=70)}" alt="{html.escape(label)}: {n[:-4]} filmstrip" loading="lazy">'
                             for n in ("load.jpg", "scroll.jpg") if (mdir / n).exists())
            img = cdir / "img"
            fold = data_uri(img / f"{bid}-{arm}-desktop-fold.jpg", 1100)
            full = data_uri(img / f"{bid}-{arm}-desktop-full.jpg", 900, max_h=7000, q=66)
            mob = data_uri(img / f"{bid}-{arm}-mobile-full.jpg", 360, max_h=5200, q=70)
            parts.append(
                f'<figure data-arm="{arm}"><div class="edge"><span>{frame_no:02d} ▸ <b>{html.escape(label)}</b></span><span>{html.escape(bid)}</span></div>'
                f'<div class="views" role="group" aria-label="View"><button type="button" data-view="fold" aria-pressed="true">First screen</button>'
                f'<button type="button" data-view="full" aria-pressed="false">Full page</button>'
                f'<button type="button" data-view="mobile" aria-pressed="false">Mobile</button>'
                + ('<button type="button" data-view="motion" aria-pressed="false">Motion</button>' if strips else '') + '</div>'
                f'<div class="frame" data-view="fold"><img src="{fold}" alt="{html.escape(label)}: first screen of the {html.escape(bid)} page"></div>'
                f'<div class="frame" data-view="full" hidden><img src="{full}" alt="{html.escape(label)}: full {html.escape(bid)} page" loading="lazy"></div>'
                f'<div class="frame mobile" data-view="mobile" hidden><img src="{mob}" alt="{html.escape(label)}: {html.escape(bid)} page on a phone" loading="lazy"></div>'
                + (f'<div class="frame" data-view="motion" hidden>{strips}</div>' if strips else '')
                + f'{facts_dl(a["facts"], motion)}<p class="note">{html.escape(n.get(arm, ""))}</p></figure>')
            frame_no += 1
        parts.append("</div>")
        if n.get("verdict"):
            parts.append(f'<p class="verdict"><strong>Verdict.</strong> {html.escape(n["verdict"])}</p>')
        parts.append("</section>")
    parts.append(f'<footer>{notes.get("footer", "")}</footer></div><script>{JS}</script>')
    Path(out).write_text("\n".join(parts), encoding="utf-8")
    print(out, f"{Path(out).stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    build(*sys.argv[1:])
