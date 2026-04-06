# SnipeBot (Foundation v1)

SnipeBot is a self-hosted price tracking project with a production-friendly Docker Compose runtime for Ubuntu servers.

## Current Scope

Included:
- frontend, backend API, and worker containers
- shared backend image for API + worker (different commands)
- SQLite persistence through Docker volume
- environment-driven runtime config
- health checks and practical container log rotation
- README deployment and troubleshooting guidance

Out of scope:
- Kubernetes
- cloud infrastructure automation
- distributed scaling
- external managed database

## Repository Structure

```text
frontend/                 React/Vite app shell
backend/src/snipebot/     FastAPI app and worker foundation
  api/                    HTTP routes
  domain/                 Domain rules (placeholder)
  persistence/            SQLite integration
  scheduler/              Worker loop
  adapters/               Future site adapters (interface seam)
  notifications/          Future notifier adapters (interface seam)
infra/docker/             Dockerfiles
```

## Quick Start (Ubuntu Docker server)

### 1) Environment setup

Copy the example file and edit values:

```bash
cp .env.example .env
```

### 2) Build and start

```bash
docker compose up -d --build
```

### 3) Check status and health

```bash
docker compose ps
curl http://localhost:8001/health
curl http://localhost:5173/api/health
```

Default endpoints:
- Frontend: http://localhost:5173
- API health: http://localhost:8001/health

### 4) Logs and stop

Logs:

```bash
docker compose logs -f frontend api worker
```

Stop services (keep data volume):

```bash
docker compose down
```

Stop and remove volumes (destructive for SQLite data):

```bash
docker compose down -v
```

## Service health checks and logs

Health checks used by Compose:
- `api`: HTTP `GET /health` inside container.
- `worker`: in-process DB readiness check (`check_db_ready()`).
- `frontend`: HTTP `GET /` from nginx container.

Interpretation:
- `healthy`: service check is passing.
- `starting`: grace period / retries still in progress.
- `unhealthy`: check failing repeatedly; inspect logs.

Log behavior:
- All services log to stdout/stderr.
- Compose json-file rotation is enabled (`max-size=10m`, `max-file=5`) per service.

Useful commands:

```bash
docker compose ps
docker compose logs --tail=200 api worker frontend
```

## Environment variables

Minimum required to run with defaults: copy `.env.example` and adjust only what you need.

### Core runtime
- `SNIPEBOT_ENV` (default: `production`)
- `SNIPEBOT_LOG_LEVEL` (default: `INFO`)
- `SNIPEBOT_DB_URL` (default: `sqlite:////data/snipebot.db`)
- `SNIPEBOT_WORKER_INTERVAL_SECONDS` (default: `60`)
- `SNIPEBOT_CHECK_INTERVAL_SECONDS` (default: `1800`)
- `SNIPEBOT_RETRY_INTERVAL_SECONDS` (default: `300`)
- `SNIPEBOT_WORKER_BATCH_SIZE` (default: `25`)

### Notification runtime (optional)
- `SNIPEBOT_NOTIFICATIONS_ENABLED`
- `SNIPEBOT_TELEGRAM_ENABLED`
- `SNIPEBOT_TELEGRAM_BOT_TOKEN` (**secret**)
- `SNIPEBOT_TELEGRAM_CHAT_ID`

### Compose host binding/ports
- `SNIPEBOT_API_BIND` (default: `127.0.0.1`)
- `SNIPEBOT_API_PORT` (default: `8001`)
- `SNIPEBOT_FRONTEND_BIND` (default: `0.0.0.0`)
- `SNIPEBOT_FRONTEND_PORT` (default: `5173`)

### Frontend build-time API base
- `VITE_API_BASE_URL` (default: `/api`)
  - Default works with built-in frontend container proxy (`/api` → `api:8000`).
  - Keep this as `/api` for easy future reverse-proxy setups.
  - Changing this value requires rebuilding frontend image.

### Secrets policy
- Do not commit `.env`.
- Keep real tokens only in deployment environment / local `.env`.
- `.env.example` must contain placeholders only.

## Volume expectations

- Compose defines a named volume: `sqlite_data`.
- API and worker mount it at `/data`.
- SQLite file path defaults to `/data/snipebot.db`.
- Data survives container rebuild/restart until volume is removed.

Backup example:

```bash
docker run --rm -v snipebot_sqlite_data:/data -v "$PWD":/backup alpine \
  sh -c "cp /data/snipebot.db /backup/snipebot.db.bak"
```

Restore example:

```bash
docker run --rm -v snipebot_sqlite_data:/data -v "$PWD":/backup alpine \
  sh -c "cp /backup/snipebot.db.bak /data/snipebot.db"
```

## Reverse proxy readiness

- The frontend container serves static files and proxies `/api/*` to the internal API service.
- For edge reverse proxy deployment later, you can expose only frontend publicly and keep API internal/private.
- Default API bind (`127.0.0.1`) already limits direct host access to localhost.

## Known limitations (v1)

- SQLite is single-node storage (no distributed failover/scaling).
- No built-in auth or multi-user isolation yet.
- No Kubernetes/cloud deployment manifests in this version.
- Scraper robustness and anti-bot handling are basic and site-dependent.
- Health checks validate process/readiness basics, not full functional correctness.

## Common troubleshooting

1. **Service not healthy**
   - `docker compose ps`
   - `docker compose logs --tail=200 api worker frontend`

2. **Port already in use**
   - Change `SNIPEBOT_API_PORT` and/or `SNIPEBOT_FRONTEND_PORT` in `.env`
   - Restart: `docker compose up -d --build`

3. **Frontend loads but API calls fail**
   - Verify API health: `curl http://localhost:8001/health`
   - Ensure `VITE_API_BASE_URL=/api` unless you intentionally changed topology
   - Rebuild frontend after changing build-time env: `docker compose build frontend`

4. **SQLite data missing after restart**
   - Confirm volume exists: `docker volume ls | grep sqlite_data`
   - Do not run `docker compose down -v` unless you intend to wipe data

5. **Clean rebuild for stuck images/containers**
   - `docker compose down`
   - `docker compose build --no-cache`
   - `docker compose up -d`

## Run without Docker (local development)

### Backend

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e "./backend[dev]"
uvicorn snipebot.main:app --app-dir backend/src --reload --port 8000
```

### Worker

```bash
python -m snipebot.worker
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## Tests

Backend:

```bash
pip install -e "./backend[dev]"
pytest backend/tests/test_adapters.py -q -k "hema"
pytest backend/tests -q
```

Frontend:

```bash
cd frontend
npm install
npm run test
```
