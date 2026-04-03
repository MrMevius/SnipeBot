## Why

SnipeBot’s current container setup is development-oriented and not reliably runnable as a production-like deployment on an Ubuntu Docker server. We need a practical v1 deployment baseline that is stable, documented, and easy to place behind a reverse proxy.

## What Changes

- Replace the current dev-biased Docker Compose behavior with a production-friendly single-file Compose setup for `frontend`, `api`, and `worker`.
- Build a production frontend container that serves compiled static assets instead of running a development server.
- Keep backend API and worker on a shared backend image with distinct runtime commands.
- Ensure persistent SQLite storage via a named Docker volume and stable DB path.
- Standardize environment variable handling with a safe `.env.example` contract and no secrets committed to repo.
- Add practical service health checks and restart policies to improve startup/readiness sanity.
- Add practical log rotation configuration in Compose.
- Expand README with Ubuntu deployment instructions, environment variables, volume expectations, and common troubleshooting.

## Capabilities

### New Capabilities
- `docker-runtime-deployment`: Production-friendly containerized runtime for SnipeBot on Ubuntu Docker server, including frontend/api/worker topology, persistence, env handling, readiness checks, and operator documentation.

### Modified Capabilities
- `bootstrap-foundation`: Deployment/runtime requirements are extended from local/dev Compose expectations to include production-oriented container behavior and operational guidance.

## Impact

- Affected files include `docker-compose.yml`, Dockerfiles under `infra/docker/`, `.env.example`, and root `README.md`.
- Operational behavior changes from dev-mode containers (`--reload`, Vite dev server, source bind mounts) to production-style runtime containers.
- No Kubernetes/cloud/distributed scaling/external database changes are introduced.
