## 1. Marktplaats adapter

- [x] 1.1 Validate and split pasted URLs; resolve the path through the page's embedded search request.
- [x] 1.2 Parse the `#` fragment with the Marktplaats client rules; report unknown keys.
- [x] 1.3 Build search-endpoint parameters (`l2CategoryIds[]`, ranges, distance, newest first, 100 per page).
- [x] 1.4 Parse listings (id, title, price, photo, attributes, place, distance, seller) and describe filters from facets.
- [x] 1.5 Seller filter via the `advertiser` facet.

## 2. Domain, persistence and worker

- [x] 2.1 Tables for searches, listings, price points and alert events (+ Alembic revision).
- [x] 2.2 Baseline, id-watermark new detection, exclude keywords, price drops, gone marking.
- [x] 2.3 Telegram alerts with photo, dedup, per-check cap, backoff on errors.
- [x] 2.4 Run due searches from the worker loop every ~10 minutes with jitter.

## 3. API and UI

- [x] 3.1 `/searches` routes: preview, create, list, detail, patch, delete, check-now, listings.
- [x] 3.2 "Marktplaats" menu section with preview-then-save form, search table and listing table.

## 4. Verification

- [x] 4.1 Backend tests for adapter parsing, detection rules, alerts, failures and API.
- [x] 4.2 Frontend tests for preview/save flow and listing view.
- [x] 4.3 Live check against marktplaats.nl with Telegram disabled (counts match the website).
- [ ] 4.4 Production check on 503-web with one real search and Telegram enabled.
