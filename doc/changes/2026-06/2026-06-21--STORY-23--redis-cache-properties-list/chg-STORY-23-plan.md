---
# Copyright (c) 2025-2026 Juliusz Ćwiąkalski
# MIT License - see LICENSE file for full terms
source: https://github.com/juliusz-cwiakalski/agentic-delivery-os/blob/main/doc/templates/implementation-plan-template.md
id: chg-STORY-23-redis-cache-properties-list
status: Proposed
created: 2026-06-21T12:00:00Z
last_updated: 2026-06-21T12:00:00Z
owners: [rendenwald]
service: real-estate-api
labels: ["change"]
links:
  change_spec: ./chg-STORY-23-spec.md
summary: >
  This change adds a Redis cache-aside layer to the GET /api/v1/properties endpoint.
  On each request, the cache is checked first using a deterministic key derived from
  the query parameters. On a cache miss, the database is queried and the result stored
  in Redis with a 120-second TTL. Responses include an X-Cache: hit|miss header for
  observability. If Redis is unreachable, the system falls back to a direct database
  query transparently.
version_impact: minor
---

# IMPLEMENTATION PLAN — STORY-23: Serve `/api/v1/properties` from Redis Cache (TTL 2min)

## Context and Goals

This plan delivers a Redis cache-aside layer for the `GET /api/v1/properties` endpoint
in the new `real-estate-api` FastAPI service. The service is built alongside the existing
`src/scrapper-base/` package, which provides the Property ORM model and async database
session infrastructure.

**What this delivers:**
- New FastAPI application (`src/real-estate-api/`) with core configuration, schemas,
  and a properties list endpoint
- Cache service with deterministic SHA-256 key derivation from normalized query parameters
- Redis `SET NX` or `asyncio.Lock` concurrency guard to prevent thundering herd
- `X-Cache: hit | miss | miss (fallback)` response headers for observability
- Prometheus counters/histograms for cache hits, misses, errors, and operation latency
- Graceful degradation — transparent DB fallback when Redis is unreachable
- Health check endpoint with Redis connectivity status
- Docker Compose integration with a `real-estate-api` service
- Comprehensive test suite using `fakeredis` for unit testing

**Open questions:**
- **OQ-1** (from spec): `page` and `limit` are included in the cache key per-page.
  Decision: cache per-page (smaller payloads, simpler). Revisit if a different
  pagination strategy is adopted.
- **OQ-3** (from spec): Health-check interval (30s) and degraded-mode threshold (3 failures)
  should be configurable via env vars. Spec recommends it; this plan makes them configurable.

## Scope

### In Scope

- **F-1**: Deterministic cache key generation from normalized query parameters using SHA-256
- **F-2**: Cache-aside read pattern with 120s TTL (Redis SETEX on miss, GET on request)
- **F-3**: `X-Cache: hit | miss | miss (fallback)` response header
- **F-4**: Graceful fallback to direct DB query when Redis is unreachable
- **F-5**: Configurable Redis connection with health-check, connection pool, and timeouts
- All 10 acceptance criteria (AC-F1-1 through AC-NFR-2)
- Prometheus metrics: `cache_hits_total`, `cache_misses_total`, `cache_errors_total`,
  `cache_operation_duration_seconds`, `cache_entry_size_bytes`
- Redis health status in `GET /health` endpoint
- Concurrent request deduplication to prevent thundering herd
- Dockerfile for `real-estate-api` and docker-compose service entry

### Out of Scope

- Cache invalidation on property upsert — covered by STORY-24
- Caching other endpoints (`/api/v1/properties/{id}`, `/api/v1/cities`, `/api/v1/stats`)
- Redis Streams or pub/sub for cross-instance cache invalidation
- Redis Sentinel or Cluster configuration for high availability
- Cache pre-warming or seeding logic
- Frontend changes — API contract (request/response shape) is unchanged
- Database query optimization — the DB query itself is not changed, only cached
- API authentication/authorization changes

### Constraints

- Must use `redis.asyncio` (official `redis-py` v5+) — no deprecated `aioredis` library
- Must use `fakeredis` for unit tests — no real Redis dependency in CI
- Must import `Property` model and `AsyncSession` from `scrapper-base` as editable dependency
- Must keep `max_limit=100` as hard upper bound for pagination
- Must use `uv` for virtualenv management (project convention)
- Python 3.12+ required (matches scrapper-base)
- Docker Compose only for MVP — no k8s manifests in this story

### Risks

- **RSK-1 (Redis outage)**: Redis becomes unavailable → cache misses but no data loss.
  Mitigated by graceful DB fallback with health-check auto-recovery per F-4.
- **RSK-2 (Stale data)**: 120s TTL may serve stale data after property upsert.
  Mitigated by TTL being a deliberate product trade-off; STORY-24 adds proactive invalidation.
- **RSK-4 (Memory exhaustion)**: `allkeys-lru` + 1 GB maxmemory prevents OOM.
  Monitor `cache_errors_total` for eviction-related issues.
- **RSK-5 (Redis timeout latency)**: 2s timeout on Redis ops could increase p99 latency.
  Mitigated by early timeout + catch-all fallback to DB.
- **RSK-6 (Thundering herd)**: Multiple concurrent requests for the same uncached key
  all hit the DB simultaneously. Mitigated by `SET NX` lock or `asyncio.Lock` per key.

### Success Metrics

| Metric | Target | Verification |
|--------|--------|-------------|
| p95 response latency (cache hit) | < 10 ms | Prometheus histogram |
| p95 response latency (cache miss / fallback) | < 200 ms | Prometheus histogram |
| Cache hit ratio (steady state) | ≥ 70% | `cache_hits_total / (cache_hits_total + cache_misses_total)` |
| DB query rate reduction | ≥ 70% | Compare pre/post query rate on `/api/v1/properties` |
| Error rate during Redis outage | 0% | No 5xx responses when Redis is stopped |

## Phases

### Phase 1: Scaffold FastAPI Project Structure

**Goal**: Create the `src/real-estate-api/` application skeleton with package layout,
dependency management, and editable link to `scrapper-base`.

**Tasks**:

- [x] **1.1** Create directory tree: `app/`, `app/core/`, `app/services/`, `app/routers/`,
      `app/schemas/`, `tests/` (done)
- [x] **1.2** Create `pyproject.toml` with dependencies: `fastapi`, `uvicorn[standard]`,
      `sqlalchemy>=2.0,<3.0`, `asyncpg>=0.29,<1.0`, `redis>=5.0,<6.0`,
      `pydantic>=2.0,<3.0`, `pydantic-settings>=2.0,<3.0`, `prometheus-client>=0.20,<1.0`,
      `structlog>=24.0,<25.0`, `geoalchemy2>=0.15,<1.0` plus `scrapper-base` as
      path dependency (`[tool.uv.sources]` with `editable = true`) (done)
- [x] **1.3** Add dev dependencies: `pytest>=8.0,<9.0`, `pytest-asyncio>=0.24,<1.0`,
      `pytest-cov>=5.0,<6.0`, `fakeredis[lua]>=2.20,<3.0`, `ruff>=0.5,<1.0`,
      `mypy>=1.10,<2.0`, `httpx>=0.27,<1.0` (for TestClient) (done)
- [x] **1.4** Create `app/__init__.py` and all `__init__.py` files for subpackages (done)
- [x] **1.5** Create `app/main.py` with FastAPI app factory (`create_app()` function)
      returning the ASGI application, with lifespan handler for startup/shutdown (done)
- [x] **1.6** Configure ruff and mypy settings in `pyproject.toml` matching
      scrapper-base conventions (line-length 120, strict mypy) (done)
- [x] **1.7** Run `uv sync` to create virtualenv and resolve dependencies (done, all 88 packages resolved)

**Acceptance Criteria**:

- Must: `uv run python -c "from real_estate_api.app import create_app; app = create_app()"` succeeds
- Must: `uv run ruff check .` on the new project passes with no errors
- Must: `uv run mypy . --strict` on the new project passes (no code yet, so minimal)

**Files and modules**:

- `src/real-estate-api/pyproject.toml` (new)
- `src/real-estate-api/app/__init__.py` (new)
- `src/real-estate-api/app/main.py` (new)
- `src/real-estate-api/app/core/__init__.py` (new)
- `src/real-estate-api/app/services/__init__.py` (new)
- `src/real-estate-api/app/routers/__init__.py` (new)
- `src/real-estate-api/app/schemas/__init__.py` (new)
- `src/real-estate-api/tests/__init__.py` (new)

**Tests**:

- Verify package imports resolve correctly
- Verify `create_app()` returns a valid FastAPI instance

**Completion signal**: `feat(STORY-23): scaffold real-estate-api project structure`

---

### Phase 2: Core Configuration Module

**Goal**: Create centralized application configuration using `pydantic-settings`,
covering Redis connection, database connection, API settings, and Prometheus metrics.

**Tasks**:

- [x] **2.1** Create `app/core/config.py` with `Settings(BaseSettings)` class (done during Phase 1)
- [x] **2.2** Create `app/core/__init__.py` that exports `get_settings()` singleton (done during Phase 1)
- [x] **2.3** Create `app/core/metrics.py` with Prometheus metric definitions (done):
  - `cache_hits = Counter("cache_hits_total", "...", ["endpoint", "cache_key_prefix"])`
  - `cache_misses = Counter("cache_misses_total", "...", ["endpoint", "cache_key_prefix"])`
  - `cache_errors = Counter("cache_errors_total", "...", ["endpoint", "operation", "error_type"])`
  - `cache_duration = Histogram("cache_operation_duration_seconds", "...", ["endpoint", "operation"])`
  - `cache_entry_size = Gauge("cache_entry_size_bytes", "...", ["endpoint"])`

**Acceptance Criteria**:

- Must: Settings load from env vars with correct defaults
- Must: Metrics objects are created and registered with the default registry
- Should: Settings are frozen/immutable after construction

**Files and modules**:

- `src/real-estate-api/app/core/config.py` (new)
- `src/real-estate-api/app/core/__init__.py` (updated)
- `src/real-estate-api/app/core/metrics.py` (new)

**Tests**:

- Unit test: settings load from env vars (monkeypatch)
- Unit test: default values match spec

**Completion signal**: `feat(STORY-23): add core configuration and Prometheus metrics`

---

### Phase 3: Cache Service

**Goal**: Implement Redis connection management, cache key generation, and the
cache-aside `get_or_compute` pattern with graceful fallback.

**Tasks**:

- [x] **3.1** Create `app/services/redis_client.py` with `RedisClient` class (done)
- [x] **3.2** Create `app/services/cache_key.py` with cache key utility (done)
- [x] **3.3** Create `app/services/cache_service.py` with `CacheService` class (done)
- [x] **3.4** Wire `RedisClient` into lifecycle — instantiate in `create_app()` lifespan,
      attach to `app.state.redis_client` and `app.state.cache_service` (done)

**Acceptance Criteria**:

- Must: Cache key is deterministic for identical params regardless of ordering (AC-F1-2)
- Must: Cache key format matches `properties:list:v1:{sha256hex}` (AC-F1-1)
- Must: `get_or_compute` returns `("...", "miss")` on first call and stores in Redis
- Must: `get_or_compute` returns `("...", "hit")` on second call within TTL (AC-F2-2)
- Must: After TTL expiry, next call returns `miss` (AC-F2-3)
- Must: When Redis is unreachable, returns `("...", "miss (fallback)")` (AC-F4-1)
- Must: Concurrent requests for same key do **one** DB query (thundering herd prevention)
- Should: Cache errors increment `cache_errors_total` counter (AC-F4-2)

**Files and modules**:

- `src/real-estate-api/app/services/redis_client.py` (new)
- `src/real-estate-api/app/services/cache_key.py` (new)
- `src/real-estate-api/app/services/cache_service.py` (new)
- `src/real-estate-api/app/services/__init__.py` (updated)
- `src/real-estate-api/app/main.py` (updated — lifespan wiring)

**Tests**:

- Unit test: `normalize_params` produces identical output for `{"page": 1, "city": "W"}`
  and `{"city": "W", "page": 1}`
- Unit test: `make_cache_key` produces expected format
- Unit test: `get_or_compute` returns miss on first call (fakeredis)
- Unit test: `get_or_compute` returns hit on repeated call (fakeredis)
- Unit test: TTL expiry triggers miss (fakeredis with TTL manipulation)
- Unit test: fallback when Redis connection fails (mock to raise exception)

**Completion signal**: `feat(STORY-23): implement cache service with Redis async client`

---

### Phase 4: Pydantic Schemas

**Goal**: Define Pydantic models for request validation, response serialization,
and API documentation.

**Tasks**:

- [x] **4.1** Create `app/schemas/common.py`:
  - `ErrorResponse(BaseModel)` — `detail: str`
  - `PaginatedResponse(BaseModel, Generic[T])` — `items: list[T]`,
    `total: int`, `page: int`, `limit: int`, `total_pages: int` (done)
- [x] **4.2** Create `app/schemas/property.py`:
  - `PropertyCard(BaseModel)` — subset of Property fields for listing
  - `SearchParams(BaseModel)` — all filter params with validation
  - `SearchResponse = PaginatedResponse[PropertyCard]` (done)

**Acceptance Criteria**:

- Must: `SearchParams` validates `limit` ≤ 100 (AC-7)
- Must: Invalid params produce 422 (AC-8)
- Must: `page` defaults to 1, `limit` defaults to 20
- Must: `sort_by` validates format `field:direction` (AC-9)
- Should: `PropertyCard` field types match spec types

**Files and modules**:

- `src/real-estate-api/app/schemas/common.py` (new)
- `src/real-estate-api/app/schemas/property.py` (new)
- `src/real-estate-api/app/schemas/__init__.py` (updated)

**Tests**:

- Unit test: `SearchParams` validates limits (0, 100, 101)
- Unit test: `SearchParams` accepts valid sort strings
- Unit test: `SearchParams` rejects invalid sort format
- Unit test: `PropertyCard` serializes from partial dict

**Completion signal**: `feat(STORY-23): add Pydantic schemas for properties API`

---

### Phase 5: Properties Router with Cache Integration

**Goal**: Implement `GET /api/v1/properties` with SQLAlchemy query building,
cache-aside integration, pagination, and `X-Cache` headers.

**Tasks**:

- [x] **5.1** Create `app/services/property_service.py` with query building (done)
- [x] **5.2** Create `app/routers/properties.py`: GET /api/v1/properties with cache-aside (done)
- [x] **5.3** Register router in `app/main.py` under /api/v1 prefix (done)
- [x] **5.4** Add startup Redis health check in lifespan (done — RedisClient.connect() pings)

**Acceptance Criteria**:

- Must: Valid params return 200 with paginated `PropertyCard[]` (AC-1)
- Must: `X-Cache: miss` on first request, `X-Cache: hit` on repeat (AC-2, AC-3)
- Must: 120s TTL enforced — after expiry, next request is a miss (AC-4)
- Must: `X-Cache: miss (fallback)` when Redis unreachable, still 200 (AC-5)
- Must: `max_limit=100` enforced (AC-7)
- Must: Invalid params return 422 (AC-8)
- Must: Sort parameter works (AC-9)
- Must: Multiple concurrent requests for same key do one DB query (AC-10)

**Files and modules**:

- `src/real-estate-api/app/services/property_service.py` (new)
- `src/real-estate-api/app/routers/properties.py` (new)
- `src/real-estate-api/app/main.py` (updated — router registration + lifespan)
- `src/real-estate-api/app/services/__init__.py` (updated)

**Tests**:

- Integration test: GET `/api/v1/properties` returns 200 with correct shape
- Integration test: X-Cache header present on all responses (AC-3)
- Integration test: repeat request returns hit (AC-2)
- Integration test: invalid params return 422 (AC-8)
- Integration test: limit=101 returns 422 (AC-7)
- Integration test: sort param works (AC-9)

**Completion signal**: `feat(STORY-23): implement /api/v1/properties with cache-aside`

---

### Phase 6: Health Endpoint

**Goal**: Implement and extend the health check endpoint to include Redis connectivity status.

**Tasks**:

- [x] **6.1** Create `app/routers/health.py`: GET /health with redis status (done)
- [x] **6.2** Register `/health` router in `app/main.py` (done)
- [x] **6.3** Wire background health-check loop into the app lifespan (done)

**Acceptance Criteria**:

- Must: `GET /health` returns `{"redis": "ok"}` when Redis is available (AC-F5-1)
- Must: `GET /health` returns `{"redis": "degraded"}` when Redis is unavailable (AC-F5-2)
- Must: Properties endpoint still works when Redis is degraded

**Files and modules**:

- `src/real-estate-api/app/routers/health.py` (new)
- `src/real-estate-api/app/main.py` (updated)

**Tests**:

- Unit test: health endpoint returns expected fields
- Unit test: mark Redis degraded and verify health response

**Completion signal**: `feat(STORY-23): add health endpoint with Redis status`

---

### Phase 7: Tests

**Goal**: Write comprehensive test suite covering all acceptance criteria,
using `fakeredis` for cache tests and `httpx.AsyncClient` for endpoint tests.

**Tasks**:

- [x] **7.1** Create `tests/conftest.py`:
  - `fake_redis` fixture: create `fakeredis.FakeAsyncRedis` instance
  - `app` fixture: FastAPI test app with fakeredis-backed RedisClient and CacheService overrides
  - `client` fixture: `httpx.AsyncClient` with `ASGITransport`
- [x] **7.2** Create `tests/test_cache_key.py`:
  - 11 tests covering deterministic key generation, normalization, SHA-256 output
- [x] **7.3** Create `tests/test_cache_service.py`:
  - Test get_or_compute miss on first call, hit on second (AC-F2-1, AC-F2-2)
  - Test TTL expiry triggers miss (AC-F2-3)
  - Test fallback on Redis exception (AC-F4-1)
  - Test degraded mode skips Redis
  - Test concurrent request dedup (AC-10)
- [x] **7.4** Create `tests/test_properties.py`:
  - Test 200 response with valid params (AC-1)
  - Test X-Cache headers (AC-2, AC-3, AC-F3-1)
  - Test fallback when Redis unreachable, still 200 (AC-5)
  - Test max_limit=100 enforcement (AC-7, AC-8)
  - Test 422 on invalid params (AC-8)
  - Test sort parameter (AC-9)
- [x] **7.5** Create `tests/test_health.py`:
  - Test health endpoint returns valid JSON with redis status
  - Test degraded mode reporting
- [x] **7.6** Run full test suite and ensure ≥ 90% coverage on `app/` code
  - 33/33 tests pass, ruff/mypy pass
  - Fixed sort_by validation — replaced `@field_validator` with `Field(pattern=...)`
    to ensure FastAPI properly returns 422 (was 500 due to sync validator in threadpool)

**Acceptance Criteria**:

- Must: All 10 ACs from the spec have corresponding tests
- Must: `fakeredis` is used (no real Redis in CI)
- Must: `pytest tests/ -v --cov=app --cov-fail-under=90` passes
- Must: Ruff and mypy pass on all test files

**Files and modules**:

- `src/real-estate-api/tests/conftest.py` (new)
- `src/real-estate-api/tests/test_cache_key.py` (new)
- `src/real-estate-api/tests/test_cache_service.py` (new)
- `src/real-estate-api/tests/test_properties.py` (new)
- `src/real-estate-api/tests/test_health.py` (new)

**Tests**:

- The test files themselves constitute the test suite

**Completion signal**: `test(STORY-23): add comprehensive test suite for cache layer`

---

### Phase 8: Docker Integration and Documentation

**Goal**: Create Dockerfile for `real-estate-api`, add service to docker-compose,
and document environment variables and usage.

**Tasks**:

- [ ] **8.1** Create `src/real-estate-api/Dockerfile`:
  - Multi-stage build: `python:3.12-slim` base
  - Install `uv`, copy `pyproject.toml` and `uv.lock`, run `uv sync --no-dev`
  - Copy source code
  - Expose port 8000
  - CMD: `uv run uvicorn real_estate_api.app.main:create_app --factory --host 0.0.0.0 --port 8000`
- [ ] **8.2** Add `real-estate-api` service to `docker-compose.yml`:
  - Build context: `./src/real-estate-api`
  - Port: `8000:8000`
  - Environment variables from `.env`:
    - `REDIS_URL=redis://redis:6379/0`
    - `DATABASE_URL=postgresql+asyncpg://postgres:postgres@postgres:5432/realestate`
  - Depends on: `postgres`, `redis` (with condition: `service_healthy`)
  - Networks: `realestate-net`
- [ ] **8.3** Create `src/real-estate-api/.env.example` with all configurable env vars
- [ ] **8.4** Update `src/real-estate-api/README.md` with:
  - Setup instructions (uv, virtualenv, docker-compose)
  - Available environment variables
  - How to run tests
  - API documentation link (auto-generated by FastAPI)
- [ ] **8.5** Perform end-to-end verification:
  - `docker compose up -d` starts all services including real-estate-api
  - `curl localhost:8000/health` returns ok
  - `curl "localhost:8000/api/v1/properties?city=Warszawa"` returns data
  - `curl -v` shows `X-Cache: miss` first call, `X-Cache: hit` second call

**Acceptance Criteria**:

- Must: Dockerfile builds without errors
- Must: `docker compose up` starts API service and it responds on port 8000
- Must: API connects to Redis and PostgreSQL containers
- Must: Cache-aside works end-to-end in Docker Compose
- Must: `.env.example` documents all configuration variables

**Files and modules**:

- `src/real-estate-api/Dockerfile` (new)
- `src/real-estate-api/README.md` (new)
- `src/real-estate-api/.env.example` (new)
- `docker-compose.yml` (updated — real-estate-api service)
- `src/real-estate-api/.dockerignore` (new)

**Tests**:

- Manual verification: `docker compose build real-estate-api` succeeds
- Manual verification: `docker compose up` and test requests via curl

**Completion signal**: `feat(STORY-23): add Dockerfile, docker-compose service, and documentation`

---

### Phase 9: Code Review and Spec Reconciliation

**Goal**: Review implementation against spec requirements, fix any issues, and
reconcile the plan and spec with the final implementation.

**Tasks**:

- [ ] **9.1** Perform self-review:
  - Check all 10 ACs are implemented and tested
  - Check all F-1 through F-5 capabilities are present
  - Check all NFRs (latency, error handling) are met
  - Check Prometheus metrics match spec table
- [ ] **9.2** Run full verification suite:
  - `ruff check .` — no warnings
  - `mypy . --strict` — no type errors
  - `pytest tests/ -v --cov=app --cov-fail-under=90`
  - Manual curl test of endpoint with cache header verification
- [ ] **9.3** Update plan and spec if implementation diverged:
  - Mark any deviations with rationale
  - Ensure spec decision log matches implementation choices
- [ ] **9.4** Verify version impact is `minor` and bump version in `pyproject.toml`
      to `0.1.0` (initial release for real-estate-api)

**Acceptance Criteria**:

- Must: All verification checks pass
- Must: Spec and plan are reconciled with implementation
- Must: Version is bumped

**Files and modules**:

- `src/real-estate-api/pyproject.toml` (updated — version)
- `doc/changes/2026-06/2026-06-21--STORY-23--redis-cache-properties-list/chg-STORY-23-spec.md` (updated — if needed)
- `doc/changes/2026-06/2026-06-21--STORY-23--redis-cache-properties-list/chg-STORY-23-plan.md` (this file, updated)

**Tests**:

- Full suite re-run

**Completion signal**: `chore(STORY-23): code review fixes and spec reconciliation`

---

## Test Scenarios

| ID | Scenario | Phases | AC |
|----|----------|--------|----|
| TS-1 | Deterministic cache key for identical params regardless of ordering | 3, 7 | AC-F1-1, AC-F1-2 |
| TS-2 | Cold cache → X-Cache: miss → data from DB | 5, 7 | AC-F2-1 |
| TS-3 | Warm cache → X-Cache: hit → cached JSON returned | 5, 7 | AC-F2-2 |
| TS-4 | Expired cache → X-Cache: miss after TTL | 3, 5, 7 | AC-F2-3 |
| TS-5 | X-Cache header present on all responses | 5, 7 | AC-F3-1 |
| TS-6 | Redis unreachable → X-Cache: miss (fallback) + 200 OK | 3, 5, 7 | AC-F4-1 |
| TS-7 | Redis unreachable → warning logged + counter incremented | 3, 7 | AC-F4-2 |
| TS-8 | Redis recovery → cache resumes working | 3, 6, 7 | AC-F4-3 |
| TS-9 | Health shows redis: ok when Redis available | 6, 7 | AC-F5-1 |
| TS-10 | Health shows redis: degraded when Redis unavailable | 6, 7 | AC-F5-2 |
| TS-11 | Response latency < 10ms p95 on cache hit | 5 | AC-NFR-1 |
| TS-12 | Response latency < 200ms p95 on fallback | 5 | AC-NFR-2 |
| TS-13 | max_limit=100 enforced → 422 on limit=101 | 4, 5, 7 | AC-7, AC-8 |
| TS-14 | Invalid params produce 422 | 4, 5, 7 | AC-8 |
| TS-15 | Sort parameter field:direction works | 5, 7 | AC-9 |
| TS-16 | Concurrent identical requests → one DB query | 3, 5, 7 | AC-10 |

## Artifacts and Links

| Artifact | Location | Type |
|----------|----------|------|
| Change specification | `./chg-STORY-23-spec.md` | Spec |
| Implementation plan | `./chg-STORY-23-plan.md` | Plan (this file) |
| Epic definition | `doc/planning/epics/epic-05--redis-cache/epic-05--redis-cache.md` | Epic |
| API spec | `specs/specs/080-API.md` | Spec module |
| Caching/storage spec | `specs/specs/120-CACHING-STORAGE.md` | Spec module |
| Frontend data models | `specs/specs/090-FRONTEND.md` | Spec module |
| System architecture | `specs/specs/020-ARCHITECTURE.md` | Spec module |
| FastAPI application | `src/real-estate-api/` | Code |
| Cache service | `src/real-estate-api/app/services/cache_service.py` | Code |
| Redis client | `src/real-estate-api/app/services/redis_client.py` | Code |
| Properties router | `src/real-estate-api/app/routers/properties.py` | Code |
| Pydantic schemas | `src/real-estate-api/app/schemas/` | Code |
| Health endpoint | `src/real-estate-api/app/routers/health.py` | Code |
| Configuration | `src/real-estate-api/app/core/config.py` | Code |
| Dockerfile | `src/real-estate-api/Dockerfile` | Build |
| Docker Compose | `docker-compose.yml` (updated) | Deploy |

## Plan Revision Log

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-06-21 | plan-writer | Initial plan for STORY-23 |

## Execution Log

| Phase | Status | Started | Completed | Commit | Notes |
|-------|--------|---------|-----------|--------|-------|
| Phase 1: Scaffold | ✅ Complete | 2026-06-21 | 2026-06-21 | (next commit) | ruff/mypy pass, create_app() works | |
| Phase 2: Core Config | ✅ Complete | 2026-06-21 | 2026-06-21 | (next commit) | Settings with all env vars, Prometheus Counter/Histogram/Gauge metrics |
| Phase 3: Cache Service | ✅ Complete | 2026-06-21 | 2026-06-21 | (next commit) | RedisClient with pool, CacheService with get_or_compute, lock-based dedup |
| Phase 4: Schemas | ✅ Complete | 2026-06-21 | 2026-06-21 | (next commit) | PropertyCard, SearchParams (validated), PaginatedResponse[PropertyCard] |
| Phase 5: Properties Router | ✅ Complete | 2026-06-21 | 2026-06-21 | (next commit) | Cache-aside route with DB query, pagination, X-Cache header |
| Phase 6: Health Endpoint | ✅ Complete | 2026-06-21 | 2026-06-21 | (next commit) | /health returns redis status, periodic health check task |
| Phase 7: Tests | ✅ Complete | 2026-06-21 | 2026-06-21 | (next commit) | 33/33 tests pass, ruff/mypy pass; fixed sort_by validation (Field pattern instead of field_validator) |
| Phase 8: Docker + Docs | ⬜ Pending | | | | |
| Phase 9: Review & Release | ⬜ Pending | | | | |
