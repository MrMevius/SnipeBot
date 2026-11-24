## 1. Adapter

- [x] 1.1 Parse listing pages: `__CONFIG__` data, car attribute groups, rendered attributes, sanitized description, gallery, seller, statistics.
- [x] 1.2 Map HTTP 410 to `gone`; image download restricted to the Marktplaats image host.

## 2. Domain, persistence and worker

- [x] 2.1 Tables for items, versions, photos and prices (+ Alembic revision `20261124_0006`).
- [x] 2.2 Feed the archive from search checks (new listings, price/title changes, reappearance, disappearance) and backfill existing listings.
- [x] 2.3 Throttled fetch queue with versioning, photo storage, gone detection, per-item backoff and global block backoff.

## 3. API and UI

- [x] 3.1 `/archive` routes: list (search, filters, sort, pagination, usage), detail with versions, photo files, refresh, delete; `archive_id` on search listings.
- [x] 3.2 Archive overview and listing page (gallery, description, attributes, seller, price chart, versions); search listings link to the archive page.

## 4. Alert price ceiling

- [x] 4.1 `alert_max_price` per search (create, edit, overview); alerts for new listings and drops only at or below it; none without a ceiling.

## 5. Verification

- [x] 5.1 Backend tests for parsing, sanitizing, worker, versions, gone/revive, backoff, throttling, backfill and API.
- [x] 5.2 Frontend tests for overview and listing page.
- [x] 5.3 Live check against marktplaats.nl with a temporary database (10 listings, 256 photos, stable re-fetch without new versions).
- [ ] 5.4 Production check on 503-web: backfill of existing listings and photo serving through the frontend proxy.
