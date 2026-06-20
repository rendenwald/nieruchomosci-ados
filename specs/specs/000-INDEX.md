# 000 — INDEX / Module Map

## Metadata
- **Version:** 2.1
- **Status:** ready
- **AI Context:** Entry point for any AI agent. Read this first to locate the relevant module.

---

## Module Dependency Graph

```
000-INDEX.md  (entry point)
│
├── 010-VISION.md  ───────────────────────────── no deps
│
├── 020-ARCHITECTURE.md  ───────────────────── depends on: 010
│
├── 030-USER-STORIES.md  ───────────────────── depends on: 010, 020
│
├── 040-ACCEPTANCE-CRITERIA.md  ────────────── depends on: 030
│
├── 050-USER-JOURNEYS.md  ──────────────────── depends on: 010, 020
│
├── 060-SCRAPER-BASE.md  ───────────────────── depends on: 070, 120 │ 070-DATABASE.md │ 120-CACHING-STORAGE.md
│
├── 070-DATABASE.md  ───────────────────────── depends on: 020
│
├── 080-API.md  ────────────────────────────── depends on: 070, 120
│
├── 090-FRONTEND.md  ───────────────────────── depends on: 080, 110
│
├── 100-MAP.md  ────────────────────────────── depends on: 090, 080
│
├── 110-I18N-CURRENCY.md  ──────────────────── depends on: 090, 120
│
├── 120-CACHING-STORAGE.md  ───────────────── depends on: 070
│
├── 130-MONITORING-ALERTS.md  ──────────────── depends on: 020, 060
│
├── 140-GITOPS-CICD.md  ───────────────────── depends on: 020
│
├── 150-SCALING.md  ────────────────────────── depends on: 020, 070, 120
│
├── 160-SPRINT-PLAN.md  ───────────────────── depends on: all
│
└── 170-RISKS-COSTS.md  ───────────────────── depends on: all
```

---

## Module Quick-Reference

| # | File | Domain | AI Agent Target |
|---|------|--------|-----------------|
| 000 | `000-INDEX.md` | Module map + deps | Any agent entry |
| 010 | `010-VISION.md` | Vision, principles | Context layer |
| 020 | `020-ARCHITECTURE.md` | System map, stack, hardware | Architecture decisions |
| 030 | `030-USER-STORIES.md` | All 10 epics, points | Sprint backlog |
| 040 | `040-ACCEPTANCE-CRITERIA.md` | Gherkin scenarios | Test specs |
| 050 | `050-USER-JOURNEYS.md` | Journey maps (3) | UX flow context |
| 060 | `060-SCRAPER-BASE.md` | BasePipeline, dedup, metrics | **scrapper-base** implementation |
| 070 | `070-DATABASE.md` | Full schema, partitioning, indexes | **DB migrations + models** |
| 080 | `080-API.md` | FastAPI endpoints, auth, cache | **real-estate-api** implementation |
| 090 | `090-FRONTEND.md` | SvelteKit routes, TS types, components | **real-estate-portal** implementation |
| 100 | `100-MAP.md` | MapLibre clusters, markers, polygon | Map integration |
| 110 | `110-I18N-CURRENCY.md` | i18n, translations, currency service | i18n implementation |
| 120 | `120-CACHING-STORAGE.md` | Redis keyspace+streams, MinIO | Cache + storage |
| 130 | `130-MONITORING-ALERTS.md` | Grafana, Prometheus, alerts | **monitoring** stack |
| 140 | `140-GITOPS-CICD.md` | GitHub Actions, ArgoCD, k8s manifests | **GitOps** setup |
| 150 | `150-SCALING.md` | 3 phases, per-component strategy | Scale planning |
| 160 | `160-SPRINT-PLAN.md` | 8 sprints, Gantt, milestones | PM / timeline |
| 170 | `170-RISKS-COSTS.md` | Risk register, cost table | Ops / risk |

---

## Conventions

Each module file follows this structure:
```
# Module: [Name]
## Metadata
- Version, Status, Dependencies, AI Context

## [Spec content ...]

## AI Implementation Notes
- Files to create
- Verification steps
- Related modules
```

**Legend:**
- `Status: draft` — not yet reviewed
- `Status: ready` — approved, ready for AI implementation
- `Status: implemented` — code exists matching the spec

---

## Task Type → Module Quick-Map

| "I need to..." | Start with |
|----------------|------------|
| Add a new database table / migration | `070-DATABASE.md` |
| Create/update a scraper or dedup logic | `060-SCRAPER-BASE.md` |
| Add an API endpoint | `080-API.md` + `070-DATABASE.md` |
| Build a new frontend page / component | `090-FRONTEND.md` |
| Implement map features (clusters, polygon) | `100-MAP.md` |
| Add translations or currency conversion | `110-I18N-CURRENCY.md` |
| Add Redis cache or MinIO storage | `120-CACHING-STORAGE.md` |
| Add monitoring / alerting / dashboard | `130-MONITORING-ALERTS.md` |
| Set up CI/CD / ArgoCD / k8s manifests | `140-GITOPS-CICD.md` |
| Plan scaling or performance optimization | `150-SCALING.md` |
| Understand sprint timeline | `160-SPRINT-PLAN.md` |
| Check risks or costs | `170-RISKS-COSTS.md` |

---

## Changelog — v2.2 (fixes applied)

| Fix | Module(s) changed | Description |
|-----|-------------------|-------------|
| FIX-1 | 060 | Dedup edge cases: hysteresis threshold, `deduplication_candidates` table, optimistic locking |
| FIX-2 | 120 | MinIO secrets via `secretKeyRef`, bucket RBAC policies |
| FIX-3 | 070 | Unique index on `canonical_properties` MV (required for CONCURRENT refresh) |
| FIX-4 | 120 | Redis Streams: MAXLEN, retry + dead-letter policy, consumer group cleanup CronJob |
| FIX-5 | 080 | Rate limiting table per-user, alert cap (10/user), DB trigger |
| FIX-6 | 090 | CSP headers, DOMPurify sanitization, AGENTS.md XSS rule |
| FIX-7 | 060, 140 | Dedup CronJob idempotency: `dedup_runs` table, `concurrencyPolicy: Forbid` |
| FIX-8 | 080 | API versioning policy, deprecation headers, changelog convention |
| FIX-9 | 060 | Selector health-check: `validate_selectors()`, nightly CI job |
| FIX-10 | 070 | `photo_assets` limit: CHECK constraint + `MAX_PHOTOS_PER_PROPERTY = 20` |
| FIX-11 | 090, 110 | RTL language preparation: `dir` attribute, `RTL_LANGUAGES` list, MapLibre RTL plugin |
| FIX-12 | 130 | SLO definitions, Prometheus recording rules, error budget tracking |
| FIX-13 | 140, AGENTS | Rollback annotations, AGENTS.md checklist additions |
| FIX-14 | 070 | `scraper_runs` range partitioning roadmap note |
| FIX-15 | 160 | Sprint 3 test allocation for Alert Worker (1.5 days) |
