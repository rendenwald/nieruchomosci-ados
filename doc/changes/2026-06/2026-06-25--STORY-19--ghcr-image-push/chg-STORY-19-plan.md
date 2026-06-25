# STORY-19: Implementation Plan

## File to Modify

### `.github/workflows/ci.yml`

Extend the existing `docker` job (lines 47-59) by adding two steps after the build:

1. **Log in to GHCR** — `docker/login-action@v3` with `ghcr.io` registry using `GITHUB_TOKEN`
2. **Push image to GHCR** — push both `${{ github.sha }}` and `latest` tags

```yaml
      - name: Build Docker image
        run: |
          docker build . \
            -f src/real-estate-api/Dockerfile \
            -t ghcr.io/rendenwald/nieruchomosci-ados:${{ github.sha }} \
            -t ghcr.io/rendenwald/nieruchomosci-ados:latest

      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Push image to GHCR
        run: |
          docker push ghcr.io/rendenwald/nieruchomosci-ados:${{ github.sha }}
          docker push ghcr.io/rendenwald/nieruchomosci-ados:latest
```

## Changes Summary

| File | Action |
|------|--------|
| `.github/workflows/ci.yml` | Add GHCR login + push steps to `docker` job |
| `doc/planning/backlog.md` | Mark STORY-19 as `done` |

## Verification

1. YAML validity: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); print('Valid YAML')"`
2. Check workflow has no syntax errors
