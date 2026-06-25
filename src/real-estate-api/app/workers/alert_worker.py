"""
Alert Worker — consumes ``stream:new_property`` for real-time alert delivery.

The Alert Worker is a background ``asyncio.Task`` that continuously reads
messages from the ``stream:new_property`` Redis Stream using ``XREADGROUP``.
Each message is processed via ``process_with_retry()`` for reliable delivery
with retry and dead-letter semantics.

Current implementation logs received messages. Actual alert matching against
user-defined criteria will be added in STORY-42+.
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog
from redis.asyncio import Redis as AsyncRedis

from app.core.config import get_settings
from app.services.redis_client import RedisClient
from app.services.stream_manager import (
    ensure_consumer_group,
    process_with_retry,
)

logger = structlog.get_logger(__name__)


class AlertWorker:
    """Background consumer of ``stream:new_property``.

    Subscribes to the Redis Stream consumer group and processes new property
    events with retry and dead-letter semantics.

    Usage::

        worker = AlertWorker(redis_client)
        await worker.start()   # creates consumer group + starts consume loop
        ...
        await worker.stop()    # cancels the consume loop
    """

    def __init__(self, redis_client: RedisClient) -> None:
        self._redis = redis_client
        self._settings = get_settings()
        self._task: asyncio.Task[Any] | None = None
        self._running: bool = False
        self._log = logger.bind(worker="alert")

    async def start(self) -> None:
        """Start the Alert Worker.

        Creates/joins the consumer group and starts the background consume
        loop. If Redis is unavailable, logs a warning and returns without
        starting.
        """
        if not self._redis.healthy:
            self._log.warning("alert_worker_not_started_redis_unhealthy")
            return

        # Ensure the consumer group exists
        group_ok = await ensure_consumer_group(
            redis=self._redis,
            stream=self._settings.REDIS_STREAM_NEW_PROPERTY,
            group=self._settings.REDIS_STREAM_CONSUMER_GROUP,
        )

        if not group_ok:
            self._log.warning("alert_worker_no_consumer_group")
            return

        self._running = True
        self._task = asyncio.create_task(self._consume_loop())
        self._log.info(
            "alert_worker_started",
            stream=self._settings.REDIS_STREAM_NEW_PROPERTY,
            group=self._settings.REDIS_STREAM_CONSUMER_GROUP,
        )

    async def stop(self) -> None:
        """Stop the Alert Worker gracefully.

        Sets the running flag to ``False`` and cancels the consume loop task.
        """
        self._running = False
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        self._log.info("alert_worker_stopped")

    async def _consume_loop(self) -> None:
        """Continuously read messages from ``stream:new_property``.

        Uses ``XREADGROUP`` with blocking reads (``BLOCK``) to wait for new
        messages. Each message is processed via ``process_with_retry()``.
        """
        consumer_name = f"alert-worker-{id(self)}"

        while self._running:
            try:
                if not self._redis.healthy or self._redis._redis is None:  # noqa: SLF001
                    await asyncio.sleep(5)
                    continue

                raw_redis: AsyncRedis = self._redis._redis  # noqa: SLF001

                # Blocking read from the consumer group
                response = await raw_redis.xreadgroup(
                    groupname=self._settings.REDIS_STREAM_CONSUMER_GROUP,
                    consumername=consumer_name,
                    streams={self._settings.REDIS_STREAM_NEW_PROPERTY: ">"},
                    count=10,
                    block=self._settings.REDIS_STREAM_POLL_TIMEOUT * 1000,  # ms
                )

                if not response:
                    continue

                # response is a list of (stream_name, messages) tuples
                for stream_name, messages in response:
                    for msg_id, msg_data in messages.items():
                        await process_with_retry(
                            redis=self._redis,
                            stream=stream_name,
                            group=self._settings.REDIS_STREAM_CONSUMER_GROUP,
                            msg_id=msg_id,
                            data=msg_data,
                            handler=self._handle_message,
                            max_retries=self._settings.REDIS_STREAM_MAX_RETRIES,
                        )

            except asyncio.CancelledError:
                self._log.debug("alert_worker_consume_loop_cancelled")
                break
            except Exception:  # noqa: BLE001
                self._log.exception("alert_worker_consume_loop_error")
                await asyncio.sleep(5)

    async def _handle_message(self, payload: dict[str, Any]) -> None:
        """Handle a single message from ``stream:new_property``.

        Args:
            payload: The deserialized message data containing property
                information (property_id, portal_source, city, etc.).

        Note:
            This is a placeholder handler that logs the received property.
            Actual alert matching against user-defined criteria will be
            implemented in STORY-42+.

        """
        property_id = payload.get("property_id")
        portal_source = payload.get("portal_source")
        city = payload.get("city")
        is_new = payload.get("is_new", False)

        self._log.info(
            "new_property_received",
            property_id=property_id,
            portal_source=portal_source,
            city=city,
            is_new=is_new,
        )
