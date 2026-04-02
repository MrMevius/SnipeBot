# SnipeBot (Foundation v1)

SnipeBot is a self-hosted price tracking project. This change provides the initial foundation only:

- React + Vite frontend shell
- FastAPI backend shell
- SQLite configuration
- Docker Compose for local/self-hosted development
- Separate backend API and worker process entrypoints

## Current Scope

Included:
- frontend scaffold
- backend scaffold with explicit module boundaries
- `GET /health` endpoint
- SQLite wiring through environment variables
- Docker Compose setup (`frontend`, `api`, `worker`)

Not included yet:
- watchlist CRUD
- scraping adapters implementation
- notifications implementation
- target price logic
- authentication

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

## Environment Setup

Copy the example file:

```bash
cp .env.example .env
```

Variables:

- `SNIPEBOT_ENV`: runtime environment (`development` by default)
- `SNIPEBOT_LOG_LEVEL`: backend log level
- `SNIPEBOT_DB_URL`: SQLite URL (`sqlite:////data/snipebot.db` in Docker)
- `SNIPEBOT_WORKER_INTERVAL_SECONDS`: worker tick interval
- `SNIPEBOT_NOTIFICATIONS_ENABLED`: enable alert notification dispatch
- `SNIPEBOT_TELEGRAM_ENABLED`: enable Telegram notifier adapter
- `SNIPEBOT_TELEGRAM_BOT_TOKEN`: Telegram bot token
- `SNIPEBOT_TELEGRAM_CHAT_ID`: Telegram chat id to receive alerts
- `SNIPEBOT_API_PORT`: host port for API in Docker Compose (default `8001`)
- `VITE_API_BASE_URL`: frontend API base URL

## Run with Docker Compose

```bash
docker compose up --build
```

Services:
- API: http://localhost:8001
- Health: http://localhost:8001/health
- Frontend: http://localhost:5173

Stop:

```bash
docker compose down
```

## Run without Docker (local)

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
pytest backend/tests -q
```

Frontend:

```bash
cd frontend
npm install
npm run test
```
