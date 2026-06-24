# Backlog — Real Estate Aggregation Platform

> **Source of truth for priority and status.**
> Work items ordered by priority (top = highest).
> See `.ai/agent/pm-instructions.md` for conventions.

---

## Epic 1: scrapper-base Core

| ID | Title | Type | Priority | Status | Labels |
|----|-------|------|----------|--------|--------|
| STORY-1 | Provide `BasePipeline` with DB, logging, metrics | story | high | done | epic, change |
| STORY-2 | Handle concurrent writes safely | story | high | done | change |
| STORY-3 | Update `last_seen_at` and changed fields on existing property | story | high | done | change |
| STORY-4 | Maintain backwards compatibility (semver) | story | medium | todo | change |
| STORY-5 | Emit Prometheus metrics automatically | story | medium | done | change |
| STORY-6 | Send alert via Alertmanager on scraper errors | story | medium | done | change |

> **Note:** STORY-3 was implicitly delivered by STORY-1's `upsert_property()` (the existing-record update path was built as part of the initial upsert implementation). STORY-6 also delivers STORY-12 (Alertmanager notification when error_rate > 5%).

## Epic 2: Scraper Metrics

| ID | Title | Type | Priority | Status | Labels |
|----|-------|------|----------|--------|--------|
| STORY-5 | Emit Prometheus metrics automatically | story | medium | done | change |
| STORY-7 | Track `listings_scraped_total` counter per portal | story | high | done | change |
| STORY-8 | Increment `scrape_errors_total` with error_type label | story | high | done | change |
| STORY-9 | Record `scrape_duration_seconds` histogram | story | high | done | change |
| STORY-10 | Track `db_write_duration_seconds` | story | high | done | change |
| STORY-11 | Show per-portal dashboard with all metrics in Grafana | story | medium | todo | change |
| STORY-12 | Trigger Alertmanager notification when error_rate > 5% | story | medium | done | change |

## Epic 3: Interactive Map

| ID | Title | Type | Priority | Status | Labels |
|----|-------|------|----------|--------|--------|
| STORY-13 | Display property clusters with counts on map | story | medium | todo | change |
| STORY-14 | Expand clusters into individual markers on zoom | story | medium | todo | change |
| STORY-15 | Show property card popup on marker click | story | medium | todo | change |
| STORY-16 | Filter results to polygon drawn on map | story | low | todo | change |
| STORY-17 | Update map markers without page reload on filter change | story | medium | todo | change |

## Epic 4: GitOps + CI/CD

| ID | Title | Type | Priority | Status | Labels |
|----|-------|------|----------|--------|--------|
| STORY-18 | Run tests, lint, build Docker image on push to main | story | high | todo | change |
| STORY-19 | Push built image to self-hosted Gitea registry | story | medium | todo | change |
| STORY-20 | ArgoCD auto-sync deployment on image push | story | medium | todo | change |
| STORY-21 | Auto-rollback to previous version on deploy failure | story | low | todo | change |
| STORY-22 | Run full test suite and preview deploy on PR | story | medium | todo | change |

## Epic 5: Redis Cache

| ID | Title | Type | Priority | Status | Labels |
|----|-------|------|----------|--------|--------|
| STORY-23 | Serve `/api/v1/properties` from Redis cache (TTL 2min) | story | high | done | change |
| STORY-24 | Invalidate relevant cache keys on new property scrape | story | high | done | change |
| STORY-25 | Cache `/api/v1/cities` response for 1 hour | story | medium | todo | change |
| STORY-26 | Use Redis Streams for real-time alert delivery | story | medium | todo | change |
| STORY-27 | Graceful fallback to direct DB query when Redis unavailable | story | high | todo | change |

## Epic 6: Photo Storage

| ID | Title | Type | Priority | Status | Labels |
|----|-------|------|----------|--------|--------|
| STORY-28 | Store scraped photos in MinIO with deduplication | story | high | todo | change |
| STORY-29 | Serve photos via CDN-friendly URL with cache headers | story | medium | todo | change |
| STORY-30 | Validate, resize and store user-uploaded photos in MinIO | story | medium | todo | change |
| STORY-31 | Generate thumbnail (400x300) automatically on photo store | story | medium | todo | change |
| STORY-32 | Cleanup orphaned photos from MinIO on property deletion | story | low | todo | change |

## Epic 7: Multi-language + Multi-currency

| ID | Title | Type | Priority | Status | Labels |
|----|-------|------|----------|--------|--------|
| STORY-33 | Display all UI in PL/EN/DE/UA based on user selection | story | high | todo | change |
| STORY-34 | Convert prices using daily ECB rates | story | high | todo | change |
| STORY-35 | Serve English version with hreflang when `/en/` accessed | story | medium | todo | change |
| STORY-36 | Format prices according to locale | story | medium | todo | change |
| STORY-37 | Normalize Polish diacritics in city names during search | story | medium | todo | change |

## Epic 8: Scaling

| ID | Title | Type | Priority | Status | Labels |
|----|-------|------|----------|--------|--------|
| STORY-38 | Scale FastAPI horizontally with multiple replicas | story | low | todo | change |
| STORY-39 | Use read replicas for SELECT operations | story | low | todo | change |
| STORY-40 | Schedule scrapers independently via Kubernetes CronJob | story | low | todo | change |
| STORY-41 | Expand MinIO across multiple disks/nodes | story | low | todo | change |

## Epic 9: Alerts + Notifications

| ID | Title | Type | Priority | Status | Labels |
|----|-------|------|----------|--------|--------|
| STORY-42 | Save user search criteria when creating alert | story | medium | todo | change |
| STORY-43 | Notify user via email when matching property scraped | story | medium | todo | change |
| STORY-44 | Send browser push notification | story | low | todo | change |
| STORY-45 | Notify admin via email + Slack on high scraper error rate | story | medium | todo | change |
| STORY-46 | Trigger critical alert to admin when DB disk > 80% | story | medium | todo | change |

## Epic 10: Monitoring

| ID | Title | Type | Priority | Status | Labels |
|----|-------|------|----------|--------|--------|
| STORY-47 | Show unified dashboard (scrapers + DB + API + frontend) in Grafana | story | low | todo | change |
| STORY-48 | Alert admin when API p95 latency > 500ms | story | medium | todo | change |
| STORY-49 | Alert admin when PostgreSQL connections > 80% | story | medium | todo | change |
| STORY-50 | Alert admin when Redis memory > 90% | story | low | todo | change |
| STORY-51 | Alert within 1 minute when container crashes | story | low | todo | change |
| STORY-52 | Alert admin when SvelteKit Core Web Vitals degrade | story | low | todo | change |

---

## Stats

- **Total items:** 52
- **Todo:** 40
- **In progress:** 0
- **Done:** 12
