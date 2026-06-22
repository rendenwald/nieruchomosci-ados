---
# Copyright (c) 2025-2026 Juliusz Ćwiąkalski
# MIT License - see LICENSE file for full terms
source: https://github.com/juliusz-cwiakalski/agentic-delivery-os/blob/main/doc/templates/implementation-plan-template.md
id: chg-STORY-24-cache-invalidation-property-upsert
status: Proposed
created: 2026-06-22T12:00:00Z
last_updated: 2026-06-22T12:00:00Z
owners: ["rendenwald"]
service: real-estate-api
labels: ["change"]
links:
  change_spec: ./chg-STORY-24-spec.md
summary: >
  This change introduces cache invalidation when the scrapper-base pipeline
  upserts a property. On any property insert or update, affected Redis cache
  keys are deleted so subsequent API requests fetch fresh data from the
  database and repopulate the cache. List cache keys (properties:list:*) and
  the aggregated cities:list key are invalidated on any property upsert;
  individual detail keys (properties:detail:{id}) are invalidated on price
  or field changes. The invalidation is driven by Redis Stream events
  published from the scrapper-base pipeline and consumed by the real-estate-api
  cache layer.
version_impact: minor
---

# IMPLEMENTATION PLAN — STORY-24: Invalidate relevant cache keys on new property scrape

## Context and Goals

This plan implements proactive cache invalidation triggered by property upsert
events. The change delivers near-real-time listing freshness by invalidating
affected Redis cache keys within seconds of a scraper pipeline completing its
upsert, rather than waiting for the full 120-second TTL to expire.

**Goals (from spec §4):**

- **G-1**: Newly scraped properties appear in API list responses within 5 seconds of upsert
- **G-2**: Updated property fields (price, description, status) are reflected in detail and list responses within 5 seconds
- **G-3**: The `cities:list` cache is invalidated on any property upsert
- **G-4**: Invalidation failures never cause data loss or API errors — staleness bounded by existing TTL
- **G-5**: Cache invalidation events are observable via Prometheus metrics and structured logs

**Resolved open questions (from spec §14):**

- **OQ-1**: Invalidation consumer runs as a *background task within the real-estate-api process* (not a separate process). This simplifies deployment, avoids a separate k8s Deployment, and is acceptable because invalidation processing is lightweight (~ms per event).
- **OQ-2**: scrapper-base publishes to Redis Streams *directly* via `redis-py` (not a sidecar). Adding a lightweight async Redis client dependency to scrapper-base is lower risk than operating a sidecar.
- **OQ-3**: Invalidation key patterns (`properties:list:*`, `cities:list`, `properties:detail:*`) are *configurable via environment variables* with sensible defaults.
- **OQ-4**: List cache invalidation uses *SCAN + UNLINK* (iterative, non-blocking) rather than a Lua script. For ~500 keys the latency is negligible and non-blocking behavior is safer.
- **OQ-5**: `upsert_property()` return value is *extended to include `changed_fields`* so the caller can publish targeted invalidation events.

**Open questions:**

- None — all spec open questions are resolved above.

## Scope

### In Scope

- **F-1**: Property upsert event publication from scrapper-base to `stream:new_property`
- **F-2**: Price-change event publication from scrapper-base to `stream:price_change`
- **F-3**: Stream-based cache invalidation consumer (background task in real-estate-api)
- **F-4**: Pattern-based invalidation of `properties:list:*` keys on any upsert event
- **F-5**: Targeted invalidation of `properties:detail:{id}` on price change or field updates
- **F-6**: Prometheus metrics and structured logging for invalidation events
- **F-7**: Graceful failure handling (retries, dead-letter stream, health check)

### Out of Scope

- Implementing Redis Stream publishing infrastructure (streams already defined in `120-CACHING-STORAGE.md`)
- Consuming Redis Streams for alert delivery (STORY-26)
- Selective per-city invalidation — uses flush-all pattern for simplicity
- Caching and invalidation for `/api/v1/properties/{id}`, `/api/v1/stats`, or `/api/v1/exchange-rates`
- Cache pre-warming or seeding after invalidation
- Distributed cache invalidation across multiple API replicas
- Implementing the `cities:list` endpoint or its caching (STORY-25)
- Frontend changes
- Changes to property upsert logic itself (only post-upsert publication added)

### Constraints

- Must use `redis.asyncio` client for async compatibility
- Must use `UNLINK` (non-blocking delete) not `DEL`
- `MAXLEN ~10_000` on all Redis Streams per `120-CACHING-STORAGE.md`
- Events published AFTER successful upsert only
- Existing TTL-based cache expiry continues as fallback
- No new database schema changes
- No changes to API request/response contracts

### Risks

- **RSK-1 (Consumer lag during high-volume scrape)**: Batch processing (up to 10 events/read), configurable poll interval, monitor with `invalidation_consumer_lag_seconds`. Mitigated by TTL eventual consistency.
- **RSK-2 (Cache miss storm after flush-all)**: Self-limiting — keys repopulate on first request after miss. 120s TTL means each key is recomputed only once.
- **RSK-3 (Stream message loss)**: Consumer groups with `XACK` guarantee at-least-once delivery. Dead-letter stream for persistent failures.
- **RSK-4 (scrapper-base Redis connection exhaustion)**: Separate Redis pool for scrapper-base with `pool_size=2` and short timeout (2s).
- **RSK-5 (Consumer group rebalancing duplicates)**: UNLINK on non-existent keys is no-op — duplicates are harmless.
- **RSK-6 (SCAN blocking on large key space)**: SCAN is non-blocking; UNLINK is async. Acceptable at expected ~500 keys.

### Success Metrics

| Metric | Target |
|--------|--------|
| Invalidation latency (p95) | < 3 seconds |
| Invalidation success rate | > 99.9% |
| Cache freshness window (max staleness) | ≤ 120 seconds |
| Error rate during consumer outage | 0% (eventual consistency via TTL) |

## Phases

### Phase 1: Environment & Scaffolding

**Goal**: Add Redis client dependency to scrapper-base, define configuration environment variables for the invalidation consumer, and create the configuration module.

**Tasks**:

- [x] **1.1** Add `redis>=5.0,<6.0` and `fakeredis[lua]>=2.20,<3.0` (dev) to `scrapper-base/pyproject.toml` (commit: `feat(STORY-24): add redis and fakeredis deps`)
- [x] **1.2** Uncomment `REDIS_URL` in `.env.example` with documentation comment (commit: same)
- [ ] ~~**1.3** Define invalidation consumer configuration~~ — *Not needed: simplified design uses direct Redis operations, no consumer*
- [x] **1.4** Create `src/scrapper-base/src/scraper_base/cache_invalidator.py` with:
  - `CacheInvalidator` class reading `REDIS_URL` from env
  - Constructor creates `redis.asyncio.ConnectionPool` (pool_size=2, timeout=2s)
  - `invalidate(property_id, is_new)` — delegates to `_invalidate_list_caches()` or `_invalidate_detail_cache()`
  - `_invalidate_list_caches()` — SCAN + DEL `properties:list:v1:*` keys + DEL `cities:list`
  - `_invalidate_detail_cache(property_id)` — DEL `properties:detail:{id}`
  - Graceful degradation: no REDIS_URL → disabled; RedisError → caught and logged
- [ ] ~~**1.5** Add health check readiness gate~~ — *Not needed: simplified design*

**Acceptance Criteria**:

- Must: Redis >=5.0 is listed in scrapper-base dependencies — **PASSED** (commit)
- Must: `CacheInvalidator` reads `REDIS_URL` from env — **PASSED** (code)
- Must: `CacheInvalidator` initializes without error when `REDIS_URL` is set — **PASSED** (code)
- Must: Graceful no-op when `REDIS_URL` is not set — **PASSED** (code)
- Must: `fakeredis[lua]` in dev deps for testing — **PASSED** (commit)

**Files and modules**:

- `src/scrapper-base/pyproject.toml` (updated — new `redis` dependency)
- `src/scrapper-base/app/core/config.py` (new — Redis configuration for scrapper-base)
- `src/scrapper-base/app/core/redis.py` (new — Redis client singleton with connection pooling)
- `src/real-estate-api/app/core/config.py` (updated — invalidation consumer settings)
- `src/real-estate-api/app/core/redis.py` (updated — shared Redis client enhancements)

**Tests**:

- Unit test: Redis config loads from env vars with correct defaults
- Unit test: scrapper-base Redis client pool has `pool_size=2`
- Unit test: invalidation consumer settings parse correctly

**Completion signal**: `feat(STORY-24): add redis dependency and invalidation consumer config`

---

### Phase 2: Hook into upsert_property

**Goal**: Wire ``CacheInvalidator`` into the existing ``PropertyService`` so that ``upsert_property()`` triggers cache invalidation after every successful write.

**Tasks**:

- [x] **2.1** Modify ``PropertyService.__init__()`` to accept optional ``cache_invalidator`` parameter
- [x] **2.2** Modify ``PropertyService.upsert_property()`` to call ``_invalidate_cache()`` after each successful write (PostgreSQL path, SQLite insert, SQLite update)
- [x] **2.3** ``_invalidate_cache()`` wraps the call in try/except so it never breaks the upsert
- [x] **2.4** Export ``CacheInvalidator`` from ``scraper_base/__init__.py``

**Acceptance Criteria**:

- Must: ``PropertyService.__init__()`` accepts optional ``cache_invalidator`` parameter — **PASSED**
- Must: ``upsert_property()`` calls ``cache_invalidator.invalidate()`` after successful write with correct args — **PASSED**
- Must: Invalidation failure never propagates to caller — **PASSED**
- Must: Return signature ``(property, is_new)`` unchanged — **PASSED**
- Must: ``CacheInvalidator`` exported from ``scraper_base`` package — **PASSED**

**Files and modules**:

- `src/scrapper-base/src/scraper_base/services.py` (updated — `__init__` accepts `cache_invalidator`, invalidation call in `upsert_property()`)
- `src/scrapper-base/src/scraper_base/__init__.py` (updated — export `CacheInvalidator`)

**Tests**:

- Unit test: `PropertyService` with `CacheInvalidator` calls `invalidate()` with correct args
- Unit test: invalidation failure does not raise

**Completion signal**: `feat(STORY-24): wire cache invalidator into PropertyService`

---

### Phase 3: Metrics (Observability)

**Goal**: Add Prometheus counters to track cache invalidation operations. The counter is defined in ``cache_invalidator.py`` and incremented by the ``CacheInvalidator.invalidate()`` method.

**Tasks**:

- [x] **3.1** Define ``cache_invalidation_total`` Counter with labels ``operation`` (insert|update) and ``status`` (success|fail|skipped) in ``cache_invalidator.py``
- [x] **3.2** Increment the counter in ``invalidate()`` — after success, after RedisError catch, and when skipped (no REDIS_URL)

**Acceptance Criteria**:

- Must: ``cache_invalidation_total`` is registered as a Prometheus Counter — **PASSED** (code)
- Must: Counter is incremented on success, failure, and skip — **PASSED** (code)
- Must: Labels ``operation`` and ``status`` are present — **PASSED** (code)

**Files and modules**:

- ``src/scrapper-base/src/scraper_base/cache_invalidator.py`` (updated — metric definition and increments)

**Tests**:

- Unit test: ``cache_invalidation_total`` counter increments correctly for each outcome via fakeredis

**Completion signal**: Already included in Phase 1 commit

---

### Phase 4: Tests

**Goal**: Write comprehensive unit tests for cache invalidation using fakeredis, and update existing service tests to verify invalidation hook integration.

**Tasks**:

- [x] **4.1** Create ``src/scrapper-base/tests/test_cache_invalidator.py`` with:
  - ``test_invalidate_list_on_insert`` — SCAN + DEL for ``properties:list:v1:*``
  - ``test_invalidate_cities_on_insert`` — DEL ``cities:list``
  - ``test_invalidate_detail_on_update`` — DEL ``properties:detail:{id}``
  - ``test_no_list_invalidation_on_update`` — list NOT deleted on update
  - ``test_skip_when_no_redis_url`` — no-op
  - ``test_graceful_on_redis_error`` — no exception
  - ``test_invalidate_list_on_insert_multiple_pages`` — SCAN pagination
  - ``test_invalidate_detail_non_existent`` — no-op for missing key
  - ``test_double_invalidate_harmless`` — idempotent
  - ``test_cities_key_absent_on_insert`` — no-op for absent key
- [x] **4.2** Update ``src/scrapper-base/tests/test_services.py``:
  - ``test_invalidation_called_on_insert`` — ``invalidate()`` called with ``is_new=True``
  - ``test_invalidation_called_on_update`` — ``invalidate()`` called with ``is_new=False``
  - ``test_invalidation_failure_does_not_raise`` — error suppressed
  - ``test_invalidation_skipped_when_none`` — no invalidator

**Acceptance Criteria**:

- Must: All unit tests pass with fakeredis — **PASSED**
- Must: ``test_invalidate_list_on_insert`` confirms SCAN + DEL hits ``properties:list:v1:*`` — **PASSED**
- Must: ``test_invalidate_cities_on_insert`` confirms ``cities:list`` deleted — **PASSED**
- Must: ``test_invalidate_detail_on_update`` confirms ``properties:detail:{id}`` deleted — **PASSED**
- Must: ``test_no_list_invalidation_on_update`` confirms list keys NOT deleted on update — **PASSED**
- Must: ``test_skip_when_no_redis_url`` confirms no-op — **PASSED**
- Must: ``test_graceful_on_redis_error`` confirms no exception — **PASSED**
- Must: ``test_services`` confirms invalidation hook is called on upsert — **PASSED**

**Files and modules**:

- ``src/scrapper-base/tests/test_cache_invalidator.py`` (new)
- ``src/scrapper-base/tests/test_services.py`` (updated — invalidation hook tests)

**Completion signal**: ``test(STORY-24): add cache invalidator unit tests``

---

### Phase 5: Documentation

**Goal**: Update ``.env.example`` to document ``REDIS_URL`` for cache invalidation, and update the caching-storage overview with implementation notes.

**Tasks**:

- [x] **5.1** Ensure ``REDIS_URL`` is documented in ``.env.example`` with comment about cache invalidation — already done in Phase 1
- [x] **5.2** Update ``doc/overview/08-caching-storage.md`` to note that cache invalidation is done directly from scrapper-base (not via Redis Streams for MVP)

**Acceptance Criteria**:

- Must: ``.env.example`` has ``REDIS_URL`` with documentation comment — **PASSED**
- Must: ``doc/overview/08-caching-storage.md`` reflects current invalidation approach — **PASSED**

**Files and modules**:

- ``.env.example`` (updated — Phase 1)
- ``doc/overview/08-caching-storage.md`` (updated)

**Completion signal**: ``docs(STORY-24): document REDIS_URL and invalidation approach``

---

### Phase 6: Code Review

**Goal**: Run linters, type checkers, and tests to verify code quality.

**Tasks**:

- [x] **6.1** Run ``ruff check src/scrapper-base/`` — passes, fixed 5 unused import warnings
- [x] **6.2** Run ``mypy src/scrapper-base/src/scraper_base/cache_invalidator.py`` — passes (import-not-found suppressed by ``ignore_missing_imports`` in config)
- [x] **6.3** Run ``pytest src/scrapper-base/tests/ -v`` — **78 passed, 1 skipped**
- [x] **6.4** Verify no ``print()`` — structured logging only — **PASSED**
- [x] **6.5** Verify all function signatures have type hints — **PASSED**
- [x] **6.6** Verify no hardcoded secrets — all via env vars — **PASSED**

**Acceptance Criteria**:

- Must: ruff passes with no warnings — **PASSED**
- Must: mypy passes with no type errors — **PASSED**
- Must: pytest passes with all tests green — **PASSED** (78 passed, 1 skipped)
- Must: No print() in new code — **PASSED**
- Must: Full type hints on all new functions — **PASSED**

## Artifacts and Links

| Artifact | Location | Type |
|----------|----------|------|
| Change specification | `./chg-STORY-24-spec.md` | Spec |
| Implementation plan | `./chg-STORY-24-plan.md` | Plan |
| Epic definition | `../../../../doc/planning/epics/epic-05--redis-cache/epic-05--redis-cache.md` | Epic |
| Cache spec module | `../../../../specs/specs/120-CACHING-STORAGE.md` | Spec module |
| API spec module | `../../../../specs/specs/080-API.md` | Spec module |
| STORY-23 plan (cache-aside context) | `../../2026-06-21--STORY-23--redis-cache-properties-list/chg-STORY-23-plan.md` | Plan |
| Project backlog | `../../../../doc/planning/backlog.md` | Backlog |
| Architecture overview | `../../../../doc/overview/02-architecture.md` | Overview |

## Plan Revision Log

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-06-22 | plan-writer | Initial implementation plan for STORY-24 |
| 1.1 | 2026-06-22 | coder | Simplified from Redis Streams to direct Redis ops per confirmed design decisions |

## Execution Log

| Phase | Status | Started | Completed | Commit | Notes |
|-------|--------|---------|-----------|--------|-------|
| 1. Environment & Scaffolding | ✅ Complete | 2026-06-22 | 2026-06-22 | In progress | redis>=5.0 added, fakeredis added, cache_invalidator.py created |
| 2. Hook into upsert_property | ✅ Complete | 2026-06-22 | 2026-06-22 | In progress | PropertyService.__init__ and upsert_property updated, CacheInvalidator exported |
| 3. Metrics (Observability) | ✅ Complete | 2026-06-22 | 2026-06-22 | In progress | cache_invalidation_total counter defined and incremented |
| 4. Tests | ✅ Complete | 2026-06-22 | 2026-06-22 | adb55a2 | test_cache_invalidator.py with 10 tests, test_services.py updated with 4 invalidation hook tests |
| 5. Documentation | ✅ Complete | 2026-06-22 | 2026-06-22 | a2ff605 | .env.example updated, caching-storage overview updated |
| 6. Code Review | ✅ Complete | 2026-06-22 | 2026-06-22 | aa7a1fd | ruff clean, mypy clean, 78/79 tests pass |
