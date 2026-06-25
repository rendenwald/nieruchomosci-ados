# STORY-20: Test Plan

## Pre-merge Verification

| # | Test | Method | Expected |
|---|------|--------|----------|
| TP-1 | All k8s YAML files parse correctly | `python3 -c "import yaml; yaml.safe_load(...)"` | All valid |
| TP-2 | CI workflow YAML valid | `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"` | Valid |
| TP-3 | Namespace manifest has correct name | YAML review | `name: app-ns` |
| TP-4 | Deployment has probes | YAML review | readinessProbe + livenessProbe on `/api/v1/health` |
| TP-5 | Deployment image matches GHCR | YAML review | `ghcr.io/rendenwald/nieruchomosci-ados:latest` |
| TP-6 | ArgoCD app-of-apps points to applications dir | YAML review | `path: k8s/argocd/applications` |
| TP-7 | ArgoCD backend-app points to k8s/app | YAML review | `path: k8s/app` |
| TP-8 | CI has manifest update step after push | YAML review | `sed -i` + `git commit` with `[skip ci]` |
| TP-9 | CI uses `[skip ci]` to prevent infinite loop | YAML review | Commit message contains `[skip ci]` |
| TP-10 | ArgoCD apps have automated syncPolicy | YAML review | `syncPolicy.automated` with `prune: true, selfHeal: true` |

## Post-merge Validation

After merge to `main`:
- GHCR push triggers manifest update commit
- Verify workflow run on main completes without errors
- Check that `k8s/app/fastapi-deployment.yaml` has correct SHA in main
