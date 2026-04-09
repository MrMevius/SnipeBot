# Title
Watchlist management fase 3: owner-scope auth, observability, reliability hardening en health dashboard

## Context
Na fase 1/2 ontbreekt nog production-hardening: data-isolatie per gebruiker, operationeel inzicht, betrouwbaardere check scheduling bij herhaalde fouten en request protection tegen misbruikpieken.

## Goals / Non-goals
### Goals
1. Introduceer owner-scoped request identiteit via API dependency, zodat watchlist data per owner gescheiden is.
2. Voeg metrics/observability toe voor API-gebruik en check-resultaten.
3. Voeg reliability hardening toe voor herhaalde check failures (retry backoff + dead-letter marker op itemniveau).
4. Voeg eenvoudige rate limiting toe voor write-heavy endpoints.
5. Voeg watchlist health dashboard endpoint toe met operationele signalen.

### Non-goals
1. Geen volledige OAuth/JWT loginflow.
2. Geen distributed queue/DLQ infrastructuur buiten bestaande DB modellen.
3. Geen externe metrics backend (Prometheus push/grafana wiring) in deze fase.

## Proposed approach
1. Voeg `RequestIdentity` dependency toe die owner-id leest uit `X-Owner-Id` header (met veilige fallback).
2. Vervang hardcoded `owner_id="local"` in watchlist API door identity owner.
3. Voeg in-memory metrics registry toe met counters voor API calls, rate-limit rejections en check outcomes.
4. Breid `WatchItem` uit met reliability velden (`consecutive_failure_count`, `dead_lettered_at`, `dead_letter_reason`) en pas scheduler check flow aan.
5. Voeg `GET /watchlist/health` endpoint toe met samenvatting (stale/error/dead-letter counts).
6. Voeg lightweight rate limiter dependency toe op bulk/import/write routes.

## Implementation steps (ordered)
1. Activeer deze spec als enige bron voor fase 3 wijzigingen.
2. Backend auth/identity:
   - nieuwe dependency module voor owner-resolutie,
   - watchlist/settings endpoints owner-aware maken waar van toepassing.
3. Backend observability:
   - metrics module + increments in API en price checks,
   - metrics endpoint op health router.
4. Backend reliability:
   - model + db upgrade voor dead-letter/failure velden,
   - backoff/dead-letter gedrag in price check flow.
5. Backend health dashboard:
   - `GET /watchlist/health` met owner-scoped aggregaties.
6. Backend rate-limit:
   - dependency toepassen op gevoelige write endpoints.
7. Frontend/client:
   - owner-id header support in API client,
   - eenvoudige health dashboard view in App.
8. Tests + verificatie + spec evidence.

## Acceptance criteria (measurable)
1. Watchlist API gebruikt request owner-id i.p.v. hardcoded owner, en data is owner-gescheiden.
2. `GET /watchlist/health` geeft minimaal counts voor total/active/archived/stale/error/dead-lettered items.
3. Metrics endpoint geeft counters voor API requests, rate-limit hits en check outcomes.
4. Bij herhaalde check failures wordt retry interval verhoogd en item kan dead-lettered raken na drempel.
5. Rate limiting blokkeert excessieve write-verzoeken met duidelijke HTTP foutstatus.
6. Frontend kan owner-id meesturen en health dashboard tonen.
7. Relevante backend/frontend tests slagen of blokkades staan onder verification evidence.

## Testing plan
Backend:
```bash
SNIPEBOT_DB_URL="sqlite:////home/mevius/snipebot/.tmp/test-suite.db" /home/mevius/snipebot/.venv/bin/pytest backend/tests/test_watchlist.py -q
```

Frontend:
```bash
PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run test -- --no-cache
PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run build
```

## Risk + rollback plan
### Risks
1. Owner-scoping kan regressies geven in bestaande data zichtbaarheidsflows.
2. Rate limiter in-memory is process-local en niet cluster-breed consistent.
3. Dead-letter logic kan te agressief items stilzetten als thresholds te laag staan.

### Mitigations
1. Backward-compatible fallback owner-id en expliciete tests voor owner isolatie.
2. Conservatieve limiter defaults, alleen op write endpoints.
3. Redelijke default threshold + heldere health signalering.

### Rollback
1. Revert commit(s) van fase 3.
2. Schakel limiter/dead-letter checks conditioneel uit via config defaults.
3. Herstel owner fallback naar single-tenant gedrag.

## Notes / links
- Backend API: `backend/src/snipebot/api/watchlist.py`
- Backend checks: `backend/src/snipebot/domain/price_checks.py`
- Backend models: `backend/src/snipebot/persistence/models.py`
- Frontend app: `frontend/src/App.tsx`

## Current status
Completed

## What changed
- Owner-scoped identity toegevoegd:
  - nieuwe dependency `backend/src/snipebot/api/deps.py` met `RequestIdentity` via `X-Owner-Id` header + validatie,
  - watchlist API gebruikt nu owner uit request i.p.v. hardcoded `owner_id="local"`.
- Rate limiting toegevoegd op write-heavy watchlist endpoints:
  - nieuwe in-memory limiter in `backend/src/snipebot/core/rate_limit.py`,
  - limiter toegepast op create/update/bulk/import/archive/restore/check-now/tag-writes,
  - 429 responses met `Retry-After`.
- Observability toegevoegd:
  - in-memory metrics registry in `backend/src/snipebot/core/metrics.py`,
  - counters toegevoegd in watchlist API en price check flow,
  - nieuw endpoint `GET /health/metrics` in `backend/src/snipebot/api/health.py`.
- Reliability hardening in checks:
  - `WatchItem` uitgebreid met `consecutive_failure_count`, `dead_lettered_at`, `dead_letter_reason` in `backend/src/snipebot/persistence/models.py`,
  - SQLite legacy column upgrades in `backend/src/snipebot/persistence/db.py`,
  - `backend/src/snipebot/domain/price_checks.py` gebruikt exponential backoff + dead-letter threshold,
  - dead-lettered items worden uitgesloten als due work items,
  - succesvolle checks resetten failure/dead-letter status.
- Watchlist health dashboard backend:
  - service `get_watchlist_health_summary(...)` in `backend/src/snipebot/domain/services.py`,
  - nieuw endpoint `GET /watchlist/health` in `backend/src/snipebot/api/watchlist.py`.
- Frontend owner + health:
  - API client gebruikt nu owner header centraal via `apiFetch(...)` + `getOwnerId/setOwnerId` in `frontend/src/api/client.ts`,
  - `fetchWatchlistHealth()` toegevoegd,
  - `frontend/src/App.tsx` uitgebreid met Owner & Health panel en owner-switching.
- Tests uitgebreid:
  - owner isolation test,
  - watchlist health + metrics endpoint test,
  - write rate-limit test,
  - dead-letter bij herhaalde failures test,
  - frontend tests bijgewerkt voor nieuwe `/watchlist/health` call.

## How to verify
1. Backend tests:
   - `SNIPEBOT_DB_URL="sqlite:////home/mevius/snipebot/.tmp/test-suite.db" /home/mevius/snipebot/.venv/bin/pytest backend/tests/test_watchlist.py -q`
2. Frontend tests:
   - `PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run test -- --no-cache`
3. Frontend build:
   - `PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run build`
   - als host-permissie op `frontend/dist` blokkeert:
     - `PATH="/home/mevius/snipebot/.tools/node/bin:/home/mevius/snipebot/frontend/node_modules/.bin:$PATH" vite build --outDir dist-local --emptyOutDir false`

## Verification evidence
- Backend tests uitgevoerd:
  - `SNIPEBOT_DB_URL="sqlite:////home/mevius/snipebot/.tmp/test-suite.db" /home/mevius/snipebot/.venv/bin/pytest backend/tests/test_watchlist.py -q`
  - resultaat: `20 passed, 7 warnings`.
- Frontend tests uitgevoerd:
  - `PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run test -- --no-cache`
  - resultaat: `6 passed`.
- Frontend standaard build geprobeerd:
  - `PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run build`
  - resultaat: gefaald door host-permissie op bestaande `frontend/dist/assets` (`EACCES: permission denied, rmdir ...`).
- Frontend build succesvol geverifieerd via alternatieve output map:
  - `PATH="/home/mevius/snipebot/.tools/node/bin:/home/mevius/snipebot/frontend/node_modules/.bin:$PATH" vite build --outDir dist-local --emptyOutDir false`
  - resultaat: `✓ built`.
