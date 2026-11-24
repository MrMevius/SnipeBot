## Why

SnipeBot only tracks the price of individual product pages. The owner also wants to watch Marktplaats.nl for a specific car (or any other item) and get a Telegram message as soon as a matching listing appears, instead of refreshing saved searches by hand.

## What Changes

- Add saved marketplace searches: the user pastes a Marktplaats search results URL (filters set on marktplaats.nl), names it, optionally adds exclude keywords and a seller filter (all / private / business).
- Resolve the pasted URL into a search request (path via the page's embedded search request, `#` fragment parsed with the Marktplaats web-client rules) and show a preview with the understood filters and result count before saving.
- Check active searches every ~10 minutes (with jitter) in the existing worker; record the first result set silently, then alert via Telegram on genuinely new listings and on price drops of known listings.
- Telegram alerts include the main photo (`sendPhoto`, text fallback), title, price, year/mileage/fuel/transmission, place/distance, seller type, search name and link.
- Add a "Marktplaats" section in the UI: manage searches (create with preview, pause/resume, check now, delete, edit name/keywords/seller) and view recorded listings per search with new/gone markers and price history.

## Capabilities

### New Capabilities
- `marketplace-search-alerts`: Saved Marktplaats searches with new-listing and price-drop alerts.

### Modified Capabilities
- None. Watchlist behaviour is unchanged; the Telegram notifier gains optional photo support.

## Impact

- New tables `marketplace_searches`, `marketplace_listings`, `marketplace_listing_prices`, `marketplace_alert_events` (created by `init_db`; Alembic revision `20261123_0005`). Existing tables are untouched.
- New API routes under `/searches`.
- Worker loop also runs due marketplace searches; new settings `SNIPEBOT_MARKETPLACE_CHECK_INTERVAL_SECONDS` (600) and `SNIPEBOT_MARKETPLACE_CHECK_JITTER_SECONDS` (60).
- Outbound requests to `www.marktplaats.nl` (one search request per active search per interval).
