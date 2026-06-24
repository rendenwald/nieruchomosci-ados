---
# Copyright (c) 2025-2026 Juliusz Ćwiąkalski
# MIT License - see LICENSE file for full terms
source: https://github.com/juliusz-cwiakalski/agentic-delivery-os/blob/main/doc/templates/implementation-plan-template.md
id: chg-STORY-27-graceful-fallback-redis-unavailable
status: Proposed
created: 2026-06-24T00:00:00Z
last_updated: 2026-06-24T00:00:00Z
owners: ["rendenwald"]
service: real-estate-api
labels: ["change"]
links:
  change_spec: ./chg-STORY-27-spec.md
summary: >
  Add a comprehensive resilience layer on top of the existing Redis cache-aside
  implementation so the platform continues operating without interruption when
  Redis is unavailable, and automatically recovers full caching capability when
  Redis returns without manual intervention.
version_impact: minor
---

# IMPLEMENTATION PLAN — STORY-27: Graceful fallback to direct DB query when Redis unavailable

## Context and Goals

This plan implements 6 capabilities (F-1 through F-6) defined in `chg-STORY-27-spec.md`
to harden the Redis cache-aside layer built in STORY-23:

| ID | Capability | Primary ACs |
|----|-----------|-------------|
| F-1 | Background recovery worker that reinitialises the connection pool on successful ping after degradation | AC-F1-1–AC-F1-4 |
| F-2 | `REDIS_ENABLED` config flag to skip Redis initialisation entirely | AC-F2-1–AC-F2-3 |
| F-3 | `GET /ready` readiness endpoint with startup grace period | AC-F3-1–AC-F3-3 |
| F-4 | `redis_degraded` Prometheus gauge (0/1) | AC-F4-1–AC-F4-3 |
| F-5 | `RedisDegraded` Prometheus alert (fires after 5 min degraded) | AC-F5-1–AC-F5-2 |
| F-6 | Distinct startup log messages (disabled / connected / unreachable) | AC-F6-1–AC-F6-3 |

**Resolved open questions:**

- **OQ-1** (recovery worker location): The recovery worker is modelled as a pair of methods
  (`_start_recovery_worker` / `_stop_recovery_worker`) on `RedisClient` itself, with a
  `_recovery_task: asyncio.Task | None` attribute. The `lifespan` handler in `main.py`
  calls these methods instead of the current `_periodic_health_check` function. This
  keeps the recovery logic co-located with the connection pool it manages.
- **OQ-2** (DB readiness in `/ready`): Deferred — the readiness endpoint only checks Redis
  for now. A DB readiness check can be added in a future change.
- **OQ-3** (gauge labels): No `reason` label — a single binary gauge is sufficient for
  alerting; cause analysis uses `cache_errors_total{error_type="..."}`.
- **OQ-4** (alert severity): `warning` — the system is degraded but functional.

## Scope

### In Scope

- Background recovery worker as an asyncio task managed by `RedisClient`, with pool
  reinitialisation (`reconnect()`) on successful ping after degradation
- `REDIS_ENABLED: bool` (default `True`) and `REDIS_STARTUP_GRACE_PERIOD: int` (default `30`)
  settings in `Settings` class
- `GET /ready` readiness endpoint returning HTTP 200/503 with dependency health status
- `redis_degraded` Prometheus gauge updated on every state transition
- `RedisDegraded` Prometheus alert rule in `docker/prometheus/alert-rules.yml`
- Distinct startup log messages for disabled / connected / unreachable states
- Update `GET /health` to report `"redis": "disabled"` when `REDIS_ENABLED=False`
- Unit and integration tests for all new functionality
- Jitter (±10%) on recovery worker sleep interval

### Out of Scope

- Changes to `scrapper-base` — all changes are within `src/real-estate-api/`
- Changes to `CacheService.get_or_compute()` — existing fallback logic unchanged
- Redis Sentinel, Cluster, or any HA Redis topology
- Cache pre-warming after recovery — cache is repopulated lazily
- Circuit-breaker pattern for individual Redis operations
- Persistent health history beyond Prometheus metrics
- DB readiness check in `/ready` (deferred)

### Constraints

- All changes must be backward-compatible — no API contract changes for existing endpoints
- `redis_degraded` gauge must be 0 when `REDIS_ENABLED=False` (not 1)
- Recovery worker must be cancellable — use `asyncio.CancelledError` handling
- Recovery worker sleep must include ±10% random jitter
- All new code must pass `ruff check`, `mypy --strict` (with `ignore_missing_imports` for fakeredis),
  and existing tests unchanged
- Use `structlog` for all logging, type hints everywhere, line length 120

### Risks

| ID | Risk | Mitigation |
|----|------|------------|
| RSK-1 | Recovery worker reconnects while old pool has in-flight operations | Old pool disconnected only after new pool verified; existing requests complete or time out naturally |
| RSK-2 | Recovery worker tight loop if `ping()` returns True but `reconnect()` repeatedly fails | On recovery failure, log warning and resume sleep — no immediate retry |
| RSK-3 | `redis_degraded` gauge toggles during network flapping | Existing `REDIS_HEALTH_CHECK_FAILURE_THRESHOLD` (3) prevents flapping on transient hiccups |
| RSK-4 | App starts with `REDIS_ENABLED=True` but Redis unavailable — readiness probe fails after grace period | Intentional: pod marked not-ready; operator should fix Redis or set `REDIS_ENABLED=False` |
| RSK-5 | `REDIS_ENABLED=False` used in production by mistake | Startup log warning + `"disabled"` health response + cache hit ratio drops to 0% — multiple signals |

### Success Metrics

| Metric | Target |
|--------|--------|
| Recovery time after Redis becomes reachable | < `REDIS_HEALTH_CHECK_INTERVAL` + 5s (next ping cycle + reconnect) |
| Application disruption during Redis outage | Zero — all requests served from DB with `"miss (fallback)"` |
| `GET /ready` response time | p95 < 5 ms (reads cached in-memory state) |
| `RedisDegraded` alert firing delay | 5 minutes after `redis_degraded` transitions to 1 |
| False positive recovery | < 1% of recovery events |

## Phases

### Phase 1: Configuration — Add `REDIS_ENABLED` and `REDIS_STARTUP_GRACE_PERIOD`

**Goal**: Add the two new configuration fields to the `Settings` class so they are available
via environment variables throughout the application.

**Tasks**:

- [ ] **1.1** Add `REDIS_ENABLED: bool = True` to the `Settings` class at `src/real-estate-api/app/core/config.py`
  - Position logically after existing Redis settings (line ~40), with comment `# Whether to initialise Redis at startup`
- [ ] **1.2** Add `REDIS_STARTUP_GRACE_PERIOD: int = 30` to the `Settings` class
  - Comment: `# Seconds after startup before /ready reports degraded Redis as not-ready`
- [ ] **1.3** Verify both new fields are read from environment variables (pydantic-settings default behaviour)

**Acceptance Criteria**:

- Must: `Settings().REDIS_ENABLED` is `True` by default
- Must: `Settings().REDIS_STARTUP_GRACE_PERIOD` is `30` by default
- Must: Setting `REDIS_ENABLED=false` in the environment overrides to `False`
- Must: Setting `REDIS_STARTUP_GRACE_PERIOD=60` in the environment overrides to `60`

**Files and modules**:

- `src/real-estate-api/app/core/config.py` (updated — lines ~40-41)

**Tests**:

- Manual verification: `from app.core.config import Settings; s = Settings(); assert s.REDIS_ENABLED is True`
- Covered by test fixtures that import settings

**Completion signal**: `feat(STORY-27): add REDIS_ENABLED and REDIS_STARTUP_GRACE_PERIOD config`

---

### Phase 2: RedisClient — Recovery worker, `reconnect()`, `REDIS_ENABLED` support, and startup logging

**Goal**: Extend `RedisClient` with a background recovery worker that periodically pings
degraded Redis and reinitialises the connection pool on recovery. Support `REDIS_ENABLED=False`.
Emit distinct startup log messages for all three Redis states (disabled / connected / unreachable).

**Tasks**:

- [ ] **2.1** Add `_recovery_task: asyncio.Task | None = None` attribute to `__init__`.
  - Add `import asyncio` and `import random` at top of file
  - Import `app.core.metrics.redis_degraded` (will be created in Phase 3 — import with a
    guard or define the metric now with a default value; see Phase 3 for the module-level init)

- [ ] **2.2** Modify `connect()` to check `REDIS_ENABLED`:
  - At the very start of `connect()`, if not `self._settings.REDIS_ENABLED`:
    - Set `self.healthy = False`, log warning with `"redis_disabled_by_config"` key,
      `self._log.warning("redis_disabled_by_config", ...)` and return early (no pool created)
  - If enabled and connection succeeds: log `self._log.info("redis_connected", ...)`
    (existing logic already does this, but adjust message to match spec)
  - If enabled and connection fails: log `self._log.warning("redis_connection_failed", ...)`
    mentioning the recovery worker (existing logic, adjust message)
  - After successful or failed connection attempt, call `_start_recovery_worker()` if
    `REDIS_ENABLED` is `True` (regardless of success — worker idles until degraded)

- [ ] **2.3** Add `_start_recovery_worker()` method:
  - Create an asyncio task via `asyncio.create_task(self._recovery_loop())`
  - Store in `self._recovery_task`
  - Log debug: `"recovery_worker_started"`
  - Only call if `self._recovery_task is None` (idempotent)

- [ ] **2.4** Add `_stop_recovery_worker()` method:
  - If `self._recovery_task` is not None and not done:
    - Cancel the task
    - Await it (surround with try/except `asyncio.CancelledError`)
    - Set `self._recovery_task = None`
  - Log debug: `"recovery_worker_stopped"`

- [ ] **2.5** Add `_recovery_loop()` async method (the core worker loop):
  - Infinite `while True` loop:
    - If `self.healthy` is `True` (Redis is fine), just sleep `REDIS_HEALTH_CHECK_INTERVAL`
      and continue (idle loop — no probing when healthy)
    - If `self.healthy` is `False` (degraded):
      - Compute sleep with jitter: `interval = settings.REDIS_HEALTH_CHECK_INTERVAL * (0.9 + random.random() * 0.2)`
      - `await asyncio.sleep(interval)`
      - Call `await self.ping()` — if it returns `True`, call `await self._reconnect_pool()`
      - If `ping()` returns `False` or raises, just loop again (degraded stays degraded)
  - Wrap the entire body in try/except `asyncio.CancelledError` to cleanly exit on shutdown
  - Wrap `_reconnect_pool()` call in try/except to prevent unhandled exceptions from crashing the task

- [ ] **2.6** Add `_reconnect_pool()` method:
  1. Log `self._log.info("redis_reconnecting")`
  2. Disconnect old pool: if `self._pool is not None`, call `await self._pool.disconnect()`
  3. Create new pool: `ConnectionPool.from_url(...)` with same params as `connect()`
  4. Create new client: `self._redis = AsyncRedis(connection_pool=self._pool)`
  5. Verify: `await self.ping()`
  6. On success: log `self._log.info("redis_reconnected", ...)`, update `redis_degraded` gauge
  7. On failure: log `self._log.warning("redis_recovery_failed", ...)`, restore old pool?
     (Decision: keep the new pool even if verify fails — next recovery cycle will try again.
      Set healthy=False, failure_count unchanged, and let the next ping cycle retry.)

- [ ] **2.7** Modify `ping()` to update `redis_degraded` gauge on state transitions:
  - On successful ping when `healthy` was `False`: set gauge to 0
  - On reaching failure threshold when `healthy` was `True`: set gauge to 1
  - Add `import` for `redis_degraded` from `app.core.metrics` (circular-safe if metrics module
    has no RedisClient imports — it doesn't)

- [ ] **2.8** Wire start/stop in `connect()` / `disconnect()`:
  - In `connect()`: after pool setup (or disabled early return), call `_start_recovery_worker()`
  - In `disconnect()`: call `_stop_recovery_worker()` before pool disconnect

- [ ] **2.9** Update `main.py` — replace `_periodic_health_check` with recovery worker:
  - Remove the `_periodic_health_check` function (lines 23-39)
  - Remove the `health_task = asyncio.create_task(_periodic_health_check(redis_client))` line
    (line 72) and the shutdown cancellation block (lines 84-89) — the recovery worker is now
    managed internally by `RedisClient`
  - Keep the `lifespan` handler structure but simplify: no separate health task needed
  - Add `redis_client._stop_recovery_worker()` call in the shutdown path (via `disconnect()` already does it)
  - Adjust the startup log message (line 74-79) to include `redis_enabled` context

**Acceptance Criteria**:

- Must: AC-F1-1 — Recovery worker task created on startup but idles when healthy
- Must: AC-F1-2 — When degraded, worker calls `ping()` every interval
- Must: AC-F1-3 — On successful ping after degradation, `_reconnect_pool()` is called and `healthy` returns to True
- Must: AC-F1-4 — If `_reconnect_pool()` fails, `healthy` remains False, worker retries next interval
- Must: AC-F2-1 — `REDIS_ENABLED=False` causes `connect()` to return without pool, `healthy=False`, warning logged
- Must: AC-F6-1 — Disabled startup logs `"redis_disabled_by_config"`
- Must: AC-F6-2 — Connected startup logs `"redis_connected"`
- Must: AC-F6-3 — Connection failure logs `"redis_connection_failed"` mentioning recovery worker
- Must: AC-NFR-1 — Pool reinitialisation completes within `REDIS_TIMEOUT_SECONDS` + 1 second
- Should: Recovery worker loop includes ±10% jitter on sleep

**Files and modules**:

- `src/real-estate-api/app/services/redis_client.py` (updated — major edits throughout)
- `src/real-estate-api/app/main.py` (updated — remove `_periodic_health_check`, simplify lifespan)

**Tests**:

- Manual: `python -m pytest src/real-estate-api/tests/ -v -k "redis"` (after test phase)
- Manual: Run app with `REDIS_ENABLED=false`, verify startup log
- Manual: Run app with `REDIS_ENABLED=true` and no Redis, verify degraded startup log + recovery worker active

**Completion signal**: `feat(STORY-27): add recovery worker, reconnect, and REDIS_ENABLED to RedisClient`

---

### Phase 3: Metrics — Add `redis_degraded` Prometheus gauge

**Goal**: Define a new Prometheus gauge `redis_degraded` (no labels) and wire it to state
transitions in `RedisClient`. The gauge is 0 when Redis is healthy or disabled, 1 when
Redis is degraded (healthy=False AND REDIS_ENABLED=True).

**Tasks**:

- [ ] **3.1** Add `redis_degraded: Gauge` to `src/real-estate-api/app/core/metrics.py`:
  ```python
  redis_degraded: Gauge = Gauge(
      "redis_degraded",
      "Redis cache layer degraded (1) or healthy/disabled (0)",
  )
  ```
  - Place after existing gauges (after `cache_entry_size_bytes`, line ~57)
  - Import `Gauge` (already imported)

- [ ] **3.2** Wire gauge updates in `RedisClient` (`src/real-estate-api/app/services/redis_client.py`):
  - Import `redis_degraded` from `app.core.metrics`
  - In `ping()`:
    - When `healthy` transitions from `False` to `True`: `redis_degraded.set(0)`
    - When `healthy` transitions from `True` to `False` (threshold reached): `redis_degraded.set(1)`
  - In `_reconnect_pool()`:
    - After successful reconnect: `redis_degraded.set(0)`
  - In `connect()`:
    - When `REDIS_ENABLED=False`: `redis_degraded.set(0)` (disabled, not degraded)
    - When connection fails: `redis_degraded.set(1)` (degraded at startup)
    - When connection succeeds: `redis_degraded.set(0)`

**Acceptance Criteria**:

- Must: AC-F4-1 — Gauge transitions 0→1 on healthy→degraded transition
- Must: AC-F4-2 — Gauge transitions 1→0 on recovery via `_reconnect_pool()`
- Must: AC-F4-3 — Gauge is 0 when `REDIS_ENABLED=False` at startup
- Must: NFR-5 — Gauge updated within 1 second of any state transition

**Files and modules**:

- `src/real-estate-api/app/core/metrics.py` (updated — add gauge)
- `src/real-estate-api/app/services/redis_client.py` (updated — wire gauge set calls)

**Tests**:

- Covered by unit tests in Phase 7 that assert gauge values

**Completion signal**: `feat(STORY-27): add redis_degraded Prometheus gauge`

---

### Phase 4: Readiness endpoint `GET /ready` and health response update

**Goal**: Add `GET /ready` readiness endpoint returning HTTP 200/503 with dependency health.
Update `GET /health` to return `"redis": "disabled"` when `REDIS_ENABLED=False`.

**Tasks**:

- [ ] **4.1** Create `src/real-estate-api/app/routers/readiness.py`:
  - New router module with `router = APIRouter(tags=["readiness"])`
  - Import `structlog`, `APIRouter`, `Request`, `time`, `get_settings`
  - Helper `_get_redis_client(request)` same pattern as `health.py`
  - Endpoint `GET /ready`:
    ```python
    @router.get("/ready")
    async def readiness_check(request: Request) -> JSONResponse:
        settings = get_settings()
        redis_client = _get_redis_client(request)
        now = time.time()
        elapsed = now - request.app.state.started_at

        if not settings.REDIS_ENABLED:
            return {"ready": True, "redis": "disabled"}

        if redis_client.healthy:
            return {"ready": True, "redis": "ok"}

        # Redis is degraded — check grace period
        if elapsed < settings.REDIS_STARTUP_GRACE_PERIOD:
            return {"ready": True, "redis": "degraded"}

        # Past grace period — not ready
        return JSONResponse(
            status_code=503,
            content={"ready": False, "redis": "degraded"},
        )
    ```
  - Import `JSONResponse` from `starlette.responses`

- [ ] **4.2** Register the readiness router in `main.py`:
  - Add `from app.routers import health, properties, readiness`
  - Add `app.include_router(readiness.router)` after `app.include_router(health.router)`

- [ ] **4.3** Set `app.state.started_at` in the `lifespan` handler:
  - At start of lifespan (before `yield`), set `app.state.started_at = time.time()`
  - Add `import time` at top of `main.py`

- [ ] **4.4** Update `GET /health` in `src/real-estate-api/app/routers/health.py`:
  - Import `get_settings` from `app.core.config`
  - In `health_check()`, get settings and check `REDIS_ENABLED`:
    ```python
    settings = get_settings()
    if not settings.REDIS_ENABLED:
        return {"status": "ok", "redis": "disabled"}
    ```
  - Existing `redis_status` logic unchanged for enabled case

**Acceptance Criteria**:

- Must: AC-F3-1 — `/ready` returns HTTP 200 with `"ready": true` when Redis ok or disabled
- Must: AC-F3-2 — `/ready` returns HTTP 503 with `"ready": false` when Redis degraded past grace period
- Must: AC-F3-3 — `/ready` returns HTTP 200 with `"ready": true` when Redis degraded within grace period
- Must: AC-F2-2 — `/health` returns `"redis": "disabled"` when `REDIS_ENABLED=False`
- Must: NFR-2 — `/ready` p95 response time < 5 ms

**Files and modules**:

- `src/real-estate-api/app/routers/readiness.py` (new)
- `src/real-estate-api/app/routers/health.py` (updated — add disabled check)
- `src/real-estate-api/app/main.py` (updated — register readiness router, set started_at)

**Tests**:

- See Phase 7 test scenarios for `/ready` endpoint tests

**Completion signal**: `feat(STORY-27): add GET /ready readiness endpoint and update health response`

---

### Phase 5: Prometheus alert rule — `RedisDegraded`

**Goal**: Add a `RedisDegraded` Prometheus alert rule that fires when `redis_degraded == 1`
for more than 5 minutes.

**Tasks**:

- [ ] **5.1** Add a new alerting group to `docker/prometheus/alert-rules.yml`:
  ```yaml
  - name: redis
    rules:
      - alert: RedisDegraded
        expr: redis_degraded == 1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Redis cache layer degraded for > 5 minutes"
          description: "Redis has been degraded for {{ $value | humanizeDuration }}. API responses are served from the database without caching. Check Redis pod and network connectivity."
  ```
  - Place after the `scrapers` group (separate group named `redis`)
  - Indentation: 2-space per Prometheus YAML convention

**Acceptance Criteria**:

- Must: AC-F5-1 — Alert fires when `redis_degraded == 1` for > 5 minutes
- Must: AC-F5-2 — Alert does not fire if `redis_degraded` returns to 0 within 5 minutes
- Must: Alert severity is `warning`, group name is `redis`

**Files and modules**:

- `docker/prometheus/alert-rules.yml` (updated)

**Tests**:

- Manual: Validate YAML syntax: `python -c "import yaml; yaml.safe_load(open('docker/prometheus/alert-rules.yml'))"`
- Manual: Validate with `promtool check rules docker/prometheus/alert-rules.yml`

**Completion signal**: `feat(STORY-27): add RedisDegraded Prometheus alert rule`

---

### Phase 6: Tests — Unit and integration tests for all new functionality

**Goal**: Write comprehensive tests for recovery worker, `reconnect()`, disabled mode,
readiness endpoint, and gauge wiring. All tests use `fakeredis` and the existing conftest
fixtures. Create new test file `test_redis_client.py` and update `test_health.py`.

**Tasks**:

- [ ] **6.1** Create `src/real-estate-api/tests/test_redis_client.py` with the following test
  functions (all `@pytest.mark.asyncio`):

  | Test function | What it verifies | AC |
  |---|---|---|
  | `test_connect_when_redis_enabled` | Calling `connect()` with default config creates `_pool` and `_redis`, sets `healthy=True` | F-2 |
  | `test_connect_when_redis_disabled` | `REDIS_ENABLED=False` causes early return, no pool, `healthy=False` | AC-F2-1 |
  | `test_connect_when_redis_disabled_sets_gauge_zero` | Gauge is 0 when disabled | AC-F4-3 |
  | `test_recovery_worker_starts_on_connect` | Recovery task created after `connect()` | AC-F1-1 |
  | `test_recovery_worker_idles_when_healthy` | When `healthy=True`, worker sleeps without pinging (use `asyncio.sleep(0.1)` with mock) | AC-F1-1 |
  | `test_recovery_worker_pings_on_degraded` | When `healthy=False`, worker calls `ping()` on next cycle | AC-F1-2 |
  | `test_reconnect_pool_reinitialises_connection` | `_reconnect_pool()` disconnects old pool, creates new one, verifies with ping | DEC-1 |
  | `test_reconnect_pool_handles_failure` | If verify ping fails after reconnect, healthy stays False | AC-F1-4 |
  | `test_recovery_worker_reconnects_on_recovery` | Worker calls `_reconnect_pool()` when ping succeeds after degradation | AC-F1-3 |
  | `test_recovery_worker_stops_on_disconnect` | Calling `disconnect()` cancels recovery worker task | AC-F1-1 implicit |
  | `test_ping_updates_gauge_on_degraded_transition` | Gauge set to 1 when failure threshold reached | AC-F4-1 |
  | `test_ping_updates_gauge_on_recovery` | Gauge set to 0 when ping succeeds after degradation | AC-F4-2 |
  | `test_ping_with_jitter` | Verify sleep interval includes ±10% jitter (mock `asyncio.sleep`, check args) | DEC-6 |

  - Use `fakeredis.FakeAsyncRedis` for the Redis instance
  - Mock `asyncio.sleep` with `unittest.mock.patch` in tests that check timing
  - Use `pytest.mark.mock_redis` or direct assignment: `client._redis = fake_redis`

- [ ] **6.2** Update `src/real-estate-api/tests/test_health.py` — add tests for `/ready`:

  | Test function | What it verifies | AC |
  |---|---|---|
  | `test_ready_returns_200_when_healthy` | `healthy=True` → 200, `"ready": true, "redis": "ok"` | AC-F3-1 |
  | `test_ready_returns_disabled_when_redis_disabled` | `REDIS_ENABLED=False` → 200, `"ready": true, "redis": "disabled"` | AC-F3-1 / AC-F2-2 |
  | `test_ready_returns_degraded_within_grace_period` | Degraded + within 30s → 200, `"ready": true, "redis": "degraded"` | AC-F3-3 |
  | `test_ready_returns_503_after_grace_period` | Degraded + past 30s → 503, `"ready": false, "redis": "degraded"` | AC-F3-2 |
  | `test_ready_returns_degraded_with_grace_override` | Set `REDIS_STARTUP_GRACE_PERIOD=0` → immediate 503 on degraded | AC-F3-2 |
  | `test_health_returns_disabled_when_redis_disabled` | `REDIS_ENABLED=False` → `"redis": "disabled"` | AC-F2-2 |

  - Need to set `app.state.started_at` in the test client fixture
  - Update `conftest.py` if needed — set `app.state.started_at = time.time()` in `app` fixture
  - For grace period tests: mock `time.time()` or set `started_at` to a known value

- [ ] **6.3** Update `src/real-estate-api/tests/conftest.py`:
  - Add `import time` and set `app.state.started_at = time.time()` in the `app` fixture
  - Add `app.state.redis_client._recovery_task = None` override for clean test state
  - Consider adding a helper fixture `degraded_redis_client` that creates a client with `healthy=False`

- [ ] **6.4** Run all tests and verify they pass:
  ```bash
  cd src/real-estate-api && python -m pytest tests/ -v --cov=. --cov-fail-under=80
  ```

**Acceptance Criteria**:

- Must: All new tests pass with `fakeredis` (no real Redis required)
- Must: Existing tests continue to pass (no regressions)
- Must: Test coverage ≥ 80% for `redis_client.py` and `readiness.py`
- Must: Coverage threshold `--cov-fail-under=80` passes
- Should: All test functions have clear docstrings describing the scenario

**Files and modules**:

- `src/real-estate-api/tests/test_redis_client.py` (new)
- `src/real-estate-api/tests/test_health.py` (updated)
- `src/real-estate-api/tests/conftest.py` (updated)

**Tests**:

- `python -m pytest src/real-estate-api/tests/ -v`

**Completion signal**: `test(STORY-27): add tests for recovery worker, disabled mode, and readiness endpoint`

---

### Phase 7: Code Review, Spec Reconciliation, and Finalize

**Goal**: Run all static analysis and fix any issues. Reconcile implementation with spec.
Update the change plan revision log.

**Tasks**:

- [ ] **7.1** Run `ruff check src/real-estate-api/` — fix any lint violations
- [ ] **7.2** Run `mypy src/real-estate-api/` — fix any type errors
- [ ] **7.3** Run `python -m pytest src/real-estate-api/tests/ -v --cov=. --cov-fail-under=80` — verify all tests pass and coverage meets threshold
- [ ] **7.4** Validate Prometheus rules: `promtool check rules docker/prometheus/alert-rules.yml`
- [ ] **7.5** Manual checklist review:
  - [ ] `REDIS_ENABLED=False` → no pool created, `healthy=False`, gauge=0, startup log warning, `/health` returns `disabled`, `/ready` returns 200 with `disabled`
  - [ ] `REDIS_ENABLED=True` + Redis reachable → pool created, `healthy=True`, gauge=0, startup log info, `/health` returns `ok`
  - [ ] `REDIS_ENABLED=True` + Redis unreachable → no pool (but recovery worker active), `healthy=False`, gauge=1, startup log warning, `/health` returns `degraded`, `/ready` returns 503 after grace period
  - [ ] Recovery: Redis comes back → worker pings → `_reconnect_pool()` → `healthy=True`, gauge=0
  - [ ] Shutdown: recovery worker cancelled, pool disconnected
  - [ ] No changes to `CacheService.get_or_compute()` — existing fallback logic unchanged
  - [ ] Existing `GET /health` response shape unchanged (only `redis` value extended)
- [ ] **7.6** Update this plan's revision log (add entry for v1.0)
- [ ] **7.7** Spec reconciliation: verify all ACs from spec are traceable to implementation (mark complete)

**Acceptance Criteria**:

- Must: Zero lint errors from `ruff`
- Must: Zero type errors from `mypy --strict`
- Must: All tests pass with ≥ 80% coverage
- Must: Prometheus rules pass `promtool check rules`
- Must: No regressions in existing behaviours

**Files and modules**:

- All modified files
- This plan file (revision log update)

**Tests**:

- Automated: `ruff check`, `mypy`, `pytest --cov`

**Completion signal**: `chore(STORY-27): finalize — code review, spec reconciliation, and static analysis`

---

## Test Scenarios

| ID | Scenario | Phases | AC |
|----|----------|--------|----|
| TS-1 | Application starts with `REDIS_ENABLED=True` and Redis reachable — pool created, healthy=true, gauge=0, /health → ok, /ready → 200 | 1, 2, 3, 4 | AC-F2-1, AC-F3-1, AC-F6-2 |
| TS-2 | Application starts with `REDIS_ENABLED=False` — no pool, healthy=false (by intent), gauge=0, /health → disabled, /ready → 200 disabled | 1, 2, 3, 4 | AC-F2-1, AC-F2-2, AC-F4-3, AC-F6-1 |
| TS-3 | Application starts with `REDIS_ENABLED=True` and Redis unreachable — no pool, healthy=false (degraded), gauge=1, /health → degraded, /ready → 503 after grace | 1, 2, 3, 4 | AC-F2-1, AC-F3-2, AC-F3-3, AC-F6-3 |
| TS-4 | Redis degrades during operation — healthy transitions to false, gauge→1, /health → degraded | 2, 3 | AC-F4-1 |
| TS-5 | Redis recovers after degradation — worker pings → reconnect → healthy=true, gauge→0, /health → ok | 2, 3 | AC-F1-3, AC-F4-2 |
| TS-6 | Recovery worker reconnects but new pool ping fails — healthy stays false, worker retries | 2 | AC-F1-4 |
| TS-7 | Grace period — /ready returns 200 while degraded within first 30s, 503 after | 4 | AC-F3-2, AC-F3-3 |
| TS-8 | `RedisDegraded` alert fires after 5 min sustained degradation | 5 | AC-F5-1, AC-F5-2 |
| TS-9 | Application shutdown — recovery worker cancelled, pool disconnected cleanly | 2 | NFR-9 |
| TS-10 | `GET /ready` response time p95 < 5ms | 4 | NFR-2 |

## Artifacts and Links

| Artifact | Location | Type |
|----------|----------|------|
| Change specification | `./chg-STORY-27-spec.md` | Spec |
| Implementation plan | `./chg-STORY-27-plan.md` | Plan (this file) |
| Application config | `src/real-estate-api/app/core/config.py` | Source — updated |
| Redis client | `src/real-estate-api/app/services/redis_client.py` | Source — updated |
| Application metrics | `src/real-estate-api/app/core/metrics.py` | Source — updated |
| Application main | `src/real-estate-api/app/main.py` | Source — updated |
| Health router | `src/real-estate-api/app/routers/health.py` | Source — updated |
| Readiness router | `src/real-estate-api/app/routers/readiness.py` | Source — new |
| Prometheus alert rules | `docker/prometheus/alert-rules.yml` | Config — updated |
| Redis client tests | `src/real-estate-api/tests/test_redis_client.py` | Tests — new |
| Health/readiness tests | `src/real-estate-api/tests/test_health.py` | Tests — updated |
| Test fixtures | `src/real-estate-api/tests/conftest.py` | Tests — updated |
| Spec modules | `specs/080-API.md`, `120-CACHING-STORAGE.md`, `130-MONITORING-ALERTS.md` | Spec — reference |

## Plan Revision Log

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-06-24 | plan-writer | Initial plan — 7 phases covering F-1 through F-6 |

## Execution Log

| Phase | Status | Started | Completed | Commit | Notes |
|-------|--------|---------|-----------|--------|-------|
| 1 — Configuration | ⬜ Pending | — | — | — | — |
| 2 — RedisClient recovery worker | ⬜ Pending | — | — | — | — |
| 3 — Metrics gauge | ⬜ Pending | — | — | — | — |
| 4 — Readiness endpoint | ⬜ Pending | — | — | — | — |
| 5 — Prometheus alert rule | ⬜ Pending | — | — | — | — |
| 6 — Tests | ⬜ Pending | — | — | — | — |
| 7 — Code review & finalize | ⬜ Pending | — | — | — | — |
