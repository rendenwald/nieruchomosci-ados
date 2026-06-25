# STORY-21: Test Plan

## Pre-merge Verification

| # | Test | Method | Expected |
|---|------|--------|----------|
| TP-1 | CI workflow YAML valid | `python3 -c "import yaml; yaml.safe_load(...)"` | Valid |
| TP-2 | Workflow captures previous image before update | Manual review | `sed` extracts current image to `bigpickle/previous-image` before updating SHA |
| TP-3 | AGENTS.md has rollback checklist item | Grep | Line exists: `[ ] Previous image SHA noted in deployment annotation` |

## Post-merge Validation
- Push to main triggers CI
- manifest update step captures previous SHA correctly
