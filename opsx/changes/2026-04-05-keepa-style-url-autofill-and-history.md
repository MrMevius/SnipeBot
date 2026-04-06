# Title
Add URL auto-fill and Keepa-style baseline price history

## Context
The current watchlist flow requires manual form entry and only shows current snapshot fields in the overview. Users want a smoother flow where pasting a product URL can auto-populate product details, plus a basic Keepa-like experience with visible price history insights.

The backend already has site adapters, URL normalization, and persisted `price_checks`, which provides the foundation for a scoped v1 implementation.

## Goals / Non-goals
### Goals
1. Add a backend URL preview endpoint that fetches product metadata for supported sites.
2. Auto-fill watchlist form fields in frontend after URL paste (with safe overwrite rules).
3. Add backend watch-item history endpoint exposing a compact time series and summary stats.
4. Show Keepa-style baseline insights in the frontend (latest/lowest/highest and a small trend chart).
5. Add tests for backend endpoints and frontend URL auto-fill/history rendering paths.

### Non-goals
1. Full Keepa feature parity (buy box, offer count, advanced filters, alerts dashboard).
2. Browser extension integrations.
3. Multi-user analytics or portfolio-wide reporting.
4. New external scraping infrastructure beyond existing adapter flow.

## Proposed approach
1. Extend watchlist API with:
   - `GET /watchlist/preview?url=...`
   - `GET /watchlist/{item_id}/history?days=30`
2. Reuse existing domain/services normalization and adapters to resolve preview payload.
3. Add domain service helper for querying `price_checks` and summarizing trend metrics.
4. Update frontend API client and `App` UI to:
   - debounce preview lookup from URL field,
   - auto-populate label only when user has not manually edited it,
   - show per-item history insights and mini chart.
5. Add/extend backend and frontend tests for the new behavior.

## Implementation steps (ordered)
1. Add preview and history response models + routes in `backend/src/snipebot/api/watchlist.py`.
2. Add history query/summarization logic in `backend/src/snipebot/domain/services.py`.
3. Extend frontend API client with preview/history calls and typed payloads.
4. Implement URL paste auto-fill and Keepa-style baseline insights in `frontend/src/App.tsx`.
5. Add styles for preview state and history mini-chart in `frontend/src/styles.css`.
6. Add/adjust tests in `backend/tests/test_watchlist.py` and `frontend/src/App.test.tsx`.

## Acceptance criteria (measurable)
1. Calling `GET /watchlist/preview?url=<supported-url>` returns normalized URL, site key, title, current price, currency, and availability.
2. In frontend, entering a valid URL triggers preview fetch and auto-fills label when the label has not been manually edited.
3. Calling `GET /watchlist/{item_id}/history` returns chronological price series and summary fields (`latest_price`, `lowest_price`, `highest_price`, `checks_count`).
4. Watchlist UI shows Keepa-style baseline insights (latest/lowest/highest) and a mini trend chart for items with history data.
5. Existing watchlist create/update behavior remains functional.

## Testing plan (canonical commands or approach)
Backend:
```bash
python3 -m pip install -e "./backend[dev]"
pytest backend/tests -q
```

Frontend:
```bash
cd frontend
npm install
npm run test
```

## Risk + rollback plan
### Risks
1. Preview endpoint may fail frequently for blocked/adaptive pages.
2. Added frontend requests may create noisy UX if debounce/state handling is incorrect.
3. History queries can become heavy if unbounded.

### Mitigations
1. Return explicit parse/fetch errors and keep graceful fallback UX.
2. Debounce preview and only request for valid HTTP(S) URLs.
3. Bound history window and row count.

### Rollback
1. Revert this change set.
2. Keep existing watchlist upsert flow untouched as fallback path.
3. Disable frontend preview usage while retaining backend endpoints if partial rollback needed.

## Notes / links
- Existing adapter seam: `backend/src/snipebot/adapters/sites/`
- Existing checks persistence: `backend/src/snipebot/persistence/models.py`
- Existing watchlist UI: `frontend/src/App.tsx`

## Current status
Completed (implementation done; runtime test execution in this shell remains partially blocked by missing host dependencies)

## What changed
- Added `GET /watchlist/preview?url=...` endpoint in `backend/src/snipebot/api/watchlist.py`:
  - normalizes URL,
  - detects adapter/site,
  - performs adapter preview check,
  - returns `normalized_url`, `site_key`, `title`, `current_price`, `currency`, `availability`, `suggested_label`.
- Added `GET /watchlist/{item_id}/history?days=...` endpoint in `backend/src/snipebot/api/watchlist.py` returning:
  - chronological `series` of successful price points,
  - summary metrics `checks_count`, `latest_price`, `lowest_price`, `highest_price`.
- Added domain history helper `get_watch_item_price_history(...)` in `backend/src/snipebot/domain/services.py` with bounded time window and max rows.
- Extended frontend API client (`frontend/src/api/client.ts`) with:
  - `previewWatchItemByUrl(...)`,
  - `fetchWatchItemHistory(...)`,
  - typed preview/history payloads.
- Updated `frontend/src/App.tsx` with:
  - debounced URL preview lookup,
  - safe auto-fill of `customLabel` only when user did not manually edit,
  - preview status/error UI,
  - per-item Keepa-style baseline insights (`L/Lo/Hi`) and mini SVG trend chart.
- Updated styles in `frontend/src/styles.css` for preview and insights/chart blocks.
- Expanded tests:
  - backend: `backend/tests/test_watchlist.py` with preview endpoint and history endpoint coverage,
  - frontend: `frontend/src/App.test.tsx` with history rendering + submit flow + URL auto-fill behavior.

## How to verify
1. Backend:
   - `python3 -m pip install -e "./backend[dev]"`
   - `pytest backend/tests -q`
2. Frontend:
   - `cd frontend`
   - `npm install`
   - `npm run test`
3. Optional backend syntax gate:
   - `python3 -m compileall backend/src backend/tests`
4. Manual functional check:
   - Open app, paste supported product URL in Add Product form,
   - verify preview appears and label auto-fills if untouched,
   - save item and verify insights/mini trend render in watchlist table.

## Verification evidence
- `pytest backend/tests/test_watchlist.py -q` failed during collection in this environment because `fastapi` is unavailable (`ModuleNotFoundError: No module named 'fastapi'`).
- `npm run test` (frontend) could not run in this environment because `npm` is unavailable (`/bin/bash: npm: command not found`).
- `python3 -m compileall backend/src backend/tests` succeeded after implementation changes.
- Re-ran `python3 -m compileall backend/src backend/tests` during close-out: succeeded.
- Re-ran `pytest backend/tests/test_watchlist.py -q` during close-out: failed with same missing dependency (`ModuleNotFoundError: No module named 'fastapi'`).
- Re-ran frontend tests command `npm --prefix frontend run test` during close-out: blocked because `npm` is unavailable in host shell (`/bin/bash: npm: command not found`).
