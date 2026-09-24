---
name: unclaudey
description: Distinctive frontend design with real photography, code-drawn illustration and purposeful motion. Use when building or restyling a website, landing page, marketing page, portfolio, web app screen or HTML artifact, especially when it should not look templated or AI-generated. Plans a subject-specific design system, casts each section as photo, drawing, live object or type, semantically searches ~25k professional photos (plus live Unsplash/Openverse) and reviews them on contact sheets, draws SVG/canvas visuals from the subject's real geometry, directs one signature motion moment plus a few scroll beats, and verifies drawings and motion with rendered sheets and filmstrips. Never invents image URLs.
license: Apache-2.0. Derived from Anthropic's frontend-design skill; see LICENSE.txt and NOTICE.
---

# unclaudey: frontend design with real photography

Approach this as the design lead at a design studio known for giving every client a distinct visual identity that is not mistaken for anyone else's. This client has already rejected proposals that felt cliché or templated, and is paying for a distinctive point of view: make deliberate, opinionated choices about palette, typography, layout **and imagery** that are specific to this brief, and take aesthetic risk if justified.

Generated pages also look generated because they have no real pictures: gradients, emoji and icon cards stand in for photography, or invented image URLs 404. This skill adds a photo pipeline you drive yourself: a local, semantically searchable library of professional photos, contact sheets you **look at** before choosing, a palette taken from the chosen photos, and export that writes correct, credited, responsive markup. Its commands are in *Imagery* below.

## Ground your designs in the subject matter

If the brief does not identify what the product or subject matter is, identify it yourself before designing, and confirm with the client. You can come up with one concrete subject, the design's audience, and the design's primary job, as a proposal. If there's any information in your memory about the client's preferences or context about what they're building, use that as a hint. The subject's industry, subject matter, materials, and vernacular are where distinctive visual choices come from — a design for a toy for girls aged 8–11 will be very aesthetically different from a dashboard for financial analysts. Build with the brief's real content and subject matter throughout.

The subject's real world is also where the imagery comes from: its places, materials, tools, food, weather, hands at work. Photography of that world is often the fastest route to a page that could only belong to this client.

## Design principles

For web designs, the hero is the first thing viewers will see. Open with the most characteristic thing in the subject's world, in the form that is most appropriate: a headline, an image, an animation, a live demo, an interactive moment, or other treatments. Be deliberate with your choice: a big number with a small label, supporting stats, and a gradient accent is the default treatment, so only use it if that's truly the best option. When the subject has a visible world, a real photograph chosen for this brief is usually a stronger opener than any decorative treatment.

Typography carries the personality of the page. You don't need a different typeface for display or headline text and body content: use one family or two, and if two, make them clearly distinct.

Choose your typefaces deliberately, not the default families you would reach for on any other project, and set a clear type scale following the default guidance of The Elements of Typographic Style with intentional weights, widths, and spacing. When type is used as a headline or visual element, use the type treatment itself as an active part of the design, not a neutral delivery vehicle for the content.

Default to line lengths of less than 80 characters. Serif typefaces can have slightly longer line lengths; give serif body text slightly more line-height than a sans-serif.

Avoid these default typographic treatments; they are the commonest tells of a generated page:
- Accenting just a single word or phrase in a headline, like putting one word in italic/bold or a different color.
- Using all caps for labels.
- Adding unnecessary typographic labels above content.

Visual structure is information. Structural devices like outlines, borders, numbering, eyebrows, dividers, labels, etc., encode useful information about the content rather than decorate it. Many generic designs use numbered markers (01 / 02 / 03), but that's only appropriate if the content actually is a sequence — like a stepped process or a timeline. Before adding numbered markers, check the content really is a sequence.

Use non-user-triggered motion sparingly and deliberately, only to draw attention. A single orchestrated moment — one page-load sequence or one reveal — lands better than scattered effects; fade-and-slide-up entrances on each section and hover transitions on every card are the generic default and read as AI-generated. Motion that answers a person's action (opening, expanding, confirming) is welcome when it shows what changed. Photography gives motion something real to do (a slow reveal of the hero, a crop that opens on scroll); see references/art-direction.md, and always respect `prefers-reduced-motion`.

Consider written content carefully. Often a design brief may not contain real content, and it's up to you to come up with copy and placeholder content. Copy can make a design feel as templated as the design itself. See the below section on writing for more guidance.

## Process: plan, review against the brief, build, critique

For calibration, AI-generated design right now clusters around some traits:
1. a warm cream background (near #F4F1EA) with a high-contrast serif display and a terracotta or warm-clay accent (often near #D97757 — Anthropic's own Claude-interaction accent, so on a user's brief it reads as a tell);
2. a near-black background with a single bright acid-green or vermilion accent;
3. a broadsheet-style layout with hairline rules, zero border-radius, and dense newspaper-like columns;
4. the SaaS-card kit: content chopped into identical rounded cards, one border-radius on everything regardless of hierarchy, the same soft grey shadow (rgba(0,0,0,.1)) under each, and gradient washes as decoration;
5. template chrome that appears whatever the subject: a tracked-out ALL-CAPS eyebrow label above every heading; meta strings joined with middle dots ('A · B · C'); labels built as 'WORD — fragment' with a spaced em dash; tinted near-black (#0B0B0B, #111) standing in for black; a monospace face for small data labels; a '→' appended to link and button text;
6. imagery that is absent or generic: gradient blobs, emoji and icon-in-a-circle cards where the subject has a visible world, or stock clichés (handshakes, people pointing at laptops, lightbulb concepts, a smiling team in an office) that could illustrate any company.

All traits are legitimate for some briefs, but they are defaults rather than choices, and they appear regardless of subject. Where the brief pins down a visual direction, follow it exactly — the brief's own words always win, including when it asks for one of these looks. Where it leaves an axis free, don't spend that freedom on one of these defaults. As with a hired human designer, there's often a careful balance between doing what you're good at and taking each project as a chance to experiment and learn.

Work in two passes. First, brainstorm a short design plan based on the client's design brief: create a compact token system with color, type, layout, imagery, and principles.
- Color: describe the core base palette as 4–6 named hex values. If the page uses photography, finalize color after choosing the photos (the `palette` step), so UI and imagery agree.
- Type: the typefaces and their roles.
- Layout: a layout concept, using one-sentence prose descriptions and ASCII wireframes to ideate and compare. Include alignment guidance; should the content be left aligned, center aligned, justified?
- Imagery: one sentence of art direction (the photographic voice: light, color grade, distance, mood) and the image plan: which sections get a photo and what each photo must show. Decide where photography earns its place; one strong hero and two to four supporting images beat a dozen stock tiles. If the subject has no visible world (an API, a dev tool), say what carries the visuals instead.
- Visuals (casting): for each section, pick photo, drawn, live, product or type (references/visual-casting.md). Photograph what must be believed, draw what must be explained or owned (references/drawn-visuals.md), and make at most one live object people can play with.
- Motion: a personality taken from the subject, the intensity (`expressive` unless the brief says otherwise), the one signature moment, at most three scroll beats, the micro-interactions, and duration and easing tokens (references/motion.md).
- Principles: the high-level guidance for what makes this page unique.

Then review that plan against the brief before building: if any part of it reads like the generic default you would produce for any similar page (work through a similar prompt to see if you arrive somewhere similar) rather than a choice made for this specific brief — revise that part, say what you changed and why. Only after you've confirmed the relative uniqueness of your design plan should you start to write the code, following the revised plan.

When writing the code, be careful of structuring your CSS selector specificities. It's easy to generate CSS classes that cancel each other out (especially with a type-based selector like .section and an element-based selector like .cta). This can happen often with padding/margin between sections.

## Imagery: real photographs, chosen with your own eyes

Run every command with uv from this skill's base directory (shown when the skill loads). Below, `$UC` means `uv run "<skill base dir>/scripts/unclaudey.py"`. Commands work in the project folder you are building in, and keep working files in its `.unclaudey/` folder.

**0. Once per machine.** Run `$UC doctor`.
- If the Unsplash Dataset terms are not accepted, ask the user before going further. Summarize the terms: the dataset may be downloaded and used internally to build a search index, but not redistributed or published, and comparisons with other datasets may not be published publicly. Link https://github.com/unsplash/datasets/blob/master/TERMS.md.
- Only with the user's yes, run `$UC setup --accept-unsplash-terms` in the background (about 15 minutes, about 1.3 GB, resumable). Meanwhile, design the parts that don't need photos.
- If the user declines, use `search --expand openverse` only, or design without photographs.
- A missing `UNSPLASH_ACCESS_KEY` only matters at publishing time. The user creates the free key themselves, following the README. Never ask them to paste the key into the chat.

**1. Write the image plan** to `.unclaudey/plan.json`:
```json
{
  "art_direction": "documentary, window light, warm but not orange, close working distance, quiet",
  "avoid": ["posed smiling people looking at the camera"],
  "slots": [
    {"id": "hero", "brief": "close-up of wet hands centering clay on a spinning pottery wheel, side window light, shallow depth of field",
     "keywords": ["pottery wheel", "clay", "ceramics"], "orientation": "landscape", "copy_space": "left", "tone": "dark"},
    {"id": "studio", "brief": "sunlit ceramics studio with shelves of unglazed bowls", "orientation": "portrait", "people": "none"}
  ]
}
```
- **brief** is required. The formula is subject + action + setting + light + camera distance or angle + mood. Concrete nouns beat adjectives.
- **keywords** are for the keyword side of the search. Give 2–4 concrete nouns.
- **orientation** is `landscape`, `wide`, `portrait`, `tall`, `square` or `any`.
- **copy_space** is `left`, `right`, `top`, `bottom` or `center`: the region that must be calm enough to hold text.
- **tone** is `dark`, `light` or `mid`. **people** is `none` or `required`.
- **color** is a hex value to lean toward. **min_width** is in px. **k** is the number of candidates, 12 by default.

See references/art-direction.md for writing briefs and references/photo-archetypes.md for photographic directions.

**2. Search.** Run `$UC search --plan .unclaudey/plan.json`. This writes one numbered contact sheet per slot to `.unclaudey/sheets/<slot>.jpg`. For a quick single look, use `$UC search "misty pine forest at dawn" --orientation landscape`.

Each slot reports **library coverage** as `good`, `fair` or `weak`. The local library holds about 25k photos. It is strong on landscapes, nature, cities, architecture, interiors, food, textures and lifestyle, and thin on specific trades and services (dental clinics, mechanics, pottery wheels, bakeries).
- On **weak**, don't choose from that sheet. Re-run the slot with `$UC search --plan … --slot <id> --expand unsplash`. That searches the full Unsplash library live (it needs the user's key) and re-ranks results with the same model and filters. Add `openverse` for keyless, Creative Commons results; it is rate-limited, so use it sparingly.
- On **fair**, check that the subject is really there, and expand if it isn't.

**3. Look, then choose.** Read every contact sheet image. The search only proposes; your eyes decide. Judge each candidate on:
- Subject accuracy.
- Whether the composition survives the crop the layout needs.
- Real calm space where text will sit.
- Light and grade consistent with the art direction.
- Authenticity: reject staged-stock looks, fake smiles and generic offices.
- Technical quality.

Then:
- For the hero and any photo that will carry text or be cropped hard, run `$UC sheet finalists --slot hero --picks 3,7,9 --crops 16:9,4:5 --copy-space left --headline "<the real headline>"`. It shows each crop with the text in place and its contrast.
- **If nothing fits:** rewrite the brief more concretely (at most twice), relax a filter, or add `--expand unsplash,openverse`. If it still fails, change that section's design (type-led, product UI, texture, illustration). A wrong photo is worse than none.

Write `.unclaudey/selection.json`:
```json
{"picks": [
  {"slot": "hero", "pick": 7, "alt": "Hands pressing into a spinning lump of wet clay", "focal": [0.62, 0.45]},
  {"slot": "studio", "pick": 2, "alt": "Rows of unglazed bowls drying on wooden studio shelves"}
]}
```
- `pick` is the number on the contact sheet.
- `alt` says what the photo shows that matters to this page. Don't write "image of". Set `"decorative": true` only for pure texture.
- `focal` (0–1, optional) moves the crop.
- The photo in a slot named `hero` (or `cover`, `banner`, `header`) loads eagerly with high priority, and every other photo loads lazily. If your top-of-page photo lives in a differently named slot, add `"hero": true` to its pick.

Then run `$UC sheet set` and check that the chosen photos read as one photographic voice: light temperature, contrast, grade and distance. Swap the outlier.

**4. Palette from the photos.** Run `$UC palette` (`--theme light|dark` to force a theme). It prints CSS tokens (`--color-bg`, `surface`, `line`, `ink`, `muted`, `accent`, `accent-ink`, `accent-2`) and draws a swatch sheet at `.unclaudey/sheets/palette.jpg`. Look at it next to the photos. Use it as the starting color system and adjust by eye, but keep contrast passing. If it warns that the palette matches a known generated look, change it.

**5. Resolve and export.**
- Run `$UC resolve`. It resolves picks through the Unsplash API: official URLs, the required download tracking, and the current photographer name. Without a key, picks stay *draft*, which is fine for local previews but not for anything you publish or hand over.
- Then choose one export mode:
  - `$UC export --mode hotlink` for websites.
  - `--mode inline` for Claude artifacts and single-file HTML, where external images are blocked.
  - `--mode download --out public/images` to self-host openly licensed photos. Unsplash photos stay hotlinked, per the API guidelines.
- Build with `.unclaudey/images.manifest.json` or `.unclaudey/snippets.html`: `src`, `srcset`, `sizes`, `width`/`height`, `object_position`, blur placeholder, and credits. For frameworks such as Next `<Image>`, Tailwind, `<picture>` and CSS backgrounds, see references/integration.md.

Rules that always apply:
- **Never type an image URL yourself.** Use only URLs from the manifest. Invented Unsplash IDs 404, and the old `source.unsplash.com` service is shut down.
- **Only use photos that came through this pipeline** (the local library, `--expand unsplash`, `--expand openverse`). Don't pull images from other stock sites, search engines or social media. Their licenses and URLs aren't verified, and hotlinking them often breaks. If the pipeline can't cover a slot, change that section's design.
- **Keep the run lean.** A typical page needs:
  - one plan with 3–6 slots and one search
  - one look at each sheet
  - finalists only for the hero and any photo that carries text
  - at most one rewrite or expand round per weak slot

  More searching rarely beats a clear brief, and every sheet you view costs the user tokens.
- **Credit photographers** with the manifest's `credits_html` (a footer line is fine). Unsplash's API guidelines and CC licenses require it.
- The hero loads eagerly with `fetchpriority="high"` and the rest load lazily. Every image gets `width`/`height` or an `aspect-ratio`.
- Put text over a photo only in its copy space. Add a scrim gradient only where the measured contrast needs it.
- Apply CSS treatments (duotone, grain, masks) only when they serve the art direction. Never make a photo look like something it isn't.

**6. Drawings and motion.** Build code-drawn visuals from the subject's real geometry, generated by a small script with the palette tokens. Use the snippets in `scripts/engine/snippets/`:
- `live-object.js` for the one interactive canvas
- `draw-on.css` for drawings that draw themselves or assemble
- `reveal.css` for photo reveals on story beats

Put `<script>document.documentElement.classList.add('js')</script>` in `<head>`, so nothing starts hidden unless scripts run.

**7. Check.**
- Run `$UC lint <built files or folder>` and fix every error. It also checks motion statically.
- Run `$UC sheet drawings --page <page>` and view the sheet. Is every drawing specific to the subject, consistent in style, on-palette and legible on a phone?
- Run `$UC motion <page>` and view `load.jpg` and `scroll.jpg`. Does the signature moment read? Do the beats land where the story turns? Fix every ✗: content hidden with reduced motion or JavaScript off, and layout shift. Reconsider every !: the same entrance repeated in many sections, no reduced-motion rule, no `@supports` fallback.
- Take desktop and mobile screenshots.
- Ask of the result: does the photography carry the page's identity? Do the drawings belong to this subject? Does the motion say something about it? Do the crops hold on mobile? Does anything still read like generic stock, or like one of the six traits above?

## Restraint and self-critique

Spend your boldness in one place. Let one element be the memorable thing, keep everything around it quiet and disciplined, and cut any decoration that does not serve the brief. Build to a quality floor without announcing it: responsive down to mobile, visible keyboard focus, reduced motion respected, visually accessible, harmonious color palettes. Critique your own work as you build, taking screenshots to review if your environment supports it — a picture is worth 1000 tokens. Consider Chanel's advice: before leaving the house, take a look in the mirror and remove one accessory. Human creatives have memory and always try to do something new, so if you have a space to quickly jot down notes about what you've tried, it can help you in future passes. (The photo library does this for images: photos used in your other projects rank lower, so sites don't converge on the same few popular shots.)

## More on writing in design

Words appear in a design for one reason: to make it easier to understand and use. They are design content, not decoration. Bring the same intentionality and minimalism to copywriting that you would bring to spacing and color. Before writing anything, ask what the design needs to say, and how it can best be said to help the person navigate the experience.

Write from the end user's perspective. Name things by what users will understand in simple language, not by how the system is built. A user manages notifications, not webhook config. Describe what something is or does in plain terms rather than selling it. Being specific and legible to new users is always better than being clever.

Use active voice as default. A CTA says exactly what happens when it is used: "Save changes," not "Submit." An action keeps the same name through the whole flow, so the button that says "Publish" produces a toast that says "Published." The vocabulary of an interface is the signposting for someone navigating the product. Cohesion and consistency are how people learn their way around.

Treat failure and emptiness as moments for direction, not mood. Explain what went wrong and how to fix it, in the interface's voice rather than a person's. Errors don't apologize, and they are never vague about what happened. An empty screen is an invitation to act.

Keep the tone conversational: plain verbs, sentence case, no filler, with tone matched to the brand and the audience. Let each written element do exactly one job.

## References
- references/art-direction.md: writing slot briefs, stock clichés to avoid, set cohesion, text on photos, crops, image-led motion
- references/photo-archetypes.md: photographic directions with query modifiers and type/layout pairings
- references/integration.md: HTML, `<picture>`, Next.js, Tailwind, CSS backgrounds, artifacts, placeholders, performance
- references/inspiration.md: where to study real design, and how to learn from references without copying
- references/licensing.md: the Unsplash License, dataset terms, API guidelines, and Creative Commons
- references/visual-casting.md: which sections get a photo, a drawing, a live object, product UI or type
- references/drawn-visuals.md: SVG and canvas illustration from the subject's real geometry, with generator building blocks
- references/motion.md: motion direction, the intensity dial, recipes (CSS-first, GSAP when needed), anti-patterns and budgets
