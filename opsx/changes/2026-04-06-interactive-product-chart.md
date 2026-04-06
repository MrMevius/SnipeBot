# Title
Interactieve en visueel verbeterde prijsgrafiek op productdetailpagina

## Context
De huidige productdetailpagina toont een functionele, maar minimale prijstrendlijn zonder interactie. Voor betere interpretatie willen we de chart interactiever en grafisch aantrekkelijker maken, zonder backend-wijzigingen of een volledige pagina-redesign.

## Goals / Non-goals
### Goals
1. Maak de detailgrafiek interactief met hover/focus en tooltip (prijs + tijdstip).
2. Voeg visuele verbeteringen toe: subtiele gridlijnen, area fill en duidelijke active-point highlight.
3. Maak keyboardnavigatie mogelijk op datapunten (links/rechts/home/end/escape).
4. Voeg aslabels toe aan de detailgrafiek (x- en y-as labels/ticks).
5. Maak de detailgrafiek groter en prominenter in de detailpagina-layout.
6. Verplaats de grafieksectie naar boven op de productdetailpagina.
7. Zet "Manage product" achter een uitklapbare sectie (optioneel openklappen).
8. Gebruik datum/tijd notatie `yyyy-mm-dd hh:mm` in de UI waar datums/tijden worden getoond.
9. Voeg of actualiseer frontend tests voor de interactie.
10. Schaal de Y-as altijd van `0` tot `+20%` boven de hoogste gemeten prijs.
11. Gebruik op de Y-as afgeronde "mooie" tick-stappen (zoals 10/25/50/100, incl. decimale varianten indien nodig).
12. Toon valuta-teken bij bedragen.
13. Toon op de X-as altijd het volledige gekozen dagenvenster (7/30/90), ook als niet elke dag datapunten heeft.
14. Toon een spatie tussen valutateken en bedrag (bijv. `€ 24.00`).
15. Toon meerdere leesbare X-as interval-labels binnen het geselecteerde tijdsvenster.
16. Toon in de paginatitel naast "Product Detail" ook een afgeleide productnaam.
17. Zorg dat de volledige frontend GUI in het Engels is.

### Non-goals
1. Geen wijzigingen in backend API of datamodel.
2. Geen migratie naar externe chart library.
3. Geen complete redesign van de productdetailpagina.

## Proposed approach
1. Breid de bestaande `TrendChart` component in `frontend/src/App.tsx` uit met interactieve laag en rijkere SVG-weergave.
2. Voeg chart-varianten toe zodat mini-chart in overzicht eenvoudig blijft en detailchart interactief/uitgebreid wordt.
3. Breid CSS uit in `frontend/src/styles.css` voor chart-skin, focus/hover states en tooltip.
4. Werk frontend tests in `frontend/src/App.test.tsx` bij om interactieve chart-gedrag te verifiëren.

## Implementation steps (ordered)
1. Maak en activeer deze change spec.
2. Refactor `TrendChart` met gedeelde schaalberekening + detail interactiestate.
3. Voeg detailchart-lagen toe (grid, area, line, datapoints, active marker, tooltip).
4. Voeg keyboard support toe voor datapuntnavigatie.
5. Werk styling bij voor detailchart en tooltip.
6. Breid tests uit voor interactieve detailchart.
7. Voer frontend verificatiecommando's uit.
8. Werk deze spec bij met status, gewijzigde onderdelen en verification evidence.

## Acceptance criteria (measurable)
1. De detailgrafiek toont tooltip met prijs en timestamp bij hover op datapunt.
2. De detailgrafiek ondersteunt focus/keyboard en laat actieve datapunt visueel zien.
3. De detailgrafiek bevat gridlijnen, area fill én aslabels.
4. De detailgrafiek is zichtbaar groter dan de vorige variant en blijft bruikbaar op kleine schermen zonder layout-break.
5. De grafieksectie staat boven de beheersectie op de detailpagina.
6. "Manage product" is standaard inklapbaar via een knop/summary en kan door de gebruiker worden uitgeklapt.
7. Datum/tijd in detailweergave en grafiektooltip gebruikt notatie `yyyy-mm-dd hh:mm`.
8. Bestaande productdetail-flow (save/check-now) blijft werken.
9. `npm --prefix frontend run test` en `npm --prefix frontend run build` slagen, of blokkades worden expliciet gedocumenteerd.
10. Y-as start op 0 en eindigt op een afgeronde waarde die minimaal 20% boven de hoogste gemeten prijs ligt.
11. Y-as ticks gebruiken afgeronde "mooie" schaalstappen.
12. X-as labels tonen het volledige geselecteerde tijdsvenster, terwijl de lijn alleen bestaande meetpunten tekent.
13. Bedragen in detailgrafiek en relevante prijsweergaves tonen valuta-teken.
14. Bedragnotatie gebruikt `€ <bedrag>` met spatie na het valutateken.
15. X-as toont meerdere tijdslabels (niet enkel start/eind) voor betere leesbaarheid.
16. Detailtitel bevat zowel "Product Detail" als een productnaam-afleiding.
17. Alle zichtbare frontend teksten in deze flow zijn in het Engels.

## Testing plan (canonical commands or approach)
```bash
npm --prefix frontend run test
npm --prefix frontend run build
```

Handmatig:
1. Open een productdetailpagina (`/products/{id}`).
2. Hover over grafiekpunten en controleer tooltip met prijs + tijd.
3. Focus grafiek en navigeer met toetsen links/rechts/home/end.
4. Controleer dat save/check-now flow ongewijzigd werkt.

## Risk + rollback plan
### Risks
1. Interactielogica kan regressies veroorzaken in bestaande chartweergave.
2. Tooltippositionering kan op smalle viewports clipping geven.

### Mitigations
1. Mini-chart eenvoudig houden, interactieve logica richten op detailvariant.
2. Tooltippositie clamped houden binnen chartgrenzen.

### Rollback
1. Revert wijzigingen in `frontend/src/App.tsx`, `frontend/src/styles.css`, `frontend/src/App.test.tsx`.
2. Vervang interactieve chart door bestaande eenvoudige polyline-rendering.

## Notes / links
- Frontend component: `frontend/src/App.tsx`
- Frontend styling: `frontend/src/styles.css`
- Frontend tests: `frontend/src/App.test.tsx`

## Current status
Completed

## What changed
- `frontend/src/App.tsx`
  - `TrendChart` uitgebreid met interactieve detailvariant (`interactive` prop) en eenvoudige mini-variant behouden voor overview.
  - Detailvariant rendert nu gridlijnen, area fill, lijn, datapunten en een actieve marker.
  - Tooltip toegevoegd met prijs en timestamp van het actieve datapunt.
  - Keyboardnavigatie toegevoegd op detailchart (`ArrowLeft`, `ArrowRight`, `Home`, `End`, `Escape`).
  - Hover op datapunten activeert tooltip/active-state (`data-testid` toegevoegd voor testbaarheid).
  - Detailpagina gebruikt nu interactieve chart in de history-sectie.
  - Datum/tijd formattering aangepast naar vast formaat `yyyy-mm-dd hh:mm`.
  - Detailchart uitgebreid met aslijnen + aslabels (x-as datum/tijd en y-as prijslabels).
  - Detailchart vergroot (grotere viewBox dimensies) voor betere leesbaarheid.
  - Sectievolgorde aangepast zodat "Price history" bovenaan de detailcontent staat.
  - "Manage product" verplaatst naar uitklapbare sectie (`<details>/<summary>`).
  - Y-as schaal gewijzigd naar vast bereik `0..(max prijs * 1.2)` met afronding naar "nice" stapgroottes.
  - X-as schaal gewijzigd naar tijdsvenster-schaal op basis van geselecteerde dagen (7/30/90) i.p.v. alleen datapunt-index.
  - X-as uitgebreid met meerdere interval-labels en verticale hulplijnen voor betere leesbaarheid (niet alleen start/eind).
  - Valuta-teken toegevoegd aan bedragweergaves via `formatPrice` met spatie na symbool (`€ 24.00`) (o.a. tooltip, aslabels en prijsvelden).
  - Detailtitel uitgebreid met productnaam-afleiding: `Product Detail — <derived name>`.
  - Chart-aslabels en overige zichtbare UI-tekst in deze flow geharmoniseerd naar Engels (o.a. `Date/time`, `Price`).
- `frontend/src/styles.css`
  - Detailchart omgezet naar container + SVG styling (`.detail-chart`, `.detail-chart-svg`).
  - Nieuwe stijlen toegevoegd voor grid, line, area, points, active point en tooltip.
  - Focus-visible en subtiele fade-in animatie toegevoegd voor betere UX.
  - Asstijl toegevoegd (`.chart-axis`, `.chart-axis-label`, `.chart-axis-title`).
  - Detailchart-container vergroot (`max-width`/`height`).
  - Styling voor uitklapbare manage-sectie toegevoegd (`.manage-details summary`).
- `frontend/src/App.test.tsx`
  - Detailpagina-test uitgebreid met verificatie van interactieve chart:
    - chart aanwezig via aria-label,
    - hover op datapunt toont tooltip met juiste prijs,
    - keyboardactie (`End`) update actieve tooltipwaarde,
    - manage-sectie wordt expliciet opengeklapt in test voordat form-velden worden aangepast,
    - bestaande save/check-now flow blijft werken.

## How to verify
1. Frontend tests:
   - `PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run test -- --no-cache`
2. Frontend build (standaard):
   - `PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run build`
3. Frontend build (fallback i.v.m. permissies op bestaande `dist/`):
   - `PATH="/home/mevius/snipebot/.tools/node/bin:/home/mevius/snipebot/frontend/node_modules/.bin:$PATH" vite build --outDir dist-local --emptyOutDir false`

## Verification evidence
- `PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run test -- --no-cache`
  - resultaat: `4 passed`.
- `PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run build`
  - resultaat: gefaald door bestaande file-permissies op outputmap: `EACCES: permission denied, rmdir '/home/mevius/snipebot/frontend/dist/assets'`.
- `PATH="/home/mevius/snipebot/.tools/node/bin:/home/mevius/snipebot/frontend/node_modules/.bin:$PATH" vite build --outDir dist-local --emptyOutDir false`
  - resultaat: succesvol (`✓ built`).
- Na scope-uitbreiding (aslabels, grotere chart, layout en datetime-format) opnieuw uitgevoerd:
  - `PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run test -- --no-cache`
    - resultaat: `4 passed`.
  - `PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run build`
    - resultaat: opnieuw geblokkeerd op bestaande permissie (`EACCES: permission denied, rmdir '/home/mevius/snipebot/frontend/dist/assets'`).
  - `PATH="/home/mevius/snipebot/.tools/node/bin:/home/mevius/snipebot/frontend/node_modules/.bin:$PATH" vite build --outDir dist-local --emptyOutDir false`
    - resultaat: succesvol (`✓ built`).
- Na extra schaal-/valuta-/x-as vensterwijzigingen opnieuw uitgevoerd:
  - `PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run test -- --no-cache`
    - resultaat: `4 passed`.
  - `PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run build`
    - resultaat: typecheck/build slaagt functioneel, maar write naar standaard `dist/` blijft geblokkeerd door bestaande permissie (`EACCES: permission denied, rmdir '/home/mevius/snipebot/frontend/dist/assets'`).
  - `PATH="/home/mevius/snipebot/.tools/node/bin:/home/mevius/snipebot/frontend/node_modules/.bin:$PATH" vite build --outDir dist-local --emptyOutDir false`
    - resultaat: succesvol (`✓ built`).
- Na toevoeging van valuta-spatie, extra X-as intervallen, productnaam in titel en Engelstalige GUI opnieuw uitgevoerd:
  - `PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run test -- --no-cache`
    - resultaat: `4 passed`.
  - `PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run build`
    - resultaat: nog steeds geblokkeerd op bestaande permissie van standaard outputmap (`EACCES: permission denied, rmdir '/home/mevius/snipebot/frontend/dist/assets'`).
  - `PATH="/home/mevius/snipebot/.tools/node/bin:/home/mevius/snipebot/frontend/node_modules/.bin:$PATH" vite build --outDir dist-local --emptyOutDir false`
    - resultaat: succesvol (`✓ built`).
