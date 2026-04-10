# Watchlist modernization and dark-theme refinement

## Title
Watchlist modernization and Pepper-inspired dark theme update

## Context
De huidige watchlist-UI bevat veel filteropties in het hoofdscherm, beperkte kolominteractie en een relatief compacte productkolom. Daarnaast staat de add-product-flow op dezelfde pagina, terwijl de gewenste ervaring watchlist-first is met add-product op een aparte pagina. Ook is gevraagd om een modernere dark uitstraling met kleurgevoel vergelijkbaar met Pepper.com.

## Goals / Non-goals
### Goals
- Product-kolom in het overzicht breder maken voor betere leesbaarheid.
- Kolommen in de watchlist-tabel sorteerbaar maken via klikbare headers.
- Filtermogelijkheden beperken tot minimaal: alleen Search en Active.
- Watchlist als standaardweergave tonen en Add product naar een aparte pagina verplaatsen.
- UI moderniseren met een Pepper-geïnspireerde dark mode look-and-feel.

### Non-goals
- Introductie van nieuwe UI frameworks of state libraries.
- Grote backend-architectuurwijzigingen buiten benodigde sorteerondersteuning.
- Volledige pixel-perfect clone van Pepper.com.

## Proposed approach
1. Bestaande routeparser uitbreiden met een dedicated route voor add-product.
2. Add-product form uit watchlist-overview halen en als aparte sectie/page renderen.
3. Filtertoolbar versimpelen tot Search + Active.
4. Server-side sort uitbreiden met extra sort keys voor tabelkolommen; frontend mapping toevoegen per kolom.
5. Tabelheaders interactief maken met asc/desc toggles en sort-indicatoren.
6. CSS variabelen en component styling moderniseren met dark-focus, betere contrasten en grotere productkolombreedte.
7. Frontend en backend tests updaten voor nieuw gedrag.

## Implementation steps (ordered)
1. Maak route-uitbreiding voor `/add-product` en render dedicated add-product pagina.
2. Verplaats add-product form + preview + feedback van watchlist section naar add-product pagina.
3. Vereenvoudig watchlist filters naar alleen Search en Active.
4. Breid backend sortering uit met site/status/target/current/label asc/desc opties.
5. Maak frontend sort state kolom-gedreven met klikbare table headers.
6. Breid productkolombreedte en truncation gedrag uit voor desktop + responsive fallback.
7. Pas dark theme design tokens en visuele componentstijlen aan.
8. Update en voeg tests toe (frontend + backend) voor route, filters en sorting.
9. Voer verificatie uit en documenteer bewijs.

## Acceptance criteria
1. Product-kolom is aantoonbaar breder dan voorheen en productnaam is beter leesbaar.
2. Minimaal de kolommen Product, Site, Target, Current en Status zijn sorteerbaar via headers (toggle asc/desc).
3. In watchlist-overview zijn alleen Search en Active zichtbaar als filter/search controls.
4. Watchlist is default view; Add product is bereikbaar via eigen route en niet meer inline in overview.
5. UI gebruikt een moderne dark-kleurstelling met verbeterde contrasten en consistent component-design.
6. `frontend` tests/build en relevante `backend` tests slagen.

## Testing plan
- Frontend:
  - `cd frontend && npm run test`
  - `cd frontend && npm run build`
- Backend:
  - `pytest backend/tests/test_watchlist.py -q`

## Risk + rollback plan
- Risico: sort key mismatch tussen frontend en backend.
  - Mitigatie: expliciete sort key mapping + backend testdekking.
- Risico: regressie in bestaande watchlist-filters.
  - Mitigatie: gerichte frontend tests op zichtbaarheid en queryparameters.
- Rollback:
  - Revert commit met route/filter/sort/css wijzigingen.

## Notes / links
- User request: productkolom breder, sorteerbare kolommen, minimale filters, watchlist default + add page, modern dark theme.

## Current status
Completed

## What changed
- Frontend routing uitgebreid met dedicated route `/add-product` en watchlist blijft default op `/`.
- Add-product flow uit watchlist-overview verwijderd en op aparte pagina gezet, inclusief preview + submit feedback.
- Watchlist filtergebied teruggebracht naar alleen `Search` en `Active`.
- Kolomsortering toegevoegd via klikbare headers voor: `Product`, `Site`, `Target`, `Current`, `Status`.
- Frontend sort-mapping toegevoegd voor server-side sort keys (`label_*`, `site_*`, `target_*`, `current_*`, `status_*`).
- Product-kolom verbreed (`.product-col` + grotere `.product-link` max-width) met responsive fallback.
- UI styling gemoderniseerd met dark-first kleurvariabelen, zachtere panel-depth, grotere radii en focus states.
- `darkMode` default in lokale UI settings gezet naar `true` voor dark-first ervaring.
- Backend sortering uitgebreid in `list_watch_items_paginated` voor nieuwe sort keys.
- Backend tests uitgebreid met `test_watchlist_supports_column_sort_keys`.
- Frontend tests aangepast op nieuwe add-product route en watchlist-only overview.
- Frontend settings test robuuster gemaakt voor dark-mode default (`click` alleen indien nog niet actief).

## How to verify
- Frontend tests + build:
  - `PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run test -- --no-cache`
  - `PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run build`
  - Fallback bij host-permissie op `frontend/dist`: `PATH="/home/mevius/snipebot/.tools/node/bin:/home/mevius/snipebot/frontend/node_modules/.bin:$PATH" vite build --outDir dist-local --emptyOutDir false`
- Backend watchlist tests:
  - `SNIPEBOT_DB_URL="sqlite:////home/mevius/snipebot/.tmp/test-suite.db" /home/mevius/snipebot/.venv/bin/pytest backend/tests/test_watchlist.py -q`
- Handmatige UI-check:
  - Open `/` en controleer dat alleen Search + Active als filters zichtbaar zijn.
  - Klik op `Add product` in topbar en controleer route `/add-product`.
  - Controleer sorteren door op tabelheaders te klikken (Product/Site/Target/Current/Status).
  - Controleer dat productnamen ruimer zichtbaar zijn in Product-kolom.
  - Controleer dark uitstraling (achtergrond, panelen, buttons, focus states).

## Verification evidence
- Frontend tests:
  - `PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run test -- --no-cache`
  - Resultaat: **pass** (`6 passed`).
- Frontend build (standaard script):
  - `PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run build`
  - Resultaat: **failed** door host permissie op bestaande outputmap (`EACCES: permission denied, rmdir '/home/mevius/snipebot/frontend/dist/assets'`).
- Permissieherstel (handmatig door user):
  - `sudo chown -R $(id -u):$(id -g) frontend/dist`
  - optioneel: `chmod -R u+rwX frontend/dist`
- Frontend build (standaard script, na permissiefix):
  - `PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run build`
  - Resultaat: **pass** (`vite build` succesvol; output naar `frontend/dist`).
- Frontend build (fallback):
  - `PATH="/home/mevius/snipebot/.tools/node/bin:/home/mevius/snipebot/frontend/node_modules/.bin:$PATH" vite build --outDir dist-local --emptyOutDir false`
  - Resultaat: **pass** (build artifacts in `frontend/dist-local`).
- Backend tests:
  - `SNIPEBOT_DB_URL="sqlite:////home/mevius/snipebot/.tmp/test-suite.db" /home/mevius/snipebot/.venv/bin/pytest backend/tests/test_watchlist.py -q`
  - Resultaat: **pass** (`21 passed`, warnings only).
