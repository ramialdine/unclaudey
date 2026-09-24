/* unclaudey · live object: the one interactive canvas centerpiece on a page.
 *
 * Markup (the static SVG is what people see if JavaScript never runs):
 *   <figure class="live" data-live>
 *     <canvas role="img" aria-label="A pot on the wheel. Drag or use arrow keys to shape it."></canvas>
 *     <svg class="live-fallback" viewBox="0 0 200 200" aria-hidden="true">…same object, drawn still…</svg>
 *     <figcaption>Drag across the clay to shape it · <button type="button" data-live-reset>Start over</button></figcaption>
 *   </figure>
 *
 * CSS:
 *   [data-live] canvas { display: none; width: 100%; aspect-ratio: 1; touch-action: pan-y; }
 *   [data-live].is-live canvas { display: block; }
 *   [data-live].is-live .live-fallback { display: none; }
 *   [data-live] canvas:focus-visible { outline: 2px solid var(--color-accent); outline-offset: 4px; }
 *
 * Script:
 *   liveObject(document.querySelector('[data-live]'), {
 *     init(s)            { s.shape = 0; s.intro = 0; },            // your state
 *     intro(s, dt)       { s.intro = Math.min(1, s.intro + dt / 1400); return s.intro < 1; },  // once; true = keep going
 *     finishIntro(s)     { s.intro = 1; },                          // reduced motion: jump to the end
 *     step(s, dt)        { return false; },                         // ongoing physics; true = keep animating
 *     draw(ctx, s)       { … draw with s.w, s.h (CSS px) … },
 *     pointer(s, phase)  { … s.pointer = {x, y} … },                // 'down' | 'move' | 'up'
 *     key(s, key)        { if (key === 'ArrowUp') { s.shape += .05; return true; } },
 *     reset(s)           { s.shape = 0; },
 *   });
 */
function liveObject(root, o) {
  const canvas = root.querySelector('canvas');
  const ctx = canvas.getContext('2d');
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)');
  const s = { w: 0, h: 0, dpr: 1, t: 0, pointer: null, visible: true };
  let running = false, last = 0, introOn = false;

  o.init && o.init(s);
  root.classList.add('is-live');
  canvas.tabIndex = 0;

  function render() { ctx.clearRect(0, 0, s.w, s.h); o.draw(ctx, s); }

  function resize() {
    const r = canvas.getBoundingClientRect();
    s.dpr = Math.min(window.devicePixelRatio || 1, 2);
    s.w = r.width; s.h = r.height;
    canvas.width = Math.max(1, Math.round(r.width * s.dpr));
    canvas.height = Math.max(1, Math.round(r.height * s.dpr));
    ctx.setTransform(s.dpr, 0, 0, s.dpr, 0, 0);
    render();
  }

  function frame(now) {
    const dt = last ? Math.min(64, now - last) : 16;
    last = now; s.t += dt;
    let more = false;
    if (introOn) { introOn = o.intro(s, dt); more = introOn; }
    if (o.step && o.step(s, dt)) more = true;
    render();
    if (more && s.visible && !document.hidden) requestAnimationFrame(frame);
    else { running = false; last = 0; }
  }
  function wake() { if (!running) { running = true; requestAnimationFrame(frame); } }

  function at(e) { const r = canvas.getBoundingClientRect(); return { x: e.clientX - r.left, y: e.clientY - r.top }; }
  canvas.addEventListener('pointerdown', e => {
    canvas.setPointerCapture(e.pointerId); s.pointer = at(e); o.pointer && o.pointer(s, 'down'); wake();
  });
  canvas.addEventListener('pointermove', e => {
    if (!s.pointer) return; s.pointer = at(e); o.pointer && o.pointer(s, 'move'); wake();
  });
  const up = () => { if (!s.pointer) return; o.pointer && o.pointer(s, 'up'); s.pointer = null; wake(); };
  canvas.addEventListener('pointerup', up);
  canvas.addEventListener('pointercancel', up);
  canvas.addEventListener('keydown', e => { if (o.key && o.key(s, e.key)) { e.preventDefault(); wake(); } });
  const resetBtn = root.querySelector('[data-live-reset]');
  if (resetBtn && o.reset) resetBtn.addEventListener('click', () => { o.reset(s); wake(); });

  new ResizeObserver(resize).observe(canvas);
  new IntersectionObserver(([en]) => { s.visible = en.isIntersecting; if (s.visible) wake(); }).observe(canvas);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) wake(); });

  // one orchestrated intro; with reduced motion, show the finished state instead
  if (o.intro && !reduce.matches) { introOn = true; } else if (o.finishIntro) { o.finishIntro(s); }
  resize();
  wake();
  return { state: s, wake, render };
}
