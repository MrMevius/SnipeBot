## Why

Saved Marktplaats searches link straight to marktplaats.nl. When a listing is removed or edited, its details and photos are lost. The owner wants every found listing kept locally as an archive and reference, independent of Marktplaats.

## What Changes

- Archive every listing a saved search records (including the silent first check): listing page details (title, price, description, labelled attributes, seller, statistics, highlights) and all photos as originally uploaded (no resizing).
- Fetch through a throttled background queue in the worker; back off globally when Marktplaats blocks requests.
- Re-fetch when price or title changes in the search results and weekly while online; store a new version only on content changes; keep photos that disappear from the listing (marked removed); mark listings gone on HTTP 410/404.
- Own listing page `/archive/<id>` (gallery, description, attributes, seller, statistics, price chart, version history with description diff); listings in a search link there. Telegram alerts keep linking to Marktplaats.
- Archive overview `/archive` across all searches with text search, search/status filters, sorting, pagination and storage usage.
- The archive is kept when a search is deleted; single listings can be deleted (rows and photo files).

## Capabilities

### New Capabilities
- `marketplace-listing-archive`: Local archive of Marktplaats listings with versions and photos.

### Modified Capabilities
- `marketplace-search-alerts`: search listing responses carry `archive_id`; checks feed the archive; Telegram alerts are limited by a per-search price ceiling (`alert_max_price`, empty = no alerts), new column added at runtime and in Alembic `20261124_0007`.

## Impact

- New tables `marketplace_items`, `marketplace_item_versions`, `marketplace_item_images`, `marketplace_item_prices` (created by `init_db`; Alembic revision `20261124_0006`). Existing tables are untouched; existing search listings are backfilled into the archive.
- Photo files under `SNIPEBOT_MARKETPLACE_ARCHIVE_DIR` (default `/data/archive`, SQLite volume). No size limit by choice; ~5–8 MB per car listing (original photos).
- Extra outbound requests: one listing page per new/changed listing and weekly per online listing, plus its photos from `images.marktplaats.com`.
- New API routes under `/archive`; new settings `SNIPEBOT_MARKETPLACE_ARCHIVE_*`.
