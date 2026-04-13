# Watchlist overview thumbnail + status clarity

## Title
Watchlist overview verbeteringen: thumbnail, duidelijke status, relatieve tijd, status-context en density-toggle

## Context
De overview toont nu alleen productnaam en ruwe statuscodes (zoals `pending` of `ok`). Hierdoor is de scanbaarheid beperkt en is het niet direct duidelijk wat een status betekent. Daarnaast ontbreekt een compacte visuele producthint in de lijst.

## Goals / Non-goals
### Goals
- Toon een thumbnail in de productkolom van de overview zonder backend-uitbreiding.
- Vervang ruwe statussen door begrijpelijke labels en visuele badges.
- Toon relatieve tijd bij de laatste check in de statuskolom.
- Maak status klikbaar met korte context/uitleg.
- Voeg een density-toggle toe (compact/comfortable) voor tabelrijen.

### Non-goals
- Geen backend- of datamodel-wijzigingen.
- Geen uitbreiding naar detailpagina of andere views.
- Geen nieuwe statusfilter of bulk retry-flow in deze wijziging.

## Proposed approach
1. Voeg frontend helpers toe voor thumbnail-afleiding (op basis van URL host), statuslabel/-uitleg en relatieve tijd.
2. Werk de overview productcel bij met thumbnail + productnaam.
3. Vervang statusweergave door badge + secundaire tekst voor relatieve tijd.
4. Voeg status-context popover/tooltip toe op klik.
5. Voeg density-toggle toe en style varianten in CSS.
6. Update frontend tests voor nieuwe overview-UI elementen.

## Implementation steps (ordered)
1. Introduceer helperfuncties in `frontend/src/App.tsx` voor statuslabeling, statuscontext, relatieve tijd en thumbnail-url.
2. Pas overview row rendering in `App.tsx` aan: thumbnail blok in productkolom en statusbadge met klikbare context.
3. Voeg state + controls toe voor density (`compact`/`comfortable`) en koppel classes op tabel.
4. Breid `frontend/src/styles.css` uit met thumbnail-, badge-, popover- en density-styles.
5. Update `frontend/src/App.test.tsx` met asserts voor thumbnail, statuslabels/context, relatieve tijd en density-toggle.
6. Run verificatiecommando’s en documenteer resultaten.

## Acceptance criteria
1. Elke overview-rij toont een thumbnail naast de productnaam (met fallback).
2. Statusen worden in begrijpelijke labels getoond i.p.v. alleen ruwe statuscodes.
3. Bij status wordt relatieve checktijd weergegeven wanneer `last_checked_at` beschikbaar is.
4. Statusbadge is klikbaar en toont korte context/uitleg per status.
5. Er is een werkende density-toggle voor `compact` en `comfortable` die rijspacing zichtbaar beïnvloedt.
6. Frontend tests en build voor gewijzigde onderdelen slagen.

## Testing plan
- `PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run test -- src/App.test.tsx`
- `PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run build`

## Risk + rollback plan
- Risico: extra UI-elementen kunnen tabel op small screens overvol maken.
  - Mitigatie: compacte thumbnail-afmetingen en responsive CSS.
- Risico: statusuitleg kan verwarren als mapping niet consistent is.
  - Mitigatie: centrale mapping helper in code en tests op labels.
- Rollback: revert commit met aanpassingen in `App.tsx`, `styles.css`, `App.test.tsx`.

## Notes / links
- User scope: overview-only, minimale impact, geen backend-wijzigingen.
- Geselecteerde verbetersuggesties: #2 relatieve tijd, #3 klikbare statuscontext, #5 density-toggle.

## Current status
Completed

## What changed
- `frontend/src/App.tsx`
  - Helpers toegevoegd voor:
    - status mapping (`getStatusMeta`) met duidelijke labels + context,
    - relatieve tijd (`formatRelativeTime`),
    - thumbnail URL-afleiding op basis van producthost (`getProductThumbnailUrl`),
    - thumbnail-fallback letter (`getThumbnailFallbackText`).
  - Overview productcel uitgebreid met thumbnail naast productlink.
  - Statuskolom aangepast naar klikbare statusbadge met contextblok en relatieve checktijd.
  - Density-toggle toegevoegd (`Compact` / `Comfortable`) en gekoppeld aan tabelklasse.
  - UI-state toegevoegd voor actieve density en geopende statuscontext.
- `frontend/src/styles.css`
  - Nieuwe styles voor thumbnail, statusbadge-kleuren, contextblok en density-toggle.
  - Tabelspacing differentie voor `density-compact` en `density-comfortable`.
- `frontend/src/App.test.tsx`
  - Overview-test uitgebreid met asserts voor thumbnail + duidelijke statuslabeling + fallback checktijd.
  - Nieuwe test toegevoegd voor relatieve tijd, klikbare statuscontext en density-toggle.

## How to verify
- `PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run test -- --no-cache src/App.test.tsx`
- `PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run build`
- Handmatige UI-check:
  - Open overview en verifieer thumbnail per rij.
  - Controleer dat statuslabels leesbaar zijn (bijv. `In orde`, `Wacht op check`).
  - Controleer relatieve checktijd in statuskolom.
  - Klik op statusbadge en verifieer contexttekst.
  - Schakel tussen `Compact` en `Comfortable` en controleer zichtbaar verschil in rijspacing.

## Verification evidence
- Frontend tests:
  - Command: `PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run test -- --no-cache src/App.test.tsx`
  - Resultaat: **pass** (`7 passed`).
- Frontend build:
  - Command: `PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run build`
  - Resultaat: **pass** (`vite build` succesvol, output in `frontend/dist`).
