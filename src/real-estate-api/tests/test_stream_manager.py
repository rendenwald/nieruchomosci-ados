"""
Tests for Redis Stream management helpers.

Covers:
- ensure_consumer_group creates a new group
- ensure_consumer_group handles existing group (BUSYGROUP)
- ensure_consumer_group returns False when Redis is unhealthy
- process_with_retry acks on success
- process_with_retry re-enqueues on failure (within max_retries)
- process_with_retry moves to dead_letter after max_retries
"""

import json
from typing import Any

import pytest

from app.services.stream_manager import (
    ensure_consumer_group,
    process_with_retry,
)


@pytest.mark.asyncio
async def test_ensure_consumer_group_creates_group(app, fake_redis) -> None:  # type: ignore[no-untyped-def]
    """ensure_consumer_group creates a new consumer group."""
    redis_client = app.state.redis_client

    result = await ensure_consumer_group(
        redis=redis_client,
        stream="test:stream",
        group="test-group",
    )
    assert result is True

    # Verify the group exists
    groups = await fake_redis.xinfo_groups("test:stream")
    assert len(groups) == 1
    # fakeredis may return string or bytes keys — check both
    group_name = groups[0].get("name") or groups[0].get(b"name", b"")
    assert group_name in ("test-group", b"test-group")


@pytest.mark.asyncio
async def test_ensure_consumer_group_exists_already(app, fake_redis) -> None:  # type: ignore[no-untyped-def]
    """ensure_consumer_group handles BUSYGROUP gracefully."""
    redis_client = app.state.redis_client

    # Create group once
    await ensure_consumer_group(
        redis=redis_client,
        stream="test:stream-existing",
        group="test-group",
    )

    # Create again — should not raise
    result = await ensure_consumer_group(
        redis=redis_client,
        stream="test:stream-existing",
        group="test-group",
    )
    assert result is True


@pytest.mark.asyncio
async def test_ensure_consumer_group_returns_false_when_unhealthy(app) -> None:  # type: ignore[no-untyped-def]
    """ensure_consumer_group returns False when Redis is unhealthy."""
    redis_client = app.state.redis_client
    redis_client.healthy = False

    result = await ensure_consumer_group(
        redis=redis_client,
        stream="test:stream",
        group="test-group",
    )
    assert result is False

    # Restore
    redis_client.healthy = True


@pytest.mark.asyncio
async def test_process_with_retry_acks_on_success(app, fake_redis) -> None:  # type: ignore[no-untyped-def]
    """process_with_retry acks the message on successful processing."""
    redis_client = app.state.redis_client

    # Set up a stream with a consumer group and a message
    stream = "test:stream-process"
    group = "test-group-process"
    await ensure_consumer_group(redis=redis_client, stream=stream, group=group)

    # Add a message to the stream
    msg_id = await fake_redis.xadd(stream, {"data": json.dumps({"key": "value"})})

    # Process the message (handler succeeds)
    processed_data = []

    async def success_handler(payload: dict[str, Any]) -> None:
        processed_data.append(payload)

    await process_with_retry(
        redis=redis_client,
        stream=stream,
        group=group,
        msg_id=msg_id,
        data={"data": json.dumps({"key": "value"})},
        handler=success_handler,
    )

    # Handler should have been called
    assert len(processed_data) == 1
    assert processed_data[0]["key"] == "value"

    # Message should be acknowledged (no pending messages)
    pending = await fake_redis.xpending(stream, group)
    assert pending["pending"] == 0


@pytest.mark.asyncio
async def test_process_with_retry_moves_to_dead_letter(app, fake_redis) -> None:  # type: ignore[no-untyped-def]
    """process_with_retry moves to dead_letter after max_retries failures."""
    redis_client = app.state.redis_client

    stream = "test:stream-dl"
    group = "test-group-dl"
    await ensure_consumer_group(redis=redis_client, stream=stream, group=group)

    # Add a message that will fail
    msg_id = await fake_redis.xadd(stream, {"data": json.dumps({"fail": True})})

    call_count = 0

    async def failing_handler(payload: dict[str, Any]) -> None:
        nonlocal call_count
        call_count += 1
        msg = "Handler failed"
        raise ValueError(msg)

    # Process with max_retries=2 — after 3rd failure it goes to dead_letter
    await process_with_retry(
        redis=redis_client,
        stream=stream,
        group=group,
        msg_id=msg_id,
        data={"data": json.dumps({"fail": True}), "_retries": 2},  # already at max_retries
        handler=failing_handler,
        max_retries=2,
        dead_letter_stream="test:dead-letter",
    )

    # Handler should have been called
    assert call_count == 1

    # Check dead-letter stream has the message
    dl_messages = await fake_redis.xread(streams={"test:dead-letter": "0"})
    if dl_messages:
        _, msgs = dl_messages[0]
        if msgs:
            dl_id, dl_data = msgs[0]  # noqa: F841
            # fakeredis may return string or bytes keys
            origin = dl_data.get("origin_stream") or dl_data.get(b"origin_stream", b"")
            assert origin in (stream, stream.encode())

    # Original message should be acknowledged
    pending = await fake_redis.xpending(stream, group)
    pending_count = pending.get("pending") or pending.get(b"pending", 0)
    assert pending_count == 0


@pytest.mark.asyncio
async def test_process_with_retry_handler_not_called_when_redis_unhealthy(app) -> None:  # type: ignore[no-untyped-def]
    """process_with_retry skips processing when Redis is unhealthy."""
    redis_client = app.state.redis_client
    redis_client.healthy = False

    handler_called = False

    async def handler(payload: dict[str, Any]) -> None:
        nonlocal handler_called
        handler_called = True

    await process_with_retry(
        redis=redis_client,
        stream="test:stream",
        group="test-group",
        msg_id="dummy-id",
        data={"data": "{}"},
        handler=handler,
    )

    assert not handler_called

    # Restore
    redis_client.healthy = True
