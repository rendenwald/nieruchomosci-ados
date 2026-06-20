# PR/MR Platform Instructions — GitHub

> **Platform:** GitHub
> **Access method:** CLI (`gh`)
> **Repository:** `rendenwald/nieruchomosci-ados`
> **Reference:** `doc/guides/pr-platform-integration.md` for setup details
> **Template source:** `doc/templates/pr-instructions-template.md`

---

## 1. Platform & Access

| Property | Value |
|----------|-------|
| Platform | GitHub |
| Host | `github.com` |
| Repository | `rendenwald/nieruchomosci-ados` |
| Access Method | CLI (`gh`) |
| Auth | `gh auth login` (configured locally) |

---

## 2. Branch Strategy

| Branch | Purpose |
|--------|---------|
| `main` | Production — protected, no direct pushes |
| `feature/*` | Feature branches — `feature/{module-id}-{kebab-name}` |

All work is done on feature branches, merged via PR after review.

---

## 3. Operations Reference

| Operation | Command / Steps |
|-----------|-----------------|
| **Create PR** | `gh pr create --title "[#module] Short description" --body "Implements XX-module.md" --base main` |
| **View PR** | `gh pr view <number>` |
| **List PRs** | `gh pr list --state open` |
| **Check status** | `gh pr status` |
| **Add reviewer** | `gh pr edit <number> --add-reviewer <handle>` |
| **Merge PR** | `gh pr merge <number> --squash --delete-branch` |
| **Close PR** | `gh pr close <number>` |
| **Checkout PR** | `gh pr checkout <number>` |
| **Comment on PR** | `gh pr comment <number> --body "message"` |
| **Create issue** | `gh issue create --title "..." --label "change"` |

---

## 4. PR Convention

- **Title format:** `[#module-id] Short description` — e.g., `[070] Add Property ORM model`
- **Description:** Reference the spec module: "Implements 070-DATABASE.md"
- **Body should include:**
  - What was changed
  - Link to spec module
  - Verification steps
  - Checklist confirming acceptance criteria met
- **Merge strategy:** Squash merge (keep history clean)
- **Delete branch** after merge

---

## 5. Review Process

- **Solo project:** Self-review with verification checklist before merging
- Run the full checklist from `AGENTS.md` section 11 before requesting review or merging
- Verify with `gh pr checks <number>` that all CI checks pass
