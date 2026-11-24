## 1. Generic searches (PR A)

- [x] 1.1 `PlatformAdapter` interface, shared listing types, taxonomy cache; Marktplaats adapter builds queries from filters.
- [x] 1.2 Sources per platform, listing platform and unverified filters (+ Alembic `20261125_0008`, runtime migration of existing searches).
- [x] 1.3 Worker checks each source; post-filters; gone-marking per platform; platform in alerts.
- [x] 1.4 API for platforms, makes, models, preview/create/update with filters and platforms.
- [x] 1.5 Filter form with make/model lists and platform choice; per-platform status; platform column and unknown markers.
- [x] 1.6 Production: convert the two existing searches to filters with an unchanged Marktplaats query.

## 2. AutoTrack (PR B)

- [x] 2.1 AutoTrack adapter: makes/models, query from filters, all result pages (newest first, de-duplicated), parsing, block detection.
- [x] 2.2 Archive AutoTrack listings (details, original photos, versions).
- [x] 2.3 Mark duplicates across platforms by license plate.
- [x] 2.4 Production: add AutoTrack to both searches with a silent baseline.

## 3. AutoScout24 (PR C)

- [x] 3.1 Shared adapter for the AutoScout24 group sites (`Scout24Site`): AutoTrack and AutoScout24.nl (NL, BE, DE; private sellers; country shown with the city).
- [x] 3.2 Same listing ids: switching AutoTrack → AutoScout24 moves search listings and archive items instead of recording them again.
- [x] 3.3 Production: replace AutoTrack by AutoScout24 in both searches.
- [x] 3.4 Per-search policy for listings without a post-filtered value: keep and alert, keep quietly, leave out (+ Alembic `20261125_0010`).
- [x] 3.5 Production: SR keeps unknown battery quietly, LR leaves out unknown range.

## 4. 2dehands (PR D)

- [x] 4.1 `MarktplaatsSite` for Marktplaats and 2dehands (search API, listing pages, seller links, image host); range and battery as post-filters on 2dehands.
- [x] 4.2 An ad on several platforms under one id is recorded once.

## 5. ViaBOVAG (PR F)

- [x] 5.1 ViaBOVAG adapter: React Server Components flight payload, make/model facets, all result pages, all other filters as post-filters.
- [x] 5.2 Archive ViaBOVAG listings (specification groups, dealer comments, BOVAG certainties, photos, license plate).

## 6. Kleinanzeigen (PR G)

- [x] 6.1 Kleinanzeigen adapter: Astro island props (result ads, make/model menus), year/price/mileage/seller in the URL, all result pages newest first, top ads skipped, range and battery as post-filters.
- [x] 6.2 Archive Kleinanzeigen listings (details, equipment, description, gallery photos, seller).
- Earlier finding revisited: the 403 was Python's HTTP client; curl with SnipeBot's own user agent gets the regular pages, and robots.txt allows `/s-autos/` and `/s-anzeige/`.
