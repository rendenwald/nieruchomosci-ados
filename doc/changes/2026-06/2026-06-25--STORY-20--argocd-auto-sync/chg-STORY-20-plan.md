# STORY-20: Implementation Plan

## Files to Create

### `k8s/namespaces/app.yaml`
```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: app-ns
```

### `k8s/app/fastapi-deployment.yaml`
- 1 replica, image `ghcr.io/rendenwald/nieruchomosci-ados`
- imagePullPolicy: Always
- Readiness probe: HTTP GET /api/v1/health port 8000
- Liveness probe: HTTP GET /api/v1/health port 8000
- Resources: requests 128m/256Mi, limits 256m/512Mi
- Environment from `config-secret` (placeholder)

### `k8s/app/services.yaml`
- ClusterIP service, selector `app: fastapi`, port 8000

### `k8s/argocd/app-of-apps.yaml`
- ArgoCD Application in `gitops-ns` namespace
- Source: repo URL, path `k8s/argocd/applications/`
- Destination: cluster `https://kubernetes.default.svc`
- Automated sync with prune + selfHeal

### `k8s/argocd/applications/backend-app.yaml`
- ArgoCD Application for backend
- Source: repo URL, path `k8s/app/`
- Destination: namespace `app-ns`
- Automated sync with prune + selfHeal

## Files to Modify

### `.github/workflows/ci.yml`
After the GHCR push steps, add:
```yaml
      - name: Update k8s manifest with new image SHA
        run: |
          sed -i "s|image: ghcr.io/rendenwald/nieruchomosci-ados:.*|image: ghcr.io/rendenwald/nieruchomosci-ados:${{ github.sha }}|" \
            k8s/app/fastapi-deployment.yaml

      - name: Commit and push manifest update
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add k8s/app/fastapi-deployment.yaml
          git commit -m "ci: update image to ${{ github.sha }} [skip ci]" || echo "No changes to commit"
          git push
```

### `doc/planning/backlog.md`
Mark STORY-20 as `done`

## Verification
1. `python3 -c "import yaml; yaml.safe_load(open('k8s/namespaces/app.yaml')); print('Valid')"`
2. All k8s yamls parse correctly
3. Workflow yaml still valid
4. `git diff --name-only` shows expected changes
