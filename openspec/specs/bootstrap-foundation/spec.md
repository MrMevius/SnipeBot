## Purpose

Define the minimum runnable SnipeBot foundation for solo self-hosted v1 development.
## Requirements
### Requirement: Backend foundation exposes a health endpoint
The system SHALL provide a FastAPI backend service with a health endpoint to report service and database readiness.

#### Scenario: Health endpoint returns healthy response
- **WHEN** a client sends `GET /health`
- **THEN** the API responds with HTTP 200 and a JSON payload containing `status: "ok"`

### Requirement: Foundation includes explicit backend module boundaries
The system SHALL organize backend code into explicit modules for `api`, `domain`, `persistence`, `scheduler`, `adapters`, and `notifications`.

#### Scenario: Backend structure is present
- **WHEN** a developer inspects the backend source tree
- **THEN** the source tree includes directories for each required module boundary

### Requirement: Foundation runs in Docker Compose for local and self-hosted use
The system SHALL provide a Docker Compose configuration that starts `frontend`, `api`, and `worker` services with shared environment configuration, production-friendly runtime commands, and persistent SQLite volume wiring suitable for Ubuntu Docker server deployments.

#### Scenario: Compose starts core services
- **WHEN** the developer or operator runs `docker compose up --build`
- **THEN** frontend, api, and worker services start successfully
- **AND** API and worker share a backend image with service-specific commands
- **AND** backend processes use persistent SQLite storage mounted from a named volume

### Requirement: Foundation uses SQLite configuration for v1
The system SHALL provide SQLite integration setup for the backend process using an environment-configurable database URL.

#### Scenario: Backend uses configured SQLite URL
- **WHEN** `SNIPEBOT_DB_URL` is set to a SQLite URL
- **THEN** backend startup initializes database connectivity without requiring an external database service

### Requirement: Foundation provides minimal frontend shell
The system SHALL provide a React + Vite frontend shell page suitable for validating connectivity to the backend.

#### Scenario: Frontend shell renders
- **WHEN** the frontend is opened in a browser
- **THEN** the app renders a basic SnipeBot foundation page

### Requirement: Foundation documents run and development instructions
The system SHALL include a README with setup, run, and test instructions for both local and Docker workflows, including deployment-oriented guidance for environment variables, volume expectations, and troubleshooting.

#### Scenario: README includes required commands
- **WHEN** a developer or operator reads the README
- **THEN** the README includes build/start commands and environment setup
- **AND** the README explains storage volume behavior and common troubleshooting steps

