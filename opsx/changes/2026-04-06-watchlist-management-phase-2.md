# Title
Watchlist management fase 2a: tags + import/export

## Context
Na fase 1 (filters, bulk-acties, archiveren, paginatie) ontbreekt nog productiviteitsfunctionaliteit voor organisatie en databeheer. Gebruikers willen items groeperen met tags en watchlists eenvoudig kunnen importeren/exporteren.

## Goals / Non-goals
### Goals
1. Voeg tags toe aan watch-items (aanmaken, toekennen, ophalen, filteren op tag).
2. Voeg watchlist export toe in JSON en CSV, met respect voor actieve lijstfilters.
3. Voeg watchlist import toe via JSON payload met `dry_run` en apply modus.
4. Voeg frontend bediening toe voor tagfilter, tagbeheer en import/export acties.
5. Behoud compatibiliteit met bestaande watchlist/detail/settings flows.

### Non-goals
1. Geen alert rule engine uitbreidingen (`percent_drop`, `new_low`, cooldown) in deze fase.
2. Geen auth/multi-user redesign (owner blijft `local`).
3. Geen file-upload parser voor CSV import in deze fase (JSON import is in scope).

## Proposed approach
1. Introduceer `watch_item_tags` en `watch_item_tag_links` tabellen.
2. Breid domain services uit met tag CRUD + item tag assignment.
3. Breid watchlist listing uit met `tag` filter.
4. Voeg `GET /watchlist/export` toe met `format=json|csv`.
5. Voeg `POST /watchlist/import?dry_run=true|false` toe met row-level resultaten.
6. Voeg frontend panel + controls toe voor tags en import/export.

## Implementation steps (ordered)
1. Activeer deze spec als enige bron voor fase 2a.
2. Backend persistence:
   - `WatchItemTag` + `WatchItemTagLink` models toevoegen.
3. Backend services:
   - list/create tags,
   - set/get tags voor item,
   - list filter op `tag`,
   - import dry-run/apply helper,
   - export row mapping helper.
4. Backend API:
   - `GET /watchlist/tags`
   - `POST /watchlist/tags`
   - `PATCH /watchlist/{item_id}/tags`
   - `GET /watchlist/export?format=json|csv&...filters`
   - `POST /watchlist/import?dry_run=true|false`
   - `GET /watchlist` uitbreiden met queryparam `tag`
5. Frontend client + UI:
   - API types/calls voor tags/import/export,
   - tagfilter + item tag assignment,
   - import JSON textarea met dry-run/apply,
   - export knoppen voor CSV/JSON.
6. Tests uitbreiden (backend + frontend).
7. Verificatie draaien en spec bijwerken.

## Definition of done (endpoint checklist)
### `GET /watchlist/tags`
- [x] Retourneert unieke tags van owner `local`.
- [x] Sorteert stabiel op tagnaam.
- [x] 200 met lege lijst als nog geen tags bestaan.

### `POST /watchlist/tags`
- [x] Accepteert niet-lege naam.
- [x] Trimt invoer.
- [x] Idempotent: bestaande tag geeft 200 met bestaande tag terug.

### `PATCH /watchlist/{item_id}/tags`
- [x] Vervangt volledige tagset van item op basis van inputlijst.
- [x] Maakt ontbrekende tags automatisch aan.
- [x] 404 bij onbekend item.

### `GET /watchlist` (uitbreiding)
- [x] Ondersteunt queryparam `tag=<name>`.
- [x] Combineert correct met bestaande filters/sort/paginatie.

### `GET /watchlist/export`
- [x] Ondersteunt `format=json|csv`.
- [x] Respecteert meegegeven watchlist filters (incl. `tag`).
- [x] Exporteert minimaal: `id,url,custom_label,target_price,site_key,active,archived_at,tags`.

### `POST /watchlist/import`
- [x] Accepteert JSON array payload met item-rows.
- [x] `dry_run=true`: geen database mutaties.
- [x] `dry_run=false`: upsert/watchitem mutaties + tag assignment.
- [x] Retourneert row-level status (`created|updated|error`) met foutdetails.

## Acceptance criteria (measurable)
1. Tags zijn beheerbaar via API en zichtbaar/toepasbaar in frontend.
2. `GET /watchlist` kan op tag filteren in combinatie met bestaande queryfilters.
3. Export levert JSON en CSV volgens actieve filters.
4. Import ondersteunt dry-run en apply met inzichtelijke row outcomes.
5. Bestaande watchlist/detail/settings functionaliteit blijft werken.
6. Relevante backend/frontend tests slagen, of blokkades worden gedocumenteerd.

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
1. Maak tags aan en wijs ze toe aan meerdere items.
2. Filter overzicht op tag en verifieer resultaten.
3. Exporteer JSON/CSV met actieve filters.
4. Voer import dry-run uit met geldige + ongeldige rows.
5. Voer import apply uit en verifieer create/update + tags.

## Risk + rollback plan
### Risks
1. Veel extra querylogica kan regressies geven in listing prestaties.
2. Import kan ongeldige/rommeldata introduceren zonder strikte validatie.
3. CSV export kan escaping issues tonen bij speciale tekens.

### Mitigations
1. Houd listing response additief en regressietests op bestaande filters.
2. Strikte row-validatie + duidelijke row errors.
3. Gebruik standaard csv writer met escaping.

### Rollback
1. Revert commit(s) van deze fase.
2. Schakel import/export endpoints uit indien nodig.
3. Houd bestaande watchlist routes als fallback actief.

## Notes / links
- Backend API: `backend/src/snipebot/api/watchlist.py`
- Backend services: `backend/src/snipebot/domain/services.py`
- Backend models: `backend/src/snipebot/persistence/models.py`
- Frontend app: `frontend/src/App.tsx`
- Frontend client: `frontend/src/api/client.ts`

## Current status
Completed

## What changed
- Nieuwe tag persistence toegevoegd in `backend/src/snipebot/persistence/models.py`:
  - `WatchItemTag` tabel (`watch_item_tags`),
  - `WatchItemTagLink` many-to-many tabel (`watch_item_tag_links`),
  - relationship `WatchItem.tags`.
- Domain services uitgebreid in `backend/src/snipebot/domain/services.py`:
  - tag helpers: `list_watch_tags`, `get_or_create_watch_tag`, `set_watch_item_tags`,
  - listing filter op `tag` via `list_watch_items_paginated(..., tag=...)`,
  - export helper `export_watch_items_rows(...)`,
  - import helper `import_watch_items_rows(...)` met dry-run/apply en row-level resultaten.
- Watchlist API uitgebreid in `backend/src/snipebot/api/watchlist.py`:
  - `GET /watchlist/tags`,
  - `POST /watchlist/tags`,
  - `PATCH /watchlist/{item_id}/tags`,
  - `GET /watchlist/export?format=json|csv`,
  - `POST /watchlist/import?dry_run=true|false`,
  - `GET /watchlist` ondersteunt nu ook `tag` queryfilter,
  - `WatchItemResponse` bevat nu `tags`.
- Frontend API client uitgebreid in `frontend/src/api/client.ts`:
  - tag/import/export types en calls,
  - `WatchItem` bevat `tags`,
  - `WatchlistQuery` ondersteunt `tag`.
- Frontend UI uitgebreid in `frontend/src/App.tsx`:
  - tagfilter in overview,
  - tagbeheer (aanmaken + toekennen per row),
  - import/export paneel met JSON textarea,
  - import dry-run/apply acties,
  - export JSON/CSV acties (inhoud in paneel geladen).
- Tests uitgebreid:
  - `backend/tests/test_watchlist.py`:
    - tags create/assign/filter test,
    - import dry-run/apply + export test.
  - `frontend/src/App.test.tsx` aangepast voor `tags` veld en `/watchlist/tags` fetches.

## How to verify
1. Backend tests:
   - `SNIPEBOT_DB_URL="sqlite:////home/mevius/snipebot/.tmp/test-suite.db" /home/mevius/snipebot/.venv/bin/pytest backend/tests/test_watchlist.py -q`
2. Frontend tests:
   - `PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run test -- --no-cache`
3. Frontend build:
   - `PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run build`
   - bij host permission issue op `frontend/dist`: 
     - `PATH="/home/mevius/snipebot/.tools/node/bin:/home/mevius/snipebot/frontend/node_modules/.bin:$PATH" vite build --outDir dist-local --emptyOutDir false`

## Verification evidence
- Backend tests uitgevoerd:
  - `SNIPEBOT_DB_URL="sqlite:////home/mevius/snipebot/.tmp/test-suite.db" /home/mevius/snipebot/.venv/bin/pytest backend/tests/test_watchlist.py -q`
  - resultaat: `16 passed, 5 warnings`.
- Frontend tests uitgevoerd:
  - `PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run test -- --no-cache`
  - resultaat: `6 passed`.
- Frontend standaard build geprobeerd:
  - `PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run build`
  - resultaat: gefaald door host-permissie op bestaande `frontend/dist/assets` (`EACCES: permission denied, rmdir ...`).
- Frontend build succesvol geverifieerd via alternatieve output map:
  - `PATH="/home/mevius/snipebot/.tools/node/bin:/home/mevius/snipebot/frontend/node_modules/.bin:$PATH" vite build --outDir dist-local --emptyOutDir false`
  - resultaat: `✓ built`.
