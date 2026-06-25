# STORY-26 — Implementation Plan

**workItemRef:** STORY-26
**Status:** plan

---

## Phase 1: Config — `real-estate-api/app/core/config.py`

Add Redis Stream configuration:

```python
# Redis Streams
REDIS_STREAM_NEW_PROPERTY: str = "stream:new_property"
REDIS_STREAM_ALERTS_PENDING: str = "stream:alerts:pending"
REDIS_STREAM_DEAD_LETTER: str = "stream:dead_letter"
REDIS_STREAM_CONSUMER_GROUP: str = "alert-workers"
REDIS_STREAM_MAXLEN_NEW_PROPERTY: int = 10_000
REDIS_STREAM_MAXLEN_DEAD_LETTER: int = 1_000
REDIS_STREAM_MAX_RETRIES: int = 3
REDIS_STREAM_POLL_TIMEOUT: int = 5  # seconds for XREADGROUP block
```

## Phase 2: Stream Publisher — `scrapper-base/src/scraper_base/stream_publisher.py`

A fire-and-forget publisher that XADDs to `stream:new_property` after upsert. Follows the same pattern as `CacheInvalidator` (silently skip if Redis unavailable).

```python
class StreamPublisher:
    """Publishes messages to Redis Streams after property upserts."""

    def __init__(self, redis_url: str | None = None):
        """Initialize with optional pool. Disabled if REDIS_URL is absent."""

    async def publish_new_property(
        self,
        property_id: int,
        portal_source: str,
        source_id: str,
        city: str,
        property_type: str | None,
        price: int | None,
        is_new: bool,
    ) -> None:
        """XADD property data to stream:new_property with MAXLEN ~10_000."""

    async def close(self) -> None:
        """Close Redis connection pool."""
```

**Graceful degradation:** If `self._disabled` or Redis error → log and return.

## Phase 3: Services Integration — `scrapper-base/src/scraper_base/services.py`

In `PropertyService.upsert_property()`, after cache invalidation, also call `StreamPublisher`.

Changes:
1. Import `StreamPublisher`
2. Add `self._stream_publisher: StreamPublisher | None` as optional attribute
3. After `self._invalidate_cache()`, call `await self._stream_publisher.publish_new_property(...)`
4. Add `set_stream_publisher()` setter method

## Phase 4: Stream Manager — `real-estate-api/app/services/stream_manager.py`

A helper module for Redis Stream operations with retry/dead-letter logic.

```python
STREAM_NAMES = {
    "new_property": "stream:new_property",
    "dead_letter": "stream:dead_letter",
}

async def ensure_consumer_group(
    redis: RedisClient,
    stream: str,
    group: str,
) -> None:
    """Create consumer group if it doesn't exist (ignore BUSYGROUP error)."""

async def process_with_retry(
    redis: RedisClient,
    stream: str,
    group: str,
    msg_id: str,
    data: dict,
    handler: Callable[[dict], Awaitable[None]],
    max_retries: int = 3,
    dead_letter_stream: str = "stream:dead_letter",
) -> None:
    """Process a message with retry and dead-letter on exhaustion."""
```

## Phase 5: Alert Worker — `real-estate-api/app/workers/alert_worker.py`

A background task that continuously reads from `stream:new_property`.

```python
class AlertWorker:
    """Background consumer of stream:new_property with retry/dead-letter."""

    def __init__(self, redis_client: RedisClient):
        self._redis = redis_client
        self._task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        """Create consumer group, start background consume loop."""
        await ensure_consumer_group(...)
        self._task = asyncio.create_task(self._consume_loop())

    async def stop(self) -> None:
        """Cancel the consume loop task."""
        self._running = False
        if self._task:
            self._task.cancel()
            try: await self._task
            except CancelledError: pass

    async def _consume_loop(self) -> None:
        """XREADGROUP loop with retry/dead-letter."""
        while self._running:
            messages = await self._redis.xreadgroup(...)
            for stream_name, msgs in messages:
                for msg_id, data in msgs:
                    await process_with_retry(
                        self._redis, stream_name, group, msg_id, data,
                        handler=self._handle_message,
                    )

    async def _handle_message(self, data: dict) -> None:
        """Handle a single message from stream:new_property.
        
        Currently: log the message (alert matching is STORY-42).
        Actual alert matching + XADD to stream:alerts:pending is future work.
        """
        logger.info("new_property_received", ...)
```

## Phase 6: App Lifespan — `real-estate-api/app/main.py`

In the lifespan handler, start the AlertWorker on startup and stop it on shutdown.

## Phase 7: Tests

### scrapper-base tests

| Test | What it verifies |
|------|------------------|
| `test_stream_publisher_publishes_message` | XADD is called with correct stream/key/data |
| `test_stream_publisher_disabled_no_redis` | Silently skipped when Redis not configured |
| `test_stream_publisher_graceful_error` | No crash on Redis error |

### real-estate-api tests

| Test | What it verifies |
|------|------------------|
| `test_ensure_consumer_group_creates_group` | Consumer group created |
| `test_ensure_consumer_group_exists_already` | BUSYGROUP handled |
| `test_process_with_retry_success` | Message processed and XACK'd |
| `test_process_with_retry_retry_then_dead_letter` | After 3 failures, goes to dead_letter |
| `test_process_with_retry_retry_then_success` | Retry succeeds and XACK'd |
| `test_alert_worker_start_stop` | Worker lifecycle clean |

## Phase 8: Quality Gates

- `ruff check .` — no new lint warnings
- `mypy . --strict` — no new type errors
- `pytest tests/ -v` — all tests pass
