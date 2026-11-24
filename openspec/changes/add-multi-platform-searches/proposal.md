## Why

Saved searches only watch Marktplaats and are defined by a pasted Marktplaats URL. Many cars, especially from dealers, are offered on other platforms too. The owner wants one search per car type that covers several platforms, with SnipeBot's own filters, and wants new platforms added one at a time. AutoTrack.nl is the first.

## What Changes

- Searches are defined by SnipeBot's own filters: make and model (from lists merged over the platforms), year, price, mileage, minimum range and battery capacity, seller, exclude words and the alert price ceiling. Pasting a URL is no longer offered.
- A search covers one or more platforms; each platform is a source with its own query and check state (baseline, schedule, errors).
- Each platform is an adapter (`PlatformAdapter`): makes/models, filters → platform query, search. Filters a platform cannot apply are checked by SnipeBot afterwards; listings that do not state the value are kept and marked unknown.
- Overview, cheapest listing, listing table and Telegram alerts show the platform when a search covers several.
- Existing URL-based searches become a single Marktplaats source with their query and state, and can be switched to filters without a new baseline when the filters produce the same query.
- AutoTrack adapter: search across all result pages (newest first), listings archived like Marktplaats listings, duplicates across platforms marked by license plate.
- AutoScout24.nl adapter on the same code (NL, BE and DE, private sellers included). It includes all AutoTrack listings under the same ids and replaces AutoTrack in the owner's searches without losing history.

## Capabilities

### New Capabilities
- `multi-platform-searches`: Searches with own filters over several platforms.

### Modified Capabilities
- `marketplace-search-alerts`: check state moves to per-platform sources; alert titles name the platform for multi-platform searches.
- `marketplace-listing-archive`: archives listings of every platform with an archive adapter.

## Impact

- New table `marketplace_search_sources`; new columns `marketplace_searches.filters_json`, `marketplace_listings.marketplace`, `marketplace_listings.unverified_filters_json` (runtime migration in `init_db`; Alembic `20261125_0008`, which copies existing searches into sources).
- API: `/searches/platforms`, `/searches/makes`, `/searches/models`; preview/create/update take `filters` and `platforms` instead of `url`.
- AutoTrack's robots.txt disallows crawlers on its search pages; the owner accepted this for personal, low-rate use (same cadence as Marktplaats, pauses between pages, backoff when blocked).
