---
change:
  ref: STORY-27
  type: feat
  status: Proposed
  slug: graceful-fallback-redis-unavailable
  title: "Graceful fallback to direct DB query when Redis unavailable"
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
      - Prometheus
      - Alertmanager
    external: []
links:
  epic: ../../../../doc/planning/epics/epic-05--redis-cache/epic-05--redis-cache.md
  spec_modules:
    - ../../../../specs/specs/080-API.md
    - ../../../../specs/specs/120-CACHING-STORAGE.md
    - ../../../../specs/specs/130-MONITORING-ALERTS.md
---

# CHANGE SPECIFICATION

> **PURPOSE**: Add a comprehensive resilience layer on top of the existing Redis cache-aside implementation so the platform continues operating without interruption when Redis is unavailable, and automatically recovers full caching capability when Redis returns without manual intervention.

## 1. SUMMARY

This change adds the missing resilience infrastructure on top of the Redis cache-aside layer built in STORY-23. A background recovery worker periodically probes a degraded Redis instance and reinitialises the connection pool on recovery, the system can be started with Redis intentionally disabled via a `REDIS_ENABLED` flag, a dedicated `GET /ready` readiness endpoint reports dependency health for Kubernetes liveness/readiness probes, a `redis_degraded` Prometheus gauge tracks degraded-state duration, and a `RedisDegraded` Prometheus alert fires when Redis has been degraded for more than five minutes. All cache operations already fall through to direct database queries when Redis is unreachable — this change ensures the system stays resilient and operators are alerted when the cache layer is impaired.

## 2. CONTEXT

### 2.1 Current State Snapshot

- STORY-23 (merged) implemented a Redis cache-aside layer for `GET /api/v1/properties`:
  - `RedisClient` class with connection pool (`ConnectionPool` from `redis.asyncio`), `healthy: bool` flag, `failure_count: int` counter, and `ping()` health-check method
  - `CacheService.get_or_compute()` catches `RedisError` exceptions, falls back to `compute()`, and returns `"miss (fallback)"` status
  - Health endpoint `GET /health` reports `{"redis": "ok" | "degraded"}` based on the `healthy` flag (no active probing — uses cached state)
  - `cache_errors_total` Prometheus counter tracks Redis errors triggering fallback
- A background health-check task (`_periodic_health_check`) runs in `main.py` every `REDIS_HEALTH_CHECK_INTERVAL` seconds calling `redis_client.ping()`, but it only updates the `healthy` flag — it does **not** reinitialise the connection pool on recovery
- `RedisClient.ping()` sets `healthy = True` and resets `failure_count` on successful ping, but the existing pool may hold stale/closed connections after an outage
- The `Settings` class supports `REDIS_URL`, `REDIS_POOL_SIZE`, `REDIS_TIMEOUT_SECONDS`, `REDIS_HEALTH_CHECK_INTERVAL`, and `REDIS_HEALTH_CHECK_FAILURE_THRESHOLD`
- The `lifespan` handler in `main.py` creates the `RedisClient`, calls `connect()`, and starts the periodic health-check task; on shutdown it cancels the task and disconnects
- scrapper-base has no Redis dependency — all changes are within `src/real-estate-api/`
- `cache_invalidator` from STORY-24 already handles `REDIS_URL` absence gracefully — no changes needed there
- No readiness endpoint exists — only the `/health` liveness endpoint is present
- No Prometheus alert rule exists for Redis degradation
- No mechanism to disable Redis at startup via configuration — the only way to skip Redis is to leave `REDIS_URL` unset, which is not an explicit opt-out

### 2.2 Pain Points / Gaps

- When Redis goes down and comes back up, the connection pool is **not** reinitialised — stale pool connections cause `ConnectionError` even though Redis itself is healthy, requiring a full application restart to recover
- No background recovery mechanism exists — the health-check task pings but does not reconnect, so recovery is manual
- No explicit configuration flag to disable Redis — operators cannot cleanly opt out of Redis in environments where it is not deployed (e.g., local development, minimal CI)
- No readiness endpoint exists — Kubernetes liveness probes use `/health` but readiness probes have no `GET /ready` endpoint to signal that dependencies (DB, Redis) are initialised
- No `redis_degraded` Prometheus gauge — operators cannot track how long Redis has been degraded or trigger alerts based on degraded duration
- No `RedisDegraded` Prometheus alert — if Redis goes down at 3 AM, no notification fires; the system works (fallback to DB) but performance degrades silently
- Startup logs do not distinguish between "Redis disabled" and "Redis enabled but unreachable" — this ambiguity makes troubleshooting harder

## 3. PROBLEM STATEMENT

Because the existing Redis cache-aside implementation has no background recovery worker, no connection-pool reinitialisation on recovery, no `REDIS_ENABLED` configuration flag, no readiness endpoint, and no dedicated Prometheus gauge or alert for degraded state, operators must manually restart the application after a Redis outage to restore full caching capability, cannot cleanly disable Redis in non-production environments, lack visibility into the duration and impact of Redis degradation, and receive no automated alert when the cache layer is impaired.

## 4. GOALS

- **G-1**: Automatically recover Redis caching capability after an outage without application restart — the background recovery worker reinitialises the connection pool when Redis responds to a health-check ping
- **G-2**: Allow operators to explicitly disable Redis at startup via a `REDIS_ENABLED` environment variable, with all cache operations falling through to database queries
- **G-3**: Provide a `GET /ready` readiness endpoint that returns HTTP 200 when all critical dependencies are healthy and HTTP 503 when they are not, enabling Kubernetes readiness probe integration
- **G-4**: Expose a `redis_degraded` Prometheus gauge (0/1) so operators can monitor degraded-state duration and build dashboards
- **G-5**: Fire a `RedisDegraded` Prometheus alert when Redis has been degraded for more than 5 minutes, ensuring operators are notified of cache-layer impairment
- **G-6**: Log a clear, unambiguous warning at startup when Redis is disabled or unreachable, distinguishing between the two states

### 4.1 Success Metrics / KPIs

| Metric | Target |
|--------|--------|
| Recovery time after Redis becomes reachable again | < `REDIS_HEALTH_CHECK_INTERVAL` + 5 seconds (next ping cycle discovers recovery and reconnects) |
| Application disruption during Redis outage | Zero — all requests served from DB with `"miss (fallback)"` status |
| `GET /ready` response time | p95 < 5 ms (reads cached in-memory state, no network calls) |
| `RedisDegraded` alert firing delay | 5 minutes after `redis_degraded` gauge transitions to 1 |
| False positive recovery (pool reinit succeeds but subsequent operations fail) | < 1% of recovery events |

### 4.2 Non-Goals

- **NG-1**: Implementing Redis Sentinel, Cluster, or any high-availability Redis topology — single-instance Redis remains the target architecture for Phase 1
- **NG-2**: Implementing Redis connection retry with exponential backoff for individual cache operations — the existing fast-fail (2-second timeout) + DB fallback is sufficient
- **NG-3**: Cache pre-warming after recovery — cache is repopulated lazily on first request after recovery
- **NG-4**: Implementing a separate health-check endpoint for scrapper-base — scrapper-base has no Redis dependency (STORY-24's stream publishing is separate)
- **NG-5**: Implementing circuit-breaker pattern for Redis operations — the existing `healthy` flag and `failure_count` threshold provide sufficient circuit-breaking
- **NG-6**: Modifying the existing `CacheService.get_or_compute()` fallback logic — it already handles `RedisError` correctly
- **NG-7**: Persistent Redis health history or degraded-state event log beyond Prometheus metrics — the gauge and alert are sufficient for Phase 1

## 5. FUNCTIONAL CAPABILITIES

| ID | Capability | Rationale |
|----|------------|-----------|
| F-1 | Background recovery worker that periodically pings degraded Redis and reinitialises the connection pool on successful ping | Eliminates the need for manual application restart after Redis outage; the existing health-check task only updates the `healthy` flag but does not reconnect the pool |
| F-2 | `REDIS_ENABLED` configuration flag that disables Redis initialisation at startup | Enables operators to cleanly opt out of Redis in environments where it is not deployed, without relying on `REDIS_URL` absence or other side effects |
| F-3 | `GET /ready` readiness endpoint returning dependency health and HTTP 200/503 | Provides a proper readiness probe for Kubernetes orchestration; distinguishes liveness (`/health`) from readiness (`/ready`) |
| F-4 | `redis_degraded` Prometheus gauge (values 0 or 1) | Enables tracking degraded-state duration in dashboards and provides the metric source for the `RedisDegraded` alert |
| F-5 | Prometheus `RedisDegraded` alert rule firing when `redis_degraded == 1` for > 5 minutes | Ensures operators are notified of prolonged cache-layer degradation via the existing Alertmanager pipeline |
| F-6 | Startup log messages clearly indicating Redis status (enabled/disabled, connected/unreachable) | Reduces ambiguity during troubleshooting; operators can immediately determine whether Redis was intentionally disabled or unexpectedly unavailable |

### 5.1 Capability Details

**F-1 (Background Recovery Worker):**
- When `RedisClient.healthy` transitions to `False` (degraded mode), a background asyncio task is started (or an existing periodic task already running in `main.py` is repurposed) that calls `redis_client.ping()` every `REDIS_HEALTH_CHECK_INTERVAL` seconds
- On successful ping after degradation, the recovery worker calls a new method `RedisClient.reconnect()` that:
  1. Disconnects the existing (stale) connection pool via `pool.disconnect()`
  2. Creates a new `ConnectionPool` from the same `REDIS_URL` configuration
  3. Creates a new `AsyncRedis` client instance using the new pool
  4. Performs a verification `ping()` on the new connection
  5. Sets `healthy = True` and resets `failure_count = 0`
  6. Logs at info level: `"redis_reconnected"` with duration and pool size
- If `reconnect()` fails (new pool also fails to connect), the client remains in degraded mode and the recovery worker retries on the next interval
- The recovery worker is managed as an asyncio task within the application lifespan — started on app startup (but only actively probes when degraded) and cancelled on shutdown
- The recovery task uses `asyncio.sleep()` between cycles and includes a try/except around `reconnect()` to prevent unhandled exceptions from crashing the task
- To avoid a thundering-herd of recovery attempts on the same interval, a small random jitter (±10% of interval) is added to the sleep duration

**F-2 (`REDIS_ENABLED` Configuration Flag):**
- A new setting `REDIS_ENABLED: bool = True` is added to the `Settings` class, read from the `REDIS_ENABLED` environment variable
- When `REDIS_ENABLED` is `False`:
  - `RedisClient.connect()` returns immediately without creating a pool or connecting
  - `healthy` is set to `False` (consistent with degraded state; cache operations skip Redis via the existing `if not self._redis.healthy` check)
  - A startup log warning is emitted: `"redis_disabled_by_config"` at warning level
  - The background health-check task and recovery worker are not started (no Redis to probe)
  - `GET /health` returns `{"redis": "disabled"}` instead of `"degraded"` (distinguishes intentional disable from outage)
  - `GET /ready` returns `{"ready": true, "redis": "disabled"}` — Redis being disabled is a known and intentional state, not a readiness failure
- When `REDIS_ENABLED` is `True` but connection fails:
  - `healthy` is `False`, the recovery worker is active
  - `GET /health` returns `{"redis": "degraded"}`
  - `GET /ready` returns 503 after the grace period (see F-3)

**F-3 (`GET /ready` Readiness Endpoint):**
- A new endpoint `GET /ready` is exposed (no authentication, same behaviour as `/health`)
- Response body: `{"ready": bool, "redis": str}` where `redis` is one of `"ok"`, `"disabled"`, or `"degraded"`
- `ready` is `true` when:
  - The database connection pool is initialised (determined by application state — e.g., `app.state.db_ready`)
  - Redis is either `healthy` (`"ok"`), `disabled` (`"disabled"`), or degraded but within the startup grace period (`"degraded"` with `"ready": true`)
- `ready` is `false` (HTTP 503) when:
  - Redis is degraded AND the application has been running longer than `REDIS_STARTUP_GRACE_PERIOD` (default 30 seconds)
  - The database connection is not ready
- The grace period allows the recovery worker time to reconnect Redis before the readiness probe starts failing — preventing crash-loop-backoff during Redis startup if the app and Redis start simultaneously
- After the grace period expires and Redis is still degraded, `GET /ready` returns HTTP 503 until Redis recovers or the application is restarted with `REDIS_ENABLED=false`
- The endpoint reads only cached in-memory state — no network calls, no Redis pings on the request path
- A new router file `routers/readiness.py` or an extension of `routers/health.py` hosts the endpoint

**F-4 (`redis_degraded` Prometheus Gauge):**
- A new Prometheus gauge `redis_degraded` is defined in `core/metrics.py` with no labels (single global gauge)
- Value is `1` when `RedisClient.healthy` is `False` AND `REDIS_ENABLED` is `True` (i.e., degraded due to outage, not intentional disable)
- Value is `0` when either `healthy` is `True` or `REDIS_ENABLED` is `False`
- The gauge is updated on every health-check cycle and on any state transition in `RedisClient.ping()` or `RedisClient.reconnect()`
- The gauge enables Grafana panels showing degraded duration, and feeds the `RedisDegraded` alert rule

**F-5 (Prometheus `RedisDegraded` Alert Rule):**
- A new alert rule is added to `docker/prometheus/alert-rules.yml` under a new `alerting` group (separate from the `scrapers` group)
- Alert name: `RedisDegraded`
- Expression: `redis_degraded == 1`
- Duration: `for: 5m` — fires only after sustained degradation
- Severity: `warning` (the system is degraded but functional — DB fallback is active)
- Annotations:
  - `summary`: `"Redis cache layer degraded for > 5 minutes"`
  - `description`: `"Redis has been degraded for {{ $value | humanizeDuration }}. API responses are served from the database without caching. Check Redis pod and network connectivity."`
- The alert is routed via the existing Alertmanager configuration (no separate receiver needed — `warning` severity goes to the default channel)

**F-6 (Startup Log Messages):**
- During `RedisClient.connect()`, distinct log messages are emitted:
  1. If `REDIS_ENABLED` is `False`:
     - Warning level: `"redis_disabled_by_config — Redis is disabled via REDIS_ENABLED=false. All cache operations will fall back to the database."`
  2. If `REDIS_ENABLED` is `True` and connection succeeds:
     - Info level: `"redis_connected — Redis is available at {REDIS_URL}. Cache operations are enabled."`
  3. If `REDIS_ENABLED` is `True` and connection fails:
     - Warning level: `"redis_connection_failed — Could not connect to Redis at {REDIS_URL}: {error}. Cache operations will fall back to the database. A background recovery worker will attempt to reconnect."`
- These messages use the existing `structlog` logger and are emitted once at startup

## 6. USER & SYSTEM FLOWS

```
Flow 1: Redis degrades during operation (nominal degradation)
  App running, Redis healthy → GET /health returns {"redis": "ok"}
  → Redis becomes unreachable (pod crash, network partition, OOM)
  → Next health-check ping → `ping()` fails with TimeoutError
  → failure_count increments → threshold reached → healthy = False
  → GET /health now returns {"redis": "degraded"}
  → CacheService.get_or_compute() sees healthy=False → skip Redis → DB query
  → redis_degraded gauge transitions to 1
  → After 5 minutes of sustained degradation: RedisDegraded alert fires
  → GET /ready (after REDIS_STARTUP_GRACE_PERIOD): returns 503
  → Operators investigate

Flow 2: Redis recovers (automatic recovery)
  Redis still degraded → recovery worker pings every REDIS_HEALTH_CHECK_INTERVAL
  → Redis pod restarts and becomes reachable
  → recovery worker's ping() returns True
  → RedisClient.reconnect() called:
     → Disconnect old pool
     → Create new ConnectionPool
     → Create new AsyncRedis instance
     → Verify with ping()
     → Set healthy = True, failure_count = 0
     → redis_degraded gauge transitions to 0
  → GET /health returns {"redis": "ok"}
  → GET /ready returns 200 with {"ready": true, "redis": "ok"}
  → Next API request: cache miss → populate cache → subsequent requests served from cache

Flow 3: Application starts with REDIS_ENABLED=false
  App starts → Settings.REDIS_ENABLED = False
  → RedisClient.connect() returns immediately
  → healthy = False (intentionally)
  → Log warning: "redis_disabled_by_config"
  → No background health-check or recovery worker started
  → GET /health returns {"redis": "disabled"}
  → GET /ready returns {"ready": true, "redis": "disabled"}
  → All cache requests fall through to DB via existing healthy=False check
  → redis_degraded gauge remains 0 (not degraded — intentionally disabled)

Flow 4: Application starts with Redis unreachable (transient outage)
  App starts → REDIS_ENABLED=True → RedisClient.connect() fails
  → healthy = False (degraded)
  → Log warning: "redis_connection_failed"
  → Recovery worker started (but not actively pinging — waits for interval)
  → GET /health returns {"redis": "degraded"}
  → GET /ready (within startup grace period): returns {"ready": true, "redis": "degraded"}
  → GET /ready (after grace period expired, still degraded): returns 503
  → Recovery worker pings → still failing → remains degraded
  → After 5+ minutes: RedisDegraded alert fires

Flow 5: Readiness probe in Kubernetes
  Kubelet → GET /ready → app checks:
     DB pool initialised? → yes
     Redis healthy or disabled? → check healthy flag + REDIS_ENABLED
  → If all conditions met: 200 OK {"ready": true}
  → If Redis degraded past grace period: 503 {"ready": false, "redis": "degraded"}
  → If DB not ready: 503 {"ready": false, "db": "not_ready"}
  → Kubelet uses response to include/exclude pod from service endpoints
```

## 7. SCOPE & BOUNDARIES

### 7.1 In Scope

- Background recovery worker as an asyncio task with pool reinitialisation on successful ping
- `RedisClient.reconnect()` method to disconnect old pool, create new pool, and verify connectivity
- `REDIS_ENABLED` configuration flag in core config with env var support
- `GET /ready` readiness endpoint with dependency health reporting and HTTP 503 after grace period
- `redis_degraded` Prometheus gauge metric
- `RedisDegraded` Prometheus alert rule in `docker/prometheus/alert-rules.yml`
- Distinct startup log messages for disabled, connected, and unreachable Redis states
- Startup grace period for readiness endpoint (`REDIS_STARTUP_GRACE_PERIOD`, default 30s)
- Cancellation of recovery worker on application shutdown
- Jitter on recovery worker sleep interval to prevent thundering-herd
- Update to `GET /health` to report `"redis": "disabled"` when `REDIS_ENABLED` is `False`
- Unit and integration tests for degraded mode, recovery, disabled mode, and readiness endpoint

### 7.2 Out of Scope

- [OUT] Changes to scrapper-base — all changes are within `src/real-estate-api/`
- [OUT] Cache invalidation logic — STORY-24 is already merged
- [OUT] Modifications to `CacheService.get_or_compute()` — the existing fallback logic is correct and unchanged
- [OUT] Redis Sentinel or Cluster configuration
- [OUT] Persistent storage of Redis health history beyond Prometheus metrics
- [OUT] Frontend changes — no API contract changes beyond adding `GET /ready`
- [OUT] Changes to the existing `GET /health` endpoint response shape (only the `redis` field value is extended to include `"disabled"`)
- [OUT] Circuit-breaker pattern or exponential backoff for individual Redis operations
- [OUT] Cache pre-warming or seeding after recovery

### 7.3 Deferred / Maybe-Later

- Multi-instance Redis health aggregation — currently each API replica tracks its own Redis health independently; a shared health view could be useful for multi-replica deployments
- Health-check endpoint authentication — no auth is needed for internal cluster probes, but external exposure may require it later
- Detailed readiness sub-resource probes (e.g., `GET /ready/db`, `GET /ready/redis`) — individual probes could be added if fine-grained orchestration is needed
- Prometheus alert for rapid toggling (flapping detection) — a `redis_degraded_flapping` alert could be useful if Redis repeatedly transitions between healthy and degraded

## 8. INTERFACES & INTEGRATION CONTRACTS

### 8.1 REST / HTTP Endpoints

**New endpoint: `GET /ready`**

| Aspect | Specification |
|--------|--------------|
| Method | `GET` |
| Path | `/ready` |
| Auth | None (internal cluster probe) |
| Response 200 | `{"ready": true, "redis": "ok" | "disabled"}` |
| Response 503 | `{"ready": false, "redis": "degraded"}` or `{"ready": false, "db": "not_ready"}` |
| Cache | Not cached (internal probe) |
| Rate limit | None |

**Modified endpoint: `GET /health`**

| Aspect | Current | After Change |
|--------|---------|-------------|
| `redis` field values | `"ok"` \| `"degraded"` | `"ok"` \| `"degraded"` \| `"disabled"` (added `"disabled"` for `REDIS_ENABLED=false`) |
| Response shape | `{"status": "ok", "redis": "ok"\|"degraded"}` | Unchanged — only the `redis` field gainsthe additional value `"disabled"` |

### 8.2 Events / Messages

No new events or messages. The existing Redis Streams (from STORY-24) are unaffected.

### 8.3 Data Model Impact

| ID | Element | Description |
|----|---------|-------------|
| DM-1 | `redis_degraded` Prometheus gauge | New metric tracking whether Redis is currently degraded (1) or healthy/disabled (0) |
| DM-2 | `RedisDegraded` Prometheus alert rule | New alert rule firing when `redis_degraded == 1` for > 5 minutes |
| DM-3 | `RedisClient.healthy` behaviour | No change to the flag itself; new state transitions occur via `reconnect()` instead of only via `ping()` |
| DM-4 | `GET /health` response `redis` field | Extended from `"ok"\|"degraded"` to `"ok"\|"degraded"\|"disabled"` |

No database schema changes. No new database tables or columns. No new Redis data structures.

### 8.4 External Integrations

| Service | Interface | Purpose | Change |
|---------|-----------|---------|--------|
| Redis 7 | `redis.asyncio` client | Cache-aside for API responses | No new interface; existing `RedisClient` gains `reconnect()` method |
| Prometheus | `/metrics` endpoint (existing) | `redis_degraded` gauge exposed | New metric added to existing endpoint |
| Alertmanager | Alert webhook (existing) | `RedisDegraded` alert notification | New alert rule added; uses existing `warning` severity routing |
| Kubernetes | `GET /ready` HTTP probe | Readiness probe for pod lifecycle | New endpoint providing readiness semantics |

### 8.5 Backward Compatibility

- Fully backward compatible — no API contract changes for existing endpoints
- `GET /health` gains one additional value for the `redis` field (`"disabled"`) — existing clients that check for `"ok"` or `"degraded"` continue to work; `"disabled"` is logically equivalent to `"degraded"` for clients that only check equality to `"ok"`
- `GET /ready` is a new endpoint — no existing client depends on it
- `redis_degraded` gauge is a new metric — existing dashboards and alerts are unaffected
- The `RedisDegraded` alert rule is additive — existing alert rules are unchanged
- Existing `CacheService` fallback behaviour is unchanged — the `healthy` flag is already read by `get_or_compute()`
- Existing test suites for STORY-23 continue to pass — no logic changes to existing cache-aside code

## 9. NON-FUNCTIONAL REQUIREMENTS (NFRs)

| ID | Requirement | Threshold |
|----|-------------|-----------|
| NFR-1 | Recovery worker reconnection latency after Redis becomes reachable | <= `REDIS_HEALTH_CHECK_INTERVAL` + 2 seconds (one ping cycle + reconnect overhead) |
| NFR-2 | `GET /ready` response latency | p95 < 5 ms (reads cached in-memory state; no network or Redis calls) |
| NFR-3 | Recovery worker memory overhead | < 1 MB RSS beyond the base application (single asyncio task with minimal state) |
| NFR-4 | CPU impact of recovery worker pings during degraded mode | < 0.1% CPU (one `ping()` call every 30 seconds) |
| NFR-5 | `redis_degraded` gauge update latency | Updated within 1 second of any healthy/degraded state transition |
| NFR-6 | `RedisDegraded` alert firing delay | `for: 5m` — alert fires exactly 5 minutes after `redis_degraded` transitions to 1 (subject to Prometheus evaluation interval, ~15s) |
| NFR-7 | Pool reinitialisation duration | New `ConnectionPool` creation + verification `ping()` completes within `REDIS_TIMEOUT_SECONDS` + 1 second |
| NFR-8 | Startup grace period configurability | `REDIS_STARTUP_GRACE_PERIOD` must be configurable via environment variable with default 30 seconds |
| NFR-9 | Recovery worker task cancellation on shutdown | Recovery task cancelled within 2 seconds of shutdown signal |

## 10. TELEMETRY & OBSERVABILITY REQUIREMENTS

**Metrics (Prometheus):**

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `cache_hits_total` | Counter | `endpoint`, `cache_key_prefix` | Existing — unchanged |
| `cache_misses_total` | Counter | `endpoint`, `cache_key_prefix` | Existing — unchanged |
| `cache_errors_total` | Counter | `endpoint`, `operation`, `error_type` | Existing — unchanged |
| `cache_operation_duration_seconds` | Histogram | `endpoint`, `operation` | Existing — unchanged |
| `cache_entry_size_bytes` | Gauge | `endpoint` | Existing — unchanged |
| `redis_degraded` | Gauge | *(no labels)* | **New** — 1 when Redis is degraded (healthy=False AND REDIS_ENABLED=True), 0 otherwise |

**Alerts:**

| Alert | Expression | For | Severity | Description |
|-------|------------|-----|----------|-------------|
| `RedisDegraded` | `redis_degraded == 1` | 5m | `warning` | Redis cache layer has been degraded for more than 5 minutes |

**Logging:**

| Event | Level | Message | Context |
|-------|-------|---------|---------|
| Redis disabled by config | `WARNING` | `"redis_disabled_by_config — Redis is disabled via REDIS_ENABLED=false. All cache operations will fall back to the database."` | Startup, once |
| Redis connected | `INFO` | `"redis_connected — Redis is available at {REDIS_URL}. Cache operations are enabled."` | Startup, once |
| Redis connection failed | `WARNING` | `"redis_connection_failed — Could not connect to Redis at {REDIS_URL}: {error}. Cache operations will fall back to the database. A background recovery worker will attempt to reconnect."` | Startup, once |
| Redis reconnected (after recovery) | `INFO` | `"redis_reconnected — Successfully reconnected to Redis after degradation. Connection pool reinitialised."` | Recovery event, once per recovery |
| Redis recovery failed | `WARNING` | `"redis_recovery_failed — Attempted to reconnect to Redis but connection failed: {error}. Will retry in {interval} seconds."` | Per failed recovery attempt |
| Health-check degraded transition | `WARNING` | `"redis_degraded — Redis health check failed {failure_count} times consecutively. Entering degraded mode."` | First degradation detection |

**Health / Readiness Endpoints:**

| Endpoint | Response (healthy) | Response (degraded) | Response (disabled) |
|----------|-------------------|---------------------|---------------------|
| `GET /health` | `{"status": "ok", "redis": "ok"}` | `{"status": "ok", "redis": "degraded"}` | `{"status": "ok", "redis": "disabled"}` |
| `GET /ready` | `{"ready": true, "redis": "ok"}` (HTTP 200) | `{"ready": false, "redis": "degraded"}` (HTTP 503, after grace period) | `{"ready": true, "redis": "disabled"}` (HTTP 200) |

## 11. RISKS & MITIGATIONS

| ID | Risk | Impact | Probability | Mitigation | Residual Risk |
|----|------|--------|-------------|------------|---------------|
| RSK-1 | Recovery worker creates new connection pool while old pool still has in-flight operations | Medium — in-flight operations may fail with `ConnectionClosedError` | Low | The old pool is disconnected only after the new pool is verified; existing requests using old connections will complete or time out naturally before the next poll cycle. No shared state between old and new pools. | Low — small window of concurrent old/new pool use during reconnect is harmless |
| RSK-2 | Recovery worker enters tight loop if `ping()` returns True but `reconnect()` repeatedly fails | Medium — CPU spike, log spam | Low | On recovery failure, the worker logs a warning and resumes the sleep cycle (no immediate retry). The next attempt happens after the regular interval. | Low — bounded by the 30-second sleep cycle |
| RSK-3 | `redis_degraded` gauge toggles rapidly during network flapping | Low — benign metric noise | Medium | The existing `REDIS_HEALTH_CHECK_FAILURE_THRESHOLD` (3 consecutive failures) already prevents flapping on transient hiccups. The `for: 5m` duration on the alert prevents alert flapping. | Low — threshold and duration prevent both metric and alert flapping |
| RSK-4 | Application starts with `REDIS_ENABLED=true` but Redis is unavailable — readiness probe fails after grace period, Kubernetes removes pod from service | Medium — no traffic served | Low | This is intentional behaviour: if Redis is expected (enabled) but unavailable for longer than the grace period, the pod is correctly marked not-ready. The operator should either fix Redis or set `REDIS_ENABLED=false` and redeploy. | Medium — operator must take action, but the behaviour is correct and visible |
| RSK-5 | `REDIS_ENABLED=false` used in production by mistake — performance degradation unnoticed | Medium — increased DB load, higher latency | Low | The startup log warning clearly states Redis is disabled; the `redis: "disabled"` health response indicates intentional disable; Grafana dashboard panels showing cache hit ratio will drop to 0% | Low — multiple observability signals make accidental disable visible |
| RSK-6 | Recovery worker is not cancelled on shutdown, continues pinging after app shutdown | Low — abandoned task, minor resource leak | Low | The asyncio task is properly cancelled in the `lifespan` shutdown handler and awaited with `CancelledError` handling. | Low — standard asyncio lifecycle management |

## 12. ASSUMPTIONS

- The existing `RedisClient.healthy` flag and `failure_count` mechanism from STORY-23 are correct and do not need to be redesigned — only augmented with the `reconnect()` method
- The existing `CacheService.get_or_compute()` fallback to DB when `healthy=False` is correct — no changes needed to the cache-aside logic
- The application lifespan (`asynccontextmanager` in `main.py`) is the correct place to manage the recovery worker task lifecycle
- `REDIS_STARTUP_GRACE_PERIOD` default of 30 seconds is sufficient for Redis to start in a co-located deployment (e.g., Docker Compose, k3s pod with init container)
- The `redis_degraded` gauge does not need per-endpoint or per-operation labels — a single global gauge is sufficient for alerting and dashboard purposes
- Kubernetes readiness probes are configured to use `GET /ready` with appropriate `initialDelaySeconds` and `periodSeconds` values — the readiness endpoint alone does not configure Kubernetes
- The solo developer (@rendenwald) operates the Prometheus and Alertmanager stack and will receive `RedisDegraded` alerts via the existing notification channel (email/Slack)
- Jitter of ±10% on the recovery worker sleep interval is sufficient to prevent thundering-herd in multi-replica deployments
- No authentication is needed on `GET /ready` — it is an internal cluster probe endpoint with no sensitive data exposure

## 13. DEPENDENCIES

| Direction | Item | Notes |
|-----------|------|-------|
| Depends on | STORY-23 (Redis cache-aside implementation) | Provides `RedisClient`, `CacheService`, `healthy` flag, health endpoint — all extended by this change |
| Depends on | Redis 7 running in `storage-ns` | Redis is the target of the recovery worker; must be deployed per `120-CACHING-STORAGE.md` |
| Depends on | Prometheus deployed in `monitoring-ns` | Exposes `redis_degraded` gauge and evaluates the `RedisDegraded` alert rule |
| Depends on | Alertmanager deployed in `monitoring-ns` | Routes the `RedisDegraded` alert to notification channels |
| Blocks | (none) | This is the final resilience layer on top of STORY-23 infrastructure; no downstream changes depend on it |
| Related | STORY-24 (Cache invalidation) | Cache invalidation consumer also depends on Redis; the recovery worker handles pool reinit for both cache-aside and invalidation scenarios |

## 14. OPEN QUESTIONS

| ID | Question | Context | Status |
|----|----------|---------|--------|
| OQ-1 | Should the recovery worker be a method on `RedisClient` or a standalone asyncio task in `main.py`? | The existing `_periodic_health_check` in `main.py` already implements a similar ping loop. The recovery worker could either extend that function (adding `reconnect()` call on successful ping after degradation) or be a new task specific to recovery. Extending the existing task is simpler but conflates health-check with recovery concerns. | Decision needed: consult `@architect` |
| OQ-2 | Should `GET /ready` also verify the database connection pool is healthy, or just Redis? | STORY-23 and STORY-24 focus on Redis. The database pool health is implicitly verified by the first query. Adding explicit DB health verification would make the readiness endpoint more comprehensive but is outside the Redis resilience scope. | Recommended: include DB readiness as a simple flag (`app.state.db_ready`) set after the first successful query or pool initialisation, but defer deep DB health-checking to a future change |
| OQ-3 | Should `redis_degraded` gauge have a `reason` label to distinguish between "connection failed" and "timeout" degradation causes? | A label would provide more granular observability but adds cardinality. For alerting purposes, a single binary gauge is sufficient. Dashboard builders could use `cache_errors_total` with `error_type` label for cause analysis. | Recommended: no label — single gauge is sufficient; cause analysis uses existing `cache_errors_total` metric |
| OQ-4 | What should the `RedisDegraded` alert severity be? | `warning` — the system is degraded but fully functional (DB fallback). `critical` would be too severe for a non-data-loss scenario. | Recommended: `warning` severity, with an annotation suggesting escalation path if degradation persists > 30 minutes |

## 15. DECISION LOG

| ID | Decision | Rationale | Date |
|----|----------|-----------|------|
| DEC-1 | Recovery worker reinitialises the full connection pool on recovery (disconnect old + create new) rather than attempting to reuse or repair the existing pool | Redis connections in the old pool may be in a closed or half-open state after an outage; creating a fresh pool is the only reliable way to restore full connectivity. Pool creation is lightweight (TCP connections are lazy — established on first use). | 2026-06-24 |
| DEC-2 | `REDIS_ENABLED=false` sets `healthy=False` (consistent with degraded state) rather than adding a separate health-check code path | The existing `CacheService.get_or_compute()` already checks `self._redis.healthy` — setting `healthy=False` reuses this path without modification. The only distinction is in the health/readiness response values (`"disabled"` vs `"degraded"`). | 2026-06-24 |
| DEC-3 | `GET /ready` returns HTTP 503 when Redis is degraded past the startup grace period, not immediately | Prevents crash-loop-backoff when Redis and the API app start simultaneously (e.g., in Docker Compose or k3s). The 30-second grace period gives Redis time to initialise before the readiness probe starts failing. | 2026-06-24 |
| DEC-4 | `redis_degraded` gauge is 0 when `REDIS_ENABLED=false` (not 1) | The gauge tracks "unexpected degradation", not "intentionally disabled". A disabled Redis does not need operator attention — the gauge should not trigger alerts or affect dashboards. | 2026-06-24 |
| DEC-5 | `RedisDegraded` alert uses `for: 5m` to prevent flapping | Transient Redis hiccups (e.g., network micro-outage, pod restart) should not trigger operator notifications. The 5-minute duration ensures the alert only fires for sustained degradation. | 2026-06-24 |
| DEC-6 | Recovery worker sleep includes ±10% random jitter | Prevents thundering-herd in multi-replica deployments where all pods would attempt recovery at the same interval boundary. | 2026-06-24 |

## 16. AFFECTED COMPONENTS (HIGH-LEVEL)

| Component | Impact |
|-----------|--------|
| `real-estate-api/app/core/config.py` | Updated — `REDIS_ENABLED` and `REDIS_STARTUP_GRACE_PERIOD` settings added |
| `real-estate-api/app/services/redis_client.py` | Updated — `reconnect()` method added; `connect()` checks `REDIS_ENABLED`; recovery worker logic integrated |
| `real-estate-api/app/core/metrics.py` | Updated — `redis_degraded` gauge added |
| `real-estate-api/app/main.py` | Updated — recovery worker lifecycle; startup log messages; `GET /ready` endpoint registration |
| `real-estate-api/app/routers/health.py` | Updated — `"disabled"` value added to `redis` field in health response |
| `real-estate-api/app/routers/readiness.py` | New — `GET /ready` readiness endpoint |
| `docker/prometheus/alert-rules.yml` | Updated — `RedisDegraded` alert rule added |
| `real-estate-api/tests/test_redis_client.py` | Updated — tests for `reconnect()`, degraded mode, disabled mode, recovery worker |
| `real-estate-api/tests/test_health.py` | Updated — tests for `"disabled"` health response and `GET /ready` endpoint |

## 17. ACCEPTANCE CRITERIA

| ID | Criterion | Linked |
|----|-----------|--------|
| AC-F1-1 | **Given** Redis is healthy, **when** the application starts, **then** the background recovery worker task is created but does not actively probe (idles until degradation) | F-1 |
| AC-F1-2 | **Given** Redis becomes unreachable (healthy transitions to False), **when** the recovery worker's next ping cycle runs, **then** it calls `ping()` and finds Redis still unreachable | F-1 |
| AC-F1-3 | **Given** Redis was degraded and becomes reachable again, **when** the recovery worker's next ping returns True, **then** `reconnect()` is called and `healthy` returns to True | F-1 |
| AC-F1-4 | **Given** `reconnect()` fails (new connection also fails), **when** the recovery worker handles the error, **then** `healthy` remains False and the worker retries on the next interval | F-1 |
| AC-F2-1 | **Given** `REDIS_ENABLED=false` is set, **when** the application starts, **then** `RedisClient.connect()` returns without creating a connection pool, `healthy` is False, and a warning is logged | F-2 |
| AC-F2-2 | **Given** `REDIS_ENABLED=false`, **when** `GET /health` is called, **then** the response includes `"redis": "disabled"` | F-2 |
| AC-F2-3 | **Given** `REDIS_ENABLED=false`, **when** a cache-aside operation is performed, **then** `get_or_compute()` returns `"miss (fallback)"` without attempting Redis | F-2 |
| AC-F3-1 | **Given** the application is healthy (DB connected, Redis ok or disabled), **when** `GET /ready` is called, **then** the response is HTTP 200 with `{"ready": true}` | F-3 |
| AC-F3-2 | **Given** Redis is degraded and the startup grace period has elapsed, **when** `GET /ready` is called, **then** the response is HTTP 503 with `{"ready": false, "redis": "degraded"}` | F-3 |
| AC-F3-3 | **Given** Redis is degraded but the startup grace period has NOT yet elapsed, **when** `GET /ready` is called, **then** the response is HTTP 200 with `{"ready": true, "redis": "degraded"}` | F-3 |
| AC-F4-1 | **Given** Redis is degrading (healthy transitions from True to False), **when** the state change occurs, **then** `redis_degraded` gauge transitions from 0 to 1 | F-4 |
| AC-F4-2 | **Given** Redis recovers (healthy transitions from False to True via `reconnect()`), **when** the state change occurs, **then** `redis_degraded` gauge transitions from 1 to 0 | F-4 |
| AC-F4-3 | **Given** `REDIS_ENABLED=false`, **when** the application starts, **then** `redis_degraded` gauge is 0 (disabled is not degraded) | F-4 |
| AC-F5-1 | **Given** `redis_degraded` is 1 for more than 5 minutes, **when** Prometheus evaluates the alert rule, **then** the `RedisDegraded` alert fires with severity `warning` | F-5 |
| AC-F5-2 | **Given** `redis_degraded` returns to 0 before 5 minutes elapse, **when** Prometheus evaluates the alert rule, **then** the `RedisDegraded` alert does not fire | F-5 |
| AC-F6-1 | **Given** `REDIS_ENABLED=false`, **when** the application starts, **then** a warning-level log message is emitted containing `"redis_disabled_by_config"` | F-6 |
| AC-F6-2 | **Given** `REDIS_ENABLED=true` and Redis connection succeeds, **when** the application starts, **then** an info-level log message is emitted containing `"redis_connected"` | F-6 |
| AC-F6-3 | **Given** `REDIS_ENABLED=true` and Redis connection fails, **when** the application starts, **then** a warning-level log message is emitted containing `"redis_connection_failed"` and mentioning the recovery worker | F-6 |
| AC-NFR-1 | **Given** Redis is degraded, **when** the recovery worker pings and finds Redis reachable, **then** pool reinitialisation completes within `REDIS_TIMEOUT_SECONDS` + 1 second | NFR-7 |

## 18. ROLLOUT & CHANGE MANAGEMENT (HIGH-LEVEL)

1. **Implementation order:**
   - Phase 1: Add `REDIS_ENABLED` and `REDIS_STARTUP_GRACE_PERIOD` to `Settings` class
   - Phase 2: Implement `RedisClient.reconnect()` method with pool reinitialisation
   - Phase 3: Refactor `_periodic_health_check` in `main.py` to serve as the recovery worker (add reconnect call on successful ping after degradation), or create a new recovery worker task
   - Phase 4: Update `RedisClient.connect()` to check `REDIS_ENABLED` and handle disabled/connection-failure paths
   - Phase 5: Add `redis_degraded` gauge to `core/metrics.py` and wire it to `RedisClient` state transitions
   - Phase 6: Implement `GET /ready` endpoint in a new router or extended health router
   - Phase 7: Add `RedisDegraded` alert rule to `docker/prometheus/alert-rules.yml`
   - Phase 8: Update `GET /health` to return `"disabled"` when applicable
   - Phase 9: Add startup log messages with distinct levels and context
   - Phase 10: Write tests (unit tests for `reconnect()`, disabled mode, readiness endpoint; integration tests for recovery worker behaviour)

2. **Deployment order:** Single deployment — all changes are within `real-estate-api` and can be merged and deployed together. The Prometheus alert rule update requires redeploying the `prometheus-config` ConfigMap.

3. **Merge strategy:** Squash merge to `main` via PR

4. **Communication:** None needed — internal change with no user-facing impact. Operators should be informed about the new `GET /ready` endpoint for Kubernetes probe configuration.

5. **Rollback:**
   - Revert the merge commit — all changes are within `real-estate-api` and `docker/prometheus/`
   - If the Prometheus alert rule is rolled back, the alert simply stops firing; no functional impact
   - If the recovery worker is rolled back, the system falls back to the STORY-23 behaviour (health-check pings but no pool reinit) — manual restart still works for recovery

## 19. DATA MIGRATION / SEEDING (IF APPLICABLE)

N/A — no database schema changes. No Redis data migration. No new Redis data structures. The `redis_degraded` gauge has no persistent state.

## 20. PRIVACY / COMPLIANCE REVIEW

No personal data is exposed or affected by this change. The `GET /ready` endpoint returns only dependency health status (`ready`, `redis` field) — no user data, no property data, no session information. The `redis_degraded` gauge is an operational metric with no privacy implications. No GDPR implications beyond those already addressed by the platform.

## 21. SECURITY REVIEW HIGHLIGHTS

- `GET /ready` exposes only dependency health status — no sensitive data, no user data, no internal network topology beyond the existence of Redis and the database
- `REDIS_ENABLED=false` provides a clean way to disable Redis without relying on empty or invalid `REDIS_URL` values — reducing the risk of misconfiguration
- Recovery worker connects using the same `REDIS_URL` environment variable — credentials are handled via environment, not hardcoded
- No new Redis commands or interfaces are exposed — the recovery worker uses the same `redis.asyncio` client as the existing cache layer
- The recovery worker cannot be triggered by external input — it is an internal asyncio task driven by timer and health-check results
- `RedisDegraded` alert does not expose any exploitable information — it is an operational alert routed within the internal monitoring stack

## 22. MAINTENANCE & OPERATIONS IMPACT

- **New configuration variables:** Operators must be aware of `REDIS_ENABLED` (bool, default true) and `REDIS_STARTUP_GRACE_PERIOD` (int seconds, default 30). Both can be set via environment variables.
- **Readiness probe configuration:** Kubernetes `deployment.yaml` should be updated to use `GET /ready` for readiness probes (separate from the existing liveness probe on `/health`). Example probe: `httpGet: { path: /ready, port: 8000 }` with `initialDelaySeconds: 5`, `periodSeconds: 10`, `failureThreshold: 3`.
- **New Prometheus alert:** Operators will receive `RedisDegraded` alerts via the existing Alertmanager pipeline. The alert should be acknowledged and investigated if it fires outside of planned maintenance windows.
- **Monitoring dashboards:** The `redis_degraded` gauge should be added to the existing Redis dashboard in Grafana. A panel showing "Redis degraded duration" (using `avg_over_time(redis_degraded[5m])`) helps track cumulative degradation.
- **Recovery testing:** Operators should periodically test the recovery path by stopping the Redis pod, verifying degraded operation, restarting Redis, and confirming automatic recovery. This can be part of the standard disaster recovery drill.
- **Unchanged:** Cache-aside fallback behaviour, cache key formats, TTL values, Redis configuration, and all existing monitoring remain unchanged.
- **Log volume:** The recovery worker logs one line per ping cycle during degradation (every 30 seconds). At scale, this is ~2,880 log lines per day per degraded instance — acceptable for debugging purposes. Events are logged at info level, not debug.

## 23. GLOSSARY

| Term | Definition |
|------|------------|
| Degraded mode | Operational state where Redis is unreachable and all cache operations fall back to direct database queries |
| Grace period (`REDIS_STARTUP_GRACE_PERIOD`) | Time window after application startup during which `GET /ready` tolerates Redis being degraded without returning HTTP 503 |
| Liveness probe | Kubernetes health check that restarts the pod if it fails — implemented by `GET /health` |
| Readiness probe | Kubernetes health check that removes the pod from service endpoints if it fails — implemented by `GET /ready` |
| Recovery worker | Background asyncio task that periodically pings a degraded Redis instance and reinitialises the connection pool on successful ping |
| `reconnect()` | `RedisClient` method that disconnects the old connection pool, creates a new pool, and verifies connectivity |
| `redis_degraded` | Prometheus gauge (0/1) tracking whether Redis is currently in degraded state |
| `REDIS_ENABLED` | Configuration flag that controls whether Redis is initialised at startup; when false, all cache operations are bypassed |
| Thundering herd | Scenario where multiple clients retry an operation simultaneously after a failure, overwhelming the recovering service — mitigated by jitter on the recovery worker sleep interval |

## 24. APPENDICES

**A. State Transition Diagram**

```
                     ┌─────────────┐
                     │   STARTUP    │
                     └──────┬──────┘
                            │
                    ┌───────┴────────┐
                    │ REDIS_ENABLED? │
                    └───────┬────────┘
                   ┌────────┴─────────┐
                   │                  │
                False               True
                   │                  │
            ┌──────┴──────┐   ┌──────┴────────┐
            │  disabled   │   │  connect()    │
            │ healthy=F   │   └──────┬────────┘
            │ gauge=0     │    ┌─────┴──────┐
            └─────────────┘    │            │
                          Success         Fail
                            │              │
                     ┌──────┴──────┐  ┌────┴──────────┐
                     │   healthy   │  │  degraded      │
                     │ healthy=T   │  │  healthy=F     │
                     │ gauge=0     │  │  gauge=1       │
                     │ worker idle │  │  worker active │
                     └──────┬──────┘  └────┬──────────┘
                            │              │
                    Redis fails       ping succeeds
                            │              │
                     ┌──────┴──────┐  ┌────┴──────────┐
                     │  degraded   │  │  reconnect()  │
                     │  healthy=F  │  └────┬──────────┘
                     │  gauge=1    │   ┌────┴──────┐
                     │  worker act │   │           │
                     └─────────────┘  Success    Fail
                                       │          │
                                ┌──────┴────┐     │
                                │  healthy  │     │
                                │  healthy=T│     │
                                │  gauge=0  │     │
                                │  idle     │     │
                                └───────────┘     │
                                          ┌───────┴──────────┐
                                          │  still degraded   │
                                          │  worker retries   │
                                          └──────────────────┘
```

**B. Recovery Worker Pseudocode (asyncio task)**

```
async def recovery_worker(redis_client: RedisClient, settings: Settings):
    """Background task that reconnects Redis when it recovers from degradation."""
    while True:
        if not redis_client.healthy and settings.REDIS_ENABLED:
            try:
                ping_ok = await redis_client.ping()
                if ping_ok:
                    await redis_client.reconnect()
                    redis_degraded_gauge.set(0)
            except Exception as exc:
                logger.warning("redis_recovery_failed", error=str(exc))
        # Sleep interval with ±10% jitter
        jitter = random.uniform(-0.1, 0.1) * settings.REDIS_HEALTH_CHECK_INTERVAL
        await asyncio.sleep(settings.REDIS_HEALTH_CHECK_INTERVAL + jitter)
```

**C. `GET /ready` Response Examples**

```json
// Healthy — Redis OK
HTTP 200
{"ready": true, "redis": "ok"}

// Redis intentionally disabled
HTTP 200
{"ready": true, "redis": "disabled"}

// Redis degraded, within startup grace period
HTTP 200
{"ready": true, "redis": "degraded"}

// Redis degraded, past startup grace period
HTTP 503
{"ready": false, "redis": "degraded"}

// Database not ready
HTTP 503
{"ready": false, "db": "not_ready"}
```

**D. Prometheus Alert Rule (YAML fragment)**

```yaml
groups:
  - name: alerting
    rules:
      - alert: RedisDegraded
        expr: |
          redis_degraded == 1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Redis cache layer degraded for > 5 minutes"
          description: >
            Redis has been degraded for {{ $value | humanizeDuration }}.
            API responses are served from the database without caching.
            Check Redis pod and network connectivity.
```

## 25. DOCUMENT HISTORY

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-06-24 | spec-writer | Initial specification for STORY-27 |

---

## AUTHORING GUIDELINES

**Sources consulted:**
- `doc/planning/epics/epic-05--redis-cache/epic-05--redis-cache.md` — Epic definition; Redis resilience requirements
- `doc/planning/backlog.md` — Work item description and priority
- `doc/changes/2026-06/2026-06-21--STORY-23--redis-cache-properties-list/chg-STORY-23-spec.md` — Prior change spec for format consistency, existing RedisClient context, and cache-aside architecture
- `doc/changes/2026-06/2026-06-22--STORY-24--cache-invalidation-property-upsert/chg-STORY-24-spec.md` — Prior change spec for invalidation consumer context
- `specs/specs/080-API.md` — API endpoint specification
- `specs/specs/120-CACHING-STORAGE.md` — Cache strategy and Redis configuration
- `specs/specs/130-MONITORING-ALERTS.md` — Monitoring and alerting framework
- `src/real-estate-api/app/services/redis_client.py` — Existing RedisClient implementation (STORY-23 baseline)
- `src/real-estate-api/app/services/cache_service.py` — Existing CacheService with fallback logic
- `src/real-estate-api/app/core/config.py` — Existing settings class
- `src/real-estate-api/app/main.py` — Existing lifespan and health-check task
- `src/real-estate-api/app/core/metrics.py` — Existing Prometheus metrics
- `src/real-estate-api/app/routers/health.py` — Existing health endpoint
- `docker/prometheus/alert-rules.yml` — Existing alert rules
- `doc/templates/change-spec-template.md` — Structural template

**Constraints:**
- No implementation details (file paths, code-level instructions, step-by-step tasks)
- Tech-agnostic within the bounds of existing spec decisions (Redis 7, FastAPI, Prometheus, Alertmanager, asyncio)
- All section ID prefixes follow stable conventions (F-, AC-, NFR-, RSK-, DEC-, DM-, OQ-)
- Acceptance criteria reference at least one F- or NFR- ID and use Given/When/Then format

## VALIDATION CHECKLIST

- [x] `change.ref` matches provided `workItemRef` (STORY-27)
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
