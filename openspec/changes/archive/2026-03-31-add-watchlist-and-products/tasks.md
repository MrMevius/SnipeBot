## 1. Backend watchlist model and contracts

- [x] 1.1 Add persistence model for watch items with required fields (`url`, `custom_label`, `target_price`, `site_key`, `active`) plus overview fields (`current_known_price`, `last_check_time`, `status`) and owner seam for future multi-user.
- [x] 1.2 Implement backend URL validation + normalization and site key detection.
- [x] 1.3 Implement watchlist API endpoints for upsert-by-URL (`POST /watchlist`) and list (`GET /watchlist`) with clean response contracts.
- [x] 1.4 Implement deactivation endpoint for watched items (`PATCH /watchlist/{id}` sets `active=false`).

## 2. Frontend watchlist UX

- [x] 2.1 Replace foundation shell with compact add form for URL, optional custom label, optional target price.
- [x] 2.2 Add watchlist overview page/table showing item label/url, site key, target price, current known price, last check time, status, and active flag.

## 3. Verification

- [x] 3.1 Add/extend backend tests for validation, upsert behavior, and listing.
- [x] 3.2 Add/extend frontend tests for add flow and watchlist rendering.
- [x] 3.3 Run verification commands and record results.
- [x] 3.4 Add/improve backend tests for URL validation, site detection mapping, and create/read/update/deactivate watched item flow.

## Current status

Implemented (runtime verification blocked by missing dependencies/tools in environment).

## What changed

- Added backend `WatchItem` SQLAlchemy model with fields for `url`, `custom_label`, `target_price`, `site_key`, `active`, plus `normalized_url`, owner seam (`owner_id`), and overview fields (`current_known_price`, `last_check_time`, `status`).
- Added URL normalization and site key detection (`hema`, `amazon_nl`, `aliexpress`, fallback `unknown`) in domain/adapter seam.
- Added watchlist API routes:
  - `POST /watchlist` for create-or-update (upsert by normalized URL)
  - `GET /watchlist` for watchlist overview data
  - `PATCH /watchlist/{id}/deactivate` to set an item inactive without deleting it
- Added backend tests for malformed URL rejection, create/list flow, and upsert-by-normalized-URL behavior.
- Added backend URL-normalization tests, backend site-key detection tests, and an integration test covering create/read/update/deactivate flow.
- Replaced frontend health shell with compact add form + plain watchlist overview table.
- Extended frontend API client contracts and added frontend tests for initial render and submit/refresh flow.

## How to verify

1. Ensure toolchain prerequisites are installed:
   - Python with `pip` available
   - Node.js + npm available
2. Install backend dependencies:
   - `python3 -m pip install -e "./backend[dev]"`
3. Run backend tests:
   - `pytest backend/tests -q`
4. Run frontend tests:
   - `cd frontend && npm run test`

## Verification evidence

- `pytest backend/tests -q` failed during test collection because dependencies are not installed in this environment (`ModuleNotFoundError: fastapi`, `ModuleNotFoundError: sqlalchemy`).
- `python3 -m pip install -e "./backend[dev]"` could not run because `pip` is unavailable (`No module named pip`).
- `npm run test` could not run because npm is unavailable in this environment (`npm: command not found`).
- Syntax validation passed for changed Python files via `python3 -m py_compile` (including new watchlist/deactivation and test modules).
