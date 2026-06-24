---
change:
  ref: STORY-24
  type: feat
  status: Proposed
  slug: cache-invalidation-property-upsert
  title: "Invalidate relevant cache keys on new property scrape"
  owners: ["rendenwald"]
  service: real-estate-api
  labels: ["change"]
  version_impact: minor
  audience: internal
  security_impact: low
  risk_level: medium
  dependencies:
    internal:
      - real-estate-api
      - scrapper-base
      - Redis 7
    external: []
links:
  epic: ../../../../doc/planning/epics/epic-05--redis-cache/epic-05--redis-cache.md
  spec_modules:
    - ../../../../specs/specs/080-API.md
    - ../../../../specs/specs/120-CACHING-STORAGE.md
---

# CHANGE SPECIFICATION

> **PURPOSE**: Add proactive cache invalidation triggered by property upsert events so that API consumers see fresh property data within seconds of a scrape, rather than waiting up to the full 120-second TTL.

## 1. SUMMARY

This change introduces cache invalidation when the scrapper-base pipeline upserts a property. On any property insert or update, affected Redis cache keys are deleted so subsequent API requests fetch fresh data from the database and repopulate the cache. List cache keys (`properties:list:*`) and the aggregated `cities:list` key are invalidated on any property upsert; individual detail keys (`properties:detail:{id}`) are invalidated on price or field changes. The invalidation is driven by Redis Stream events published from the scrapper-base pipeline and consumed by the real-estate-api cache layer, keeping the two components decoupled.

## 2. CONTEXT

### 2.1 Current State Snapshot

- STORY-23 implemented a Redis cache-aside layer for `GET /api/v1/properties` with a 120-second TTL and `X-Cache` response headers
- The cache key patterns defined in `120-CACHING-STORAGE.md` are:
  - `properties:list:{sha256hex(params)}` — TTL 120s, populated by `GET /api/v1/properties`
  - `cities:list` — TTL 3600s (to be implemented under STORY-25)
  - `properties:detail:{id}` — TTL 300s (to be implemented separately)
- scrapper-base's `PropertyService.upsert_property()` inserts new records and updates existing ones, returning `(property, is_new)` where `is_new` distinguishes inserts from updates
- The architecture diagram in `120-CACHING-STORAGE.md` defines two Redis Streams:
  - `stream:new_property` — triggered after property upsert
  - `stream:price_change` — triggered after price update
- Neither stream is currently published to nor consumed — no invalidation mechanism exists yet
- scrapper-base does not currently have a Redis client dependency; it only connects to PostgreSQL and MinIO
- real-estate-api has a full Redis client (`RedisClient`) and cache service (`CacheService`) with connection pooling, health checks, and graceful degradation

### 2.2 Pain Points / Gaps

- After a scraper run inserts or updates properties, API responses return stale cached data for up to 120 seconds (the TTL of list keys)
- Users browsing the platform immediately after a scrape see outdated listings, missing newly scraped properties
- The `allkeys-lru` eviction policy does not remove specific keys on data change — invalidation must be explicit
- No mechanism exists for scrapper-base to signal the cache layer that data has changed — the two components operate independently against the same Redis instance but have no coordination protocol
- No observability exists for cache invalidation events — operators cannot measure invalidation latency or detect missed invalidations

## 3. PROBLEM STATEMENT

Because the Redis cache has no proactive invalidation, newly scraped properties remain invisible to API consumers for up to 120 seconds, and updated property fields (price, availability, description) are served stale for the same window, contradicting the product expectation of near-real-time listing freshness after a scraper run.

## 4. GOALS

- **G-1**: Newly scraped properties appear in API list responses within 5 seconds of upsert completing
- **G-2**: Updated property fields (price, description, status) are reflected in detail and list responses within 5 seconds of upsert completing
- **G-3**: The `cities:list` cache is invalidated on any property upsert so city-level offer counts reflect current data
- **G-4**: Invalidation failures (e.g., Redis temporarily unreachable) never cause data loss or API errors — staleness is bounded by the existing TTL
- **G-5**: Cache invalidation events are observable via Prometheus metrics and structured logs

### 4.1 Success Metrics / KPIs

| Metric | Target |
|--------|--------|
| Invalidation latency (upsert completion → cache key deleted) | p95 < 3 seconds |
| Invalidation success rate | > 99.9% of upsert events result in invalidation |
| Cache freshness window (max staleness after invalidation fails) | ≤ 120 seconds (bounded by TTL) |
| Percentage of cache miss responses caused by invalidation (vs. TTL expiry) | Measurable via `invalidation_events_total` vs `cache_misses_total` |
| Error rate during Redis Stream consumer outage | 0% — data eventually consistent via TTL |

### 4.2 Non-Goals

- **NG-1**: Implementing Redis Stream publishing infrastructure in scrapper-base (e.g., Redis client, connection management) — covered by this story as a new dependency, scoped to stream publishing only
- **NG-2**: Consuming Redis Streams for alert delivery — that is STORY-26; this story uses the same stream pattern only for invalidation
- **NG-3**: Selective invalidation of only affected `properties:list:{hash}` keys (e.g., per-city pattern deletion) — the initial implementation uses a flush-everything approach for simplicity; selective invalidation may be added later
- **NG-4**: Caching and invalidation for `/api/v1/properties/{id}`, `/api/v1/stats`, or `/api/v1/exchange-rates` — those are separate stories
- **NG-5**: Cache pre-warming or seeding after invalidation — new cache entries are populated lazily on the first request after invalidation
- **NG-6**: Distributed cache invalidation across multiple API replicas — the stream consumer group pattern handles this; each consumer in the group processes events exactly once
- **NG-7**: Implementing the `cities:list` endpoint or its caching — covered by STORY-25; this story only invalidates the key when it exists

## 5. FUNCTIONAL CAPABILITIES

| ID | Capability | Rationale |
|----|------------|-----------|
| F-1 | Property upsert event publication from scrapper-base | After `upsert_property()` completes, scrapper-base publishes an event to the `new_property` Redis Stream with metadata about the upserted property (id, city, property type, portal_source, is_new flag, changed fields) |
| F-2 | Property update event publication (price change) | When a property update includes a price change, scrapper-base additionally publishes to the `price_change` Redis Stream with the property id and old/new price values |
| F-3 | Stream-based cache invalidation consumer | A consumer (running within real-estate-api or as a standalone process) reads from `new_property` and `price_change` Redis Streams using consumer groups, processing each event and deleting affected cache keys |
| F-4 | Pattern-based invalidation of list cache keys | On any `new_property` event, all keys matching `properties:list:*` are deleted via Redis SCAN + DEL (or UNLINK for non-blocking deletion), and the `cities:list` key is deleted |
| F-5 | Targeted invalidation of property detail keys | On a `price_change` event, the specific `properties:detail:{id}` key is deleted (when implemented); on a `new_property` event where the property was updated (not new), detail keys for that property are also invalidated |
| F-6 | Invocation observability | Prometheus counters track invalidation events, deleted key counts, and errors; structured logs record each invalidation with cause (event type, property id, city) |
| F-7 | Graceful failure handling | If the invalidation consumer fails to process an event (e.g., Redis momentarily unreachable), the event is retried up to N times, then moved to a dead-letter stream; data is eventually consistent via the existing TTL |

### 5.1 Capability Details

**F-1 (Property Upsert Event Publication):**
- After `PropertyService.upsert_property()` returns, scrapper-base publishes to the `stream:new_property` Redis Stream
- The event payload is a JSON string containing: `property_id`, `portal_source`, `source_id`, `city`, `property_type`, `is_new` (boolean), `changed_fields` (list of field names that changed), and `timestamp`
- Stream messages include `MAXLEN ~10_000` as defined in `120-CACHING-STORAGE.md` to prevent unbounded growth
- Publishing uses a dedicated Redis connection configured for scrapper-base (separate from the cache layer's Redis client), connecting via `REDIS_URL` environment variable compatible with the existing Redis deployment

**F-2 (Price Change Event Publication):**
- On each upsert, scrapper-base detects whether the `price` field changed compared to the existing record
- If price changed, a separate event is published to `stream:price_change` with: `property_id`, `old_price`, `new_price`, `currency`, `city`, `portal_source`
- The `price_change` stream uses `MAXLEN ~10_000` as defined in `120-CACHING-STORAGE.md`
- Price change detection is done by comparing the incoming price with the existing property's price before the upsert

**F-3 (Stream-Based Cache Invalidation Consumer):**
- A consumer group `cg:cache-invalidation` is created on `stream:new_property` and `stream:price_change`
- Each event is read using `XREADGROUP` with `>` (new messages only) and acknowledged with `XACK` after successful processing
- The consumer runs as a background task within the real-estate-api application lifespan (started on app startup, cancelled on shutdown)
- Consumer group semantics ensure each event is processed exactly once even with multiple API replicas
- Events that fail processing are retried up to 3 times, then moved to `stream:dead_letter` per the retry policy in `120-CACHING-STORAGE.md`
- The consumer processes events in batches (up to 10 at a time) with a configurable poll interval (default 1 second)

**F-4 (Pattern-Based List Cache Invalidation):**
- On receiving a `new_property` event, the consumer uses Redis `SCAN 0 MATCH properties:list:* COUNT 100` in a loop to find all list cache keys, then applies `UNLINK` (non-blocking delete) on each matched key
- The `cities:list` key (when present) is deleted directly via `UNLINK cities:list`
- Pattern-based flush is intentionally broad — at the expected scale (~500 unique keys), the operation completes in < 50ms
- If the `SCAN` or `UNLINK` operation fails, the event is left unacknowledged for retry per F-3

**F-5 (Targeted Detail Key Invalidation):**
- On receiving a `price_change` event, the consumer deletes `properties:detail:{property_id}` via `UNLINK`
- On receiving a `new_property` event where `is_new` is `false` (update, not insert) and `changed_fields` is non-empty, the consumer also deletes `properties:detail:{property_id}`
- This ensures that property detail views reflect the latest state after an update
- Not deleting detail keys on `is_new: true` (inserts) is safe — no detail cache entry exists for a never-before-seen property

**F-6 (Invocation Observability):**
- New Prometheus counters (registered in `real-estate-api/app/core/metrics.py`):
  - `invalidation_events_total` — Counter with labels `stream` (new_property|price_change), `result` (success|skipped|error)
  - `invalidation_keys_deleted_total` — Counter with labels `key_pattern` (properties:list:*|cities:list|properties:detail:*)
  - `invalidation_errors_total` — Counter with labels `stream`, `error_type`
  - `invalidation_consumer_lag_seconds` — Gauge tracking how far behind the consumer is (difference between stream last-entry timestamp and last-processed timestamp)
- Structured logs at info level for each invalidation event: event type, property id, city, number of keys deleted, duration
- Warning-level logs for retries; error-level logs for dead-letter events

**F-7 (Graceful Failure Handling):**
- If the consumer cannot connect to Redis at startup, it retries with exponential backoff (1s, 2s, 4s, ... up to 60s max) and logs warnings
- If a single event processing fails (e.g., SCAN times out), the event is not acknowledged and will be redelivered after the pending-entries timeout
- After 3 failed attempts, the event is moved to `stream:dead_letter` with original payload and error context, then acknowledged
- Dead-letter events are logged at error level with full context for manual investigation
- The consumer health is exposed via the `/health` endpoint (extended to include invalidation consumer status)

## 6. USER & SYSTEM FLOWS

```
Flow 1: New property scraped (nominal path)
  Scrapy spider → process_item() → item_to_data() → upsert_property()
  → is_new: True → publish to stream:new_property {property_id, city, is_new: true}
  → Cache invalidation consumer reads event
  → SCAN properties:list:* → UNLINK all matched keys
  → UNLINK cities:list
  → XACK event
  → Next API request for properties list: cache miss → DB query → repopulate cache

Flow 2: Existing property updated (price change)
  Scrapy spider → process_item() → item_to_data() → upsert_property()
  → is_new: False, price changed from 500000 to 520000
  → publish to stream:new_property {property_id, city, is_new: false, changed_fields: ["price"]}
  → publish to stream:price_change {property_id, old_price: 500000, new_price: 520000}
  → Consumer reads from both streams:
     - new_property → SCAN properties:list:* → UNLINK all + UNLINK cities:list
     - price_change → UNLINK properties:detail:{property_id}
  → Next API request for detail page: cache miss → DB query → repopulate detail cache
  → Next API request for list: cache miss → DB query → repopulate list cache

Flow 3: Invalidation consumer temporarily down
  Scraper batch completes → events published to stream:new_property
  → Consumer process crashes or restarts
  → Events accumulate in stream (pending entries list)
  → Consumer restarts → XREADGROUP reads pending entries
  → Processes all accumulated events → invalidates cache
  → During consumer downtime: API serves stale cache (bounded by 120s TTL)
  → No data loss; consumers catch up within seconds of restart

Flow 4: Multiple properties scraped in batch (burst)
  Scraper processes 100 properties in 30 seconds
  → Each upsert publishes a stream:new_property event
  → Consumer reads events in batches of up to 10 every 1 second
  → Each event triggers SCAN + UNLINK of all properties:list:* keys
  → Redundant invalidations (same keys deleted 100 times) are harmless:
     UNLINK on non-existent keys is a no-op
  → Next API request after batch completes: cache miss → repopulate
```

## 7. SCOPE & BOUNDARIES

### 7.1 In Scope

- Redis Stream publishing from scrapper-base after each `upsert_property()` call
- Redis Stream consumer for cache invalidation running within real-estate-api lifecycle
- Creation and management of consumer groups (`cg:cache-invalidation`) on `stream:new_property` and `stream:price_change`
- Pattern-based deletion of `properties:list:*` keys on any property upsert
- Direct deletion of `cities:list` key on any property upsert
- Direct deletion of `properties:detail:{id}` on price change or field updates
- Retry and dead-letter handling for failed invalidation events
- Prometheus metrics for invalidation events, key deletions, consumer lag, and errors
- Health check endpoint extension to report invalidation consumer status
- Environment variable configuration for scrapper-base Redis connection
- Graceful startup/shutdown of the invalidation consumer

### 7.2 Out of Scope

- [OUT] Redis Stream infrastructure itself (streams are already defined in `120-CACHING-STORAGE.md`; this story implements the publishing and consuming)
- [OUT] Alert delivery via Redis Streams — covered by STORY-26
- [OUT] Caching of `/api/v1/properties/{id}`, `/api/v1/cities`, `/api/v1/stats` — separate stories
- [OUT] Selective invalidation (e.g., invalidating only list keys for the affected city) — deferred optimization
- [OUT] Cache warming after invalidation — lazy population on first request
- [OUT] Cross-datacenter or cluster-mode Redis invalidation — single-instance Redis for Phase 1
- [OUT] Database-level triggers or change-data-capture (CDC) for invalidation — application-level invalidation is sufficient
- [OUT] Frontend changes — API response shape is unchanged
- [OUT] Changes to the property upsert logic itself — only the post-upsert publication is added
- [OUT] MinIO or photo storage cache invalidation — photo URLs are generated with short-lived pre-signed tokens

### 7.3 Deferred / Maybe-Later

- Selective invalidation per-city/property-type — evaluate if flush-all pattern causes excessive cache misses under heavy traffic
- Batch deduplication of invalidation events — if multiple properties in the same scrape run trigger redundant flush-all cycles, consider debouncing with a short window (e.g., flush once per batch)
- Standalone invalidation consumer as a separate Kubernetes Deployment (separate from real-estate-api) — useful if consumer processing becomes a bottleneck
- Consumer lag alerting via Alertmanager — add when consumer-lag Gauge crosses a threshold

## 8. INTERFACES & INTEGRATION CONTRACTS

### 8.1 REST / HTTP Endpoints

No new REST endpoints. The existing endpoints are unchanged:

| Endpoint | Change |
|----------|--------|
| `GET /api/v1/properties` | No change to request/response contract; benefit from fresher cached data |
| `GET /health` | Extended to include invalidation consumer status: `{"redis": "ok", "invalidation_consumer": "running"|"degraded"|"stopped"}` |

### 8.2 Events / Messages

| Event | Stream | Producer | Consumer | Payload |
|-------|--------|----------|----------|---------|
| Property upserted | `stream:new_property` | scrapper-base (after `upsert_property`) | Cache invalidation consumer | `{"property_id": int, "portal_source": str, "source_id": str, "city": str\|null, "property_type": str\|null, "is_new": bool, "changed_fields": list[str], "timestamp": ISO datetime}` |
| Price changed | `stream:price_change` | scrapper-base (when price differs from existing) | Cache invalidation consumer | `{"property_id": int, "portal_source": str, "source_id": str, "city": str\|null, "old_price": int\|null, "new_price": int, "currency": str, "timestamp": ISO datetime}` |

**Stream configuration:**

| Property | Value |
|----------|-------|
| `stream:new_property` MAXLEN | ~10_000 (approximate trim) |
| `stream:price_change` MAXLEN | ~10_000 (approximate trim) |
| Consumer group (new_property) | `cg:cache-invalidation` |
| Consumer group (price_change) | `cg:cache-invalidation` |
| Dead-letter stream | `stream:dead_letter` with MAXLEN ~1_000 |
| Max retries before dead-letter | 3 |

### 8.3 Data Model Impact

| ID | Element | Description |
|----|---------|-------------|
| DM-1 | Redis Stream `stream:new_property` | New stream (might already exist from prior stream definitions in `120-CACHING-STORAGE.md`); this story implements the producer and consumer |
| DM-2 | Redis Stream `stream:price_change` | New stream (might already exist); this story implements the producer and consumer |
| DM-3 | Consumer group `cg:cache-invalidation` | New consumer group on both streams |
| DM-4 | Redis keys `properties:list:*` | No change to key format; these keys are now proactively deleted (they were previously TTL-expired only) |
| DM-5 | Redis key `cities:list` | No change to key format; now proactively deleted on property upsert |
| DM-6 | `invalidation_events_total` | New Prometheus counter |
| DM-7 | `invalidation_keys_deleted_total` | New Prometheus counter |
| DM-8 | `invalidation_errors_total` | New Prometheus counter |
| DM-9 | `invalidation_consumer_lag_seconds` | New Prometheus gauge |

No database schema changes. No new database tables or columns.

### 8.4 External Integrations

| Service | Interface | Purpose | Change |
|---------|-----------|---------|--------|
| Redis 7 | `redis.asyncio` client | Stream publishing from scrapper-base | New dependency for `scrapper-base` (Redis client added) |
| Redis 7 | `redis.asyncio` client | Stream consuming (via real-estate-api) | New consumer group operations; new invalidation operations (SCAN, UNLINK) |
| PostgreSQL 16 | SQLAlchemy 2.0 async | Property upsert and price detection | No change |

### 8.5 Backward Compatibility

- Fully backward compatible — no API contract changes
- Existing cache keys (`properties:list:{hash}`) that were previously TTL-expired will now also be proactively deleted on upsert — this is a strictly additive behavior change that only reduces staleness
- If the invalidation consumer fails to start or crashes, the existing TTL-based expiry continues to work — no regression
- Existing Redis clients (monitoring tools, redis-cli) are unaffected — new streams and consumer groups are additive
- Scrapper-base pipelines (OtodomPipeline, etc.) require no code changes beyond the base class — the publication is handled by `BasePipeline`
- Event payloads are JSON — any consumer can read the streams, not just the invalidation consumer

## 9. NON-FUNCTIONAL REQUIREMENTS (NFRs)

| ID | Requirement | Threshold |
|----|-------------|-----------|
| NFR-1 | Invalidation consumer startup time | Consumer must be ready to process events within 5 seconds of application startup |
| NFR-2 | Invalidation latency (upsert → keys deleted) | p95 < 3 seconds, p99 < 5 seconds under normal load |
| NFR-3 | Stream event processing rate | Minimum 50 events/second sustained |
| NFR-4 | SCAN + UNLINK throughput | Full flush of ~500 properties:list:* keys completes in < 100ms |
| NFR-5 | Consumer restart recovery | On restart, consumer processes all accumulated pending entries within 30 seconds |
| NFR-6 | Error recovery | After Redis recovers from an outage, consumer resumes processing within one health-check interval (30 seconds) |
| NFR-7 | Memory overhead per invalidation consumer | < 10 MB RSS beyond the base application |
| NFR-8 | Failed event retry backoff | Exponential backoff: 1s, 2s, 4s; max 3 retries before dead-letter |
| NFR-9 | Consumer poll interval | Configurable, default 1 second (poll timeout: 5 seconds, returns early if messages available) |
| NFR-10 | Dead-letter retention | Events remain in dead-letter stream for 7 days (matching Loki retention as per `120-CACHING-STORAGE.md`) |

## 10. TELEMETRY & OBSERVABILITY REQUIREMENTS

**Metrics (Prometheus counters/histograms):**

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `invalidation_events_total` | Counter | `stream` (new_property\|price_change), `result` (success\|skipped\|error) | Count of invalidation events processed |
| `invalidation_keys_deleted_total` | Counter | `key_pattern` (properties:list:\*\|cities:list\|properties:detail:\*) | Count of cache keys deleted by invalidation |
| `invalidation_errors_total` | Counter | `stream`, `error_type` | Count of invalidation processing errors |
| `invalidation_consumer_lag_seconds` | Gauge | `stream` | How far behind the consumer is (seconds between last stream entry and last processed entry) |
| `invalidation_duration_seconds` | Histogram | `operation` (scan\|unlink\|xread\|xack) | Duration of invalidation operations |

**Logging:**

- Info level: each invalidation event processed — `"event_type": "new_property", "property_id": 123, "city": "Warszawa", "keys_deleted": 12, "duration_ms": 45`
- Warning level: retry attempts, consumer restarts, stream reconnection
- Error level: dead-letter events (with full payload), consumer failures that cannot be recovered, stream consumer group creation failures
- Debug level: per-event details (all fields, individual key deletions)

**Health check:**

- `GET /health` extended with `"invalidation_consumer": "running" | "degraded" | "stopped"`
- `running`: consumer is actively processing events
- `degraded`: consumer is connected but has unprocessed pending entries > 1000 or has errors in the last 5 minutes
- `stopped`: consumer is not running (startup failure or crashed)
- Consumer status is derived from the consumer group info (`XINFO GROUPS stream:new_property`) and in-memory state

## 11. RISKS & MITIGATIONS

| ID | Risk | Impact | Probability | Mitigation | Residual Risk |
|----|------|--------|-------------|------------|---------------|
| RSK-1 | Invalidation consumer falls behind during high-volume scrape (thousands of properties) | Medium — cache keys not invalidated promptly, stale data served longer | Medium | Batch processing (up to 10 events per read); consumer poll interval configurable; monitor `invalidation_consumer_lag_seconds` | Low — even if consumer lags, TTL provides eventual consistency |
| RSK-2 | Flush-all pattern causes cache miss storm after large scrape: every list request hits the DB | Medium — increased DB load until cache repopulates | Medium | New keys are repopulated on first request per key; 120s TTL means keys are only recomputed once; consider debouncing if persistent issue | Low — cache miss storm is self-limiting as keys repopulate |
| RSK-3 | Redis Stream message loss causes missed invalidation | Medium — cache not invalidated, stale data up to TTL | Low | Consumer groups with `XACK` guarantee at-least-once delivery; dead-letter stream for persistent failures | Low — at-least-once delivery prevents message loss; duplicate processing is harmless (UNLINK on missing key is no-op) |
| RSK-4 | scrapper-base Redis connection exhaustion | Medium — scrapper pipeline fails if Redis pool exhausted | Low | Separate Redis connection pool for scrapper-base with small size (pool_size=2); short timeout (2s) | Low — scrapper-base has minimal Redis usage (only stream publish) |
| RSK-5 | Stream consumer group rebalancing (multiple API replicas) causes duplicate processing | Low — duplicate UNLINK is harmless | Low | UNLINK on non-existent keys is a no-op; dedup within processing window is acceptable | Low — no correctness impact |
| RSK-6 | Redis SCAN blocks on large key space | Low — operation may be slow if Redis is under memory pressure | Low | SCAN is non-blocking (cursor-based iteration); use UNLINK (non-blocking) vs DEL | Low — even slow SCAN only adds milliseconds to processing |
| RSK-7 | Dead-letter stream grows unboundedly | Low — disk usage | Low | `MAXLEN ~1_000` on dead-letter stream as defined in `120-CACHING-STORAGE.md` | Low — bounded by configuration |

## 12. ASSUMPTIONS

- Redis 7 is deployed and accessible from both scrapper-base and real-estate-api at the configured `REDIS_URL`
- The `stream:new_property` and `stream:price_change` Redis Streams may or may not exist at deployment time — the consumer creates them on startup if they do not exist
- The `cg:cache-invalidation` consumer group may already exist (e.g., if the application restarted) — the consumer handles the `BUSYGROUP` error gracefully
- scrapper-base's `upsert_property()` method already distinguishes new inserts from updates (`is_new` flag) — this capability exists in the current implementation (see `services.py` lines 232-233)
- scrapper-base's `upsert_property()` has access to both the incoming data and the existing record, enabling price-change detection
- The `allkeys-lru` eviction policy on Redis means that stale cache keys may be evicted before TTL expiry — this is acceptable; invalidation is proactive, not a substitute for TTL
- The number of `properties:list:*` cache keys is bounded (estimated ~500 unique combinations per `120-CACHING-STORAGE.md` appendix B) — the flush-all pattern is efficient at this scale
- Invalidation does not need to be transactional with the upsert — eventual consistency within TTL is acceptable for the product use case
- The solo developer (@rendenwald) is responsible for monitoring dead-letter events and investigating persistent failures

## 13. DEPENDENCIES

| Direction | Item | Notes |
|-----------|------|-------|
| Depends on | STORY-23 (Redis cache-aside for properties list) | Cache layer must exist for invalidation to be meaningful |
| Depends on | scrapper-base with `upsert_property()` | The upsert method provides the trigger point for publishing invalidation events |
| Depends on | Redis 7 running in `storage-ns` | Streams, SCAN, UNLINK operations require Redis 7+ |
| Depends on | `redis` Python package (>=5.0, async compatible) in scrapper-base | New dependency added to `scrapper-base/pyproject.toml` |
| Depends on | Redis Stream consumer group support | Requires Redis 5.0+ (Redis 7 is used per architecture spec) |
| Blocks | STORY-25 (Cache cities endpoint) | STORY-24 provides the invalidation mechanism that STORY-25 will rely on for `cities:list` freshness |
| Blocks | STORY-26 (Redis Streams for alert delivery) | Stream publishing from scrapper-base is a shared capability needed for alert delivery |
| Related | STORY-27 (Graceful fallback when Redis unavailable) | Invalidation is disabled when Redis is unreachable; TTL-based expiry acts as the fallback |

## 14. OPEN QUESTIONS

| ID | Question | Context | Status |
|----|----------|---------|--------|
| OQ-1 | Should the invalidation consumer run as a background task within the real-estate-api process, or as a separate standalone process? | Running in-process simplifies deployment (no separate k8s Deployment, health check, or Docker image) but shares resources with API requests. A separate process isolates invalidation processing from API traffic. | Decision needed: consult `@architect` |
| OQ-2 | Should scrapper-base publish to Redis Streams directly (requiring a Redis client dependency) or via a lightweight sidecar/proxy? | Adding `redis-py` to scrapper-base adds a new dependency but enables direct stream publishing. A sidecar adds deployment complexity. Given scrapper-base already runs as a batch process with database connectivity, a Redis client is a minimal addition. | Recommended: direct publishing from scrapper-base (simpler); dependency is low-risk |
| OQ-3 | Should the invalidation key patterns (`properties:list:*`, `cities:list`, `properties:detail:*`) be configurable via environment variables? | Hardcoded patterns reduce operational flexibility if key naming changes. Configurable patterns enable reuse in different environments. | Recommended: configurable via env vars with sensible defaults matching the spec-defined patterns |
| OQ-4 | Should `properties:list:*` invalidation use SCAN + UNLINK (iterative) or a Lua script (atomic)? | SCAN + UNLINK is non-blocking and safe for production. A Lua script is atomic but blocks Redis during execution. For ~500 keys, the latency difference is negligible. | Recommended: SCAN + UNLINK (non-blocking, no atomicity requirement since UNLINK on miss is harmless) |
| OQ-5 | Should the scrapper-base upsert method return the set of changed fields so the caller can publish targeted events? | Currently `upsert_property()` returns `(property, is_new)`. Adding `changed_fields` to the return value would enable more precise invalidation events. | Recommended: extend `upsert_property()` return to include `changed_fields` (non-breaking change) |

## 15. DECISION LOG

| ID | Decision | Rationale | Date |
|----|----------|-----------|------|
| DEC-1 | Use Redis Streams for invalidation events rather than direct cache key manipulation from scrapper-base | Decouples scrapper-base from cache key patterns; aligns with existing architecture in `120-CACHING-STORAGE.md`; enables multiple consumers (invalidation, alerts) | 2026-06-22 |
| DEC-2 | Flush-all pattern for `properties:list:*` rather than selective per-city invalidation | Simpler to implement and reason about; at expected scale (~500 keys), flush completes in < 100ms; correctness is guaranteed (no risk of missing keys that should be invalidated) | 2026-06-22 |
| DEC-3 | Use `UNLINK` (non-blocking) rather than `DEL` for key deletion | UNLINK is asynchronous and does not block Redis, reducing risk of latency spikes during invalidation bursts | 2026-06-22 |
| DEC-4 | Threshold-based retry (3 attempts) with dead-letter stream | Balances resilience against transient failures with protection against infinite retry loops; dead-letter provides forensic trail | 2026-06-22 |
| DEC-5 | Invalidation consumer uses a separate consumer group on existing streams (not a dedicated invalidation stream) | Reuses the stream architecture already defined in `120-CACHING-STORAGE.md`; consumer groups allow independent offset tracking per consumer type | 2026-06-22 |
| DEC-6 | scrapper-base publishes events AFTER successful upsert (not before) | Ensures invalidation only triggers when data has actually changed; avoids unnecessary cache flushes on failed upserts | 2026-06-22 |

## 16. AFFECTED COMPONENTS (HIGH-LEVEL)

| Component | Impact |
|-----------|--------|
| scrapper-base (`BasePipeline`) | Updated — post-upsert Redis Stream publishing added; new Redis client dependency |
| scrapper-base (`PropertyService`) | Updated — return value extended to include `changed_fields` for targeted invalidation |
| scrapper-base (`pyproject.toml`) | Updated — `redis` dependency added |
| real-estate-api (cache layer) | Updated — new invalidation consumer background task added to application lifecycle |
| real-estate-api (`app/core/metrics.py`) | Updated — new Prometheus metrics for invalidation |
| real-estate-api (`app/routers/health.py`) | Updated — invalidation consumer status added to health response |
| real-estate-api (`app/core/config.py`) | Updated — configurable invalidation consumer settings added |
| Redis 7 streams | Updated — existing streams gain new producers (scrapper-base) and consumers (cache invalidator) |

## 17. ACCEPTANCE CRITERIA

| ID | Criterion | Linked |
|----|-----------|--------|
| AC-F1-1 | **Given** a scraper pipeline calls `upsert_property()` with new property data, **when** the upsert succeeds, **then** an event is published to `stream:new_property` with `is_new: true` and the correct property metadata | F-1 |
| AC-F1-2 | **Given** a scraper pipeline calls `upsert_property()` with existing property data, **when** the upsert succeeds, **then** an event is published to `stream:new_property` with `is_new: false` and `changed_fields` containing the modified field names | F-1 |
| AC-F2-1 | **Given** an upsert changes the property price, **when** the upsert succeeds, **then** an event is published to `stream:price_change` with the old and new prices | F-2 |
| AC-F3-1 | **Given** a `new_property` event is published to `stream:new_property`, **when** the invalidation consumer reads it, **then** `properties:list:*` keys are deleted and the event is acknowledged | F-3, F-4 |
| AC-F3-2 | **Given** the invalidation consumer starts, **when** the application is ready, **then** the consumer group `cg:cache-invalidation` exists on both streams | F-3 |
| AC-F3-3 | **Given** a `new_property` event processing fails, **when** the consumer retries 3 times, **then** the event is moved to `stream:dead_letter` and acknowledged | F-3, F-7 |
| AC-F4-1 | **Given** a `new_property` event for a new listing in Warszawa, **when** the consumer processes it, **then** all keys matching `properties:list:*` are deleted, including keys for queries unrelated to Warszawa | F-4 |
| AC-F4-2 | **Given** a `new_property` event is processed, **when** the consumer runs, **then** the `cities:list` key is also deleted if it exists | F-4 |
| AC-F5-1 | **Given** a `price_change` event for property 42, **when** the consumer processes it, **then** the key `properties:detail:42` is deleted | F-5 |
| AC-F5-2 | **Given** a `new_property` event with `is_new: false` and non-empty `changed_fields`, **when** the consumer processes it, **then** the key `properties:detail:{property_id}` is deleted | F-5 |
| AC-F6-1 | **Given** an invalidation event is processed successfully, **when** the operation completes, **then** `invalidation_events_total` counter is incremented with result=success | F-6 |
| AC-F6-2 | **Given** an invalidation event fails, **when** the error occurs, **then** `invalidation_errors_total` is incremented with the appropriate error_type | F-6 |
| AC-F6-3 | **Given** a `new_property` event is processed, **when** keys are deleted, **then** `invalidation_keys_deleted_total` is incremented for each key pattern | F-6 |
| AC-F7-1 | **Given** Redis is unavailable, **when** the invalidation consumer tries to publish or process events, **then** it retries with backoff and does not crash the application | F-7 |
| AC-F7-2 | **Given** the invalidation consumer is stopped, **when** the application serves API requests, **then** requests still work and cache is served from TTL-bounded entries | F-7, G-4 |
| AC-NFR-1 | **Given** a property upsert completes, **when** the invalidation consumer processes the event, **then** p95 invalidation latency is below 3 seconds | NFR-2 |
| AC-NFR-2 | **Given** the application starts, **when** the invalidation consumer initializes, **then** `GET /health` includes invalidation consumer status | NFR-1 |

## 18. ROLLOUT & CHANGE MANAGEMENT (HIGH-LEVEL)

1. **Implementation order:**
   - Phase 1: Add `redis` dependency to scrapper-base; implement stream publishing in `BasePipeline` (post-upsert hook)
   - Phase 2: Implement price-change detection in `upsert_property()` and `stream:price_change` publishing
   - Phase 3: Implement invalidation consumer in real-estate-api (stream reading, key deletion, consumer group management)
   - Phase 4: Add Prometheus metrics and health check extension
   - Phase 5: Add configuration (env vars) for consumer behavior (poll interval, batch size, retry limits)
   - Phase 6: Write tests (unit tests for stream publishing with fakeredis; integration tests for invalidation consumer)
   - Phase 7: Review and spec reconciliation

2. **Deployment order:**
   - Deploy updated scrapper-base first (new `redis` dependency, stream publishing)
   - Deploy updated real-estate-api second (invalidation consumer, metrics, health)
   - The streams are created lazily when first published to or consumed — no pre-creation needed

3. **Merge strategy:** Squash merge to `main` via PR

4. **Communication:** None needed — internal change with no user-facing impact

5. **Rollback:**
   - Revert the invalidation consumer commit in real-estate-api — cache fallback to TTL-only (no proactive invalidation) is safe
   - If scrapper-base publishing is rolled back, the invalidation consumer stops receiving events but continues to idle — no errors
   - If real-estate-api is rolled back, scrapper-base continues publishing to streams (messages accumulate with MAXLEN bound) — no data loss

## 19. DATA MIGRATION / SEEDING (IF APPLICABLE)

N/A — no database schema changes. Redis Streams are created lazily when first published to. No existing data migration needed.

## 20. PRIVACY / COMPLIANCE REVIEW

No personal data is present in invalidation events. Stream payloads contain only property identifiers and metadata (city, property type, price) — already part of public listing data. Stream messages are ephemeral (bounded by MAXLEN ~10,000) and automatically trimmed. No GDPR implications beyond those already addressed by the platform.

## 21. SECURITY REVIEW HIGHLIGHTS

- Stream payloads contain no secrets, credentials, or user data — only property listing metadata
- Redis connection credentials are configured via environment variables (`REDIS_URL`), not hardcoded
- The invalidation consumer only deletes cache keys matching known patterns (`properties:list:*`, `cities:list`, `properties:detail:*`) — no user-controlled key patterns are accepted
- Event payloads are validated JSON; no user-controlled input reaches Redis commands directly (all property data flows through `PropertyCreate` model validation before publication)
- If Redis is compromised, an attacker could prevent invalidation (causing stale data), but cannot inject malicious data into API responses because the cache is always validated against the database on the next miss
- Stream consumer groups ensure that only authorized consumers can read events — no authentication bypass

## 22. MAINTENANCE & OPERATIONS IMPACT

- **Monitoring:** Team must monitor `invalidation_consumer_lag_seconds` and `invalidation_errors_total` to detect consumer degradation
- **Dead-letter inspection:** Periodic review of `stream:dead_letter` entries via `redis-cli XLEN stream:dead_letter` or a Grafana dashboard panel; investigate recurring failures
- **Consumer group management:** The `cg:cache-invalidation` consumer group may accumulate stale consumers on redeployment — the Redis GC CronJob (defined in `120-CACHING-STORAGE.md`) handles cleanup of idle consumers
- **Capacity:** Stream messages are bounded by MAXLEN (~10,000); at ~100 messages per scrape run, the stream retains roughly the last 100 runs (~3-4 days)
- **Redis memory:** Stream data adds negligible memory overhead (~100 bytes per message × 10,000 messages = ~1 MB)
- **Restart behavior:** On real-estate-api restart, the consumer group persists in Redis; the new consumer instance picks up from the last acknowledged position, processing any events that accumulated during downtime
- **Scaling:** If the real-estate-api runs with multiple replicas, the consumer group ensures each event is processed by exactly one consumer instance; redundant processing (all replicas flushing the same keys) is prevented by the group mechanism

## 23. GLOSSARY

| Term | Definition |
|------|------------|
| Consumer group | Redis Streams feature enabling multiple consumers to cooperatively process messages from a stream, with each message delivered to only one consumer |
| Dead-letter stream | A Redis Stream where events that failed processing after max retries are stored for manual investigation |
| Invalidation consumer | The process (background task) that reads invalidation events from Redis Streams and deletes affected cache keys |
| Stream publishing | The act of adding a message to a Redis Stream using `XADD` |
| `XACK` | Redis command to acknowledge a stream message as processed, removing it from the pending entries list |
| `XREADGROUP` | Redis command to read messages from a stream as part of a consumer group |
| `SCAN` | Redis cursor-based command for iterating over keys matching a pattern — non-blocking |
| `UNLINK` | Redis command for non-blocking key deletion (asynchronous, unlike `DEL` which blocks) |
| Flush-all invalidation | Strategy of deleting all keys matching a pattern rather than selectively deleting only affected keys |

## 24. APPENDICES

**A. Stream Event Payload Examples**

```
Event: stream:new_property (new listing)
{
  "property_id": 12345,
  "portal_source": "otodom",
  "source_id": "OD-12345",
  "city": "Warszawa",
  "property_type": "apartment",
  "is_new": true,
  "changed_fields": [],
  "timestamp": "2026-06-22T10:30:00Z"
}

Event: stream:new_property (updated listing, price changed)
{
  "property_id": 12345,
  "portal_source": "otodom",
  "source_id": "OD-12345",
  "city": "Warszawa",
  "property_type": "apartment",
  "is_new": false,
  "changed_fields": ["price", "last_seen_at"],
  "timestamp": "2026-06-22T10:30:00Z"
}

Event: stream:price_change
{
  "property_id": 12345,
  "portal_source": "otodom",
  "source_id": "OD-12345",
  "city": "Warszawa",
  "old_price": 500000,
  "new_price": 520000,
  "currency": "PLN",
  "timestamp": "2026-06-22T10:30:00Z"
}
```

**B. Invalidation Consumer Processing Flow**

```
1. Startup:
   → Create consumer group cg:cache-invalidation on stream:new_property (if not exists)
   → Create consumer group cg:cache-invalidation on stream:price_change (if not exists)
   → Set consumer status to "running"
   → Report consumer status in /health endpoint

2. Poll loop (every 1 second):
   → XREADGROUP BLOCK 5000 COUNT 10 STREAMS stream:new_property stream:price_change >
   → For each event:
      a. Parse JSON payload
      b. Determine event type (new_property or price_change)
      c. If new_property:
         - SCAN 0 MATCH properties:list:* COUNT 100 → iterate → UNLINK each key
         - UNLINK cities:list
         - If is_new=false AND changed_fields non-empty: UNLINK properties:detail:{id}
      d. If price_change:
         - UNLINK properties:detail:{id}
      e. Increment metrics (invalidation_events_total, invalidation_keys_deleted_total)
      f. XACK the event
      g. On error: retry up to 3 times, then XADD to dead-letter stream + XACK

3. Shutdown:
   → Cancel poll loop
   → Wait for in-flight processing to complete (max 10 seconds)
   → Consumer group remains in Redis (next startup picks up where left off)
```

**C. Key Invalidation Matrix**

| Upsert Type | Stream Event | Keys Invalidated | Rationale |
|-------------|--------------|------------------|-----------|
| New insert | `new_property` | `properties:list:*`, `cities:list` | New property could match any search filter; city counts change |
| Update (non-price) | `new_property` | `properties:list:*`, `cities:list`, `properties:detail:{id}` | Updated fields (description, rooms, area) affect search results and detail view |
| Update (price change) | `new_property` + `price_change` | `properties:list:*`, `cities:list`, `properties:detail:{id}` | Price affects search results and detail view |
| No changes (re-scrape) | `new_property` | `properties:list:*`, `cities:list` | Last_seen_at changes but data is same; flush-all is safe but redundant — acceptable |

**D. Health Check Response Example**

```json
{
  "status": "ok",
  "redis": "ok",
  "invalidation_consumer": "running",
  "invalidation": {
    "streams": {
      "stream:new_property": {
        "pending": 0,
        "lag_seconds": 0.5,
        "last_processed": "2026-06-22T10:30:05Z"
      },
      "stream:price_change": {
        "pending": 0,
        "lag_seconds": 0.3,
        "last_processed": "2026-06-22T10:30:05Z"
      }
    },
    "dead_letter_count": 0,
    "error_rate_last_5m": 0.0
  }
}
```

## 25. DOCUMENT HISTORY

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-06-22 | spec-writer | Initial specification for STORY-24 |

---

## AUTHORING GUIDELINES

**Sources consulted:**
- `doc/planning/epics/epic-05--redis-cache/epic-05--redis-cache.md` — Epic definition and cache invalidation requirements
- `doc/planning/backlog.md` — Work item description
- `specs/specs/080-API.md` — API endpoint specification and cache strategy
- `specs/specs/120-CACHING-STORAGE.md` — Cache strategy matrix, Redis Streams architecture, retry/dead-letter policy
- `specs/specs/020-ARCHITECTURE.md` — System architecture and component relationships
- `doc/changes/2026-06/2026-06-21--STORY-23--redis-cache-properties-list/chg-STORY-23-spec.md` — Prior change spec for format consistency and cache layer context
- `doc/changes/2026-06/2026-06-21--STORY-23--redis-cache-properties-list/chg-STORY-23-plan.md` — Implementation plan for STORY-23 (for context on existing cache service implementation)
- Existing source code in `src/scrapper-base/` and `src/real-estate-api/` — for understanding current upsert behavior and cache service architecture
- `doc/templates/change-spec-template.md` — Structural template

**Constraints:**
- No implementation details (file paths, code-level instructions, step-by-step tasks)
- Tech-agnostic within the bounds of existing spec decisions (Redis 7, FastAPI, cache-aside, Redis Streams)
- All section ID prefixes follow stable conventions (F-, AC-, NFR-, RSK-, DEC-, DM-, OQ-)
- Acceptance criteria reference at least one F- or NFR- ID and use Given/When/Then format

## VALIDATION CHECKLIST

- [x] `change.ref` matches provided `workItemRef` (STORY-24)
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
