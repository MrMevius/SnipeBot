## 1. Generic searches (PR A)

- [x] 1.1 `PlatformAdapter` interface, shared listing types, taxonomy cache; Marktplaats adapter builds queries from filters.
- [x] 1.2 Sources per platform, listing platform and unverified filters (+ Alembic `20261125_0008`, runtime migration of existing searches).
- [x] 1.3 Worker checks each source; post-filters; gone-marking per platform; platform in alerts.
- [x] 1.4 API for platforms, makes, models, preview/create/update with filters and platforms.
- [x] 1.5 Filter form with make/model lists and platform choice; per-platform status; platform column and unknown markers.
- [ ] 1.6 Production: convert the two existing searches to filters with an unchanged Marktplaats query.

## 2. AutoTrack (PR B)

- [ ] 2.1 AutoTrack adapter: makes/models, query from filters, all result pages, parsing, block detection.
- [ ] 2.2 Archive AutoTrack listings (details, original photos, versions).
- [ ] 2.3 Mark duplicates across platforms by license plate.
- [ ] 2.4 Production: add AutoTrack to both searches with a silent baseline.
