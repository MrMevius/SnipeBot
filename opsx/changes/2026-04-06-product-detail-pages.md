# Title
Per tracked product een aparte detailpagina met beheer, historie en operationele acties

## Context
De huidige frontend toont alle watch-items in één overzichtstabel. Dit is bruikbaar voor snelle scan, maar niet voor diepere productinspectie of beheer per item.

De gewenste uitbreiding is een aparte pagina per tracked product waarop kerninformatie zichtbaar en deels aanpasbaar is: label, actuele prijs, historische prijs (grafiek), last check, status. Daarnaast zijn extra features gewenst: notities, check-nu knop, alertgeschiedenis en low-metrics (7 day low, 30 day low, all time low).

De backend heeft al een sterke basis met `watch_items`, `price_checks`, `alert_events`, een bestaande history-endpoint (`GET /watchlist/{item_id}/history`) en worker scheduling op `next_check_at`.

## Goals / Non-goals
### Goals
1. Voeg een aparte productdetailpagina toe in de frontend (`/products/:id`).
2. Maak vanuit het watchlist-overzicht per item navigatie naar die detailpagina mogelijk.
3. Toon op detailpagina minimaal:
   - label (aanpasbaar),
   - actuele prijs,
   - historische prijs in grafiekvorm,
   - last check,
   - status.
4. Voeg notities per product toe (persisted, aanpasbaar).
5. Voeg een "Check nu" actie toe per productdetailpagina.
6. Voeg alertgeschiedenis toe per productdetailpagina.
7. Toon low-metrics: 7 day low, 30 day low, all time low.
8. Voeg geautomatiseerde tests toe voor nieuwe backend/frontend paden.

### Non-goals
1. Geen prijsverschil-weergave sinds vorige check (expliciet uitgesloten).
2. Geen nieuwe notificatiekanalen of alertregels.
3. Geen complete redesign van de bestaande watchlist-overzichtspagina.
4. Geen multi-user autorisatie/auth flows.
5. Geen live streaming/push updates; dit blijft pull-based via API calls.

## Proposed approach
1. Breid backend watchlist API uit met detail-, update-, check-now- en alert-history endpoints.
2. Hergebruik bestaande `GET /watchlist/{item_id}/history` endpoint voor grafiekdata.
3. Voeg `notes` veld toe aan `watch_items` en maak deze editable via `PATCH /watchlist/{item_id}`.
4. Implementeer check-now als "schedule now" door `next_check_at` op huidige UTC-tijd te zetten; worker pakt item op in volgende tick.
5. Bereken low-metrics op basis van succesvolle `price_checks` met `current_price`:
   - 7 day low: minimum prijs sinds nu-7 dagen,
   - 30 day low: minimum prijs sinds nu-30 dagen,
   - all time low: minimum prijs over alle succesvolle checks.
6. Voeg frontend routing toe en bouw een dedicated detailcomponent met beheerform + historie + operationele secties.

## Implementation steps (ordered)
1. Maak/activeer deze change spec en leg scopegrenzen vast.
2. Backend data model:
   - voeg `notes` kolom toe op `WatchItem` model,
   - voeg compatibele SQLite init/upgrade handling toe voor bestaande DB's.
3. Backend domain services:
   - detail ophalen per item,
   - item update (label, target_price, notes, active),
   - check-now trigger,
   - alertgeschiedenis query,
   - low-metrics berekening (7d/30d/all-time).
4. Backend API (`backend/src/snipebot/api/watchlist.py`):
   - `GET /watchlist/{item_id}`,
   - `PATCH /watchlist/{item_id}`,
   - `POST /watchlist/{item_id}/check-now`,
   - `GET /watchlist/{item_id}/alerts?limit=...`.
5. Frontend API client uitbreiden met types/calls voor nieuwe endpoints.
6. Frontend routing en UI:
   - overzichtspagina blijft bestaan,
   - productnaam/link opent `/products/:id`,
   - detailpagina rendert alle gevraagde velden + extra features,
   - add/edit flows met loading/error/success states.
7. Styling uitbreiden voor detaillayout, status badges, grafiekcontainer, alertlijst.
8. Tests bijwerken/uitbreiden:
   - backend `backend/tests/test_watchlist.py`,
   - frontend `frontend/src/App.test.tsx` (en/of nieuwe detailpage testfile).
9. Voer verificatiecommando's uit en werk deze spec bij met resultaten en status.

## Acceptance criteria (measurable)
1. Vanuit watchlist-overzicht is elk product klikbaar en opent een aparte detailpagina met pad `/products/{id}`.
2. Detailpagina toont label, actuele prijs, historische prijs (grafiek), last check en status voor het gekozen product.
3. Label kan op detailpagina worden aangepast en wordt na opslaan persistent teruggelezen via API.
4. Notities kunnen op detailpagina worden aangepast en worden persistent teruggelezen via API.
5. De knop "Check nu" triggert een serveractie die het item direct inpland voor een check (waarneembaar via API-respons en/of gewijzigde scheduling-velden).
6. Detailpagina toont alertgeschiedenis voor het item, inclusief minimaal alerttype, delivery status en timestamp.
7. Detailpagina toont 7 day low, 30 day low en all time low op basis van beschikbare succesvolle checks; bij ontbrekende data wordt een duidelijke lege waarde getoond.
8. Bestaande watchlist create/update/list functionaliteit blijft werken.
9. Relevante backend- en frontendtests voor nieuwe paden slagen, of blokkades worden expliciet gedocumenteerd in `Verification evidence`.

## Testing plan (canonical commands or approach)
Backend:
```bash
python3 -m pip install -e "./backend[dev]"
pytest backend/tests/test_watchlist.py -q
pytest backend/tests -q
```

Frontend:
```bash
cd frontend
npm install
npm run test
npm run build
```

Manual smoke:
1. Start app/API.
2. Open watchlist-overzicht en navigeer naar een productdetailpagina.
3. Pas label en notities aan, sla op, refresh pagina en verifieer persistente waarden.
4. Klik "Check nu" en verifieer succesvolle API response.
5. Controleer grafiekweergave, low-metrics, last check/status en alertgeschiedenis.

## Risk + rollback plan
### Risks
1. Bestaande SQLite database bevat nog geen `notes` kolom, wat runtime fouten kan geven zonder migratiepad.
2. Extra detail-API calls kunnen frontend latency of foutpaden zichtbaarder maken.
3. Low-metrics kunnen inconsistent lijken als onvoldoende historical datapoints bestaan.
4. Check-now kan verwachtingen van direct resultaat oproepen terwijl worker interval asynchroon is.

### Mitigations
1. Voeg defensieve schema-upgrade toe bij DB-init voor `notes` kolom op bestaande SQLite DB's.
2. Bouw duidelijke loading/error UI states en robuuste fallbackweergave (`-`) bij missende data.
3. Documenteer low-metrics definitie expliciet en toon lege states transparant.
4. Maak check-now response expliciet over scheduling ("queued for next worker tick").

### Rollback
1. Revert commit(s) van deze change.
2. Laat bestaande overzichtspagina intact als fallback UX.
3. Schakel detailnavigatie uit als partiële rollback nodig is.

## Notes / links
- Frontend huidige hoofdcomponent: `frontend/src/App.tsx`
- Frontend API client: `frontend/src/api/client.ts`
- Backend watchlist router: `backend/src/snipebot/api/watchlist.py`
- Backend services: `backend/src/snipebot/domain/services.py`
- Data models: `backend/src/snipebot/persistence/models.py`
- Worker scheduling: `backend/src/snipebot/domain/price_checks.py`

## Current status
Completed

## What changed
- Backend data model uitgebreid:
  - `backend/src/snipebot/persistence/models.py`: `WatchItem.notes` toegevoegd.
  - `backend/src/snipebot/persistence/db.py`: defensieve SQLite schema-upgrade toegevoegd (`ALTER TABLE watch_items ADD COLUMN notes TEXT` wanneer kolom ontbreekt).
- Backend domain services uitgebreid in `backend/src/snipebot/domain/services.py`:
  - `get_watch_item(...)`
  - `update_watch_item(...)`
  - `trigger_watch_item_check_now(...)`
  - `list_watch_item_alert_events(...)`
  - `get_watch_item_lows(...)` met 7d/30d/all-time berekening op succesvolle checks.
- Backend API uitgebreid in `backend/src/snipebot/api/watchlist.py`:
  - response model `WatchItemResponse` bevat nu `notes`.
  - nieuw `GET /watchlist/{item_id}` retourneert itemdetail + low-metrics.
  - nieuw `PATCH /watchlist/{item_id}` voor updaten van `custom_label`, `target_price`, `notes`, `active`.
  - nieuw `POST /watchlist/{item_id}/check-now` (status: `queued_for_next_worker_tick`).
  - nieuw `GET /watchlist/{item_id}/alerts?limit=...` voor alertgeschiedenis.
  - `GET /watchlist/preview` route vóór dynamische `/{item_id}` routes geplaatst om path-conflicts te voorkomen.
- Frontend API client uitgebreid in `frontend/src/api/client.ts`:
  - types voor detail/lows/alerts/check-now/update toegevoegd.
  - nieuwe calls: `fetchWatchItemDetail`, `patchWatchItem`, `triggerWatchItemCheckNow`, `fetchWatchItemAlerts`.
- Frontend UI herwerkt in `frontend/src/App.tsx`:
  - eenvoudige path-based routing toegevoegd met detailroute `/products/:id`.
  - watchlist-overzicht behoudt bestaande add/list flow; productnaam is klikbaar naar detailpagina.
  - nieuwe detailpagina met:
    - bewerkbaar label,
    - bewerkbare notities,
    - target price + active toggle,
    - actuele prijs,
    - last check,
    - status,
    - 7 day low / 30 day low / all time low,
    - historische prijsgrafiek,
    - "Check now" knop,
    - alertgeschiedenis tabel.
- Frontend styling uitgebreid in `frontend/src/styles.css` voor detaillayout, form controls, toggles en grotere grafiek.
- Tests uitgebreid:
  - `backend/tests/test_watchlist.py`: nieuwe tests voor detail+lows, patch notes/label, check-now en alerts history.
  - `frontend/src/App.test.tsx`: nieuwe test voor navigatie naar detailpagina, save-flow en check-now flow.
- Stabilisatie na eerste testrun:
  - `backend/src/snipebot/domain/services.py`: URL-normalisatie harmoniseert nu `www.` en non-`www.` hostvarianten (upsert werkt hierdoor consistent op dezelfde product-URL).
  - `backend/tests/test_url_normalization.py`: verwachting aangepast op canonical host zonder `www.`.
  - `backend/tests/test_price_check_worker.py`: ontbrekende variabele `first_run_alert_count` gefixt in de dedup-test.
  - `frontend/src/App.test.tsx`: auto-fill test gestabiliseerd (geen fake timers nodig, waitFor timeout expliciet).
- Docker buildfix voor frontend:
  - `frontend/package.json`: build script aangepast van `tsc -b && vite build` naar `tsc -p tsconfig.app.json && vite build` zodat build geen Node-config emit meer probeert te schrijven (`vite.config.js/.d.ts`).
  - `.dockerignore`: `*.tsbuildinfo` en `frontend/vite.config.js/.d.ts` expliciet uitgesloten uit Docker context om stale artefacts te voorkomen.
  - `frontend/tsconfig.node.json`: `noEmit: true` toegevoegd (typecheck-only voor Node/Vite config project).

## How to verify
1. Backend setup en tests:
   - `uv venv .venv`
   - `uv pip install --python .venv/bin/python -e "./backend[dev]"`
   - `SNIPEBOT_DB_URL="sqlite:////home/mevius/snipebot/.tmp/test.db" .venv/bin/pytest backend/tests/test_watchlist.py -q`
   - `SNIPEBOT_DB_URL="sqlite:////home/mevius/snipebot/.tmp/test.db" .venv/bin/pytest backend/tests -q`
2. Frontend tests en build:
   - `PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run test -- --no-cache`
   - `PATH="/home/mevius/snipebot/.tools/node/bin:/home/mevius/snipebot/frontend/node_modules/.bin:$PATH" vite build --outDir dist-local --emptyOutDir false` (alternatieve build in deze host wegens permissie op bestaande `dist/`)
3. Extra syntax gate backend:
   - `python3 -m compileall backend/src backend/tests`
4. Handmatige smokecheck:
   - open `/` en klik op product in overzicht (navigatie naar `/products/{id}`),
   - wijzig label/notities en klik Save,
   - klik Check now,
   - verifieer lows + history chart + alert history renderen.

## Verification evidence
- `pytest backend/tests/test_watchlist.py -q` is geblokkeerd in deze shell: `ModuleNotFoundError: No module named 'fastapi'`.
- `pytest backend/tests -q` is geblokkeerd in deze shell door missende dependencies (`fastapi`, `sqlalchemy`, `pydantic_settings`).
- `npm --prefix frontend run test` is geblokkeerd in deze shell: `/bin/bash: npm: command not found`.
- `npm --prefix frontend run build` is geblokkeerd in deze shell: `/bin/bash: npm: command not found`.
- `python3 -m compileall backend/src backend/tests` uitgevoerd en succesvol afgerond.
- Host dependencies succesvol geïnstalleerd voor backend tests via `uv`:
  - `uv venv /home/mevius/snipebot/.venv`
  - `uv pip install --python /home/mevius/snipebot/.venv/bin/python -e "./backend[dev]"`
- `SNIPEBOT_DB_URL="sqlite:////home/mevius/snipebot/.tmp/test.db" /home/mevius/snipebot/.venv/bin/pytest backend/tests/test_watchlist.py -q` uitgevoerd:
  - resultaat: `2 failed, 8 passed`
  - failures: bestaande upsert-normalisatieverwachtingen (`www.` varianten) in `test_watchlist_upserts_by_normalized_url` en `test_watchlist_create_read_update_deactivate_flow`.
- `SNIPEBOT_DB_URL="sqlite:////home/mevius/snipebot/.tmp/test.db" /home/mevius/snipebot/.venv/bin/pytest backend/tests -q` uitgevoerd:
  - resultaat: `3 failed, 35 passed`
  - extra failure: bestaande testbug `NameError: first_run_alert_count is not defined` in `test_alerts_are_recorded_and_deduplicated_for_unchanged_state`.
- Frontend tests met lokale Node toolchain uitgevoerd:
  - `PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run test -- --no-cache`
  - resultaat: `4 passed`.
- Frontend standaard buildcommand (`npm --prefix frontend run build`) blijft in deze host geblokkeerd op permissies van historisch root-owned gegenereerde files (`vite.config.js/.d.ts` en bestaande `dist/`).
- Vite build succesvol geverifieerd via alternatieve output map:
  - `PATH="/home/mevius/snipebot/.tools/node/bin:/home/mevius/snipebot/frontend/node_modules/.bin:$PATH" vite build --outDir dist-local --emptyOutDir false`
  - resultaat: `✓ built`.
- Na stabilisatie en fixes:
  - `SNIPEBOT_DB_URL="sqlite:////home/mevius/snipebot/.tmp/test.db" /home/mevius/snipebot/.venv/bin/pytest backend/tests -q`
  - resultaat: `38 passed, 5 warnings`.
- Frontend regressiecheck na testfix:
  - `PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run test -- --no-cache`
  - resultaat: `4 passed`.
- Syntax gate herhaald na fixes:
  - `python3 -m compileall backend/src backend/tests`
  - resultaat: succesvol.
- Docker frontend build verificatie (exacte user blocker):
  - `docker compose build --no-cache frontend`
  - resultaat: succesvol, image gebouwd (`snipebot-frontend Built`).
- Runtime verificatie na build:
  - `docker compose up -d`
  - resultaat: frontend container succesvol recreated/started, api/worker healthy/running.
