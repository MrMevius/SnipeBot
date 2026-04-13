# Title
Compacte product preview op watchlist en productdetailpagina

## Context
De huidige UI toonde alleen een favicon-achtige site-thumbnail, terwijl de wens was om echte productfoto’s (zoals t-shirts, koffiebonen) in overview en detail te tonen. Daarom is de scope uitgebreid met een beperkte backend/API-aanpassing voor `image_url`.

## Goals / Non-goals
### Goals
1. Toon een compacte inline product preview op de watchlist per product.
2. Toon dezelfde compacte inline product preview op de productdetailpagina.
3. Houd de implementatie beperkt tot UI-rendering met bestaande data (geen backendwijzigingen).
4. Toon echte productafbeeldingen (waar beschikbaar) in plaats van alleen site-favicon.
5. Maak productafbeelding beschikbaar via backend `image_url` in watchlist/detail responses.

### Non-goals
1. Geen brede backend-refactor buiten het toevoegen van `image_url`.
2. Geen nieuwe data-ophaalflows of extra preview-endpoints.
3. Geen brede herontwerp/refactor buiten de preview-presentatie.

## Proposed approach
1. Breid parser/adapters uit met extractie van product-afbeelding (`og:image` / vergelijkbare metadata) als `image_url`.
2. Sla `image_url` op in `watch_items` en expose via watchlist/detail/preview API responses.
3. Introduceer of hergebruik `ProductInlinePreview` in frontend en laat thumbnail primair `image_url` gebruiken met fallback naar favicon.
4. Gebruik dezelfde renderer in de watchlist productcel en detail snapshot-context voor visuele consistentie.
5. Voeg compacte styles toe en werk tests bij (backend + frontend).

## Implementation steps (ordered)
1. Breid backend datamodel uit met `image_url` op `WatchItem` + migratie.
2. Breid parsing/adapters uit met image-url extractie en persist op succesvolle checks.
3. Expose `image_url` in API response modellen en frontend API types.
4. Integreer (bestaande) preview-renderer in `frontend/src/App.tsx` zodat thumbnail `image_url` gebruikt met favicon-fallback.
5. Voeg/werk CSS classes in `frontend/src/styles.css` voor consistente weergave.
6. Update `frontend/src/App.test.tsx` met:
   - watchlist assert(s) voor preview-zichtbaarheid,
   - detailpagina assert(s) voor preview-zichtbaarheid,
   - regressiechecks op bestaande navigatie/detailinteractie.
7. Voeg backend tests toe voor image-url extractie/API contract waar nodig.
8. Voer verificatiecommando’s uit en documenteer uitkomsten.
9. Werk spec-secties `What changed`, `How to verify`, `Verification evidence`, `Current status` bij.

## Acceptance criteria
1. Elke watchlist-rij toont een compacte inline preview met echte productafbeelding indien `image_url` beschikbaar is.
2. De productdetailpagina toont dezelfde productafbeelding in de preview/snapshot-context.
3. Als `image_url` ontbreekt of laden faalt, blijft favicon/fallback zichtbaar (geen broken UI).
4. Bestaande kerninteracties (navigatie naar detail, detailweergave) blijven werken.
5. Backend en frontend tests/build voor gewijzigde onderdelen slagen.

## Testing plan
```bash
PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run test -- --no-cache src/App.test.tsx
PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run test -- --no-cache
PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run build
python -m pytest backend/tests
```

## Risk + rollback plan
### Risks
1. Compacte preview kan op small screens de productkolom te vol maken.
2. Nieuwe preview-markup kan bestaande testselectors beïnvloeden.

### Mitigations
1. Houd layout compact, met ellipsis en responsive wrapping.
2. Voeg gerichte testids/selectors toe zonder bestaande selectors te breken.

### Rollback
1. Revert wijzigingen in:
   - `backend/src/snipebot/adapters/sites/base.py`
   - `backend/src/snipebot/adapters/sites/parsing.py`
   - `backend/src/snipebot/adapters/sites/{hema,amazon_nl,aliexpress}.py`
   - `backend/src/snipebot/persistence/models.py`
   - `backend/src/snipebot/domain/price_checks.py`
   - `backend/src/snipebot/api/watchlist.py`
   - `backend/migrations/versions/20260413_0003_add_watch_item_image_url.py`
   - `backend/tests/test_adapters.py`
   - `backend/tests/test_watchlist.py`
   - `frontend/src/api/client.ts`
   - `frontend/src/App.tsx`
   - `frontend/src/styles.css`
   - `frontend/src/App.test.tsx`

## Notes / links
- Scopekeuze bijgewerkt: backend + frontend voor echte productafbeelding.
- Prioriteit: beide pagina’s in één implementatieronde.
- Preview-vorm: compacte inline preview.

## Current status
Completed

## What changed
- `backend/src/snipebot/adapters/sites/parsing.py`
  - Nieuwe `extract_image_url(html, page_url)` toegevoegd met support voor `og:image`, `twitter:image` en JSON-LD `image`.
- `backend/src/snipebot/adapters/sites/base.py`
  - `ParsedProductData` uitgebreid met optionele `image_url`.
- `backend/src/snipebot/adapters/sites/{hema,amazon_nl,aliexpress}.py`
  - Adapters vullen nu `image_url` uit parserdata.
- `backend/src/snipebot/persistence/models.py`
  - `WatchItem` uitgebreid met `image_url` kolom.
- `backend/src/snipebot/persistence/db.py`
  - SQLite compatibiliteitsfix toegevoegd in `_ensure_legacy_columns()` om `watch_items.image_url` automatisch toe te voegen op startup voor bestaande databases.
- `backend/migrations/versions/20260413_0003_add_watch_item_image_url.py`
  - Alembic migratie toegevoegd voor `watch_items.image_url`.
- `backend/src/snipebot/domain/price_checks.py`
  - Bij succesvolle check wordt `item.image_url` geüpdatet wanneer parser een image URL levert.
- `backend/src/snipebot/api/watchlist.py`
  - `WatchItemResponse` en `WatchItemPreviewResponse` uitgebreid met `image_url`.
  - Preview endpoint retourneert nu `image_url`.
- `backend/tests/test_adapters.py`
  - Test toegevoegd voor image-url extractie (meta + JSON-LD).
- `backend/tests/test_watchlist.py`
  - Preview API-test uitgebreid met assert op `image_url`.
- `frontend/src/api/client.ts`
  - `WatchItem` en `WatchItemPreviewResponse` uitgebreid met `image_url`.
- `frontend/src/App.tsx`
  - Thumbnaillogica gebruikt nu primair `item.image_url` met favicon fallback bij load failure.
  - `referrerPolicy="no-referrer"` toegevoegd op image element.
- `frontend/src/styles.css`
  - Bestaande compacte preview-styles behouden; rendering blijft consistent met productafbeeldingen.
- `frontend/src/App.tsx`
  - `ProductThumbnail` uitgebreid naar een thumbnail-pair: grotere productthumbnail + aparte shop thumbnail (favicon) ernaast.
  - Productthumbnail blijft `image_url` eerst gebruiken met fallback naar shop-favicon.
- `frontend/src/styles.css`
  - Thumbnail sizing verhoogd (compact + detail).
  - Nieuwe styles toegevoegd voor `.product-thumb-pair`, `.shop-thumb`, `.shop-thumb-large`, `.shop-thumb-fallback`.
  - Shop thumbnail extra vergroot op verzoek (22px compact, 26px large) voor betere zichtbaarheid.
  - Beide thumbnails op verzoek 200% vergroot t.o.v. vorige set:
    - product: 38→76 (compact), 56→112 (large)
    - shop: 24→48 (compact), 28→56 (large)
- `frontend/src/App.test.tsx`
  - Bestaande preview-regressietests blijven groen met nieuwe image/fallbacklogica.

## How to verify
- Frontend gericht:
  - `PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run test -- --no-cache src/App.test.tsx`
- Frontend volledig:
  - `PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run test -- --no-cache`
- Frontend build:
  - `PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run build`
- Backend tests (vereist backend dependencies geïnstalleerd):
  - `python3 -m pytest backend/tests`
- Fallback zonder lokale Python/pip (in Docker):
  - `docker run --rm -v "/home/mevius/snipebot:/work" -w /work python:3.12-slim bash -lc "pip install --no-cache-dir -e /work/backend[dev] && pytest /work/backend/tests"`

## Verification evidence
- ✅ `PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run test -- --no-cache src/App.test.tsx`
  - Resultaat: `8 passed`.
- ✅ `PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run test -- --no-cache`
  - Resultaat: `8 passed`.
- ✅ `PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run build`
  - Resultaat: succesvol (`vite build` voltooid).
- ℹ️ `python3 -m pytest backend/tests`
  - Resultaat: kon lokaal niet direct draaien door ontbrekende host Python dependencies (`fastapi`, `sqlalchemy`, `pydantic_settings`).
- ✅ Docker fallback uitgevoerd:
  - Command: `docker run --rm -v "/home/mevius/snipebot:/work" -w /work python:3.12-slim bash -lc "pip install --no-cache-dir -e /work/backend[dev] && pytest /work/backend/tests"`
  - Resultaat: `52 passed, 13 warnings`.
- ✅ Na SQLite compatibiliteitsfix opnieuw uitgevoerd:
  - Command: `docker run --rm -v "/home/mevius/snipebot:/work" -w /work python:3.12-slim bash -lc "pip install --no-cache-dir -e /work/backend[dev] && pytest /work/backend/tests"`
  - Resultaat: `52 passed, 13 warnings`.
- ✅ UI wijziging grotere thumbnail + shop thumbnail:
  - Command: `PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run test -- --no-cache src/App.test.tsx`
  - Resultaat: `8 passed`.
- ✅ Frontend build na UI wijziging:
  - Command: `PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run build`
  - Resultaat: succesvol (`vite build` voltooid).
- ✅ Frontend rebuild container na shop-icon grootte update:
  - Command: `docker compose up -d --build frontend`
  - Resultaat: frontend draait met bijgewerkte assets.
- ✅ Frontend build na 200% vergroting van beide thumbnails:
  - Command: `PATH="/home/mevius/snipebot/.tools/node/bin:$PATH" npm --prefix frontend run build`
  - Resultaat: succesvol (`vite build` voltooid).
- ✅ Frontend container herstart na 200% vergroting:
  - Command: `docker compose up -d --build frontend`
  - Resultaat: frontend draait met bijgewerkte assets.
