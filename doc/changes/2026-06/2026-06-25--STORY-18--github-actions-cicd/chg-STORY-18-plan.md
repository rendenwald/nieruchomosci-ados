# STORY-18: Implementation Plan

## Files to Create

### `.github/workflows/ci.yml`

One workflow with two jobs:

```yaml
name: CI/CD Pipeline

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  # ── Job 1: Run all checks (both projects) ─────────────────────────────
  quality:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        project: [real-estate-api, scrapper-base]
    defaults:
      run:
        working-directory: src/${{ matrix.project }}
    steps:
      - uses: actions/checkout@v4
      - name: Install uv
        uses: astral-sh/setup-uv@v3
      - name: Install dependencies
        run: uv sync --all-extras --dev
      - name: Lint (ruff)
        run: uv run ruff check .
      - name: Type check (mypy)
        run: uv run mypy . --strict
      - name: Test (pytest)
        run: uv run pytest -v

  # ── Job 2: Build Docker image (main only) ─────────────────────────────
  docker:
    if: github.ref == 'refs/heads/main'
    needs: quality
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Build Docker image
        run: docker build . -f src/real-estate-api/Dockerfile -t real-estate-api:${{ github.sha }}
```

## Verification

1. Lint: `ruff check src/real-estate-api/ src/scrapper-base/` — no warnings
2. Workflow file is valid YAML (parse with `python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"`)
