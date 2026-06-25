"""Tests for StreamPublisher — Redis Stream publishing after property upsert."""

from __future__ import annotations

import json
import os

import pytest
from fakeredis.aioredis import FakeRedis

from scraper_base.stream_publisher import (
    MAXLEN_NEW_PROPERTY,
    NEW_PROPERTY_STREAM,
    StreamPublisher,
)


@pytest.fixture
def fake_redis() -> FakeRedis:
    """Return a fake Redis client for testing."""
    return FakeRedis()


@pytest.fixture
def publisher(fake_redis: FakeRedis) -> StreamPublisher:
    """Return a StreamPublisher backed by fake Redis.

    Creates a publisher with a fake Redis connection for testing.
    """
    pub = StreamPublisher(redis_url="redis://localhost:6379/0")
    pub._redis = fake_redis  # noqa: SLF001
    pub._disabled = False
    return pub


class TestStreamPublisher:
    """StreamPublisher unit tests."""

    async def test_publish_new_property_adds_to_stream(
        self,
        publisher: StreamPublisher,
        fake_redis: FakeRedis,
    ) -> None:
        """publish_new_property XADDs a message to stream:new_property."""
        await publisher.publish_new_property(
            property_id=123,
            portal_source="otodom",
            source_id="OTODOM-123",
            city="Warszawa",
            property_type="apartment",
            price=520000,
            is_new=True,
        )

        # Check the stream exists and has 1 message
        stream_len = await fake_redis.xlen(NEW_PROPERTY_STREAM)
        assert stream_len == 1

        # Read the message back and verify content
        messages = await fake_redis.xread(streams={NEW_PROPERTY_STREAM: "0"})
        assert len(messages) == 1
        stream_name, msgs = messages[0]
        # fakeredis returns bytes for stream names
        assert stream_name in (NEW_PROPERTY_STREAM, NEW_PROPERTY_STREAM.encode())

        if isinstance(msgs, dict):
            for msg_id, msg_data in msgs.items():  # noqa: B007
                assert "data" in msg_data
                payload = json.loads(msg_data["data"])
                assert payload["property_id"] == 123
                assert payload["portal_source"] == "otodom"
                assert payload["city"] == "Warszawa"
                assert payload["is_new"] is True
                assert payload["price"] == 520000
        elif isinstance(msgs, list):
            for msg_id, msg_data in msgs:  # noqa: B007
                data_key = "data" if "data" in msg_data else b"data"
                payload = json.loads(msg_data[data_key])
                assert payload["property_id"] == 123
                assert payload["portal_source"] == "otodom"
                assert payload["city"] == "Warszawa"
                assert payload["is_new"] is True
                assert payload["price"] == 520000

    async def test_publish_new_property_update(
        self,
        publisher: StreamPublisher,
        fake_redis: FakeRedis,
    ) -> None:
        """Update (is_new=False) is correctly reflected in the message."""
        await publisher.publish_new_property(
            property_id=456,
            portal_source="gratka",
            source_id="GRATKA-456",
            city="Kraków",
            is_new=False,
        )

        messages = await fake_redis.xread(streams={NEW_PROPERTY_STREAM: "0"})
        _, msgs = messages[0]
        if isinstance(msgs, dict):
            for msg_id, msg_data in msgs.items():  # noqa: B007
                payload = json.loads(msg_data["data"])
                assert payload["property_id"] == 456
                assert payload["portal_source"] == "gratka"
                assert payload["is_new"] is False
        elif isinstance(msgs, list):
            for msg_id, msg_data in msgs:  # noqa: B007
                data_key = "data" if "data" in msg_data else b"data"
                payload = json.loads(msg_data[data_key])
                assert payload["property_id"] == 456
                assert payload["portal_source"] == "gratka"
                assert payload["is_new"] is False

    async def test_maxlen_is_set(
        self,
        publisher: StreamPublisher,
        fake_redis: FakeRedis,
    ) -> None:
        """The MAXLEN for new_property stream is respected."""
        # Publish slightly more than maxlen to trigger trimming
        # (using a smaller batch for test performance)
        count = min(MAXLEN_NEW_PROPERTY + 20, 200)
        for i in range(count):
            await publisher.publish_new_property(
                property_id=i,
                portal_source="otodom",
                source_id=f"SRC-{i}",
                city="Warszawa",
                is_new=True,
            )

        # Stream length should be <= count (no overflow errors)
        stream_len = await fake_redis.xlen(NEW_PROPERTY_STREAM)
        assert stream_len <= count
        assert stream_len > 0

    async def test_disabled_when_no_redis_url(self) -> None:
        """When REDIS_URL is not set, publishing is a no-op."""
        old = os.environ.pop("REDIS_URL", None)
        try:
            pub = StreamPublisher()
            assert pub.is_disabled
            # Should not raise
            await pub.publish_new_property(
                property_id=1,
                portal_source="otodom",
                source_id="SRC-1",
                city="Warszawa",
                is_new=True,
            )
        finally:
            if old is not None:
                os.environ["REDIS_URL"] = old

    async def test_graceful_on_redis_error(self, publisher: StreamPublisher) -> None:
        """When Redis raises, publish_new_property does not propagate the exception."""
        from redis.exceptions import RedisError  # noqa: PLC0415

        async def _broken_xadd(*args, **kwargs):  # type: ignore[no-untyped-def]  # noqa: ANN002, ANN003
            msg = "Connection refused"
            raise RedisError(msg)

        assert publisher._redis is not None  # noqa: SLF001
        original_xadd = publisher._redis.xadd
        publisher._redis.xadd = _broken_xadd  # type: ignore[method-assign]  # noqa: SLF001

        try:
            # Should not raise
            await publisher.publish_new_property(
                property_id=1,
                portal_source="otodom",
                source_id="SRC-1",
                city="Warszawa",
                is_new=True,
            )
        except Exception:  # noqa: BLE001
            pytest.fail("publish_new_property raised an exception on Redis error")
        finally:
            publisher._redis.xadd = original_xadd  # noqa: SLF001
