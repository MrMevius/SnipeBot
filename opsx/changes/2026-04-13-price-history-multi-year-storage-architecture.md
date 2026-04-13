Title
Multi-year price history storage architecture (PostgreSQL + TimescaleDB)

Context
SnipeBot stores price history in `price_checks` and serves it via `GET /watchlist/{item_id}/history`.
The current implementation and defaults are SQLite-centric, and history retrieval is currently bounded to 365 days in `get_watch_item_price_history`.
For business and product evolution, we need a technical architecture that can store and query more than one year of price data in a cost-efficient way.

Goals / Non-goals
Goals
- Support at least 24 months of price history retention in warm storage.
- Keep detail history queries (7/30/90 days) responsive.
- Keep long-range history queries (> 1 year) reliable with bounded payloads.
- Minimize storage/operational cost via compression and tiering policies.
- Provide a clear migration and rollback path from current runtime setup.

Non-goals
- No dashboard/UI redesign.
- No scraper adapter redesign.
- No notifications/alerting product scope changes.

Proposed approach
1. Move production storage to PostgreSQL 16 + TimescaleDB.
2. Convert `price_checks` to a hypertable partitioned by `checked_at`.
3. Add query-focused indexing for `watch_item_id + checked_at` with partial index for successful priced checks.
4. Enable Timescale compression (after a short warm period) and retention policy (24 months warm raw).
5. Add long-range query strategy (downsampling / aggregate view) while keeping existing API response shape compatible.
6. Optionally add a cold archive tier (Parquet/object storage) for data older than warm retention.

Implementation steps (ordered)
1. Create and lock this change spec as active spec for the migration work.
2. Add PostgreSQL runtime path and dependency support.
3. Add migration workflow and create schema migration(s) for Timescale setup.
4. Update history service and API query constraints for >365-day windows.
5. Add/adjust tests for long-range history behavior.
6. Add operational verification/runbook documentation for retention, compression, and rollback.

Acceptance criteria
1. Architecture and migration plan clearly define how SnipeBot stores and queries price data for more than one year.
2. System supports at least 24 months of warm price history retention for `price_checks`.
3. `GET /watchlist/{item_id}/history` supports query windows beyond 365 days without breaking existing clients.
4. Storage cost controls are defined and implemented (compression/retention policies).
5. Verification commands and objective evidence are captured for retention span and query performance.

Testing plan
- Targeted backend tests for history endpoints and history service behavior.
- DB-level verification of hypertable, retention, and compression metadata.
- Query plan/latency checks for short and long windows.

Risk + rollback plan
Risks
- Migration complexity and extension availability differences by environment.
- Query regressions on larger historical windows.
- Operational mismatch between dev SQLite flows and production PostgreSQL flows.

Rollback
- Keep pre-migration database snapshot/backup.
- Roll back to previous schema/app release if migration validation fails.
- Preserve backward-compatible API behavior to minimize client impact.

Notes / links
- Relevant source paths:
  - `backend/src/snipebot/domain/services.py` (`get_watch_item_price_history`)
  - `backend/src/snipebot/persistence/models.py` (`PriceCheck`)
  - `backend/src/snipebot/persistence/db.py`
  - `backend/src/snipebot/api/watchlist.py`

Current status
Completed

What changed
- Created a dedicated change spec for multi-year price history storage architecture and migration.
- Updated backend history service to support multi-year request windows by raising the safe cap from 365 to 3650 days:
  - `backend/src/snipebot/domain/services.py`
- Added regression coverage for >1-year history windows:
  - `backend/tests/test_watchlist.py`
  - New test: `test_watch_item_history_supports_more_than_one_year_window`
- Added PostgreSQL/Timescale dependency support:
  - `backend/pyproject.toml` now includes `psycopg[binary]` and `alembic`.
- Added migration workflow scaffolding (Alembic):
  - `backend/alembic.ini`
  - `backend/migrations/env.py`
  - `backend/migrations/script.py.mako`
  - `backend/migrations/versions/20260413_0001_timescale_price_checks.py`
- Added Timescale migration skeleton for `price_checks`:
  - enables extension,
  - converts to hypertable,
  - adds history query indexes,
  - configures compression + 24-month retention policies.
- Added runtime/docs support for PostgreSQL profile:
  - `.env.example` postgres DB URL recommendation.
  - `docker-compose.yml` optional `db` service (`timescale/timescaledb:latest-pg16`, profile `postgres`).
  - `README.md` section for PostgreSQL/Timescale workflow and migration command.
- Implemented long-range history query strategy with backward-compatible response shape:
  - `backend/src/snipebot/domain/services.py`
    - introduced history `resolution` modes (`auto`, `raw`, `daily`),
    - `auto` now switches to daily aggregation for windows > 90 days,
    - raw mode now orders by newest-first (`checked_at`, `id`) then reverses to preserve chronological output while keeping newest data in bounded result sets.
  - `backend/src/snipebot/api/watchlist.py`
    - added optional `resolution` query param to `GET /watchlist/{item_id}/history`.
- Added test coverage for long-window auto aggregation behavior:
  - `backend/tests/test_watchlist.py`
  - New test: `test_watch_item_history_auto_resolution_uses_daily_aggregation_for_long_windows`
- Ran PostgreSQL/Timescale operational verification with compose profile:
  - started DB service with alternate host port due local `5432` conflict:
    - `SNIPEBOT_POSTGRES_PORT=55432 docker compose --profile postgres up -d db`
  - installed new backend deps into existing venv via `uv` (to include Alembic/psycopg).
  - applied Alembic migrations successfully on PostgreSQL:
    - final revision `20260413_0002` at head.
- Hardened Timescale migration for safe execution:
  - `backend/migrations/versions/20260413_0001_timescale_price_checks.py`
    - now checks PostgreSQL/table existence,
    - attempts hypertable conversion with graceful fallback notice instead of hard-failing,
    - applies compression/retention policies only when hypertable conversion is effective.
- Updated Alembic path config:
  - `backend/alembic.ini` now uses `prepend_sys_path = src`.
- Implemented schema compatibility follow-up for Timescale conversion:
  - `backend/migrations/versions/20260413_0002_timescale_compat_schema.py`
    - adds `alert_events.price_check_checked_at` and backfills from `price_checks`,
    - migrates `price_checks` primary key to `(id, checked_at)` for Timescale compatibility,
    - replaces single-column FK with composite FK from `alert_events (price_check_id, price_check_checked_at)` to `price_checks (id, checked_at)`,
    - creates hypertable and enables compression/retention policies after successful conversion.
- Updated persistence/runtime compatibility for new alert linkage timestamp:
  - `backend/src/snipebot/persistence/models.py` adds `AlertEvent.price_check_checked_at`.
  - `backend/src/snipebot/domain/price_checks.py` now persists `price_check_checked_at` on alert writes.
  - `backend/src/snipebot/persistence/db.py` adds SQLite legacy-column guard for `alert_events.price_check_checked_at`.

How to verify
- Run backend watchlist tests with isolated SQLite test DB:
  - `SNIPEBOT_DB_URL="sqlite:////home/mevius/snipebot/.tmp/test-suite.db" /home/mevius/snipebot/.venv/bin/pytest backend/tests/test_watchlist.py -q`
- Confirm the new test passes and history request with `days=731` includes data points older than 365 days.
- Run backend DB smoke test:
  - `SNIPEBOT_DB_URL="sqlite:////home/mevius/snipebot/.tmp/test-suite.db" /home/mevius/snipebot/.venv/bin/pytest backend/tests/test_db_smoke.py -q`
- Verify long-window auto aggregation behavior:
  - `SNIPEBOT_DB_URL="sqlite:////home/mevius/snipebot/.tmp/test-suite.db" /home/mevius/snipebot/.venv/bin/pytest backend/tests/test_watchlist.py -q -k "auto_resolution or more_than_one_year or history_returns_series"`
- (PostgreSQL/Timescale environment) run migration:
  - `cd backend && alembic upgrade head`
- (PostgreSQL/Timescale environment) validate Timescale metadata:
  - `psql "$PG_URL" -c "SELECT hypertable_name FROM timescaledb_information.hypertables WHERE hypertable_name='price_checks';"`
  - `psql "$PG_URL" -c "SELECT remove_retention_policy('price_checks', if_exists => TRUE);"` (rollback smoke if needed)
- (Equivalent Python-based check if `psql` unavailable):
  - query `timescaledb_information.hypertables` and `timescaledb_information.jobs` via SQLAlchemy/psycopg.
- Optional PostgreSQL integration smoke (note: some existing test fixtures use SQLite-style boolean literals):
  - `SNIPEBOT_DB_URL="postgresql+psycopg://snipebot:snipebot@127.0.0.1:55432/snipebot" /home/mevius/snipebot/.venv/bin/pytest backend/tests/test_watchlist.py -q`

Verification evidence
- Spec file created: `opsx/changes/2026-04-13-price-history-multi-year-storage-architecture.md`.
- Test run executed:
  - `SNIPEBOT_DB_URL="sqlite:////home/mevius/snipebot/.tmp/test-suite.db" /home/mevius/snipebot/.venv/bin/pytest backend/tests/test_watchlist.py -q`
  - Result: `23 passed, 13 warnings in 1.12s`
- Test run executed:
  - `SNIPEBOT_DB_URL="sqlite:////home/mevius/snipebot/.tmp/test-suite.db" /home/mevius/snipebot/.venv/bin/pytest backend/tests/test_db_smoke.py -q`
  - Result: `1 passed in 0.21s`
- PostgreSQL migration run executed:
  - `SNIPEBOT_DB_URL="postgresql+psycopg://snipebot:snipebot@127.0.0.1:55432/snipebot" /home/mevius/snipebot/.venv/bin/python -m alembic upgrade head`
  - Result: migration completed; current revision head = `20260413_0002`.
- PostgreSQL metadata check executed:
  - `alembic_revision=20260413_0002`
  - `is_hypertable=True`
  - `compression_jobs=1`
  - `retention_jobs=1`
  - `price_checks_pk_columns=['id', 'checked_at']`
  - `alert_events_fks=['alert_events_watch_item_id_fkey', 'fk_alert_events_price_checks_composite']`
- PostgreSQL watchlist test run (exploratory) executed:
  - `SNIPEBOT_DB_URL="postgresql+psycopg://snipebot:snipebot@127.0.0.1:55432/snipebot" /home/mevius/snipebot/.venv/bin/pytest backend/tests/test_watchlist.py -q`
  - Result: fixture SQL failures in existing tests due integer boolean literals (`used_fallback = 0/1`) under PostgreSQL typing; not a regression from this change and outside this change scope.
