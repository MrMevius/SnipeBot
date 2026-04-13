# Title
Watchlist UI compacter maken met topbar-menu voor Stats en Settings

## Context
De huidige overview-pagina toont meerdere grote panelen onder elkaar (Owner & Health, Settings, Add Product, Watchlist, Import/Export). Hierdoor wordt de pagina lang en druk. De gebruiker wil een compactere workflow met duidelijke topbar-acties en minder verticale ruimte in filters en watchlist-rijen.

## Goals / Non-goals
### Goals
1. Verplaats Owner & Health naar een Stats-sectie achter een menu.
2. Plaats Settings achter hetzelfde menu.
3. Maak Add Product beschikbaar in de topbar.
4. Maak watchlist filteropties zichtbaar compacter.
5. Verwijder Import/Export uit de frontend UI.
6. Maak watchlist-overzicht compacter zodat 1 artikel in 1 regel getoond wordt.

### Non-goals
1. Geen backend API-wijzigingen voor watchlist/settings/health.
2. Geen wijzigingen aan datamodel of schedulergedrag.
3. Geen complete redesign van product detail pagina.

## Proposed approach
1. Introduceer een topbar met titel, primaire Add Product actie en een menu-toggle.
2. Voeg een eenvoudige menu-view state toe met opties `watchlist`, `stats`, `settings`.
3. Render Stats (Owner & Health) en Settings conditioneel achter menu-selectie.
4. Herstructureer filter-controls naar compacte layout met kortere labels en strakkere spacing.
5. Verwijder Import/Export sectie en ongebruikte state/handlers/imports.
6. Compacteer watchlist tabel door minder multi-line inhoud per cel en compactere actie-elementen.

## Implementation steps (ordered)
1. Activeer deze spec als enige bron voor deze wijziging.
2. Bouw topbar + menu-navigatie in `frontend/src/App.tsx`.
3. Verplaats Owner & Health naar Stats view en Settings naar Settings view.
4. Houd Add Product bereikbaar vanuit topbar en render de form in compacte vorm.
5. Maak Watchlist filters compacter in markup + styles.
6. Verwijder Import/Export sectie uit UI + verwijder ongebruikte code.
7. Maak watchlist rows compacter (1 item per regel) en update styles.
8. Werk frontend tests bij voor nieuwe structuur/labels.
9. Run tests/build en leg evidence vast in deze spec.

## Acceptance criteria (measurable)
1. Owner & Health staat niet meer als los hoofdpanel op de overview; deze is bereikbaar via `Menu -> Stats`.
2. Settings staat niet meer als los hoofdpanel op de overview; deze is bereikbaar via `Menu -> Settings`.
3. Add Product actie staat in de topbar.
4. Filtersectie gebruikt een compactere layout (minder verticale ruimte, compact controls).
5. Import/Export sectie is niet meer zichtbaar in de frontend.
6. Watchlist toont items compacter met 1 artikel per tabelregel zonder extra hoge multi-line celopmaak.
7. Bestaande basisfunctionaliteit (watchlist laden, item navigatie, settings opslaan) blijft werken.
8. Relevante frontend tests slagen of blokkades staan expliciet onder `Verification evidence`.

## Testing plan (canonical commands or approach)
Frontend tests:
```bash
PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run test -- --no-cache
```

Frontend build:
```bash
PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run build
```

Fallback build (bij host-permissie op `frontend/dist`):
```bash
PATH="/home/mevius/snipebot/.tools/node/bin:/home/mevius/snipebot/frontend/node_modules/.bin:$PATH" vite build --outDir dist-local --emptyOutDir false
```

## Risk + rollback plan
### Risks
1. UI-herstructurering kan regressies veroorzaken in bestaande frontend tests.
2. Compacte layout kan leesbaarheid verminderen op kleinere schermen.
3. Verwijderen van Import/Export UI kan bestaande gebruikersflow beïnvloeden.

### Mitigations
1. Tests bijwerken en gericht valideren op bestaande kernflows.
2. Responsive CSS met wrapping en minimale control-breedte gebruiken.
3. Alleen UI verwijderen; backend import/export endpoints onaangetast laten.

### Rollback
1. Revert commit(s) van deze change.
2. Herstel vorige panel-structuur en Import/Export sectie in `App.tsx`.
3. Herstel eerdere styles in `styles.css`.

## Notes / links
- Frontend app: `frontend/src/App.tsx`
- Frontend styling: `frontend/src/styles.css`
- Frontend tests: `frontend/src/App.test.tsx`

## Current status
Completed

## What changed
- Frontend overview-layout in `frontend/src/App.tsx` geherstructureerd naar een compacte topbar + menu-flow:
  - nieuwe topbar met titel, `Add product` actie en `Menu` knop,
  - nieuwe view-state (`watchlist` / `stats` / `settings`) achter menu-selectie.
- `Owner & Health` panel verplaatst achter `Menu -> Stats` (nu als `Stats` sectie).
- `Settings` panel verplaatst achter `Menu -> Settings` (geen losse settings-panel meer op overview).
- `Import / Export` UI volledig verwijderd uit de overview:
  - import/export gerelateerde handlers en state verwijderd,
  - import/export client-calls niet langer gebruikt in de overzichtsweergave.
- `Add Product` sectie compacter gemaakt en bereikbaar via topbar link.
- Watchlist filters compacter gemaakt:
  - compacte filter-grid met korte labels (`Search`, `Active`, `Target`, `Site`, `Tag`, `Sort`, `Rows`),
  - compacte action-rows voor archief/tags/bulk acties.
- Watchlist tabel compacter gemaakt zodat items als lage single-row entry worden gerenderd:
  - productweergave op één regel,
  - compacte trend/insight weergave,
  - compacte status/flags/tags/actions cellen.
- Styling uitgebreid in `frontend/src/styles.css`:
  - topbar/menu component styles,
  - compacte grids/rows/table styles,
  - responsive compact behavior voor kleinere schermen.
- Frontend tests bijgewerkt in `frontend/src/App.test.tsx` voor de nieuwe UI flow:
  - menu-gebaseerde settings navigatie,
  - aangepaste bulk-labels/knoptekst,
  - compact trend-tekstassertie.

## How to verify
1. Frontend tests:
   - `PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run test -- --no-cache`
2. Frontend build (standaard):
   - `PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run build`
3. Frontend build fallback (bij host-permissie op `frontend/dist`):
   - `PATH="/home/mevius/snipebot/.tools/node/bin:/home/mevius/snipebot/frontend/node_modules/.bin:$PATH" vite build --outDir dist-local --emptyOutDir false`
4. Handmatige smoke:
   - Open `/` en controleer dat topbar `Add product` en `Menu` toont.
   - Klik `Menu` → `Stats`; verifieer owner input + health snapshot.
   - Klik `Menu` → `Settings`; wijzig instelling en save.
   - Klik `Menu` → `Watchlist`; verifieer compacte filters, compacte rijen en afwezigheid van Import/Export.

## Verification evidence
- Frontend tests uitgevoerd:
  - `PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run test -- --no-cache`
  - resultaat: `6 passed`.
- Frontend standaard build geprobeerd:
  - `PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run build`
  - resultaat: gefaald door host-permissie op bestaande `frontend/dist/assets` (`EACCES: permission denied, rmdir ...`).
- Frontend fallback build succesvol uitgevoerd:
  - `PATH="/home/mevius/snipebot/.tools/node/bin:/home/mevius/snipebot/frontend/node_modules/.bin:$PATH" vite build --outDir dist-local --emptyOutDir false`
  - resultaat: `✓ built`.
