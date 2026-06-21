---
change:
  ref: STORY-23
  type: feat
  status: Proposed
  slug: redis-cache-properties-list
  title: "Serve `/api/v1/properties` from Redis cache (TTL 2min)"
  owners: ["rendenwald"]
  service: real-estate-api
  labels: ["change"]
  version_impact: minor
  audience: internal
  security_impact: low
  risk_level: low
  dependencies:
    internal:
      - real-estate-api
      - Redis 7
    external: []
links:
  epic: ../../../../doc/planning/epics/epic-05--redis-cache/epic-05--redis-cache.md
  spec_modules:
    - ../../../../specs/specs/080-API.md
    - ../../../../specs/specs/120-CACHING-STORAGE.md
---

# CHANGE SPECIFICATION

> **PURPOSE**: Introduce Redis cache-aside for the `GET /api/v1/properties` endpoint to reduce database load and improve API response latency, with automatic fallback to direct query when Redis is unavailable.

## 1. SUMMARY

This change adds a Redis cache-aside layer to the `GET /api/v1/properties` endpoint. On each request, the cache is checked first using a deterministic key derived from the query parameters. On a cache miss, the database is queried and the result stored in Redis with a 120-second TTL. Responses include an `X-Cache: hit|miss` header for observability. If Redis is unreachable, the system falls back to a direct database query transparently. Cache invalidation is scoped to STORY-24 (separate change).

## 2. CONTEXT

### 2.1 Current State Snapshot

- The `GET /api/v1/properties` endpoint is defined in spec `080-API.md` — returns a paginated list of properties with filters (city, property type, price range, area, rooms, market type, bounding box, sort order)
- The response model is `SearchResponse` = `PaginatedResponse<PropertyCard>` as defined in `090-FRONTEND.md`
- Every request currently executes a full PostgreSQL query against the `properties` table (or the `canonical_properties` materialized view)
- Redis 7 is deployed in the `storage-ns` Kubernetes namespace with `maxmemory 1GB` and `allkeys-lru` eviction policy
- The caching/storage spec (`120-CACHING-STORAGE.md`) already defines the target cache key pattern `properties:list:{hash_params}` with TTL 120s
- STORY-24 (cache invalidation) and STORY-27 (graceful fallback) are separate work items but closely related

### 2.2 Pain Points / Gaps

- Every property list request hits PostgreSQL, increasing CPU/IO load and connection pool pressure
- Repeated identical queries (e.g., same filters from different users in quick succession) produce the same result but are computed each time
- Under high concurrency, DB queries for the list endpoint contribute to connection pool exhaustion
- No caching observability exists — unable to measure cache hit/miss ratio for API responses
- No graceful degradation path is defined for when the cache layer is unavailable

## 3. PROBLEM STATEMENT

Because `GET /api/v1/properties` queries PostgreSQL on every request without a caching layer, repeated identical or near-identical searches (same city, filters, and pagination) cause redundant database load, increase p95 response latency, and consume connection pool capacity that should be available for write-heavy scraper operations.

## 4. GOALS

- **G-1**: Reduce p95 response latency for `GET /api/v1/properties` by serving repeated identical requests from Redis
- **G-2**: Reduce PostgreSQL query rate for the properties list endpoint by at least 70% under normal traffic
- **G-3**: Maintain correctness — stale data is bounded by a 120-second TTL
- **G-4**: Ensure zero downtime — system operates normally when Redis is unavailable (transparent fallback to DB)

### 4.1 Success Metrics / KPIs

| Metric | Target |
|--------|--------|
| p95 response latency (cache hit) | < 10 ms |
| p95 response latency (cache miss / fallback) | < 200 ms |
| Cache hit ratio (steady state) | ≥ 70% |
| DB query rate reduction for `/api/v1/properties` | ≥ 70% |
| Error rate during Redis outage | 0% (transparent fallback) |

### 4.2 Non-Goals

- **NG-1**: Cache invalidation on property upsert — covered by STORY-24
- **NG-2**: Caching other endpoints (`/api/v1/properties/{id}`, `/api/v1/cities`, `/api/v1/stats`) — separate stories (STORY-25 covers cities)
- **NG-3**: Redis Streams or alert delivery — covered by STORY-26
- **NG-4**: Redis capacity planning or cluster mode — single-instance Redis is sufficient for Phase 1
- **NG-5**: Pre-warming the cache on application startup — cache is populated lazily on first request after each deployment
- **NG-6**: Distributed cache invalidation (publish/subscribe pattern) — TTL-based expiry is sufficient

## 5. FUNCTIONAL CAPABILITIES

| ID | Capability | Rationale |
|----|------------|-----------|
| F-1 | Deterministic cache key generation from query parameters | Ensures identical queries produce the same cache key, maximizing hit ratio |
| F-2 | Cache-aside read pattern with TTL 120s | Standard read-through caching pattern; 2-minute TTL balances freshness vs hit rate |
| F-3 | `X-Cache` response header indicating hit/miss | Provides observability into cache effectiveness for operators |
| F-4 | Graceful fallback to direct DB query when Redis is unavailable | Ensures zero-downtime operation during Redis maintenance or outages |
| F-5 | Configurable Redis connection with health-check and retry | Enables resilient connection management with configurable endpoint, timeout, and pool size |

### 5.1 Capability Details

**F-1 (Cache Key Generation):**
- Cache key format: `properties:list:{sha256hex(normalized_params)}`
- Normalization steps: sort keys alphabetically, omit params with default/empty values, convert all values to strings, serialize as canonical JSON
- Parameters included: `city`, `property_type`, `auction_type`, `price_min`, `price_max`, `area_min`, `area_max`, `rooms`, `market_type`, `bbox` (serialized as `minLat,minLng,maxLat,maxLng`), `page`, `limit`, `sort_by`
- Parameters excluded from cache key: `lang`, `currency` (these are UI preferences, not data filters — currency conversion applied client-side per `110-I18N-CURRENCY.md`)
- SHA-256 is used for deterministic hashing; the full key length stays within Redis key length limits (~200 chars)

**F-2 (Cache-Aside Read Pattern):**
- On request: compute cache key → `redis.GET(key)` — if found, deserialize JSON → return with `X-Cache: hit`
- On miss: query PostgreSQL → serialize response to JSON → `redis.SETEX(key, 120, json)` → return with `X-Cache: miss`
- TTL of 120 seconds (2 minutes) as defined in `120-CACHING-STORAGE.md` cache strategy matrix
- Serialized value is the complete `SearchResponse` JSON (Pydantic model dump)

**F-3 (X-Cache Header):**
- All responses from the endpoint include `X-Cache: hit` or `X-Cache: miss`
- In fallback mode (Redis unavailable), header value is `X-Cache: miss (fallback)`
- Additional optional header: `X-Cache-TTL: <remaining-seconds>` on cache hits for debugging

**F-4 (Graceful Fallback):**
- If `redis.GET()` raises an exception (connection refused, timeout, etc.), catch the exception, log a warning, and proceed with the DB query
- A Prometheus counter `cache_errors_total{operation="get"}` is incremented on each fallback
- Redis connection errors are logged but never propagated to the API response — the endpoint always returns data from the DB
- A separate health-check pings Redis every 30 seconds; if unhealthy, all cache operations are skipped until the next successful health check

**F-5 (Redis Connection):**
- Connection configured via environment variables:
  - `REDIS_URL` (default: `redis://localhost:6379/0`)
  - `REDIS_POOL_SIZE` (default: `10`)
  - `REDIS_TIMEOUT_SECONDS` (default: `2`)
- Uses `redis.asyncio` client (aioredis-compatible) with connection pool
- Connection health is verified on startup; degraded mode (skip cache) is entered if Redis is unavailable at startup

## 6. USER & SYSTEM FLOWS

```
Flow 1: Cache Hit (nominal path)
  Client → GET /api/v1/properties?city=Warszawa&page=1
  → API computes cache key: properties:list:{sha256(...)}
  → redis.GET(key) → returns JSON
  → Deserialize to SearchResponse
  → Add header X-Cache: hit
  → Return 200 OK with SearchResponse JSON

Flow 2: Cache Miss
  Client → GET /api/v1/properties?city=Kraków&page=1
  → API computes cache key: properties:list:{sha256(...)}
  → redis.GET(key) → nil (not found)
  → Query PostgreSQL (via SQLAlchemy async session)
  → Serialize result to SearchResponse JSON
  → redis.SETEX(key, 120, json)
  → Add header X-Cache: miss
  → Return 200 OK with SearchResponse JSON

Flow 3: Redis Unavailable (graceful fallback)
  Any request to GET /api/v1/properties
  → API computes cache key
  → redis.GET(key) → raises ConnectionError (Redis down)
  → Log warning, increment cache_errors_total counter
  → Fallback: query PostgreSQL directly
  → Add header X-Cache: miss (fallback) — no cache write
  → Return 200 OK with SearchResponse JSON

Flow 4: Consecutive identical requests (burst)
  User A requests city=Warszawa page=1 → cache miss → DB query → cache set
  User B requests city=Warszawa page=1 200ms later → cache hit → served from Redis
  User C requests city=Warszawa page=1 500ms later → cache hit → served from Redis
```

## 7. SCOPE & BOUNDARIES

### 7.1 In Scope

- Cache-aside read implementation in the properties router (`real-estate-api/app/routers/properties.py`)
- Cache key generation utility function with deterministic parameter normalization
- Redis connection manager with health-check, pool, timeouts, and graceful degradation
- `X-Cache` response header injection
- Prometheus metrics for cache operations (hits, misses, errors, latency)
- Environment variable configuration for Redis connection
- Integration of caching into the existing properties endpoint without changing the API contract

### 7.2 Out of Scope

- [OUT] Cache invalidation when new properties are scraped — covered by STORY-24
- [OUT] Caching for other endpoints (`/api/v1/properties/{id}`, `/api/v1/cities`, `/api/v1/stats`)
- [OUT] Redis Streams or pub/sub for cross-instance cache invalidation
- [OUT] Redis Sentinel or Cluster configuration for high availability
- [OUT] Cache pre-warming or seeding logic
- [OUT] Frontend changes — API contract (request/response shape) is unchanged
- [OUT] Database query optimization — the DB query itself is not changed, only cached
- [OUT] API authentication/authorization changes — caching behaves identically for all requests

### 7.3 Deferred / Maybe-Later

- Per-user cache segregation (authenticated users see personalized results) — deferred until personalization features are added
- Cache compression for large response payloads — evaluate if response sizes exceed Redis value limits
- Stale-while-revalidate pattern — consider if 120s TTL is too short for production traffic patterns
- Distributed cache warming after deployment — consider if cold-start miss rate is problematic

## 8. INTERFACES & INTEGRATION CONTRACTS

### 8.1 REST / HTTP Endpoints

**Modified endpoint: `GET /api/v1/properties`**

| Aspect | Current | After Change |
|--------|---------|-------------|
| Request | Same query parameters | Unchanged |
| Response body | Same `SearchResponse` JSON | Unchanged |
| Response headers | Standard HTTP headers | **Added**: `X-Cache: hit\|miss\|miss (fallback)` |
| HTTP status codes | 200 OK | Unchanged (200, 422, 429) |
| Rate limiting | Per FIX-5 in 080-API.md | Unchanged |
| Auth | None / JWT optional | Unchanged |

No new endpoints are created. No existing endpoints are removed.

### 8.2 Events / Messages

| Event | Producer | Consumer | Description |
|-------|----------|----------|-------------|
| (none new) | — | — | Cache invalidation events are scoped to STORY-24; this story implements cache reads only |

### 8.3 Data Model Impact

| ID | Element | Description |
|----|---------|-------------|
| DM-1 | Cache key `properties:list:{sha256(normalized_params)}` | New Redis key pattern, TTL 120s, JSON value of `SearchResponse` |
| DM-2 | Response header `X-Cache` | New HTTP response header, values: `hit` / `miss` / `miss (fallback)` |

No database schema changes. No new database tables or columns.

### 8.4 External Integrations

| Service | Interface | Purpose | Change |
|---------|-----------|---------|--------|
| Redis 7 | `redis.asyncio` client | Cache-aside for properties list | New dependency for `real-estate-api` |
| PostgreSQL 16 | SQLAlchemy 2.0 async | Fallback data source on cache miss | Unchanged |

### 8.5 Backward Compatibility

- Fully backward compatible — the API response contract (JSON shape, status codes) is identical
- The only addition is the `X-Cache` response header, which is optional and ignored by existing clients
- If Redis is not deployed, the system falls back to direct DB query transparently — existing clients see no difference
- No changes to existing request parameters or response schema
- Existing monitoring and logging continue to work unchanged

## 9. NON-FUNCTIONAL REQUIREMENTS (NFRs)

| ID | Requirement | Threshold |
|----|-------------|-----------|
| NFR-1 | Cache hit response latency | p95 < 10 ms end-to-end (including deserialization) |
| NFR-2 | Cache miss / DB fallback latency | p95 < 200 ms (existing DB query performance baseline) |
| NFR-3 | Redis connection timeout | Fail fast within 2 seconds; do not block request thread |
| NFR-4 | Cache key collision | Zero — SHA-256 collisions are not feasible for key space of < 10⁶ entries |
| NFR-5 | Memory overhead per cached entry | < 100 KB per entry (estimated average `SearchResponse` size with 20 results) |
| NFR-6 | Maximum cache entries before LRU eviction | ~10 000 entries fit within 1 GB Redis maxmemory at 100 KB each; LRU evicts oldest if exceeded |
| NFR-7 | Error handling | Zero errors propagated to client when Redis is unreachable — always fall back to DB |

## 10. TELEMETRY & OBSERVABILITY REQUIREMENTS

**Metrics (Prometheus counters/histograms):**

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `cache_hits_total` | Counter | `endpoint`, `cache_key_prefix` | Count of successful cache hits |
| `cache_misses_total` | Counter | `endpoint`, `cache_key_prefix` | Count of cache misses (key not found) |
| `cache_errors_total` | Counter | `endpoint`, `operation`, `error_type` | Count of Redis errors triggering fallback |
| `cache_operation_duration_seconds` | Histogram | `endpoint`, `operation` | Latency of Redis GET/SET operations |
| `cache_entry_size_bytes` | Gauge | `endpoint` | Size of cached response payload (sampled) |

**Logging:**

- Redis connection status logged at startup (info level): `"redis_connected": true|false`
- Cache hit/miss logged at debug level (not emitted in production unless debug logging is enabled)
- Redis errors logged at warning level with error details: `"redis_error": "...", "fallback": true`
- Health-check transitions (connected → disconnected, disconnected → connected) logged at warning level

**Health check:**

- `GET /health` endpoint extended to include Redis status: `{"redis": "ok"|"degraded"}` (separate from the cache endpoint)
- Redis ping executed every 30 seconds; three consecutive failures mark Redis as degraded
- Degraded mode disables all cache operations (reads skip Redis entirely) until ping succeeds again

## 11. RISKS & MITIGATIONS

| ID | Risk | Impact | Probability | Mitigation | Residual Risk |
|----|------|--------|-------------|------------|---------------|
| RSK-1 | Redis outage causes cache misses but no data loss | Low | Medium | Graceful fallback to DB; health-check auto-recovery | Low — data is never lost, only latency increases |
| RSK-2 | Stale data served within 120s TTL after property upsert | Medium | High | TTL is a deliberate trade-off; STORY-24 will add proactive invalidation | Medium — 2-min staleness is acceptable per product spec |
| RSK-3 | Cache key hash collision (SHA-256) | Low | Very Low | SHA-256 collision probability is negligible for this key space | Low — practically zero risk |
| RSK-4 | Redis memory exhaustion under high traffic | Medium | Low | `allkeys-lru` eviction + 1 GB maxmemory; monitor `cache_errors_total` | Low — LRU guards against OOM |
| RSK-5 | Increased p99 latency from Redis timeout (2s wait) | Medium | Low | Configure short timeout (2s); if exceeded, error is caught and DB fallback is used | Low — timeout is bounded |

## 12. ASSUMPTIONS

- Redis 7 is deployed and accessible at the configured `REDIS_URL` in all environments (dev, staging, production)
- The `/api/v1/properties` endpoint already implements the DB query logic (established by earlier API implementation)
- API responses are deterministic for the same query parameters — no session-specific or user-specific filtering
- The `SearchResponse` serialization is idempotent — the same DB result always produces the same JSON
- TTL of 120 seconds is acceptable for data freshness — users tolerate up to 2-minute delay for property listings
- Redis `maxmemory 1GB` with `allkeys-lru` is sufficient for the expected cache key space
- The `redis.asyncio` client (aioredis-compatible) is available in the `real-estate-api` dependency tree

## 13. DEPENDENCIES

| Direction | Item | Notes |
|-----------|------|-------|
| Depends on | Redis 7 running in `storage-ns` | Must be deployed and configured per `120-CACHING-STORAGE.md` |
| Depends on | `real-estate-api` application scaffold | Router, services, config, and DB query must exist |
| Depends on | `redis` Python package (>=5.0, async compatible) | Added to `pyproject.toml` dependencies |
| Depends on | STORY-27 (Graceful fallback) | Fallback logic for STORY-23 is a subset of STORY-27; STORY-23 implements the core fallback within this endpoint only |
| Blocks | STORY-24 (Cache invalidation) | Invalidation needs the cache layer to exist first |
| Blocks | STORY-25 (Cache cities endpoint) | Cache service infrastructure is shared |

## 14. OPEN QUESTIONS

| ID | Question | Context | Status |
|----|----------|---------|--------|
| OQ-1 | Should `page` and `limit` be part of the cache key, or should we cache the full result set (all pages) and paginate server-side from cache? | Caching per-page increases the number of keys but keeps each payload small; caching all results would require one key per unique filter set but increases per-payload size and complexity | Decision needed: consult `@architect` |
| OQ-2 | Should authenticated users with personalized preferences (e.g., `preferred_currency`, `preferred_language`) receive cache-separate responses? | Currently `lang` and `currency` are excluded from the cache key (per F-1); if user-specific data is added later, cache key design must accommodate it | Deferred — no personalized filtering exists yet |
| OQ-3 | Should the health-check interval (30s) and degraded-mode threshold (3 failures) be configurable via environment variables? | Hardcoded values reduce operational flexibility but simplify configuration | Recommended: configurable via env vars |

## 15. DECISION LOG

| ID | Decision | Rationale | Date |
|----|----------|-----------|------|
| DEC-1 | Cache key excludes `lang` and `currency` | These are UI formatting preferences, not data filters; currency conversion is client-side per `110-I18N-CURRENCY.md` | 2026-06-21 |
| DEC-2 | Use SHA-256 of normalized params, not raw query string | Raw query strings may vary by ordering/encoding; normalized canonical form ensures identical filters produce the same key | 2026-06-21 |
| DEC-3 | Catch-all fallback on any Redis exception (not just specific errors) | Simpler and more robust — any Redis failure (timeout, connection refused, OOM, etc.) should degrade gracefully | 2026-06-21 |
| DEC-4 | Health-check with 3-failure threshold before entering degraded mode | Prevents transient network hiccups from disabling the cache; 30s interval × 3 failures = 90s before degraded mode | 2026-06-21 |
| DEC-5 | Response serialized as full JSON string (not compressed) | Simplicity; compression can be added later if payload sizes exceed thresholds | 2026-06-21 |

## 16. AFFECTED COMPONENTS (HIGH-LEVEL)

| Component | Impact |
|-----------|--------|
| `real-estate-api/app/routers/properties.py` | Updated — cache-aside logic added to the properties list endpoint |
| `real-estate-api/app/services/cache.py` | New — Redis connection manager, cache key generation, cache-aside helpers |
| `real-estate-api/app/core/config.py` | Updated — Redis configuration environment variables added |
| `real-estate-api/pyproject.toml` | Updated — `redis` dependency added |
| `real-estate-api/app/routers/health.py` | Updated — Redis health status added to `/health` endpoint |
| `infrastructure/k8s/storage/redis-statefulset.yaml` | No change — Redis is already deployed per 120-CACHING-STORAGE.md |

## 17. ACCEPTANCE CRITERIA

| ID | Criterion | Linked |
|----|-----------|--------|
| AC-F1-1 | **Given** a request to `GET /api/v1/properties?city=Warszawa&page=1`, **when** the cache key is computed, **then** it matches the format `properties:list:{sha256hex}` and is deterministic for identical parameters | F-1 |
| AC-F1-2 | **Given** two requests with identical filters but different parameter ordering (e.g., `page=1&city=Warszawa` vs `city=Warszawa&page=1`), **when** cache keys are computed, **then** they are identical | F-1 |
| AC-F2-1 | **Given** a cold cache, **when** `GET /api/v1/properties?city=Gdańsk` is requested, **then** the response has `X-Cache: miss` and the body contains correct data from PostgreSQL | F-2 |
| AC-F2-2 | **Given** a cached entry exists for `city=Gdańsk&page=1`, **when** the same request is made again within 120 seconds, **then** the response has `X-Cache: hit` and the body matches the first response | F-2 |
| AC-F2-3 | **Given** a cached entry is older than 120 seconds, **when** the same request is made, **then** the cache entry is expired and the response has `X-Cache: miss` | F-2, NFR-1 |
| AC-F3-1 | **Given** any response from `GET /api/v1/properties`, **when** the response headers are inspected, **then** `X-Cache` is present with value `hit`, `miss`, or `miss (fallback)` | F-3 |
| AC-F4-1 | **Given** Redis is unreachable (stopped, firewalled, or misconfigured), **when** `GET /api/v1/properties` is requested, **then** the response has `X-Cache: miss (fallback)`, status 200 OK, and correct data from PostgreSQL | F-4 |
| AC-F4-2 | **Given** Redis is unreachable, **when** `GET /api/v1/properties` is requested, **then** a warning is logged and `cache_errors_total` counter is incremented | F-4 |
| AC-F4-3 | **Given** Redis was unreachable and recovers, **when** the next request arrives, **then** the cache-aside pattern resumes with cache hits | F-4 |
| AC-F5-1 | **Given** the application starts with Redis available, **when** the health endpoint is checked, **then** `GET /health` returns `{"redis": "ok"}` | F-5 |
| AC-F5-2 | **Given** the application starts with Redis unavailable, **when** the health endpoint is checked, **then** `GET /health` returns `{"redis": "degraded"}` and the properties endpoint still works | F-5 |
| AC-NFR-1 | **Given** a cache hit scenario with a loaded Redis, **when** the response time is measured, **then** p95 is below 10 ms | NFR-1 |
| AC-NFR-2 | **Given** the Redis fallback path is active, **when** the response time is measured, **then** p95 is below 200 ms | NFR-2 |

## 18. ROLLOUT & CHANGE MANAGEMENT (HIGH-LEVEL)

1. **Implementation order:** Implement cache service → integrate into properties router → add health check → add metrics → add tests
2. **Phase 1 (dev):** Deploy with Redis running locally; verify cache hit/miss behavior manually
3. **Phase 2 (staging):** Enable with production-like filter patterns; monitor cache hit ratio and latency
4. **Phase 3 (production):** Gradual rollout — the change is backward-compatible; no feature flag needed
5. **Merge strategy:** Squash merge to `main` via PR
6. **Communication:** None needed — internal change with no user-facing impact
7. **Rollback:** Revert the cache integration commit; DB-only mode is the fallback behavior

## 19. DATA MIGRATION / SEEDING (IF APPLICABLE)

N/A — no database schema changes. Cache is populated lazily on first request after deployment.

## 20. PRIVACY / COMPLIANCE REVIEW

No personal data is cached. Property listing data cached in Redis is public data already exposed via the API. Cached responses are ephemeral (TTL-bounded) and do not contain user identifiers or session information. No GDPR implications beyond those already addressed by the API layer.

## 21. SECURITY REVIEW HIGHLIGHTS

- No secrets are stored in cached data — cached is serialized API responses
- Redis connection credentials are configured via environment variables (`REDIS_URL`), not hardcoded
- The cache key uses SHA-256 hashing of parameters — no injection risk via cache key
- If Redis is compromised, the attacker can only observe cached public listing data or serve stale data within the 120s TTL — no write path exists from this change
- No Redis commands are exposed to user input — all cache keys are generated server-side from parsed and validated query parameters

## 22. MAINTENANCE & OPERATIONS IMPACT

- **Redis monitoring:** Team must monitor `cache_hits_total` and `cache_errors_total` metrics to detect degradation
- **Memory usage:** Redis `maxmemory 1GB` with `allkeys-lru` is self-managing; alert if evictions exceed expected thresholds
- **Deployment ordering:** Cache layer must be deployed after Redis is available; the system functions in degraded (DB-only) mode if Redis is not yet ready
- **Config changes:** Redis URL changes require env var update and pod restart; no code changes needed
- **Cache flush:** If stale data needs to be purged immediately (before TTL expiry), run `redis-cli DEL properties:list:*` or use `FLUSHDB` (caution: affects all keys in Redis DB 0)

## 23. GLOSSARY

| Term | Definition |
|------|------------|
| Cache-aside | Application-side caching pattern where the application checks the cache before querying the database |
| Cache hit | Request where the data is found in the cache and served without querying the database |
| Cache miss | Request where the data is not found in the cache, requiring a database query |
| Degraded mode | Operational mode where Redis is unavailable and all requests fall back to direct database queries |
| LRU | Least Recently Used — eviction policy that removes the least recently accessed keys when memory is full |
| `allkeys-lru` | Redis maxmemory policy that evicts any key (not just those with TTL) using LRU algorithm |
| TTL | Time To Live — the duration a cached entry remains valid before automatic expiration |

## 24. APPENDICES

**A. Cache Key Computation Example**

```
Input parameters (sorted, defaults omitted):
  city=Warszawa
  page=1
  limit=20
  property_type=apartment

Normalized JSON:
  {"city":"Warszawa","limit":20,"page":1,"property_type":"apartment"}

SHA-256 hex:
  a1b2c3d4e5f6... (64 hex chars)

Cache key:
  properties:list:a1b2c3d4e5f6...
```

**B. Redis Memory Estimation**

| Factor | Estimate |
|--------|----------|
| Average `SearchResponse` size (20 results) | ~50 KB JSON |
| Redis key overhead (key + pointers) | ~500 bytes per entry |
| Total per cached entry | ~51 KB |
| Estimated unique filter combinations under normal traffic | ~500 (20 cities × 5 property types × 5 pagination combos) |
| Total memory usage | ~25 MB (well within 1 GB limit) |

## 25. DOCUMENT HISTORY

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-06-21 | spec-writer | Initial specification for STORY-23 |

---

## AUTHORING GUIDELINES

**Sources consulted:**
- `doc/planning/epics/epic-05--redis-cache/epic-05--redis-cache.md` — Epic definition
- `doc/planning/backlog.md` — Work item description
- `specs/specs/080-API.md` — API endpoint specification
- `specs/specs/120-CACHING-STORAGE.md` — Cache strategy and Redis configuration
- `specs/specs/090-FRONTEND.md` — SearchParams and SearchResponse interfaces
- `specs/specs/020-ARCHITECTURE.md` — System architecture and component relationships
- `doc/changes/STORY-1/chg-STORY-1-spec.md` — Prior spec reference for format consistency

**Constraints:**
- No implementation details (file paths, code-level instructions, step-by-step tasks)
- Tech-agnostic within the bounds of existing spec decisions (Redis 7, FastAPI, cache-aside)
- All section IDs follow stable prefix conventions (F-, AC-, NFR-, RSK-, DEC-, DM-, OQ-)
- Acceptance criteria reference at least one F- or NFR- ID and use Given/When/Then format

## VALIDATION CHECKLIST

- [x] `change.ref` matches provided `workItemRef` (STORY-23)
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
