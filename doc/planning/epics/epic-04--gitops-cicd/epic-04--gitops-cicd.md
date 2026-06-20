# Epic 04: GitOps + CI/CD

> **Goal:** Set up automated CI/CD pipeline with GitHub Actions, self-hosted Gitea registry, and ArgoCD GitOps deployment to k3s.

## Scope

- GitHub Actions CI pipeline (lint, test, build)
- Docker image build and push
- Gitea self-hosted container registry
- ArgoCD application definitions
- Auto-rollback on deploy failure
- PR preview deployments

## Success Criteria

- Push to `main` triggers: lint → test → build → push → deploy
- ArgoCD detects manifest changes and syncs automatically
- Failed deployments roll back to previous version

## Related Spec Modules

- `specs/140-GITOPS-CICD.md`
- `specs/020-ARCHITECTURE.md`

## Work Items

| ID | Title |
|----|-------|
| STORY-18 | Run tests, lint, build Docker image on push to main |
| STORY-19 | Push built image to self-hosted Gitea registry |
| STORY-20 | ArgoCD auto-sync deployment on image push |
| STORY-21 | Auto-rollback to previous version on deploy failure |
| STORY-22 | Run full test suite and preview deploy on PR |
