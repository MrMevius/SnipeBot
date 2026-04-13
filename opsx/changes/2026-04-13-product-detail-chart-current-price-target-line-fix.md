# Title
Fix detailpagina prijsgrafiek, actuele prijs en targetlijn

## Context
Op de individuele project/product detailpagina's werkt de prijsgrafiek niet meer betrouwbaar. Daarnaast moet de actuele prijs expliciet hersteld worden en moet een targetlijn zichtbaar zijn in de detailgrafiek wanneer een targetprijs is ingesteld.

## Goals / Non-goals
### Goals
1. Herstel de werkende prijsgrafiek op individuele detailpagina's.
2. Herstel de actuele prijsweergave op detailpagina's.
3. Voeg een targetlijn toe in de detailgrafiek wanneer targetprijs aanwezig is.

### Non-goals
1. Geen backend API-contractwijzigingen.
2. Geen brede UI-redesign of refactor buiten deze bugfix.
3. Geen wijzigingen aan niet-detailpagina flows behalve noodzakelijke regressiepreventie.

## Proposed approach
1. Pas `TrendChart` in `frontend/src/App.tsx` gericht aan voor robuuste rendering en targetlijn-ondersteuning.
2. Gebruik op detailpagina consistente actuele-prijslogica met veilige fallback naar history latest indien nodig.
3. Voeg beperkte styling toe in `frontend/src/styles.css` voor targetlijn en label.
4. Werk bestaande frontend tests bij in `frontend/src/App.test.tsx` voor targetlijn en actuele-prijsweergave.

## Implementation steps (ordered)
1. Maak en activeer deze change spec.
2. Werk `TrendChart` bij met optionele `targetPrice`-prop en render targetlijn in interactieve detailweergave.
3. Maak chart-rendering robuuster voor lage datapunt-aantallen in detailweergave.
4. Herstel actuele-prijsweergave met fallback op history latest als item current ontbreekt.
5. Update CSS voor targetlijn/label.
6. Breid frontend tests uit.
7. Voer frontend tests/build uit.
8. Werk specstatus en verificatie-evidence bij.

## Acceptance criteria
1. Op detailpagina's rendert de prijsgrafiek weer zonder runtimefouten.
2. De actuele prijs op detailpagina toont een correcte waarde (item current price, met fallback op latest history indien item current ontbreekt).
3. Als targetprijs is ingesteld, toont de detailgrafiek een zichtbare horizontale targetlijn met duidelijke styling.
4. Als targetprijs ontbreekt, toont de detailgrafiek geen targetlijn.
5. Bestaande detailpagina-interactie (hover/tooltip, save, check-now) blijft werken.

## Testing plan
```bash
PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run test -- --no-cache
PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run build
```

Fallback bij bekende `dist/` permissieblokkade:
```bash
PATH="/home/mevius/snipebot/.tools/node/bin:/home/mevius/snipebot/frontend/node_modules/.bin:$PATH" vite build --outDir dist-local --emptyOutDir false
```

Handmatig:
1. Open meerdere `/products/{id}` detailpagina's.
2. Verifieer grafiekrender, actuele prijs, en targetlijn (met/zonder target).

## Risk + rollback plan
### Risks
1. Chart-aanpassingen kunnen regressie geven in bestaande interactieve tooltip/keyboardflow.
2. Fallbacklogica voor actuele prijs kan inconsistentie tonen als history-data afwijkt.

### Mitigations
1. Beperk wijzigingen tot detailchart en voeg gerichte tests toe.
2. Gebruik expliciete prioriteit: item current price eerst, anders history latest.

### Rollback
1. Revert wijzigingen in `frontend/src/App.tsx`, `frontend/src/styles.css`, `frontend/src/App.test.tsx`.

## Notes / links
- `frontend/src/App.tsx`
- `frontend/src/styles.css`
- `frontend/src/App.test.tsx`

## Current status
Completed

## What changed
- `frontend/src/App.tsx`
  - `TrendChart` uitgebreid met optionele `targetPrice` prop voor detailweergave.
  - Detailchart targetlijn toegevoegd (horizontale lijn + label `Target € ...`) wanneer targetprijs aanwezig is.
  - Chart-rendering robuuster gemaakt: interactieve detailchart rendert nu ook met 1 datapunt (alleen lege state bij 0 punten).
  - Detailpagina geeft `targetPrice={detail.item.target_price}` door aan `TrendChart`.
  - Actuele prijs op detailpagina hersteld met fallback: eerst `detail.item.current_price`, anders `history.latest_price`.
  - `data-testid="detail-current-price"` toegevoegd voor gerichte regressietests.
  - Extra synchronisatie-fix: detailgrafiek gebruikt nu `historySeriesWithSnapshot`.
    - Als `detail.item.last_checked_at` + `detail.item.current_price` recenter zijn dan het laatste history-punt, wordt een synthetisch laatste datapunt toegevoegd voor de grafiekweergave.
    - Hierdoor blijft de grafiek synchroon met de Snapshot-sectie bij tijdelijke history-achterstand.
  - Samenvattingswaarden onder de chart (`Latest/Lowest/Highest`) gebruiken dezelfde gesynchroniseerde reeks als de grafiek.
- `frontend/src/styles.css`
  - Styling toegevoegd voor targetlijn en label (`.chart-target-line`, `.chart-target-label`).
- `frontend/src/App.test.tsx`
  - Bestaande detailpagina-test uitgebreid:
    - targetlijn aanwezig bij targetprijs,
    - actuele prijs fallback correct (`€ 24.00`) wanneer `current_price` ontbreekt.
  - Nieuwe test toegevoegd die verifieert dat targetlijn **niet** rendert bij `target_price: null`.
  - Deze test verifieert nu ook dat een recenter snapshot-checkmoment een extra (gesynchroniseerd) chart-datapunt oplevert (`detail-chart-point-2`).

## How to verify
1. Frontend tests:
   - `PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run test -- --no-cache`
2. Frontend build:
   - `PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run build`
3. Handmatig (aanbevolen smoke):
   - open `/products/{id}` met targetprijs en verifieer targetlijn zichtbaar,
   - open `/products/{id}` zonder targetprijs en verifieer targetlijn afwezig,
   - verifieer dat "Current price" een waarde toont wanneer `current_price` ontbreekt maar history `latest_price` aanwezig is.

## Verification evidence
- `PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run test -- --no-cache`
  - resultaat: `8 passed`.
- `PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run build`
  - resultaat: succesvol (`✓ built`).
- Na synchronisatie-fix opnieuw uitgevoerd:
  - `PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run test -- --no-cache`
    - resultaat: `8 passed`.
  - `PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run build`
    - resultaat: succesvol (`✓ built`).
