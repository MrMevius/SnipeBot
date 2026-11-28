# SnipeBot

SnipeBot is a self-hosted price-tracking application with a Docker-first runtime (frontend, API, and worker) and configurable persistence.

## What this repository contains

- `frontend/` — React + Vite UI
- `backend/` — FastAPI API, worker, persistence, and adapters
- `infra/docker/` — Dockerfiles for backend and frontend
- `docker-compose.yml` — multi-service local/host deployment definition

## Car searches (Marktplaats and more)

Besides product pages, SnipeBot can watch car searches on several platforms at once (Marktplaats.nl, 2dehands.be, AutoScout24.nl, ViaBOVAG.nl, Kleinanzeigen.de and AutoTrack.nl):

1. Open **Car searches**, choose a make and model (the lists come from the platforms; a platform that lacks the model is greyed out), tick the platforms and set the filters you need: year, price, mileage, minimum range and battery capacity.
2. Optionally add exclude words and a seller filter, click **Preview** and compare the count per platform with the websites, then **Save search**.
3. The first check of each platform records the current listings silently. Afterwards the worker checks every ~10 minutes per platform and sends a Telegram message (with photo) for each new matching listing and for price drops. When a search covers several platforms, the message names the platform.
4. Set an **alert price ceiling** per search: Telegram only alerts for new listings and price drops at or below it (listings without a price never alert). Without a ceiling the search records and archives listings but sends no alerts.

A filter a platform cannot apply itself is checked by SnipeBot against the listing data. What happens to listings that do not state the value (e.g. no battery capacity) is set per search under **Value not stated**: *Keep and alert* (default; marked "unknown" in the list and the Telegram message), *Keep, no alerts* or *Leave out*. Switching away from *Leave out* records the listings that were left out silently, so they do not alert as new.

**Wrong model**: sellers now and then put a car under the wrong model ("TESLA Y RWD" listed as Model 3). A listing whose title names another model of the make (from the platform's own model list; "Tesla Y" counts as Model Y) and not the searched model is left out; a listing already in the search leaves it silently. Only the title counts, because descriptions often mention other models ("same charger as the Model Y"); a title without any model name stays in. More generally, a listing that is still on the platform but no longer matches the search leaves it at the next check.

**Network hiccups**: when a platform cannot be reached (DNS failure, dropped connection, server error), SnipeBot retries once after 5 seconds. If that fails too, the platform stays "OK" and is checked again after the retry interval (5 min); only a second failed check in a row shows the error. Blocks (HTTP 403/429) show at once.

**Same car on several platforms**: dealers often list one car on Marktplaats, AutoScout24 and ViaBOVAG at once. Listings on different platforms with the same build year and mileage (at least 1,000 km), the same place or the same title start, and prices at most 6 % apart are shown as one result: the cheapest listing that is still online, with badges linking to the other platforms (and their price if it differs). One platform holds a car once, so two cars of one dealer with the same round mileage stay apart (each platform's listing joins the car with the closest price). The overview counts cars, not listings. A new listing or price drop of a car that another platform already offers for that price or less sends no alert; a cheaper offer elsewhere does.

**Variant** (Tesla Model 3 from 2024 on): tick Standard Range, Long Range RWD, Long Range AWD and/or Performance to search one variant over all platforms, also where range or battery are not stated. SnipeBot recognises the variant from the title or version text ("Long Range AWD", "SR+"), the battery capacity, the power (208 kW SR, 235 kW LR RWD, 366 kW LR AWD, ~460 kW Performance), the drive and the range, in that order; a value that contradicts the earlier ones is taken as a typo and ignored ("Premium" alone says nothing, dealers use it for every variant). When the search data do not tell (Marktplaats, 2dehands and Kleinanzeigen show power only on the listing page), SnipeBot reads the archived listing page or fetches it once (at most 40 pages per check, 2 s apart; a baseline check has no limit) and remembers the result per listing. A listing that still cannot be placed (e.g. "Tesla Model 3 Dual Motor": LR AWD or Performance) counts as "value not stated".

Each platform is an adapter (`backend/src/snipebot/adapters/marketplaces/`) implementing `PlatformAdapter`: it lists makes and models, turns the filters into a platform query (reporting the filters it cannot apply) and runs that query.

Platform notes:

- **Marktplaats** filters on every SnipeBot filter itself; a check reads the newest 100 listings.
- **2dehands** (2dehands.be / 2ememain.be) runs on the Marktplaats platform (same search API and listing pages); Belgian listings, private and business, city shown as "Gent (BE)". Belgian sellers rarely state range or battery capacity, so SnipeBot checks those itself (battery also from the title) and the search's **Value not stated** setting applies. An ad shown on both Marktplaats and 2dehands under the same id is recorded once.
- **AutoScout24** (autoscout24.nl) is searched in the Netherlands, Belgium and Germany, with dealers and private sellers; it shows the part of the German offer that is advertised to Dutch buyers. Cars abroad show the country with the city ("Dilbeek (BE)"); their prices exclude Dutch BPM and import costs. Range and battery capacity work as for AutoTrack below, and are unknown more often for foreign listings. AutoScout24.nl includes every AutoTrack listing under the same id: switching a search from AutoTrack to AutoScout24 keeps its listings, price history and archived photos.
- **ViaBOVAG** (viabovag.nl) lists cars of BOVAG-certified dealers, with license plate, BOVAG warranties and the specified range and battery capacity. Its pages only filter on make and model, so SnipeBot applies year, price, mileage, range and battery itself; the values are always stated. Many of these cars are also on AutoScout24 or Marktplaats (duplicates are linked by license plate where both show one).
- **Kleinanzeigen** (kleinanzeigen.de) is searched in Germany (offers only, no wanted ads), private sellers and dealers; the city is shown as "Klarenthal (DE)" and prices exclude Dutch BPM and import costs. It filters on year, price, mileage and seller itself; it has no range or battery filter, so SnipeBot checks those: battery capacity only comes from the title or the start of the description, range is never stated, so the search's **Value not stated** setting decides. Paid "top ads" are skipped (they appear on every page and need not match the search), and a placeholder price below 100 € ("1 € VB") counts as no price. A check reads all result pages newest first (25 per page, at most 20 pages, 3 s apart). Kleinanzeigen refuses Python's HTTP client, so SnipeBot fetches its pages and photos with `curl` under its own user agent; robots.txt allows the search and listing pages. No distance is shown (search pages hold no coordinates).
- **AutoTrack** lists dealer cars only (a "private only" search cannot include it) and cannot filter on range or battery capacity, so SnipeBot checks those itself: range comes from the listing data, battery capacity only from the title (e.g. "78 kWh"), so it is often unknown. A check reads all result pages newest first (20 per page, at most 20 pages, 3 s apart). AutoTrack's robots.txt disallows crawlers on search pages; SnipeBot uses it for personal searches at the regular cadence and backs off when blocked. AutoTrack is moving pages to a newer site without the page data SnipeBot reads; when that reaches search pages, the search shows a parse error instead of wrong results.

Searches created earlier from a pasted Marktplaats URL keep working; choose a make and model on the search page to switch them to filters and add platforms.

**Search page**: a compact header shows the filters, each platform's result count (hover for its last check and notes) and four counts: cars listed, cars **new in the last 24 hours** (not counting a silent baseline), cars **gone in the last 24 hours** (no longer on any platform) and the cheapest price. The list holds cars still online; gone cars are in the archive. It loads 25, 50, 100 or all cars per page (remembered in the browser), sorted by the server on the clicked column. **Details** shows only what tells cars apart: the drive (AWD/RWD, from the title, the drive field or the recognised variant) and **Tow hitch** when the title or options mention one ("trekhaak", "AHK", "Anhängerkupplung", "towbar"); descriptions are not stored, so a tow hitch mentioned only there is not shown.

Listings show their country as a flag and, when `SNIPEBOT_HOME_NAME`, `SNIPEBOT_HOME_POSTCODE`, `SNIPEBOT_HOME_LATITUDE` and `SNIPEBOT_HOME_LONGITUDE` are set, the straight-line distance from that place (Marktplaats/2dehands from the listing coordinates, AutoScout24 from the site's own distance for the postcode).

Telegram uses the same notification settings as the watchlist (Settings → Telegram).

### Listing archive

Every listing a saved search records is also archived locally, so it stays available when the platform removes or changes it:

- The worker fetches each listing page and stores title, price, description, all attributes, seller details, statistics and **all photos** as originally uploaded (no resizing, ~150–300 KB each). Fetching is throttled (one listing per ~3 s, at most ~45 s per worker tick) and pauses that platform with increasing backoff when it blocks requests. AutoTrack photos are stored as the uploaded JPEG (typically 1920×1280, ~200 KB).
- A listing is fetched again when its price or title changes in the search results and otherwise weekly while it is online. A new version is stored only when the content changed; photos are only added, a photo removed from the listing is kept and marked as removed.
- Listings in a search link to SnipeBot's own listing page (`/archive/<id>`) with gallery, description, attributes, seller, price history and version history (including description diffs). **Archive** in the menu lists the cars that are **gone from every platform** (newest gone first), laid out like a search: one row per car (same-car rules as in a search, plus the license plate) with badges linking to each platform's saved page, drive and tow hitch under Details, 25/50/100/all per page, text, search and platform filters, the number of cars gone in the last 24 hours and the storage used. Cars still online are reached from their search; the API still lists them with `status=online` or `all`.
- The same car on several platforms is recognized by its license plate (AutoTrack always shows it, Marktplaats sometimes in the car attributes); its archive page then links to the other listings ("also listed").
- The archive is kept when a search is deleted; delete single listings from their archive page. Photos are stored under `SNIPEBOT_MARKETPLACE_ARCHIVE_DIR` (default `/data/archive`, inside the SQLite volume) and served through the API. There is no size limit: plan roughly 5–8 MB per car listing (about 25 photos).

## Prerequisites

- Docker Engine with Compose plugin (`docker compose`)
- Linux/macOS shell (or equivalent)

Optional for local non-Docker development:
- Python `>=3.12`
- Node.js + npm
- curl for Lidl Netherlands product checks

## Quick start (Docker)

1. Create runtime configuration:

```bash
cp .env.example .env
```

2. Build and run services:

```bash
docker compose up -d --build
```

3. Verify health:

```bash
docker compose ps
curl http://localhost:8001/health
curl http://localhost:5173/api/health
```

Default endpoints:
- Frontend: `http://localhost:5173`
- API health: `http://localhost:8001/health`

## Configuration

The source of truth for runtime settings is `.env.example`.

Most commonly adjusted variables:
- `SNIPEBOT_DB_URL`
- `SNIPEBOT_API_PORT`
- `SNIPEBOT_FRONTEND_PORT`
- `VITE_API_BASE_URL` (build-time frontend API base; keep `/api` by default)
- `SNIPEBOT_MARKETPLACE_CHECK_INTERVAL_SECONDS` / `SNIPEBOT_MARKETPLACE_CHECK_JITTER_SECONDS` (search cadence per platform, default 600 ± 60)
- `SNIPEBOT_MARKETPLACE_ARCHIVE_ENABLED` (default `true`), `SNIPEBOT_MARKETPLACE_ARCHIVE_DIR` (default `/data/archive`), `SNIPEBOT_MARKETPLACE_ARCHIVE_IMAGE_SIZE` (default `original`; or a Marktplaats size code such as `85` = XXL), `SNIPEBOT_MARKETPLACE_ARCHIVE_DELAY_SECONDS` (default 3), `SNIPEBOT_MARKETPLACE_ARCHIVE_TICK_BUDGET_SECONDS` (default 45), `SNIPEBOT_MARKETPLACE_ARCHIVE_REFRESH_DAYS` (default 7)

Optional PostgreSQL/Timescale profile is available via the `db` service (`docker compose --profile postgres ...`).

## Daily operations

View status:

```bash
docker compose ps
```

Stream logs:

```bash
docker compose logs -f frontend api worker
```

Stop services (preserve volumes):

```bash
docker compose down
```

Stop and remove volumes (destructive):

```bash
docker compose down -v
```

## Troubleshooting

### Service unhealthy

```bash
docker compose ps
docker compose logs --tail=200 api worker frontend
```

### Port conflicts

Update `SNIPEBOT_API_PORT` and/or `SNIPEBOT_FRONTEND_PORT` in `.env`, then restart:

```bash
docker compose up -d --build
```

### Frontend reachable but API calls fail

- Check API health: `curl http://localhost:8001/health`
- Confirm `VITE_API_BASE_URL=/api` unless intentionally overridden
- Rebuild frontend image after changing build-time variables

## Local development (without Docker)

Backend API:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e "./backend[dev]"
uvicorn snipebot.main:app --app-dir backend/src --reload --port 8000
```

Worker:

```bash
python -m snipebot.worker
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

## Test commands

Backend:

```bash
pip install -e "./backend[dev]"
pytest backend/tests -q
```

Frontend:

```bash
cd frontend
npm install
npm run test
```

## Security notes

- Never commit `.env` with real secrets.
- Keep tokens and credentials in deployment/runtime secrets.
