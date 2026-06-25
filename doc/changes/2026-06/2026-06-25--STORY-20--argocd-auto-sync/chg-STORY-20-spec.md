# STORY-20: ArgoCD auto-sync deployment on image push

## Problem

After STORY-19, the CI pipeline builds and pushes Docker images to GHCR, but
they are not deployed anywhere. Every deployment requires manual `kubectl`
commands. There is no GitOps workflow to automatically apply new images.

## Goals

- Define Kubernetes manifests for the FastAPI application (namespace,
  deployment, service)
- Define ArgoCD Application manifests for GitOps auto-sync
- Extend the CI pipeline to update the deployment manifest with the new
  image SHA after a successful push, committing the change back to the repo
  (with `[skip ci]` to prevent infinite loops)
- ArgoCD detects the manifest change and syncs automatically

## Scope

| In scope | Out of scope |
|----------|-------------|
| `k8s/namespaces/app.yaml` — Application namespace | Other service manifests (sveltekit, scrapers, storage, monitoring) |
| `k8s/app/fastapi-deployment.yaml` — API deployment | ArgoCD installation in the cluster |
| `k8s/app/services.yaml` — API service | Auto-rollback (STORY-21) |
| `k8s/argocd/app-of-apps.yaml` — ArgoCD root app | PR preview deploys (STORY-22) |
| `k8s/argocd/applications/backend-app.yaml` — Backend ArgoCD app | Multi-replica or HPA config |
| CI workflow: update manifest + commit after GHCR push | Ingress configuration |
| | TLS/cert-manager setup |

## Acceptance Criteria

- **AC-1:** `k8s/namespaces/app.yaml` exists with namespace `app-ns`
- **AC-2:** `k8s/app/fastapi-deployment.yaml` exists with:
  - 1 replica
  - Container image from `ghcr.io/rendenwald/nieruchomosci-ados`
  - `imagePullPolicy: Always`
  - Readiness and liveness probes on `/api/v1/health`
  - Resource limits (256m CPU, 512Mi memory)
- **AC-3:** `k8s/app/services.yaml` exposes the FastAPI deployment on port 8000
- **AC-4:** `k8s/argocd/app-of-apps.yaml` is a valid ArgoCD Application that
  references the applications directory
- **AC-5:** `k8s/argocd/applications/backend-app.yaml` deploys manifests from
  `k8s/app/` to namespace `app-ns`
- **AC-6:** After GHCR push, the CI workflow uses `sed` to update the image
  tag in `fastapi-deployment.yaml` and commits with `[skip ci]`
- **AC-7:** All YAML files are valid and parseable
- **AC-8:** ArgoCD Application uses `syncPolicy` with `automated: { prune: true, selfHeal: true }`

## Risks & Dependencies

- k3s cluster must exist (spec references `kubectl get nodes`)
- ArgoCD must be installed (one-time setup documented in spec)
- Image update commit uses `[skip ci]` to prevent infinite CI loops
- Only the FastAPI deployment is covered; other services will be added in
  subsequent stories
