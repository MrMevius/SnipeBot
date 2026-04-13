# Watchlist overview + detail thumbnail and status clarity

## Title
Watchlist overview/detail verbeteringen: thumbnail, duidelijke status, relatieve tijd, status-context en density-toggle

## Context
De overview toonde oorspronkelijk alleen productnaam en ruwe statuscodes (zoals `pending` of `ok`), waardoor scanbaarheid beperkt was en betekenis van status niet direct duidelijk. Inmiddels is dit verbeterd met badges/context en thumbnail in de lijst. Voor consistente visuele herkenning ontbreekt nog thumbnail-weergave op de productdetailpagina.

## Goals / Non-goals
### Goals
- Toon een thumbnail in de productkolom van de overview zonder backend-uitbreiding.
- Toon ook een thumbnail op de productdetailpagina, met dezelfde afleidings- en fallbacklogica.
- Vervang ruwe statussen door begrijpelijke labels en visuele badges.
- Toon relatieve tijd bij de laatste check in de statuskolom.
- Maak status klikbaar met korte context/uitleg.
- Voeg een density-toggle toe (compact/comfortable) voor tabelrijen.

### Non-goals
- Geen backend- of datamodel-wijzigingen.
- Geen uitbreiding naar andere views buiten overview + detail.
- Geen nieuwe statusfilter of bulk retry-flow in deze wijziging.

## Proposed approach
1. Voeg frontend helpers toe voor thumbnail-afleiding (op basis van URL host), statuslabel/-uitleg en relatieve tijd.
2. Werk de overview productcel bij met thumbnail + productnaam.
3. Hergebruik thumbnail-rendering op detailpagina met consistente fallback.
4. Vervang statusweergave door badge + secundaire tekst voor relatieve tijd.
5. Voeg status-context popover/tooltip toe op klik.
6. Voeg density-toggle toe en style varianten in CSS.
7. Update frontend tests voor overview + detail UI elementen.

## Implementation steps (ordered)
1. Introduceer helperfuncties in `frontend/src/App.tsx` voor statuslabeling, statuscontext, relatieve tijd en thumbnail-url.
2. Pas overview row rendering in `App.tsx` aan: thumbnail blok in productkolom en statusbadge met klikbare context.
3. Voeg thumbnail toe op detailpagina in `App.tsx` met gedeelde fallbacklogica.
4. Voeg state + controls toe voor density (`compact`/`comfortable`) en koppel classes op tabel.
5. Breid `frontend/src/styles.css` uit met thumbnail-, badge-, popover- en density-styles (inclusief detail-variant).
6. Update `frontend/src/App.test.tsx` met asserts voor thumbnail op overview + detail, statuslabels/context, relatieve tijd en density-toggle.
7. Run verificatiecommando’s en documenteer resultaten.

## Acceptance criteria
1. Elke overview-rij toont een thumbnail naast de productnaam (met fallback).
2. Productdetailpagina toont een thumbnail voor het artikel (met fallback) zonder backendwijziging.
3. Statusen worden in begrijpelijke labels getoond i.p.v. alleen ruwe statuscodes.
4. Bij status wordt relatieve checktijd weergegeven wanneer `last_checked_at` beschikbaar is.
5. Statusbadge is klikbaar en toont korte context/uitleg per status.
6. Er is een werkende density-toggle voor `compact` en `comfortable` die rijspacing zichtbaar beïnvloedt.
7. Frontend tests en build voor gewijzigde onderdelen slagen.

## Testing plan
- `PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run test -- src/App.test.tsx`
- `PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run build`

## Risk + rollback plan
- Risico: extra UI-elementen kunnen tabel op small screens overvol maken.
  - Mitigatie: compacte thumbnail-afmetingen en responsive CSS.
- Risico: detailheader kan visueel druk worden door extra thumbnail.
  - Mitigatie: compacte detail-layout met consistente spacing en schaalbare thumbnail.
- Risico: statusuitleg kan verwarren als mapping niet consistent is.
  - Mitigatie: centrale mapping helper in code en tests op labels.
- Rollback: revert commit met aanpassingen in `App.tsx`, `styles.css`, `App.test.tsx`.

## Notes / links
- User scope: overview + detail, minimale impact, geen backend-wijzigingen.
- Geselecteerde verbetersuggesties: #2 relatieve tijd, #3 klikbare statuscontext, #5 density-toggle.

## Current status
Completed

## What changed
- `frontend/src/App.tsx`
  - Herbruikbare `ProductThumbnail` component toegevoegd die bestaande thumbnail-afleiding en fallback gebruikt.
  - Overview productcel gebruikt nu deze gedeelde thumbnail-rendering.
  - Detailpagina uitgebreid met een zichtbare productthumbnail (`data-testid="detail-thumbnail-<id>"`) in de snapshotsectie.
  - Statuskolom aangepast naar klikbare statusbadge met contextblok en relatieve checktijd.
  - Density-toggle toegevoegd (`Compact` / `Comfortable`) en gekoppeld aan tabelklasse.
  - UI-state toegevoegd voor actieve density en geopende statuscontext.
- `frontend/src/styles.css`
  - Nieuwe styles voor thumbnail, statusbadge-kleuren, contextblok en density-toggle.
  - Detail-specifieke styles toegevoegd: `.product-thumb-large` en `.detail-product-head`.
  - Tabelspacing differentie voor `density-compact` en `density-comfortable`.
- `frontend/src/App.test.tsx`
  - Overview-test uitgebreid met asserts voor thumbnail + duidelijke statuslabeling + fallback checktijd.
  - Detailtests uitgebreid met asserts dat thumbnail zichtbaar is op de productdetailpagina.
  - Testset dekt relatieve tijd, klikbare statuscontext, density-toggle en thumbnail op overview + detail.

## How to verify
- `PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run test -- --no-cache src/App.test.tsx`
- `PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run build`
- Handmatige UI-check:
  - Open overview en verifieer thumbnail per rij.
  - Open een productdetailpagina en verifieer thumbnail bij Snapshot.
  - Controleer dat statuslabels leesbaar zijn (bijv. `In orde`, `Wacht op check`).
  - Controleer relatieve checktijd in statuskolom.
  - Klik op statusbadge en verifieer contexttekst.
  - Schakel tussen `Compact` en `Comfortable` en controleer zichtbaar verschil in rijspacing.

## Verification evidence
- Frontend tests:
  - Command: `PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run test -- --no-cache src/App.test.tsx`
  - Resultaat: **pass** (`8 passed` in `src/App.test.tsx`).
- Frontend build:
  - Command: `PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run build`
  - Resultaat: **pass** (`vite build` succesvol, output in `frontend/dist`).
