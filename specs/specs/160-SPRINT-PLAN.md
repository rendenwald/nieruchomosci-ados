# 160 — SPRINT-PLAN / Implementation Timeline

## Metadata
- **Version:** 2.1
- **Status:** ready
- **Dependencies:** all modules (indexed view)
- **AI Context:** 8-sprint implementation plan with Gantt chart. Use for project management and milestone tracking.

---

```mermaid
gantt
    title Implementation Plan v2.1
    dateFormat YYYY-MM-DD

    section Sprint 1: scrapper-base core
    database + models + services     :2026-06-16, 4d
    BasePipeline + metrics           :2026-06-20, 3d
    logging + storage (MinIO)        :2026-06-23, 3d
    Testy + dokumentacja             :2026-06-26, 2d

    section Sprint 2: Refactor scrapers
    Refactor otodom-scrapper         :2026-06-30, 4d
    Refactor nieruchomosci-online    :2026-07-04, 4d
    GitOps setup (Gitea + ArgoCD)    :2026-07-08, 3d

    section Sprint 3: Deduplication
    Blocking + heuristics            :2026-07-14, 4d
    Fuzzy matching + image hash      :2026-07-18, 4d
    Alert worker + Redis Streams     :2026-07-22, 4d

    section Sprint 4: Monitoring
    Prometheus + Grafana dashboards  :2026-07-28, 4d
    Alertmanager + notifications     :2026-08-01, 3d
    Loki log aggregation + retention :2026-08-04, 3d

    section Sprint 5: API + Cache
    FastAPI endpoints                :2026-08-11, 5d
    Redis cache-aside                :2026-08-16, 3d
    JWT auth + user alerts           :2026-08-19, 4d

    section Sprint 6: Frontend SvelteKit
    Routing i18n + layout            :2026-08-25, 4d
    Offer list + filters             :2026-08-29, 5d
    MapLibre map + clusters          :2026-09-03, 5d

    section Sprint 7: Frontend cont.
    Detail page + portals            :2026-09-09, 4d
    Alert system UI                  :2026-09-13, 3d
    Multi-currency ECB               :2026-09-16, 3d

    section Sprint 8: Production
    Security audit + load testing    :2026-09-22, 4d
    Scaling + DB optimization        :2026-09-26, 3d
    Documentation + launch           :2026-09-29, 3d
```

---

## Sprint ⇄ Module Mapping

| Sprint | Modules | Focus |
|--------|---------|-------|
| 1 | 060, 070, 120 | scrapper-base core, DB schema, MinIO storage |
| 2 | 060 (scrapers), 140 | Individual scrapers, GitOps infra |
| 3 | 060 (dedup) | Deduplication pipeline, alert worker |
| 4 | 130 | Complete monitoring stack |
| 5 | 080, 120 | FastAPI endpoints, Redis cache |
| 6 | 090, 100, 110 | SvelteKit, map, i18n basics |
| 7 | 090, 110, 100 | Frontend details, alerts UI, currency |
| 8 | 150, 170, all | Security, scaling, launch |

---

## AI Implementation Notes

- **Current date:** 2026-06-16 (Sprint 1 start)
- Each sprint maps to specific modules — AI agents can work per-sprint
- Sprint 1 is the priority: scrapper-base foundation
- Use this as a roadmap, not a strict schedule

---

## FIX-15: Sprint 3 — Alert Worker test allocation

Sprint 3 original allocation: "Alert worker + Redis Streams (4 days)"

**Revised allocation:**

| Task | Days |
|------|------|
| Alert Worker implementation (Redis Stream consumer) | 2.5 |
| Tests: Alert Worker (fakeredis mock, end-to-end ALT-2 scenario) | 1.5 |

Test files to create in Sprint 3:
- `tests/test_alert_worker.py` — unit tests with `fakeredis.aioredis.FakeRedis`
- `tests/test_alt2_e2e.py` — Gherkin scenario ALT-2 (new property → email delivered in < 5 min)

Acceptance: `pytest tests/test_alert_worker.py tests/test_alt2_e2e.py -v --cov=alert_worker --cov-fail-under=80`

> Rationale: AGENTS.md states "Tests are first-class — every function/endpoint gets a pytest unit test. No exceptions." The original Sprint 3 plan had no explicit test time for the Alert Worker.
