---
change:
  ref: STORY-1
  type: feat
  status: Accepted
  slug: scrapper-base-core
  title: "Provide BasePipeline with DB, logging, metrics"
  owners: ["rendenwald"]
  service: scrapper-base
  labels: ["epic", "change"]
  version_impact: minor
  audience: internal
  security_impact: low
  risk_level: medium
  dependencies:
    internal: []
    external: ["PostgreSQL 16", "Redis 7", "MinIO"]
links:
  feature_spec: ../../doc/spec/features/feature-scrapper-base.md
  epic: ../../doc/planning/epics/epic-01--scrapper-base-core/epic-01--scrapper-base-core.md
  spec_modules:
    - ../../specs/060-SCRAPER-BASE.md
    - ../../specs/070-DATABASE.md
---

# CHANGE SPECIFICATION

> **PURPOSE**: Create the `scrapper-base` Python package — the foundational library all portal-specific scrapers depend on — so that a new scraper can be created by subclassing `BasePipeline` and implementing one method (`item_to_data()`).

## 1. SUMMARY

This change creates the `src/scrapper-base/` Python package with async PostgreSQL connectivity (SQLAlchemy 2.0 + asyncpg), a `BasePipeline` ABC for Scrapy pipelines, Prometheus metrics auto-emission, structured JSON logging, and a MinIO storage client. It includes Alembic migrations for the initial database schema and a fully runnable package scaffold with pinned dependencies.

## 2. CONTEXT

### 2.1 Current State Snapshot

No source code exists yet. The project has:
- Specification modules in `specs/` (18 modules covering architecture, DB, scrapers, frontend, etc.)
- An ADOS feature spec: `doc/spec/features/feature-scrapper-base.md` (draft)
- Development tools installed (Python 3.12, uv, PostgreSQL 16, Redis 7, Playwright)
- No Python code, no database schema, no scraper code

### 2.2 Pain Points / Gaps

- Each planned portal scraper (Otodom, Gratka, Nieruchomości Online) would require duplicating DB connection logic, upsert logic, metrics emission, and logging setup
- No shared abstraction exists for the scraper pipeline pattern
- No database schema exists to store scraped properties

## 3. PROBLEM STATEMENT

Because there is no shared `scrapper-base` package, each portal scraper must reimplement database connectivity, property persistence, metrics, and logging from scratch, resulting in 2-3 days of setup per portal instead of a few hours.

## 4. GOALS

- **G-1**: New scraper can be created by subclassing `BasePipeline` and implementing `item_to_data()`
- **G-2**: Properties are persisted via upsert (no duplicates by `portal_source` + `source_id`)
- **G-3**: Metrics are auto-emitted without manual instrumentation in portal scrapers
- **G-4**: All components have structured logging out of the box

### 4.1 Success Metrics / KPIs

| Metric | Target |
|--------|--------|
| New scraper setup time | < 2 hours |
| Test coverage | ≥ 80% |
| Upsert throughput | ≥ 100 properties/second |

### 4.2 Non-Goals

- **NG-1**: Deduplication pipeline (blocking, heuristics, fuzzy matching, image hashing) — deferred to Sprint 3
- **NG-2**: Grafana dashboards for scraper metrics — deferred to Epic 10
- **NG-3**: Alertmanager integration — deferred to Sprint 2 (STORY-6)
- **NG-4**: Portal-specific scrapers (Otodom, Gratka, Nieruchomości Online) — separate changes

## 5. FUNCTIONAL CAPABILITIES

| ID | Capability | Rationale |
|----|------------|-----------|
| F-1 | Async PostgreSQL connection via SQLAlchemy 2.0 + asyncpg | Foundation for all data persistence |
| F-2 | SQLAlchemy models for `properties`, `agencies`, `scraper_runs` | Data model per 070-DATABASE.md |
| F-3 | Alembic migration setup + initial migration | Schema versioning and reproducibility |
| F-4 | `PropertyService.upsert_property()` — insert new or update existing by `(portal_source, source_id)` | Core data operation |
| F-5 | `BasePipeline` ABC with `item_to_data()`, `open_spider()`, `close_spider()`, `process_item()` hooks | Shared scraper pipeline abstraction |
| F-6 | Prometheus metrics: counters, histograms, gauges (see §10) | Observability |
| F-7 | Structured JSON logging with consistent fields (`portal`, `scraper_id`, `run_id`) | Debugging and monitoring |
| F-8 | MinIO storage client for photo upload/download | Image storage per architecture |

### 5.1 Capability Details

**F-1 (DB Connection):**
- Async engine with configurable pool size (5-10 connections)
- Connection string from `DATABASE_URL` env var
- Retry with exponential backoff on connection failure (3 attempts)

**F-2 (Models):**
- `Property` — portal_source, source_id, source_url, title, description, property_type, price, area, latitude, longitude, location (PostGIS geometry), photos (JSONB), scraped_at, last_seen_at, is_active, etc.
- `Agency` — name, source_id, portal_source, phone, email, logo_url
- `ScraperRun` — portal_source, started_at, finished_at, items_scraped, errors, status

**F-4 (Upsert):**
- Match on `(portal_source, source_id)` unique constraint
- On insert: set `scraped_at = NOW()`, `last_seen_at = NOW()`, `is_active = True`
- On update: set `last_seen_at = NOW()`, update all data fields
- Return `(property, is_new: bool)`

**F-5 (BasePipeline):**
```python
class BasePipeline(ABC):
    PORTAL_SOURCE: str

    @abstractmethod
    def item_to_data(self, item: ScrapyItem) -> dict: ...

    async def open_spider(self, spider: Spider) -> None: ...
    async def close_spider(self, spider: Spider) -> None: ...
    async def process_item(self, item, spider) -> dict: ...
```

**F-8 (MinIO Storage):**
- Client configured via `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY` env vars
- `upload_photo(bucket, object_name, data)` → SHA256-deduplicated path
- `get_photo_url(bucket, object_name)` → presigned URL
- Graceful degradation if MinIO unavailable

## 6. USER & SYSTEM FLOWS

```
Flow 1: Developer uses BasePipeline
  Developer → subclasses BasePipeline → implements item_to_data()
  → open_spider() auto-opens DB + MinIO connections
  → process_item() auto-calls upsert_property() + emits metrics
  → close_spider() auto-closes connections

Flow 2: Property upsert
  process_item() → item_to_data() → upsert_property()
    → check existing by (portal_source, source_id)
    → if exists: update fields, set last_seen_at = NOW()
    → if new: insert, set scraped_at = NOW()
    → emit db_write_duration_seconds histogram
    → increment listings_scraped_total counter
```

## 7. SCOPE & BOUNDARIES

### 7.1 In Scope

- `src/scrapper-base/pyproject.toml` with pinned dependencies
- `scraper_base/` Python package with modules: database, models, services, pipeline, metrics, logging_config, storage
- Alembic configuration directory + initial migration creating `properties`, `agencies`, `scraper_runs` tables
- Unit tests for all components (with mocked external services)
- Type hints throughout

### 7.2 Out of Scope

- [OUT] Deduplication pipeline (blocking, heuristics, fuzzy matching, image hashing)
- [OUT] Portal-specific scrapers
- [OUT] Grafana dashboards
- [OUT] Prometheus `/metrics` endpoint (provided by Scrapy or app server later)
- [OUT] Docker Compose setup for infrastructure services

### 7.3 Deferred / Maybe-Later

- Concurrent write locking (STORY-2) — optimistic locking with `SELECT ... FOR UPDATE`
- `duplicate_groups` table and dedup logic — Sprint 3
- Photo hash deduplication in MinIO storage — Sprint 3

## 8. INTERFACES & INTEGRATION CONTRACTS

### 8.1 REST / HTTP Endpoints

None. The package is a library, not a service.

### 8.2 Events / Messages

None.

### 8.3 Data Model Impact

**New tables (created by initial Alembic migration):**

| Table | Description |
|-------|-------------|
| `properties` | Real estate listings, LIST partitioned by `portal_source` |
| `agencies` | Property agencies/owners |
| `scraper_runs` | Scraper execution history |
| `alembic_version` | Migration tracking (auto) |

### 8.4 External Integrations

| Service | Interface | Purpose |
|---------|-----------|---------|
| PostgreSQL 16 | asyncpg via SQLAlchemy 2.0 | Data persistence |
| MinIO | S3-compatible API (`minio` Python SDK) | Photo storage |

### 8.5 Backward Compatibility

N/A — first version of the package. Follows semver from the start (`0.1.0` pre-release, then `1.0.0` at first stable).

## 9. NON-FUNCTIONAL REQUIREMENTS (NFRs)

| ID | Requirement | Threshold |
|----|-------------|-----------|
| NFR-1 | Upsert throughput | ≥ 100 properties/second |
| NFR-2 | DB connection pool | 5-10 connections per scraper instance |
| NFR-3 | Metrics emission | Non-blocking, zero-copy |
| NFR-4 | Type safety | Full type hints on all public functions |
| NFR-5 | Lint quality | `ruff check` passes with no warnings |
| NFR-6 | Test coverage | ≥ 80% |
| NFR-7 | Error handling | DB failure → retry 3x with backoff, then fail with logged error |

## 10. TELEMETRY & OBSERVABILITY REQUIREMENTS

**Metrics (defined in `metrics.py`):**

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `listings_scraped_total` | Counter | `portal`, `city`, `type` | Total listings scraped |
| `scrape_errors_total` | Counter | `portal`, `error_type` | Total scrape errors |
| `scrape_duration_seconds` | Histogram | `portal` | Scrape duration |
| `db_write_duration_seconds` | Histogram | `operation` | DB write latency |
| `active_listings_gauge` | Gauge | `portal` | Currently active listings |

**Logging:**
- All log entries emitted as JSON with fields: `timestamp`, `level`, `logger`, `message`, `portal`, `scraper_id`, `run_id`, `error` (if applicable)

## 11. RISKS & MITIGATIONS

| ID | Risk | Impact | Probability | Mitigation | Residual Risk |
|----|------|--------|-------------|------------|---------------|
| RSK-1 | PostgreSQL 16 features not available in dev Docker image | Medium | Low | Pin `postgis/postgis:16-3.4` image, test locally | Low |
| RSK-2 | Scrapy API changes | Medium | Low | Pin to `scrapy>=2.11,<3.0` | Low |
| RSK-3 | asyncpg + SQLAlchemy 2.0 async learning curve | Low | Medium | Use well-documented patterns from SQLAlchemy docs | Low |
| RSK-4 | Missing MinIO service during dev/testing | Low | High | Graceful degradation — log warning, continue without photo storage | Low |

## 12. ASSUMPTIONS

- Docker Compose will provide PostgreSQL and MinIO for development; the plan includes instructions for starting them
- The package will use `scrapy` ≥ 2.11
- The `uv` package manager is available in the development environment
- All infrastructure services (PostgreSQL, MinIO) run locally via Docker

## 13. DEPENDENCIES

| Direction | Item | Notes |
|-----------|------|-------|
| Depends on | PostgreSQL 16 + PostGIS | Running via Docker |
| Depends on | MinIO | Running via Docker (graceful degradation if absent) |
| Blocks | All portal-specific scrapers | They depend on this package |
| Blocks | Documentation website generation | N/A |

## 14. OPEN QUESTIONS

None resolved during planning.

## 15. DECISION LOG

| ID | Decision | Rationale | Date |
|----|----------|-----------|------|
| DEC-1 | Deduplication excluded from STORY-1 | Per Sprint Plan, dedup is Sprint 3 | 2026-06-20 |
| DEC-2 | Package lives under `src/scrapper-base/` (monorepo) | Simpler than separate repo; split later if needed | 2026-06-20 |
| DEC-3 | Alembic included from the start | Schema versioning critical from day one | 2026-06-20 |
| DEC-4 | Full package scaffold with pyproject.toml | Package must be installable immediately | 2026-06-20 |

## 16. AFFECTED COMPONENTS (HIGH-LEVEL)

| Component | Impact |
|-----------|--------|
| `src/scrapper-base/` | New — Python package with 8 modules + tests + Alembic |
| `pyproject.toml` (root) | Might need workspace config if monorepo tooling demands it |

## 17. ACCEPTANCE CRITERIA

| ID | Criterion | Linked |
|----|-----------|--------|
| AC-F1-1 | **Given** a PostgreSQL database is running, **when** `create_async_engine()` is called with `DATABASE_URL`, **then** a working async engine is returned | F-1 |
| AC-F1-2 | **Given** the engine is created, **when** a session is opened, **then** queries execute successfully against the database | F-1 |
| AC-F2-1 | **Given** SQLAlchemy models are defined, **when** `Base.metadata.create_all()` is run, **then** all tables exist in the database | F-2 |
| AC-F3-1 | **Given** Alembic is initialized, **when** `alembic upgrade head` is run, **then** all tables are created with the correct schema | F-3 |
| AC-F4-1 | **Given** a valid property dict, **when** `upsert_property()` is called, **then** the property is inserted and `is_new=True` is returned | F-4 |
| AC-F4-2 | **Given** the same `(portal_source, source_id)` is upserted again, **then** the existing record is updated and `is_new=False` is returned | F-4 |
| AC-F4-3 | **Given** an invalid property dict (missing required fields), **when** `upsert_property()` is called, **then** a `ValueError` is raised and the error is logged | F-4 |
| AC-F5-1 | **Given** a BasePipeline subclass implements `item_to_data()`, **when** `process_item()` is called, **then** the item is persisted and metrics are emitted | F-5 |
| AC-F5-2 | **Given** a BasePipeline subclass, **when** `open_spider()` is called, **then** DB and MinIO connections are initialized | F-5 |
| AC-F6-1 | **Given** a scraped item is processed, **when** metrics are inspected, **then** `listings_scraped_total` is incremented | F-6 |
| AC-F6-2 | **Given** a scrape error occurs, **when** metrics are inspected, **then** `scrape_errors_total` is incremented | F-6 |
| AC-F6-3 | **Given** a DB write operation completes, **when** metrics are inspected, **then** `db_write_duration_seconds` records the duration | F-6 |
| AC-F7-1 | **Given** logging is configured, **when** any log is emitted, **then** it is in JSON format with `timestamp`, `level`, `message`, `portal` | F-7 |
| AC-F8-1 | **Given** MinIO is running, **when** `upload_photo()` is called, **then** the photo is stored and a path is returned | F-8 |
| AC-F8-2 | **Given** MinIO is unavailable, **when** `upload_photo()` is called, **then** a warning is logged and no exception propagates | F-8 |

## 18. ROLLOUT & CHANGE MANAGEMENT (HIGH-LEVEL)

1. Create feature branch: `feature/060-scrapper-base-core` from `main`
2. Implement all phases per implementation plan
3. Run verification checklist
4. Create PR (squash merge to `main`)
5. Tag as `scrapper-base-v0.1.0` when stable

## 19. DATA MIGRATION / SEEDING (IF APPLICABLE)

Initial Alembic migration creates the schema. No data migration needed.

## 20. PRIVACY / COMPLIANCE REVIEW

No personal data is stored by this package directly. Property data fields may contain addresses (street, city, coordinates) which are public listing data.

## 21. SECURITY REVIEW HIGHLIGHTS

- No secrets in code — all credentials via environment variables
- MinIO presigned URLs for temporary access
- Input validation via Pydantic before DB write

## 22. MAINTENANCE & OPERATIONS IMPACT

- Alembic migrations require careful review before applying to production
- Package follows semver; breaking changes require major version bump

## 23. GLOSSARY

| Term | Definition |
|------|------------|
| BasePipeline | Abstract base class for Scrapy pipelines in `scrapper-base` |
| Upsert | Insert or update — if exists by `(portal_source, source_id)`, update; otherwise insert |
| Portal source | Identifier string for each real estate portal (e.g., "otodom", "gratka") |
| scrapper-base | The Python package created by this change (intentional British spelling per project convention) |

## 24. APPENDICES

N/A

## 25. DOCUMENT HISTORY

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-06-20 | plan-writer | Initial specification for STORY-1 |

---

## AUTHORING GUIDELINES

Authored from:
- `doc/spec/features/feature-scrapper-base.md` — ADOS feature spec (draft)
- `specs/060-SCRAPER-BASE.md` — Base pipeline spec module
- `specs/070-DATABASE.md` — Database schema spec module
- `doc/planning/epics/epic-01--scrapper-base-core/epic-01--scrapper-base-core.md` — Epic definition
- Interview with @rendenwald (2026-06-20)

## VALIDATION CHECKLIST

- [x] `change.ref` matches provided `workItemRef` (STORY-1)
- [x] `owners` has at least one entry
- [x] `status` is "Proposed"
- [x] All sections present in order (1-25 + guidelines + checklist)
- [x] ID prefixes consistent and unique (F-, AC-, NFR-, RSK-, DEC-, DM-, OQ-)
- [x] Acceptance criteria reference at least one F-/NFR- ID and use Given/When/Then
- [x] NFRs include measurable values
- [x] Risks include Impact & Probability
- [x] No implementation details (no file-level code paths, no step-by-step tasks)
- [x] No content duplicated from linked docs
- [x] Front matter validates per front_matter_rules
