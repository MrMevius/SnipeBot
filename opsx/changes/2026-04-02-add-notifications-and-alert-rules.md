# Title
Add alert rules, dedup persistence, and Telegram notifications

## Context
SnipeBot foundation currently does **not** include notifications or target-price alert logic (see `README.md` “Not included yet”). The repo already has placeholder seams for `backend/src/snipebot/notifications/` and worker scheduling, which makes this a good time to add a first end-to-end alerting slice.

This change defines a minimal but complete backend notification capability that:
- evaluates alert rules during worker cycles,
- prevents duplicate alert spam,
- stores sent alert history,
- dispatches Telegram notifications via a notifier interface that can support future channels.

## Goals / Non-goals
### Goals
1. Add backend domain logic to evaluate two alert kinds: `price_drop` and `target_reached`.
2. Add persistence for sent alert events to support explicit deduplication and delivery history.
3. Trigger notifications from worker execution using a pluggable notifier interface (initial channel: Telegram).
4. Keep alert message content concise and useful with product/site/pricing context.
5. Configure Telegram notifier entirely via environment variables.

### Non-goals
1. Email notifications.
2. Multiple users and per-user notification preferences.
3. Notification preferences UI and mobile push integrations.
4. Advanced rule engine (compound expressions, time windows).

## Proposed approach
1. **Domain layer**: Introduce deterministic alert evaluation for `price_drop` and `target_reached` based on previous successful price, new successful price, and target price.
2. **Persistence layer**: Add an `alert_events` table to persist each send attempt with kind, dedup key, pricing context, message text, and delivery outcome.
3. **Worker integration**: After successful price check persistence, evaluate alert intents and dispatch only when dedup conditions permit.
4. **Notifier seam**: Keep notifier implementation behind interface/protocol and add Telegram adapter as first concrete implementation.
5. **Observability**: Add structured logs around dedup suppression and delivery success/failure.

## Implementation steps (ordered)
1. Define alert intent contracts and evaluation logic in `backend/src/snipebot/domain/alerts.py`.
2. Add SQLAlchemy `alert_events` model for sent alert records and dedup history.
3. Integrate alert orchestration in worker price-check success path.
4. Extend notifier interface and add Telegram notifier implementation.
5. Add environment-driven notifier configuration in `backend/src/snipebot/core/config.py` and `.env.example`.
6. Add/extend backend tests for alert decision rules, dedup behavior, and Telegram notifier behavior.
7. Update docs with Telegram configuration variables.

## Acceptance criteria (measurable)
1. Successful check with lower price than previous successful check triggers a `price_drop` alert intent.
2. Successful check at/below target triggers a `target_reached` alert intent only when crossing from above target (or no previous successful price).
3. Re-running checks with unchanged price state does not resend duplicate alerts.
4. Sent alert records are persisted with kind, dedup key, message, and delivery status.
5. Alert messages include product label/title, site, old price, new price, target price when relevant, and URL.
6. Telegram notifier uses environment variables for configuration and remains behind notifier interface/protocol.

## Testing plan (canonical commands or approach)
Backend:
```bash
pip install -e "./backend[dev]"
pytest backend/tests -q
```

Frontend:
```bash
cd frontend
npm install
npm run test
```

Optional end-to-end smoke (local):
```bash
docker compose up --build
# verify /health then exercise alert endpoints with seeded/mock data
docker compose down
```

## Risk + rollback plan
### Risks
1. Duplicate notifications due to race conditions or insufficient idempotency keys.
2. Worker latency growth if alert evaluation is not bounded/paginated.
3. Schema changes may require careful migration handling for existing SQLite volumes.

### Mitigations
1. Enforce transaction boundaries and deterministic dedupe keys (item_id + rule_type + trigger_window).
2. Add bounded query limits and pagination.
3. Keep migration additive and backward-compatible where possible.

### Rollback
1. Feature-flag alert dispatch path (evaluate-only mode).
2. Revert deployment to prior image and disable worker dispatch.
3. If needed, retain new tables but stop writes; no destructive down-migration required for immediate rollback.

## Notes / links
- Project README foundation scope: notifications and target logic currently excluded.
- Relevant seams:
  - `backend/src/snipebot/scheduler/`
  - `backend/src/snipebot/notifications/`
  - `backend/src/snipebot/domain/`
  - `backend/src/snipebot/persistence/`

## Current status
Completed (core acceptance criteria implemented; full-suite runtime verification depends on backend deps in environment).

## What changed
- Added domain alert decision module for `price_drop` and `target_reached` with explicit transition semantics.
- Added `alert_events` persistence model to record sent alert attempts, dedup key, payload context, and delivery result.
- Integrated alert evaluation + dedup + notifier dispatch into successful worker price checks.
- Extended notifier interface to structured message/result contracts and added Telegram notifier + notifier factory/noop fallback.
- Added environment-driven notification configuration (`SNIPEBOT_NOTIFICATIONS_ENABLED`, `SNIPEBOT_TELEGRAM_ENABLED`, `SNIPEBOT_TELEGRAM_BOT_TOKEN`, `SNIPEBOT_TELEGRAM_CHAT_ID`).
- Added backend tests for alert decision rules, worker dedup behavior, and Telegram notifier response handling.
- Expanded tests to explicitly cover Telegram request payload generation (`chat_id`, `text`, and preview flag) and strengthened duplicate-suppression assertion by validating no new alert rows are created on unchanged follow-up checks.
- Updated documentation and `.env.example` with Telegram-related settings.

## How to verify
1. Install backend dependencies:
   - `python3 -m pip install -e "./backend[dev]"`
2. Run backend tests:
   - `pytest backend/tests -q`
3. Optional syntax validation:
   - `python3 -m compileall backend/src backend/tests`

## Verification evidence
- `pytest backend/tests -q` failed during collection because required packages are unavailable in this environment (`fastapi`, `sqlalchemy`, `pydantic_settings`).
- `python3 -m compileall backend/src backend/tests` succeeded after implementation changes.
- `pytest backend/tests/test_alert_rules.py backend/tests/test_telegram_notifier.py -q` succeeded (`6 passed`).
- Re-ran `python3 -m compileall backend/src backend/tests` after additional test updates: succeeded.

---
Status: completed  
Owner: (unassigned)  
Date: 2026-04-02
