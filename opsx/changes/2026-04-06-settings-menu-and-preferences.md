# Title
Settings-menu toevoegen met backend/app instellingen en UI-voorkeuren

## Context
De huidige SnipeBot frontend heeft geen centraal settings-menu. Runtime-configuratie bestaat nu vooral uit environment variables. Gebruikers willen een beheerscherm voor de meest relevante instellingen, inclusief dark mode en UI-voorkeuren.

De gekozen scope door de gebruiker:
- Wel: notificaties, Telegram toggle, globale check-interval, Playwright fallback + adapterlijst, standaard historievenster, prijsweergave/valuta, logniveau, dark mode.
- Niet: retry-interval en worker batch-grootte.

## Goals / Non-goals
### Goals
1. Voeg een Settings-menu toe in de frontend.
2. Voeg backend API toe om app-instellingen persistent op te slaan en op te halen.
3. Ondersteun deze backend settings:
   - notifications_enabled
   - telegram_enabled
   - check_interval_seconds
   - playwright_fallback_enabled
   - playwright_fallback_adapters
   - log_level
4. Ondersteun deze UI-voorkeuren (frontend/local):
   - default_history_days
   - currency_display_mode
   - dark_mode
5. Koppel settings aan bestaande UI waar relevant (history default, prijsformat, theme).
6. Voeg tests toe/werk tests bij voor nieuwe backend/frontend paden.

### Non-goals
1. Geen UI voor retry-interval of worker-batch-size.
2. Geen opslag of weergave van Telegram bot token in de frontend.
3. Geen live hot-reload van worker config zonder restart-garantie; wijzigingen mogen "na restart" van kracht zijn voor workergedrag.
4. Geen complete redesign van de bestaande watchlist/detail layouts.

## Proposed approach
1. Introduceer een nieuwe DB-tabel `app_settings` (key/value) met eenvoudige upsert-helpers.
2. Voeg service-laag toe voor typed read/write van ondersteunde app settings met validatie en defaults (fall back op bestaande env-waarden waar logisch).
3. Voeg API-routes toe: `GET /settings` en `PATCH /settings`.
4. Breid frontend API client uit met typed settings calls.
5. Voeg settings-paneel toe in `App.tsx` met save/feedback/error states.
6. Bewaar UI-voorkeuren in `localStorage`; pas ze direct toe op UI en formatting.

## Implementation steps (ordered)
1. Activeer deze spec als enige bron voor deze wijziging.
2. Backend persistence:
   - voeg `AppSetting` model toe,
   - zorg dat `init_db()` tabel meeneemt.
3. Backend domain/service:
   - typed settings schema en defaults,
   - read/update functies met inputvalidatie.
4. Backend API:
   - nieuw settings-routerbestand,
   - include router in API root.
5. Frontend API client:
   - types en calls voor `fetchSettings` en `patchSettings`.
6. Frontend UI:
   - settings-menu met velden volgens scope,
   - dark mode toggle,
   - default history days toepassen in detailpagina,
   - currency display toepassen op `formatPrice`.
7. Styling:
   - theme variables voor light/dark,
   - settings panel controls.
8. Tests:
   - backend tests voor settings endpoints + validatie,
   - frontend tests voor settings render/save en dark mode/price formatting behavior.
9. Verificatiecommando’s uitvoeren en spec updaten met evidence.

## Acceptance criteria (measurable)
1. Er is een zichtbaar settings-menu in de frontend vanaf de overzichtspagina.
2. Het settings-menu bevat minimaal toggles/velden voor: notificaties, Telegram aan/uit, check-interval, Playwright fallback, fallback adapters, logniveau, standaard history days, prijsweergave/valuta en dark mode.
3. `GET /settings` retourneert actuele instellingen met stabiele defaults.
4. `PATCH /settings` valideert en bewaart ondersteunde backend-instellingen persistent.
5. Na verversen blijven backend-instellingen behouden (via API) en UI-voorkeuren behouden (via localStorage).
6. `default_history_days` beïnvloedt de default selectie op productdetailpagina.
7. Prijsweergave-instelling beïnvloedt zichtbare prijsformaten in overzicht/detail/grafiek tooltip.
8. Dark mode instelling past een donker thema toe op de app en blijft behouden na refresh.
9. Bestaande watchlist en detail functionaliteit blijft werken.
10. Relevante backend- en frontendtests slagen, of blokkades zijn expliciet gedocumenteerd onder `Verification evidence`.

## Testing plan (canonical commands or approach)
Backend:
```bash
python3 -m pip install -e "./backend[dev]"
pytest backend/tests/test_watchlist.py -q
```

Frontend:
```bash
npm --prefix frontend run test -- --no-cache
npm --prefix frontend run build
```

Manual smoke:
1. Open app en open settings-menu.
2. Wijzig en save backend settings; refresh; verifieer persistent via UI/API.
3. Wijzig default history days; open detailpagina; verifieer default dagselectie.
4. Wijzig currency display en dark mode; verifieer directe UI-impact + persist na refresh.

## Risk + rollback plan
### Risks
1. Nieuwe settings-API kan validatiefouten introduceren bij ongeldige input.
2. Theme/CSS-wijzigingen kunnen bestaande leesbaarheid of contrast beïnvloeden.
3. Runtime settings (zoals check-interval/loglevel) kunnen functioneel verwachtingen wekken die pas na restart volledig zichtbaar zijn.

### Mitigations
1. Strikte backend validatie met duidelijke foutmeldingen.
2. Beperk CSS-wijzigingen tot variabelen en bestaande componentstructuur.
3. Communiceer in UI dat sommige wijzigingen na service restart effect hebben.

### Rollback
1. Revert commit(s) van deze change.
2. Verwijder settings-router include om API snel uit te schakelen indien nodig.
3. Houd bestaande watchlist/detail flows onaangetast als fallback.

## Notes / links
- Frontend app: `frontend/src/App.tsx`
- Frontend client: `frontend/src/api/client.ts`
- Backend API root: `backend/src/snipebot/api/__init__.py`
- Backend watchlist routes: `backend/src/snipebot/api/watchlist.py`
- Backend config defaults: `backend/src/snipebot/core/config.py`

## Current status
Completed

## What changed
- Backend settings-opslag en API toegevoegd:
  - `backend/src/snipebot/persistence/models.py`: nieuw `AppSetting` model (`app_settings` key/value tabel).
  - `backend/src/snipebot/domain/settings.py`: typed settings service met defaults, validatie en persistente update-logica.
  - `backend/src/snipebot/api/settings.py`: nieuwe endpoints:
    - `GET /settings`
    - `PATCH /settings`
  - `backend/src/snipebot/api/__init__.py`: settings-router geregistreerd.
- Backend tests uitgebreid:
  - `backend/tests/test_watchlist.py`:
    - settings defaults/persist test toegevoegd,
    - invalid log level test toegevoegd,
    - reset helper wist nu ook `app_settings`.
- Frontend API client uitgebreid:
  - `frontend/src/api/client.ts`:
    - types `BackendSettings` en `BackendSettingsUpdatePayload`,
    - calls `fetchSettings()` en `patchSettings()`.
- Frontend settings-menu en voorkeuren toegevoegd:
  - `frontend/src/App.tsx`:
    - nieuw settings-paneel op de overzichtspagina,
    - backend-instellingen bewerkbaar + opslaan,
    - UI-voorkeuren met localStorage (`default_history_days`, `currency_display_mode`, `dark_mode`),
    - dark mode toepassen via root class,
    - default history days doorgegeven aan detailpagina,
    - prijsformattering (`€` vs `EUR`) doorgezet in overzicht/detail/grafiek-tooltip.
- Styling voor settings en dark mode toegevoegd:
  - `frontend/src/styles.css`:
    - CSS variables voor light/dark,
    - settings form/header styles,
    - theming op panel/input/select/link/muted/table borders.
- Frontend tests uitgebreid:
  - `frontend/src/App.test.tsx`:
    - mocks uitgebreid voor `/settings` calls,
    - nieuwe test voor settings save + dark mode toepassing.

## How to verify
1. Backend tests:
   - `SNIPEBOT_DB_URL="sqlite:////home/mevius/snipebot/.tmp/test-suite.db" /home/mevius/snipebot/.venv/bin/pytest backend/tests -q`
2. Frontend tests:
   - `PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run test -- --no-cache`
3. Frontend build (standaard command kan in deze host permissieproblemen hebben op bestaande `frontend/dist`):
   - `PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run build`
   - alternatief (gebruikt voor verificatie):
     - `PATH="/home/mevius/snipebot/.tools/node/bin:/home/mevius/snipebot/frontend/node_modules/.bin:$PATH" vite build --outDir dist-local --emptyOutDir false`
4. Handmatige smoke:
   - Open `/`, klik "Open settings".
   - Wijzig backend settings en klik "Save settings"; refresh en verifieer behoud.
   - Wijzig history window default naar 7/30/90; open een productdetail en verifieer default selectie.
   - Zet price display op `EUR` en dark mode aan; verifieer directe UI-impact en behoud na refresh.

## Verification evidence
- Backend test suite uitgevoerd:
  - `SNIPEBOT_DB_URL="sqlite:////home/mevius/snipebot/.tmp/test-suite.db" .venv/bin/pytest backend/tests -q`
  - resultaat: `40 passed, 5 warnings`.
- Frontend tests uitgevoerd:
  - `PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run test -- --no-cache`
  - resultaat: `5 passed`.
- Frontend standaard build geprobeerd:
  - `PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run build`
  - resultaat: gefaald door host-permissie op bestaande `frontend/dist/assets` (`EACCES: permission denied, rmdir ...`).
- Frontend build succesvol geverifieerd via alternatieve output map:
  - `PATH="/home/mevius/snipebot/.tools/node/bin:/home/mevius/snipebot/frontend/node_modules/.bin:$PATH" vite build --outDir dist-local --emptyOutDir false`
  - resultaat: `✓ built`.
