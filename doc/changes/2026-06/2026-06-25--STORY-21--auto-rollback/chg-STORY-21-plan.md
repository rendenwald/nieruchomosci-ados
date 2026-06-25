# STORY-21: Implementation Plan

## Files to Modify

### `.github/workflows/ci.yml`
Extend the "Update k8s manifest" step to first capture the current image SHA
into the `bigpickle/previous-image` annotation before updating to the new SHA.

Current:
```yaml
      - name: Update k8s manifest with new image SHA
        run: |
          sed -i "s|image: ghcr.io/rendenwald/nieruchomosci-ados:.*|image: ghcr.io/rendenwald/nieruchomosci-ados:${{ github.sha }}|" \
            k8s/app/fastapi-deployment.yaml
```

New:
```yaml
      - name: Update k8s manifest with new image SHA
        run: |
          # Capture current image as previous-image for rollback
          CURRENT_IMAGE=$(sed -n 's/.*image: ghcr.io\/rendenwald\/nieruchomosci-ados:\(.*\)/\1/p' \
            k8s/app/fastapi-deployment.yaml | head -1)
          sed -i "s|bigpickle/previous-image:.*|bigpickle/previous-image: \"ghcr.io/rendenwald/nieruchomosci-ados:${CURRENT_IMAGE}\"|" \
            k8s/app/fastapi-deployment.yaml
          sed -i "s|image: ghcr.io/rendenwald/nieruchomosci-ados:.*|image: ghcr.io/rendenwald/nieruchomosci-ados:${{ github.sha }}|" \
            k8s/app/fastapi-deployment.yaml
```

### `AGENTS.md`
Add rollback verification items to the checklist section.

### `doc/planning/backlog.md`
Mark STORY-21 as done.

## Verification
1. YAML validity: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"`
2. Workflow logic review: previous-image annotation captured before SHA update
