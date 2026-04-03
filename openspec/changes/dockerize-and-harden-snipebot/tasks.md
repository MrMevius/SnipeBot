## 1. Compose and backend runtime hardening

- [x] 1.1 Convert `docker-compose.yml` to production-friendly service configuration (no dev bind mounts/reload commands, restart policies, logging options, and practical health checks).
- [x] 1.2 Ensure `api` and `worker` share the same backend image with distinct commands and persistent SQLite volume wiring.

## 2. Frontend production container

- [x] 2.1 Update frontend Dockerfile to build static assets and serve them from a production web server container.
- [x] 2.2 Configure frontend runtime to remain reverse-proxy-friendly for later deployment behind an edge proxy.

## 3. Environment contract and documentation

- [x] 3.1 Update `.env.example` to document deployment-safe defaults/placeholders and keep secrets out of repo.
- [x] 3.2 Update `README.md` with Ubuntu Docker deployment instructions including build/start commands, env variables, volume expectations, and common troubleshooting steps.

## 4. Verification and change artifact updates

- [x] 4.1 Run targeted verification commands for changed deployment assets and service build/start sanity.
- [x] 4.2 Record implementation summary and verification evidence in the active OPSX change spec.

## 5. Final v1 hardening polish

- [x] 5.1 Remove obvious dead deployment configuration/code paths that no longer apply to production compose runtime.
- [x] 5.2 Improve `.env.example` readability with grouped sections and clear optional/secret markers.
- [x] 5.3 Tighten README for operator-first deployment guidance and reduce ambiguity.
- [x] 5.4 Clarify healthcheck and logging behavior in docs so operators can quickly interpret service state.
- [x] 5.5 Add explicit known limitations section for v1 runtime/deployment.
