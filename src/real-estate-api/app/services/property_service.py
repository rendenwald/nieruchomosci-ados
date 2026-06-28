"""
Property search service with SQLAlchemy query building and pagination.

Integrates with ``scrapper-base`` for the ``Property`` ORM model and
async database session management.
"""

import re
from typing import Any

import structlog
from scraper_base.models import Property
from sqlalchemy import func as sa_func
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from app.schemas.property import PropertyCard, SearchParams

logger = structlog.get_logger(__name__)

# Mapping of sort field names to SQLAlchemy column attributes.
# Only fields listed here are valid sort targets.
SORTABLE_FIELDS: dict[str, object] = {
    "price": Property.price,
    "area": Property.area,
    "rooms": Property.rooms,
    "scraped_at": Property.scraped_at,
    "last_seen_at": Property.last_seen_at,
    "price_per_m2": Property.price_per_m2,
    "city": Property.city,
    "province": Property.province,
    "created_at": Property.source_created_at,
}


def build_search_query(params: SearchParams) -> Select[Any]:
    """Construct a SQLAlchemy ``SELECT`` query from search parameters.

    Applies WHERE clauses for each non-``None`` filter parameter.
    Always filters for active canonical properties.

    Args:
        params: Validated search parameters.

    Returns:
        A ``Select`` statement ready for execution or count.

    """
    stmt = select(Property).where(
        Property.is_active.is_(True),
        Property.is_canonical.is_(True),
    )

    # City: case-insensitive partial match
    if params.city:
        stmt = stmt.where(Property.city.ilike(f"%{params.city}%"))

    # Exact match filters
    if params.property_type:
        stmt = stmt.where(Property.property_type == params.property_type)
    if params.auction_type:
        stmt = stmt.where(Property.auction_type == params.auction_type)
    if params.market_type:
        stmt = stmt.where(Property.market_type == params.market_type)

    # Range filters
    if params.price_min is not None:
        stmt = stmt.where(Property.price >= params.price_min)
    if params.price_max is not None:
        stmt = stmt.where(Property.price <= params.price_max)
    if params.area_min is not None:
        stmt = stmt.where(Property.area >= params.area_min)
    if params.area_max is not None:
        stmt = stmt.where(Property.area <= params.area_max)

    # Rooms
    if params.rooms:
        stmt = stmt.where(Property.rooms == params.rooms)

    return stmt


def build_order_by(sort_by: str) -> list[Any]:
    """Parse a sort string and return SQLAlchemy ``order_by`` expressions.

    Format: ``field:direction`` where field is one of the ``SORTABLE_FIELDS``
    keys and direction is ``asc`` or ``desc``. Always appends ``Property.id``
    as a tiebreaker for deterministic pagination.

    Args:
        sort_by: Sort string in ``field:direction`` format.

    Returns:
        A list of SQLAlchemy column expression for ``.order_by()``.

    Raises:
        ValueError: If the field is not in ``SORTABLE_FIELDS``.

    """
    field_str, direction = sort_by.split(":")
    column = SORTABLE_FIELDS.get(field_str)
    if column is None:
        msg = f"Invalid sort field: '{field_str}'. Valid fields: {', '.join(SORTABLE_FIELDS)}"
        raise ValueError(msg)

    if direction == "desc":
        return [column.desc().nullslast(), Property.id.asc()]  # type: ignore[attr-defined]
    return [column.asc().nullslast(), Property.id.asc()]  # type: ignore[attr-defined]


async def count_results(session: AsyncSession, query: Select[Any]) -> int:
    """Count total results for a search query.

    Wraps the query in a ``COUNT(*)`` subquery.

    Args:
        session: Async database session.
        query: The base ``SELECT`` statement (without pagination).

    Returns:
        Total number of matching records.

    """
    count_query = select(sa_func.count()).select_from(query.subquery())
    result = await session.execute(count_query)
    return result.scalar_one()


async def execute_search(
    session: AsyncSession,
    query: Select[Any],
    page: int,
    limit: int,
) -> list[Property]:
    """Execute a search query with pagination.

    Args:
        session: Async database session.
        query: The base ``SELECT`` statement (without pagination).
        page: Page number (1-indexed).
        limit: Items per page.

    Returns:
        List of ``Property`` ORM objects for the requested page.

    """
    offset = (page - 1) * limit
    paginated_query = query.offset(offset).limit(limit)
    result = await session.execute(paginated_query)
    return list(result.scalars().all())


# Regex to extract SHA256 from MinIO object paths like
# ``photos/ab/cd/abc123...def.jpg``
_SHA256_PATH_PATTERN = re.compile(r"/([a-f0-9]{64})\.jpg$")


def _minio_path_to_api_url(path: str) -> str | None:
    """Convert a MinIO object path to a CDN-friendly API URL.

    Given a MinIO path like ``photos/ab/cd/abc123...def.jpg``, extracts
    the SHA256 hash and returns ``/api/v1/photos/abc123...def.jpg``.

    Args:
        path: MinIO object path.

    Returns:
        API URL string, or ``None`` if the path does not match the expected
        pattern.

    """
    match = _SHA256_PATH_PATTERN.search(path)
    if match:
        return f"/api/v1/photos/{match.group(1)}.jpg"
    return None


def property_to_card(prop: Property) -> PropertyCard:
    """Convert a ``Property`` ORM object to a ``PropertyCard`` schema.

    Extracts the first photo URL from the photos dict/list if present.
    Uses CDN-friendly API URLs (based on MinIO SHA256 paths) when available,
    falling back to original source URLs.

    Args:
        prop: The ``Property`` ORM object.

    Returns:
        A ``PropertyCard`` instance.

    """
    # Extract first photo URL
    photo_urls: list[str] | None = None
    if prop.photos:
        if isinstance(prop.photos, list):
            photo_urls = []
            for p in prop.photos[:5]:  # Limit to 5 thumbnails
                if isinstance(p, dict):
                    # Try MinIO path first (CDN-friendly), fall back to original URL
                    path = p.get("path")
                    if path and isinstance(path, str):
                        api_url = _minio_path_to_api_url(path)
                        if api_url:
                            photo_urls.append(api_url)
                            continue
                    # Fall back to original URL
                    url = p.get("url", "")
                    if isinstance(url, str) and url:
                        photo_urls.append(url)
                elif isinstance(p, str):
                    photo_urls.append(p)
        elif isinstance(prop.photos, dict):
            url = prop.photos.get("url") or prop.photos.get("thumbnail", "")
            if url:
                photo_urls = [url]

    return PropertyCard(
        id=prop.id,
        title=prop.title,
        property_type=prop.property_type,
        price=prop.price,
        price_currency=prop.price_currency,
        price_per_m2=prop.price_per_m2,
        area=prop.area,
        rooms=prop.rooms,
        city=prop.city,
        district=prop.district,
        province=prop.province,
        latitude=prop.latitude,
        longitude=prop.longitude,
        agency_name=prop.agency_name,
        photos=photo_urls,
        source_url=prop.source_url,
        portal_source=prop.portal_source,
        created_at=prop.scraped_at,
    )
