# Motion that makes a page pop (without looking generated)

A fade-up on every section is the motion equivalent of the cream-and-terracotta palette: the default, and a tell of generated design. Great motion has a **direction** that comes from the subject, a **few deliberate moments**, and holds up under reduced motion, slow devices and failed scripts.

## 1. Direction (write this into the design plan)
- **Personality:** how does this subject move? Pick one word pair and derive easing and timing from it.

  | Personality | Easing (CSS variable) | Durations | Feels like |
  |---|---|---|---|
  | weighty, handmade | `--ease: cubic-bezier(.2,.7,.2,1)` | 700–1100 ms | clay, wood, print |
  | snappy, upward | `--ease: cubic-bezier(.2,.9,.3,1.15)` (slight overshoot) | 250–450 ms | climbing, sport, youth |
  | precise, technical | `--ease: cubic-bezier(.3,0,.2,1)` | 150–300 ms | APIs, finance, tools |
  | drifting, calm | `--ease: cubic-bezier(.4,0,.2,1)` | 1200–2000 ms | spa, nature, hospitality |

  Put them in `:root` as `--ease`, `--dur-1` (fast UI) through `--dur-3` (the signature moment).
- **Intensity dial** (the default is `expressive`):
  - **calm:** hover and press states plus one quiet load moment. CSS only.
  - **expressive:** one signature moment, 2–3 scroll story beats, micro-interactions and smooth state changes.
  - **showpiece:** adds a pinned scroll story (GSAP ScrollTrigger), one split-text headline, and a richer live object (WebGL allowed). It needs a performance budget and is for portfolios and launches.
- **One signature moment**, taken from the subject: clay centering and rising on the wheel, a route lighting up hold by hold, an invoice stamping itself PAID. It happens once, on load or on the first interaction.
- **At most three scroll beats.** They are the story's turns (the six weeks, the new building, the payout arriving), not every section.

## 2. Recipes
The CSS is copy-ready in `scripts/engine/snippets/`. All of it is gated by `.js`, set by an inline script in `<head>`: `<script>document.documentElement.classList.add('js')</script>`. It's also wrapped in `@media (prefers-reduced-motion: no-preference)`, so content is visible at rest whatever happens.

- **Photo reveal on scroll** (`reveal.css`): the frame opens with `clip-path` while the photo settles from a 1.08 scale. It uses CSS scroll timelines where supported, with a small IntersectionObserver fallback for Firefox.
- **Drawing draws itself** (`draw-on.css`): give paths `pathLength="1"` and they stroke in. Staggered with `style="--i:2"`. Can be tied to scroll.
- **Layers assemble:** SVG groups rise into place one after another (a pot built coil by coil, a building floor by floor): `.assemble > g`.
- **Photo + drawing:** a drawn route or annotation traces over a photo as it enters the viewport, which combines the two approaches.
- **The live object's intro** (`live-object.js`): one orchestrated load animation, then it waits for the visitor.
- **Hover and press:** photos shift `object-position` or scale 1.03 on hover. Buttons move 1–2px with a color change. Links draw their underline. Keep it at 150–250 ms.
- **State changes and gallery → detail:** View Transitions API.
  ```js
  if (document.startViewTransition) document.startViewTransition(() => showDetail(id)); else showDetail(id);
  ```
  Give the thumbnail and the large image the same `view-transition-name` (unique per page).
- **Pinned scroll story** (showpiece only): GSAP ScrollTrigger from a pinned CDN.
  ```html
  <script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.15.0/gsap.min.js"></script>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.15.0/ScrollTrigger.min.js"></script>
  <script>
  if (!matchMedia('(prefers-reduced-motion: reduce)').matches) {
    gsap.registerPlugin(ScrollTrigger);
    gsap.timeline({scrollTrigger: {trigger: '#story', start: 'top top', end: '+=150%', scrub: true, pin: true}})
        .from('#story .step', {autoAlpha: 0, y: 30, stagger: .5});
  }
  </script>
  ```
  GSAP is free for commercial sites. Its license only bars competing visual builders. Load it from a CDN and don't copy it into repos. The official `greensock/gsap-skills` skill covers the API in depth.
- **Split-text headline** (showpiece only, once per page): lines rise from behind a mask. Never split every heading.

## 3. Anti-patterns (`motion` and `lint` flag most of these)
- the same fade-up entrance on four or more sections
- content that starts at `opacity: 0` with no `.js` gate, so it stays invisible if scripts fail, for crawlers and in link previews
- animating `top`, `left`, `width`, `height` or `margin`: use `transform`, `opacity` or `clip-path`
- scroll-jacking (hijacking the wheel, snapping full-page sections)
- parallax on everything; bounce on everything; durations over 1.2 s for UI feedback
- motion that ignores `prefers-reduced-motion`
- scroll-driven CSS without `@supports (animation-timeline: view())`, which leaves Firefox with nothing
- infinite ambient loops competing with reading (one subtle loop at most, and it pauses offscreen)

## 4. Budgets
- Animate only `transform`, `opacity`, `clip-path` and `filter`.
- Keep layout shift (CLS) below 0.1, with no long tasks while scrolling and about 60 fps.
- The live object pauses when offscreen and when the tab is hidden.
- The page is complete and readable with JavaScript off and with reduced motion.

## 5. Check it
Run `unclaudey.py motion index.html` and look at:
- `load.jpg`: does the signature moment read in the frames?
- `scroll.jpg`: do the beats land where the story turns?
- `hover.jpg`: do things respond?

Fix every ✗ and reconsider every !. Add `--video` to hand the user a clip.
