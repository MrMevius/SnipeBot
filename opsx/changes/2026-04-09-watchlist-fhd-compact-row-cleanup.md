# Title
Watchlist overview compacter maken voor FHD (bredere layout, minder kolommen, compacte acties)

## Context
De watchlist-overview wordt primair gebruikt op Full HD schermen. De huidige layout gebruikt relatief smalle containerbreedte en toont extra kolommen/metadata (trend, flags, tags, statusdatum) die de scanbaarheid verminderen. De gebruiker wil een compacter, rustiger overzicht met één product per regel.

## Goals / Non-goals
### Goals
1. Maak de interface breder op FHD in de overview.
2. Houd watchlist-items compact: één product per regel.
3. Verwijder trendweergave uit het overzicht.
4. Toon status zonder datum in de tabel.
5. Verwijder flags-kolom uit de tabel.
6. Verwijder tags-kolom uit de tabel.
7. Maak archive/restore knop compacter.

### Non-goals
1. Geen backend/API wijzigingen.
2. Geen wijzigingen aan product-detail trendgrafiek.
3. Geen functionele wijziging aan bulk-selectie, paginatie of navigatie.

## Proposed approach
1. Verhoog overzichtsbreedte via CSS container-aanpassing voor desktop/FHD.
2. Vereenvoudig watchlist tabelkolommen in `frontend/src/App.tsx`.
3. Verwijder trend/flags/tags uit tabelheader en rijrendering.
4. Vereenvoudig statuscel naar alleen statuswaarde.
5. Introduceer compactere button-variant voor archive/restore in rij-acties.
6. Werk frontend tests bij waar UI-verwachtingen zijn gewijzigd.

## Implementation steps (ordered)
1. Activeer deze spec als bron voor de wijziging.
2. Pas watchlist tabelrendering aan in `frontend/src/App.tsx` (kolommen + cellen).
3. Pas styles aan in `frontend/src/styles.css` (containerbreedte + compacte archiveknop).
4. Update frontend tests in `frontend/src/App.test.tsx` voor gewijzigde overviewstructuur.
5. Run frontend tests en build.
6. Vul deze spec aan met `What changed`, `How to verify`, `Verification evidence`, `Current status`.

## Acceptance criteria (measurable)
1. Overview container is breder op FHD dan voorheen.
2. Watchlist overzicht toont items als compacte enkele rij per product.
3. Kolom `Trend` is afwezig in watchlist overzicht.
4. Statuscel toont alleen status (geen datum/subregel).
5. Kolom `Flags` is afwezig in watchlist overzicht.
6. Kolom `Tags` is afwezig in watchlist overzicht.
7. Archive/Restore actieknop gebruikt compactere visuele variant.
8. Relevante frontend tests slagen of blokkades zijn vastgelegd onder `Verification evidence`.

## Testing plan (canonical commands or approach)
Frontend tests:
```bash
PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run test -- --no-cache
```

Frontend build:
```bash
PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run build
```

Fallback build (bij permissieprobleem op `frontend/dist`):
```bash
PATH="/home/mevius/snipebot/.tools/node/bin:/home/mevius/snipebot/frontend/node_modules/.bin:$PATH" vite build --outDir dist-local --emptyOutDir false
```

## Risk + rollback plan
### Risks
1. Minder kolommen kan informatie verbergen die sommige users nog verwachten.
2. Testasserties kunnen falen door gewijzigde tabelstructuur.

### Mitigations
1. Scope beperken tot overzichtstabelformaat zonder backend-impacts.
2. Tests gericht updaten op gewenste nieuwe UI.

### Rollback
1. Revert commit van deze change.
2. Herstel tabelkolommen en styles naar vorige staat in `App.tsx`/`styles.css`.

## Notes / links
- Frontend app: `frontend/src/App.tsx`
- Frontend styles: `frontend/src/styles.css`
- Frontend tests: `frontend/src/App.test.tsx`

## Current status
Completed

## What changed
- `frontend/src/App.tsx` aangepast voor compactere watchlist-overview:
  - tabelkolom `Trend` verwijderd uit header en rows,
  - tabelkolom `Flags` verwijderd uit header en rows,
  - tabelkolom `Tags` verwijderd uit header en rows,
  - statuscel vereenvoudigd naar alleen `last_status` (zonder datum/subregel),
  - row-actions vereenvoudigd naar compacte archive/restore actie,
  - overview watchlist-load vereenvoudigd door history-fetch per row te verwijderen (niet meer nodig zonder trendkolom).
- `frontend/src/styles.css` aangepast:
  - `.container` verbreed naar `max-width: 1560px` met iets ruimere horizontale padding voor FHD,
  - nieuwe compacte actievarianten toegevoegd: `.row-actions-compact` en `.compact-button`,
  - responsive override in media query behouden zodat kleinere schermen niet breken.
- `frontend/src/App.test.tsx` bijgewerkt:
  - overview test valideert nu dat `Trend`, `Flags` en `Tags` niet meer zichtbaar zijn.

## How to verify
1. Frontend tests:
   - `PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run test -- --no-cache`
2. Frontend build (standaard):
   - `PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run build`
3. Frontend build fallback (bij permissie op `frontend/dist`):
   - `PATH="/home/mevius/snipebot/.tools/node/bin:/home/mevius/snipebot/frontend/node_modules/.bin:$PATH" vite build --outDir dist-local --emptyOutDir false`
4. Handmatige UI-check:
   - Start app en open `/`.
   - Verifieer bredere container op FHD.
   - Verifieer dat watchlist geen `Trend`, `Flags`, `Tags` kolommen toont.
   - Verifieer dat status alleen statuswaarde toont (zonder datumregel).
   - Verifieer dat archive/restore knop visueel compacter is.

## Verification evidence
- Frontend tests uitgevoerd:
  - `PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run test -- --no-cache`
  - resultaat: `6 passed`.
- Frontend standaard build uitgevoerd:
  - `PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run build`
  - resultaat: gefaald door host-permissie op bestaande `frontend/dist/assets` (`EACCES: permission denied, rmdir ...`).
- Frontend fallback build uitgevoerd:
  - `PATH="/home/mevius/snipebot/.tools/node/bin:/home/mevius/snipebot/frontend/node_modules/.bin:$PATH" vite build --outDir dist-local --emptyOutDir false`
  - resultaat: `✓ built`.
