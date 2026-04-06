# Title
Watchlist management fase 1 (MVP): filters, bulk-acties, archiveren en paginatie

## Context
De huidige watchlist ondersteunt toevoegen/updaten en detailinteractie, maar beheer op grotere lijsten is beperkt. Gebruikers willen items gericht kunnen filteren/sorteren, meerdere items tegelijk beheren, en items archiveren zonder definitief verlies.

Deze change richt zich op fase 1 (MVP) uit het goedgekeurde plan.

## Goals / Non-goals
### Goals
1. Voeg server-side filteren, sorteren en paginatie toe aan `GET /watchlist`.
2. Voeg bulk-acties toe voor meerdere watch-items tegelijk.
3. Voeg archive/restore gedrag toe via soft archive.
4. Voeg frontend bediening toe voor filters, paginatie, selectie en bulk-acties.
5. Behoud compatibiliteit met bestaande watchlist/detail workflows.

### Non-goals
1. Geen auth/multi-user redesign (owner blijft `local`).
2. Geen import/export functionaliteit in deze fase.
3. Geen tags/folders in deze fase.
4. Geen geavanceerde alertregel-engine in deze fase.

## Proposed approach
1. Breid `WatchItem` uit met `archived_at`.
2. Maak query-helpers in domeinlaag voor gefilterde/pagineerde listing en bulk-mutaties.
3. Breid watchlist API uit met queryparameters en bulk/archive routes.
4. Breid frontend API-client en UI uit voor nieuwe managementflows.
5. Voeg regressie- en featuretests toe voor backend en frontend.

## Implementation steps (ordered)
1. Activeer deze spec als enige bron voor deze wijziging.
2. Backend persistence/model:
   - voeg `archived_at` toe aan `WatchItem`.
3. Backend services:
   - listing met filters/sort/limit/offset + `total`.
   - bulk mutate helper voor `pause|resume|archive|set_target`.
   - individuele archive/restore helpers.
4. Backend API:
   - breid `GET /watchlist` uit met queryparams en paginated response.
   - voeg `POST /watchlist/bulk` toe.
   - voeg `POST /watchlist/{item_id}/archive` en `/restore` toe.
5. Frontend API client:
   - types en calls voor paginated listing, bulk, archive, restore.
6. Frontend UI:
   - filter/sort controls en paginatieknoppen.
   - multi-select + bulk action bar.
   - archive/restore acties in itembeheer.
7. Tests:
   - backend tests voor listing/bulk/archive.
   - frontend tests voor bulk en filter/paginatie flows.
8. Verificatie uitvoeren en spec bijwerken.

## Acceptance criteria (measurable)
1. `GET /watchlist` accepteert en verwerkt queryparams: `active`, `site_key`, `has_target`, `q`, `sort`, `limit`, `offset`.
2. `GET /watchlist` response bevat naast `items` ook `total`, `limit` en `offset`.
3. `POST /watchlist/bulk` ondersteunt acties `pause`, `resume`, `archive`, `set_target` en rapporteert verwerkte items.
4. `POST /watchlist/{item_id}/archive` archiveert een item (standaard verborgen in lijst), en `/restore` maakt het item weer zichtbaar.
5. Frontend ondersteunt filteren/sorteren/paginatie en bulk-acties zonder page reload.
6. Bestaande create/update/detail/history/check-now paden blijven functioneel.
7. Relevante backend/frontend tests slagen, of blokkades staan expliciet onder `Verification evidence`.

## Testing plan (canonical commands or approach)
Backend:
```bash
SNIPEBOT_DB_URL="sqlite:////home/mevius/snipebot/.tmp/test-suite.db" /home/mevius/snipebot/.venv/bin/pytest backend/tests/test_watchlist.py -q
```

Frontend:
```bash
PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run test -- --no-cache
PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run build
```

Manual smoke:
1. Voeg meerdere items toe, filter op status/site/zoekterm.
2. Selecteer meerdere items en voer bulk pause/resume/archive uit.
3. Open archived filter en herstel een item.
4. Verifieer dat bestaande detailpagina en check-now nog werken.

## Risk + rollback plan
### Risks
1. Query-uitbreiding kan onverwachte impact hebben op bestaande watchlist consumers.
2. Bulk-mutaties kunnen foutgevoelig zijn bij deels ongeldige item-id sets.
3. Soft archive filtering kan items onbedoeld verbergen.

### Mitigations
1. Houd responseveld `items` in stand en voeg extra velden additief toe.
2. Valideer bulk-input strikt en retourneer duidelijke operation summary.
3. Voeg expliciete `archived` filteropties toe en test restore-flow.

### Rollback
1. Revert commit(s) van deze wijziging.
2. Disable nieuwe routes (bulk/archive/restore) indien nodig.
3. Keer terug naar basis watchlist listing zonder geavanceerde queryparams.

## Notes / links
- Backend API: `backend/src/snipebot/api/watchlist.py`
- Backend services: `backend/src/snipebot/domain/services.py`
- Backend models: `backend/src/snipebot/persistence/models.py`
- Frontend app: `frontend/src/App.tsx`
- Frontend client: `frontend/src/api/client.ts`

## Current status
Completed

## What changed
- Backend model/persistence:
  - `backend/src/snipebot/persistence/models.py`: `WatchItem.archived_at` toegevoegd (`DateTime`, nullable, indexed).
  - `backend/src/snipebot/persistence/db.py`: defensieve SQLite schema-upgrade toegevoegd voor legacy DB's (`ALTER TABLE watch_items ADD COLUMN archived_at DATETIME` als kolom ontbreekt).
- Backend services (`backend/src/snipebot/domain/services.py`):
  - `list_watch_items_paginated(...)` toegevoegd met support voor filters/sort/limit/offset + `total`.
  - `bulk_update_watch_items(...)` toegevoegd voor acties `pause|resume|archive|set_target`.
  - `archive_watch_item(...)` en `restore_watch_item(...)` toegevoegd.
  - `upsert_watch_item(...)` herstelt nu gearchiveerd item automatisch (`archived_at=None`) bij upsert op bestaande normalized URL.
- Backend API (`backend/src/snipebot/api/watchlist.py`):
  - `GET /watchlist` uitgebreid met queryparams:
    - `active`, `site_key`, `has_target`, `q`, `sort`, `limit`, `offset`
    - additief: `include_archived`, `archived_only`
  - `GET /watchlist` response uitgebreid met `total`, `limit`, `offset` naast `items`.
  - `POST /watchlist/bulk` toegevoegd.
  - `POST /watchlist/{item_id}/archive` en `POST /watchlist/{item_id}/restore` toegevoegd.
  - `WatchItemResponse` uitgebreid met `archived_at`.
- Frontend API client (`frontend/src/api/client.ts`):
  - `WatchlistQuery`, `BulkWatchItemPayload`, `BulkWatchItemResponse` types toegevoegd.
  - `fetchWatchlist(query)` uitgebreid met query-ondersteuning.
  - `bulkUpdateWatchItems(...)`, `archiveWatchItem(...)`, `restoreWatchItem(...)` toegevoegd.
  - `WatchItem` type uitgebreid met `archived_at`; `WatchlistResponse` met `total/limit/offset`.
- Frontend UI (`frontend/src/App.tsx`):
  - filter controls toegevoegd (search, active, has target, site key).
  - sortering + page size + vorige/volgende paginatie toegevoegd.
  - archive filters toegevoegd (`Include archived`, `Archived only`).
  - multi-select + bulk action bar toegevoegd voor `pause|resume|archive|set_target`.
  - individuele archive/restore knop toegevoegd per row.
  - feedbackmeldingen toegevoegd voor bulk en archive/restore acties.
- Tests:
  - `backend/tests/test_watchlist.py` uitgebreid met:
    - filter/paginatie test,
    - bulk archive + restore flow test.
  - `frontend/src/App.test.tsx` uitgebreid/gewijzigd:
    - aangepast voor paginated watchlist responses,
    - nieuwe bulk archive overview test.

## How to verify
1. Backend watchlist tests:
   - `SNIPEBOT_DB_URL="sqlite:////home/mevius/snipebot/.tmp/test-suite.db" /home/mevius/snipebot/.venv/bin/pytest backend/tests/test_watchlist.py -q`
2. Frontend tests:
   - `PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run test -- --no-cache`
3. Frontend build:
   - `PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run build`
   - als host-permissie op `frontend/dist` blokkeert: 
     - `PATH="/home/mevius/snipebot/.tools/node/bin:/home/mevius/snipebot/frontend/node_modules/.bin:$PATH" vite build --outDir dist-local --emptyOutDir false`
4. Handmatige smoke:
   - open overzicht, gebruik filters/sort/paginatie,
   - selecteer items en voer bulk-actie uit,
   - archiveer en herstel item,
   - verifieer dat detailpagina + check-now nog werken.

## Verification evidence
- Backend tests uitgevoerd:
  - `SNIPEBOT_DB_URL="sqlite:////home/mevius/snipebot/.tmp/test-suite.db" /home/mevius/snipebot/.venv/bin/pytest backend/tests/test_watchlist.py -q`
  - resultaat: `14 passed, 5 warnings`.
- Frontend tests uitgevoerd:
  - `PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run test -- --no-cache`
  - resultaat: `6 passed`.
- Frontend standaard build geprobeerd:
  - `PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run build`
  - resultaat: gefaald door host-permissie op bestaande `frontend/dist/assets` (`EACCES: permission denied, rmdir ...`).
- Frontend build succesvol geverifieerd via alternatieve output map:
  - `PATH="/home/mevius/snipebot/.tools/node/bin:/home/mevius/snipebot/frontend/node_modules/.bin:$PATH" vite build --outDir dist-local --emptyOutDir false`
  - resultaat: `✓ built`.
