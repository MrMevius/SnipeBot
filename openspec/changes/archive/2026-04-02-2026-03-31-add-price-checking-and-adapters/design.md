## Title

Add pragmatic scheduled price checking and site adapters.

## Context

Current backend supports watchlist CRUD and site-key detection, but does not perform scheduled checks or parsing. The deployment target is a single self-hosted Docker Compose instance, so the design must avoid distributed components and keep operational complexity low.

## Goals / Non-goals

**Goals**
- Every active watched item can be checked by the worker.
- Stable adapter interface returning normalized structured data:
  - `title`
  - `current_price`
  - `currency`
  - `availability`
  - `parser_metadata` (or `raw_source_hint`)
- Adapter-per-site implementations for `hema`, `amazon_nl`, and `aliexpress`.
- Standard adapter flow is HTTP fetch + HTML parse.
- Optional Playwright fallback only for adapters that enable fallback.
- Append history entries in `price_checks`.
- Track latest snapshot on `watch_items`: `last_checked_at`, `last_status`, `current_price`.
- Structured logs clearly show adapter failures and reasons.
- One failed item/adapter must not stop the polling cycle.

**Non-goals**
- Seller-to-seller price comparison.
- Search result scraping.
- Auth/login-protected pages.
- Advanced anti-bot bypass beyond pragmatic fallback attempt.
- Queues or distributed architecture (Kafka, Celery, Redis, etc.).

## Proposed approach

1. **Scheduler/worker (single-instance)**
   - Keep one worker loop process.
   - On each tick, fetch due active items (`next_check_at <= now`) in bounded batches.
   - Process each item independently with exception isolation.
   - Commit per item so partial failures do not roll back successful checks.

2. **Adapter interface + orchestration**
   - Registry by `site_key`.
   - Shared result contracts for success/failure and normalized parsed payload.
   - Per-adapter fallback capability flag.

3. **Fetch/parse flow**
   - HTTP fetch first.
   - Parse HTML using adapter parser.
   - If parse fails and fallback enabled for that adapter: one Playwright attempt, then parse again.

4. **Persistence model**
   - `watch_items` snapshot + scheduling metadata.
   - New `price_checks` append-only rows for each successful check (and failures in v1 for observability).

5. **Failure posture**
   - `fetch_error` and `parse_error` are first-class statuses.
   - Maintain last known good `current_price` on failures.
   - Structured logs include adapter key, watch item id, error kind, and fallback usage.

## Implementation steps (ordered)

1. Extend persistence schema (`watch_items`, new `price_checks`).
2. Introduce adapter contracts and common parser result models.
3. Add initial site adapters (HEMA, Amazon.nl, AliExpress).
4. Implement price-check orchestration service with optional fallback.
5. Wire worker scheduler to execute due checks and reschedule.
6. Update API response models for new watch item fields.
7. Add/extend backend tests for worker, adapters, and persistence behavior.
8. Document configuration and verification evidence.

## Acceptance criteria

1. Worker checks every due active watched item in each cycle.
2. Each adapter returns normalized structured fields (`title`, `current_price`, `currency`, `availability`, `parser_metadata`).
3. `price_checks` history table persists check outcomes.
4. `watch_items` is updated with `last_checked_at`, `last_status`, `current_price` snapshot semantics.
5. HTTP parse failure triggers Playwright fallback only when configured for that adapter.
6. One failed adapter/item does not stop the full polling cycle.
7. Logs clearly identify which adapter failed and why.

## Testing plan

- Unit tests for adapter host matching and parse extraction.
- Service tests for check result persistence and snapshot updates.
- Worker tests to ensure cycle continues on per-item failure.
- API tests confirm watchlist payload includes new fields.
- Run `pytest backend/tests -q`.

## Risk + rollback plan

- Risk: parser fragility due site markup changes.
  - Mitigation: explicit parse error statuses, fallback path, and structured metadata.
- Risk: scheduler overload with too many due items.
  - Mitigation: bounded batch size and configurable interval.
- Rollback: revert change directory and code deltas; schema remains additive with nullable fields and safe defaults.

## Notes / links

- Keep implementation intentionally single-instance and SQLite-friendly.

## Current status

Implemented (runtime verification partially blocked by missing Python dependencies in this environment).

## What changed

- Implemented worker-driven due-item price checking with per-item isolation and structured success/failure logging.
- Added adapter architecture with normalized result payload and concrete adapters for HEMA, Amazon.nl, and AliExpress.
- Added optional Playwright fallback path after parse failure, gated by adapter capability + configuration.
- Added `price_checks` history persistence model and extended watched item snapshot/scheduling fields.
- Updated watchlist API and frontend contracts to expose `current_price`, `last_checked_at`, and `last_status`.
- Added backend tests for adapter parsing/fallback and worker failure isolation behavior.

## How to verify

1. `python3 -m pip install -e "./backend[dev]"`
2. `pytest backend/tests -q`

## Verification evidence

- `pytest backend/tests -q` failed in this environment due to missing dependencies (`fastapi`, `sqlalchemy`, `pydantic_settings`).
- `python3 -m compileall backend/src backend/tests` succeeded.
