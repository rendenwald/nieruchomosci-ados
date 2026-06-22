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

- [ ] **1.1** Add `redis>=5.0` dependency to `scrapper-base/pyproject.toml` (async-compatible `redis.asyncio`)
- [ ] **1.2** Create Redis configuration for scrapper-base: `REDIS_URL` env var (reuses existing Redis deployment URL)
- [ ] **1.3** Define invalidation consumer configuration settings in `real-estate-api/app/core/config.py`:
  - `INVALIDATION_CONSUMER_ENABLED` (default: `true`)
  - `INVALIDATION_POLL_INTERVAL` (default: `1.0` seconds)
  - `INVALIDATION_BATCH_SIZE` (default: `10`)
  - `INVALIDATION_POLL_TIMEOUT` (default: `5.0` seconds)
  - `INVALIDATION_MAX_RETRIES` (default: `3`)
  - `INVALIDATION_KEY_PATTERN_LIST` (default: `"properties:list:*"`)
  - `INVALIDATION_KEY_CITIES` (default: `"cities:list"`)
  - `INVALIDATION_KEY_DETAIL_TEMPLATE` (default: `"properties:detail:{id}"`)
  - `INVALIDATION_DEAD_LETTER_MAXLEN` (default: `1000`)
- [ ] **1.4** Create a dedicated Redis client module for scrapper-base (`scrapper-base/app/core/redis.py`) with connection pool (`pool_size=2`, timeout=2s)
- [ ] **1.5** Add `INVALIDATION_CONSUMER_ENABLED` to the health check readiness gate — if disabled, health reports `invalidation_consumer: "stopped"`

**Acceptance Criteria**:

- Must: Redis >=5.0 is listed in scrapper-base dependencies
- Must: Configuration settings are loadable from environment variables with documented defaults
- Must: scrapper-base Redis client initializes without error when `REDIS_URL` is set

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

### Phase 2: Core — Stream Publishing from scrapper-base

**Goal**: Implement post-upsert event publishing from scrapper-base to Redis Streams `stream:new_property` and `stream:price_change`, with price-change detection.

**Tasks**:

- [ ] **2.1** Extend `PropertyService.upsert_property()` return value to include `changed_fields: list[str]` — i.e., return `(property, is_new, changed_fields)` — a non-breaking change as callers that destructure `(prop, _)` continue to work
- [ ] **2.2** Implement price-change detection logic in `upsert_property()`: compare incoming `price` field with existing record's price before upsert; if different, include `"price"` in `changed_fields`
- [ ] **2.3** Create a stream publisher module `scrapper-base/app/core/stream_publisher.py`:
  - `async def publish_new_property(property_id, portal_source, source_id, city, property_type, is_new, changed_fields)` — publishes JSON payload to `stream:new_property`
  - `async def publish_price_change(property_id, portal_source, source_id, city, old_price, new_price, currency)` — publishes JSON payload to `stream:price_change`
  - Uses `XADD stream:new_property MAXLEN ~10000 * field1 val1 field2 val2 ...` (Redis Stream field-value format with JSON-encoded value)
  - Both functions use the scrapper-base Redis client (from Phase 1)
- [ ] **2.4** Add post-upsert hook in `BasePipeline.process_item()` (or the upsert caller):
  - After `upsert_property()` returns, call `publish_new_property()` with the upsert result
  - If price changed (detected via `changed_fields`), additionally call `publish_price_change()`
  - Wrap in try/except — publication failures are logged but never block the pipeline
- [ ] **2.5** Ensure all scrapper pipelines (OtodomPipeline, GratkaPipeline, NieruchomosciOnlinePipeline) inherit the post-upsert hook from `BasePipeline` (no per-pipeline changes needed)

**Acceptance Criteria**:

- Must: AC-F1-1 — new property upsert publishes to `stream:new_property` with `is_new: true`
- Must: AC-F1-2 — existing property upsert publishes to `stream:new_property` with `is_new: false` and `changed_fields`
- Must: AC-F2-1 — price-changing upsert publishes to `stream:price_change` with old/new prices
- Must: Stream messages use `MAXLEN ~10_000`
- Must: Stream publication failure does not raise or fail the pipeline item
- Should: `upsert_property()` callers that destructure `(property, _)` continue to work unchanged

**Files and modules**:

- `src/scrapper-base/app/services/property_service.py` (updated — return `changed_fields`, price detection)
- `src/scrapper-base/app/core/stream_publisher.py` (new — stream publishing functions)
- `src/scrapper-base/pipelines/base.py` (updated — post-upsert hook in `BasePipeline`)
- `src/scrapper-base/pipelines/otodom.py` (no change expected — inherits from BasePipeline)
- `src/scrapper-base/pipelines/gratka.py` (no change expected — inherits from BasePipeline)
- `src/scrapper-base/pipelines/nieruchomosci_online.py` (no change expected — inherits from BasePipeline)

**Tests**:

- Unit test: `upsert_property()` returns `changed_fields` with correct field names
- Unit test: price-change detection identifies price changes correctly
- Unit test: `publish_new_property()` produces correct JSON payload (use fakeredis)
- Unit test: `publish_price_change()` produces correct JSON payload
- Unit test: BasePipeline post-upsert hook calls publisher and does not raise on failure
- Integration test: end-to-end with real Redis — verify stream entries appear after upsert

**Completion signal**: `feat(STORY-24): implement redis stream publishing from scrapper-base`

---

### Phase 3: Core — Invalidation Consumer in real-estate-api

**Goal**: Implement the background invalidation consumer that reads events from Redis Streams and deletes affected cache keys using SCAN + UNLINK.

**Tasks**:

- [ ] **3.1** Create invalidation consumer module `real-estate-api/app/services/cache_invalidator.py`:
  - `class CacheInvalidator` with lifecycle methods: `start()`, `stop()`, `is_running`
  - On `start()`:
    - Create consumer group `cg:cache-invalidation` on `stream:new_property` and `stream:price_change` (handle `BUSYGROUP` error gracefully)
    - Set consumer status to `"running"`
  - Poll loop (configurable interval, default 1s):
    - `XREADGROUP BLOCK 5000 COUNT 10 STREAMS stream:new_property stream:price_change >`
    - For each event:
      1. Parse JSON payload
      2. Determine event type from stream name
      3. Process per invalidation matrix (spec Appendix C)
      4. Increment Prometheus counters
      5. `XACK` the event
      6. On error: retry up to 3 times, then `XADD` to `stream:dead_letter` + `XACK`
  - On `stop()`: cancel poll loop, wait for in-flight processing (max 10s)
- [ ] **3.2** Implement list cache invalidation (F-4):
  - `async def _invalidate_list_caches()`:
    - `SCAN 0 MATCH properties:list:* COUNT 100` in a loop
    - `UNLINK` each matched key
    - `UNLINK cities:list`
    - Return count of deleted keys
- [ ] **3.3** Implement detail cache invalidation (F-5):
  - `async def _invalidate_detail_cache(property_id)`:
    - `UNLINK properties:detail:{property_id}`
  - Triggered by:
    - `price_change` event — always invalidate detail key
    - `new_property` event with `is_new=false` and non-empty `changed_fields` — invalidate detail key
    - `new_property` event with `is_new=true` — skip (no detail cache exists yet)
- [ ] **3.4** Wire the consumer into the FastAPI application lifespan:
  - In `real-estate-api/app/main.py` (or `app/core/lifespan.py`), start the `CacheInvalidator` on startup, stop on shutdown
  - Respect `INVALIDATION_CONSUMER_ENABLED` config flag
- [ ] **3.5** Implement retry and dead-letter logic (F-7):
  - Track retry count per message ID in-memory
  - On failure: increment retry, do NOT `XACK` — message remains pending
  - On max retries exceeded: `XADD stream:dead_letter MAXLEN ~1000 * payload <json> error <str>`, then `XACK` the original event
  - Log warning on each retry; log error on dead-letter move
- [ ] **3.6** Implement consumer startup resilience:
  - Retry Redis connection with exponential backoff (1s, 2s, 4s, ... max 60s)
  - Log warning during backoff; consumer status is `"degraded"` until connected
  - If Redis never connects, consumer status is `"stopped"` and app continues serving (existing TTL fallback)

**Acceptance Criteria**:

- Must: AC-F3-1 — new_property event triggers `properties:list:*` deletion and `XACK`
- Must: AC-F3-2 — consumer group `cg:cache-invalidation` exists on both streams after startup
- Must: AC-F3-3 — failed event moves to `stream:dead_letter` after 3 retries
- Must: AC-F4-1 — new_property event flushes ALL keys matching `properties:list:*`
- Must: AC-F4-2 — `cities:list` key is deleted on new_property event
- Must: AC-F5-1 — price_change event deletes `properties:detail:{property_id}`
- Must: AC-F5-2 — new_property with `is_new=false` and changed_fields deletes detail key
- Must: AC-F7-1 — Redis unavailability does not crash the application
- Must: AC-F7-2 — API requests succeed and cache is served from TTL entries when consumer is stopped

**Files and modules**:

- `src/real-estate-api/app/services/cache_invalidator.py` (new — CacheInvalidator class)
- `src/real-estate-api/app/main.py` or `src/real-estate-api/app/core/lifespan.py` (updated — consumer lifecycle)
- `src/real-estate-api/app/core/redis.py` (updated — shared Redis client for consumer)

**Tests**:

- Unit test: `_invalidate_list_caches()` scans and unlinks all matching keys (use fakeredis)
- Unit test: `_invalidate_detail_cache()` unlinks the correct key
- Unit test: event parsing handles all payload variants
- Unit test: retry logic increments counter and moves to dead-letter at max retries
- Unit test: consumer starts/stops cleanly
- Unit test: consumer does not block app shutdown (timeout after 10s)
- Integration test: end-to-end with real Redis — publish event, verify keys deleted

**Completion signal**: `feat(STORY-24): implement cache invalidation consumer`

---

### Phase 4: Observability & Health

**Goal**: Add Prometheus metrics, structured logging, and health check extensions for the invalidation consumer.

**Tasks**:

- [ ] **4.1** Register Prometheus counters and histograms in `real-estate-api/app/core/metrics.py`:
  - `invalidation_events_total` (Counter, labels: `stream`, `result`)
  - `invalidation_keys_deleted_total` (Counter, labels: `key_pattern`)
  - `invalidation_errors_total` (Counter, labels: `stream`, `error_type`)
  - `invalidation_consumer_lag_seconds` (Gauge, labels: `stream`)
  - `invalidation_duration_seconds` (Histogram, labels: `operation`)
- [ ] **4.2** Instrument the consumer (Phase 3) with metrics:
  - Increment `invalidation_events_total` on each event processed (result=success/skipped/error)
  - Increment `invalidation_keys_deleted_total` per key pattern after deletion
  - Increment `invalidation_errors_total` on errors with error_type label
  - Update `invalidation_consumer_lag_seconds` each poll cycle (compare stream last-entry timestamp vs last-processed entry timestamp)
  - Observe `invalidation_duration_seconds` for SCAN, UNLINK, XREAD, XACK operations
- [ ] **4.3** Add structured logging to the consumer:
  - Info: each invalidation event — event type, property id, city, keys deleted count, duration
  - Warning: retry attempts, consumer restarts, stream reconnection
  - Error: dead-letter events (full payload), unrecoverable errors
  - Debug: per-event details, individual key deletions
- [ ] **4.4** Extend `GET /health` endpoint:
  - Add `invalidation_consumer` field: `"running" | "degraded" | "stopped"`
  - Add nested `invalidation` object with per-stream details (pending count, lag seconds, last processed timestamp) and `dead_letter_count`, `error_rate_last_5m`
  - Consumer status derivation:
    - `running`: consumer actively processing, pending < 1000, no recent errors
    - `degraded`: connected but pending > 1000 or errors in last 5 minutes
    - `stopped`: not started or crashed
- [ ] **4.5** Instrument the stream publisher (Phase 2) with basic error logging

**Acceptance Criteria**:

- Must: AC-F6-1 — successful invalidation increments `invalidation_events_total` with `result=success`
- Must: AC-F6-2 — failed invalidation increments `invalidation_errors_total`
- Must: AC-F6-3 — keys deleted increments `invalidation_keys_deleted_total`
- Must: AC-NFR-2 — `GET /health` includes invalidation consumer status
- Must: All new metrics appear in the `/metrics` Prometheus endpoint

**Files and modules**:

- `src/real-estate-api/app/core/metrics.py` (updated — new Prometheus metrics)
- `src/real-estate-api/app/routers/health.py` (updated — invalidation consumer status)
- `src/real-estate-api/app/services/cache_invalidator.py` (updated — instrumentation)
- `src/scrapper-base/app/core/stream_publisher.py` (updated — error logging)

**Tests**:

- Unit test: metrics are registered and increment correctly
- Unit test: health endpoint returns expected invalidation consumer structure
- Unit test: consumer status transitions correctly (running → degraded → stopped)
- Integration test: verify metrics appear in `/metrics` output after invalidation

**Completion signal**: `feat(STORY-24): add invalidation observability and health checks`

---

### Phase 5: Tests

**Goal**: Write comprehensive unit tests for stream publishing and invalidation consumer using fakeredis, and integration tests with a real Redis instance.

**Tasks**:

- [ ] **5.1** Write unit tests for scrapper-base stream publishing (Phase 2):
  - `test_publish_new_property()` — verify stream entry format, field values, JSON payload
  - `test_publish_price_change()` — verify price change stream entry
  - `test_publish_failure_does_not_block()` — publication exception is caught, item processing continues
  - `test_upsert_returns_changed_fields()` — verify `changed_fields` list accuracy
  - `test_price_change_detection()` — price change detected correctly
  - Use `fakeredis` for Redis mocking
- [ ] **5.2** Write unit tests for invalidation consumer (Phase 3, 4):
  - `test_invalidate_list_caches()` — verify SCAN + UNLINK for `properties:list:*`
  - `test_invalidate_detail_cache()` — verify UNLINK for `properties:detail:{id}`
  - `test_process_new_property_event()` — full flow: read event, invalidate, XACK
  - `test_process_price_change_event()` — full flow: read event, invalidate detail, XACK
  - `test_retry_logic()` — event fails, retries up to N times, dead-letter after max
  - `test_dead_letter_format()` — dead-letter entry contains original payload + error info
  - `test_consumer_group_creation()` — group created on startup, BUSYGROUP handled
  - `test_consumer_start_stop()` — lifecycle management
  - Use `fakeredis` with stream support
- [ ] **5.3** Write unit tests for metrics and health (Phase 4):
  - `test_metrics_increment()` — verify counter values after processing events
  - `test_health_endpoint_structure()` — verify health response schema
  - `test_consumer_status_running()` — verify status derivation
- [ ] **5.4** Write integration tests (require running Redis):
  - `test_publish_and_consume_flow()` — start real Redis, publish event via scrapper-base publisher, consume via invalidation consumer, verify keys deleted
  - `test_batch_processing()` — publish 10+ events, verify consumer processes all
  - `test_consumer_recovery()` — stop Redis, start consumer (should degrade), restart Redis (should resume)
  - `test_duplicate_processing_harmless()` — process same event twice, verify no errors
- [ ] **5.5** Write test for the health endpoint contract:
  - `test_health_response_schema()` — validate JSON response matches the schema in spec Appendix D

**Acceptance Criteria**:

- Must: All unit tests pass with fakeredis
- Must: All integration tests pass with real Redis (CI with Redis service container)
- Must: Test coverage for new code meets project threshold (>80%)
- Should: Integration tests are marked with pytest marker `integration` for CI filtering

**Files and modules**:

- `tests/scrapper-base/test_stream_publisher.py` (new)
- `tests/scrapper-base/test_property_service.py` (updated — changed_fields tests)
- `tests/real-estate-api/test_cache_invalidator.py` (new)
- `tests/real-estate-api/test_health.py` (updated — invalidation consumer health)
- `tests/real-estate-api/test_metrics.py` (updated — invalidation metrics)
- `tests/integration/test_cache_invalidation_flow.py` (new)
- `tests/conftest.py` (updated — Redis fixtures for integration tests)

**Tests**:

- All tests defined above

**Completion signal**: `test(STORY-24): add unit and integration tests for cache invalidation`

---

### Phase 6: Documentation & Spec Synchronization

**Goal**: Update relevant documentation to reflect the new invalidation mechanism, document environment variables, and update the spec status.

**Tasks**:

- [ ] **6.1** Update `specs/120-CACHING-STORAGE.md`:
  - Mark Redis Streams `stream:new_property` and `stream:price_change` as implemented
  - Mark consumer group `cg:cache-invalidation` as implemented
  - Update the cache strategy matrix to reflect proactive invalidation
- [ ] **6.2** Document new environment variables in environment reference or `.env.example`:
  - `REDIS_URL` (scrapper-base)
  - All `INVALIDATION_*` variables
- [ ] **6.3** Update `doc/overview/08-caching-storage.md` if it exists with implementation notes
- [ ] **6.4** Update the change spec status from "Proposed" to "Implemented" (done at end of phase 8)
- [ ] **6.5** Add ADR entry for key architectural decisions made during implementation (see spec §15):
  - Flush-all vs selective invalidation
  - In-process consumer vs standalone process
  - SCAN + UNLINK vs Lua script

**Acceptance Criteria**:

- Must: `120-CACHING-STORAGE.md` reflects current invalidation implementation
- Must: Environment variables documented
- Must: ADRs recorded for significant decisions

**Files and modules**:

- `specs/specs/120-CACHING-STORAGE.md` (updated)
- `.env.example` or equivalent config reference (updated)
- `doc/overview/08-caching-storage.md` (updated if exists)
- `doc/decisions/adr-*.md` (new — architectural decisions)

**Tests**:

- Manual review of documentation accuracy

**Completion signal**: `docs(STORY-24): update documentation for cache invalidation`

---

### Phase 7: Code Review (Analysis)

**Goal**: Perform structured code review of all changes against the spec and project standards.

**Tasks**:

- [ ] **7.1** Run automated checks:
  - `ruff check src/scrapper-base/ src/real-estate-api/` — no lint warnings
  - `mypy --strict src/` — no type errors
  - `pytest tests/ -v --cov=. --cov-fail-under=80` — tests pass with coverage
- [ ] **7.2** Verify all AGENTS.md hard rules are respected:
  - No `print()` — structured logging only
  - No synchronous DB drivers — async only
  - All function signatures have type hints
  - Redis Stream `XADD` uses `MAXLEN`
  - No hardcoded secrets — all via env vars
- [ ] **7.3** Verify acceptance criteria traceability:
  - Every AC from spec §17 has a corresponding test or manual verification
  - Every F-# capability is implemented in at least one phase
- [ ] **7.4** Verify security review highlights (spec §21):
  - No user-controlled input reaches Redis commands directly
  - Stream payloads contain no secrets or credentials
  - Event payloads validated through `PropertyCreate` model
- [ ] **7.5** Verify edge cases:
  - Redis is unreachable at startup → consumer degrades gracefully
  - Redis becomes unreachable during polling → retry with backoff
  - Multiple API replicas → consumer group ensures once-per-event processing
  - Empty `changed_fields` → no detail key invalidation (correct behavior)
  - Non-existent property IDs in detail key → UNLINK is no-op

**Acceptance Criteria**:

- Must: All lint and type checks pass
- Must: Test coverage ≥ 80%
- Must: All ACs from spec are verifiable
- Should: No warnings from ruff or mypy

**Files and modules**:

- All files from phases 1–6

**Tests**:

- Full CI pipeline run

**Completion signal**: `chore(STORY-24): code review findings addressed`

---

### Phase 8: Finalize and Release

**Goal**: Final version bump, spec reconciliation, and merge preparation.

**Tasks**:

- [ ] **8.1** Version bump per repo conventions (minor version increment for `real-estate-api` and `scrapper-base`; deprecation note on unchanged packages)
- [ ] **8.2** Update change spec status from "Proposed" to "Implemented" in `chg-STORY-24-spec.md`
- [ ] **8.3** Ensure `chg-STORY-24-plan.md` `status` field is set to "Updated" if plan was revised during execution
- [ ] **8.4** Populate execution log in this plan document with phase statuses
- [ ] **8.5** Verify branch is up to date with `main`: `git fetch origin main && git rebase origin/main`
- [ ] **8.6** Final review of the complete diff to ensure no accidental changes outside scope
- [ ] **8.7** Squash merge preparation: verify PR description references spec modules and acceptance criteria

**Acceptance Criteria**:

- Must: Version bumped in `pyproject.toml` for both packages
- Must: Spec status updated
- Must: Branch rebased on latest `main`
- Must: No unrelated files changed

**Files and modules**:

- `src/scrapper-base/pyproject.toml` (updated — version bump)
- `src/real-estate-api/pyproject.toml` (updated — version bump)
- `doc/changes/2026-06/2026-06-22--STORY-24--cache-invalidation-property-upsert/chg-STORY-24-spec.md` (updated — status)
- `doc/changes/2026-06/2026-06-22--STORY-24--cache-invalidation-property-upsert/chg-STORY-24-plan.md` (updated — execution log)

**Tests**:

- Final CI run

**Completion signal**: `chore(STORY-24): finalize and release cache invalidation`

---

## Test Scenarios

| ID | Scenario | Phases | AC |
|----|----------|--------|----|
| TS-1 | New property scraped — event published to `stream:new_property` with `is_new: true` | 2 | AC-F1-1 |
| TS-2 | Existing property updated — event published to `stream:new_property` with `is_new: false` and `changed_fields` | 2 | AC-F1-2 |
| TS-3 | Price change upsert — event published to `stream:price_change` with old/new prices | 2 | AC-F2-1 |
| TS-4 | Consumer reads `new_property` event — `properties:list:*` keys deleted, event acknowledged | 3 | AC-F3-1, AC-F4-1 |
| TS-5 | Consumer group `cg:cache-invalidation` created on both streams at startup | 3 | AC-F3-2 |
| TS-6 | Failed event retried 3 times then moved to dead-letter stream | 3 | AC-F3-3 |
| TS-7 | `cities:list` key deleted on any property upsert | 3 | AC-F4-2 |
| TS-8 | `price_change` event triggers `properties:detail:{id}` deletion | 3 | AC-F5-1 |
| TS-9 | `new_property` with `is_new: false` and changed_fields triggers detail key deletion | 3 | AC-F5-2 |
| TS-10 | Successful invalidation increments `invalidation_events_total` counter | 4 | AC-F6-1 |
| TS-11 | Failed invalidation increments `invalidation_errors_total` counter | 4 | AC-F6-2 |
| TS-12 | Key deletion increments `invalidation_keys_deleted_total` per pattern | 4 | AC-F6-3 |
| TS-13 | Redis unavailable — consumer retries without crashing the application | 3 | AC-F7-1 |
| TS-14 | Consumer stopped — API requests work and serve TTL-bounded cache | 3 | AC-F7-2 |
| TS-15 | Health endpoint returns invalidation consumer status | 4 | AC-NFR-2 |
| TS-16 | End-to-end flow: publish → consume → invalidate → verify cache miss on next request | 5 | AC-F3-1, AC-F4-1 |
| TS-17 | Consumer recovers after Redis outage and processes accumulated pending entries | 5 | NFR-5, NFR-6 |

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

## Execution Log

| Phase | Status | Started | Completed | Commit | Notes |
|-------|--------|---------|-----------|--------|-------|
| 1. Environment & Scaffolding | ❌ Pending | — | — | — | — |
| 2. Core — Stream Publishing | ❌ Pending | — | — | — | — |
| 3. Core — Invalidation Consumer | ❌ Pending | — | — | — | — |
| 4. Observability & Health | ❌ Pending | — | — | — | — |
| 5. Tests | ❌ Pending | — | — | — | — |
| 6. Documentation & Spec Sync | ❌ Pending | — | — | — | — |
| 7. Code Review | ❌ Pending | — | — | — | — |
| 8. Finalize and Release | ❌ Pending | — | — | — | — |
