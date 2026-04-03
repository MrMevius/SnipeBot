# Title
Dockerize and harden SnipeBot runtime for Ubuntu Docker server

## Context
Current SnipeBot containers were development-oriented (`--reload`, source bind mounts, Vite dev server) and not reliable as a production-like Ubuntu Docker deployment. This change provides a pragmatic v1 runtime topology that keeps operations simple while improving startup sanity, persistence, and documentation.

## Goals / Non-goals
### Goals
1. Provide a production-friendly single `docker-compose.yml` setup for `frontend`, `api`, and `worker`.
2. Keep `api` and `worker` on a shared backend image with different commands.
3. Persist SQLite data in a Docker named volume.
4. Use environment variable configuration with secrets kept out of repo.
5. Add practical health checks and log rotation settings.
6. Keep runtime easy to put behind a reverse proxy later.
7. Document deployment flow and troubleshooting in README.

### Non-goals
1. Kubernetes manifests.
2. Cloud infrastructure automation.
3. Distributed scaling design.
4. External managed database migration.

## Proposed approach
1. Convert `docker-compose.yml` from dev defaults to production-friendly defaults.
2. Build frontend assets in Docker and serve with nginx runtime container.
3. Keep backend Dockerfile reusable for API and worker processes.
4. Wire persistent SQLite via named volume mounted at `/data`.
5. Add health checks/logging limits per service.
6. Expand `.env.example` and README deployment documentation.

## Implementation steps (ordered)
1. Update `docker-compose.yml` with restart policies, logging options, healthchecks, and production commands.
2. Ensure API and worker share backend image and data volume.
3. Update `infra/docker/frontend.Dockerfile` to multi-stage build + nginx runtime.
4. Add nginx config to proxy `/api/*` to internal API service.
5. Update `.env.example` with deployment-safe defaults and port/bind variables.
6. Update `README.md` with build/start commands, env vars, volume expectations, and troubleshooting.
7. Verify compose config/build/start/health and proxy behavior.
8. Perform final v1 hardening polish (remove obvious dead deployment config, improve `.env.example`, tighten README wording, and document v1 limitations).

## Acceptance criteria
1. A single compose file starts `frontend`, `api`, and `worker` in production-friendly mode.
2. API and worker use the same backend image with different commands.
3. SQLite file persists under a named volume and is shared between API and worker.
4. Health checks exist where practical for API, worker, and frontend.
5. Compose logging is configured with bounded rotation settings.
6. Secrets are not committed; `.env.example` contains placeholders/defaults only.
7. Frontend runtime is reverse-proxy-friendly and can route API calls via `/api`.
8. README includes required deployment and troubleshooting sections.
9. README includes a concise “known limitations (v1)” section.

## Testing plan
```bash
docker compose config
docker compose build
docker compose up -d
docker compose ps
curl http://localhost:8001/health
curl http://localhost:5173/api/health
docker compose down
```

## Risk + rollback plan
### Risks
1. Runtime permission issues for SQLite volume.
2. Frontend/API connectivity mismatch from build-time env config.
3. Healthcheck false negatives due endpoint/binding mismatch.

### Mitigations
1. Validate compose startup and DB write path in live container checks.
2. Keep default `VITE_API_BASE_URL=/api` plus nginx `/api` proxy.
3. Verify health checks with explicit localhost/127.0.0.1 endpoints.

### Rollback
1. Revert Docker/compose/README changes to previous commit.
2. Rebuild and redeploy prior images.
3. Keep `sqlite_data` volume intact unless data reset is intentional.

## Notes / links
- OpenSpec change: `openspec/changes/dockerize-and-harden-snipebot/`

## Current status
Completed

## What changed
- Converted `docker-compose.yml` to production-friendly defaults:
  - removed source bind mounts and API reload mode,
  - added restart policies,
  - added practical healthchecks for API/worker/frontend,
  - added per-service log rotation (`max-size`, `max-file`),
  - kept one-file topology for `frontend`, `api`, `worker`.
- Kept API and worker on shared backend image (`snipebot-backend:latest`) with distinct commands.
- Updated backend Dockerfile for stable runtime packaging and shared image use.
- Replaced frontend dev-server Dockerfile with multi-stage build + nginx runtime static serving.
- Added nginx config (`infra/docker/frontend.nginx.conf`) including `/api` reverse proxy to internal API service.
- Added `.dockerignore` to reduce build context and avoid shipping secrets like `.env` into build context.
- Expanded `.env.example` with deployment-safe defaults, bind/port variables, and build-time frontend API variable guidance.
- Reworked root README deployment guidance:
  - build/start commands,
  - environment variable reference,
  - volume expectations + backup/restore examples,
  - reverse proxy readiness notes,
  - troubleshooting checklist.
- Final v1 hardening polish updates:
  - removed `frontend` `env_file` from compose as dead runtime config for nginx-based container,
  - improved `.env.example` readability with grouped sections and secret/optional hints,
  - tightened README quickstart and clarified healthcheck/logging semantics,
  - added explicit `Known limitations (v1)` section.

## How to verify
1. `docker compose config`
2. `docker compose build`
3. `docker compose up -d`
4. `docker compose ps`
5. `curl -fsS http://localhost:8001/health`
6. `curl -fsS http://localhost:5173/api/health`
7. `docker compose down`

## Verification evidence
- `docker compose config`: succeeded; service definitions include healthchecks, log rotation, named volume, and shared backend image.
- `docker compose build`: succeeded for backend and frontend images.
- First `docker compose up -d` failed due SQLite write permissions (`attempt to write a readonly database`) after initial non-root backend container attempt.
- Adjusted backend runtime user strategy in Dockerfile and redeployed.
- `docker compose up -d` + `docker compose ps`: API and worker reached `healthy`; frontend healthcheck was initially failing due `localhost` resolution behavior.
- Updated frontend healthcheck to `http://127.0.0.1/` and recreated frontend; frontend reached `healthy`.
- `curl -fsS http://localhost:8001/health`: returned `{"status":"ok","db_ready":true}`.
- `curl -fsS http://localhost:5173/api/health`: returned `{"status":"ok","db_ready":true}` confirming frontend `/api` proxy path.
- Re-ran full compose sanity after final hardening polish:
  - `docker compose config`: succeeded,
  - `docker compose up -d --build`: succeeded,
  - `docker compose ps`: api healthy; frontend/worker initially in `starting` status during warmup,
  - `curl -fsS http://localhost:8001/health`: returned `{"status":"ok","db_ready":true}`,
  - `curl -fsS http://localhost:5173/api/health`: returned `{"status":"ok","db_ready":true}`,
  - `docker compose down`: succeeded.
