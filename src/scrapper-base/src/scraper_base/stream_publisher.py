"""
Stream publisher — publishes property upsert events to Redis Streams.

After a property upsert, the publisher sends a message to ``stream:new_property``
so that downstream consumers (Alert Worker, Email Worker) can react in real time.

Graceful degradation: if ``REDIS_URL`` env var is absent or a Redis error
occurs, publishing is silently skipped and the write path is unaffected.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime

import structlog
from prometheus_client import Counter
from redis.asyncio import ConnectionPool, Redis
from redis.exceptions import RedisError

logger = structlog.get_logger(__name__)

# ── Prometheus metrics ─────────────────────────────────────────────────────

stream_publish_total: Counter = Counter(
    "stream_publish_total",
    "Total number of Redis Stream publish attempts",
    ["stream", "status"],
)

# ── Stream configuration ──────────────────────────────────────────────────

NEW_PROPERTY_STREAM: str = "stream:new_property"
MAXLEN_NEW_PROPERTY: int = 10_000


class StreamPublisher:
    """Publishes messages to Redis Streams after property upserts.

    The publisher is a *fire-and-forget* helper — it never raises and never
    blocks the caller. If Redis is not configured or unreachable, publishing
    is silently skipped.
    """

    def __init__(
        self,
        redis_url: str | None = None,
        *,
        pool: ConnectionPool | None = None,
    ) -> None:
        """Initialise the publisher.

        Args:
            redis_url: Redis connection URL. Falls back to ``REDIS_URL`` env
                var. If *both* are ``None``, publishing is disabled.
            pool: An optional pre-existing ``ConnectionPool``. If given,
                ``redis_url`` is ignored.
        """
        self._pool: ConnectionPool | None = pool
        self._redis: Redis | None = None
        self._disabled: bool = False

        url = redis_url or os.environ.get("REDIS_URL")
        if url is None:
            self._disabled = True
            logger.info("stream_publisher_disabled", reason="REDIS_URL not configured")
            return

        if self._pool is None:
            try:
                self._pool = ConnectionPool.from_url(
                    url,
                    max_connections=2,
                    timeout=2,
                )
            except Exception as exc:
                logger.warning("stream_publisher_pool_creation_failed", error=str(exc))
                self._disabled = True
                return

        self._redis = Redis(connection_pool=self._pool)

    @property
    def is_disabled(self) -> bool:
        """Return ``True`` if the publisher is not connected to Redis."""
        return self._disabled or self._redis is None

    async def publish_new_property(
        self,
        property_id: int,
        portal_source: str,
        source_id: str,
        city: str,
        property_type: str | None = None,
        price: int | None = None,
        is_new: bool = False,
    ) -> None:
        """Publish a property upsert event to ``stream:new_property``.

        Args:
            property_id: The upserted property's database ID.
            portal_source: Portal source identifier (e.g. ``"otodom"``).
            source_id: Source-specific identifier.
            city: The property city name.
            property_type: Property type (e.g. ``"apartment"``).
            price: Property price in PLN.
            is_new: ``True`` if this is a new insert, ``False`` for update.
        """
        if self._disabled or self._redis is None:
            stream_publish_total.labels(
                stream=NEW_PROPERTY_STREAM,
                status="skipped",
            ).inc()
            return

        message: dict[str, object] = {
            "property_id": property_id,
            "portal_source": portal_source,
            "source_id": source_id,
            "city": city,
            "property_type": property_type or "",
            "price": price or 0,
            "is_new": is_new,
            "updated_at": datetime.now(UTC).isoformat(),
        }

        try:
            await self._redis.xadd(
                NEW_PROPERTY_STREAM,
                fields={"data": json.dumps(message, ensure_ascii=False, default=str)},
                maxlen=MAXLEN_NEW_PROPERTY,
                approximate=True,
            )
            stream_publish_total.labels(
                stream=NEW_PROPERTY_STREAM,
                status="success",
            ).inc()
            logger.debug(
                "stream_new_property_published",
                property_id=property_id,
                portal_source=portal_source,
                is_new=is_new,
            )
        except RedisError:
            logger.exception(
                "stream_publish_failed",
                stream=NEW_PROPERTY_STREAM,
                property_id=property_id,
            )
            stream_publish_total.labels(
                stream=NEW_PROPERTY_STREAM,
                status="fail",
            ).inc()

    async def close(self) -> None:
        """Close the underlying Redis connection pool, if owned."""
        if self._pool is not None:
            await self._pool.disconnect()
