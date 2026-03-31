## 1. Project scaffolding

- [x] 1.1 Create root-level project files for environment strategy and developer docs (`.env.example`, `.gitignore`, `README.md`).
- [x] 1.2 Scaffold frontend React/Vite TypeScript app with a minimal shell and backend health check integration.
- [x] 1.3 Scaffold backend FastAPI app with module boundaries (`api`, `domain`, `persistence`, `scheduler`, `adapters`, `notifications`).

## 2. Backend runtime foundation

- [x] 2.1 Implement backend configuration and SQLite setup using environment variables.
- [x] 2.2 Implement `GET /health` endpoint including a lightweight database readiness check.
- [x] 2.3 Add worker process entrypoint stub that runs independently from API process.

## 3. Containerized development setup

- [x] 3.1 Add backend and frontend Dockerfiles for development/runtime use.
- [x] 3.2 Add Docker Compose configuration for `frontend`, `api`, and `worker` services, including SQLite data volume.

## 4. Test and verification baseline

- [x] 4.1 Add backend tests for health endpoint and basic database connectivity behavior.
- [x] 4.2 Add frontend smoke test for minimal shell rendering.
- [x] 4.3 Run verification commands and capture results in change status notes.

## Current status

Completed.

## What changed

- Added a minimal backend foundation with FastAPI entrypoint, worker entrypoint, and explicit module boundaries for `api`, `domain`, `persistence`, `scheduler`, `adapters`, and `notifications`.
- Replaced deprecated FastAPI startup event usage with lifespan startup initialization to avoid deprecation warnings.
- Fixed frontend build configuration by switching `defineConfig` import to `vitest/config` so Vitest `test` config is type-valid during `tsc -b`.
- Added SQLite setup with environment-based configuration and a health check endpoint (`GET /health`) that reports API and DB readiness.
- Added a minimal React/Vite frontend shell that checks backend health.
- Added Dockerfiles and Docker Compose for `frontend`, `api`, and `worker`, plus SQLite volume wiring.
- Added initial backend and frontend smoke tests.
- Added root docs/config files: `.gitignore`, `.env.example`, and `README.md`.

## How to verify

1. `docker compose up --build -d`
2. `docker compose ps`
3. `curl http://localhost:8001/health`
4. `docker run --rm -v "/home/mevius/snipebot/backend/src:/app/backend/src" -v "/home/mevius/snipebot/backend/tests:/app/backend/tests" snipebot-api sh -lc "pip install --no-cache-dir pytest httpx && pytest /app/backend/tests -q"`
5. `cd frontend && npm install && npm run test`
6. `docker compose down`

## Verification evidence

- `docker compose up -d && docker compose ps` succeeded with `api`, `worker`, and `frontend` running; `api` healthy and bound to host port `8001`.
- `curl http://localhost:8001/health` returned `{"status":"ok","db_ready":true}`.
- Backend tests executed in container context passed: `2 passed`.
- Backend tests were rerun after lifespan fix and still passed: `2 passed`.
- Frontend tests passed once (`1 passed`) before disk filled; subsequent rerun failed with `ENOSPC` (environment disk-space limitation, not test assertion failure).
- Frontend build/test currently fail to run in this environment due `ENOSPC` (no disk space available for npm writes).
- After disk space was recovered, frontend checks passed in containerized Node environment: `npm ci && npm run test && npm run build` (tests: `1 passed`, Vite build successful).
