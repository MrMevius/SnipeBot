## 1. Persistence and contracts

- [x] 1.1 Extend `watch_items` with scheduling/snapshot fields (`next_check_at`, `last_checked_at`, `last_status`, `current_price`, failure metadata) while preserving existing watchlist behavior.
- [x] 1.2 Add `price_checks` table to store per-check history with normalized result and failure metadata.

## 2. Adapter architecture

- [x] 2.1 Define stable adapter result contracts returning `title`, `current_price`, `currency`, `availability`, and `parser_metadata`.
- [x] 2.2 Implement adapters for HEMA, Amazon.nl, and AliExpress using HTTP fetch + HTML parse.
- [x] 2.3 Implement optional Playwright fallback path scoped per adapter and only attempted after HTTP parse failure.

## 3. Worker execution

- [x] 3.1 Implement worker check service that processes every due active watched item each cycle.
- [x] 3.2 Ensure one item/adapter failure does not break the polling cycle.
- [x] 3.3 Add clear structured logging for adapter failures and reasons.

## 4. API and tests

- [x] 4.1 Update watchlist API response fields to expose `last_checked_at`, `last_status`, and `current_price`.
- [x] 4.2 Add/extend tests for adapters, price-check persistence, and worker failure isolation.
- [x] 4.3 Run backend verification and record evidence.

## Current status

Implemented (runtime test execution blocked by missing backend dependencies in environment).

## What changed

- Extended backend persistence model: `watch_items` now tracks `current_price`, `last_checked_at`, `last_status`, scheduling fields (`next_check_at`) and failure metadata; added `price_checks` history table.
- Added stable adapter contracts and normalized parsed product data contract (`title`, `current_price`, `currency`, `availability`, `parser_metadata`).
- Implemented HEMA, Amazon.nl, and AliExpress adapters using HTTP fetch + HTML parse.
- Added optional adapter-scoped Playwright fallback path used only after parse failure when enabled by config.
- Implemented worker price-check execution service with due-item selection, per-item transaction boundary, failure isolation, and rescheduling.
- Added structured logs for check success/failure with adapter and error context.
- Updated watchlist API/frontend contracts to `current_price`, `last_checked_at`, `last_status` snapshot naming.
- Added backend tests for adapter normalized parsing, fallback behavior, and worker cycle isolation.
- Improved backend tests to cover parsing edge cases, price history persistence, and latest known price snapshot behavior across success/failure runs.

## How to verify

1. Install backend dependencies:
   - `python3 -m pip install -e "./backend[dev]"`
2. Run backend tests:
   - `pytest backend/tests -q`

## Verification evidence

- `pytest backend/tests -q` failed during collection because required packages are missing in this environment (`ModuleNotFoundError` for `fastapi`, `sqlalchemy`, `pydantic_settings`).
- `python3 -m compileall backend/src backend/tests` succeeded, confirming syntax validity for changed backend source and tests.
- Re-ran `python3 -m compileall backend/src backend/tests` after test improvements: succeeded.
