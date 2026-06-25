# STORY-22: Test Plan

## Pre-merge Verification

| # | Test | Method | Expected |
|---|------|--------|----------|
| TP-1 | preview-deploy.yml YAML valid | `python3 -c "import yaml; yaml.safe_load(...)"` | Valid |
| TP-2 | preview-cleanup.yml YAML valid | Same | Valid |
| TP-3 | preview-deploy triggers on opened/synchronize/reopened | YAML review | `types: [opened, synchronize, reopened]` |
| TP-4 | preview-cleanup triggers on closed | YAML review | `types: [closed]` |
| TP-5 | PR image tag is `pr-{number}` | YAML review | Tag format correct |

## Post-merge Validation
- Open a test PR → verify preview-deploy workflow is visible in Actions tab
- Close the PR → verify cleanup workflow appears
