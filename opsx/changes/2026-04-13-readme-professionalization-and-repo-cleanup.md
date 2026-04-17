# Title
README professionalization and repository cleanup

## Context
The current root README contains useful information but is too broad for day-to-day developer onboarding and includes low-priority/legacy detail that reduces clarity. The repository also accumulates generated local artifacts that are not relevant to source control.

## Goals / Non-goals
### Goals
- Deliver a professional English developer README focused on installation and usage.
- Remove outdated/legacy guidance and keep only relevant operational instructions.
- Clean repository hygiene by ignoring and removing non-relevant generated local artifacts.

### Non-goals
- No feature development or runtime behavior changes.
- No API reference expansion beyond practical install/usage context.
- No infrastructure redesign.

## Proposed approach
- Rewrite `README.md` into a concise developer-oriented structure.
- Keep content aligned to actual repository/runtime files (`docker-compose.yml`, `.env.example`, current scripts).
- Tighten `.gitignore` for generated local artifacts and remove currently untracked noise directories.

## Implementation steps
1. Review current repository runtime/config sources.
2. Rewrite root README with a focused install/usage flow.
3. Remove legacy/noise content from README and improve professional tone.
4. Add missing ignore rules for local generated artifacts.
5. Remove currently present non-relevant local artifact directories.
6. Validate via lightweight content/repo checks and document evidence.

## Acceptance criteria
- Root README is fully updated in professional English.
- README remains developer-focused and centered on install + usage.
- Legacy/outdated instructions are removed.
- Non-relevant repository artifacts are cleaned/ignored.
- Change spec is updated with what changed, verification steps/evidence, and final status.

## Testing plan
- Run lightweight verification commands for README structure/relevance.
- Validate repository cleanliness with git status and ignore checks.
- For this docs/hygiene change, no functional runtime tests are required.

## Risk + rollback plan
- Risk: over-trimming may remove context some contributors still use.
- Mitigation: keep essential operational sections (quick start, config, troubleshooting, local dev, testing).
- Rollback: restore previous `README.md` and `.gitignore` from git history.

## Notes / links
- Main doc: `README.md`
- Runtime source of truth: `docker-compose.yml`, `.env.example`

## Current status
Completed

## What changed
- Rewrote root `README.md` into a concise, professional English developer guide focused on installation and usage.
- Removed broad/legacy-style narrative and retained only relevant sections for daily developer operation:
  - quick start,
  - configuration,
  - run/stop/log workflows,
  - troubleshooting,
  - local development,
  - test commands,
  - secrets/security notes.
- Updated `.gitignore` to exclude non-relevant generated artifacts:
  - `.tmp/`, `.tools/`, `.ruff_cache/`, `*.egg-info/`, `frontend/dist-local/`.
- Cleaned existing local untracked artifact directories from the workspace:
  - `.tmp/`, `.tools/`, `backend/src/snipebot_backend.egg-info/`, `frontend/dist-local/`.

## How to verify
- `rg -n "^## " README.md`
- `rg -n "legacy|deprecated|old|TODO|WIP" README.md`
- `rg -n "services:|frontend:|api:|worker:" docker-compose.yml`
- `rg -n "SNIPEBOT_|VITE_" .env.example`
- `git status --short`
- `git ls-files | rg "(\.tmp/|\.venv/|\.ruff_cache/|dist-local|\.egg-info/)"`

## Verification evidence
- README section structure check returned 9 clear top-level sections (`What this repository contains` through `Security notes`).
- Legacy/noise keyword scan in `README.md` returned no matches.
- Runtime references validated:
  - `docker-compose.yml` contains `services`, `api`, `worker`, `frontend`.
  - `.env.example` exposes expected `SNIPEBOT_*` and `VITE_API_BASE_URL` keys.
- `git status --short` shows only intended changes:
  - `M .gitignore`
  - `M README.md`
  - `?? opsx/changes/2026-04-13-readme-professionalization-and-repo-cleanup.md`
- `git ls-files | rg "(\.tmp/|\.venv/|\.ruff_cache/|dist-local|\.egg-info/)"` returned no tracked matches.
