"""`motion`: a contact sheet for animation, so motion can be reviewed like photos.

Screenshots show a page at rest; this records what it does over time and under stress:
- load filmstrip (first screen at 0-2000 ms) and scroll filmstrip (12 positions), as sheets
- hover probe on the first call to action and the first large visual
- layout shift (CLS) during load and scroll, long tasks, frame pacing while scrolling
- content at rest: headings and text must be visible with JavaScript off, and with reduced
  motion before any scrolling
- census of scroll reveals, warning when many sections share one generic entrance
- reduced motion must actually reduce motion; scroll-driven CSS needs an @supports fallback
"""
from __future__ import annotations

import io
import time
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from . import config
from .browser import SCROLL_THROUGH, browser, new_page, page_url
from .sheets import BG, FG, _badge, _fit, font
from .util import write_json

LOAD_TIMES = [0, 100, 250, 500, 800, 1200, 2000]
SCROLL_STOPS = 12

INIT = """
window.__uc = {cls: 0, shifts: [], longtasks: []};
try { new PerformanceObserver(l => { for (const e of l.getEntries()) { if (!e.hadRecentInput) {
  __uc.cls += e.value; __uc.shifts.push([Math.round(e.startTime), +e.value.toFixed(4)]); } } })
  .observe({type: 'layout-shift', buffered: true}); } catch (e) {}
try { new PerformanceObserver(l => { for (const e of l.getEntries())
  __uc.longtasks.push([Math.round(e.startTime), Math.round(e.duration)]); })
  .observe({type: 'longtask', buffered: true}); } catch (e) {}
window.__ucSample = (ms) => new Promise(res => { const t = []; let last = performance.now();
  const end = last + ms; function f(now) { t.push(now - last); last = now;
  if (now < end) requestAnimationFrame(f); else res(t); } requestAnimationFrame(f); });
"""

HIDDEN_TEXT = """
() => {
  const sel = 'h1,h2,h3,h4,p,li,blockquote,figcaption,button,a,label,td,th,dt,dd';
  const clipHidden = v => /inset\\(\\s*100%|inset\\(\\s*0(px)?\\s+0(px)?\\s+100%|inset\\(\\s*0(px)?\\s+100%|circle\\(\\s*0/.test(v || '');
  const eff = el => { let o = 1;
    for (let n = el; n && n.nodeType === 1; n = n.parentElement) {
      const cs = getComputedStyle(n);
      if (cs.visibility === 'hidden' || cs.display === 'none' || clipHidden(cs.clipPath)) return 0;
      o *= parseFloat(cs.opacity); if (o < 0.05) return o; }
    return o; };
  const out = {total: 0, hidden: 0, samples: []};
  for (const el of document.querySelectorAll(sel)) {
    if (el.closest('details:not([open]), [aria-hidden="true"], nav[hidden], dialog:not([open])')) continue;
    const txt = (el.innerText || el.textContent || '').trim(); if (txt.length < 2) continue;
    const r = el.getBoundingClientRect(); if (r.width === 0 && r.height === 0) continue;
    out.total++;
    if (eff(el) < 0.1) { out.hidden++; if (out.samples.length < 5) out.samples.push(txt.replace(/\\s+/g, ' ').slice(0, 70)); }
  }
  return out;
}
"""

SNAPSHOT = """
(phase) => {
  const eff = el => { let o = 1; for (let n = el; n && n.nodeType === 1; n = n.parentElement) {
    o *= parseFloat(getComputedStyle(n).opacity); if (o < 0.05) break; } return o; };
  const blocks = Array.from(document.querySelectorAll('section, main > *, body > *'))
    .filter(el => el.getBoundingClientRect().height > 120);
  blocks.forEach((b, i) => { if (!b.dataset.ucSec) b.dataset.ucSec = 's' + i; });
  const sectionOf = el => { let s = el.closest('section'); if (s) return s;
    for (const b of blocks) if (b.contains(el)) return b; return null; };
  const els = Array.from(document.querySelectorAll('main *, section *, article *, header *, footer *')).slice(0, 4000);
  if (phase === 'before') {
    els.forEach((el, i) => { el.dataset.ucid = i; el.dataset.ucClass = el.className && el.className.baseVal === undefined ? el.className : '';
      el.dataset.ucOp = eff(el).toFixed(2); el.dataset.ucTf = getComputedStyle(el).transform; });
    return {tracked: els.length};
  }
  const revealed = [];
  for (const el of document.querySelectorAll('[data-ucid]')) {
    const before = parseFloat(el.dataset.ucOp), after = eff(el);
    const tfBefore = el.dataset.ucTf, tfAfter = getComputedStyle(el).transform;
    const opReveal = before < 0.2 && after > 0.8;
    const tfReveal = tfBefore !== 'none' && tfAfter === 'none' && before < 0.99;
    if (!(opReveal || tfReveal)) continue;
    // count only the outermost revealed element
    if (el.parentElement && el.parentElement.closest('[data-uc-rev]')) continue;
    el.dataset.ucRev = '1';
    const oldCls = new Set((el.dataset.ucClass || '').split(/\\s+/).filter(Boolean));
    const cur = typeof el.className === 'string' ? el.className : '';
    const added = cur.split(/\\s+/).filter(c => c && !oldCls.has(c));
    const sec = sectionOf(el);
    const secId = sec ? (sec.dataset.ucSec || sec.id || 'x') : 'page';
    revealed.push({sec: secId, added: added.join(' '), kind: opReveal ? 'fade' : 'move',
                   anim: getComputedStyle(el).animationName, trans: getComputedStyle(el).transitionProperty.slice(0, 40)});
  }
  return {revealed};
}
"""

CSS_TEXT = """
() => { let css = '';
  for (const s of document.styleSheets) { try { for (const r of s.cssRules) css += r.cssText + '\\n'; } catch (e) {} }
  const libs = {gsap: !!window.gsap, scrollTrigger: !!window.ScrollTrigger, lenis: !!window.Lenis || !!window.lenis,
                aos: !!document.querySelector('[data-aos]'), three: !!window.THREE};
  return {css, libs, canvases: document.querySelectorAll('canvas').length, svgs: document.querySelectorAll('svg').length}; }
"""


def _gray(png: bytes, w: int = 160) -> np.ndarray:
    im = Image.open(io.BytesIO(png)).convert("L")
    im = im.resize((w, int(im.height * w / im.width)))
    return np.asarray(im, dtype=np.float32)


def _diff(a: bytes, b: bytes) -> float:
    x, y = _gray(a), _gray(b)
    h = min(x.shape[0], y.shape[0])
    return float(np.abs(x[:h] - y[:h]).mean())


def _diff_local(a: bytes, b: bytes, cols: int = 8, rows: int = 5) -> float:
    """Largest mean change in any grid cell: catches motion confined to one area (a canvas, a photo)."""
    x, y = _gray(a), _gray(b)
    h = min(x.shape[0], y.shape[0])
    d = np.abs(x[:h] - y[:h])
    ch, cw = max(1, h // rows), max(1, d.shape[1] // cols)
    return float(max(d[r * ch:(r + 1) * ch, c * cw:(c + 1) * cw].mean() for r in range(rows) for c in range(cols)))


def _strip(frames: list[tuple[str, bytes]], title: str, out: Path, cols: int = 4, cell: int = 360) -> None:
    ims = [(lab, Image.open(io.BytesIO(png)).convert("RGB")) for lab, png in frames]
    ch = int(cell * ims[0][1].height / ims[0][1].width) if ims else 200
    rows = (len(ims) + cols - 1) // cols
    gap, head = 10, 44
    sheet = Image.new("RGB", (cols * cell + (cols + 1) * gap, head + rows * (ch + gap) + gap), BG)
    d = ImageDraw.Draw(sheet)
    d.text((gap, 12), title, font=font(18), fill=FG)
    for i, (lab, im) in enumerate(ims):
        r, c = divmod(i, cols)
        x, y = gap + c * (cell + gap), head + r * (ch + gap)
        sheet.paste(_fit(im, cell, ch), (x, y))
        _badge(d, (x + 6, y + 6), lab, size=15)
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, quality=84)


def _generic_entrances(revealed: list[dict]) -> dict:
    by_sig = Counter()
    secs_by_sig: dict[str, set] = {}
    for r in revealed:
        sig = r["added"] or (r["anim"] if r["anim"] and r["anim"] != "none" else f"{r['kind']}:{r['trans']}")
        by_sig[sig] += 1
        secs_by_sig.setdefault(sig, set()).add(r["sec"])
    top = max(secs_by_sig.items(), key=lambda kv: len(kv[1]), default=(None, set()))
    return {"revealed_elements": len(revealed), "sections_with_reveals": len({r["sec"] for r in revealed}),
            "most_common": top[0], "most_common_sections": len(top[1])}


def run(target: str, out_dir: Path, video: bool = False) -> dict:
    url = page_url(target)
    report: dict = {"page": target, "checked": time.strftime("%Y-%m-%dT%H:%M:%S")}
    findings: list[tuple[str, str]] = []
    with browser() as b:
        # 1. load filmstrip + metrics
        ctx, pg = new_page(b)
        pg.add_init_script(INIT)
        t0 = time.time()
        pg.goto(url, wait_until="commit", timeout=90_000)
        frames, settled, running = [], [], []
        for t in LOAD_TIMES:
            wait = t / 1000 - (time.time() - t0)
            if wait > 0:
                pg.wait_for_timeout(wait * 1000)
            png = pg.screenshot(type="png")
            try:
                st = pg.evaluate("""() => {
                  const inView = Array.from(document.images).filter(i => { const r = i.getBoundingClientRect();
                    return r.bottom > 0 && r.top < innerHeight && r.width > 0; });
                  return {ready: document.readyState !== 'loading' && document.fonts.status === 'loaded'
                                 && inView.every(i => i.complete && i.naturalWidth > 0),
                          running: document.getAnimations ? document.getAnimations().filter(a => a.playState === 'running').length : 0};
                }""")
            except Exception:
                st = {"ready": False, "running": 0}
            frames.append((f"{int((time.time() - t0) * 1000)} ms", png))
            settled.append(bool(st["ready"]) and float(_gray(png).std()) > 3.0)
            running.append(int(st["running"]))
        pg.wait_for_load_state("networkidle", timeout=60_000)
        pg.wait_for_timeout(600)
        diffs = [_diff_local(frames[i][1], frames[i + 1][1]) for i in range(len(frames) - 1)]
        # ignore first paint, font swaps and photos arriving: only count intervals whose start frame had settled
        moving = [f"{frames[i][0]}→{frames[i + 1][0]}" for i, dv in enumerate(diffs) if dv > 3.0 and settled[i]]
        report["load_motion"] = {"frame_diffs": [round(x, 2) for x in diffs], "moving_intervals": moving,
                                 "still_moving_at_2s": diffs[-1] > 3.0, "css_js_animations_running": running}
        _strip(frames, "load filmstrip · first screen over time", out_dir / "load.jpg")

        # 2. reveal census + scroll filmstrip + frame pacing
        pg.evaluate(SNAPSHOT, "before")
        max_y = pg.evaluate("() => Math.max(0, document.documentElement.scrollHeight - innerHeight)")
        sframes = []
        for i in range(SCROLL_STOPS):
            y = int(max_y * i / max(1, SCROLL_STOPS - 1))
            pg.evaluate(f"() => window.scrollTo(0, {y})")
            pg.wait_for_timeout(450)
            sframes.append((f"{round(100 * y / max(1, max_y))}%", pg.screenshot(type="png")))
        _strip(sframes, "scroll filmstrip · 12 stops top to bottom", out_dir / "scroll.jpg")
        census = pg.evaluate(SNAPSHOT, "after")
        pg.evaluate("() => window.scrollTo(0, 0)")
        pg.wait_for_timeout(400)
        pg.evaluate("() => { window.__ucFrames = null; __ucSample(2600).then(t => window.__ucFrames = t); }")
        for _ in range(45):
            pg.mouse.wheel(0, 140)
            pg.wait_for_timeout(50)
        pg.wait_for_timeout(500)
        ft = pg.evaluate("() => window.__ucFrames || []")[2:]
        metrics = pg.evaluate("() => __uc")
        css = pg.evaluate(CSS_TEXT)
        report["cls"] = round(metrics["cls"], 4)
        report["long_tasks"] = {"count": len(metrics["longtasks"]),
                                "max_ms": max((d for _, d in metrics["longtasks"]), default=0)}
        report["scroll_frames"] = {"samples": len(ft), "p95_ms": round(float(np.percentile(ft, 95)), 1) if ft else None}
        report["entrances"] = _generic_entrances(census["revealed"])
        report["libraries"] = {k: v for k, v in css["libs"].items() if v}
        report["drawings"] = {"canvas": css["canvases"], "svg": css["svgs"]}
        cssText = css["css"]
        report["css"] = {"keyframes": cssText.count("@keyframes"), "scroll_driven": "animation-timeline" in cssText,
                         "supports_guard": "@supports" in cssText and "animation-timeline" in cssText.split("@supports", 1)[-1],
                         "reduced_motion_rule": "prefers-reduced-motion" in cssText}

        # 3. hover probe (back at the top of the page)
        pg.evaluate("() => window.scrollTo(0, 0)")
        pg.wait_for_timeout(500)
        hovers = []
        for kind in ("cta", "visual"):
            el = pg.evaluate_handle("""(kind) => {
                const vis = e => { const r = e.getBoundingClientRect();
                  return r.width > 40 && r.height > 20 && r.top < innerHeight * 0.85 && r.bottom > 40; };
                if (kind === 'cta') {
                  const cands = Array.from(document.querySelectorAll('a[href], button')).filter(vis);
                  const solid = cands.find(e => { const bg = getComputedStyle(e).backgroundColor;
                    return bg && !/rgba\\(0, 0, 0, 0\\)|transparent/.test(bg); });
                  return solid || cands.find(e => e.textContent.trim().length > 3) || null;
                }
                return Array.from(document.querySelectorAll('canvas, img, svg, picture')).filter(vis)
                  .sort((a, b) => b.getBoundingClientRect().width * b.getBoundingClientRect().height
                                - a.getBoundingClientRect().width * a.getBoundingClientRect().height)[0] || null;
            }""", kind)
            sel = kind
            box = el.as_element().bounding_box() if el and el.as_element() else None
            if box:  # keep the probe inside the first screen
                box = {"x": box["x"], "y": max(0, box["y"]), "width": box["width"],
                       "height": min(box["height"], 900 - max(0, box["y"]))}
            if not box:
                continue
            pad = 24
            x0, y0 = max(0, box["x"] - pad), max(0, box["y"] - pad)
            clip = {"x": x0, "y": y0, "width": min(box["width"] + 2 * pad, 1440 - x0),
                    "height": min(box["height"] + 2 * pad, 900 - y0)}
            pg.mouse.move(5, 5)
            pg.wait_for_timeout(250)
            before = pg.screenshot(type="png", clip=clip)
            pg.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            pg.wait_for_timeout(450)
            after = pg.screenshot(type="png", clip=clip)
            hovers += [("rest", before), ("hover", after)]
            report.setdefault("hover", []).append({"target": sel, "responds": _diff_local(before, after) > 3.0})
        if hovers:
            _strip(hovers, "hover probe · rest vs hover", out_dir / "hover.jpg", cols=4, cell=330)
        ctx.close()

        # 4. content at rest: reduced motion (no scrolling) and JavaScript off
        ctx, pg = new_page(b, reduced_motion=True)
        pg.goto(url, wait_until="networkidle", timeout=90_000)
        a = pg.screenshot(type="png")
        pg.wait_for_timeout(1400)
        c = pg.screenshot(type="png")
        report["reduced_motion"] = {"hidden_text": pg.evaluate(HIDDEN_TEXT), "load_diff": round(_diff(a, c), 2)}
        ctx.close()
        ctx, pg = new_page(b, javascript=False)
        pg.goto(url, wait_until="load", timeout=90_000)
        pg.wait_for_timeout(500)
        report["no_js"] = {"hidden_text": pg.evaluate(HIDDEN_TEXT)}
        ctx.close()

        if video:
            vdir = out_dir / "video"
            ctx, pg = new_page(b, video_dir=str(vdir))
            pg.goto(url, wait_until="networkidle", timeout=90_000)
            pg.wait_for_timeout(1500)
            pg.evaluate(SCROLL_THROUGH)
            ctx.close()
            vids = sorted(vdir.glob("*.webm"))
            if vids:
                final = out_dir / "motion.webm"
                vids[-1].replace(final)
                report["video"] = str(final)

    # findings
    if report["load_motion"]["moving_intervals"]:
        findings.append(("ok", f"signature/load motion between {report['load_motion']['moving_intervals'][0]}"
                               f"{' (still moving at 2 s: a long intro or an ambient loop; make sure it settles or stays subtle)' if report['load_motion']['still_moving_at_2s'] else ''}"))
    else:
        findings.append(("warn", "no visible motion on load: consider one signature moment (see references/motion.md)"))
    findings.append(("ok" if report["cls"] < 0.1 else "fail", f"layout shift (CLS) {report['cls']} during load and scroll (budget < 0.1)"))
    lt = report["long_tasks"]
    findings.append(("ok" if lt["max_ms"] < 200 else "warn", f"long tasks: {lt['count']} (longest {lt['max_ms']} ms)"))
    p95 = report["scroll_frames"]["p95_ms"]
    if p95 is not None:
        findings.append(("ok" if p95 <= 34 else "warn", f"scroll frame pacing p95 {p95} ms (~{round(1000 / p95) if p95 else 0} fps; headless estimate)"))
    ent = report["entrances"]
    if ent["most_common_sections"] >= 4:
        findings.append(("warn", f"the same scroll entrance ('{ent['most_common']}') repeats in {ent['most_common_sections']} sections: "
                                 "a generated-looking pattern; keep reveals for 2-3 story beats"))
    else:
        findings.append(("ok", f"scroll reveals: {ent['revealed_elements']} elements in {ent['sections_with_reveals']} sections"))
    rm = report["reduced_motion"]
    if rm["hidden_text"]["hidden"]:
        findings.append(("fail", f"reduced motion: {rm['hidden_text']['hidden']} text elements stay hidden without scrolling "
                                 f"(e.g. '{rm['hidden_text']['samples'][0]}'); show content at rest when motion is reduced"))
    if rm["load_diff"] > 3.0:
        findings.append(("warn", "reduced motion still animates the first screen noticeably; honor prefers-reduced-motion"))
    nj = report["no_js"]["hidden_text"]
    if nj["hidden"]:
        findings.append(("fail", f"JavaScript off: {nj['hidden']} of {nj['total']} text elements are invisible "
                                 f"(e.g. '{nj['samples'][0]}'); gate hidden start states behind a .js class"))
    else:
        findings.append(("ok", f"content visible with JavaScript off ({nj['total']} text elements)"))
    if report["css"]["keyframes"] and not report["css"]["reduced_motion_rule"]:
        findings.append(("warn", "animations without any prefers-reduced-motion rule in CSS"))
    if report["css"]["scroll_driven"] and not report["css"]["supports_guard"]:
        findings.append(("warn", "scroll-driven CSS (animation-timeline) without an @supports guard; Firefox needs a fallback"))
    if "hover" in report:
        resp = [h for h in report["hover"] if h["responds"]]
        findings.append(("ok" if resp else "warn", f"hover response on {len(resp)} of {len(report['hover'])} probed elements"))
    report["findings"] = findings
    write_json(out_dir / "report.json", report)
    return report


def run_cli(a) -> int:
    ws = config.workspace()
    stem = Path(a.page).stem if not a.page.startswith("http") else "url"
    out = ws / "motion" / stem
    rep = run(a.page, out, video=a.video)
    icon = {"ok": "✓", "warn": "!", "fail": "✗"}
    print(f"motion check: {a.page}")
    for state, msg in rep["findings"]:
        print(f" {icon[state]} {msg}")
    print(f"\nsheets: {out / 'load.jpg'}  {out / 'scroll.jpg'}" + (f"  {out / 'hover.jpg'}" if (out / 'hover.jpg').exists() else ""))
    if rep.get("video"):
        print(f"video: {rep['video']}")
    print(f"report: {out / 'report.json'}\nView the sheets: does the motion carry the page's idea, and does anything look generic?")
    return 1 if any(s == "fail" for s, _ in rep["findings"]) else 0
