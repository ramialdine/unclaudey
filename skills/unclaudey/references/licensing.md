# Licensing: what unclaudey does and why

Not legal advice. This is how the tool is built to stay inside each source's rules.

## The local photo index: Unsplash Dataset (Lite)

- Each user downloads it directly from Unsplash, after agreeing to the **Unsplash Dataset Terms**: https://github.com/unsplash/datasets/blob/master/TERMS.md
- **What the Lite license allows:** download and store the data and photos, and *internally* use them to build models or algorithms. The local search index (embeddings, keyword index, image statistics) is that kind of internal use.
- **What it does not allow** without Unsplash's written permission:
  - redistributing or publishing any part of the dataset
  - publicly disclosing comparisons of the dataset with similar datasets

  So:
  - the dataset, thumbnails and index stay in `~/.cache/unclaudey/` and are never committed or shared
  - photos that end up in a published design are **resolved through the Unsplash API** (below), not taken from the dataset files
  - the project does not publish dataset-vs-dataset comparisons
- If Unsplash notifies you that content is disputed, delete it. Removing `~/.cache/unclaudey/` removes everything.

## Photos in designs: Unsplash License + API guidelines

- Photos on unsplash.com are under the **Unsplash License** (https://unsplash.com/license).
  - They are free to use, commercially too.
  - Attribution isn't legally required by the license, but it is required by the API guidelines below.
  - You may not sell unaltered copies, or compile photos to replicate a similar or competing service.
- unclaudey talks to the **Unsplash API** with *your own* free key (`UNSPLASH_ACCESS_KEY`), and follows the guidelines (https://help.unsplash.com/en/articles/2511245-unsplash-api-guidelines):
  - **Hotlink** the image URLs the API returns: `export --mode hotlink` (default). `--mode download` keeps Unsplash photos hotlinked.
  - **Track the download** by calling `download_location` when a photo is used in a design. `resolve` does this.
  - **Attribute** Unsplash and the photographer with links that carry `utm_source=<your app name>&utm_medium=referral`. `export` writes `credits_html`.
- **Sandboxed artifacts** (claude.ai artifacts, single-file HTML) cannot load external images. `--mode inline` embeds a copy after the download has been tracked, keeping the credits in the page. This is the same thing design tools do when you insert an Unsplash photo into a file.
- Without a key, picks are **draft**: fine to preview locally, not for publishing. `lint` flags draft manifests.
- **Rate limits:** a new (demo) app gets 50 requests/hour; after Unsplash approves it for production, 1,000/hour.
  - Searching the local index uses **no** API requests.
  - Each photo you actually use costs about 2 requests (lookup plus download tracking), so a 5-photo page is about 10.
  - `search --expand unsplash` costs 1 request per slot and is cached for 24 h.

## Openverse (keyless live search)

- Openverse indexes openly licensed works. unclaudey only requests licenses that allow **commercial use and modification** (`license_type=commercial,modification`), and additionally drops any NC or ND results. This matters because designs crop and recolor photos.
- Most CC licenses (BY, BY-SA) **require attribution**: title, creator, license and link. `export` writes it from the API's attribution data. CC0 and Public Domain Mark don't require it, but credit anyway.
- BY-SA has share-alike terms for adaptations. If you heavily alter a BY-SA photo, the altered image must stay BY-SA.
- Anonymous limits are 20 requests/min and 200/day for search, and 1,000/day for thumbnails.

## What to tell the user

When you ship images, say in one line:
- where the photos came from
- that credits are in the footer
- if anything is still draft, that they need an Unsplash key before publishing
