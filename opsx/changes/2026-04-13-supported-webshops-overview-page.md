# Title
Supported webshops overview page

## Context
De frontend heeft nu geen aparte overzichtspagina die expliciet toont welke webshops ondersteund worden en hoe een gebruiker die shops snel kan gebruiken bij het toevoegen van een product.

## Goals / Non-goals
### Goals
- Voeg een overzichtspagina toe met alle momenteel ondersteunde webshops.
- Toon per webshop een korte, praktische instructie hoe je de shop gebruikt in SnipeBot.
- Houd de pagina in lijn met de bestaande frontendstijl en navigatie.

### Non-goals
- Geen backend API-uitbreiding of dynamische shoplijst vanuit de backend.
- Geen zoek/filter functionaliteit op de overzichtspagina.
- Geen uitgebreide long-form handleiding.

## Proposed approach
- Voeg een nieuwe overview-view toe in `frontend/src/App.tsx` via bestaande `menuView`-navigatie.
- Definieer een kleine, statische lijst met ondersteunde shops op basis van de huidige adapter-registry (`hema`, `amazon_nl`, `aliexpress`).
- Render per shop een compacte kaart met naam, domein en korte stappen.
- Voeg minimale CSS toe in `frontend/src/styles.css` voor nette, responsive kaarten in de bestaande visuele taal.
- Voeg tests toe in `frontend/src/App.test.tsx` voor navigatie en zichtbaarheid van shops + instructietekst.

## Implementation steps
1. Breid `MenuView` en globale menunavigatie uit met een item voor de supported shops-overview.
2. Voeg statische shopdata toe met korte instructies per webshop.
3. Implementeer de overview-sectie in `App.tsx` (panel + kaarten per shop).
4. Voeg bijbehorende CSS-klassen toe in `styles.css` met bestaande spacing/kleuren.
5. Update frontend tests voor het nieuwe menu-item en de inhoud.

## Acceptance criteria
- Er is een overzichtspagina bereikbaar vanuit de bestaande navigatie.
- De pagina toont alle ondersteunde webshops: `hema`, `amazon_nl`, `aliexpress`.
- Per webshop staat een korte instructie hoe de gebruiker die shop gebruikt in SnipeBot.
- Layout en styling sluiten aan op de bestaande frontendstijl.

## Testing plan
- Frontend tests draaien met `cd frontend && npm run test`.
- Frontend build controleren met `cd frontend && npm run build`.
- Handmatige check in de UI: navigatie-item openen en visuele controle van alle shopkaarten + instructies.

## Risk + rollback plan
- Risico: inconsistente labels of onduidelijke instructietekst.
- Mitigatie: korte, uniforme instructieformaten per shop en test op zichtbaarheid.
- Rollback: verwijder nieuwe menuView/item en CSS-blokken; herstel vorige navigatie.

## Notes / links
- Frontend view: `frontend/src/App.tsx`
- Styling: `frontend/src/styles.css`
- Tests: `frontend/src/App.test.tsx`
- Bron ondersteunde shops: `backend/src/snipebot/adapters/sites/registry.py`

## Current status
Completed (verification blocked in this environment)

## What changed
- `frontend/src/App.tsx`
  - `MenuView` uitgebreid met `"supported-shops"`.
  - Nieuwe statische dataset toegevoegd: `SUPPORTED_WEBSHOPS` met `hema`, `amazon_nl`, `aliexpress`.
  - Globale menubalk uitgebreid met nieuw item **Supported shops** (op overview, add-product en detail-navigatie).
  - Nieuwe overview-sectie toegevoegd (`menuView === "supported-shops"`) met:
    - titel + korte intro,
    - card per webshop,
    - site key, domein en 3 korte gebruiksstappen.
- `frontend/src/styles.css`
  - Nieuwe styling toegevoegd voor de overzichtspagina:
    - `.supported-shops-grid`
    - `.supported-shop-card`
    - `.supported-shop-head`
    - `.supported-shop-key`
    - lijst-opmaak voor instructiestappen.
  - Responsive gedrag toegevoegd voor small screens (1 kolom).
- `frontend/src/App.test.tsx`
  - Bestaande render-test uitgebreid met navigatie naar **Supported shops**.
  - Assertions toegevoegd voor:
    - actieve menustatus,
    - zichtbare panel,
    - alle drie shop-cards,
    - voorbeeld-instructietekst per webshop.

## How to verify
- `cd frontend && npm run test`
- `cd frontend && npm run build`

## Verification evidence
- `cd frontend && npm run test` → **failed**: `/bin/bash: line 1: npm: command not found`
- `cd frontend && npm run build` → **failed**: `/bin/bash: line 1: npm: command not found`
- Functionele verificatie moet opnieuw worden uitgevoerd in een omgeving met Node.js + npm beschikbaar.
