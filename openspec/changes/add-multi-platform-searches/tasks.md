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
- [ ] 3.5 Production: SR keeps unknown battery quietly, LR leaves out unknown range.
