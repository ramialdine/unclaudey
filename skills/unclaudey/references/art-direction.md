# Art direction for web photography

## Decide where photography earns its place

Ask what the visitor needs to *see* to believe the page: the room they'll sit in, the food they'll eat, the trail they'll climb, the object in someone's hands, the people the service is for. Those are the photos. Everything else can be type, color, and layout.

- **Hero**: the single most characteristic image of the subject's world. It is often the most important visual decision on the page.
- **Supporting images (2–4)**: each one does a different job, such as place, process, detail, people, or result. Don't make two images that say the same thing.
- **Texture or detail**: a material close-up (paper, stone, linen, wood grain, water) can carry a section background or a quiet band between sections.
- **No photo** is often right for pricing, forms, documentation, and API or dev-tool pages. There, product UI, code, data, or type does the job honestly.

## One photographic voice

Write the art direction as one sentence that every photo must obey:

> documentary, window light, warm but not orange, close working distance, quiet

It fixes five things:
- **light**: soft, hard, window, overcast, golden, neon, flash
- **grade**: warm, cool, muted, saturated, monochrome, film
- **distance**: macro, close, medium, wide, aerial
- **mood**: quiet, energetic, austere, playful, tense
- **authenticity**: documentary vs staged

A set that mixes golden-hour warmth with cold blue studio light, or wide landscapes with macro details at random, reads as "found on a stock site".

## Writing a slot brief

Formula: **subject + action + setting + light + camera + mood**. Use concrete nouns and real verbs.

| Weak | Strong |
|---|---|
| "happy customers" | "two friends sharing a bowl of ramen at a steamy counter, night, shallow depth of field" |
| "modern office" | "late-afternoon light across a long oak worktable with laptops and paper prototypes, nobody in frame" |
| "fitness" | "chalked hands gripping a climbing hold, close-up, hard side light, black background" |
| "technology" | "close-up of a circuit board under a jeweler's loupe, cool light, macro" |

- Put 2–4 **keywords** in the slot (concrete nouns: "pottery wheel", "clay"). They drive the keyword half of the search and the live providers.
- Use **avoid** for what keeps showing up but is wrong: "posed smiling people", "text overlay", "christmas decorations", "a laptop on a bed".
- Ask for **copy_space** only for photos that will carry text. It is a strong filter.
- Ask for **people: none** for places and objects, and **people: required** when the human is the point.

## Stock clichés to steer away from

Put these in `avoid`, or just reject them on the contact sheet:
- handshakes; people pointing at laptop screens; a team high-fiving in an office; a headset-wearing "support agent" smiling at the camera
- lightbulbs, chess pieces, puzzle pieces, rockets, targets and dartboards as concepts
- a person looking at a sunset with arms outstretched (for "freedom", "success")
- generic city skyline at night for "business"; generic server-room blue for "cloud"
- flat-lays of a laptop + coffee + succulent + notebook
- anything with visible watermarks, fake UI glued onto screens, or heavy HDR

## Judging a contact sheet

For each candidate, in order:
1. **Is it the subject?** Is it the actual thing, or a lookalike? A pottery studio is not a paint studio.
2. **Does it survive the crop?** Picture it at the layout's aspect ratio on desktop *and* on a phone.
3. **Where does the text go?** Calm, even-toned space on the side you need, with the subject on the other side.
4. **Does it match the voice?** Check light, grade, distance, and mood against the art direction.
5. **Is it believable?** Look for real moments, not performances. Faces looking at the lens are usually a stock tell.
6. **Is the quality there?** Check focus where it matters, no motion blur unless intended, and enough resolution.

Pick finalists, then run `sheet finalists` with the real headline and the layout's crops. Choose what works *in the layout*, not what is prettiest on its own.

## Cohesion across the set

Run `sheet set`. Squint at it:
- Is one photo warmer, cooler, or more saturated than the rest? Swap it, or plan a consistent CSS treatment for all of them (see below).
- Do the distances vary with purpose? For example: wide hero, medium process, macro detail.
- Is anyone in more than one photo by accident, or is there the same location twice? Replace one.

## Text on photographs

1. Put text in the copy space the photo already has. Don't fight the subject.
2. Measure: `sheet finalists` prints the contrast of white or near-black text on the region's average. Aim for at least 4.5:1 for body text and 3:1 for large display type.
3. If contrast is short, add a *local* scrim that follows the copy space, such as `linear-gradient(90deg, rgb(0 0 0 / .55), transparent 60%)`. Don't darken the whole photo.
4. Never rely on `text-shadow` alone.
5. On mobile the copy space often disappears. Stack the text below the photo instead of overlaying it, or use a crop whose calm area survives (see art direction with `<picture>` in integration.md).

## Cropping and focal points

- Export puts the focal point in `object_position`. Override it in selection.json with `"focal": [x, y]` (0–1) after looking at the finalists sheet.
- Use `aspect-ratio` on the container plus `object-fit: cover` for consistent frames. Use different ratios per breakpoint only when the composition needs it.
- Don't crop through faces, hands at work, or the product. Crop through background.

## Treatments (use sparingly and on purpose)

- **Duotone or monotone** to unify a mixed set: `filter: grayscale(1) contrast(1.05)` plus a `mix-blend-mode: multiply` overlay in the accent color.
- **Grain** for analog warmth: an SVG `feTurbulence` noise overlay at 4–8% opacity.
- **Masks and shapes** (`clip-path`, rounded arches) when the brand vocabulary supports them, not as decoration.
- **Photo as a texture band**: a full-width strip at a low height with `object-fit: cover`.

Whatever you apply, apply it to the whole set, not to one image.

## Image-led motion (respect `prefers-reduced-motion`)

Motion that uses photography reads as intentional. Pick one moment:
- a slow hero reveal: `clip-path: inset(0 0 100% 0)` to `inset(0)` over about 900 ms on load
- a crop that opens on scroll (scale 1.08 to 1 with `animation-timeline: view()`, with a static fallback)
- a hover on a gallery image that shifts `object-position` a few percent (a gentle "look closer")
- view transitions between a grid thumbnail and its detail image (`view-transition-name`)

Wrap all of it in `@media (prefers-reduced-motion: no-preference) { … }`.
