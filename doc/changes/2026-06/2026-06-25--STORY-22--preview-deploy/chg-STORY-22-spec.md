# STORY-22: Run full test suite and preview deploy on PR

## Problem

Pull requests should be validated with a full test suite and, optionally,
deployed to a preview environment before merging. This catches regressions
before they reach production.

## Goals

- Full test suite (ruff lint, mypy type check, pytest) runs on every PR
- Preview deployment workflow exists for PRs, ready to use once k3s cluster
  is operational
- Preview namespace is cleaned up when PR is closed/merged

## Scope

| In scope | Out of scope |
|----------|-------------|
| Document that `quality` job already runs on PRs | k3s cluster setup |
| Create preview-deploy workflow stub that builds + deploys PR images | Ingress/TLS for preview URLs |
| Create cleanup workflow (PR closed → delete namespace) | |
| Add PR comment with preview URL after deploy | |

## Acceptance Criteria

- **AC-1:** CI workflow runs `quality` job on every PR commit (already implemented)
- **AC-2:** `.github/workflows/preview-deploy.yml` exists with:
  - Trigger: PR opened, synchronize, reopened
  - Build and push PR-specific image to GHCR
  - Deploy to `preview-{pr-number}` namespace via kubectl
  - Comment preview URL on PR
- **AC-3:** `.github/workflows/preview-cleanup.yml` exists with:
  - Trigger: PR closed
  - Delete `preview-{pr-number}` namespace
- **AC-4:** Workflow YAMLs are valid

## Risks & Dependencies

- Preview deploy requires k3s cluster with kubectl configured in CI
- Preview cleanup requires GitHub token with repo write access
