"""
Redis Stream management helpers for the real-estate-api.

Provides consumer group creation, message processing with retry and
dead-letter semantics, and stream configuration constants.

Usage::

    from app.services.stream_manager import ensure_consumer_group, process_with_retry

    # On worker startup
    await ensure_consumer_group(redis_client, "stream:new_property", "alert-workers")

    # For each message
    async def handle(data: dict) -> None:
        ...

    await process_with_retry(redis_client, stream, group, msg_id, data, handle)
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import structlog
from redis.exceptions import RedisError, ResponseError

from app.services.redis_client import RedisClient

logger = structlog.get_logger(__name__)

# ── Default configuration ─────────────────────────────────────────────────

DEAD_LETTER_STREAM: str = "stream:dead_letter"
MAXLEN_DEAD_LETTER: int = 1_000
DEFAULT_MAX_RETRIES: int = 3


async def ensure_consumer_group(
    redis: RedisClient,
    stream: str,
    group: str,
) -> bool:
    """Ensure a consumer group exists for the given stream.

    Creates the consumer group if it does not already exist. If the stream
    does not exist yet, it is created implicitly (via ``XGROUP CREATE`` with
    ``mkstream``).

    Args:
        redis: The ``RedisClient`` instance.
        stream: Stream key (e.g. ``"stream:new_property"``).
        group: Consumer group name (e.g. ``"alert-workers"``).

    Returns:
        ``True`` if the group exists or was created, ``False`` if Redis is
        unavailable.

    """
    if not redis.healthy or redis._redis is None:  # noqa: SLF001
        logger.warning(
            "ensure_consumer_group_skipped",
            reason="redis_unavailable",
            stream=stream,
            group=group,
        )
        return False

    try:
        await redis._redis.xgroup_create(  # noqa: SLF001
            name=stream,
            groupname=group,
            id="$",
            mkstream=True,
        )
        logger.info(
            "consumer_group_created",
            stream=stream,
            group=group,
        )
    except ResponseError as exc:
        # BUSYGROUP: Consumer group name already exists
        if "BUSYGROUP" in str(exc):
            logger.debug(
                "consumer_group_already_exists",
                stream=stream,
                group=group,
            )
        else:
            logger.warning(
                "consumer_group_creation_failed",
                error=str(exc),
                stream=stream,
                group=group,
            )
            return False

    return True


async def process_with_retry(
    redis: RedisClient,
    stream: str,
    group: str,
    msg_id: str,
    data: dict[str, Any],
    handler: Callable[[dict[str, Any]], Awaitable[None]],
    max_retries: int = DEFAULT_MAX_RETRIES,
    dead_letter_stream: str = DEAD_LETTER_STREAM,
) -> None:
    """Process a Redis Stream message with retry and dead-letter semantics.

    Attempts to process the message via the given ``handler``. On success,
    acknowledges the message (``XACK``). On failure, checks the retry count
    in the message data and either re-enqueues it (with ``_retries + 1``) or
    moves it to the dead-letter stream.

    The dead-letter message includes the original stream, message ID, error
    details, and the original data for debugging.

    Args:
        redis: The ``RedisClient`` instance.
        stream: The source stream name.
        group: The consumer group name.
        msg_id: The message ID to acknowledge.
        data: The message data dict (must be JSON-decodable values).
        handler: Async callable that processes the message payload.
        max_retries: Maximum retry attempts before dead-letter.
        dead_letter_stream: Stream name for dead-letter messages.

    """
    if not redis.healthy or redis._redis is None:  # noqa: SLF001
        logger.warning(
            "process_with_retry_skipped",
            reason="redis_unavailable",
            msg_id=msg_id,
            stream=stream,
        )
        return

    try:
        # Parse the actual payload from the message
        payload_str = data.get("data", "{}")
        if isinstance(payload_str, str):
            payload = json.loads(payload_str)
        elif isinstance(payload_str, dict):
            payload = payload_str
        else:
            payload = {}

        await handler(payload)
        await redis._redis.xack(stream, group, msg_id)  # noqa: SLF001
        logger.debug(
            "message_processed_and_acked",
            msg_id=msg_id,
            stream=stream,
        )

    except Exception as exc:  # noqa: BLE001
        retries = int(data.get("_retries", 0))

        if retries >= max_retries:
            # Move to dead-letter stream
            try:
                dead_letter_data = {
                    "origin_stream": stream,
                    "msg_id": msg_id,
                    "error": str(exc),
                    "data": json.dumps(payload) if isinstance(payload_str, str) else str(payload_str),
                    "timestamp": datetime.now(UTC).isoformat(),
                }
                await redis._redis.xadd(  # noqa: SLF001
                    dead_letter_stream,
                    fields=dead_letter_data,  # type: ignore[arg-type]
                    maxlen=MAXLEN_DEAD_LETTER,
                    approximate=True,
                )
                await redis._redis.xack(stream, group, msg_id)  # noqa: SLF001
                logger.warning(
                    "message_moved_to_dead_letter",
                    msg_id=msg_id,
                    stream=stream,
                    dead_letter=dead_letter_stream,
                    retries=retries,
                    error=str(exc),
                )
            except RedisError:
                logger.exception(
                    "dead_letter_operation_failed",
                    msg_id=msg_id,
                    stream=stream,
                )
        else:
            # Re-enqueue with incremented retry count
            try:
                data["_retries"] = retries + 1
                await redis._redis.xadd(  # noqa: SLF001
                    stream,
                    fields=data,  # type: ignore[arg-type]
                    maxlen=MAXLEN_DEAD_LETTER,
                    approximate=True,
                )
                await redis._redis.xack(stream, group, msg_id)  # noqa: SLF001
                logger.warning(
                    "message_re_enqueued_for_retry",
                    msg_id=msg_id,
                    stream=stream,
                    retry=retries + 1,
                    max_retries=max_retries,
                    error=str(exc),
                )
            except RedisError:
                logger.exception(
                    "retry_enqueue_failed",
                    msg_id=msg_id,
                    stream=stream,
                )
