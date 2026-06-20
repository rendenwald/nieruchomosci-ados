# 030 — USER-STORIES / Complete Backlog

## Metadata
- **Version:** 2.1
- **Status:** ready
- **Dependencies:** 010-VISION.md, 020-ARCHITECTURE.md
- **AI Context:** All 10 epics with EARS-format user stories and story points. Use for sprint planning and backlog prioritization.

---

## Epic 1: scrapper-base Core

| ID | User Story (EARS) | Points |
|----|-------------------|--------|
| SB-1 | **When** developer adds scraper, **shall** provide `BasePipeline` with DB, logging, metrics | 8 |
| SB-2 | **When** scrapers write simultaneously, **shall** handle concurrent writes safely | 5 |
| SB-3 | **When** property exists, **shall** update `last_seen_at` and changed fields | 3 |
| SB-4 | **When** scrapper-base updated, **shall** remain backwards compatible (semver) | 3 |
| SB-5 | **When** scraper runs, **shall** emit Prometheus metrics automatically | 5 |
| SB-6 | **When** scraper errors occur, **shall** send alert via Alertmanager | 5 |

## Epic 2: Scraper Metrics

| ID | User Story (EARS) | Points |
|----|-------------------|--------|
| MT-1 | **When** scraper runs, **shall** track `listings_scraped_total` counter per portal | 3 |
| MT-2 | **When** scraper errors, **shall** increment `scrape_errors_total` with error_type label | 3 |
| MT-3 | **When** scraper finishes, **shall** record `scrape_duration_seconds` histogram | 3 |
| MT-4 | **When** DB write occurs, **shall** track `db_write_duration_seconds` | 3 |
| MT-5 | **When** Grafana opens, **shall** show per-portal dashboard with all metrics | 5 |
| MT-6 | **When** error_rate > 5%, **shall** trigger Alertmanager notification | 5 |

## Epic 3: Interactive Map

| ID | User Story (EARS) | Points |
|----|-------------------|--------|
| MAP-1 | **When** user opens map view, **shall** display property clusters with counts | 8 |
| MAP-2 | **When** user zooms in, **shall** expand clusters into individual markers | 5 |
| MAP-3 | **When** user clicks marker, **shall** show property card popup | 3 |
| MAP-4 | **When** user draws area on map, **shall** filter results to that polygon | 8 |
| MAP-5 | **When** filters change, **shall** update map markers without page reload | 5 |

## Epic 4: GitOps + CI/CD

| ID | User Story (EARS) | Points |
|----|-------------------|--------|
| CI-1 | **When** code pushed to main, **shall** run tests, lint, build Docker image | 5 |
| CI-2 | **When** image built, **shall** push to self-hosted Gitea registry | 3 |
| CI-3 | **When** image pushed, **shall** ArgoCD auto-sync deployment | 5 |
| CI-4 | **When** deployment fails, **shall** auto-rollback to previous version | 5 |
| CI-5 | **When** PR opened, **shall** run full test suite and preview deploy | 8 |

## Epic 5: Redis Cache

| ID | User Story (EARS) | Points |
|----|-------------------|--------|
| RC-1 | **When** `/api/v1/properties` called, **shall** serve from Redis cache (TTL 2min) | 5 |
| RC-2 | **When** new property scraped, **shall** invalidate relevant cache keys | 3 |
| RC-3 | **When** `/api/v1/cities` called, **shall** cache response for 1 hour | 3 |
| RC-4 | **When** user alert triggered, **shall** use Redis Streams for real-time delivery | 8 |
| RC-5 | **When** Redis unavailable, **shall** fallback to direct DB query gracefully | 5 |

## Epic 6: Photo Storage

| ID | User Story (EARS) | Points |
|----|-------------------|--------|
| IMG-1 | **When** scraper downloads photo, **shall** store in MinIO with deduplication | 5 |
| IMG-2 | **When** photo requested, **shall** serve via CDN-friendly URL with cache headers | 3 |
| IMG-3 | **When** user uploads property photo, **shall** validate, resize and store in MinIO | 8 |
| IMG-4 | **When** photo stored, **shall** generate thumbnail (400x300) automatically | 5 |
| IMG-5 | **When** property deleted, **shall** cleanup orphaned photos from MinIO | 3 |

## Epic 7: Multi-language + Multi-currency

| ID | User Story (EARS) | Points |
|----|-------------------|--------|
| I18N-1 | **When** user selects language, **shall** display all UI in PL/EN/DE/UA | 8 |
| I18N-2 | **When** user selects currency, **shall** convert prices using daily ECB rates | 8 |
| I18N-3 | **When** URL accessed with `/en/`, **shall** serve English version with hreflang | 5 |
| I18N-4 | **When** price displayed, **shall** format according to locale | 3 |
| I18N-5 | **When** search performed, **shall** normalize Polish diacritics in city names | 3 |

## Epic 8: Scaling

| ID | User Story (EARS) | Points |
|----|-------------------|--------|
| SC-1 | **When** traffic spikes, **shall** scale FastAPI horizontally with multiple replicas | 8 |
| SC-2 | **When** DB queries slow, **shall** use read replicas for SELECT operations | 8 |
| SC-3 | **When** scraper count grows, **shall** schedule via Kubernetes CronJob independently | 5 |
| SC-4 | **When** storage grows, **shall** MinIO expand across multiple disks/nodes | 5 |

## Epic 9: Alerts + Notifications

| ID | User Story (EARS) | Points |
|----|-------------------|--------|
| ALT-1 | **When** user creates alert (city + price + type), **shall** save search criteria | 5 |
| ALT-2 | **When** new matching property scraped, **shall** notify user via email | 8 |
| ALT-3 | **When** user enables push, **shall** send browser push notification | 8 |
| ALT-4 | **When** scraper error_rate > 5%, **shall** notify admin via email + Slack | 5 |
| ALT-5 | **When** DB disk > 80%, **shall** trigger critical alert to admin | 5 |

## Epic 10: Monitoring

| ID | User Story (EARS) | Points |
|----|-------------------|--------|
| MON-1 | **When** Grafana opened, **shall** show unified dashboard: scrapers + DB + API + frontend | 8 |
| MON-2 | **When** API p95 latency > 500ms, **shall** alert admin | 5 |
| MON-3 | **When** PostgreSQL connections > 80%, **shall** alert admin | 5 |
| MON-4 | **When** Redis memory > 90%, **shall** alert admin | 3 |
| MON-5 | **When** any container crashes, **shall** alert within 1 minute | 5 |
| MON-6 | **When** SvelteKit Core Web Vitals degrade, **shall** alert admin | 5 |

---

## AI Implementation Notes

- Total: **232 story points** across 10 epics.
- Each ID corresponds to a module: SB=060, MT=130, MAP=100, CI=140, RC=120, IMG=120, I18N=110, SC=150, ALT=130, MON=130.
- Use this module as the source of truth for backlog prioritization.
