# First paint and startup

The previous page could remain blank while Google Fonts, CDN styles or
parser-blocking scripts were pending. It also fetched the entire gallery and
about 1.9 MB of below-the-fold JPEG backgrounds on first navigation. Gallery
filter initialization waited for the global window load event.

The public page now:

- Includes the dark “Website wordt geladen…” screen and its system-font styling
  in the initial HTML, before any network-dependent asset.
- Loads styles without blocking first paint. Bootstrap, the main stylesheet and
  layout CSS are preloaded; their success or error releases the loading screen.
  A five-second deadline prevents an endless overlay. The page never waits for
  images, fonts, deferred scripts or `window.load` to reveal content.
- Serves Open Sans, Raleway, Satisfy and pinned Bootstrap Table 1.24.0 locally,
  with font-display swap. The duplicate external jQuery request is removed.
- Defers scripts while preserving their dependency order and calendar formatters.
- Preloads the selected hero at high priority. Fallback photos are WebP; the
  default hero is 127,294 bytes instead of a 387 KB JPEG.
- Loads gallery thumbnails lazily and gives them a provisional aspect ratio.
  Isotope initializes after parsing and relayouts as images or core CSS arrive,
  preserving first-click year filters and full-resolution lightbox links.
- Loads about, sponsor and footer backgrounds when they enter the viewport.
  Uploaded site images retain the same selection behavior. Without JavaScript,
  core styles and backgrounds are supplied through noscript fallbacks.

## Verification on 2026-10-05

Before changes, the live HTML response started in roughly 0.18 seconds. On a
fresh browser at 1.6 Mbit/s and 150 ms simulated latency, first content was
visible at 1.24 seconds but DOMContentLoaded and load were still pending after
12 seconds. This does not reproduce every visitor's reported ten-second blank
screen; it confirms blocking dependencies and unnecessary initial traffic.

The complete local production-style preview, with compressed, hashed assets
and a full gallery, rendered first content at 0.12 seconds unthrottled and
0.22 seconds throttled. In the throttled run DOMContentLoaded was 5.59 seconds
and load 5.68 seconds. These local timings are diagnostic, not a promise for
all networks. Live post-deployment timings are checked separately.

Behavioral browser checks covered desktop/mobile, first-click year filters,
gallery image loading and lightbox, the calendar, zero external asset requests,
failed CSS, failed JavaScript and JavaScript disabled. Holding every asset
while allowing only HTML still rendered the loading screen at 0.068 seconds;
the five-second escape released the page and assets subsequently recovered.
Before scrolling, fewer than ten gallery thumbnail requests were permitted.

All 15 Django tests pass, including a regression check for local asset origins,
one deferred jQuery instance and a first-paint screen preceding all styles.
Run `python server/manage.py test www` with development settings. No database
migration or production content change is needed.

Font licenses and Bootstrap Table's license are stored beside the vendored
assets. Font sources use the Google Fonts CSS2 API; Bootstrap Table comes from
the pinned npm distribution. Do not reintroduce remote stylesheets or remove
lazy loading to work around a gallery layout problem.
