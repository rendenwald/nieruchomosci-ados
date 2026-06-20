"""
Database utility helpers.

Provides convenience functions for initialisation and health-checking.
"""

import structlog
from sqlalchemy import func as sa_func
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from scraper_base.models import Property

logger = structlog.get_logger(__name__)


async def check_connection(engine: AsyncEngine) -> bool:
    """Return ``True`` if the database is reachable.

    Args:
        engine: An ``AsyncEngine`` instance.

    Returns:
        ``True`` if the database responds, ``False`` otherwise.
    """
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Database health check failed", error=str(exc))
        return False


async def property_count(session: AsyncSession, portal: str | None = None) -> int:
    """Return the total number of properties, optionally filtered by portal."""
    stmt = select(sa_func.count(Property.id))
    if portal:
        stmt = stmt.where(Property.portal_source == portal)
    result = await session.execute(stmt)
    return result.scalar_one()
