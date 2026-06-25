# STORY-19: Push built image to GHCR (GitHub Container Registry)

## Problem

The CI pipeline (STORY-18) builds Docker images but does not push them to any
registry. Built images are discarded after the workflow finishes. For ArgoCD to
deploy these images, they must be published to a container registry.

## Goals

- Every push to `main` builds and pushes a Docker image to GHCR
- The image is tagged with the commit SHA (immutable) and `latest` (mutable)
- Authentication uses `docker/login-action@v3` with `secrets.GITHUB_TOKEN`
- No additional secrets or PAT tokens are required

## Scope

| In scope | Out of scope |
|----------|-------------|
| Extend existing `.github/workflows/ci.yml` `docker` job with login + push | ArgoCD sync (STORY-20) |
| Push to `ghcr.io/rendenwald/nieruchomosci-ados:${{ github.sha }}` | Trivy security scan |
| Also push `ghcr.io/rendenwald/nieruchomosci-ados:latest` | Multi-architecture builds |
| `docker/login-action@v3` with `GITHUB_TOKEN` | k8s manifest updates |
| | Other service images (scraper, frontend) |

## Acceptance Criteria

- **AC-1:** On push to `main`, the Docker image is pushed to `ghcr.io/rendenwald/nieruchomosci-ados:${{ github.sha }}`
- **AC-2:** A `latest` tag is also pushed for convenience
- **AC-3:** Authentication uses `docker/login-action@v3` with `registry: ghcr.io` and `password: ${{ secrets.GITHUB_TOKEN }}`
- **AC-4:** The push happens **after** a successful build, as part of the existing `docker` job
- **AC-5:** No push occurs on PR builds (only on `main` pushes, matching existing `if: github.ref == 'refs/heads/main'` condition)
- **AC-6:** The workflow file is valid YAML

## Risks & Dependencies

- Depends on STORY-18's CI pipeline and Docker build step
- `GITHUB_TOKEN` has write access to GHCR for the current repository by default — no additional setup needed
- Image name `nieruchomosci-ados` must match the GitHub repository name for GHCR default permissions
