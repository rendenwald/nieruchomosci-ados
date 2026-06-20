---
id: chg-STORY-1-scrapper-base-core
status: Accepted
created: 2026-06-20
last_updated: 2026-06-20
owners: [rendenwald]
service: scrapper-base
labels: [epic, change]
links:
  change_spec: ./chg-STORY-1-spec.md
summary: >
  Create the scrapper-base Python package with async PostgreSQL connectivity,
  BasePipeline ABC, Prometheus metrics, structured logging, MinIO storage,
  Alembic migrations, and a full package scaffold.
version_impact: minor
---

# IMPLEMENTATION PLAN — STORY-1: Provide BasePipeline with DB, logging, metrics

## Context and Goals

This plan delivers the `src/scrapper-base/` Python package as specified in `chg-STORY-1-spec.md`. The package provides the shared infrastructure all portal-specific scrapers will depend on. Key decisions resolved during planning:

- Deduplication excluded (Sprint 3)
- Package lives under `src/scrapper-base/` (monorepo)
- Alembic migration setup included from the start
- Full package scaffold with `pyproject.toml` and pinned dependencies

## Scope

### In Scope

- Package scaffold with `pyproject.toml`, `CHANGELOG.md`, `README.md`
- `scraper_base/database.py` — async PostgreSQL engine + session factory
- `scraper_base/models.py` — SQLAlchemy ORM models (Property, Agency, ScraperRun)
- Alembic directory with initial migration
- `scraper_base/services.py` — PropertyService with upsert_property()
- `scraper_base/pipeline.py` — BasePipeline ABC
- `scraper_base/metrics.py` — Prometheus metric definitions
- `scraper_base/logging_config.py` — Structured JSON logging
- `scraper_base/storage.py` — MinIO client
- Unit tests for all modules (with mocked external services)
- Verification: lint, type check, test pass, manual smoke test

### Out of Scope

- Deduplication pipeline (Sprint 3)
- Portal-specific scrapers
- Grafana dashboards
- Docker Compose setup (developer runs services manually or via separate `docker-compose.yml` later)

### Constraints

- All credentials via environment variables (never hardcoded)
- All public functions have type hints
- Async only (no synchronous DB access)
- Follow existing `specs/` conventions for module structure

### Risks

- **RSK-1**: PostgreSQL 16 + PostGIS not available locally → Mitigated by Docker setup instructions in plan
- **RSK-2**: MinIO not available during testing → Mitigated by graceful degradation in storage module
- **RSK-3**: asyncpg + SQLAlchemy 2.0 async patterns unfamiliar → Mitigated by well-documented reference patterns

### Success Metrics

- Package installable via `uv pip install -e src/scrapper-base/`
- All tests pass with ≥ 80% coverage
- `ruff check` passes with zero warnings
- `mypy --strict` passes on all modules
- New scraper can be created by subclassing `BasePipeline` and implementing `item_to_data()`

## Phases

### Phase 1: Package Scaffold

**Goal**: Create the initial package directory structure, pyproject.toml with pinned dependencies, and skeleton modules.

**Tasks**:

- [ ] **1.1** Create directory tree: `src/scrapper-base/src/scraper_base/`, `src/scrapper-base/tests/`, `src/scrapper-base/alembic/`
- [ ] **1.2** Write `src/scrapper-base/pyproject.toml`:
  - Package name: `scrapper-base`
  - Version: `0.1.0`
  - Python: `>=3.12`
  - Dependencies: `sqlalchemy>=2.0,<3.0`, `asyncpg>=0.29,<1.0`, `scrapy>=2.11,<3.0`, `prometheus-client>=0.20,<1.0`, `structlog>=24.0,<25.0`, `minio>=7.2,<8.0`, `pydantic>=2.0,<3.0`, `alembic>=1.13,<2.0`, `geoalchemy2>=0.15,<1.0`
  - Dev dependencies: `pytest>=8.0,<9.0`, `pytest-asyncio>=0.24,<1.0`, `pytest-cov>=5.0,<6.0`, `ruff>=0.5,<1.0`, `mypy>=1.10,<2.0`
  - Build system: `setuptools>=70.0`
- [ ] **1.3** Write `src/scrapper-base/src/scraper_base/__init__.py` with version string and clean public API exports
- [ ] **1.4** Write `src/scrapper-base/CHANGELOG.md` with initial entry
- [ ] **1.5** Write `src/scrapper-base/README.md` (brief — points to project docs)
- [ ] **1.6** Write `src/scrapper-base/pyproject.toml` build configuration

**Acceptance Criteria**:

- Must: `uv pip install -e src/scrapper-base/` succeeds
- Must: `python -c "import scraper_base; print(scraper_base.__version__)"` prints `0.1.0`

**Files and modules**:

- `src/scrapper-base/pyproject.toml` (new)
- `src/scrapper-base/CHANGELOG.md` (new)
- `src/scrapper-base/README.md` (new)
- `src/scrapper-base/src/scraper_base/__init__.py` (new)

**Tests**:

- `python -c "import scraper_base"` — import works

**Completion signal**: `feat(STORY-1): scaffold scrapper-base package with pyproject.toml`

---

### Phase 2: Database Layer

**Goal**: Create async PostgreSQL connection management, SQLAlchemy ORM models, and Alembic migration setup.

**Tasks**:

- [ ] **2.1** Write `src/scrapper-base/src/scraper_base/database.py`:
  - `create_async_engine(database_url: str, pool_size: int = 5)` → `AsyncEngine`
  - `create_session_factory(engine: AsyncEngine)` → `async_sessionmaker`
  - `get_db_session()` → async context manager yielding `AsyncSession`
  - Retry logic: 3 attempts with exponential backoff (1s, 2s, 4s)
  - Config via `DATABASE_URL` env var with default `postgresql+asyncpg://localhost:5432/realestate`
- [ ] **2.2** Write `src/scrapper-base/src/scraper_base/models.py`:
  - `Property` model with all fields from `specs/070-DATABASE.md`:
    - `id` (UUID PK), `portal_source`, `source_id`, `source_url`, `title`, `description`
    - `property_type`, `market_type`, `offered_by`
    - `price`, `price_currency`, `price_per_m2`, `rent`
    - `area`, `plot_area`, `rooms`, `floor`, `floors_total`, `year_built`
    - `condition`, `heating`, `extras`
    - `province`, `city`, `district`, `street`
    - `latitude`, `longitude`, `location` (PostGIS `Geometry`)
    - `photos` (JSONB), `localization` (JSONB), `building` (JSONB)
    - `agency_name`, `agency_source_id`
    - `is_promoted`, `promotion_expires_at`
    - `duplicate_group_id` (UUID, nullable), `is_canonical` (default True)
    - `scraped_at`, `last_seen_at`, `is_active`, `source_created_at`
    - Unique constraint on `(portal_source, source_id)`
    - Indexes on: `city`, `portal_source`, `is_active`, `last_seen_at`, `location` (GIST)
  - `Agency` model: `id` (UUID PK), `name`, `source_id`, `portal_source`, `phone`, `email`, `logo_url`, `created_at`, `updated_at`
  - `ScraperRun` model: `id` (UUID PK), `portal_source`, `started_at`, `finished_at`, `items_scraped`, `errors`, `status` (enum: running, completed, failed)
  - All models use `TZTimeStamp` aware UTC timestamps
- [ ] **2.3** Initialize Alembic:
  - Create `src/scrapper-base/alembic/env.py` — async Alembic config with `run_async_migrations()`
  - Create `src/scrapper-base/alembic.ini` — referencing `alembic/` directory
  - Create `src/scrapper-base/alembic/script.py.mako` — migration template
  - Create initial migration: `src/scrapper-base/alembic/versions/0001_create_core_tables.py`
    - Create `properties` table with LIST partition by `portal_source`
    - Create `agencies` table
    - Create `scraper_runs` table
    - Create unique index on `properties(portal_source, source_id)`
    - Create GIST index on `properties.location`
    - Note: LIST partitioning requires PostGIS extension to be installed first
- [ ] **2.4** Write `src/scrapper-base/src/scraper_base/db_utils.py`:
  - `check_connection(engine)` — health check function
  - `init_db()` — create all tables (convenience for tests / dev)

**Acceptance Criteria**:

- Must: `alembic upgrade head` creates all 3 tables
- Must: `alembic downgrade -1` drops all tables
- Must: Async engine connects and executes a simple query against a running PostgreSQL
- Must: Property unique constraint on `(portal_source, source_id)` is enforced

**Files and modules**:

- `src/scrapper-base/src/scraper_base/database.py` (new)
- `src/scrapper-base/src/scraper_base/models.py` (new)
- `src/scrapper-base/src/scraper_base/db_utils.py` (new)
- `src/scrapper-base/alembic.ini` (new)
- `src/scrapper-base/alembic/env.py` (new)
- `src/scrapper-base/alembic/script.py.mako` (new)
- `src/scrapper-base/alembic/versions/0001_create_core_tables.py` (new)

**Tests**:

- `tests/test_database.py` — engine creation, session lifecycle, connection failure retry
- `tests/test_models.py` — model instantiation, relationship loading, constraint enforcement

**Completion signal**: `feat(STORY-1): add database models, async engine, and Alembic migration`

---

### Phase 3: Services Layer

**Goal**: Implement the PropertyService with upsert logic and query methods.

**Tasks**:

- [ ] **3.1** Write `src/scrapper-base/src/scraper_base/services.py`:
  - `PropertyService` class:
    - `__init__(self, session: AsyncSession)`
    - `async upsert_property(data: dict) -> tuple[Property, bool]`:
      - Validate input fields against Pydantic model
      - Look up existing by `(portal_source, source_id)`
      - If exists: update all mutable fields, set `last_seen_at = NOW()`, return `(property, False)`
      - If new: insert with `scraped_at = NOW()`, `last_seen_at = NOW()`, return `(property, True)`
      - Emit `db_write_duration_seconds` histogram with `operation` label (upsert/insert)
    - `async get_by_source(portal: str, source_id: str) -> Property | None`
    - `async get_active_listings(portal: str | None = None, limit: int = 100) -> list[Property]`
    - `async mark_inactive(portal: str, older_than: datetime) -> int` — soft-delete stale listings
  - `AgencyService` class (simple):
    - `async upsert_agency(data: dict) -> Agency`
    - `async get_by_source(portal: str, source_id: str) -> Agency | None`
  - Input validation using Pydantic models:
    - `PropertyCreate(BaseModel)` — validates required fields, types, ranges
    - `PropertyUpdate(BaseModel)` — partial update validation

**Acceptance Criteria**:

- Must: New property upsert → inserted, `is_new=True`
- Must: Existing property upsert → updated, `is_new=False`, `last_seen_at` changed
- Must: Invalid data → `ValueError` raised with descriptive message
- Must: Concurrent upserts of same key → no duplicate records

**Files and modules**:

- `src/scrapper-base/src/scraper_base/services.py` (new)

**Tests**:

- `tests/test_services.py` — upsert flow, update flow, validation errors, edge cases

**Completion signal**: `feat(STORY-1): implement PropertyService with upsert and validation`

---

### Phase 4: Cross-Cutting Concerns

**Goal**: Implement BasePipeline ABC, Prometheus metrics, structured logging, and MinIO storage client.

**Tasks**:

- [ ] **4.1** Write `src/scrapper-base/src/scraper_base/pipeline.py`:
  ```python
  class BasePipeline(ABC):
      PORTAL_SOURCE: str

      def __init__(self):
          self.db_session: AsyncSession | None = None
          self.minio_client: Minio | None = None
          self.scraper_id: str = str(uuid.uuid4())
          self.run_id: str = str(uuid.uuid4())
          self.logger = get_logger(self.PORTAL_SOURCE, self.scraper_id, self.run_id)

      @abstractmethod
      def item_to_data(self, item: ScrapyItem) -> dict:
          """Convert ScrapyItem to property data dict."""
          ...

      async def open_spider(self, spider: Spider) -> None:
          """Initialize DB session and MinIO client. Track start in scraper_runs."""
          ...

      async def close_spider(self, spider: Spider) -> None:
          """Flush metrics, close session, update scraper_run status."""
          ...

      async def process_item(self, item: ScrapyItem, spider: Spider) -> dict:
          """Process item: validate, upsert, emit metrics."""
          ...
  ```
  - Include error handling: catch exceptions, increment `scrape_errors_total`, log, re-raise
  - Track run via `ScraperRun` model (start on `open_spider`, finish on `close_spider`)
- [ ] **4.2** Write `src/scrapper-base/src/scraper_base/metrics.py`:
  - Module-level metric definitions:
    - `listings_scraped_total = Counter("listings_scraped_total", "Total listings scraped", ["portal", "city", "type"])`
    - `scrape_errors_total = Counter("scrape_errors_total", "Total scrape errors", ["portal", "error_type"])`
    - `scrape_duration_seconds = Histogram("scrape_duration_seconds", "Scrape duration", ["portal"], buckets=[1, 5, 10, 30, 60, 120, 300, 600])`
    - `db_write_duration_seconds = Histogram("db_write_duration_seconds", "DB write duration", ["operation"], buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0])`
    - `active_listings_gauge = Gauge("active_listings_gauge", "Active listings", ["portal"])`
  - Helper functions:
    - `increment_listings_scraped(portal, city, type)`
    - `increment_errors(portal, error_type)`
    - `observe_scrape_duration(portal, duration)`
    - `observe_db_write(operation, duration)`
    - `set_active_listings(portal, count)`
  - These use the global prometheus_client registry (Scrapy can expose `/metrics` via extensions)
- [ ] **4.3** Write `src/scrapper-base/src/scraper_base/logging_config.py`:
  - `configure_logging(level=INFO)` — sets up structlog with:
    - JSON renderer for production (`structlog.processors.JSONRenderer`)
    - Console renderer for development
    - Timestamp in ISO-8601 with timezone
    - Standard fields: `timestamp`, `level`, `logger`, `message`, `portal`, `scraper_id`, `run_id`
  - `get_logger(portal, scraper_id, run_id)` — returns a bound logger with those fields pre-populated
- [ ] **4.4** Write `src/scrapper-base/src/scraper_base/storage.py`:
  - `MinioStorageClient` class:
    - `__init__(self)` — reads `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `MINIO_BUCKET` from env
    - `async ensure_bucket(bucket: str | None = None)` — create bucket if not exists
    - `async upload_photo(data: bytes, object_name: str | None = None) -> str` — upload with SHA256 object name
    - `async get_photo_url(object_name: str, expires: int = 3600) -> str` — presigned GET URL
    - Graceful degradation: if MinIO is unavailable or misconfigured, log warning, return None
  - Singleton pattern: reuse client across scraper runs

**Acceptance Criteria**:

- Must: BasePipeline subclass with `item_to_data()` can be instantiated and `process_item()` persists data
- Must: Metrics module increments counters correctly
- Must: Logs are emitted as JSON with required fields
- Must: MinIO client uploads a photo and returns a path
- Must: MinIO client degrades gracefully when MinIO is unavailable

**Files and modules**:

- `src/scrapper-base/src/scraper_base/pipeline.py` (new)
- `src/scrapper-base/src/scraper_base/metrics.py` (new)
- `src/scrapper-base/src/scraper_base/logging_config.py` (new)
- `src/scrapper-base/src/scraper_base/storage.py` (new)

**Tests**:

- `tests/test_pipeline.py` — pipeline lifecycle, error handling, metric emission
- `tests/test_metrics.py` — counter/histogram/gauge behavior, label correctness
- `tests/test_logging.py` — JSON format, field presence, bound logger
- `tests/test_storage.py` — upload, URL generation, graceful degradation

**Completion signal**: `feat(STORY-1): add BasePipeline, metrics, logging, and MinIO storage`

---

### Phase 5: Tests & Verification

**Goal**: Write comprehensive unit tests, configure linting/type checking, and verify everything works.

**Tasks**:

- [ ] **5.1** Write `src/scrapper-base/tests/conftest.py`:
  - Async fixtures for in-memory SQLite (for model tests) and test PostgreSQL (when available)
  - Mock fixtures for MinIO, Prometheus registry
  - Fixture for `PropertyService` with mocked session
  - Fixture for `BasePipeline` subclass (e.g., `TestPipeline`)
- [ ] **5.2** Write `src/scrapper-base/tests/test_database.py`:
  - Test engine creation and session lifecycle
  - Test connection retry with mock failure
  - Test `check_connection()` health check
- [ ] **5.3** Write `src/scrapper-base/tests/test_models.py`:
  - Test model creation with valid/invalid data
  - Test unique constraint on `(portal_source, source_id)`
  - Test relationship loading
  - Test default values
- [ ] **5.4** Write `src/scrapper-base/tests/test_services.py`:
  - Test `upsert_property` — new insert, existing update
  - Test `upsert_property` — invalid data raises `ValueError`
  - Test `get_by_source` — found, not found
  - Test `get_active_listings` — filtered by portal, limit
  - Test `mark_inactive` — soft-delete stale records
  - Test concurrent upserts (async)
- [ ] **5.5** Write `src/scrapper-base/tests/test_pipeline.py`:
  - Test `open_spider` initializes connections
  - Test `close_spider` cleans up connections
  - Test `process_item` calls `item_to_data()` and `upsert_property()`
  - Test error handling — exception in `item_to_data()` increments error counter
  - Test `ScraperRun` tracking (started → completed/failed)
- [ ] **5.6** Write `src/scrapper-base/tests/test_metrics.py`:
  - Test counter increment with labels
  - Test histogram observation
  - Test gauge set
  - Test metric values after pipeline processing
- [ ] **5.7** Write `src/scrapper-base/tests/test_logging.py`:
  - Test JSON log format
  - Test field presence (`timestamp`, `level`, `message`, `portal`, `scraper_id`, `run_id`)
  - Test bound logger carries fields
- [ ] **5.8** Write `src/scrapper-base/tests/test_storage.py`:
  - Test upload with mock MinIO
  - Test presigned URL generation
  - Test graceful degradation when MinIO unavailable
- [ ] **5.9** Configure linting and type checking:
  - Add `ruff` configuration to `pyproject.toml`:
    ```toml
    [tool.ruff]
    line-length = 100
    target-version = "py312"

    [tool.ruff.lint]
    select = ["E", "F", "I", "N", "W", "UP"]

    [tool.mypy]
    strict = true
    ignore_missing_imports = true
    ```
  - Add `pytest` configuration:
    ```toml
    [tool.pytest.ini_options]
    asyncio_mode = "auto"
    testpaths = ["tests"]
    ```
- [ ] **5.10** Run verification:
  - `ruff check src/scrapper-base/` — zero warnings
  - `mypy src/scrapper-base/ --strict` — zero errors
  - `pytest src/scrapper-base/tests/ -v --cov=scraper_base --cov-fail-under=80` — all pass

**Acceptance Criteria**:

- Must: Code coverage ≥ 80%
- Must: `ruff check` passes with zero warnings
- Must: `mypy --strict` passes with zero errors
- Must: All tests pass

**Files and modules**:

- `src/scrapper-base/tests/conftest.py` (new)
- `src/scrapper-base/tests/test_database.py` (new)
- `src/scrapper-base/tests/test_models.py` (new)
- `src/scrapper-base/tests/test_services.py` (new)
- `src/scrapper-base/tests/test_pipeline.py` (new)
- `src/scrapper-base/tests/test_metrics.py` (new)
- `src/scrapper-base/tests/test_logging.py` (new)
- `src/scrapper-base/tests/test_storage.py` (new)

**Tests**:

- Self-referential — the tests themselves are the validation.

**Completion signal**: `test(STORY-1): add comprehensive unit tests and verification`

---

### Phase 6: Manual Smoke Test

**Goal**: Run a manual end-to-end verification that the package works with real infrastructure.

**Tasks**:

- [ ] **6.1** Start PostgreSQL (if Docker available: `docker run -d --name pg16 -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=realestate -p 5432:5432 postgis/postgis:16-3.4`)
- [ ] **6.2** Run Alembic migration: `alembic upgrade head`
- [ ] **6.3** Verify tables exist: `psql -h localhost -U postgres -d realestate -c "\dt"`
- [ ] **6.4** Run a Python script that:
  - Creates an engine and session
  - Upserts a test property
  - Queries it back
  - Logs the result
- [ ] **6.5** Start MinIO (if Docker available: `docker run -d --name minio -p 9000:9000 -p 9001:9001 minio/minio server /data --console-address ":9001"`)
- [ ] **6.6** Verify MinIO client uploads a test photo
- [ ] **6.7** Run final `pytest` to confirm all tests pass
- [ ] **6.8** Create PR

**Acceptance Criteria**:

- Must: End-to-end flow works with real PostgreSQL
- Must: `alembic upgrade head` + `downgrade -1` produces no errors
- Must: All automated tests pass

**Completion signal**: `feat(STORY-1): complete scrapper-base with smoke test verification`

---

## Test Scenarios

| ID | Scenario | Phases | AC |
|----|----------|--------|----|
| T-1 | Database engine creates successfully and runs a query | 2 | AC-F1-1 |
| T-2 | Tables created by Alembic migration match model definitions | 2 | AC-F2-1, AC-F3-1 |
| T-3 | New property upsert inserts record and returns `is_new=True` | 3 | AC-F4-1 |
| T-4 | Existing property upsert updates record and returns `is_new=False` | 3 | AC-F4-2 |
| T-5 | Invalid property data raises `ValueError` | 3 | AC-F4-3 |
| T-6 | BasePipeline subclass processes item end-to-end | 4 | AC-F5-1 |
| T-7 | `listings_scraped_total` increments after processing | 4 | AC-F6-1 |
| T-8 | `scrape_errors_total` increments on error | 4 | AC-F6-2 |
| T-9 | `db_write_duration_seconds` records after upsert | 4 | AC-F6-3 |
| T-10 | Log output is valid JSON with required fields | 4 | AC-F7-1 |
| T-11 | MinIO upload succeeds when server is available | 4 | AC-F8-1 |
| T-12 | MinIO upload degrades gracefully when server is unavailable | 4 | AC-F8-2 |

## Artifacts and Links

| Artifact | Location | Type |
|----------|----------|------|
| Change specification | `./chg-STORY-1-spec.md` | Spec |
| Implementation plan | `./chg-STORY-1-plan.md` | Plan |
| Package scaffold | `src/scrapper-base/pyproject.toml` | Config |
| Package init | `src/scrapper-base/src/scraper_base/__init__.py` | Code |
| Database module | `src/scrapper-base/src/scraper_base/database.py` | Code |
| Models module | `src/scrapper-base/src/scraper_base/models.py` | Code |
| DB utilities | `src/scrapper-base/src/scraper_base/db_utils.py` | Code |
| Alembic config | `src/scrapper-base/alembic.ini` | Config |
| Alembic env | `src/scrapper-base/alembic/env.py` | Config |
| Alembic migration | `src/scrapper-base/alembic/versions/0001_create_core_tables.py` | Migration |
| Services module | `src/scrapper-base/src/scraper_base/services.py` | Code |
| Pipeline module | `src/scrapper-base/src/scraper_base/pipeline.py` | Code |
| Metrics module | `src/scrapper-base/src/scraper_base/metrics.py` | Code |
| Logging module | `src/scrapper-base/src/scraper_base/logging_config.py` | Code |
| Storage module | `src/scrapper-base/src/scraper_base/storage.py` | Code |
| Tests | `src/scrapper-base/tests/*.py` | Tests |

## Plan Revision Log

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-06-20 | plan-writer | Initial plan |

## Execution Log

| Phase | Status | Started | Completed | Commit | Notes |
|-------|--------|---------|-----------|--------|-------|
| Phase 1: Package Scaffold | completed | 2026-06-20 | 2026-06-20 | — | Package installed via uv, import verified |
| Phase 2: Database Layer | completed | 2026-06-20 | 2026-06-20 | — | ruff/mypy clean, imports verified |
| Phase 3: Services Layer | pending | — | — | — | — |
| Phase 4: Cross-Cutting | pending | — | — | — | — |
| Phase 5: Tests & Verification | pending | — | — | — | — |
| Phase 6: Manual Smoke Test | pending | — | — | — | — |
