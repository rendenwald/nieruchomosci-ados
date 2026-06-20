# AGENTS.md — Constitution for AI Agents

> **Read this first.** Every agent reads this before any task.
> It describes what this project is, how we deliver, and where to find everything.

---

## What This Repo Is

**Real Estate Aggregation Platform** — a self-hosted, open-source platform that scrapes Polish real estate portals (Otodom, Gratka, Nieruchomości Online), deduplicates listings, and provides a unified search experience with:

- Interactive map (MapLibre GL) with clustering and polygon filtering
- Multi-language UI (PL/EN/DE/UA) via paraglide-js
- Multi-currency support (PLN/EUR/USD/GBP/UAH) via daily ECB rates
- User alerts with email and push notifications
- Full monitoring stack (Prometheus, Grafana, Loki, Alertmanager)

| Attribute | Value |
|-----------|-------|
| **Repository** | `github.com/rendenwald/nieruchomosci-ados` |
| **Team** | Solo developer (@rendenwald) |
| **Tracker** | Local markdown backlog (`doc/planning/backlog.md`) |
| **Spec root** | `specs/` — 18 specification modules (see `specs/000-INDEX.md`) |
| **ADOS spec root** | `doc/spec/features/` — ADOS feature specs |

---

## Delivery Process

All work follows the **ADOS 10-phase change lifecycle**. Reference: `doc/guides/change-lifecycle.md`.

```
1. Triage     → 2. Spec      → 3. Plan     → 4. Review    → 5. Implement
6. Verify     → 7. PR/MR     → 8. Review    → 9. Merge     → 10. Close
```

Each change creates artifacts in `doc/changes/<change-id>/`.

---

## Repo Structure

```
/
├── AGENTS.md                    ← This file — read first
├── .ai/                         ← ADOS configuration
│   ├── agent/
│   │   ├── pm-instructions.md   ← PM: local backlog rules
│   │   └── pr-instructions.md   ← PR: GitHub CLI operations
│   └── local/                   ← Bootstrapper state (git-ignored)
├── doc/                         ← ADOS documentation
│   ├── 00-index.md              ← Documentation landing page
│   ├── overview/                ← North star, architecture
│   ├── spec/features/           ← ADOS feature specs
│   ├── planning/                ← Backlog + epics
│   ├── changes/                 ← Change artifacts per lifecycle
│   ├── decisions/               ← Decision records (ADR/PDR/TDR)
│   ├── guides/                  ← ADOS process guides
│   └── templates/               ← Document templates
├── specs/                       ← 18 specification modules
│   ├── 000-INDEX.md             ← Start here
│   ├── 010-VISION.md            ← Product vision
│   ├── 020-ARCHITECTURE.md      ← System architecture
│   ├── 030-USER-STORIES.md      ← All user stories (52 total)
│   └── ... (18 modules)
├── src/                         ← Source code (to be created)
├── tests/                       ← Test suites (to be created)
├── k8s/                         ← Kubernetes manifests (to be created)
└── .github/                     ← GitHub Actions (to be created)
```

---

## Tech Stack

| Layer | Technology | Spec |
|-------|------------|------|
| **Backend** | FastAPI + SQLAlchemy 2.0 async + Alembic | `080-API.md` |
| **Database** | PostgreSQL 16 + PostGIS, LIST partitioning | `070-DATABASE.md` |
| **Scraping** | Scrapy + Playwright via `BasePipeline` | `060-SCRAPER-BASE.md` |
| **Frontend** | SvelteKit + TypeScript + MapLibre GL + paraglide-js | `090-FRONTEND.md`, `100-MAP.md` |
| **Cache** | Redis 7 (maxmemory 1GB, allkeys-lru, no persist) | `120-CACHING-STORAGE.md` |
| **Storage** | MinIO standalone — SHA256 dedup, 400x300 thumbnails | `120-CACHING-STORAGE.md` |
| **Monitoring** | Prometheus + Grafana + Loki (7d) + Alertmanager | `130-MONITORING-ALERTS.md` |
| **CI/CD** | GitHub Actions + ArgoCD + Gitea Registry | `140-GITOPS-CICD.md` |
| **Infra** | k3s single node (→ cluster) | `020-ARCHITECTURE.md` |

---

## Agents

| Agent | Role | When to use |
|-------|------|-------------|
| `@pm` | Manage backlog, prioritize, select next work item | Start of session, backlog grooming |
| `@plan-writer` | Write change implementation plans | After spec is approved |
| `@spec-writer` | Write change specifications | After triage |
| `@test-plan-writer` | Write test plans per change | After plan is approved |
| `@coder` | Implement code from plan | After plan is approved |
| `@reviewer` | Review changes against spec and code quality | Before PR/MR |
| `@pr-manager` | Create/update PR/MR title and description | Before merge |
| `@committer` | Create a conventional commit | During implementation |
| `@architect` | Architecture decisions, trade-off analysis | When spec is unclear on approach |
| `@fixer` | Reproduce and fix bugs | When tests fail |
| `@doc-syncer` | Reconcile specs with completed changes | After merge |
| `@runner` | Run commands, save logs | For CI or local verification |

---

## Key Conventions

### Branching

```
feature/{module-id}-{kebab-name}
```

Examples: `feature/070-property-model`, `feature/060-scrapper-base-pipeline`

### Commits

Conventional commits: `feat:`, `fix:`, `chore:`, `test:`, `docs:`

### PRs

```
Title:  [#module-id] Short description    — e.g. "[070] Add Property ORM model"
Body:   Implements XX-module.md            — reference the spec module
Merge:  Squash, delete branch
```

### Work Items

Sequential IDs across all types: `STORY-1`, `BUG-1`, `TASK-1`

### Backlog

Source of truth: `doc/planning/backlog.md` (ordered table, priority = row order)
Epics: `doc/planning/epics/<epic-id>--<slug>/`

---

## Hard Rules (Never Violate)

| Rule | Why |
|------|-----|
| NEVER hardcode secrets — use env vars only | Security |
| NEVER use synchronous DB drivers with FastAPI — use asyncpg | Performance |
| NEVER write `print()` — use structured logging | Ops |
| NEVER skip type hints on function signatures | Maintainability |
| NEVER commit directly to `main` — use feature branches + PR | Git discipline |
| NEVER store files on the filesystem — use MinIO for images, DB for data | Architecture |
| NEVER add `# type: ignore` without a comment explaining why | Quality |
| NEVER write Gherkin without a scenario ID (e.g., `SB-3`) | Traceability |
| NEVER render raw HTML from external sources — `DOMPurify` always | XSS |
| NEVER use `env.value` for k8s credentials — always `secretKeyRef` | Security |
| NEVER create a CronJob without `concurrencyPolicy: Forbid` | Idempotency |
| NEVER call `REFRESH MATERIALIZED VIEW CONCURRENTLY` before creating a unique index | PostgreSQL |
| NEVER merge dedup with fuzzy score < 0.85 | Data quality |
| NEVER upload > 20 photos per scrape run (`MAX_PHOTOS_PER_PROPERTY`) | Storage |
| NEVER `XADD` to a Redis Stream without `MAXLEN` | Memory |

---

## When Spec Is Silent — Question Template

```
**Question:** [component] — [one-line summary]

**Context:** Implementing [feature X] from [spec module]. The spec says
"[quote]" but does not specify [missing detail].

**Options:**
  - A: [option 1] — [pro/con]
  - B: [option 2] — [pro/con]

**Recommendation:** [A/B] because [reason].
```

---

## Verification Checklist

Before marking *any* task complete:

```
[ ] ruff check .                          — no lint warnings
[ ] mypy . --strict                       — no type errors
[ ] pytest tests/ -v --cov=. --cov-fail-under=80
[ ] npm run build                         — if frontend work
[ ] Manual flow check (curl / browser)
[ ] No hardcoded values — all config via env vars
[ ] Matches the spec's AI Implementation Notes
[ ] AGENTS.md or README needs updating?
[ ] Changes reversible without data migration?
[ ] DB migration — does alembic downgrade -1 succeed?
[ ] New MV — unique index before REFRESH CONCURRENTLY?
[ ] New CronJob — concurrencyPolicy: Forbid?
[ ] New k8s Secret — secretKeyRef?
[ ] External HTML — DOMPurify sanitizeHtml()?
[ ] Redis Stream XADD — MAXLEN set?
```

---

## Reference Documents

| Document | Path | Purpose |
|----------|------|---------|
| Change Lifecycle | `doc/guides/change-lifecycle.md` | 10-phase delivery workflow |
| PM Instructions | `.ai/agent/pm-instructions.md` | Backlog management rules |
| PR Instructions | `.ai/agent/pr-instructions.md` | GitHub CLI operations |
| Spec Index | `specs/000-INDEX.md` | 18 spec modules |
| North Star | `doc/overview/01-north-star.md` | Product vision & strategy |
| Architecture | `doc/overview/02-architecture.md` | System architecture |
| Backlog | `doc/planning/backlog.md` | Priority-ordered work items |
| Developer Setup | `doc/guides/developer-setup.md` | Tool installation & dev environment |
| Documentation Handbook | `doc/documentation-handbook.md` | Doc structure & conventions |
