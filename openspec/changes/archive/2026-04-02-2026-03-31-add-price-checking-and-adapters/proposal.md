## Why

SnipeBot can store watched items but cannot run scheduled checks, parse product pages, or persist historical pricing. This change adds the smallest viable single-instance price-checking pipeline with adapter-per-site behavior and robust failure handling.

## What Changes

- Add scheduled worker-driven price checks for active watched items.
- Introduce a stable adapter interface with site-specific adapters for HEMA, Amazon.nl, and AliExpress.
- Implement standard adapter flow: HTTP fetch + HTML parse, with optional adapter-scoped Playwright fallback.
- Persist check outcomes in a `price_checks` history table.
- Keep `watch_items` latest snapshot fields updated: `last_checked_at`, `last_status`, and `current_price`.
- Ensure worker cycle continues when one adapter/item fails, with clear structured logging.

## Capabilities

### New Capabilities
- `scheduled-price-checking`: Run periodic checks and store results.

### Modified Capabilities
- `watchlist-management`: Extend watched item status/snapshot and list response fields.

## Impact

- Backend persistence schema updates (`watch_items` + new `price_checks`).
- New adapter contract/orchestration and three initial site adapters.
- Worker scheduler now processes due watch items, records outcomes, and reschedules.
