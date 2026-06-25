"""
Cities listing endpoint with Redis cache-aside integration.

``GET /api/v1/cities`` — returns a list of cities with active property counts,
cached for 1 hour, with ``X-Cache`` headers indicating cache status.
"""

from typing import cast

import structlog
from fastapi import APIRouter, Depends, Request, Response
from scraper_base.database import create_async_engine, create_session_factory
from scraper_base.models import Property
from sqlalchemy import func as sa_func
from sqlalchemy import select

from app.core.config import get_settings
from app.schemas.city import CityCount
from app.services.cache_service import CacheService
from app.services.redis_client import RedisClient

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/cities", tags=["cities"])


async def _get_cache_service(request: Request) -> CacheService:
    """Dependency: return the cache service from app state."""
    return cast(CacheService, request.app.state.cache_service)


async def _get_redis_client(request: Request) -> RedisClient:
    """Dependency: return the Redis client from app state."""
    return cast(RedisClient, request.app.state.redis_client)


@router.get("")
async def list_cities(
    cache_service: CacheService = Depends(_get_cache_service),
    redis_client: RedisClient = Depends(_get_redis_client),  # noqa: ARG001
    request: Request = None,  # type: ignore[assignment]  # noqa: ARG001
) -> Response:
    """Get a list of cities with active property counts, cached for 1 hour.

    The response is sorted alphabetically by city name and includes an
    ``X-Cache`` header indicating whether the data was served from Redis
    (``hit``), freshly computed (``miss``), or from the database because
    Redis was unavailable (``miss (fallback)``).

    Args:
        cache_service: Injected cache service.
        redis_client: Injected Redis client (unused but required for Depends).
        request: The FastAPI request object.

    Returns:
        A ``Response`` with JSON body and ``X-Cache`` header.

    """
    settings = get_settings()

    # ── Static cache key for cities ─────────────────────────────────────
    cache_key = settings.CITIES_CACHE_KEY_PREFIX

    # ── Define the compute function (DB query) ──────────────────────────
    async def query_db() -> str:
        """Query the database for city counts and serialize to JSON."""
        try:
            engine = create_async_engine(
                database_url=settings.DATABASE_URL,
                pool_size=settings.DB_POOL_SIZE,
            )
            session_factory = create_session_factory(engine)
            async with session_factory() as session:
                try:
                    # Build aggregation query
                    stmt = (
                        select(
                            Property.city,
                            sa_func.count().label("count"),
                        )
                        .where(
                            Property.is_active.is_(True),
                            Property.is_canonical.is_(True),
                        )
                        .group_by(Property.city)
                        .order_by(Property.city.asc())
                    )
                    result = await session.execute(stmt)
                    rows = result.all()

                    # Map to CityCount schema
                    # Index-based access avoids mypy issues with labeled
                    # SQLAlchemy aggregation columns
                    cities = [
                        CityCount(city=str(row[0]), count=int(row[1]))
                        for row in rows
                    ]

                    # Serialize as JSON array
                    import json  # noqa: PLC0415

                    return json.dumps(
                        [c.model_dump() for c in cities],
                        ensure_ascii=False,
                    )
                finally:
                    await engine.dispose()
        except Exception:  # noqa: BLE001
            logger.warning("DB query failed for cities, returning empty results", exc_info=True)
            return "[]"

    # ── Cache-aside read ────────────────────────────────────────────────
    json_data, cache_status = await cache_service.get_or_compute(
        key=cache_key,
        compute=query_db,
        ttl=settings.CITIES_CACHE_TTL,
        endpoint="cities",
        key_prefix=settings.CITIES_CACHE_KEY_PREFIX,
    )

    # ── Build response ──────────────────────────────────────────────────
    headers: dict[str, str] = {
        "X-Cache": cache_status,
        "Content-Type": "application/json",
    }

    return Response(
        content=json_data,
        status_code=200,
        headers=headers,
    )
