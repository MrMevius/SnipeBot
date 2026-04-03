## Context

SnipeBot currently runs with a Docker Compose setup that is tuned for local development (source bind mounts, API `--reload`, frontend dev server). The target deployment environment is an Ubuntu Docker server where the application must be stable as long-running containers and easy to place behind a reverse proxy later.

The requested v1 scope keeps architecture simple: one Compose file, three services (`frontend`, `api`, `worker`), SQLite persistence, environment-driven configuration, practical health checks/logging, and clear deployment documentation. It explicitly excludes Kubernetes, cloud infrastructure, distributed scaling, and external managed databases.

## Goals / Non-Goals

**Goals:**
- Produce a production-friendly single-file Compose topology for Ubuntu Docker deployment.
- Run API and worker from a shared backend image with distinct commands.
- Build and serve frontend as static assets in a runtime web server container.
- Persist SQLite data in a named Docker volume.
- Keep secrets out of version control while documenting required runtime environment variables.
- Add health checks and practical logging defaults for operators.
- Provide README deployment instructions including build/start, envs, volume behavior, and troubleshooting.

**Non-Goals:**
- Kubernetes manifests or Helm charts.
- Cloud-provider infrastructure setup.
- Horizontal/distributed scaling design.
- Migration to Postgres or managed database services.

## Decisions

1. **Single compose file for v1**
   - Use only `docker-compose.yml` to match the requested simplicity.
   - Keep service definitions production-oriented by default (no source code bind mounts, no dev reload commands).

2. **Shared backend image for API and worker**
   - Build one backend image from `infra/docker/backend.Dockerfile`.
   - Use service-level commands for `uvicorn` API process and `python -m snipebot.worker` worker process.
   - This keeps build maintenance low while preserving process isolation.

3. **Frontend served as static build output**
   - Use a multi-stage frontend Dockerfile: build with Node, serve with nginx runtime.
   - Provide reverse-proxy-friendly behavior by keeping frontend externally exposed and keeping API/worker internal by default in docs.

4. **Persistent SQLite via named volume**
   - Mount named volume at `/data` for API and worker.
   - Keep `SNIPEBOT_DB_URL=sqlite:////data/snipebot.db` as canonical Docker runtime value.

5. **Health checks where practical**
   - API: HTTP `/health` check.
   - Frontend: HTTP `/` check.
   - Worker: command-based process/DB sanity check (no new HTTP endpoint required).

6. **Operational logging defaults in Compose**
   - Use json-file logging options with `max-size` and `max-file` to prevent unbounded disk growth.

7. **Secrets handling**
   - `.env` remains ignored and never committed.
   - `.env.example` documents placeholders and non-secret defaults only.

## Risks / Trade-offs

- **[Risk] Frontend-to-API connectivity mismatch in deployments** → Mitigation: document env strategy and reverse proxy pattern clearly in README.
- **[Risk] Worker healthcheck may be less expressive than HTTP health endpoint** → Mitigation: use practical command healthcheck and rely on logs for deeper diagnostics.
- **[Trade-off] Single-file Compose keeps setup simple but less profile flexibility** → Accepted for v1; can introduce overrides in later iterations.
- **[Risk] SQLite file contention if misconfigured paths differ between API/worker** → Mitigation: shared named volume and shared default DB URL in compose.

## Migration Plan

1. Update Dockerfiles and compose definitions.
2. Update `.env.example` and README operator docs.
3. Build and run containers with compose on local Linux test environment.
4. Validate health checks and persistence behavior.
5. Rollout to Ubuntu server using documented commands.

Rollback:
- Revert to prior compose/Dockerfile commit and redeploy previous images.
- Preserve `sqlite_data` volume unless explicit destructive reset is required.

## Open Questions

- None for v1 scope; follow-up hardening (e.g., stricter runtime security constraints) can be tracked in a separate change.
