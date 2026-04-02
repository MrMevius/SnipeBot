## Why

SnipeBot currently has only a foundation shell and health endpoint, so users cannot save product URLs for tracking. This change introduces a minimal watchlist management slice that allows URL-based product tracking setup with clean API contracts and a plain functional UI.

## What Changes

- Add watchlist persistence and API endpoints for create-or-update and list operations.
- Add backend URL normalization and malformed URL validation.
- Detect and store `site_key` mapped to adapter names (`hema`, `amazon_nl`, `aliexpress`, fallback `unknown`).
- Add a compact frontend add form and watchlist overview page.
- Show `current_known_price`, `last_check_time`, and `status` in the overview using known stored values.

## Capabilities

### New Capabilities
- `watchlist-management`: Manage watched products by URL with optional label and target price.

### Modified Capabilities
- None.

## Impact

- Adds a new `watch_items` persistence model/table in backend SQLite.
- Adds new backend API routes under `/watchlist`.
- Replaces frontend foundation health-only shell with a simple watchlist workflow page.
