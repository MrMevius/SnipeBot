## MODIFIED Requirements

### Requirement: Foundation runs in Docker Compose for local and self-hosted use
The system SHALL provide a Docker Compose configuration that starts `frontend`, `api`, and `worker` services with shared environment configuration, production-friendly runtime commands, and persistent SQLite volume wiring suitable for Ubuntu Docker server deployments.

#### Scenario: Compose starts core services
- **WHEN** the developer or operator runs `docker compose up --build`
- **THEN** frontend, api, and worker services start successfully
- **AND** API and worker share a backend image with service-specific commands
- **AND** backend processes use persistent SQLite storage mounted from a named volume

### Requirement: Foundation documents run and development instructions
The system SHALL include a README with setup, run, and test instructions for both local and Docker workflows, including deployment-oriented guidance for environment variables, volume expectations, and troubleshooting.

#### Scenario: README includes required commands
- **WHEN** a developer or operator reads the README
- **THEN** the README includes build/start commands and environment setup
- **AND** the README explains storage volume behavior and common troubleshooting steps
