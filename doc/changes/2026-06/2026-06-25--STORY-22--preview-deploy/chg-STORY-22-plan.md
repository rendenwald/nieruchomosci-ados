# STORY-22: Implementation Plan

## Files to Create

### `.github/workflows/preview-deploy.yml`
New workflow triggered on PR events:
- Build PR-specific Docker image
- Push to GHCR with `pr-{number}` tag
- Deploy to preview namespace (kubectl apply)
- Comment PR with preview URL

### `.github/workflows/preview-cleanup.yml`
New workflow triggered on PR close:
- Delete the preview namespace
- Remove the PR-specific GHCR image tag

## Files to Modify

### `.github/workflows/ci.yml`
No changes needed — quality checks already run on every PR.

### `doc/planning/backlog.md`
Mark STORY-22 as done.

## Verification
1. All YAML files parse correctly
2. Workflows have correct triggers
