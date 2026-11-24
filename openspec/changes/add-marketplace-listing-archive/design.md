## Context

Listing pages (`/v/…/m<id>-…`) embed `window.__CONFIG__` JSON with title, price, gallery (`media.images[].base` with a `#` size placeholder), seller, statistics, highlights and, for cars, grouped labelled attributes. The description and the attributes of non-car listings are only rendered as HTML. Removed listings return HTTP 410. Image sizes: 82 (~5 KB) … 85 XXL (~50–80 KB) … 87 (1280 px, re-encoded); without the `rule` query the image host returns the original upload (byte-identical to sizes 88+), which the archive stores by default.

## Decisions

- **Separate archive tables keyed by `(marketplace, item_id)`**, not by search, so archived listings survive search deletion and are shared when several searches find the same listing. Search listings link by item id; no columns are added to existing tables.
- **Parsing**: `__CONFIG__` via `json.JSONDecoder.raw_decode`; description and rendered attributes via `html.parser`. The description is reduced to an allowlist (`br p strong b em i u ul ol li`, no attributes), script/style content dropped, text escaped; the frontend renders it with `dangerouslySetInnerHTML`. A plain-text copy is kept for search and diffs.
- **Versions**: a SHA-256 over title, price, description, attributes, seller, highlights, reserved flag and photo keys (statistics excluded). A new version row only when the hash changes; the API computes field changes, a line diff of the description and photo additions/removals between consecutive versions.
- **Photos**: keyed by Marktplaats `mediaId`; downloaded once, stored as `<dir>/marktplaats/<item id>/<sha256>.jpg` (atomic write), never deleted on re-fetch; photos missing from the gallery get `removed_at`. Only `https://images.marktplaats.com` is fetched, max 10 MB. Served by `GET /archive/images/{id}` (no owner header on `<img>` requests; SnipeBot is single-owner behind Basic auth).
- **Queue**: `next_fetch_at` on the item. New listings, price/title changes in search results, reappearance and disappearance from a complete result set set it to now; success sets it to +7 days (+1 hour when photos failed). Per-item failures back off (retry settings) and stop after 5 until the weekly refresh. A block (403/429) pauses the whole archive with exponential backoff (in-process state of the worker).
- **Throttling**: 3 s between listings, 0.2 s between photos, a 45 s budget per worker tick (worker interval 60 s), so price checks and search checks keep their cadence.
- **Backfill**: each tick creates items for search listings without one, so listings recorded before this change (or while the archive was disabled) are archived too.

- **Alert price ceiling**: `marketplace_searches.alert_max_price` (nullable). New listings and price drops alert only when the price is at or below it; listings without a price and searches without a ceiling never alert. Recording and archiving are unaffected. Changing the ceiling does not re-baseline. The column is added by `init_db` (SQLite `ALTER TABLE`) and by Alembic `20261124_0007`.

## Risks

- Disk usage on 503-web (no limit chosen): usage is shown on the archive page; the host disk is monitored by the NOC.
- Marktplaats may start challenging the extra requests (AWS WAF present). Throttle and global backoff limit the impact; searches and alerts are unaffected because they run separately.
- Seller details include names of private sellers (owner's choice); data stays on the owner's server.
