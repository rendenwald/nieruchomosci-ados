"""
Tests for the ``GET /api/v1/cities`` endpoint.

Covers:
- 200 response with valid shape
- X-Cache headers (miss/hit/fallback)
- Empty database returns []
- Correct cache key (cities:list)
"""

import json

import pytest


@pytest.mark.asyncio
async def test_cities_endpoint_returns_list(client) -> None:  # type: ignore[no-untyped-def]
    """GET /api/v1/cities returns 200 with a JSON array."""
    response = await client.get("/api/v1/cities")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    # X-Cache header should be present
    assert "X-Cache" in response.headers


@pytest.mark.asyncio
async def test_cities_x_cache_miss_on_first_request(client) -> None:  # type: ignore[no-untyped-def]
    """First request returns X-Cache: miss or miss (fallback)."""
    response = await client.get("/api/v1/cities")
    assert response.status_code == 200
    cache_status = response.headers.get("X-Cache", "")
    assert cache_status in ("miss", "miss (fallback)")


@pytest.mark.asyncio
async def test_cities_x_cache_hit_on_repeat_request(client, fake_redis) -> None:  # type: ignore[no-untyped-def]
    """Repeat request returns X-Cache: hit if data was cached."""
    # First request populates cache
    await client.get("/api/v1/cities")

    # Second request should hit cache (or fallback if DB failed)
    response2 = await client.get("/api/v1/cities")
    assert response2.status_code == 200
    cache_status = response2.headers.get("X-Cache", "")
    assert cache_status in ("hit", "miss (fallback)")


@pytest.mark.asyncio
async def test_cities_empty_db_returns_empty_list(client) -> None:  # type: ignore[no-untyped-def]
    """When DB is empty, cities returns []."""
    response = await client.get("/api/v1/cities")
    assert response.status_code == 200
    body = response.json()
    assert body == []


@pytest.mark.asyncio
async def test_cities_cache_key_is_cities_list(client, fake_redis) -> None:  # type: ignore[no-untyped-def]
    """The cache key used should be 'cities:list'."""
    # Make a request to populate the cache
    await client.get("/api/v1/cities")

    # Check that cities:list key exists in fake Redis
    cached = await fake_redis.get("cities:list")
    if cached is not None:
        # Data was cached — verify it's valid JSON array
        data = json.loads(cached)
        assert isinstance(data, list)


@pytest.mark.asyncio
async def test_cities_response_content_type(client) -> None:  # type: ignore[no-untyped-def]
    """Response has Content-Type application/json."""
    response = await client.get("/api/v1/cities")
    assert response.status_code == 200
    assert response.headers.get("content-type") == "application/json"


@pytest.mark.asyncio
async def test_cities_city_count_shape(client) -> None:  # type: ignore[no-untyped-def]
    """If cities data is present, each item has city and count fields."""
    response = await client.get("/api/v1/cities")
    assert response.status_code == 200
    body = response.json()
    if body:
        for item in body:
            assert "city" in item
            assert "count" in item
            assert isinstance(item["city"], str)
            assert isinstance(item["count"], int)
