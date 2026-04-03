# docker-runtime-deployment Specification

## Purpose
TBD - created by archiving change dockerize-and-harden-snipebot. Update Purpose after archive.
## Requirements
### Requirement: Compose deployment SHALL run frontend, API, and worker services in one file
The system SHALL provide a single Docker Compose configuration for v1 that defines `frontend`, `api`, and `worker` services with shared network communication and environment loading.

#### Scenario: Operator starts all core services with one command
- **WHEN** an operator runs `docker compose up -d --build`
- **THEN** `frontend`, `api`, and `worker` containers are created from the compose file
- **AND** each service enters a running or healthy state when dependencies are satisfied

### Requirement: API and worker SHALL share one backend image with different commands
The system SHALL build one backend image used by both API and worker services, with API and worker processes selected through service-level command configuration.

#### Scenario: Shared image with separate processes
- **WHEN** compose services are inspected after build
- **THEN** `api` and `worker` reference the same backend build target
- **AND** `api` runs the API server command while `worker` runs the worker entrypoint command

### Requirement: Runtime SHALL persist SQLite data in a named volume
The system SHALL mount a named volume for backend SQLite storage and use a stable SQLite path under `/data` for API and worker runtime.

#### Scenario: Data persists across container restarts
- **WHEN** services are restarted or re-created without removing volumes
- **THEN** existing SQLite data remains available to API and worker
- **AND** watchlist and check history data are preserved

### Requirement: Runtime configuration SHALL be environment-driven without committed secrets
The system SHALL document and load runtime configuration from environment variables and SHALL keep secret values out of version-controlled files.

#### Scenario: Safe configuration handoff
- **WHEN** an operator prepares deployment configuration
- **THEN** `.env.example` provides variable names and placeholders only
- **AND** `.env` is used for real secrets and is not committed to the repository

### Requirement: Services SHALL include practical health checks and log controls
The system SHALL define health checks where practical for frontend/API/worker services and SHALL configure container log rotation defaults to avoid unbounded log file growth.

#### Scenario: Health and log controls are visible in compose
- **WHEN** an operator inspects compose service definitions
- **THEN** each service has a practical health check strategy appropriate to its process type
- **AND** services include logging options that cap per-file size and retained file count

### Requirement: Deployment documentation SHALL include operator essentials
The system SHALL document build/start commands, environment variables, volume expectations, and common troubleshooting steps for Ubuntu Docker deployment.

#### Scenario: Operator can deploy and debug from README
- **WHEN** an operator follows README deployment instructions
- **THEN** they can build and start services successfully
- **AND** they can identify volume behavior and use troubleshooting commands for common failures

