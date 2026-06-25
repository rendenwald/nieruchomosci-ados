# STORY-18: Run tests, lint, build Docker image on push to main

## Problem

The project has no automated CI pipeline. Every push to `main` requires manual
linting, type-checking, testing, and Docker build verification. This slows
development and risks regressions reaching production.

## Goals

- Every push to `main` runs: ruff lint → mypy type check → pytest → Docker build
- Every PR against `main` runs: ruff lint → mypy type check → pytest
- Build artifacts (Docker images) are published only on `main` pushes
- CI uses the same tooling (`uv`, `ruff`, `mypy`, `pytest`) the project already uses

## Scope

| In scope | Out of scope |
|----------|-------------|
| `.github/workflows/ci.yml` — one workflow for the monorepo | ArgoCD deployment (STORY-20) |
| Ruff lint for both `src/real-estate-api` and `src/scrapper-base` | Docker image push to GHCR (STORY-19) |
| mypy type check for both projects | k8s manifest updates |
| pytest for both projects | Trivy security scan |
| Docker build for `real-estate-api` | Auto-rollback (STORY-21) |
| | PR preview deploys (STORY-22) |

## Acceptance Criteria

- **AC-1:** `.github/workflows/ci.yml` exists and is valid YAML
- **AC-2:** On push to `main`, workflow triggers: lint → type check → test → Docker build
- **AC-3:** On PR to `main`, workflow triggers: lint → type check → test (no Docker build)
- **AC-4:** Each project (`src/real-estate-api`, `src/scrapper-base`) is linted, type-checked, and tested independently
- **AC-5:** Docker build uses the existing `src/real-estate-api/Dockerfile` with root context
- **AC-6:** Workflow installs dependencies via `uv` (no pip, no poetry)
- **AC-7:** Lint uses `ruff check .` with the project's configured settings
- **AC-8:** Type check uses `mypy . --strict` (matching `pyproject.toml`)
- **AC-9:** Test uses `pytest -v` with the project's `asyncio_mode = auto` config
- **AC-10:** Workflow fails on first error (fail-fast matrix or sequential jobs)

## Risks & Dependencies

- Dockerfile expects `src/scrapper-base/` at the root — build context must be repo root
- scrapper-base is an editable dependency of real-estate-api; tests for real-estate-api need scrapper-base installed
- No Dockerfile for scrapper-base (it's a library, not a deployable service)
