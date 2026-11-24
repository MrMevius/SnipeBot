# SnipeBot

SnipeBot is a self-hosted price-tracking application with a Docker-first runtime (frontend, API, and worker) and configurable persistence.

## What this repository contains

- `frontend/` — React + Vite UI
- `backend/` — FastAPI API, worker, persistence, and adapters
- `infra/docker/` — Dockerfiles for backend and frontend
- `docker-compose.yml` — multi-service local/host deployment definition

## Marktplaats searches

Besides product pages, SnipeBot can watch Marktplaats.nl searches (e.g. a specific car):

1. Set up the search on marktplaats.nl (category, brand/model, year, mileage, price, distance…).
2. Open **Marktplaats** in SnipeBot, paste the results URL, optionally add exclude words and a seller filter, click **Preview** and compare the filters and count with the website, then **Save search**.
3. The first check records the current listings silently. Afterwards the worker checks every ~10 minutes and sends a Telegram message (with photo) for each new matching listing and for price drops.
4. Set an **alert price ceiling** per search: Telegram only alerts for new listings and price drops at or below it (listings without a price never alert). Without a ceiling the search records and archives listings but sends no alerts.

Telegram uses the same notification settings as the watchlist (Settings → Telegram).

### Listing archive

Every listing a saved search records is also archived locally, so it stays available when Marktplaats removes or changes it:

- The worker fetches each listing page and stores title, price, description, all attributes, seller details, statistics and **all photos** as originally uploaded (no resizing, ~150–300 KB each). Fetching is throttled (one listing per ~3 s, at most ~45 s per worker tick) and pauses with increasing backoff when Marktplaats blocks requests.
- A listing is fetched again when its price or title changes in the search results and otherwise weekly while it is online. A new version is stored only when the content changed; photos are only added, a photo removed from the listing is kept and marked as removed.
- Listings in a search link to SnipeBot's own listing page (`/archive/<id>`) with gallery, description, attributes, seller, price history and version history (including description diffs). **Archive** in the menu lists all archived listings across searches (search, filter, sort) and shows the storage used.
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
- `SNIPEBOT_MARKETPLACE_CHECK_INTERVAL_SECONDS` / `SNIPEBOT_MARKETPLACE_CHECK_JITTER_SECONDS` (Marktplaats search cadence, default 600 ± 60)
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
