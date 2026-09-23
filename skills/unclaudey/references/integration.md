# Using exported images in code

`export` writes `.unclaudey/images.manifest.json`. Each slot has:
- `src`, `srcset`, `sizes`
- `width` and `height`: display size with the true aspect ratio
- `alt`
- `object_position`: from the focal point
- `lqip`: a tiny blurred placeholder as a data URI
- `credit` (text and HTML)
- `html`: a ready `<img>` tag

The file also has a top-level `credits_html`. Always copy values from the manifest. Never write or edit image URLs by hand.

## Plain HTML

```html
<!-- hero: loads first -->
<img src="…" srcset="… 480w, … 1080w, … 1920w" sizes="100vw"
     width="1600" height="1067" alt="Hands centering wet clay on a wheel"
     fetchpriority="high" decoding="async"
     style="object-fit:cover;object-position:62% 45%;background:#8a7 url(data:image/png;base64,…) center/cover no-repeat">

<!-- everything else -->
<img … loading="lazy" decoding="async">
```

Container pattern for a framed crop:

```css
.frame { aspect-ratio: 4 / 5; overflow: hidden; }
.frame img { width: 100%; height: 100%; object-fit: cover; /* object-position from the manifest */ }
```

Full-bleed hero with text in the photo's copy space (left):

```css
.hero { position: relative; min-height: min(92vh, 900px); display: grid; align-items: end; }
.hero img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }
.hero .copy { position: relative; max-width: 34ch; padding: clamp(24px, 6vw, 96px); }
/* only if the measured contrast needs it, and only on the copy side */
.hero::before { content: ""; position: absolute; inset: 0; z-index: 0;
  background: linear-gradient(90deg, rgb(0 0 0 / .5), transparent 55%); }
.hero .copy { z-index: 1; }
@media (max-width: 700px) {        /* the copy space rarely survives a phone crop */
  .hero { min-height: auto; display: block; }
  .hero img { position: static; aspect-ratio: 4 / 5; height: auto; }
  .hero::before { display: none; }
}
```

## Art direction per breakpoint (`<picture>`)

When mobile needs a different crop, use the same photo's CDN URL with other parameters, taken from the manifest `srcset`. Or use two different photos from the selection:

```html
<picture>
  <source media="(max-width: 700px)" srcset="{mobile slot srcset}" sizes="100vw">
  <img src="{hero src}" srcset="{hero srcset}" sizes="100vw" width="…" height="…" alt="…" fetchpriority="high">
</picture>
```

## React / Vite

Import the manifest (copy it into `src/`, or pass `--manifest src/images.manifest.json` to export):

```jsx
import m from "./images.manifest.json";
const Img = ({ slot, ...p }) => {
  const i = m.images[slot];
  return <img src={i.src} srcSet={i.srcset ?? undefined} sizes={i.sizes} width={i.width} height={i.height}
    alt={i.alt} loading={i.hero ? "eager" : "lazy"} fetchPriority={i.hero ? "high" : undefined}
    style={{ objectFit: "cover", objectPosition: i.object_position }} {...p} />;
};
// footer: <p className="credits" dangerouslySetInnerHTML={{ __html: m.credits_html }} />
```

`credits_html` is generated from API data and escaped by unclaudey. That's why it's acceptable here. Don't do this with user input.

## Next.js

`next.config.js`:
```js
module.exports = { images: { remotePatterns: [{ protocol: "https", hostname: "images.unsplash.com" }] } };
```

```jsx
import Image from "next/image";
import m from "@/images.manifest.json";
const i = m.images.hero;
<Image src={i.src} width={i.width} height={i.height} alt={i.alt} sizes={i.sizes} priority
  placeholder={i.lqip ? "blur" : "empty"} blurDataURL={i.lqip ?? undefined}
  style={{ objectFit: "cover", objectPosition: i.object_position }} />
```

Unsplash's CDN already resizes (`w`, `q`, `auto=format`). To avoid double optimization you can add a custom loader:
```js
const unsplashLoader = ({ src, width, quality }) => {
  const u = new URL(src); u.searchParams.set("w", width); u.searchParams.set("q", quality || 75); u.searchParams.set("auto", "format"); return u.toString();
};
```

## Tailwind

```html
<img class="aspect-[4/5] w-full object-cover" style="object-position:62% 45%" …>
```
Keep `object-position` inline from the manifest. Arbitrary percentages are specific to each photo.

## CSS backgrounds

Prefer `<img>`, which gives you alt text, lazy loading and srcset. For purely decorative textures only:

```css
.band { background-image: image-set(url("…w=1080…") 1x, url("…w=2160…") 2x); background-size: cover; background-position: 50% 40%; }
```

## Claude artifacts and single-file HTML

Artifact pages block external hosts (images from CDNs will not load). Use `export --mode inline`: images become WebP data URIs within `--budget-kb` (3 MB by default). Then:
- Use `m.images[slot].src` as-is.
- Keep the credits line in the page.
- Prefer fewer, well-chosen images. Each one costs page weight.

## Performance and accessibility checklist

- Only the hero is eager, with `fetchpriority="high"`. Everything below the fold is `loading="lazy"`.
- Every `<img>` has `width` and `height` or a container with `aspect-ratio`, so there's no layout shift.
- `sizes` matches the layout. A half-width image on desktop is `(min-width: 1024px) 50vw, 100vw`.
- `alt` describes what the photo shows that matters to the page. Pure textures get `alt=""`, marked `"decorative": true` in the selection.
- Text over photos meets contrast on the region behind it, not the photo average.
- Credits are visible (a footer line is fine) and link the photographer and Unsplash with the manifest's utm links.
- Run `unclaudey.py lint <files>` before calling it done.
