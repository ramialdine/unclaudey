# Visual casting: which kind of visual each section gets

Every section gets one visual mode (or none). Decide in the design plan, before searching or drawing. The best pages mix modes on purpose. Photos make the place real, drawings explain and give the brand its own marks, and one live object is the thing people remember.

| Mode | Use it for | Made with |
|---|---|---|
| **photo** | what must be *believed*: the place, the people, the craft, the product in use | the photo pipeline (search → contact sheet → export) |
| **drawn** | what must be *explained or owned*: process, sequences, data, maps, the brand's own marks | SVG and CSS generated from the subject's real geometry (drawn-visuals.md) |
| **live** | the *one* thing visitors should play with | canvas (or WebGL) with `snippets/live-object.js` |
| **product** | software, APIs and dashboards: show the real thing | HTML and CSS UI, code, forms and tables, not screenshots of fake apps |
| **type** | sections where words carry it | typography only; a strong headline can be the visual |

**Hybrids** (where the two approaches work best together):
- **photo + drawn**: a drawn annotation traces over a real photo (the route on a climbing wall, the stages of a pot on the potter's hands). Same palette, so the drawing feels part of the photo.
- **drawn + live**: the course shown as a row of pot drawings, where the current week is the live, reshapeable one.
- **photo + product**: a real UI mockup sitting in a documentary photo's copy space.

## Rules of thumb
- **One live object per page.** Two interactive centerpieces compete for attention; everything else stays still or responds only to hover and press.
- **Photos first where trust matters** (bookings, places, food, people). Drawings first where understanding matters (how it works, what happens when, what's included).
- **Never both for the same job.** If a photo shows the studio, don't also draw the studio. Draw the thing the photo can't show, such as the six weeks as a progression.
- **One palette for everything.** Drawings take their colors from `palette` tokens (which come from the chosen photos), so the page reads as one system.
- **One rendering style for all drawings** on a page. Keep stroke weight, fill style, texture and light direction consistent.

## Examples from the A/B
- **Ceramics studio:**
  - photo: hands in clay (hero), the studio shelves
  - drawn: the six-week course as a progression of pots, the seconds table with each pot's flaw
  - live: one pot you can reshape on the wheel
- **Bouldering gym:**
  - photo: real climbers on real walls
  - drawn: the mill as a line drawing that doubles as a map, grade bars
  - live: optional, e.g. drag to set your own problem on a drawn wall
- **Invoicing API:**
  - product: the invoice, payout slip and tax form as HTML
  - photo: one row of freelancers' cities (human scale)
  - drawn: the currency and payout flow as a diagram
