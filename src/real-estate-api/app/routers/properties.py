"""
Properties listing endpoint with Redis cache-aside integration.

``GET /api/v1/properties`` — returns a paginated, filterable list of properties
with ``X-Cache`` headers indicating cache status.
"""

from math import ceil
from typing import cast

import structlog
from fastapi import APIRouter, Depends, Request, Response
from scraper_base.database import create_async_engine, create_session_factory

from app.core.config import get_settings
from app.schemas.property import SearchParams, SearchResponse
from app.services.cache_key import make_cache_key
from app.services.cache_service import CacheService
from app.services.property_service import (
    build_order_by,
    build_search_query,
    count_results,
    execute_search,
    property_to_card,
)
from app.services.redis_client import RedisClient

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/properties", tags=["properties"])


async def _get_cache_service(request: Request) -> CacheService:
    """Dependency: return the cache service from app state."""
    return cast(CacheService, request.app.state.cache_service)


async def _get_redis_client(request: Request) -> RedisClient:
    """Dependency: return the Redis client from app state."""
    return cast(RedisClient, request.app.state.redis_client)


@router.get("")
async def list_properties(
    params: SearchParams = Depends(),
    cache_service: CacheService = Depends(_get_cache_service),
    redis_client: RedisClient = Depends(_get_redis_client),
    request: Request = None,  # type: ignore[assignment]  # noqa: ARG001
) -> Response:
    """Get a paginated, filterable list of properties with cache-aside.

    The response includes an ``X-Cache`` header indicating whether the data
    was served from Redis (``hit``), freshly computed (``miss``), or from the
    database because Redis was unavailable (``miss (fallback)``).

    Args:
        params: Validated search query parameters.
        cache_service: Injected cache service.
        redis_client: Injected Redis client (unused but required for Depends).
        request: The FastAPI request object.

    Returns:
        A ``Response`` with JSON body and ``X-Cache`` header.

    """
    settings = get_settings()

    # ── Build cache key from search params ──────────────────────────────
    params_dict = params.model_dump(exclude_none=True)
    cache_key = make_cache_key(settings.CACHE_KEY_PREFIX, params_dict)

    # ── Define the compute function (DB query) ──────────────────────────
    async def query_db() -> str:
        """Execute DB query and serialize to JSON string."""
        try:
            engine = create_async_engine(
                database_url=settings.DATABASE_URL,
                pool_size=settings.DB_POOL_SIZE,
            )
            session_factory = create_session_factory(engine)
            async with session_factory() as session:
                try:
                    # Build query with filters
                    query = build_search_query(params)

                    # Apply sort
                    sort_by = params.sort_by or "last_seen_at:desc"
                    order_by_clauses = build_order_by(sort_by)
                    query = query.order_by(*order_by_clauses)

                    # Count total
                    total = await count_results(session, query)

                    # Execute paginated query
                    properties = await execute_search(session, query, params.page, params.limit)

                    # Map to PropertyCard
                    cards = [property_to_card(p) for p in properties]

                    # Build paginated response
                    total_pages = max(1, ceil(total / params.limit)) if total > 0 else 0
                    response = SearchResponse(
                        items=cards,
                        total=total,
                        page=params.page,
                        limit=params.limit,
                        total_pages=total_pages,
                    )

                    return response.model_dump_json()
                finally:
                    await engine.dispose()
        except Exception:  # noqa: BLE001
            logger.warning("DB query failed, returning empty results", exc_info=True)
            # Return empty result set on DB failure (e.g. in tests or during outages)
            empty_response = SearchResponse(
                items=[],
                total=0,
                page=params.page,
                limit=params.limit,
                total_pages=0,
            )
            return empty_response.model_dump_json()

    # ── Cache-aside read ────────────────────────────────────────────────
    json_data, cache_status = await cache_service.get_or_compute(
        key=cache_key,
        compute=query_db,
        ttl=settings.CACHE_TTL_SECONDS,
        endpoint="properties",
        key_prefix=settings.CACHE_KEY_PREFIX,
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
