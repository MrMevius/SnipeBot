# SnipeBot

SnipeBot is a self-hosted price-tracking application with a Docker-first runtime (frontend, API, and worker) and configurable persistence.

## What this repository contains

- `frontend/` — React + Vite UI
- `backend/` — FastAPI API, worker, persistence, and adapters
- `infra/docker/` — Dockerfiles for backend and frontend
- `docker-compose.yml` — multi-service local/host deployment definition

## Prerequisites

- Docker Engine with Compose plugin (`docker compose`)
- Linux/macOS shell (or equivalent)

Optional for local non-Docker development:
- Python `>=3.12`
- Node.js + npm

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
