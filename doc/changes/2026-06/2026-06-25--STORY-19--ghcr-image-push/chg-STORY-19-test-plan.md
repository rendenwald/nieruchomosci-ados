# STORY-19: Test Plan

## Pre-merge verification

Since this is a CI/CD pipeline change, testing is limited to static validation:

| # | Test | Method | Expected |
|---|------|--------|----------|
| TP-1 | Workflow YAML is valid | `python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); print('OK')"` | Prints "OK" |
| TP-2 | Workflow has push steps after build | Manual YAML review | `docker/login-action@v3` + `docker push` steps present |
| TP-3 | Push only on main | YAML condition check | Push steps gated by `github.ref == 'refs/heads/main'` |
| TP-4 | No push on PR | YAML review | `if` condition ensures push only on main branch |
| TP-5 | Image tagged with SHA and latest | YAML review | Two push commands: `${{ github.sha }}` and `latest` |

## Post-merge validation

After merge to `main`, verify in GitHub Actions UI:
- Push to main triggers the workflow
- The `docker` job shows login, build, push steps
- Image appears in GHCR packages at `https://github.com/orgs/rendenwald/packages`
