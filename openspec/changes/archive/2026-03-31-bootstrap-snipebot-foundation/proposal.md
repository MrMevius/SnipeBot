## Why

SnipeBot needs a minimal but runnable foundation so development can proceed with fast feedback in local Docker and on a small Ubuntu host. Creating this baseline now reduces setup churn and keeps future feature work focused on product behavior instead of project plumbing.

## What Changes

- Scaffold a React + Vite frontend with a minimal shell page.
- Scaffold a FastAPI backend with clear module boundaries and a health endpoint.
- Add SQLite integration setup for local/self-hosted persistence.
- Add Docker Compose setup for frontend + backend API + backend worker processes.
- Add a simple, explicit environment variable strategy for frontend and backend.
- Add README instructions for local and Docker-based development.

## Capabilities

### New Capabilities
- `bootstrap-foundation`: Establish the initial runnable SnipeBot foundation and development workflow.

### Modified Capabilities
- None.

## Impact

- Adds initial repository code structure for frontend, backend, tests, and containerization.
- Introduces baseline Python and Node dependencies.
- Defines first developer workflow and run/test commands in README.
