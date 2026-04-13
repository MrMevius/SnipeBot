# Title
Global Top Menubar

## Context
De frontend heeft nu route-/view-specifieke headerstukken in `frontend/src/App.tsx`. Daardoor is navigatie niet overal consistent zichtbaar. Er is behoefte aan een algemene menubalk bovenin de pagina met basisnavigatie.

## Goals / Non-goals
### Goals
- Een algemene menubalk bovenin tonen op desktop en mobiel.
- Basisnavigatie bieden: Watchlist, Add product, Stats, Settings.
- Actieve pagina/view visueel markeren.
- Bestaande stijl en componentpatronen volgen.

### Non-goals
- Geen zoekveld, accountmenu of extra headeracties.
- Geen nieuwe dependencies.
- Geen grote herstructurering van onderliggende pagina-inhoud.

## Proposed approach
- Centraliseer menu-items in één config in `App.tsx`.
- Render één gedeelde top-menubar voor relevante routes/views.
- Koppel actieve state aan route (`/`, `/add-product`) en interne menuView (`stats`, `settings`, `watchlist`).
- Voeg responsive gedrag toe voor mobiel (hamburger/toggle).
- Houd styling in `frontend/src/styles.css` consistent met bestaande variabelen/kleuren.

## Implementation steps
1. Inventariseer huidige header- en menu-renderpaden in `frontend/src/App.tsx`.
2. Introduceer centrale menubalk-config (label + target).
3. Refactor bestaande topbars naar één algemene menubalk.
4. Implementeer actieve-state logica voor route + menuView.
5. Voeg mobiele toggle/hamburger toe met keyboard/focus support.
6. Werk CSS bij voor desktop/mobiel, actieve tabs en focus-states.
7. Update/voeg tests toe in `frontend/src/App.test.tsx`.

## Acceptance criteria
- Er staat een algemene menubalk bovenin de pagina.
- Menulinks zijn klikbaar en navigeren correct.
- Actieve pagina/view is duidelijk zichtbaar.
- Menubalk werkt op desktop én mobiel.
- UI sluit aan op bestaande stijl.

## Testing plan
- Unit/integration tests in Vitest + Testing Library voor:
  - zichtbaarheid menubalk,
  - actieve-state rendering,
  - kliknavigatie tussen route/view.
- Build-validatie via bestaande frontend build.

## Risk + rollback plan
- Risico: regressie in bestaande route/view flow door header-refactor.
- Mitigatie: kleine, centrale refactor + testdekking op navigatie.
- Rollback: terug naar huidige header/menu-renderblokken in `App.tsx`.

## Notes / links
- Hoofdbestand: `frontend/src/App.tsx`
- Styling: `frontend/src/styles.css`
- Tests: `frontend/src/App.test.tsx`

## Current status
Completed (verification blocked in this environment)

## What changed
- Algemene top-menubalk toegevoegd in `frontend/src/App.tsx` via nieuwe `GlobalTopMenubar` renderfunctie.
- Menunavigatie gecentraliseerd naar vaste items: `Watchlist`, `Add product`, `Stats`, `Settings`.
- Actieve-state toegevoegd met `aria-current="page"` op basis van route/view.
- Bestaande losse topbar + uitklapmenuflow vervangen door de nieuwe algemene menubalk op overview en add-product.
- Product detail pagina toont nu dezelfde algemene menubalk bovenaan voor consistente navigatie.
- Responsive mobiel gedrag toegevoegd (menu toggle + open/close state) in `frontend/src/styles.css`.
- Tests bijgewerkt in `frontend/src/App.test.tsx` voor zichtbare menubalk, actieve-state en settings-navigatie via de menubalk.

## How to verify
- `cd frontend && npm run build`
- `cd frontend && npm run test`

## Verification evidence
- `npm run test` kon niet worden uitgevoerd: `npm: command not found`.
- Omgevingscheck: `which npm; which node; which pnpm; which yarn` gaf geen beschikbare binaries terug.
- Verificatie moet opnieuw worden uitgevoerd in een omgeving met Node.js + npm.
