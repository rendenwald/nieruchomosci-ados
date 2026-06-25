# STORY-21: Auto-rollback to previous version on deploy failure

## Problem

When a new image is deployed and fails health checks, there is no automated
mechanism to roll back to the previous working version. Manual intervention
is required, increasing downtime.

## Goals

- Track the previous image SHA via a `bigpickle/previous-image` annotation
  on the FastAPI deployment
- Update the annotation automatically during CI manifest updates
- Document ArgoCD rollback procedures
- Add rollback-related items to the verification checklist

## Scope

| In scope | Out of scope |
|----------|-------------|
| Extend CI to capture previous image before updating to new SHA | Automated rollback in CI (detects failure) |
| Add `bigpickle/previous-image` update in CI workflow | Rollback of other services (scrapers, etc.) |
| Document rollback commands in AGENTS.md checklist | CronJob rollback configuration |
| Add verification checklist items from FIX-13 | |

## Acceptance Criteria

- **AC-1:** Before CI updates the image SHA in `fastapi-deployment.yaml`, it
  captures the current SHA to `bigpickle/previous-image` annotation
- **AC-2:** The annotation is updated in the same CI step as the image SHA
- **AC-3:** AGENTS.md verification checklist includes:
  - `[ ] Is the previous image SHA noted in the deployment annotation for fast rollback?`
  - `[ ] Are changes reversible without a data migration?`
  - `[ ] If DB migration — does a `down` revision exist?`
- **AC-4:** `k8s/app/fastapi-deployment.yaml` has the working annotation

## Risks & Dependencies

- Requires CI to have write access to the repo (already configured)
- k3s + ArgoCD must be operational for actual rollback to work
