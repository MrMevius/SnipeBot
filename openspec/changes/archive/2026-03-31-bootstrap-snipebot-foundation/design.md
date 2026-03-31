## Context

The repository currently has OpenSpec configuration but no application code. The v1 foundation must prioritize simplicity for a solo operator while preserving clear seams for future adapters and notifier implementations.

## Goals / Non-Goals

**Goals:**
- Create a small runnable frontend/backend foundation.
- Provide separate backend process entrypoints for API and worker.
- Use SQLite for v1 with straightforward initialization.
- Keep module boundaries explicit: api, domain, persistence, scheduler, adapters, notifications.
- Support local/self-hosted development through Docker Compose.

**Non-Goals:**
- Product watchlist CRUD.
- Scraping implementations.
- Notification sending implementations.
- Authentication and multi-user behavior.
- Reverse proxy production setup.

## Decisions

1. **Single backend codebase, two process entrypoints (API + worker).**
   - Rationale: keeps deployment simple while allowing scheduler logic to evolve independently.
   - Alternative considered: separate service repos/process architectures, rejected as unnecessary for v1.

2. **SQLite via SQLAlchemy with minimal startup initialization.**
   - Rationale: enough for solo v1 and easy to run in Docker volume.
   - Alternative considered: Postgres from day one, rejected to avoid extra moving parts.

3. **Minimal interface seams only where near-term value is obvious.**
   - Keep abstract base placeholders for site adapters and notifier adapters.
   - Avoid introducing command/query/event layers before real use cases exist.

4. **Compose with three services: frontend, api, worker.**
   - Rationale: mirrors target runtime shape and validates process split early.

## Risks / Trade-offs

- **[SQLite write contention in future]** → Keep transactions short; migrate to Postgres when concurrent writes become meaningful.
- **[Worker does little in foundation phase]** → Accept temporary simplicity; adds low-cost seam for upcoming scheduler tasks.
- **[Early abstractions may drift]** → Limit abstractions to adapter and notifier interfaces only.
