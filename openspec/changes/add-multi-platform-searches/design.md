## Context

Searches were a single Marktplaats query resolved from a pasted URL, with the check state on the search row. Platforms differ in taxonomy (Marktplaats: l2 category per make and a `model` attribute; AutoTrack: numeric make/model ids) and in which filters they support.

## Decisions

- **Own filters, platform queries stored per source.** The filters are stored on the search; each source stores the query its adapter built. Checks run the stored query, so a platform taxonomy change does not alter a running search until it is edited.
- **Make/model matched by normalized name** (lowercase, letters and digits only) across platforms. A model only one platform knows is offered for that platform only.
- **Post-filters.** An adapter returns the filter keys it cannot apply. SnipeBot checks them against normalized `Listing.specs` (year, mileage, range km, battery kWh). Unknown values keep the listing and mark it, as chosen by the owner.
- **No new baseline without a real change.** Editing compares the rebuilt query order-insensitively with the stored one; only changed or new sources record silently again. This lets the existing searches switch to filters without losing their baseline or Marktplaats id watermark.
- **Legacy columns stay** on `marketplace_searches` (unused) so a rollback to the previous image keeps working on the same database.

## Risks

- AutoTrack disallows crawling its search pages in robots.txt and may block the server IP. Mitigation: low rate, newest-first sorting, backoff on 403/429; other platforms are unaffected because sources fail independently.
